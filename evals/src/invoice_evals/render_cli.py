"""CLI: render the documents of a generated dataset and update its manifest.

    uv run python -m invoice_evals.render_cli --data evals/data/week1 --seed 42 \
        --degrade inv-003=light inv-004=heavy

Each invoice gets ``<id>.pdf`` next to its JSON. Degraded invoices get only the scan:
the clean PDF is never written for them, because the model must only ever see the scan.
"""

import argparse
import json
from pathlib import Path

from invoice_evals.generator import GeneratedInvoice
from invoice_evals.render import PRESETS, describe, render_document


def parse_degradations(items: list[str]) -> dict[str, str]:
    result = {}
    for item in items:
        invoice_id, _, level = item.partition("=")
        if level not in PRESETS:
            raise SystemExit(f"unknown degradation level {level!r} in {item!r}")
        result[invoice_id] = level
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render invoices to PDF, some as degraded scans.")
    parser.add_argument("--data", type=Path, required=True, help="dataset directory")
    parser.add_argument("--seed", type=int, default=42, help="seed for styles and degradations")
    parser.add_argument("--degrade", nargs="*", default=[], metavar="ID=LEVEL")
    args = parser.parse_args(argv)

    degradations = parse_degradations(args.degrade)
    manifest_path = args.data / "manifest.jsonl"
    entries = [json.loads(line) for line in manifest_path.read_text().splitlines()]

    for entry in entries:
        invoice = GeneratedInvoice.model_validate_json((args.data / entry["file"]).read_text())
        level = degradations.get(invoice.id)
        document, style, degradation = render_document(invoice, args.seed, level)
        (args.data / f"{invoice.id}.pdf").write_bytes(document)
        entry["document"] = f"{invoice.id}.pdf"
        entry.update(describe(style, degradation, level))
        print(f"{invoice.id}: {style.layout}, {style.font}, {level or 'clean'}")

    lines = [json.dumps(entry, ensure_ascii=False) for entry in entries]
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
