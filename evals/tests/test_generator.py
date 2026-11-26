"""Generator tests: reproducibility and invariants (they need invoice_api.rules to exist)."""

import json
from pathlib import Path

import pytest

from invoice_api.rules import compute_totals, fr_vat_number, is_valid_siret, line_amount
from invoice_evals.generate import main
from invoice_evals.generator import GeneratedInvoice, generate_dataset


@pytest.fixture(scope="module")
def dataset() -> list[GeneratedInvoice]:
    return generate_dataset(n=40, seed=7)


def test_same_seed_gives_identical_output() -> None:
    first = [inv.model_dump_json() for inv in generate_dataset(n=10, seed=42)]
    second = [inv.model_dump_json() for inv in generate_dataset(n=10, seed=42)]
    assert first == second


def test_different_seed_gives_different_output() -> None:
    assert generate_dataset(n=3, seed=1) != generate_dataset(n=3, seed=2)


def test_languages_alternate(dataset: list[GeneratedInvoice]) -> None:
    languages = [inv.truth.language for inv in dataset]
    assert languages.count("fr") == languages.count("en") == 20


def test_amounts_and_totals_follow_the_rules(dataset: list[GeneratedInvoice]) -> None:
    for inv in dataset:
        t = inv.truth
        for line in t.lines:
            assert line.amount == line_amount(line.quantity, line.unit_price)
        totals = compute_totals(t.lines)
        assert (t.total_excl_vat, t.total_vat, t.total_incl_vat) == tuple(totals)


def test_identifiers_and_currency_match_language(dataset: list[GeneratedInvoice]) -> None:
    for inv in dataset:
        t = inv.truth
        if t.language == "fr":
            assert t.currency == "EUR"
            assert t.supplier_siret is not None and is_valid_siret(t.supplier_siret)
            assert t.supplier_vat_number == fr_vat_number(t.supplier_siret[:9])
        else:
            assert t.currency == "GBP"
            assert t.supplier_siret is None
            assert t.supplier_vat_number is not None and t.supplier_vat_number.startswith("GB")


def test_due_date_after_issue_date(dataset: list[GeneratedInvoice]) -> None:
    for inv in dataset:
        if inv.truth.due_date is not None:
            assert inv.truth.due_date > inv.truth.issue_date


def test_cli_writes_invoices_and_manifest(tmp_path: Path) -> None:
    main(["--n", "4", "--seed", "1", "--out", str(tmp_path)])

    manifest = [json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert [entry["id"] for entry in manifest] == ["inv-001", "inv-002", "inv-003", "inv-004"]
    for entry in manifest:
        reloaded = GeneratedInvoice.model_validate_json((tmp_path / entry["file"]).read_text())
        assert reloaded.id == entry["id"]
