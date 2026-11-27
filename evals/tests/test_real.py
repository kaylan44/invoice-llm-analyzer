"""Real invoices (week 3, step 5): templates, completeness check, and the billing guard."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from invoice_evals.harness import extract_dataset, load_records
from invoice_evals.real import check_dataset, prepare_dataset

TRUTH = {
    "supplier_name": "Fournisseur Réel SARL",
    "supplier_vat_number": "FR03668205255",
    "supplier_siret": "66820525589836",
    "invoice_number": "F-2026-001",
    "issue_date": "2026-03-02",
    "due_date": None,
    "currency": "EUR",
    "total_excl_vat": "100.00",
    "total_vat": "20.00",
    "total_incl_vat": "120.00",
    "language": "fr",
    "lines": [
        {
            "description": "Prestation",
            "quantity": "1",
            "unit_price": "100.00",
            "vat_rate": "20",
            "amount": "100.00",
        }
    ],
}


@pytest.fixture
def real_dir(tmp_path: Path) -> Path:
    for name in ("b-facture.pdf", "a-facture.pdf"):
        (tmp_path / name).write_bytes(b"%PDF-1.7 " + name.encode())
    return tmp_path


def fill(real_dir: Path, invoice_id: str, truth: dict) -> None:
    path = real_dir / f"{invoice_id}.json"
    data = json.loads(path.read_text())
    data["truth"] = truth
    path.write_text(json.dumps(data))


def test_prepare_writes_a_template_and_a_manifest_per_pdf(real_dir: Path) -> None:
    prepare_dataset(real_dir)
    entries = [json.loads(line) for line in (real_dir / "manifest.jsonl").read_text().splitlines()]
    assert [e["id"] for e in entries] == ["real-001", "real-002"]
    assert [e["document"] for e in entries] == ["a-facture.pdf", "b-facture.pdf"]  # sorted
    assert all(e["source"] == "real" and e["degradation"] is None for e in entries)
    template = json.loads((real_dir / "real-001.json").read_text())
    assert template["truth"]["total_incl_vat"] is None
    assert template["truth"]["lines"] == []


def test_prepare_never_overwrites_an_annotated_invoice(real_dir: Path) -> None:
    prepare_dataset(real_dir)
    fill(real_dir, "real-001", TRUTH)
    prepare_dataset(real_dir)
    assert json.loads((real_dir / "real-001.json").read_text())["truth"] == TRUTH


def test_check_lists_incomplete_invoices(real_dir: Path) -> None:
    prepare_dataset(real_dir)
    fill(real_dir, "real-001", TRUTH)
    problems = check_dataset(real_dir)
    assert list(problems) == ["real-002"]


def test_check_passes_when_every_truth_is_valid(real_dir: Path) -> None:
    prepare_dataset(real_dir)
    fill(real_dir, "real-001", TRUTH)
    fill(real_dir, "real-002", {**TRUTH, "invoice_number": "F-2026-002"})
    assert check_dataset(real_dir) == {}


# --- Billing guard ---------------------------------------------------------------------


class Boom:
    def generate_content(self, **_: object) -> None:
        raise AssertionError("a real invoice must not reach the model")


def test_real_invoices_are_never_sent_without_a_paid_tier(
    real_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prepare_dataset(real_dir)
    monkeypatch.delenv("GEMINI_TIER", raising=False)
    with pytest.raises(SystemExit, match="GEMINI_TIER=paid"):
        extract_dataset(
            real_dir, tmp_path / "run", client=SimpleNamespace(models=Boom()), model="m"
        )


def test_records_load_without_render_info(real_dir: Path, tmp_path: Path) -> None:
    prepare_dataset(real_dir)
    fill(real_dir, "real-001", TRUTH)
    fill(real_dir, "real-002", {**TRUTH, "invoice_number": "F-2026-002"})
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    for invoice_id in ("real-001", "real-002"):
        saved = {"id": invoice_id, "error": None, "extraction": None, "latency_s": 1.0}
        (run_dir / f"{invoice_id}.json").write_text(json.dumps(saved))
    records = load_records(real_dir, run_dir)
    assert [r.condition for r in records] == ["clean", "clean"]
