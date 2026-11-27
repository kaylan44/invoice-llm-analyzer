"""Extraction pipeline v1: fixed order, no agent.

    extract -> checks -> supplier match -> duplicate check -> line categories -> save

Every step's result is stored: the extraction (raw answer, tokens, checks) in ``extractions``,
the fields in ``invoices`` and ``invoice_lines``, the progress in ``jobs``. The invoice ends
"to_review" with its reasons when anything failed, "pending" otherwise. No automatic retry in
v1: a human looks at what the checks flag.
"""

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import tuple_row

from invoice_api.checks import run_checks
from invoice_api.embeddings import Embedder
from invoice_api.extraction import extract
from invoice_api.matching import match_supplier, search_categories
from invoice_api.schema import InvoiceExtraction


def create_invoice(conn: psycopg.Connection, file_path: str) -> tuple[UUID, UUID]:
    """Register an uploaded document and its job. Returns (invoice_id, job_id)."""
    cur = conn.cursor(row_factory=tuple_row)  # whatever row format the connection uses
    row = cur.execute(
        "insert into invoices (file_path) values (%s) returning id", (file_path,)
    ).fetchone()
    assert row is not None
    invoice_id = row[0]
    job = cur.execute(
        "insert into jobs (invoice_id) values (%s) returning id", (invoice_id,)
    ).fetchone()
    assert job is not None
    conn.commit()
    return invoice_id, job[0]


def _duplicate_reason(
    conn: psycopg.Connection, invoice_id: UUID, supplier_id: int | None, number: str | None
) -> str | None:
    if supplier_id is None or not number:
        return None
    cur = conn.cursor(row_factory=tuple_row)  # row[0] works whatever the connection's format
    row = cur.execute(
        "select id from invoices where supplier_id = %s and upper(invoice_number) = upper(%s)"
        " and id <> %s limit 1",
        (supplier_id, number, invoice_id),
    ).fetchone()
    return f"duplicate: same supplier and invoice number as invoice {row[0]}" if row else None


def _save_fields(
    conn: psycopg.Connection,
    invoice_id: UUID,
    e: InvoiceExtraction,
    *,
    supplier_id: int | None,
    supplier_match: str,
    status: str,
    reasons: list[str],
    categories: list[tuple[str | None, float | None]],
) -> None:
    conn.execute(
        "update invoices set status = %s, review_reasons = %s, supplier_id = %s,"
        " supplier_match = %s, supplier_name = %s, supplier_vat_number = %s,"
        " supplier_siret = %s, invoice_number = %s, issue_date = %s, due_date = %s,"
        " currency = %s, total_excl_vat = %s, total_vat = %s, total_incl_vat = %s,"
        " language = %s, updated_at = now() where id = %s",
        (
            status, reasons, supplier_id, supplier_match, e.supplier_name,
            e.supplier_vat_number, e.supplier_siret, e.invoice_number, e.issue_date,
            e.due_date, e.currency, e.total_excl_vat, e.total_vat, e.total_incl_vat,
            e.language, invoice_id,
        ),
    )  # fmt: skip
    conn.execute("delete from invoice_lines where invoice_id = %s", (invoice_id,))
    for position, (line, (code, score)) in enumerate(zip(e.lines, categories, strict=True), 1):
        conn.execute(
            "insert into invoice_lines (invoice_id, position, description, quantity,"
            " unit_price, vat_rate, amount, category_code, category_score)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                invoice_id, position, line.description, line.quantity, line.unit_price,
                line.vat_rate, line.amount, code, score,
            ),
        )  # fmt: skip


def process_invoice(
    conn: psycopg.Connection,
    invoice_id: UUID,
    document: bytes,
    mime_type: str,
    *,
    client: Any,
    embedder: Embedder,
    model: str,
) -> str:
    """Run the pipeline on one stored invoice. Returns the final status."""
    result = extract(document, mime_type, client=client, model=model)
    e = result.extraction
    checks = run_checks(e) if e else []
    conn.execute(
        "insert into extractions (invoice_id, model, prompt_version, raw, checks, error,"
        " input_tokens, output_tokens, latency_s) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            invoice_id, result.model, result.prompt_version,
            json.dumps(e.model_dump(mode="json")) if e else None,
            json.dumps([asdict(c) for c in checks]), result.error,
            result.input_tokens, result.output_tokens, result.latency_s,
        ),
    )  # fmt: skip

    if e is None:
        conn.execute(
            "update invoices set status = 'to_review', review_reasons = %s, updated_at = now()"
            " where id = %s",
            ([f"extraction_failed: {result.error}"], invoice_id),
        )
        conn.commit()
        return "to_review"

    reasons = [f"{c.name}: {c.message}" for c in checks if c.outcome == "fail"]
    match = match_supplier(conn, e, embedder=embedder)
    duplicate = _duplicate_reason(conn, invoice_id, match.supplier_id, e.invoice_number)
    if duplicate:
        reasons.append(duplicate)

    descriptions = [line.description for line in e.lines]
    found = search_categories(conn, descriptions, embedder=embedder, k=1) if descriptions else []
    categories = [(c[0].key, c[0].score) if c else (None, None) for c in found]

    status = "to_review" if reasons else "pending"
    _save_fields(
        conn, invoice_id, e, supplier_id=match.supplier_id, supplier_match=match.method,
        status=status, reasons=reasons, categories=categories,
    )  # fmt: skip
    conn.commit()
    return status


def run_job(
    conn: psycopg.Connection,
    job_id: UUID,
    document: bytes,
    mime_type: str,
    *,
    client: Any,
    embedder: Embedder,
    model: str,
) -> None:
    """Background task: run the pipeline and record the job's outcome."""
    row = conn.execute(
        "update jobs set status = 'running', updated_at = now() where id = %s returning invoice_id",
        (job_id,),
    ).fetchone()
    conn.commit()
    assert row is not None
    try:
        process_invoice(
            conn, row[0], document, mime_type, client=client, embedder=embedder, model=model
        )
    except Exception as exc:  # the job must record any crash, then the error propagates
        conn.rollback()
        conn.execute(
            "update jobs set status = 'failed', error = %s, updated_at = now() where id = %s",
            (f"{type(exc).__name__}: {exc}", job_id),
        )
        conn.commit()
        raise
    conn.execute("update jobs set status = 'done', updated_at = now() where id = %s", (job_id,))
    conn.commit()
