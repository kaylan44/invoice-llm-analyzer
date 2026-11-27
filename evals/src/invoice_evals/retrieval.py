"""Retrieval eval: can the search find the right supplier and the right category?

Supplier directory = the suppliers of the dataset + distractors (other fake companies).
Queries = deformed versions of the dataset suppliers' names, as an extraction might return
them: upper case without accents, legal form dropped, one typo. Category queries = the
catalog line labels plus realistic labels never seen in the catalog.

Each query is run with three settings of the same SQL function:
  full_text  (semantic weight 0)   lexical only
  semantic   (full-text weight 0)  vectors only
  hybrid     (both weights 1)      fused by RRF

Metrics, per method:
  recall@k   share of queries whose right answer is in the top k
  MRR        mean of 1/rank of the right answer (0 when absent): rewards ranking it first
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from faker import Faker

from invoice_api.embeddings import Embedder
from invoice_api.matching import add_supplier, load_categories, search_categories, search_suppliers
from invoice_api.schema import InvoiceTruth
from invoice_evals.generator import CATEGORY_OF

METHODS = {"full_text": (1.0, 0.0), "semantic": (0.0, 1.0), "hybrid": (1.0, 1.0)}
KS = (1, 3, 5)
SEARCH_DEPTH = 10

LEGAL_FORMS = {
    "sas", "sarl", "sa", "sasu", "eurl", "sci", "snc", "et", "fils", "ltd", "limited", "plc",
    "llc", "inc", "and", "co",
}  # fmt: skip

# Line labels absent from the catalog, with the category an accountant would choose.
EXTRA_LINE_QUERIES: list[tuple[str, str]] = [
    ("Stylos bille bleus, boîte de 50", "6064"),
    ("Enveloppes C4 kraft", "6064"),
    ("Printer ink cartridge, cyan", "6064"),
    ("Déjeuner client restaurant Le Bistrot", "6257"),
    ("Team dinner with customer", "6257"),
    ("Livraison express J+1", "6241"),
    ("Pallet freight Lyon to Paris", "6241"),
    ("Licence annuelle CRM, 5 utilisateurs", "6135"),
    ("Cloud hosting subscription, December", "6135"),
    ("Intervention dépannage serveur", "6156"),
    ("Laptop repair and diagnostics", "6156"),
    ("Abonnement revue professionnelle", "6181"),
    ("Accounting textbook", "6181"),
    ("Perceuse sans fil", "6063"),
    ("Office chair cushion", "6063"),
    ("Billet de train Paris-Lyon", "6251"),
    ("Forfait mobile professionnel", "6262"),
    ("Honoraires expert-comptable bilan", "6226"),
]


@dataclass(frozen=True)
class Query:
    text: str
    expected: int | str  # supplier id or category code
    kind: str  # how the query was built


def name_variants(name: str, rng: random.Random) -> list[tuple[str, str]]:
    """Three deformations of a supplier name, as an imperfect extraction could produce."""
    words = name.replace(",", " ").split()
    variants = [("upper", name.upper())]
    kept = [w for w in words if w.lower().replace(".", "").strip("&") not in LEGAL_FORMS]
    if kept and len(kept) < len(words):
        variants.append(("no_legal_form", " ".join(kept)))
    longest = max(range(len(words)), key=lambda i: len(words[i]))
    word = words[longest]
    if len(word) > 3:
        i = rng.randrange(1, len(word) - 1)
        typo = word[:i] + word[i + 1 :]  # one letter dropped
        variants.append(("typo", " ".join(words[:longest] + [typo] + words[longest + 1 :])))
    return variants


def build_suppliers(
    conn: psycopg.Connection,
    truths: Sequence[InvoiceTruth],
    *,
    embedder: Embedder,
    distractors: int,
    seed: int,
) -> list[Query]:
    """Insert the dataset suppliers and distractors; return the supplier queries."""
    rng = random.Random(seed)
    queries = []
    seen: set[str] = set()
    for t in truths:
        if t.supplier_name in seen:
            continue
        seen.add(t.supplier_name)
        supplier_id = add_supplier(
            conn, t.supplier_name, embedder=embedder,
            vat_number=t.supplier_vat_number, siret=t.supplier_siret,
        )  # fmt: skip
        queries += [
            Query(text, supplier_id, kind) for kind, text in name_variants(t.supplier_name, rng)
        ]
    for i in range(distractors):
        fake = Faker("fr_FR" if i % 2 == 0 else "en_GB")
        fake.seed_instance(seed * 1000 + i)
        name = fake.company()
        if name not in seen:
            seen.add(name)
            add_supplier(conn, name, embedder=embedder)
    return queries


def category_queries() -> list[Query]:
    catalog = [Query(desc, code, "catalog") for desc, code in sorted(CATEGORY_OF.items())]
    extra = [Query(desc, code, "unseen") for desc, code in EXTRA_LINE_QUERIES]
    return catalog + extra


def rank_of(expected: int | str, keys: Sequence[int | str]) -> int | None:
    return keys.index(expected) + 1 if expected in keys else None


def scores(ranks: Sequence[int | None]) -> dict[str, float]:
    n = len(ranks)
    result = {f"recall@{k}": round(sum(r is not None and r <= k for r in ranks) / n, 4) for k in KS}
    result["mrr"] = round(sum(1 / r for r in ranks if r is not None) / n, 4)
    return result


def evaluate(
    conn: psycopg.Connection, supplier_qs: list[Query], category_qs: list[Query], *,
    embedder: Embedder,
) -> dict[str, Any]:  # fmt: skip
    report: dict[str, Any] = {"suppliers": {}, "categories": {}, "failures": []}
    for method, (ft, sem) in METHODS.items():
        ranks = []
        for q in supplier_qs:
            found = search_suppliers(
                conn, q.text, embedder=embedder, k=SEARCH_DEPTH,
                full_text_weight=ft, semantic_weight=sem,
            )  # fmt: skip
            ranks.append(rank_of(q.expected, [c.key for c in found]))
            if method == "hybrid" and ranks[-1] != 1:
                top = found[0].label if found else None
                report["failures"].append(
                    {"type": "supplier", "query": q.text, "kind": q.kind, "rank": ranks[-1],
                     "top": top}
                )  # fmt: skip
        report["suppliers"][method] = scores(ranks)

        results = search_categories(
            conn, [q.text for q in category_qs], embedder=embedder, k=SEARCH_DEPTH,
            full_text_weight=ft, semantic_weight=sem,
        )  # fmt: skip
        ranks = [
            rank_of(q.expected, [c.key for c in found])
            for q, found in zip(category_qs, results, strict=True)
        ]
        report["categories"][method] = scores(ranks)
        for q, found, rank in zip(category_qs, results, ranks, strict=True):
            if method == "hybrid" and rank != 1:
                report["failures"].append(
                    {"type": "category", "query": q.text, "kind": q.kind, "rank": rank,
                     "expected": q.expected, "top": found[0].key if found else None}
                )  # fmt: skip
    report["n_supplier_queries"] = len(supplier_qs)
    report["n_category_queries"] = len(category_qs)
    return report


def prepare(
    conn: psycopg.Connection, truths: Sequence[InvoiceTruth], *, embedder: Embedder,
    distractors: int = 60, seed: int = 7,
) -> tuple[list[Query], list[Query]]:  # fmt: skip
    conn.execute("truncate jobs, extractions, invoice_lines, invoices, suppliers, categories"
                 " restart identity cascade")  # fmt: skip
    supplier_qs = build_suppliers(
        conn, truths, embedder=embedder, distractors=distractors, seed=seed
    )
    load_categories(conn, embedder=embedder)
    conn.commit()
    return supplier_qs, category_queries()


def render_retrieval_report(report: dict[str, Any], model: str) -> str:
    lines = [
        "# Évaluation du rapprochement (RAG)",
        "",
        f"Embeddings `{model}` (768 dimensions). Fournisseurs : {report['n_supplier_queries']}"
        f" requêtes ; catégories : {report['n_category_queries']} requêtes.",
        "",
    ]
    for kind, title in (("suppliers", "Fournisseurs"), ("categories", "Catégories")):
        lines += [f"## {title}", "", "| Méthode | recall@1 | recall@3 | recall@5 | MRR |",
                  "| --- | --- | --- | --- | --- |"]  # fmt: skip
        for method, s in report[kind].items():
            lines.append(
                f"| {method} | {s['recall@1']:.0%} | {s['recall@3']:.0%} | {s['recall@5']:.0%}"
                f" | {s['mrr']:.3f} |"
            )
        lines.append("")
    lines += ["## Requêtes que l'hybride ne classe pas en premier", ""]
    if not report["failures"]:
        lines.append("Aucune.")
    else:
        lines += [
            "| Type | Requête | Variante | Rang | En tête |",
            "| --- | --- | --- | --- | --- |",
        ]
        for f in report["failures"]:
            lines.append(
                f"| {f['type']} | {f['query']} | {f['kind']} | {f['rank'] or 'absent'}"
                f" | {f['top']} |"
            )
    return "\n".join(lines) + "\n"
