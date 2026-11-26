"""Metrics tests (step 3): validate the ruler before measuring the model with it.

Two properties: the truth compared with itself scores 100 %, and a truth deliberately
damaged in known places scores exactly what we expect.
"""

from decimal import Decimal

import pytest

from invoice_api.schema import InvoiceExtraction, InvoiceTruth
from invoice_evals.generator import generate_dataset
from invoice_evals.metrics import (
    FieldScore,
    aggregate,
    compare_invoice,
    normalize_identifier,
    normalize_text,
    perfect_extraction,
)


@pytest.fixture(scope="module")
def truths() -> list[InvoiceTruth]:
    return [inv.truth for inv in generate_dataset(n=10, seed=42)]


def score(pairs: list[tuple[InvoiceTruth, InvoiceExtraction | None]]) -> dict[str, FieldScore]:
    results = [r for truth, extraction in pairs for r in compare_invoice(truth, extraction)]
    return aggregate(results)


# --- Normalization ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Papeterie du Rhône SAS", "  PAPETERIE DU RHONE S.A.S. "),
        ("Porter, Smith and Johnson", "porter smith and johnson"),
        ("Lemaître-Bouvier", "Lemaitre Bouvier"),
        ("Repas d'affaires", "repas d affaires"),
    ],
)
def test_normalize_text_ignores_case_accents_punctuation_spacing(a: str, b: str) -> None:
    assert normalize_text(a) == normalize_text(b)


def test_normalize_text_keeps_real_differences() -> None:
    assert normalize_text("Papeterie du Rhône") != normalize_text("Papeterie du Rhin")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("FR 21 842 157 398", "FR21842157398"),
        ("842.157.398.00012", "84215739800012"),
        ("fac-2026-0412", "FAC-2026-0412"),  # hyphens are part of an invoice number
        (" eur ", "EUR"),
    ],
)
def test_normalize_identifier(raw: str, expected: str) -> None:
    assert normalize_identifier(raw) == expected


# --- Truth against itself --------------------------------------------------------------


def test_truth_against_itself_scores_100_percent(truths: list[InvoiceTruth]) -> None:
    scores = score([(t, perfect_extraction(t)) for t in truths])
    for field, s in scores.items():
        assert s.accuracy == 1.0, field


def test_equal_amounts_with_different_decimals_are_correct(truths: list[InvoiceTruth]) -> None:
    truth = truths[0]
    extraction = perfect_extraction(truth).model_copy(
        update={"total_excl_vat": truth.total_excl_vat.quantize(Decimal("0.0001"))}
    )
    outcomes = {r.field: r.outcome for r in compare_invoice(truth, extraction)}
    assert outcomes["total_excl_vat"] == "correct"


# --- Known damage gives known scores ---------------------------------------------------


def test_wrong_total_on_3_of_10_gives_70_percent(truths: list[InvoiceTruth]) -> None:
    pairs: list[tuple[InvoiceTruth, InvoiceExtraction | None]] = []
    for i, t in enumerate(truths):
        e = perfect_extraction(t)
        if i < 3:
            e = e.model_copy(update={"total_excl_vat": t.total_excl_vat + Decimal("5")})
        pairs.append((t, e))
    scores = score(pairs)
    assert scores["total_excl_vat"].accuracy == pytest.approx(0.7)
    assert scores["total_excl_vat"].wrong == 3
    assert scores["total_vat"].accuracy == 1.0  # damage stays where it was made


def test_missed_siret_lowers_recall_not_precision(truths: list[InvoiceTruth]) -> None:
    french = [t for t in truths if t.language == "fr"]  # 5 invoices, all with a SIRET
    pairs = [(t, perfect_extraction(t)) for t in french]
    pairs[0] = (french[0], pairs[0][1].model_copy(update={"supplier_siret": None}))
    s = score(pairs)["supplier_siret"]
    assert s.missed == 1
    assert s.recall == pytest.approx(4 / 5)
    assert s.precision == 1.0


def test_invented_siret_lowers_precision_not_recall(truths: list[InvoiceTruth]) -> None:
    english = [t for t in truths if t.language == "en"]  # no SIRET in the truth
    pairs = [(t, perfect_extraction(t)) for t in english]
    pairs[0] = (english[0], pairs[0][1].model_copy(update={"supplier_siret": "84215739800012"}))
    s = score(pairs)["supplier_siret"]
    assert s.hallucinated == 1
    assert s.precision == 0.0  # the only SIRET predicted is invented
    assert s.recall is None  # nothing to find: recall is undefined, not 0 or 1
    assert s.accuracy == pytest.approx(4 / 5)  # the other 4 correctly report "no SIRET"


def test_failed_extraction_counts_every_field_as_missed(truths: list[InvoiceTruth]) -> None:
    results = compare_invoice(truths[0], None)
    present = [r for r in results if r.expected is not None]
    assert present and all(r.outcome == "missed" for r in present)


def test_missing_line_is_missed_and_breaks_line_count(truths: list[InvoiceTruth]) -> None:
    truth = next(t for t in truths if len(t.lines) >= 3)
    full = perfect_extraction(truth)
    extraction = full.model_copy(update={"lines": full.lines[:-1]})
    results = compare_invoice(truth, extraction)
    outcomes = {r.field: r.outcome for r in results}
    assert outcomes["line_count"] == "wrong"
    last = len(truth.lines)
    line_results = [r for r in results if r.field.startswith("lines.")]
    missed = [r for r in line_results if r.outcome == "missed"]
    assert len(missed) == 5  # the 5 fields of the last line
    assert all(r.line == last for r in missed)
