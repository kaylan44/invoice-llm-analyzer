"""Load the accounting categories (with their embeddings) into DATABASE_URL.

    uv run python -m invoice_api.seed                  # local database
    uv run python -m invoice_api.seed --production     # Supabase: only with explicit approval

Calls the embedding model once for all categories. Idempotent (upsert on the code).
"""

import argparse
from urllib.parse import urlparse

from dotenv import load_dotenv

from invoice_api.db import connect, database_url
from invoice_api.embeddings import embed
from invoice_api.extraction import make_client
from invoice_api.matching import load_categories


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load accounting categories.")
    parser.add_argument("--production", action="store_true", help="allow a Supabase host")
    args = parser.parse_args(argv)
    load_dotenv()
    host = urlparse(database_url()).hostname or ""
    if "supabase" in host and not args.production:
        raise SystemExit(f"{host} is production: pass --production, after approval")
    client = make_client()
    with connect() as conn:
        count = load_categories(conn, embedder=lambda texts: embed(texts, client=client))
        conn.commit()
    print(f"{count} categories loaded into {host}")


if __name__ == "__main__":
    main()
