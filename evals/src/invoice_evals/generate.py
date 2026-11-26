"""CLI: write a synthetic dataset to disk.

    uv run python -m invoice_evals.generate --n 10 --seed 42 --out evals/data/week1

Writes one ``<id>.json`` per invoice (ground truth + render info) and ``manifest.jsonl``
(one line per invoice; step 4 adds the rendered file and its degradation).
"""

import argparse
import json
from pathlib import Path

from invoice_evals.generator import generate_dataset


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic invoices with ground truth.")
    parser.add_argument("--n", type=int, default=10, help="number of invoices")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument("--out", type=Path, required=True, help="output directory")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for invoice in generate_dataset(args.n, args.seed):
        path = args.out / f"{invoice.id}.json"
        path.write_text(invoice.model_dump_json(indent=2) + "\n", encoding="utf-8")
        manifest.append({"id": invoice.id, "language": invoice.truth.language, "file": path.name})

    lines = [json.dumps(entry, ensure_ascii=False) for entry in manifest]
    (args.out / "manifest.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(manifest)} invoices written to {args.out}")


if __name__ == "__main__":
    main()
