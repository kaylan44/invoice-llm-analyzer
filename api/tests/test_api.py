"""API and pipeline tests (week 2, step 10): end to end on the local database.

A fake Gemini client returns a fixed extraction; a fake embedder replaces the embedding
model. FastAPI's TestClient runs background tasks right after the response, so the
pipeline has finished when the next request is sent.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from invoice_api.app import Settings, create_app
from invoice_api.matching import add_supplier, load_categories

from .fakes import fake_embedder
from .test_checks import VALID

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PDF = ("invoice.pdf", b"%PDF-1.7 fake", "application/pdf")


class FakeGemini:
    def __init__(self) -> None:
        self.answer: dict[str, Any] | None = VALID

    def generate_content(self, **_: Any) -> Any:
        usage = SimpleNamespace(
            prompt_token_count=900, candidates_token_count=300, thoughts_token_count=None
        )
        text = json.dumps(self.answer) if self.answer is not None else None
        return SimpleNamespace(text=text, usage_metadata=usage, candidates=[])


@pytest.fixture
def gemini() -> FakeGemini:
    return FakeGemini()


@pytest.fixture
def api(db: psycopg.Connection, db_url: str, tmp_path: Path, gemini: FakeGemini) -> TestClient:
    load_categories(db, embedder=fake_embedder)
    add_supplier(db, "Papeterie du Rhône SAS", embedder=fake_embedder,
                 vat_number="FR21842157398")  # fmt: skip
    db.commit()
    settings = Settings(api_token=TOKEN, database_url=db_url, storage_dir=tmp_path)
    app = create_app(settings, client=SimpleNamespace(models=gemini), embedder=fake_embedder)
    return TestClient(app)


def upload(api: TestClient) -> dict[str, Any]:
    response = api.post("/invoices", files={"file": PDF}, headers=AUTH)
    assert response.status_code == 202, response.text
    return response.json()


def test_health_needs_no_token(api: TestClient) -> None:
    assert api.get("/health").json() == {"status": "ok"}


def test_requests_without_a_valid_token_are_refused(api: TestClient) -> None:
    assert api.get("/invoices").status_code == 401
    assert api.get("/invoices", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_api_without_configured_token_refuses_everything(db_url: str) -> None:
    app = create_app(Settings(api_token=None, database_url=db_url))
    assert TestClient(app).get("/invoices", headers=AUTH).status_code == 503


def test_upload_runs_the_whole_pipeline(api: TestClient) -> None:
    created = upload(api)
    invoice = api.get(f"/invoices/{created['invoice_id']}", headers=AUTH).json()

    assert invoice["status"] == "pending"
    assert invoice["review_reasons"] == []
    assert invoice["supplier_match"] == "vat_number"  # exact match on the VAT number
    assert invoice["total_incl_vat"] == "400.20"
    assert [line["category_code"] for line in invoice["lines"]] == ["6064", "6064", "6064"]
    assert invoice["job"]["status"] == "done"
    assert invoice["extraction"]["input_tokens"] == 900
    assert "file_path" not in invoice  # internal path never exposed


def test_inconsistent_invoice_goes_to_review_with_its_reason(
    api: TestClient, gemini: FakeGemini
) -> None:
    gemini.answer = {**VALID, "total_incl_vat": "410.20"}
    invoice_id = upload(api)["invoice_id"]
    invoice = api.get(f"/invoices/{invoice_id}", headers=AUTH).json()
    assert invoice["status"] == "to_review"
    assert invoice["review_reasons"][0].startswith("totals:")


def test_second_upload_of_the_same_invoice_is_flagged_as_duplicate(api: TestClient) -> None:
    first = upload(api)["invoice_id"]
    second = upload(api)["invoice_id"]
    invoice = api.get(f"/invoices/{second}", headers=AUTH).json()
    assert invoice["status"] == "to_review"
    assert invoice["review_reasons"] == [
        f"duplicate: same supplier and invoice number as invoice {first}"
    ]


def test_failed_extraction_goes_to_review(api: TestClient, gemini: FakeGemini) -> None:
    gemini.answer = None  # empty model answer
    invoice_id = upload(api)["invoice_id"]
    invoice = api.get(f"/invoices/{invoice_id}", headers=AUTH).json()
    assert invoice["status"] == "to_review"
    assert invoice["review_reasons"][0].startswith("extraction_failed: empty_output")


def test_list_filters_by_status(api: TestClient, gemini: FakeGemini) -> None:
    upload(api)
    gemini.answer = {**VALID, "invoice_number": "OTHER-1", "total_incl_vat": "1.00"}
    upload(api)
    pending = api.get("/invoices", params={"status": "pending"}, headers=AUTH).json()
    to_review = api.get("/invoices", params={"status": "to_review"}, headers=AUTH).json()
    assert (len(pending), len(to_review)) == (1, 1)


def test_upload_rejects_unsupported_and_oversized_files(api: TestClient) -> None:
    docx = ("invoice.docx", b"x", "application/octet-stream")
    assert api.post("/invoices", files={"file": docx}, headers=AUTH).status_code == 415
    big = ("big.pdf", b"0" * (10 * 1024 * 1024 + 1), "application/pdf")
    assert api.post("/invoices", files={"file": big}, headers=AUTH).status_code == 413


def test_job_endpoint(api: TestClient) -> None:
    created = upload(api)
    job = api.get(f"/jobs/{created['job_id']}", headers=AUTH).json()
    assert job["status"] == "done"
    assert api.get(f"/jobs/{'0' * 8}-0000-0000-0000-{'0' * 12}", headers=AUTH).status_code == 404
