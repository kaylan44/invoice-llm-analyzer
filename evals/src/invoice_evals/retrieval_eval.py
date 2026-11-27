"""CLI: measure supplier and category retrieval (recall@k, MRR) on the local database.

    docker compose up -d db
    uv run python -m invoice_evals.retrieval_eval --data evals/data/week2 \
        --baseline evals/baselines/week2_retrieval

Uses a dedicated database, ``invoices_eval``, recreated from the migrations on every run,
so the eval never touches the development data. Embeddings are cached in
evals/results/embeddings_cache.jsonl (git-ignored): re-running costs no API call.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg
from dotenv import load_dotenv

from invoice_api.db import apply_migrations, database_url
from invoice_api.embeddings import CachedEmbedder, embedding_model
from invoice_api.extraction import make_client
from invoice_evals.generator import GeneratedInvoice
from invoice_evals.harness import load_manifest
from invoice_evals.retrieval import evaluate, prepare, render_retrieval_report

EVAL_DB = "invoices_eval"


def eval_database_url() -> str:
    admin_url = database_url()
    if "supabase" in (urlparse(admin_url).hostname or ""):
        raise SystemExit("the retrieval eval only runs on the local database")
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f"drop database if exists {EVAL_DB} with (force)")
        admin.execute(f"create database {EVAL_DB}")
    return urlunparse(urlparse(admin_url)._replace(path=f"/{EVAL_DB}"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Measure supplier and category retrieval.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--cache", type=Path, default=Path("evals/results/embeddings_cache.jsonl"))
    parser.add_argument("--baseline", type=Path, default=None, help="path without extension")
    args = parser.parse_args(argv)

    load_dotenv()
    truths = [
        GeneratedInvoice.model_validate_json((args.data / e["file"]).read_text()).truth
        for e in load_manifest(args.data)
    ]
    embedder = CachedEmbedder(make_client(), args.cache)
    with psycopg.connect(eval_database_url()) as conn:
        apply_migrations(conn)
        supplier_qs, category_qs = prepare(conn, truths, embedder=embedder)
        report = evaluate(conn, supplier_qs, category_qs, embedder=embedder)
    report["embedding_model"] = embedding_model()
    report["embedding_api_calls"] = embedder.calls
    markdown = render_retrieval_report(report, embedding_model())
    if args.baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.with_suffix(".json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        args.baseline.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(markdown)
    print(f"(embedding API calls this run: {embedder.calls})")


if __name__ == "__main__":
    main()
