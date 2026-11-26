"""Tests for the invoice schema (step 1).

Written before the code: they fail until api/src/invoice_api/schema.py exists.
"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoice_api.schema import InvoiceExtraction, InvoiceLine, InvoiceTruth, LineExtraction


def make_truth(**overrides: object) -> InvoiceTruth:
    """A valid ground-truth invoice (the one shown in the review mockup)."""
    data: dict[str, object] = {
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
            {
                "description": "Ramettes papier A4 80 g",
                "quantity": "20",
                "unit_price": "4.90",
                "vat_rate": "20",
                "amount": "98.00",
            },
            {
                "description": "Cartouches toner noir",
                "quantity": "3",
                "unit_price": "62.50",
                "vat_rate": "20",
                "amount": "187.50",
            },
            {
                "description": "Classeurs à levier",
                "quantity": "15",
                "unit_price": "3.20",
                "vat_rate": "20",
                "amount": "48.00",
            },
        ],
    }
    data.update(overrides)
    return InvoiceTruth.model_validate(data)


# --- InvoiceTruth: strict ground truth -------------------------------------------------


def test_truth_parses_money_as_exact_decimal() -> None:
    truth = make_truth()
    assert isinstance(truth.total_excl_vat, Decimal)
    assert truth.total_excl_vat == Decimal("333.50")
    # Exact arithmetic: with floats this kind of sum drifts.
    assert sum(line.amount for line in truth.lines) == truth.total_excl_vat


def test_truth_parses_iso_dates() -> None:
    truth = make_truth()
    assert truth.issue_date == date(2026, 11, 3)
    assert truth.due_date == date(2026, 12, 3)


def test_truth_optional_fields_accept_none() -> None:
    # An English invoice has no SIRET; some invoices have no due date.
    truth = make_truth(supplier_siret=None, supplier_vat_number=None, due_date=None)
    assert truth.supplier_siret is None
    assert truth.supplier_vat_number is None
    assert truth.due_date is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("language", "de"),
        ("currency", "XYZ"),
        ("issue_date", "not-a-date"),
        ("total_vat", "abc"),
    ],
)
def test_truth_rejects_invalid_values(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        make_truth(**{field: value})


def test_truth_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        make_truth(notes="free text")


def test_truth_requires_at_least_one_line() -> None:
    with pytest.raises(ValidationError):
        make_truth(lines=[])


def test_line_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        InvoiceLine(
            description="Classeurs",
            quantity=Decimal("0"),
            unit_price=Decimal("3.20"),
            vat_rate=Decimal("20"),
            amount=Decimal("0"),
        )


def test_truth_json_round_trip() -> None:
    # Ground truth is stored as JSON next to each generated PDF: it must reload identically.
    truth = make_truth()
    assert InvoiceTruth.model_validate_json(truth.model_dump_json()) == truth


# --- InvoiceExtraction: what the model returns, every field may be missing -------------


def test_extraction_accepts_all_fields_missing() -> None:
    extraction = InvoiceExtraction()
    assert extraction.invoice_number is None
    assert extraction.total_incl_vat is None
    assert extraction.lines == []


def test_extraction_keeps_unknown_currency() -> None:
    # Rejecting it here would hide the error: the "known currency" check comes later.
    assert InvoiceExtraction(currency="XYZ").currency == "XYZ"


def test_extraction_line_fields_are_optional() -> None:
    line = LineExtraction(description="Toner")
    assert line.quantity is None
    assert line.amount is None


def test_extraction_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        InvoiceExtraction.model_validate({"invoice_number": "A1", "confidence": 0.9})


def test_extraction_json_schema_lists_all_fields() -> None:
    # The JSON schema is what we will send to Gemini as the structured output format.
    properties = InvoiceExtraction.model_json_schema()["properties"]
    expected = {
        "supplier_name",
        "supplier_vat_number",
        "supplier_siret",
        "invoice_number",
        "issue_date",
        "due_date",
        "currency",
        "total_excl_vat",
        "total_vat",
        "total_incl_vat",
        "language",
        "lines",
    }
    assert expected <= set(properties)
