"""Agent v2 tests: a scripted fake Gemini client plays the model's turns.

Each test lists the function calls the "model" makes, turn by turn, and checks what the
loop sends back and what it returns. No network, no key.
"""

from typing import Any

from google.genai import errors, types

from invoice_api.agent import AGENT_VERSION, MAX_TURNS, extract_with_agent

GOOD: dict[str, Any] = {
    "supplier_name": "Moulin SA",
    "supplier_vat_number": "FR03668205255",
    "supplier_siret": "66820525589836",
    "invoice_number": "2026-1798",
    "issue_date": "2026-02-18",
    "due_date": "2026-04-04",
    "currency": "EUR",
    "total_excl_vat": 759.5,
    "total_vat": 151.9,
    "total_incl_vat": 911.4,
    "language": "fr",
    "lines": [
        {
            "description": "Ramettes papier A4 80 g",
            "quantity": 5,
            "unit_price": 4.9,
            "vat_rate": 20,
            "amount": 24.5,
        },
        {
            "description": "Abonnement logiciel mensuel",
            "quantity": 15,
            "unit_price": 49,
            "vat_rate": 20,
            "amount": 735,
        },
    ],
}
BAD_SIRET = {**GOOD, "supplier_siret": "66820525589838"}  # one misread digit: Luhn fails


def call(name: str, extraction: dict[str, Any] | None = None, **args: Any) -> types.FunctionCall:
    if extraction is not None:
        args["extraction"] = extraction
    return types.FunctionCall(name=name, args=args)


def response(
    *calls: types.FunctionCall, signature: bytes = b"sig"
) -> types.GenerateContentResponse:
    parts = [types.Part(function_call=c, thought_signature=signature) for c in calls]
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=1000, candidates_token_count=100, thoughts_token_count=10
        ),
    )


class ScriptedModels:
    def __init__(self, turns: list[types.GenerateContentResponse | Exception]) -> None:
        self.turns = list(turns)
        self.requests: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:
        # Copy: the loop appends to the same list after the call.
        self.requests.append({"contents": list(contents), "config": config})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn


def run(turns: list[Any]) -> tuple[Any, ScriptedModels]:
    models = ScriptedModels(turns)
    client: Any = type("Client", (), {"models": models})()
    result = extract_with_agent(b"%PDF-fake", "application/pdf", client=client, model="m")
    return result, models


def function_responses(contents: list[Any]) -> list[types.FunctionResponse]:
    return [
        part.function_response
        for content in contents
        if isinstance(content, types.Content)
        for part in content.parts or []
        if part.function_response
    ]


# --- Happy paths -----------------------------------------------------------------------


def test_direct_submit_returns_the_extraction() -> None:
    result, models = run([response(call("submit_extraction", GOOD))])
    assert result.error is None
    assert result.extraction is not None and result.extraction.invoice_number == "2026-1798"
    assert result.prompt_version == AGENT_VERSION
    assert [step["tool"] for step in result.trace] == ["submit_extraction"]
    assert len(models.requests) == 1


def test_tools_are_forced_and_never_run_automatically() -> None:
    _, models = run([response(call("submit_extraction", GOOD))])
    config = models.requests[0]["config"]
    assert config.tool_config.function_calling_config.mode == types.FunctionCallingConfigMode.ANY
    assert config.automatic_function_calling.disable is True
    names = {d.name for tool in config.tools for d in tool.function_declarations}
    assert names == {"check_extraction", "submit_extraction"}


def test_check_result_is_sent_back_then_submit() -> None:
    result, models = run(
        [response(call("check_extraction", GOOD)), response(call("submit_extraction", GOOD))]
    )
    assert result.error is None
    sent = function_responses(models.requests[1]["contents"])
    assert len(sent) == 1 and sent[0].name == "check_extraction"
    assert sent[0].response["status"] == "pending"
    assert sent[0].response["failed"] == []


def test_failed_check_lets_the_agent_fix_a_misread_value() -> None:
    result, models = run(
        [
            response(call("check_extraction", BAD_SIRET)),
            response(call("submit_extraction", GOOD)),
        ]
    )
    sent = function_responses(models.requests[1]["contents"])[0].response
    assert sent["status"] == "to_review"
    assert [f["check"] for f in sent["failed"]] == ["identifiers"]
    assert result.extraction is not None
    assert result.extraction.supplier_siret == GOOD["supplier_siret"]
    assert result.trace[0]["failed"] == ["identifiers"]


def test_model_turn_is_sent_back_unchanged_with_its_thought_signature() -> None:
    first = response(call("check_extraction", GOOD), signature=b"keep-me")
    _, models = run([first, response(call("submit_extraction", GOOD))])
    assert first.candidates[0].content in models.requests[1]["contents"]


def test_tokens_add_up_over_turns() -> None:
    result, _ = run(
        [response(call("check_extraction", GOOD)), response(call("submit_extraction", GOOD))]
    )
    assert (result.input_tokens, result.output_tokens, result.thinking_tokens) == (2000, 200, 20)


# --- Failures --------------------------------------------------------------------------


def test_invalid_arguments_are_reported_to_the_model() -> None:
    broken = {**GOOD, "issue_date": "18 février"}
    result, models = run(
        [response(call("submit_extraction", broken)), response(call("submit_extraction", GOOD))]
    )
    sent = function_responses(models.requests[1]["contents"])[0].response
    assert "error" in sent and "issue_date" in sent["error"]
    assert result.error is None


def test_without_submit_the_last_valid_draft_is_kept() -> None:
    result, models = run([response(call("check_extraction", GOOD))] * MAX_TURNS)
    assert len(models.requests) == MAX_TURNS
    assert result.error is None
    assert result.extraction is not None
    assert result.trace[-1] == {"tool": "stop", "reason": "max_turns"}


def test_without_any_valid_draft_it_is_an_error() -> None:
    result, _ = run([response(call("check_extraction", {"lines": "oops"}))] * MAX_TURNS)
    assert result.extraction is None
    assert result.error == "no_submission: max_turns"


def test_api_error_is_returned_not_raised() -> None:
    busy = errors.ServerError(503, {"error": {"message": "busy"}})
    result, _ = run([busy])
    assert result.error is not None and result.error.startswith("api_error 503")


def test_a_turn_without_function_call_is_an_error() -> None:
    empty = types.GenerateContentResponse(
        candidates=[
            types.Candidate(content=types.Content(role="model", parts=[types.Part(text="hi")]))
        ]
    )
    result, _ = run([empty])
    assert result.error == "no_function_call"
