"""CLI: extract one document with Gemini and compare it with its ground truth.

    uv run python -m invoice_evals.extract_one evals/data/week1/inv-001.pdf

Reads GEMINI_API_KEY and EXTRACTION_MODEL from the environment or from .env at the repo
root (the key is never printed). If ``<id>.json`` sits next to the document, prints the
field-by-field comparison with the ground truth.
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from invoice_api.extraction import extract, make_client, mime_type_for
from invoice_evals.generator import GeneratedInvoice
from invoice_evals.metrics import compare_invoice

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract one invoice with Gemini.")
    parser.add_argument("document", type=Path)
    parser.add_argument("--model", default=None, help="overrides EXTRACTION_MODEL")
    args = parser.parse_args(argv)

    load_dotenv()  # .env in the current directory or a parent; existing variables win
    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set (put it in .env, see .env.example)")
    model = args.model or os.environ.get("EXTRACTION_MODEL", DEFAULT_MODEL)

    result = extract(
        args.document.read_bytes(),
        mime_type_for(args.document),
        client=make_client(),
        model=model,
    )
    print(f"model={result.model} prompt={result.prompt_version} latency={result.latency_s}s")
    print(
        f"tokens: input={result.input_tokens} output={result.output_tokens} "
        f"thinking={result.thinking_tokens}"
    )
    if result.error:
        print(f"ERROR: {result.error}")
        if result.raw_text:
            print(result.raw_text)
        return
    assert result.extraction is not None
    print(result.extraction.model_dump_json(indent=2))

    truth_path = args.document.with_suffix(".json")
    if truth_path.exists():
        truth = GeneratedInvoice.model_validate_json(truth_path.read_text()).truth
        print("\n--- comparison with ground truth")
        for r in compare_invoice(truth, result.extraction):
            if r.outcome in ("correct", "both_absent"):
                continue
            where = f" (line {r.line})" if r.line else ""
            print(f"{r.outcome:13} {r.field}{where}: expected={r.expected!r} got={r.got!r}")
        print("(fields not listed are correct)")


if __name__ == "__main__":
    main()
