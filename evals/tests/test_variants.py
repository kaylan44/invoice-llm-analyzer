"""Hard variants (week 3): invoices built to break the ceiling of the week 2 baseline.

A variant changes how an invoice looks, never what the right answer is: the ground truth
stays consistent (totals follow the rules), so every error the model makes on a variant is
a reading error, not a debatable label.
"""

import json
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from invoice_api.rules import compute_totals, line_amount
from invoice_evals.generate import main as generate_main
from invoice_evals.generator import (
    VARIANTS,
    GeneratedInvoice,
    apply_trap,
    apply_variant,
    generate_dataset,
)
from invoice_evals.render import (
    format_money,
    pick_degradation,
    pick_style,
    render_document,
    render_html,
)
from invoice_evals.render_cli import main as render_main


@pytest.fixture(scope="module")
def base() -> list[GeneratedInvoice]:
    return generate_dataset(n=2, seed=5)  # inv-001 fr, inv-002 en


def page_count(pdf_bytes: bytes) -> int:
    with pdfium.PdfDocument(pdf_bytes) as pdf:
        return len(pdf)


# --- Generator -------------------------------------------------------------------------


def test_variants_are_known() -> None:
    assert set(VARIANTS) == {"long", "client_vat", "deposit"}


def test_variant_is_reproducible(base: list[GeneratedInvoice]) -> None:
    for name in VARIANTS:
        assert apply_variant(base[0], name, seed=5) == apply_variant(base[0], name, seed=5)


def test_long_invoice_has_many_lines_and_consistent_totals(base: list[GeneratedInvoice]) -> None:
    for inv in base:
        t = apply_variant(inv, "long", seed=5).truth
        assert len(t.lines) >= 34
        for line in t.lines:
            assert line.amount == line_amount(line.quantity, line.unit_price)
        assert (t.total_excl_vat, t.total_vat, t.total_incl_vat) == tuple(compute_totals(t.lines))


def test_client_vat_number_differs_from_the_supplier_one(base: list[GeneratedInvoice]) -> None:
    for inv in base:
        varied = apply_variant(inv, "client_vat", seed=5)
        client_vat = varied.render.client_vat_number
        assert client_vat is not None
        assert client_vat[:2] == inv.truth.supplier_vat_number[:2]  # same country prefix
        assert client_vat != inv.truth.supplier_vat_number
        assert varied.truth == inv.truth  # the answer does not change


def test_deposit_is_a_part_of_the_total(base: list[GeneratedInvoice]) -> None:
    for inv in base:
        varied = apply_variant(inv, "deposit", seed=5)
        deposit = varied.render.deposit
        assert deposit is not None and Decimal("0") < deposit < inv.truth.total_incl_vat
        assert deposit == deposit.quantize(Decimal("0.01"))
        assert varied.truth == inv.truth  # total_incl_vat stays the invoice total


def test_variants_combine_and_a_trap_still_applies_after(base: list[GeneratedInvoice]) -> None:
    inv = apply_variant(apply_variant(base[0], "long", seed=5), "client_vat", seed=5)
    assert len(inv.truth.lines) >= 34 and inv.render.client_vat_number is not None
    trapped = apply_trap(inv, "total_mismatch")
    assert trapped.truth.total_incl_vat == inv.truth.total_incl_vat + Decimal("10.00")


def test_cli_records_variants_in_the_manifest(tmp_path: Path) -> None:
    generate_main(
        ["--n", "2", "--seed", "5", "--out", str(tmp_path), "--variant", "inv-002=long,deposit"]
    )
    entries = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert "variants" not in entries[0]
    assert entries[1]["variants"] == ["long", "deposit"]
    saved = GeneratedInvoice.model_validate_json((tmp_path / "inv-002.json").read_text())
    assert len(saved.truth.lines) >= 34 and saved.render.deposit is not None


def test_cli_rejects_an_unknown_variant(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        generate_main(["--n", "1", "--out", str(tmp_path), "--variant", "inv-001=coffee"])


# --- Rendering -------------------------------------------------------------------------


def test_long_invoice_spans_two_pages(base: list[GeneratedInvoice]) -> None:
    inv = apply_variant(base[0], "long", seed=5)
    pdf, _, _ = render_document(inv, seed=5, degradation_level=None)
    assert page_count(pdf) >= 2


def test_long_scan_keeps_every_page(base: list[GeneratedInvoice]) -> None:
    inv = apply_variant(base[1], "long", seed=5)
    clean, _, _ = render_document(inv, seed=5, degradation_level=None)
    scan, _, d = render_document(inv, seed=5, degradation_level="medium")
    assert d is not None
    assert page_count(scan) == page_count(clean) >= 2


def test_client_vat_is_printed_with_the_same_label(base: list[GeneratedInvoice]) -> None:
    inv = apply_variant(base[0], "client_vat", seed=5)
    html = render_html(inv, pick_style(inv.id, seed=5))
    assert inv.render.client_vat_number in html
    assert html.count("TVA intracom.") == 2  # supplier and client: the confusion is the point


def test_deposit_prints_the_total_and_a_smaller_balance(base: list[GeneratedInvoice]) -> None:
    for inv in base:
        varied = apply_variant(inv, "deposit", seed=5)
        t, deposit = varied.truth, varied.render.deposit
        assert deposit is not None
        html = render_html(varied, pick_style(varied.id, seed=5))
        assert format_money(t.total_incl_vat, t.currency, t.language) in html
        assert format_money(t.total_incl_vat - deposit, t.currency, t.language) in html
        assert ("Net à payer" if t.language == "fr" else "Balance due") in html


def test_medium_sits_between_heavy_and_illegible() -> None:
    heavy = pick_degradation("heavy", "inv-001", seed=5)
    medium = pick_degradation("medium", "inv-001", seed=5)
    illegible = pick_degradation("illegible", "inv-001", seed=5)
    assert heavy.blur < medium.blur < illegible.blur
    assert heavy.noise < medium.noise < illegible.noise
    assert illegible.dpi < medium.dpi < heavy.dpi


def test_render_cli_accepts_medium(tmp_path: Path) -> None:
    generate_main(["--n", "1", "--seed", "5", "--out", str(tmp_path)])
    render_main(["--data", str(tmp_path), "--seed", "5", "--degrade", "inv-001=medium"])
    entry = json.loads((tmp_path / "manifest.jsonl").read_text())
    assert entry["degradation"]["level"] == "medium"
