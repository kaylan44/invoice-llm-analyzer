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
    category: str  # accounting category code, see invoice_api/reference/categories.json
    hourly: bool = False  # hourly items get fractional quantities (1.5 h)


def _item(
    description: str, price: str, rate: str, category: str, hourly: bool = False
) -> CatalogItem:
    return CatalogItem(description, Decimal(price), Decimal(rate), category, hourly)


# French VAT: 20 % standard, 10 % catering, 5.5 % books. UK VAT: 20 %, 5 % (child car seats),
# 0 % (books). Categories are the expected answer of the line classification (week 2).
CATALOG: dict[Language, list[CatalogItem]] = {
    "fr": [
        _item("Ramettes papier A4 80 g", "4.90", "20", "6064"),
        _item("Cartouches toner noir", "62.50", "20", "6064"),
        _item("Classeurs à levier", "3.20", "20", "6064"),
        _item("Maintenance informatique", "75.00", "20", "6156", hourly=True),
        _item("Ouvrages techniques", "34.00", "5.5", "6181"),
        _item("Repas d'affaires", "18.50", "10", "6257"),
        _item("Transport de marchandises", "120.00", "20", "6241"),
        _item("Abonnement logiciel mensuel", "49.00", "20", "6135"),
    ],
    "en": [
        _item("A4 copier paper, box of 5 reams", "24.99", "20", "6064"),
        _item("Black toner cartridge", "58.00", "20", "6064"),
        _item("Lever arch files", "2.75", "20", "6064"),
        _item("IT support", "65.00", "20", "6156", hourly=True),
        _item("Technical books", "29.00", "0", "6181"),
        _item("Child car seat", "89.00", "5", "6063"),
        _item("Courier delivery", "15.00", "20", "6241"),
        _item("Monthly software subscription", "39.00", "20", "6135"),
    ],
}

# Ground truth of the line classification: catalog description -> category code.
CATEGORY_OF: dict[str, str] = {
    item.description: item.category for items in CATALOG.values() for item in items
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
    # Week 3 variants. Defaults keep the week 1 and week 2 JSON files valid as they are.
    client_vat_number: str | None = None  # printed in the client box, same label
    deposit: Decimal | None = None  # deposit already paid: prints a balance below the total


class GeneratedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    truth: InvoiceTruth
    render: RenderInfo | None = None  # None for a real invoice: nothing to render


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


# --- Trap invoices (week 2) ------------------------------------------------------------
# A trap prints an inconsistent invoice on purpose. The ground truth stays what is printed
# (the model must read the wrong value as it is); the consistency checks must then flag it.
# Each trap breaks exactly one check, named in TRAP_CHECK.


def _trap_total_mismatch(t: InvoiceTruth) -> dict[str, object]:
    return {"total_incl_vat": t.total_incl_vat + Decimal("10.00")}


def _trap_lines_sum_mismatch(t: InvoiceTruth) -> dict[str, object]:
    # Excl. VAT and incl. VAT both shifted: HT + TVA = TTC still holds, the line sum does not.
    return {
        "total_excl_vat": t.total_excl_vat + Decimal("5.00"),
        "total_incl_vat": t.total_incl_vat + Decimal("5.00"),
    }


def _trap_vat_mismatch(t: InvoiceTruth) -> dict[str, object]:
    return {
        "total_vat": t.total_vat + Decimal("1.00"),
        "total_incl_vat": t.total_incl_vat + Decimal("1.00"),
    }


def _trap_due_before_issue(t: InvoiceTruth) -> dict[str, object]:
    return {"due_date": t.issue_date - timedelta(days=10)}


def _trap_bad_siret(t: InvoiceTruth) -> dict[str, object]:
    if t.supplier_siret is None:
        raise ValueError("bad_siret needs a French invoice")
    last = (int(t.supplier_siret[-1]) + 1) % 10  # one changed digit breaks the Luhn checksum
    return {"supplier_siret": t.supplier_siret[:-1] + str(last)}


TRAPS: dict[str, Callable[[InvoiceTruth], dict[str, object]]] = {
    "total_mismatch": _trap_total_mismatch,
    "lines_sum_mismatch": _trap_lines_sum_mismatch,
    "vat_mismatch": _trap_vat_mismatch,
    "due_before_issue": _trap_due_before_issue,
    "bad_siret": _trap_bad_siret,
}
TRAP_CHECK = {
    "total_mismatch": "totals",
    "lines_sum_mismatch": "lines_sum",
    "vat_mismatch": "vat_amount",
    "due_before_issue": "dates",
    "bad_siret": "identifiers",
}


# --- Hard variants (week 3) ------------------------------------------------------------
# A variant makes an invoice harder to read without changing what the right answer is:
# the ground truth stays consistent. Week 2 scored 100 % almost everywhere (ceiling
# effect), so it could not tell two versions of the pipeline apart. Each variant targets
# a known way of misreading a real invoice:
#   long:       35-45 lines over two pages, totals on the last page only.
#   client_vat: the client's VAT number printed with the same label as the supplier's.
#   deposit:    a deposit already paid, so the amount to pay is smaller than the total.
# Variants are applied before traps: "long" recomputes the totals, a trap then shifts them.

LONG_LINES = (35, 45)
DEPOSIT_SHARE = Decimal("0.3")
Changes = dict[str, dict[str, object]]  # {"truth" or "render": {field: new value}}


def _variant_long(rng: random.Random, inv: GeneratedInvoice) -> Changes:
    language = inv.truth.language
    ref = "réf." if language == "fr" else "ref."
    lines = []
    for _ in range(rng.randint(*LONG_LINES)):
        item = rng.choice(CATALOG[language])  # with replacement: items repeat, as in real life
        quantity = rng.choice(HOURLY_QUANTITIES if item.hourly else UNIT_QUANTITIES)
        code = rng.choice("ABCDEFGHJK") + _random_digits(rng, 4)
        lines.append(
            InvoiceLine(
                description=f"{item.description}, {ref} {code}",
                quantity=quantity,
                unit_price=item.unit_price,
                vat_rate=item.vat_rate,
                amount=line_amount(quantity, item.unit_price),
            )
        )
    totals = compute_totals(lines)
    return {
        "truth": {
            "lines": lines,
            "total_excl_vat": totals.total_excl_vat,
            "total_vat": totals.total_vat,
            "total_incl_vat": totals.total_incl_vat,
        }
    }


def _variant_client_vat(rng: random.Random, inv: GeneratedInvoice) -> Changes:
    if inv.truth.language == "fr":
        number = fr_vat_number(random_siret(rng)[:9])
    else:
        number = "GB" + _random_digits(rng, 9)
    return {"render": {"client_vat_number": number}}


def _variant_deposit(rng: random.Random, inv: GeneratedInvoice) -> Changes:
    deposit = (inv.truth.total_incl_vat * DEPOSIT_SHARE).quantize(Decimal("0.01"))
    return {"render": {"deposit": deposit}}


VARIANTS: dict[str, Callable[[random.Random, GeneratedInvoice], Changes]] = {
    "long": _variant_long,
    "client_vat": _variant_client_vat,
    "deposit": _variant_deposit,
}


def apply_variant(invoice: GeneratedInvoice, variant: str, seed: int) -> GeneratedInvoice:
    # One RNG per (seed, invoice, variant): adding a variant to an invoice never changes
    # what another variant or another invoice draws.
    rng = random.Random(f"{seed}:{invoice.id}:{variant}")
    changes = VARIANTS[variant](rng, invoice)
    data = invoice.model_dump()
    for part, fields in changes.items():
        data[part] = {**(data[part] or {}), **fields}
    return GeneratedInvoice.model_validate(data)  # re-validated: a broken variant fails here


def apply_trap(invoice: GeneratedInvoice, trap: str) -> GeneratedInvoice:
    changes = TRAPS[trap](invoice.truth)
    truth = InvoiceTruth.model_validate({**invoice.truth.model_dump(), **changes})
    return invoice.model_copy(update={"truth": truth})


def generate_dataset(n: int, seed: int) -> list[GeneratedInvoice]:
    """``n`` invoices alternating French and English, fully determined by ``seed``."""
    rng = random.Random(seed)
    languages: list[Language] = ["fr", "en"]
    return [generate_invoice(rng, languages[i % 2], f"inv-{i + 1:03d}") for i in range(n)]
