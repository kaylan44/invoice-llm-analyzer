"""Invoice business rules: rounding, totals, French company identifiers.

Used by the synthetic generator (to build correct invoices) and, from week 2, by the
consistency checks (to flag extracted invoices that break them). One implementation, two
uses: the generator and the checks can never disagree.
"""

from collections import defaultdict
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal
from typing import NamedTuple

from invoice_api.schema import InvoiceLine

CENT = Decimal("0.01")


def round_money(value: Decimal) -> Decimal:
    """Round to cents, half up (2.125 -> 2.13), as invoices do.

    Python's round() uses banker's rounding (2.125 -> 2.12), hence quantize().
    """
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def line_amount(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """Line total excluding VAT."""
    return round_money(quantity * unit_price)


class Totals(NamedTuple):
    total_excl_vat: Decimal
    total_vat: Decimal
    total_incl_vat: Decimal


class VatLine(NamedTuple):
    rate: Decimal
    base: Decimal  # total excluding VAT of the lines at this rate
    vat: Decimal


def vat_breakdown(lines: Iterable[InvoiceLine]) -> list[VatLine]:
    """VAT per rate, rounded once per rate (not once per line), sorted by rate descending.

    Rounding per line would add up small errors: two lines of 0.30 at 5.5 % give 0.04 of
    VAT per line but 0.03 on the 0.60 base. Printed invoices show this table.
    """
    base_by_rate: defaultdict[Decimal, Decimal] = defaultdict(Decimal)  # missing key -> 0
    for line in lines:
        base_by_rate[line.vat_rate] += line.amount
    return [
        VatLine(rate, round_money(base), round_money(base * rate / 100))
        for rate, base in sorted(base_by_rate.items(), reverse=True)
    ]


def compute_totals(lines: Iterable[InvoiceLine]) -> Totals:
    """Invoice totals: sum of the VAT breakdown."""
    breakdown = vat_breakdown(lines)
    total_excl_vat = sum((v.base for v in breakdown), Decimal("0.00"))
    total_vat = sum((v.vat for v in breakdown), Decimal("0.00"))
    return Totals(total_excl_vat, total_vat, round_money(total_excl_vat + total_vat))


def luhn_is_valid(digits: str) -> bool:
    """Luhn checksum: from the right, double every second digit (minus 9 if above 9)."""
    if not digits or not digits.isdigit():
        return False
    total = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)
        if position % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def is_valid_siren(siren: str) -> bool:
    """French company number: 9 digits, Luhn-valid. Input must be digits only."""
    return len(siren) == 9 and luhn_is_valid(siren)


def is_valid_siret(siret: str) -> bool:
    """French establishment number: 14 digits (SIREN + 5), Luhn-valid.

    Known exception not handled: La Poste establishments use a different checksum.
    """
    return len(siret) == 14 and luhn_is_valid(siret)


def fr_vat_number(siren: str) -> str:
    """French intra-EU VAT number derived from the SIREN: FR + 2-digit key + SIREN."""
    if not is_valid_siren(siren):
        raise ValueError(f"invalid SIREN: {siren!r}")
    key = (12 + 3 * (int(siren) % 97)) % 97
    return f"FR{key:02d}{siren}"
