"""Database access: connection, migrations, and helpers shared by the API and the evals.

Locally the database is the docker compose Postgres + pgvector; in production it is Supabase.
Both run the same SQL files from supabase/migrations/. In production those files are applied
by the Supabase CLI (`supabase db push`), never by this module.

psycopg 3 is used directly, without an ORM: the queries are part of what this project
teaches, so they stay visible as SQL.
"""

import os
from collections.abc import Sequence
from pathlib import Path

import psycopg

# api/src/invoice_api/db.py -> repository root is three levels above the package.
MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"
DEFAULT_LOCAL_URL = "postgresql://postgres:postgres@localhost:54329/invoices"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_LOCAL_URL)


def connect(url: str | None = None, *, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(url or database_url(), autocommit=autocommit)


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply, in file name order, the migrations not yet recorded. Returns the applied files.

    Each file runs in its own transaction with its bookkeeping row: a failing migration
    leaves no half-applied schema behind.
    """
    conn.execute(
        "create table if not exists schema_migrations ("
        " version text primary key, name text not null,"
        " applied_at timestamptz not null default now())"
    )
    conn.commit()
    applied = {row[0] for row in conn.execute("select version from schema_migrations")}
    done = []
    for path in sorted(directory.glob("*.sql")):
        version = path.name.split("_", 1)[0]
        if version in applied:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))  # several statements: no parameters
            conn.execute(
                "insert into schema_migrations (version, name) values (%s, %s)",
                (version, path.name),
            )
        done.append(path.name)
    conn.commit()
    return done


def to_vector(values: Sequence[float]) -> str:
    """pgvector's text format, "[0.1,0.2,...]", passed as a parameter and cast with ::vector."""
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"
