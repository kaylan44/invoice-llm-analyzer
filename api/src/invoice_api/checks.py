"""Deterministic consistency checks on an extraction.

Each check returns pass, fail or skip (skip: an input it needs is missing; the missing field
is reported by ``required_fields`` instead, so one gap is not counted twice). Any failure sends
the invoice to "to_review" with the reasons; otherwise it waits for a one-click validation
("pending").

The checks reuse invoice_api.rules: the generator built its invoices with the same functions,
so a correctly read invoice can never fail a check because of a rounding disagreement.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from invoice_api.rules import fr_vat_number, is_valid_siren, is_valid_siret, round_money
from invoice_api.schema import InvoiceExtraction

Outcome = Literal["pass", "fail", "skip"]
Status = Literal["pending", "to_review"]  # "en attente" / "à vérifier"

REQUIRED_FIELDS = (
    "supplier_name",
    "invoice_number",
    "issue_date",
    "currency",
    "total_excl_vat",
    "total_vat",
    "total_incl_vat",
)
KNOWN_CURRENCIES = {"EUR", "GBP", "USD"}
CENT = Decimal("0.01")
TOTAL_TOLERANCE = Decimal("0.02")  # two cents: some software rounds differently


@dataclass(frozen=True)
class Check:
    name: str
    outcome: Outcome
    message: str = ""


def check_required_fields(e: InvoiceExtraction) -> Check:
    missing = [f for f in REQUIRED_FIELDS if getattr(e, f) is None]
    if not e.lines:
        missing.append("lines")
    if missing:
        return Check("required_fields", "fail", "missing: " + ", ".join(missing))
    return Check("required_fields", "pass")


def check_line_amounts(e: InvoiceExtraction) -> Check:
    """Each line: quantity x unit price = amount, to the cent."""
    wrong, checked = [], 0
    for i, ln in enumerate(e.lines, start=1):
        if ln.quantity is None or ln.unit_price is None or ln.amount is None:
            continue
        checked += 1
        expected = round_money(ln.quantity * ln.unit_price)
        if abs(expected - ln.amount) > CENT:
            wrong.append(f"line {i}: {ln.quantity} x {ln.unit_price} = {expected}, not {ln.amount}")
    if not checked:
        return Check("line_amounts", "skip", "no line with quantity, unit price and amount")
    return (
        Check("line_amounts", "fail", "; ".join(wrong)) if wrong else Check("line_amounts", "pass")
    )


def check_lines_sum(e: InvoiceExtraction) -> Check:
    """Sum of line amounts = total excluding VAT."""
    amounts = [ln.amount for ln in e.lines]
    if e.total_excl_vat is None or not amounts or None in amounts:
        return Check("lines_sum", "skip", "total or line amounts missing")
    total = sum(amounts, Decimal(0))  # type: ignore[arg-type]
    if abs(total - e.total_excl_vat) > TOTAL_TOLERANCE:
        return Check(
            "lines_sum", "fail", f"lines sum to {total}, total excl. VAT is {e.total_excl_vat}"
        )
    return Check("lines_sum", "pass")


def check_vat_amount(e: InvoiceExtraction) -> Check:
    """Total VAT = VAT recomputed from the lines, rounded once per rate."""
    if e.total_vat is None or not e.lines:
        return Check("vat_amount", "skip", "total VAT or lines missing")
    base_by_rate: defaultdict[Decimal, Decimal] = defaultdict(Decimal)
    for ln in e.lines:
        if ln.amount is None or ln.vat_rate is None:
            return Check("vat_amount", "skip", "a line amount or VAT rate is missing")
        base_by_rate[ln.vat_rate] += ln.amount
    expected = sum(
        (round_money(base * rate / 100) for rate, base in base_by_rate.items()), Decimal(0)
    )
    if abs(expected - e.total_vat) > TOTAL_TOLERANCE:
        return Check(
            "vat_amount", "fail", f"VAT from lines is {expected}, total VAT is {e.total_vat}"
        )
    return Check("vat_amount", "pass")


def check_totals(e: InvoiceExtraction) -> Check:
    """Total excl. VAT + VAT = total incl. VAT."""
    if e.total_excl_vat is None or e.total_vat is None or e.total_incl_vat is None:
        return Check("totals", "skip", "a total is missing")
    computed = e.total_excl_vat + e.total_vat
    if abs(computed - e.total_incl_vat) > TOTAL_TOLERANCE:
        message = f"{e.total_excl_vat} + {e.total_vat} = {computed}, not {e.total_incl_vat}"
        return Check("totals", "fail", message)
    return Check("totals", "pass")


def check_dates(e: InvoiceExtraction) -> Check:
    """Due date, when printed, is not before the issue date."""
    if e.issue_date is None or e.due_date is None:
        return Check("dates", "skip", "issue or due date missing")
    if e.due_date < e.issue_date:
        return Check("dates", "fail", f"due date {e.due_date} is before issue date {e.issue_date}")
    return Check("dates", "pass")


def check_currency(e: InvoiceExtraction) -> Check:
    if e.currency is None:
        return Check("currency", "skip", "currency missing")
    if e.currency.upper() not in KNOWN_CURRENCIES:
        return Check("currency", "fail", f"unknown currency {e.currency!r}")
    return Check("currency", "pass")


def check_identifiers(e: InvoiceExtraction) -> Check:
    """SIRET checksum, VAT number format, and for France a VAT key matching the SIRET."""
    siret = re.sub(r"\s", "", e.supplier_siret) if e.supplier_siret else None
    vat = re.sub(r"[\s.]", "", e.supplier_vat_number).upper() if e.supplier_vat_number else None
    if siret is None and vat is None:
        return Check("identifiers", "skip", "no SIRET or VAT number")

    problems = []
    if siret is not None and not is_valid_siret(siret):
        problems.append(f"invalid SIRET {siret}")
    if vat is not None and vat.startswith("FR"):
        siren = vat[4:]
        if not re.fullmatch(r"FR\d{11}", vat) or not is_valid_siren(siren):
            problems.append(f"invalid French VAT number {vat}")
        elif fr_vat_number(siren) != vat:
            problems.append(f"wrong key in French VAT number {vat}")
        elif siret is not None and siret[:9] != siren:
            problems.append(f"VAT number {vat} does not match SIRET {siret}")
    elif vat is not None and vat.startswith("GB"):
        if not re.fullmatch(r"GB(\d{9}|\d{12})", vat):
            problems.append(f"invalid UK VAT number {vat}")
    elif vat is not None and not re.fullmatch(r"[A-Z]{2}[0-9A-Z]{2,12}", vat):
        problems.append(f"invalid VAT number {vat}")

    if problems:
        return Check("identifiers", "fail", "; ".join(problems))
    return Check("identifiers", "pass")


CHECKS = (
    check_required_fields,
    check_line_amounts,
    check_lines_sum,
    check_vat_amount,
    check_totals,
    check_dates,
    check_currency,
    check_identifiers,
)


def run_checks(extraction: InvoiceExtraction) -> list[Check]:
    return [check(extraction) for check in CHECKS]


def review_status(checks: list[Check]) -> Status:
    return "to_review" if any(c.outcome == "fail" for c in checks) else "pending"
