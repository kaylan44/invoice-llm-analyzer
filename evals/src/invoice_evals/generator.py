"""Synthetic invoice generator.

Ground truth comes first: every value is chosen here, and the PDF is rendered from it later
(step 4), never the other way round. Totals and identifiers go through invoice_api.rules,
so the generated invoices satisfy the same rules the consistency checks will enforce.

Determinism: one ``random.Random(seed)`` drives every choice, and Faker is re-seeded from it
for each invoice. Same seed + same locked dependencies = byte-identical output.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from faker import Faker
from pydantic import BaseModel, ConfigDict

from invoice_api.rules import (
    compute_totals,
    fr_vat_number,
    is_valid_siren,
    is_valid_siret,
    line_amount,
)
from invoice_api.schema import Currency, InvoiceLine, InvoiceTruth, Language


@dataclass(frozen=True)
class CatalogItem:
    description: str
    unit_price: Decimal
    vat_rate: Decimal
    hourly: bool = False  # hourly items get fractional quantities (1.5 h)


def _item(description: str, price: str, rate: str, hourly: bool = False) -> CatalogItem:
    return CatalogItem(description, Decimal(price), Decimal(rate), hourly)


# French VAT: 20 % standard, 10 % catering, 5.5 % books. UK VAT: 20 %, 5 % (child car seats),
# 0 % (books).
CATALOG: dict[Language, list[CatalogItem]] = {
    "fr": [
        _item("Ramettes papier A4 80 g", "4.90", "20"),
        _item("Cartouches toner noir", "62.50", "20"),
        _item("Classeurs à levier", "3.20", "20"),
        _item("Maintenance informatique", "75.00", "20", hourly=True),
        _item("Ouvrages techniques", "34.00", "5.5"),
        _item("Repas d'affaires", "18.50", "10"),
        _item("Transport de marchandises", "120.00", "20"),
        _item("Abonnement logiciel mensuel", "49.00", "20"),
    ],
    "en": [
        _item("A4 copier paper, box of 5 reams", "24.99", "20"),
        _item("Black toner cartridge", "58.00", "20"),
        _item("Lever arch files", "2.75", "20"),
        _item("IT support", "65.00", "20", hourly=True),
        _item("Technical books", "29.00", "0"),
        _item("Child car seat", "89.00", "5"),
        _item("Courier delivery", "15.00", "20"),
        _item("Monthly software subscription", "39.00", "20"),
    ],
}

CURRENCY: dict[Language, Currency] = {"fr": "EUR", "en": "GBP"}
FAKER_LOCALE: dict[Language, str] = {"fr": "fr_FR", "en": "en_GB"}

UNIT_QUANTITIES = [Decimal(q) for q in ("1", "2", "3", "5", "10", "15", "20")]
HOURLY_QUANTITIES = [Decimal(q) for q in ("0.5", "1", "1.5", "2", "3.5", "8")]
DUE_DAYS = [30, 45, 60, None]  # None: no due date printed


class RenderInfo(BaseModel):
    """Printed on the PDF but not scored: only the renderer (step 4) reads it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    supplier_address: str
    client_name: str
    client_address: str


class GeneratedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    truth: InvoiceTruth
    render: RenderInfo


def _with_check_digit(prefix: str, is_valid: Callable[[str], bool]) -> str:
    """Append the single digit that makes ``prefix + digit`` valid (Luhn has exactly one)."""
    for digit in "0123456789":
        if is_valid(prefix + digit):
            return prefix + digit
    raise AssertionError(f"no check digit found for {prefix}")


def _random_digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice("0123456789") for _ in range(n))


def random_siret(rng: random.Random) -> str:
    siren_prefix = rng.choice("123456789") + _random_digits(rng, 7)
    siren = _with_check_digit(siren_prefix, is_valid_siren)
    return _with_check_digit(siren + _random_digits(rng, 4), is_valid_siret)


def _invoice_number(rng: random.Random, language: Language, issue: date) -> str:
    n = rng.randrange(1, 10_000)
    if language == "fr":
        formats = [
            f"FAC-{issue.year}-{n:04d}",
            f"F{issue.year % 100}-{n:04d}",
            f"{issue.year}-{n:03d}",
        ]
    else:
        formats = [f"INV-{n:05d}", f"{rng.choice('ABCDEFGHJK')}{n:05d}", f"SI-{issue.year}-{n:04d}"]
    return rng.choice(formats)


def _lines(rng: random.Random, language: Language) -> list[InvoiceLine]:
    items = rng.sample(CATALOG[language], k=rng.randint(1, 6))
    lines = []
    for item in items:
        quantity = rng.choice(HOURLY_QUANTITIES if item.hourly else UNIT_QUANTITIES)
        lines.append(
            InvoiceLine(
                description=item.description,
                quantity=quantity,
                unit_price=item.unit_price,
                vat_rate=item.vat_rate,
                amount=line_amount(quantity, item.unit_price),
            )
        )
    return lines


def generate_invoice(rng: random.Random, language: Language, invoice_id: str) -> GeneratedInvoice:
    fake = Faker(FAKER_LOCALE[language])
    fake.seed_instance(rng.randrange(2**32))

    issue = date(2026, 1, 1) + timedelta(days=rng.randrange(330))
    due_days = rng.choice(DUE_DAYS)
    lines = _lines(rng, language)
    totals = compute_totals(lines)

    if language == "fr":
        siret: str | None = random_siret(rng)
        vat_number: str | None = fr_vat_number(siret[:9])
    else:
        # UK VAT numbers have their own mod-97 check; not modelled here (week 2 if needed).
        siret = None
        vat_number = "GB" + _random_digits(rng, 9)

    truth = InvoiceTruth(
        supplier_name=fake.company(),
        supplier_vat_number=vat_number,
        supplier_siret=siret,
        invoice_number=_invoice_number(rng, language, issue),
        issue_date=issue,
        due_date=issue + timedelta(days=due_days) if due_days else None,
        currency=CURRENCY[language],
        total_excl_vat=totals.total_excl_vat,
        total_vat=totals.total_vat,
        total_incl_vat=totals.total_incl_vat,
        language=language,
        lines=lines,
    )
    render = RenderInfo(
        supplier_address=f"{fake.street_address()}, {fake.postcode()} {fake.city()}",
        client_name=fake.company(),
        client_address=f"{fake.street_address()}, {fake.postcode()} {fake.city()}",
    )
    return GeneratedInvoice(id=invoice_id, truth=truth, render=render)


def generate_dataset(n: int, seed: int) -> list[GeneratedInvoice]:
    """``n`` invoices alternating French and English, fully determined by ``seed``."""
    rng = random.Random(seed)
    languages: list[Language] = ["fr", "en"]
    return [generate_invoice(rng, languages[i % 2], f"inv-{i + 1:03d}") for i in range(n)]
