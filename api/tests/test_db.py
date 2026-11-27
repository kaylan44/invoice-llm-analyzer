"""Database tests (week 2, step 7): migrations, constraints, RLS, hybrid search SQL.

They need the local Postgres (docker compose up -d db) and are skipped without it.
Vectors here are tiny hand-made ones padded to 768 dimensions, so the expected
nearest neighbour is known without calling an embedding model.
"""

import psycopg
import pytest

from invoice_api.db import apply_migrations, to_vector


def unit(i: int) -> str:
    """A 768-dim vector pointing along axis i: cosine distance 0 to itself, 1 to others."""
    values = [0.0] * 768
    values[i] = 1.0
    return to_vector(values)


def test_migrations_are_recorded_and_idempotent(db: psycopg.Connection) -> None:
    versions = [r[0] for r in db.execute("select version from schema_migrations")]
    assert versions == ["20261127090000"]
    assert apply_migrations(db) == []  # second run: nothing to do


def test_rls_is_enabled_on_every_table(db: psycopg.Connection) -> None:
    rows = db.execute(
        "select relname, relrowsecurity from pg_class where relname = any(%s)",
        (["suppliers", "categories", "invoices", "invoice_lines", "extractions", "jobs"],),
    ).fetchall()
    assert len(rows) == 6 and all(enabled for _, enabled in rows)


def test_vat_number_is_unique(db: psycopg.Connection) -> None:
    insert = "insert into suppliers (name, vat_number, search_text) values (%s, %s, %s)"
    db.execute(insert, ("A", "FR21842157398", "a"))
    with pytest.raises(psycopg.errors.UniqueViolation):
        db.execute(insert, ("B", "FR21842157398", "b"))


def test_fts_column_is_generated(db: psycopg.Connection) -> None:
    db.execute("insert into suppliers (name, search_text) values ('X', 'papeterie du rhone sas')")
    (fts,) = db.execute("select fts::text from suppliers").fetchone()
    assert "'papeterie'" in fts and "'rhone'" in fts


@pytest.fixture
def three_suppliers(db: psycopg.Connection) -> psycopg.Connection:
    rows = [
        ("Papeterie du Rhône SAS", "papeterie du rhone sas", unit(0)),
        ("Transports Lemoine", "transports lemoine", unit(1)),
        ("Atelier Durand SARL", "atelier durand sarl", unit(2)),
    ]
    for name, text, vec in rows:
        db.execute(
            "insert into suppliers (name, search_text, embedding) values (%s, %s, %s::vector)",
            (name, text, vec),
        )
    return db


def test_hybrid_search_both_methods_agree(three_suppliers: psycopg.Connection) -> None:
    rows = three_suppliers.execute(
        "select id, full_text_rank, semantic_rank from match_suppliers(%s, %s::vector, 3)",
        ("papeterie rhone", unit(0)),
    ).fetchall()
    assert rows[0] == (1, 1, 1)  # ranked first by both methods


def test_hybrid_search_survives_a_typo(three_suppliers: psycopg.Connection) -> None:
    # "Lemoyne" matches no word, but "transports" does: OR semantics keeps the candidate.
    (first,) = three_suppliers.execute(
        "select id from match_suppliers(%s, %s::vector, 1)", ("transports lemoyne", unit(1))
    ).fetchone()
    assert first == 2


def test_hybrid_search_falls_back_on_vectors(three_suppliers: psycopg.Connection) -> None:
    # No word in common at all: only the vector ranking contributes.
    row = three_suppliers.execute(
        "select id, full_text_rank, semantic_rank from match_suppliers(%s, %s::vector, 1)",
        ("zzz", unit(2)),
    ).fetchone()
    assert row == (3, None, 1)
