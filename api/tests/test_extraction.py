"""Extraction tests (step 5). A fake client stands in for Gemini: no network, no quota.

The one test that calls the real API is marked ``live`` and is excluded by default
(``-m "not live"`` in pyproject). Run it explicitly with ``pytest -m live``.
"""

import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from invoice_api.extraction import (
    PROMPT_VERSION,
    extract,
    gemini_response_schema,
    mime_type_for,
)
from invoice_api.schema import InvoiceExtraction

PDF = b"%PDF-1.7 fake bytes"

VALID_OUTPUT = {
    "supplier_name": "Papeterie du Rhône SAS",
    "supplier_vat_number": "FR21842157398",
    "supplier_siret": "84215739800012",
    "invoice_number": "FAC-2026-0412",
    "issue_date": "2026-11-03",
    "due_date": None,
    "currency": "EUR",
    "total_excl_vat": 333.5,
    "total_vat": 66.7,
    "total_incl_vat": 400.2,
    "language": "fr",
    "lines": [
        {
            "description": "Ramettes papier A4 80 g",
            "quantity": 20,
            "unit_price": 4.9,
            "vat_rate": 20,
            "amount": 98,
        }
    ],
}


class FakeModels:
    """Records the call and returns a canned response, like client.models."""

    def __init__(self, text: str | None = None, raise_error: Exception | None = None) -> None:
        self.text = text
        self.raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.raise_error is not None:
            raise self.raise_error
        return SimpleNamespace(
            text=self.text,
            usage_metadata=SimpleNamespace(
                prompt_token_count=1200, candidates_token_count=300, thoughts_token_count=40
            ),
            candidates=[SimpleNamespace(finish_reason="STOP")],
        )


def fake_client(**kwargs: Any) -> Any:
    return SimpleNamespace(models=FakeModels(**kwargs))


# --- Schema sent to Gemini -------------------------------------------------------------


def test_response_schema_uses_only_simple_keywords() -> None:
    # The structured output feature supports a subset of JSON Schema: no $ref, anyOf, pattern.
    text = json.dumps(gemini_response_schema())
    for keyword in ('"$ref"', '"anyOf"', '"pattern"', '"$defs"'):
        assert keyword not in text


def test_response_schema_fields() -> None:
    schema = gemini_response_schema()
    props = schema["properties"]
    assert props["total_excl_vat"]["type"] == ["number", "null"]
    assert props["issue_date"]["format"] == "date"
    assert props["lines"]["items"]["properties"]["amount"]["type"] == ["number", "null"]
    # Every key is required: the model must say null explicitly rather than skip a field.
    assert set(schema["required"]) == set(props)


def test_valid_output_validates_against_the_pydantic_model() -> None:
    # What the schema asks for must be accepted by InvoiceExtraction.
    InvoiceExtraction.model_validate_json(json.dumps(VALID_OUTPUT))


# --- Successful call -------------------------------------------------------------------


def test_extract_returns_validated_extraction_and_usage() -> None:
    client = fake_client(text=json.dumps(VALID_OUTPUT))
    result = extract(PDF, "application/pdf", client=client, model="gemini-test")

    assert result.error is None
    assert result.extraction is not None
    assert result.extraction.total_incl_vat == Decimal("400.2")
    assert result.extraction.lines[0].amount == Decimal("98")
    assert (result.input_tokens, result.output_tokens, result.thinking_tokens) == (1200, 300, 40)
    assert result.model == "gemini-test"
    assert result.prompt_version == PROMPT_VERSION
    assert result.latency_s >= 0


def test_extract_sends_document_schema_and_model() -> None:
    client = fake_client(text=json.dumps(VALID_OUTPUT))
    extract(PDF, "application/pdf", client=client, model="gemini-test")

    call = client.models.calls[0]
    assert call["model"] == "gemini-test"
    document = call["contents"][0]
    assert document.inline_data.data == PDF
    assert document.inline_data.mime_type == "application/pdf"
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_json_schema == gemini_response_schema()


# --- Failures are recorded, not raised -------------------------------------------------


def test_invalid_json_is_an_error_not_a_crash() -> None:
    result = extract(PDF, "application/pdf", client=fake_client(text="{not json"), model="m")
    assert result.extraction is None
    assert result.error is not None and result.error.startswith("invalid_output")
    assert result.raw_text == "{not json"  # kept for error analysis


def test_output_breaking_the_schema_is_an_error() -> None:
    bad = {**VALID_OUTPUT, "total_vat": "about sixty"}
    result = extract(PDF, "application/pdf", client=fake_client(text=json.dumps(bad)), model="m")
    assert result.extraction is None
    assert result.error is not None and result.error.startswith("invalid_output")


def test_empty_output_is_an_error() -> None:
    result = extract(PDF, "application/pdf", client=fake_client(text=None), model="m")
    assert result.extraction is None
    assert result.error is not None and result.error.startswith("empty_output")


def test_api_error_is_recorded_with_its_code() -> None:
    error = errors.ClientError(
        429, {"error": {"code": 429, "message": "quota", "status": "RESOURCE_EXHAUSTED"}}
    )
    result = extract(PDF, "application/pdf", client=fake_client(raise_error=error), model="m")
    assert result.extraction is None
    assert result.error is not None and result.error.startswith("api_error 429")


# --- Helpers ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "mime"),
    [("a.pdf", "application/pdf"), ("b.PNG", "image/png"), ("c.jpg", "image/jpeg")],
)
def test_mime_type_for(name: str, mime: str) -> None:
    assert mime_type_for(Path(name)) == mime


def test_mime_type_for_rejects_unknown_extension() -> None:
    with pytest.raises(ValueError):
        mime_type_for(Path("invoice.docx"))


# --- Real API (opt-in) -----------------------------------------------------------------


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
def test_live_extraction_on_a_synthetic_invoice() -> None:
    from google import genai

    pdf = Path(__file__).parents[2] / "evals" / "data" / "week1" / "inv-001.pdf"
    model = os.environ.get("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    result = extract(pdf.read_bytes(), "application/pdf", client=genai.Client(), model=model)
    assert result.error is None, result.error
    assert result.extraction is not None and result.extraction.invoice_number
