"""Tests for invoice business rules (step 2).

Written before the code: they fail until api/src/invoice_api/rules.py exists.
The generator uses these functions now; the consistency checks reuse them in week 2.
"""

from decimal import Decimal

import pytest

from invoice_api.rules import (
    Totals,
    compute_totals,
    fr_vat_number,
    is_valid_siren,
    is_valid_siret,
    line_amount,
    luhn_is_valid,
    round_money,
)
from invoice_api.schema import InvoiceLine


def line(amount: str, vat_rate: str) -> InvoiceLine:
    return InvoiceLine(
        description="item",
        quantity=Decimal("1"),
        unit_price=Decimal(amount),
        vat_rate=Decimal(vat_rate),
        amount=Decimal(amount),
    )


# --- Rounding --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2.125", "2.13"),  # half up: banker's rounding (Python's default) would give 2.12
        ("2.124", "2.12"),
        ("98", "98.00"),  # always two decimals
    ],
)
def test_round_money_rounds_half_up_to_cents(value: str, expected: str) -> None:
    # Compare strings: Decimal("98") == Decimal("98.00") is True, but we want the cents.
    assert str(round_money(Decimal(value))) == expected


def test_line_amount_is_quantity_times_price_rounded() -> None:
    assert str(line_amount(Decimal("20"), Decimal("4.90"))) == "98.00"
    assert str(line_amount(Decimal("2.5"), Decimal("0.85"))) == "2.13"


# --- Totals ----------------------------------------------------------------------------


def test_compute_totals_single_rate() -> None:
    lines = [line("98.00", "20"), line("187.50", "20"), line("48.00", "20")]
    assert compute_totals(lines) == Totals(
        total_excl_vat=Decimal("333.50"),
        total_vat=Decimal("66.70"),
        total_incl_vat=Decimal("400.20"),
    )


def test_compute_totals_rounds_vat_per_rate_not_per_line() -> None:
    # Per line: 0.0165 -> 0.02, twice = 0.04. Per rate: 0.60 * 5.5 % = 0.033 -> 0.03.
    totals = compute_totals([line("0.30", "5.5"), line("0.30", "5.5")])
    assert totals.total_vat == Decimal("0.03")


def test_compute_totals_mixed_rates() -> None:
    lines = [line("98.00", "20"), line("187.50", "20"), line("0.30", "5.5"), line("0.30", "5.5")]
    totals = compute_totals(lines)
    assert totals == Totals(Decimal("286.10"), Decimal("57.13"), Decimal("343.23"))
    # A NamedTuple is also a tuple: fields by name or by position.
    assert totals.total_incl_vat == totals[2]


# --- Luhn, SIREN, SIRET ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("digits", "expected"),
    [
        ("842157398", True),
        ("842157399", False),
        ("84215739800012", True),
        ("0", True),
        ("", False),
        ("8421573a8", False),
    ],
)
def test_luhn_is_valid(digits: str, expected: bool) -> None:
    assert luhn_is_valid(digits) is expected


@pytest.mark.parametrize(
    ("siren", "expected"),
    [
        ("842157398", True),
        ("842157399", False),  # wrong check digit
        ("84215739", False),  # 8 digits
        ("842 157 398", False),  # inputs are normalized digits only
    ],
)
def test_is_valid_siren(siren: str, expected: bool) -> None:
    assert is_valid_siren(siren) is expected


@pytest.mark.parametrize(
    ("siret", "expected"),
    [
        ("84215739800012", True),
        ("84215739800013", False),
        ("8421573980001", False),  # 13 digits
    ],
)
def test_is_valid_siret(siret: str, expected: bool) -> None:
    assert is_valid_siret(siret) is expected


# --- French VAT number -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("siren", "expected"),
    [
        ("842157398", "FR21842157398"),
        ("100000207", "FR03100000207"),  # key below 10: always two digits
    ],
)
def test_fr_vat_number(siren: str, expected: str) -> None:
    assert fr_vat_number(siren) == expected


def test_fr_vat_number_rejects_invalid_siren() -> None:
    with pytest.raises(ValueError):
        fr_vat_number("842157399")
