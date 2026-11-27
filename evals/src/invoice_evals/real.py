"""Real invoices: turn a folder of anonymized PDFs into an eval dataset.

    # 1. Put the anonymized PDFs in evals/data/real/ (git-ignored: never committed).
    uv run python -m invoice_evals.real prepare --dir evals/data/real
    # 2. Fill the "truth" of every real-NNN.json by hand, reading the PDF.
    uv run python -m invoice_evals.real check --dir evals/data/real
    # 3. Only on a Google project with billing enabled (GEMINI_TIER=paid in .env):
    uv run python -m invoice_evals.run --data evals/data/real

The ground truth of a real invoice is typed by a human, so it is the slow and costly part:
``check`` validates it with the same strict model as the synthetic truth (InvoiceTruth),
so a typo (a date in the wrong format, a line total that is not a number) fails before
any model call.

The free tier of the Gemini API may use what it receives to improve Google's models
(docs/architecture.md). The manifest marks these invoices ``"source": "real"`` and the
harness refuses to send them unless GEMINI_TIER=paid.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from invoice_api.schema import InvoiceTruth

TEMPLATE_TRUTH: dict[str, Any] = {
    **{name: None for name in InvoiceTruth.model_fields if name != "lines"},
    "lines": [],  # one {"description", "quantity", "unit_price", "vat_rate", "amount"} per line
}


def prepare_dataset(directory: Path) -> list[str]:
    """One template per PDF (never overwritten) and a manifest. Returns the ids."""
    pdfs = sorted(p for p in directory.iterdir() if p.suffix.lower() == ".pdf")
    entries = []
    for number, pdf in enumerate(pdfs, start=1):
        invoice_id = f"real-{number:03d}"
        truth_path = directory / f"{invoice_id}.json"
        if not truth_path.exists():
            template = {"id": invoice_id, "truth": TEMPLATE_TRUTH, "render": None}
            truth_path.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n")
        entries.append(
            {
                "id": invoice_id,
                "language": None,  # filled from the truth by check_dataset
                "file": truth_path.name,
                "document": pdf.name,
                "degradation": None,
                "source": "real",
            }
        )
    _write_manifest(directory, entries)
    return [e["id"] for e in entries]


def check_dataset(directory: Path) -> dict[str, str]:
    """{id: problem} for every invoice whose truth is missing or invalid; {} when all good.

    Also copies each valid truth's language into the manifest (segments use it).
    """
    manifest = directory / "manifest.jsonl"
    entries = [json.loads(line) for line in manifest.read_text().splitlines()]
    problems = {}
    for entry in entries:
        data = json.loads((directory / entry["file"]).read_text())
        try:
            truth = InvoiceTruth.model_validate(data["truth"])
        except ValidationError as exc:
            fields = sorted({".".join(map(str, e["loc"])) for e in exc.errors()})
            problems[entry["id"]] = f"{exc.error_count()} invalid field(s): {', '.join(fields)}"
        else:
            entry["language"] = truth.language
    _write_manifest(directory, entries)
    return problems


def _write_manifest(directory: Path, entries: list[dict[str, Any]]) -> None:
    lines = [json.dumps(e, ensure_ascii=False) for e in entries]
    (directory / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Prepare and check the real-invoice dataset.")
    parser.add_argument("command", choices=["prepare", "check"])
    parser.add_argument("--dir", type=Path, default=Path("evals/data/real"))
    args = parser.parse_args(argv)

    if args.command == "prepare":
        ids = prepare_dataset(args.dir)
        print(f"{len(ids)} invoice(s): fill the truth of each JSON, then run 'check'")
        return
    problems = check_dataset(args.dir)
    for invoice_id, problem in problems.items():
        print(f"{invoice_id}: {problem}")
    if problems:
        raise SystemExit(f"{len(problems)} invoice(s) to complete")
    print("every truth is valid")


if __name__ == "__main__":
    main()
