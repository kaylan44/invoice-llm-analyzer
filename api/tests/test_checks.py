"""Consistency checks tests (week 2, step 8)."""

from decimal import Decimal
from typing import Any

import pytest

from invoice_api.checks import review_status, run_checks
from invoice_api.schema import InvoiceExtraction

LINE_KEYS = ("description", "quantity", "unit_price", "vat_rate", "amount")

VALID: dict[str, Any] = {
    "supplier_name": "Papeterie du Rhône SAS",
    "supplier_vat_number": "FR21842157398",
    "supplier_siret": "84215739800012",
    "invoice_number": "FAC-2026-0412",
    "issue_date": "2026-11-03",
    "due_date": "2026-12-03",
    "currency": "EUR",
    "total_excl_vat": "333.50",
    "total_vat": "66.70",
    "total_incl_vat": "400.20",
    "language": "fr",
    "lines": [
        dict(zip(LINE_KEYS, ("Ramettes", "20", "4.90", "20", "98.00"), strict=True)),
        dict(zip(LINE_KEYS, ("Toner", "3", "62.50", "20", "187.50"), strict=True)),
        dict(zip(LINE_KEYS, ("Classeurs", "15", "3.20", "20", "48.00"), strict=True)),
    ],
}


def outcomes(**changes: Any) -> dict[str, str]:
    extraction = InvoiceExtraction.model_validate({**VALID, **changes})
    return {c.name: c.outcome for c in run_checks(extraction)}


def test_valid_invoice_passes_every_check() -> None:
    checks = run_checks(InvoiceExtraction.model_validate(VALID))
    assert all(c.outcome == "pass" for c in checks), checks
    assert review_status(checks) == "pending"


@pytest.mark.parametrize(
    ("changes", "failing"),
    [
        ({"total_incl_vat": "410.20"}, "totals"),
        ({"total_excl_vat": "338.50", "total_incl_vat": "405.20"}, "lines_sum"),
        ({"total_vat": "67.70", "total_incl_vat": "401.20"}, "vat_amount"),
        ({"due_date": "2026-10-01"}, "dates"),
        ({"currency": "XYZ"}, "currency"),
        ({"supplier_siret": "84215739800013"}, "identifiers"),
        ({"supplier_vat_number": "FR22842157398"}, "identifiers"),
        ({"invoice_number": None}, "required_fields"),
    ],
)
def test_each_trap_fails_its_own_check(changes: dict[str, Any], failing: str) -> None:
    result = outcomes(**changes)
    assert result[failing] == "fail"
    # The trap is caught by its check and not blamed on unrelated ones.
    others = {name: o for name, o in result.items() if name != failing}
    assert "fail" not in others.values(), others


def test_wrong_line_amount_is_reported_with_its_line() -> None:
    lines = [dict(line) for line in VALID["lines"]]
    lines[1]["amount"] = "178.50"
    checks = run_checks(InvoiceExtraction.model_validate({**VALID, "lines": lines}))
    by_name = {c.name: c for c in checks}
    assert by_name["line_amounts"].outcome == "fail"
    assert "line 2" in by_name["line_amounts"].message


def test_rounding_within_two_cents_is_tolerated() -> None:
    assert outcomes(total_incl_vat="400.21")["totals"] == "pass"


def test_empty_extraction_fails_required_fields_and_skips_the_rest() -> None:
    checks = run_checks(InvoiceExtraction())
    by_name = {c.name: c.outcome for c in checks}
    assert by_name["required_fields"] == "fail"
    assert {o for n, o in by_name.items() if n != "required_fields"} == {"skip"}
    assert review_status(checks) == "to_review"


def test_uk_vat_number_format() -> None:
    assert outcomes(supplier_vat_number="GB835030564", supplier_siret=None)["identifiers"] == "pass"
    assert outcomes(supplier_vat_number="GB8350", supplier_siret=None)["identifiers"] == "fail"


def test_amounts_are_decimal() -> None:
    e = InvoiceExtraction.model_validate(VALID)
    assert e.total_excl_vat == Decimal("333.50")
