"""Shared pytest fixtures.

``db`` gives a connection to a throwaway database: created once per test session on the
local Postgres (DATABASE_URL, default docker compose), migrated, emptied before each test,
dropped at the end. Tests that use it are skipped when the database is not running.
"""

import uuid
from collections.abc import Iterator
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest

from invoice_api.db import apply_migrations, database_url

TABLES = ("jobs", "extractions", "invoice_lines", "invoices", "suppliers", "categories")


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    admin_url = database_url()
    if "supabase" in (urlparse(admin_url).hostname or ""):
        pytest.skip("tests never run against Supabase")
    name = f"test_{uuid.uuid4().hex[:8]}"
    try:
        admin = psycopg.connect(admin_url, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("local Postgres not running (docker compose up -d db)")
    with admin:
        admin.execute(f'create database "{name}"')
    url = urlunparse(urlparse(admin_url)._replace(path=f"/{name}"))
    with psycopg.connect(url) as conn:
        apply_migrations(conn)
    yield url
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'drop database "{name}" with (force)')


@pytest.fixture
def db(db_url: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(db_url) as conn:
        conn.execute(f"truncate {', '.join(TABLES)} restart identity cascade")
        conn.commit()
        yield conn
