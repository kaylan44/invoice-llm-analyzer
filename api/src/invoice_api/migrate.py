"""Apply the migrations to the local database (DATABASE_URL, default: docker compose).

    docker compose up -d db
    uv run python -m invoice_api.migrate

Refuses to run against a Supabase host: production migrations go through
`supabase db push`, with explicit approval (see CLAUDE.md).
"""

from urllib.parse import urlparse

from dotenv import load_dotenv

from invoice_api.db import apply_migrations, connect, database_url


def main() -> None:
    load_dotenv()
    url = database_url()
    host = urlparse(url).hostname or ""
    if "supabase" in host:
        raise SystemExit(f"refusing to migrate {host}: use `supabase db push` for production")
    with connect(url) as conn:
        applied = apply_migrations(conn)
    print("\n".join(f"applied {name}" for name in applied) or "database already up to date")


if __name__ == "__main__":
    main()
