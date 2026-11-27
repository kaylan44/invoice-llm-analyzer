"""Rendering tests (step 4). They need WeasyPrint's system libraries (Pango)."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from invoice_evals.generate import main as generate_main
from invoice_evals.generator import GeneratedInvoice, generate_dataset
from invoice_evals.render import (
    NBSP,
    format_date,
    format_money,
    pick_degradation,
    pick_style,
    render_document,
    render_html,
)
from invoice_evals.render_cli import main as render_main


@pytest.fixture(scope="module")
def invoices() -> list[GeneratedInvoice]:
    return generate_dataset(n=4, seed=42)


def pdf_text(pdf_bytes: bytes) -> str:
    with pdfium.PdfDocument(pdf_bytes) as pdf:
        return "\n".join(page.get_textpage().get_text_range() for page in pdf)


# --- Formatting ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "currency", "language", "expected"),
    [
        ("1234.5", "EUR", "fr", f"1{NBSP}234,50{NBSP}€"),
        ("1234.5", "GBP", "en", "£1,234.50"),
        ("49.5", "GBP", "en", "£49.50"),
    ],
)
def test_format_money(value: str, currency: str, language: str, expected: str) -> None:
    assert format_money(Decimal(value), currency, language) == expected  # type: ignore[arg-type]


def test_format_date() -> None:
    assert format_date(date(2026, 11, 3), "fr") == "03/11/2026"
    assert format_date(date(2026, 11, 3), "en") == "3 November 2026"


# --- HTML ------------------------------------------------------------------------------


def test_html_shows_the_ground_truth(invoices: list[GeneratedInvoice]) -> None:
    for inv in invoices:
        html = render_html(inv, pick_style(inv.id, seed=42))
        t = inv.truth
        assert t.invoice_number in html
        assert format_money(t.total_incl_vat, t.currency, t.language) in html
        assert "None" not in html  # an absent value must not be printed as "None"
        # Every scored value must be printed: here the VAT total, which a trap can change.
        assert format_money(t.total_vat, t.currency, t.language) in html
        if t.due_date is None:
            assert ("Échéance" if t.language == "fr" else "Due date") not in html


# --- PDF -------------------------------------------------------------------------------


def test_clean_pdf_has_a_text_layer_with_the_invoice_number(
    invoices: list[GeneratedInvoice],
) -> None:
    inv = invoices[0]
    pdf, _, degradation = render_document(inv, seed=42, degradation_level=None)
    assert pdf.startswith(b"%PDF")
    assert degradation is None
    assert inv.truth.invoice_number in pdf_text(pdf)


def test_scan_is_an_image_only_pdf(invoices: list[GeneratedInvoice]) -> None:
    pdf, _, degradation = render_document(invoices[1], seed=42, degradation_level="heavy")
    assert pdf.startswith(b"%PDF")
    assert degradation is not None and degradation.dpi == 150
    assert pdf_text(pdf).strip() == ""  # like a real scan: no text to copy


def test_scan_is_reproducible(invoices: list[GeneratedInvoice]) -> None:
    first, _, _ = render_document(invoices[1], seed=42, degradation_level="light")
    second, _, _ = render_document(invoices[1], seed=42, degradation_level="light")
    with pdfium.PdfDocument(first) as a, pdfium.PdfDocument(second) as b:
        image_a = a[0].render(scale=1).to_pil()
        image_b = b[0].render(scale=1).to_pil()
        assert image_a.tobytes() == image_b.tobytes()


def test_degradation_levels_differ() -> None:
    light = pick_degradation("light", "inv-001", seed=42)
    heavy = pick_degradation("heavy", "inv-001", seed=42)
    assert abs(light.rotation) < abs(heavy.rotation)
    assert light.jpeg_quality > heavy.jpeg_quality


def test_illegible_is_harsher_than_heavy() -> None:
    heavy = pick_degradation("heavy", "inv-011", seed=42)
    illegible = pick_degradation("illegible", "inv-011", seed=42)
    assert abs(illegible.rotation) > abs(heavy.rotation)
    assert illegible.blur > heavy.blur
    assert illegible.noise > heavy.noise
    assert illegible.jpeg_quality < heavy.jpeg_quality
    assert illegible.dpi < heavy.dpi


# --- CLI -------------------------------------------------------------------------------


def test_cli_renders_every_invoice_and_updates_manifest(tmp_path: Path) -> None:
    generate_main(["--n", "2", "--seed", "1", "--out", str(tmp_path)])
    render_main(["--data", str(tmp_path), "--seed", "1", "--degrade", "inv-002=light"])

    entries = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert [e["document"] for e in entries] == ["inv-001.pdf", "inv-002.pdf"]
    assert entries[0]["degradation"] is None
    assert entries[1]["degradation"]["level"] == "light"
    assert all((tmp_path / e["document"]).read_bytes().startswith(b"%PDF") for e in entries)


def test_cli_only_extends_a_dataset_without_touching_it(tmp_path: Path) -> None:
    generate_main(["--n", "2", "--seed", "1", "--out", str(tmp_path)])
    render_main(["--data", str(tmp_path), "--seed", "1"])
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    generate_main(["--n", "3", "--seed", "1", "--out", str(tmp_path), "--only", "inv-003"])
    render_main(
        ["--data", str(tmp_path), "--seed", "1", "--only", "inv-003", "--degrade", "inv-003=heavy"]
    )

    for name in ("inv-001.json", "inv-001.pdf", "inv-002.json", "inv-002.pdf"):
        assert (tmp_path / name).read_bytes() == before[name], name
    entries = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert [e["id"] for e in entries] == ["inv-001", "inv-002", "inv-003"]
    assert entries[0]["layout"]  # rendering info of existing entries is kept
    assert entries[2]["degradation"]["level"] == "heavy"
    # Invoice 3 is the same whether the dataset is generated with n=3 or extended with --only.
    assert (tmp_path / "inv-003.json").read_text() == generate_dataset(3, 1)[2].model_dump_json(
        indent=2
    ) + "\n"
