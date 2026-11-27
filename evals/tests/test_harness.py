"""Harness tests (step 6): a fake Gemini client that answers from the ground truth.

The fake recognizes each document by its bytes and returns the perfect extraction, or an
error for chosen invoices, so every expected score is known in advance.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from invoice_evals.generate import main as generate_main
from invoice_evals.generator import GeneratedInvoice
from invoice_evals.harness import (
    GROUPS,
    extract_dataset,
    load_records,
    render_report,
    summarize,
)
from invoice_evals.metrics import perfect_extraction
from invoice_evals.render_cli import main as render_main


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """4 invoices: inv-001 fr clean, inv-002 en clean, inv-003 fr light, inv-004 en heavy.

    inv-001 carries a trap (printed total incl. VAT is wrong).
    """
    data = tmp_path_factory.mktemp("data")
    generate_main(
        ["--n", "4", "--seed", "3", "--out", str(data), "--trap", "inv-001=total_mismatch"]
    )
    render_main(["--data", str(data), "--seed", "3", "--degrade", "inv-003=light", "inv-004=heavy"])
    return data


class FakeModels:
    def __init__(self, data: Path, failing: set[str]) -> None:
        self.answers: dict[bytes, str | Exception] = {}
        for entry in map(json.loads, (data / "manifest.jsonl").read_text().splitlines()):
            truth = GeneratedInvoice.model_validate_json((data / entry["file"]).read_text()).truth
            document = (data / entry["document"]).read_bytes()
            if entry["id"] in failing:
                self.answers[document] = errors.ServerError(503, {"error": {"message": "busy"}})
            else:
                self.answers[document] = perfect_extraction(truth).model_dump_json()

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        answer = self.answers[contents[0].inline_data.data]
        if isinstance(answer, Exception):
            raise answer
        usage = SimpleNamespace(
            prompt_token_count=1000, candidates_token_count=200, thoughts_token_count=None
        )
        return SimpleNamespace(text=answer, usage_metadata=usage, candidates=[])


def run(dataset: Path, tmp_path: Path, failing: set[str]) -> dict[str, Any]:
    client = SimpleNamespace(models=FakeModels(dataset, failing))
    extract_dataset(dataset, tmp_path, client=client, model="fake-model")
    records = load_records(dataset, tmp_path)
    return summarize(records, model="fake-model", dataset=str(dataset), run_id="test")


def test_perfect_model_scores_100_percent_everywhere(dataset: Path, tmp_path: Path) -> None:
    summary = run(dataset, tmp_path, failing=set())
    for segment in summary["segments"].values():
        if not segment["n_invoices"]:  # empty segment (no variant here): no score, not 0 %
            continue
        for group in segment["groups"].values():
            assert group["accuracy"] == 1.0
    assert summary["errors"] == {}


def test_segments_split_by_language_and_condition(dataset: Path, tmp_path: Path) -> None:
    segments = run(dataset, tmp_path, failing=set())["segments"]
    counts = {name: s["n_invoices"] for name, s in segments.items()}
    assert counts == {"all": 4, "fr": 2, "en": 2, "clean": 2, "scan": 2, "long": 0, "confusers": 0}


def test_variant_segments_and_report_columns(tmp_path: Path) -> None:
    """Week 3: invoices with variants get their own columns; plain datasets do not."""
    data = tmp_path / "data"
    generate_main(
        [
            "--n",
            "3",
            "--seed",
            "3",
            "--out",
            str(data),
            "--variant",
            "inv-001=long",
            "inv-002=deposit,client_vat",
        ]
    )
    render_main(["--data", str(data), "--seed", "3", "--degrade", "inv-003=medium"])
    run_dir = tmp_path / "run"
    client = SimpleNamespace(models=FakeModels(data, failing=set()))
    extract_dataset(data, run_dir, client=client, model="fake-model")
    records = load_records(data, run_dir)
    assert [r.variants for r in records] == [("long",), ("deposit", "client_vat"), ()]
    summary = summarize(records, model="fake-model", dataset=str(data), run_id="t")
    counts = {name: s["n_invoices"] for name, s in summary["segments"].items()}
    assert counts["long"] == 1 and counts["confusers"] == 1 and counts["scan"] == 1
    report = render_report(summary)
    assert "Multipages (n=1)" in report and "Pièges de lecture (n=1)" in report


def test_report_hides_empty_variant_columns(dataset: Path, tmp_path: Path) -> None:
    report = render_report(run(dataset, tmp_path, failing=set()))
    assert "Multipages" not in report and "Pièges de lecture" not in report


def test_failed_invoice_counts_as_missed_and_is_listed(dataset: Path, tmp_path: Path) -> None:
    summary = run(dataset, tmp_path, failing={"inv-004"})
    assert summary["errors"]["inv-004"].startswith("api_error 503")
    # The failure only hurts the segments inv-004 belongs to: en and scan.
    assert summary["segments"]["fr"]["groups"]["Totaux et devise"]["accuracy"] == 1.0
    assert summary["segments"]["clean"]["groups"]["Totaux et devise"]["accuracy"] == 1.0
    assert summary["segments"]["en"]["groups"]["Totaux et devise"]["accuracy"] == 0.5
    assert summary["fields"]["total_incl_vat"]["missed"] == 1


def test_results_are_saved_and_can_be_rescored(dataset: Path, tmp_path: Path) -> None:
    first = run(dataset, tmp_path, failing={"inv-002"})
    saved = json.loads((tmp_path / "inv-002.json").read_text())
    assert saved["error"].startswith("api_error 503")
    assert saved["extraction"] is None
    # Rescoring from disk gives the same numbers without calling the model again.
    again = summarize(load_records(dataset, tmp_path), model="fake-model", dataset="d", run_id="t")
    assert again["fields"] == first["fields"]


def test_usage_and_cost(dataset: Path, tmp_path: Path) -> None:
    usage = run(dataset, tmp_path, failing=set())["usage"]
    assert usage["input_tokens"] == 4000
    assert usage["output_tokens"] == 800
    assert usage["estimated_cost_usd_paid_tier"] is None  # unknown model: no price


def test_review_detection_with_a_perfect_reader(dataset: Path, tmp_path: Path) -> None:
    rd = run(dataset, tmp_path, failing=set())["review_detection"]
    # The trap is caught; the 3 consistent invoices stay pending.
    assert (rd["true_positive"], rd["false_positive"], rd["false_negative"]) == (1, 0, 0)
    assert rd["true_negative"] == 3
    trapped = next(i for i in rd["invoices"] if i["id"] == "inv-001")
    assert trapped["failed_checks"] == ["totals"]


def test_failed_extraction_is_sent_to_review(dataset: Path, tmp_path: Path) -> None:
    rd = run(dataset, tmp_path, failing={"inv-002"})["review_detection"]
    # inv-002 should have been pending: sending it to review is a false positive.
    assert rd["false_positive"] == 1
    failed = next(i for i in rd["invoices"] if i["id"] == "inv-002")
    assert failed["failed_checks"] == ["extraction_failed"]


def test_stained_totals_expect_review_and_null(tmp_path_factory: pytest.TempPathFactory) -> None:
    data = tmp_path_factory.mktemp("stained")
    generate_main(["--n", "1", "--seed", "3", "--out", str(data)])
    render_main(["--data", str(data), "--seed", "3", "--degrade", "inv-001=stain:totals"])
    run_dir = tmp_path_factory.mktemp("run")
    # The fake model reads everything except the stained totals: the ideal behaviour.
    truth = GeneratedInvoice.model_validate_json((data / "inv-001.json").read_text()).truth
    answer = perfect_extraction(truth).model_copy(
        update={"total_excl_vat": None, "total_vat": None, "total_incl_vat": None}
    )
    models = FakeModels(data, failing=set())
    models.answers = {k: answer.model_dump_json() for k in models.answers}
    extract_dataset(data, run_dir, client=SimpleNamespace(models=models), model="fake")
    summary = summarize(load_records(data, run_dir), model="fake", dataset="d", run_id="t")

    rd = summary["review_detection"]
    assert rd["invoices"][0]["expected"] == "to_review"  # a required total is hidden
    assert rd["invoices"][0]["predicted"] == "to_review"  # ... and the checks see it missing
    assert {h["behaviour"] for h in summary["hidden_fields"]} == {"null"}
    assert all(m["hidden"] for m in summary["mistakes"])
    assert "Champs masqués par une tache" in render_report(summary)


def test_report_has_one_row_per_group(dataset: Path, tmp_path: Path) -> None:
    report = render_report(run(dataset, tmp_path, failing={"inv-003"}))
    for group in GROUPS:
        assert f"| {group} |" in report
    assert "inv-003" in report  # failures appear in the error analysis
