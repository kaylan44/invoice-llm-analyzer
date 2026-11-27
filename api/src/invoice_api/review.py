"""Human review: corrections, validation and export of invoices.

A correction changes stored fields, then runs the same consistency checks as the pipeline
on the corrected invoice: fixing a misread total clears the "totals" reason, writing a due
date before the issue date creates a "dates" reason. The duplicate check is recomputed too,
because a corrected invoice number can create or remove a duplicate.

A validated invoice is locked: no more corrections. Validating an invoice that still has
review reasons needs an explicit acknowledgement: the reviewer decides, but knowingly.
"""

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from invoice_api.checks import run_checks
from invoice_api.pipeline import _duplicate_reason
from invoice_api.schema import Amount, InvoiceExtraction


class InvoiceCorrection(BaseModel):
    """Header fields a reviewer may correct. Fields not sent are left as they are."""

    model_config = ConfigDict(extra="forbid")  # "status": ... is refused (422), not ignored

    supplier_name: str | None = None
    supplier_vat_number: str | None = None
    supplier_siret: str | None = None
    invoice_number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    total_excl_vat: Amount | None = None
    total_vat: Amount | None = None
    total_incl_vat: Amount | None = None


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledge_reasons: bool = False


class ReviewError(Exception):
    """A request that conflicts with the invoice's state (HTTP 409)."""


HEADER_FIELDS = (
    "supplier_name", "supplier_vat_number", "supplier_siret", "invoice_number", "issue_date",
    "due_date", "currency", "total_excl_vat", "total_vat", "total_incl_vat", "language",
)  # fmt: skip
EXPORT_COLUMNS = ("id", *HEADER_FIELDS, "supplier_match", "updated_at")


def _invoice(conn: psycopg.Connection, invoice_id: UUID) -> dict[str, Any] | None:
    cur = conn.cursor(row_factory=dict_row)
    return cur.execute("select * from invoices where id = %s", (invoice_id,)).fetchone()


def stored_extraction(conn: psycopg.Connection, invoice: dict[str, Any]) -> InvoiceExtraction:
    """The invoice as it is stored now (corrections included), in the extraction format."""
    cur = conn.cursor(row_factory=dict_row)
    lines = cur.execute(
        "select description, quantity, unit_price, vat_rate, amount from invoice_lines"
        " where invoice_id = %s order by position",
        (invoice["id"],),
    ).fetchall()
    return InvoiceExtraction.model_validate(
        {**{f: invoice[f] for f in HEADER_FIELDS}, "lines": lines}
    )


def correct_invoice(
    conn: psycopg.Connection, invoice_id: UUID, correction: InvoiceCorrection
) -> bool:
    """Apply a correction and recompute status and reasons. False if the invoice is unknown."""
    invoice = _invoice(conn, invoice_id)
    if invoice is None:
        return False
    if invoice["status"] == "validated":
        raise ReviewError("a validated invoice cannot be corrected")

    # model_fields_set: the fields present in the request body, even when sent as null.
    changes = {name: getattr(correction, name) for name in correction.model_fields_set}
    if changes:
        # Column names come from the pydantic model, never from the client; sql.Identifier
        # quotes them anyway. Values always go through placeholders.
        assignments = sql.SQL(", ").join(
            sql.SQL("{} = %s").format(sql.Identifier(name)) for name in changes
        )
        conn.execute(
            sql.SQL("update invoices set {} where id = %s").format(assignments),
            (*changes.values(), invoice_id),
        )
        invoice = {**invoice, **changes}

    checks = run_checks(stored_extraction(conn, invoice))
    reasons = [f"{c.name}: {c.message}" for c in checks if c.outcome == "fail"]
    duplicate = _duplicate_reason(
        conn, invoice_id, invoice["supplier_id"], invoice["invoice_number"]
    )
    if duplicate:
        reasons.append(duplicate)
    conn.execute(
        "update invoices set status = %s, review_reasons = %s, updated_at = now() where id = %s",
        ("to_review" if reasons else "pending", reasons, invoice_id),
    )
    conn.commit()
    return True


def validate_invoice(
    conn: psycopg.Connection, invoice_id: UUID, request: ValidationRequest
) -> bool:
    invoice = _invoice(conn, invoice_id)
    if invoice is None:
        return False
    if invoice["status"] == "to_review" and not request.acknowledge_reasons:
        raise ReviewError(
            "invoice has review reasons: correct it, or validate with acknowledge_reasons=true"
        )
    conn.execute(
        "update invoices set status = 'validated', updated_at = now() where id = %s",
        (invoice_id,),
    )
    conn.commit()
    return True


def validated_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    cur = conn.cursor(row_factory=dict_row)
    columns = sql.SQL(", ").join(map(sql.Identifier, EXPORT_COLUMNS))
    return cur.execute(
        sql.SQL(
            "select {} from invoices where status = 'validated' order by issue_date, id"
        ).format(columns)
    ).fetchall()


def to_csv(rows: list[dict[str, Any]]) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, Decimal):
            return format(value, "f")  # 400.20, never 4.002E+2
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows({k: cell(v) for k, v in row.items()} for row in rows)
    return buffer.getvalue()
