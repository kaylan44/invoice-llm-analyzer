"""Retrieval tests (week 2, step 9): exact matches, hybrid search, categories, embeddings.

Database tests use the local Postgres and a fake bag-of-words embedder (no network).
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from invoice_api.embeddings import CachedEmbedder, document_text, embed, query_text
from invoice_api.matching import (
    add_supplier,
    load_categories,
    match_supplier,
    search_categories,
)
from invoice_api.schema import InvoiceExtraction

from .fakes import fake_embedder


@pytest.fixture
def directory(db: psycopg.Connection) -> psycopg.Connection:
    add_supplier(
        db,
        "Papeterie du Rhône SAS",
        embedder=fake_embedder,
        vat_number="FR21 842 157 398",
        siret="842 157 398 00012",
    )
    add_supplier(db, "Transports Lemoine", embedder=fake_embedder, vat_number="FR55139117188")
    add_supplier(db, "Porter, Smith and Johnson", embedder=fake_embedder, vat_number="GB835030564")
    return db  # fmt: skip


def test_exact_match_on_vat_number_ignores_spaces(directory: psycopg.Connection) -> None:
    e = InvoiceExtraction(supplier_name="anything", supplier_vat_number="fr21842157398")
    m = match_supplier(directory, e, embedder=fake_embedder)
    assert (m.supplier_id, m.method) == (1, "vat_number")


def test_exact_match_on_siret_when_vat_is_unknown(directory: psycopg.Connection) -> None:
    e = InvoiceExtraction(supplier_vat_number="FR00000000000", supplier_siret="84215739800012")
    assert match_supplier(directory, e, embedder=fake_embedder).method == "siret"


def test_hybrid_match_on_a_name_variant(directory: psycopg.Connection) -> None:
    e = InvoiceExtraction(supplier_name="PAPETERIE DU RHONE")
    m = match_supplier(directory, e, embedder=fake_embedder)
    assert (m.supplier_id, m.method) == (1, "hybrid")
    assert m.candidates[0].full_text_rank == 1


def test_unknown_supplier_is_not_forced_onto_a_neighbour(directory: psycopg.Connection) -> None:
    e = InvoiceExtraction(supplier_name="Boulangerie Martin")
    m = match_supplier(directory, e, embedder=fake_embedder)
    assert (m.supplier_id, m.method) == (None, "none")


def test_categories_are_loaded_and_searched(db: psycopg.Connection) -> None:
    assert load_categories(db, embedder=fake_embedder) >= 10
    assert load_categories(db, embedder=fake_embedder) >= 10  # upsert: idempotent
    (toner, meal) = search_categories(
        db, ["Cartouches toner noir", "Repas d'affaires"], embedder=fake_embedder, k=3
    )
    assert toner[0].key == "6064"
    assert meal[0].key == "6257"


# --- Embeddings (no database) ----------------------------------------------------------


def test_prefixes() -> None:
    assert query_text("toner") == "task: search result | query: toner"
    assert document_text("Papier, classeurs") == "title: none | text: Papier, classeurs"
    assert document_text("Papier", title="Fournitures") == "title: Fournitures | text: Papier"


class FakeEmbedModels:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    def embed_content(self, *, model: str, contents: list[Any], config: Any) -> Any:
        self.calls.append(contents)
        values = [[float(i)] * 768 for i in range(len(contents))]
        return SimpleNamespace(embeddings=[SimpleNamespace(values=v) for v in values])


def test_embed_sends_one_content_per_text_in_batches() -> None:
    client = SimpleNamespace(models=FakeEmbedModels())
    vectors = embed([f"t{i}" for i in range(120)], client=client, model="m")
    assert len(vectors) == 120
    assert [len(batch) for batch in client.models.calls] == [50, 50, 20]
    # One Content per text: a plain list of strings would be embedded as ONE text.
    assert client.models.calls[0][0].parts[0].text == "t0"


def test_cache_avoids_repeated_calls(tmp_path: Path) -> None:
    client = SimpleNamespace(models=FakeEmbedModels())
    cache = tmp_path / "cache.jsonl"
    CachedEmbedder(client, cache, model="m")(["a", "b", "a"])
    assert len(client.models.calls) == 1 and len(client.models.calls[0]) == 2  # "a" once
    again = CachedEmbedder(client, cache, model="m")  # reloaded from disk
    again(["b", "a"])
    assert len(client.models.calls) == 1
    assert len(cache.read_text().splitlines()) == 2
    assert json.loads(cache.read_text().splitlines()[0])["key"]
