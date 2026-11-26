"""CLI: write a synthetic dataset to disk.

    uv run python -m invoice_evals.generate --n 10 --seed 42 --out evals/data/week1

    # Add invoices to an existing dataset without touching the others:
    uv run python -m invoice_evals.generate --n 11 --seed 42 --out evals/data/week1 --only inv-011

Writes one ``<id>.json`` per invoice (ground truth + render info) and ``manifest.jsonl``
(one line per invoice; step 4 adds the rendered file and its degradation).

The dataset is a sequence drawn from one seed: invoice k is the same whether n is 10 or 11,
so ``--only`` can extend a dataset reproducibly.
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
    parser.add_argument("--only", nargs="*", default=None, metavar="ID", help="write only these")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.jsonl"
    # With --only, keep the existing manifest entries (and their rendering info) as they are.
    entries: dict[str, dict] = {}
    if args.only is not None and manifest_path.exists():
        for line in manifest_path.read_text().splitlines():
            entry = json.loads(line)
            entries[entry["id"]] = entry

    written = 0
    for invoice in generate_dataset(args.n, args.seed):
        if args.only is not None and invoice.id not in args.only:
            continue
        path = args.out / f"{invoice.id}.json"
        path.write_text(invoice.model_dump_json(indent=2) + "\n", encoding="utf-8")
        entries[invoice.id] = {
            "id": invoice.id,
            "language": invoice.truth.language,
            "file": path.name,
        }
        written += 1

    lines = [json.dumps(entries[i], ensure_ascii=False) for i in sorted(entries)]
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{written} invoices written to {args.out}")


if __name__ == "__main__":
    main()
