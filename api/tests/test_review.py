"""Review endpoints (week 3): document, corrections, validation, export.

Same setup as test_api.py: local database, fake Gemini, fake embedder.
"""

import csv
import io

from fastapi.testclient import TestClient

from .test_api import AUTH, PDF, FakeGemini, upload
from .test_checks import VALID


def get(api: TestClient, invoice_id: str) -> dict:
    return api.get(f"/invoices/{invoice_id}", headers=AUTH).json()


# --- Document --------------------------------------------------------------------------


def test_document_is_served_with_its_type(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    response = api.get(f"/invoices/{invoice_id}/document", headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == PDF[1]


def test_document_needs_the_token(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    assert api.get(f"/invoices/{invoice_id}/document").status_code == 401


# --- Corrections -----------------------------------------------------------------------


def test_correction_reruns_the_checks_and_clears_the_review(
    api: TestClient, gemini: FakeGemini
) -> None:
    gemini.answer = {**VALID, "total_incl_vat": "410.20"}  # misread total
    invoice_id = upload(api)["invoice_id"]
    assert get(api, invoice_id)["status"] == "to_review"

    response = api.patch(f"/invoices/{invoice_id}", json={"total_incl_vat": "400.20"}, headers=AUTH)
    assert response.status_code == 200, response.text
    invoice = response.json()
    assert invoice["total_incl_vat"] == "400.20"
    assert invoice["status"] == "pending"
    assert invoice["review_reasons"] == []


def test_correction_can_create_a_review_reason(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    invoice = api.patch(
        f"/invoices/{invoice_id}", json={"due_date": "2000-01-01"}, headers=AUTH
    ).json()
    assert invoice["status"] == "to_review"
    assert invoice["review_reasons"][0].startswith("dates:")


def test_correction_only_touches_sent_fields(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    before = get(api, invoice_id)
    after = api.patch(f"/invoices/{invoice_id}", json={"invoice_number": "X-1"}, headers=AUTH)
    after_json = after.json()
    assert after_json["invoice_number"] == "X-1"
    assert after_json["supplier_name"] == before["supplier_name"]
    assert after_json["total_incl_vat"] == before["total_incl_vat"]


def test_correction_rejects_unknown_fields_and_bad_values(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    assert api.patch(f"/invoices/{invoice_id}", json={"status": "validated"},
                     headers=AUTH).status_code == 422  # fmt: skip
    assert api.patch(f"/invoices/{invoice_id}", json={"issue_date": "hier"},
                     headers=AUTH).status_code == 422  # fmt: skip


def test_duplicate_reason_survives_a_correction(api: TestClient) -> None:
    upload(api)
    second = upload(api)["invoice_id"]
    invoice = api.patch(f"/invoices/{second}", json={"supplier_name": "Papeterie du Rhône"},
                        headers=AUTH).json()  # fmt: skip
    assert invoice["status"] == "to_review"
    assert invoice["review_reasons"][0].startswith("duplicate:")


# --- Validation ------------------------------------------------------------------------


def test_pending_invoice_is_validated(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    response = api.post(f"/invoices/{invoice_id}/validate", json={}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["status"] == "validated"


def test_invoice_to_review_needs_an_explicit_acknowledgement(
    api: TestClient, gemini: FakeGemini
) -> None:
    gemini.answer = {**VALID, "total_incl_vat": "410.20"}
    invoice_id = upload(api)["invoice_id"]
    refused = api.post(f"/invoices/{invoice_id}/validate", json={}, headers=AUTH)
    assert refused.status_code == 409
    accepted = api.post(
        f"/invoices/{invoice_id}/validate", json={"acknowledge_reasons": True}, headers=AUTH
    )
    assert accepted.json()["status"] == "validated"


def test_validated_invoice_is_locked(api: TestClient) -> None:
    invoice_id = upload(api)["invoice_id"]
    api.post(f"/invoices/{invoice_id}/validate", json={}, headers=AUTH)
    patch = api.patch(f"/invoices/{invoice_id}", json={"invoice_number": "X"}, headers=AUTH)
    assert patch.status_code == 409


def test_unknown_invoice_is_404(api: TestClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert api.patch(f"/invoices/{missing}", json={}, headers=AUTH).status_code == 404
    assert api.post(f"/invoices/{missing}/validate", json={}, headers=AUTH).status_code == 404
    assert api.get(f"/invoices/{missing}/document", headers=AUTH).status_code == 404


# --- Export ----------------------------------------------------------------------------


def test_export_contains_only_validated_invoices(api: TestClient, gemini: FakeGemini) -> None:
    validated = upload(api)["invoice_id"]
    api.post(f"/invoices/{validated}/validate", json={}, headers=AUTH)
    gemini.answer = {**VALID, "invoice_number": "OTHER-1"}
    upload(api)  # pending, not exported

    as_json = api.get("/export", params={"format": "json"}, headers=AUTH).json()
    assert [row["id"] for row in as_json] == [validated]

    response = api.get("/export", params={"format": "csv"}, headers=AUTH)
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1 and rows[0]["total_incl_vat"] == "400.20"
