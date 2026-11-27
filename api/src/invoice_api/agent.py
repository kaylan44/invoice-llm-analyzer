"""Extraction v2: an agent that checks its own draft before answering.

The model gets the document and two tools:

- ``check_extraction(extraction)``: runs the consistency checks of ``checks.py`` on a draft
  and returns what fails (a SIRET whose Luhn key is wrong, lines that do not add up...).
- ``submit_extraction(extraction)``: the final answer; it ends the loop.

The loop is written by hand (no framework, no automatic function calling): call the model,
run the tool it asked for, send the result back, repeat until it submits or ``MAX_TURNS``
is reached. ``mode=ANY`` forces a tool call on every turn, so every answer is structured.

Each model turn is appended to the history exactly as received: on Gemini 3 models, function
call parts carry a ``thought_signature`` that must come back with them, or the model loses
its reasoning between turns (google-genai 3.6.1: ``types.Part.thought_signature``).

The risk this version must be measured on: an agent that "fixes" an invoice that is wrong on
paper. The checks exist to send such invoices to a human, so the prompt says to keep the
printed values. The week 2 traps measure exactly that.
"""

import json
import time
from typing import Any

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from invoice_api.checks import review_status, run_checks
from invoice_api.extraction import PROMPT, ExtractionResult, gemini_response_schema
from invoice_api.schema import InvoiceExtraction

AGENT_VERSION = "agent-v1"
MAX_TURNS = 4  # draft, check, fix, submit

AGENT_PROMPT = (
    PROMPT
    + """
Workflow:
1. Read the invoice and fill the extraction.
2. Call check_extraction with your draft. It runs consistency checks (sums, VAT, dates,
   SIRET and VAT number keys) and lists what fails.
3. If a check fails, look again at the document where the failing values are printed.
   Change a value only if you misread it: a digit confused with a letter (8/B, 0/O, 5/S),
   a skipped or duplicated line, a decimal separator.
   If the document itself is inconsistent (printed totals that do not add up, a due date
   before the issue date, an invalid identifier printed as such), keep the printed values:
   the failed check will send the invoice to a human, which is the right outcome.
4. Call submit_extraction with your final extraction.
"""
)


def _extraction_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"extraction": gemini_response_schema()},
        "required": ["extraction"],
    }


TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="check_extraction",
                description="Run the consistency checks on a draft extraction. "
                "Returns the status and the failed checks with their messages.",
                parameters_json_schema=_extraction_parameters(),
            ),
            types.FunctionDeclaration(
                name="submit_extraction",
                description="Submit the final extraction. Ends the task.",
                parameters_json_schema=_extraction_parameters(),
            ),
        ]
    )
]


def _config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        tools=TOOLS,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.ANY  # a tool call on every turn
            )
        ),
        # We pass declarations, not Python functions, so nothing could run by itself;
        # disabling it states the intent and guards against a future refactor.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def _parse(call: types.FunctionCall) -> InvoiceExtraction:
    """The tool arguments, validated by pydantic like a v1 answer (raises ValidationError)."""
    args = call.args or {}
    return InvoiceExtraction.model_validate_json(json.dumps(args.get("extraction")))


def _check_response(extraction: InvoiceExtraction) -> dict[str, Any]:
    checks = run_checks(extraction)
    return {
        "status": review_status(checks),
        "failed": [{"check": c.name, "message": c.message} for c in checks if c.outcome == "fail"],
    }


def extract_with_agent(
    document: bytes, mime_type: str, *, client: genai.Client, model: str
) -> ExtractionResult:
    start = time.perf_counter()
    tokens = {"input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0}
    trace: list[dict[str, Any]] = []
    last_valid: InvoiceExtraction | None = None

    def result(error: str | None, extraction: InvoiceExtraction | None = None) -> ExtractionResult:
        return ExtractionResult(
            extraction=extraction,
            error=error,
            model=model,
            prompt_version=AGENT_VERSION,
            latency_s=round(time.perf_counter() - start, 3),
            trace=tuple(trace),
            **tokens,
        )

    contents: list[Any] = [types.Part.from_bytes(data=document, mime_type=mime_type), AGENT_PROMPT]
    config = _config()

    for _ in range(MAX_TURNS):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as exc:
            return result(f"api_error {exc.code}: {exc.message}", last_valid)

        usage = response.usage_metadata
        tokens["input_tokens"] += (usage and usage.prompt_token_count) or 0
        tokens["output_tokens"] += (usage and usage.candidates_token_count) or 0
        tokens["thinking_tokens"] += (usage and usage.thoughts_token_count) or 0

        calls = response.function_calls or []
        if not calls or not response.candidates or not response.candidates[0].content:
            return result("no_function_call", last_valid)
        contents.append(response.candidates[0].content)  # as received: keeps the signatures

        replies = []
        for call in calls:
            name = call.name or ""
            try:
                extraction = _parse(call)
            except ValidationError as exc:
                trace.append({"tool": name, "error": f"{exc.error_count()} invalid field(s)"})
                reply: dict[str, Any] = {"error": str(exc)}
            else:
                last_valid = extraction
                if name == "submit_extraction":
                    trace.append({"tool": name})
                    return result(None, extraction)
                reply = _check_response(extraction)
                trace.append({"tool": name, "failed": [f["check"] for f in reply["failed"]]})
            replies.append(types.Part.from_function_response(name=name, response=reply))
        contents.append(types.Content(role="user", parts=replies))

    trace.append({"tool": "stop", "reason": "max_turns"})
    if last_valid is None:
        return result("no_submission: max_turns")
    return result(None, last_valid)
