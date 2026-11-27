"""Retrieval: attach what the model read to known entities.

Supplier: exact match on VAT number, then SIRET (SQL equality, certain); otherwise hybrid
search on the name (full text + vectors fused by RRF, see the match_suppliers SQL function).
A hybrid candidate is only accepted when BOTH rankings found it: the full-text side proves
some words are shared, the vector side that the names are close as a whole. Otherwise the
invoice keeps the name as read and no supplier is attached ("none").

Category: hybrid search of each line description among the accounting categories; the top
candidate is proposed, the human confirms in review.
"""

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import psycopg

from invoice_api.db import to_vector
from invoice_api.embeddings import Embedder, document_text, query_text
from invoice_api.schema import InvoiceExtraction
from invoice_api.text import normalize_text

CATEGORIES_FILE = Path(__file__).parent / "reference" / "categories.json"

MatchMethod = Literal["vat_number", "siret", "hybrid", "none"]


@dataclass(frozen=True)
class Candidate:
    key: int | str  # supplier id or category code
    label: str
    score: float
    full_text_rank: int | None
    semantic_rank: int | None


@dataclass(frozen=True)
class SupplierMatch:
    supplier_id: int | None
    method: MatchMethod
    candidates: list[Candidate]


def normalize_vat(value: str) -> str:
    return re.sub(r"[\s.]", "", value).upper()


def normalize_siret(value: str) -> str:
    return re.sub(r"\D", "", value)


# --- Reference data ------------------------------------------------------------------


def add_supplier(
    conn: psycopg.Connection,
    name: str,
    *,
    embedder: Embedder,
    vat_number: str | None = None,
    siret: str | None = None,
    aliases: Sequence[str] = (),
) -> int:
    (vector,) = embedder([document_text(name)])
    row = conn.execute(
        "insert into suppliers (name, aliases, vat_number, siret, search_text, embedding)"
        " values (%s, %s, %s, %s, %s, %s::vector) returning id",
        (
            name,
            list(aliases),
            normalize_vat(vat_number) if vat_number else None,
            normalize_siret(siret) if siret else None,
            normalize_text(" ".join([name, *aliases])),
            to_vector(vector),
        ),
    ).fetchone()
    assert row is not None
    return int(row[0])


def load_categories(conn: psycopg.Connection, *, embedder: Embedder) -> int:
    """Insert or update the accounting categories from reference/categories.json."""
    categories = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
    vectors = embedder([document_text(c["description"], title=c["label"]) for c in categories])
    for c, vector in zip(categories, vectors, strict=True):
        conn.execute(
            "insert into categories (code, label, description, search_text, embedding)"
            " values (%s, %s, %s, %s, %s::vector)"
            " on conflict (code) do update set label = excluded.label,"
            " description = excluded.description, search_text = excluded.search_text,"
            " embedding = excluded.embedding",
            (
                c["code"],
                c["label"],
                c["description"],
                normalize_text(f"{c['label']} {c['description']}"),
                to_vector(vector),
            ),
        )
    return len(categories)


# --- Search --------------------------------------------------------------------------


def search_suppliers(
    conn: psycopg.Connection,
    name: str,
    *,
    embedder: Embedder,
    k: int = 5,
    full_text_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> list[Candidate]:
    (vector,) = embedder([query_text(name)])
    rows = conn.execute(
        "select m.id, s.name, m.score, m.full_text_rank, m.semantic_rank"
        " from match_suppliers(%s, %s::vector, %s, %s, %s) m join suppliers s using (id)"
        " where m.score > 0 order by m.score desc",
        (normalize_text(name), to_vector(vector), k, full_text_weight, semantic_weight),
    ).fetchall()
    return [Candidate(*row) for row in rows]


def search_categories(
    conn: psycopg.Connection,
    descriptions: Sequence[str],
    *,
    embedder: Embedder,
    k: int = 5,
    full_text_weight: float = 1.0,
    semantic_weight: float = 1.0,
) -> list[list[Candidate]]:
    """Candidates for each description; all queries are embedded in one call."""
    vectors = embedder([query_text(d) for d in descriptions])
    results = []
    for description, vector in zip(descriptions, vectors, strict=True):
        rows = conn.execute(
            "select m.code, c.label, m.score, m.full_text_rank, m.semantic_rank"
            " from match_categories(%s, %s::vector, %s, %s, %s) m join categories c using (code)"
            " where m.score > 0 order by m.score desc",
            (normalize_text(description), to_vector(vector), k, full_text_weight, semantic_weight),
        ).fetchall()
        results.append([Candidate(*row) for row in rows])
    return results


def match_supplier(
    conn: psycopg.Connection, extraction: InvoiceExtraction, *, embedder: Embedder, k: int = 5
) -> SupplierMatch:
    if extraction.supplier_vat_number:
        row = conn.execute(
            "select id from suppliers where vat_number = %s",
            (normalize_vat(extraction.supplier_vat_number),),
        ).fetchone()
        if row:
            return SupplierMatch(row[0], "vat_number", [])
    if extraction.supplier_siret:
        row = conn.execute(
            "select id from suppliers where siret = %s",
            (normalize_siret(extraction.supplier_siret),),
        ).fetchone()
        if row:
            return SupplierMatch(row[0], "siret", [])
    if not extraction.supplier_name:
        return SupplierMatch(None, "none", [])

    candidates = search_suppliers(conn, extraction.supplier_name, embedder=embedder, k=k)
    best = candidates[0] if candidates else None
    if best and best.full_text_rank is not None and best.semantic_rank is not None:
        return SupplierMatch(int(best.key), "hybrid", candidates)
    return SupplierMatch(None, "none", candidates)
