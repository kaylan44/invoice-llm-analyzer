"""Comparison of two runs on the same dataset (week 3, step 2)."""

import pytest

from invoice_evals.compare import (
    bootstrap_difference,
    compare_records,
    discordant,
    pair_records,
    render_comparison,
    wilson_interval,
)
from invoice_evals.harness import Record
from invoice_evals.metrics import FieldResult


def record(invoice_id: str, outcomes: list[str], condition: str = "clean") -> Record:
    """One invoice: the first outcome is its total_vat, the others are line amounts."""
    results = [
        FieldResult(
            field="total_vat" if i == 0 else "lines.amount",
            outcome=outcome,  # type: ignore[arg-type]
            expected="1",
            got="1" if outcome == "correct" else "2",
            line=None if i == 0 else i,
        )
        for i, outcome in enumerate(outcomes)
    ]
    return Record(id=invoice_id, language="fr", condition=condition, saved={}, results=results)


def run_of(pattern: list[list[str]]) -> list[Record]:
    return [record(f"inv-{i + 1:03d}", outcomes) for i, outcomes in enumerate(pattern)]


# --- Wilson interval -------------------------------------------------------------------


def test_wilson_interval_never_leaves_0_1_and_is_not_degenerate_at_100_percent() -> None:
    low, high = wilson_interval(10, 10)
    assert high == 1.0 and 0.70 < low < 0.75  # 10/10 does not prove "always right"
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and 0.25 < high < 0.30


def test_wilson_interval_shrinks_with_n() -> None:
    small = wilson_interval(9, 10)
    large = wilson_interval(900, 1000)
    assert (small[1] - small[0]) > 5 * (large[1] - large[0])


def test_wilson_interval_of_empty_sample_is_everything() -> None:
    assert wilson_interval(0, 0) == (0.0, 1.0)


# --- Pairing ---------------------------------------------------------------------------


def test_pairing_requires_the_same_invoices() -> None:
    with pytest.raises(ValueError, match="same invoices"):
        pair_records(run_of([["correct"]]), run_of([["correct"], ["correct"]]))


def test_discordant_counts_fields_right_in_one_run_only() -> None:
    a = run_of([["correct", "wrong"], ["wrong", "correct"]])
    b = run_of([["correct", "correct"], ["correct", "wrong"]])
    pairs = pair_records(a, b)
    assert discordant(pairs, lambda field: True) == (1, 2)  # (only A right, only B right)


# --- Paired bootstrap ------------------------------------------------------------------


def test_identical_runs_have_a_zero_difference() -> None:
    a = run_of([["correct", "wrong"]] * 10)
    diff, low, high = bootstrap_difference(pair_records(a, a), lambda f: True, seed=1)
    assert diff == low == high == 0.0


def test_one_better_invoice_out_of_24_is_not_significant() -> None:
    a = run_of([["correct", "correct"]] * 23 + [["wrong", "wrong"]])
    b = run_of([["correct", "correct"]] * 24)
    diff, low, high = bootstrap_difference(pair_records(a, b), lambda f: True, seed=1)
    assert diff > 0
    assert low <= 0 < high  # the interval contains 0: no conclusion


def test_better_on_every_invoice_is_significant() -> None:
    a = run_of([["correct", "wrong"]] * 24)
    b = run_of([["correct", "correct"]] * 24)
    diff, low, high = bootstrap_difference(pair_records(a, b), lambda f: True, seed=1)
    assert diff == pytest.approx(0.5)
    assert low > 0


def test_bootstrap_is_reproducible() -> None:
    a = run_of([["correct", "wrong"], ["wrong", "wrong"], ["correct", "correct"]] * 4)
    b = run_of([["correct", "correct"], ["wrong", "correct"], ["correct", "wrong"]] * 4)
    pairs = pair_records(a, b)
    assert bootstrap_difference(pairs, lambda f: True, seed=3) == bootstrap_difference(
        pairs, lambda f: True, seed=3
    )


# --- Summary and report ----------------------------------------------------------------


def test_compare_records_reports_each_group_and_a_verdict() -> None:
    a = run_of([["correct", "wrong"]] * 24)
    b = run_of([["correct", "correct"]] * 24)
    summary = compare_records(a, b, name_a="v1", name_b="v2", seed=1)
    overall = summary["groups"]["Tous les champs"]
    assert overall["a"]["correct"] == 24 and overall["b"]["correct"] == 48
    assert overall["verdict"] == "B meilleur"
    assert summary["groups"]["Lignes"]["verdict"] == "B meilleur"
    assert summary["groups"]["Fournisseur"]["n"] == 0
    report = render_comparison(summary)
    assert "v1" in report and "v2" in report and "B meilleur" in report
