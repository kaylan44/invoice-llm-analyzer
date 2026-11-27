"""Extraction v1: one Gemini call with structured output, no agent.

The document goes in as an inline part (PDF or image), the prompt says what to read, and the
response is constrained to a JSON schema derived from ``InvoiceExtraction``. The JSON is then
validated by pydantic: the schema guides the model, pydantic is the final check.

Failures (API error, empty answer, invalid JSON) are returned in ``ExtractionResult.error``
instead of raised: the eval harness must count them, not crash on them.
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from invoice_api.schema import InvoiceExtraction

PROMPT_VERSION = "v1"

PROMPT = """\
You extract data from one supplier invoice, written in French or English.
Return only values printed on the document.

Rules:
- supplier_* fields describe the company that issued the invoice, not the customer billed.
- Copy identifiers as printed: invoice number unchanged; VAT number and SIRET without spaces.
- Dates as YYYY-MM-DD.
- Amounts as plain numbers with a dot as decimal separator, no currency symbol and no
  thousands separator: "1 234,50 €" becomes 1234.50.
- currency is the ISO 4217 code: € is EUR, £ is GBP, $ is USD.
- vat_rate is a percentage: "20 %" becomes 20.
- lines: one entry per invoice line, in printed order. The VAT summary and the totals are
  not lines.
- language: the language the invoice is written in.
- If a value is not printed on the invoice, use null. Never guess, and never compute a value
  that is not printed.
"""

MIME_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def mime_type_for(path: Path) -> str:
    try:
        return MIME_TYPES[path.suffix.lower()]
    except KeyError:
        raise ValueError(f"unsupported document type: {path.name}") from None


# --- Response schema -------------------------------------------------------------------
# Pydantic's JSON schema uses $ref, anyOf and regex patterns (a Decimal is "number or string
# matching a pattern"). Gemini's structured output supports a subset of JSON Schema, so we
# rewrite it into plain types: Decimal -> number, "X or null" -> ["X", "null"], refs inlined.

_KEPT_KEYS = ("type", "format", "description", "enum", "items", "properties")


def _simplify(node: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in node:
        target = _simplify(defs[node["$ref"].split("/")[-1]], defs)
        return {**target, **({"description": node["description"]} if "description" in node else {})}

    if "anyOf" in node:
        options = node["anyOf"]
        nullable = any(o.get("type") == "null" for o in options)
        others = [o for o in options if o.get("type") != "null"]
        if {o.get("type") for o in others} == {"number", "string"}:  # pydantic's Decimal
            base: dict[str, Any] = {"type": "number"}
        elif len(others) == 1:
            base = _simplify(others[0], defs)
        else:
            raise ValueError(f"cannot simplify anyOf: {options}")
        if "description" in node:
            base["description"] = node["description"]
        if nullable:
            base["type"] = [base["type"], "null"]
            if "enum" in base:
                base["enum"] = [*base["enum"], None]
        return base

    out = {key: node[key] for key in _KEPT_KEYS if key in node}
    if "items" in out:
        out["items"] = _simplify(out["items"], defs)
    if "properties" in out:
        out["properties"] = {k: _simplify(v, defs) for k, v in out["properties"].items()}
        out["required"] = list(out["properties"])  # explicit null rather than a missing key
    return out


def gemini_response_schema() -> dict[str, Any]:
    schema = InvoiceExtraction.model_json_schema()
    return _simplify(schema, schema.get("$defs", {}))


# --- Client ----------------------------------------------------------------------------

RETRYABLE_STATUS = [429, 500, 503, 504]  # rate limit, server error, overloaded, timeout


def make_client(attempts: int = 4) -> genai.Client:
    """Gemini client reading GEMINI_API_KEY from the environment.

    Transient errors (429, 5xx) are retried by the SDK with exponential backoff: 2 s, 4 s,
    8 s... capped at 30 s. A call that still fails after ``attempts`` is returned as an
    ``api_error`` by ``extract``.
    """
    retry = types.HttpRetryOptions(
        attempts=attempts,
        initial_delay=2.0,
        max_delay=30.0,
        http_status_codes=RETRYABLE_STATUS,
    )
    return genai.Client(http_options=types.HttpOptions(retry_options=retry))


# --- Call ------------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionResult:
    extraction: InvoiceExtraction | None
    error: str | None
    model: str
    prompt_version: str
    latency_s: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None
    raw_text: str | None = None  # the model's raw answer, kept for error analysis
    # Agent v2 only: one entry per tool call, to read what the agent did (empty for v1).
    trace: tuple[dict[str, Any], ...] = ()


def extract(
    document: bytes,
    mime_type: str,
    *,
    client: genai.Client,
    model: str,
    thinking_level: types.ThinkingLevel | None = None,
) -> ExtractionResult:
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=gemini_response_schema(),
        thinking_config=types.ThinkingConfig(thinking_level=thinking_level)
        if thinking_level
        else None,
    )
    contents = [types.Part.from_bytes(data=document, mime_type=mime_type), PROMPT]

    def result(
        error: str | None, extraction: InvoiceExtraction | None = None, **kw: Any
    ) -> ExtractionResult:
        return ExtractionResult(
            extraction=extraction,
            error=error,
            model=model,
            prompt_version=PROMPT_VERSION,
            latency_s=round(time.perf_counter() - start, 3),
            **kw,
        )

    start = time.perf_counter()
    try:
        response = client.models.generate_content(model=model, contents=contents, config=config)
    except errors.APIError as exc:  # ClientError (4xx: quota, bad request) and ServerError (5xx)
        return result(f"api_error {exc.code}: {exc.message}")

    usage = response.usage_metadata
    tokens = {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "thinking_tokens": getattr(usage, "thoughts_token_count", None),
    }
    text = response.text
    if not text:
        reason = response.candidates[0].finish_reason if response.candidates else None
        return result(f"empty_output: finish_reason={reason}", **tokens)

    try:
        extraction = InvoiceExtraction.model_validate_json(text)
    except ValidationError as exc:  # invalid JSON is a ValidationError too
        return result(f"invalid_output: {exc.error_count()} error(s)", raw_text=text, **tokens)

    return result(None, extraction, raw_text=text, **tokens)
