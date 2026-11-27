"""Compare two runs on the same dataset: is B really better than A, or is it noise?

    uv run python -m invoice_evals.compare --data evals/data/week3 \
        --a evals/results/<run v1> --b evals/results/<run v2> --out evals/baselines/week3_v1_v2

Two tools, for two different questions:

- Wilson interval, per run: "with n fields, how far can the true accuracy be from the
  measured one?". Unlike the textbook p ± 1.96·sqrt(p(1-p)/n), it stays inside [0, 1] and
  does not collapse to a zero width at 100 % (10/10 right does not prove "always right").
- Paired bootstrap over invoices, for the difference B - A. Both runs read the same
  invoices, so they are compared invoice by invoice (paired). Invoices are resampled, not
  fields: fields of one invoice fail together (a blurry scan hurts all of them), so
  treating them as independent would claim more certainty than the data gives.

The verdict is "B meilleur" only when the whole 95 % interval of B - A is above 0.
"""

import argparse
import json
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from invoice_evals.harness import GROUPS, Record, load_records

FieldFilter = Callable[[str], bool]
ALL_FIELDS = "Tous les champs"
COMPARED_GROUPS: dict[str, FieldFilter] = {ALL_FIELDS: lambda field: True, **GROUPS}
CORRECT = ("correct", "both_absent")


def wilson_interval(correct: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson score interval for a proportion correct/n."""
    if n == 0:
        return 0.0, 1.0  # no data: anything is possible
    p = correct / n
    denominator = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


@dataclass(frozen=True)
class PairedField:
    field: str
    a_ok: bool
    b_ok: bool


# One invoice = the list of its fields, each scored in both runs.
PairedInvoice = list[PairedField]


def pair_records(a: list[Record], b: list[Record]) -> list[PairedInvoice]:
    """Line up both runs invoice by invoice and field by field."""
    by_id_b = {r.id: r for r in b}
    if [r.id for r in a] != [r.id for r in b]:
        raise ValueError("both runs must cover the same invoices, in the same order")
    pairs = []
    for rec_a in a:
        rec_b = by_id_b[rec_a.id]
        # The fields come from the ground truth, so both runs score the same keys.
        b_ok = {(r.field, r.line): r.outcome in CORRECT for r in rec_b.results}
        pairs.append(
            [
                PairedField(r.field, r.outcome in CORRECT, b_ok[(r.field, r.line)])
                for r in rec_a.results
            ]
        )
    return pairs


def _counts(invoices: list[PairedInvoice], keep: FieldFilter) -> tuple[int, int, int]:
    """(n fields, correct in A, correct in B) over the selected fields."""
    n = a = b = 0
    for invoice in invoices:
        for f in invoice:
            if keep(f.field):
                n += 1
                a += f.a_ok
                b += f.b_ok  # bool is an int: True counts 1
    return n, a, b


def discordant(pairs: list[PairedInvoice], keep: FieldFilter) -> tuple[int, int]:
    """(right in A only, right in B only): the only fields that tell the runs apart."""
    only_a = sum(f.a_ok and not f.b_ok for inv in pairs for f in inv if keep(f.field))
    only_b = sum(f.b_ok and not f.a_ok for inv in pairs for f in inv if keep(f.field))
    return only_a, only_b


def bootstrap_difference(
    pairs: list[PairedInvoice], keep: FieldFilter, *, n_resamples: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    """Accuracy B - A on the selected fields, with its 95 % paired bootstrap interval."""
    n, a, b = _counts(pairs, keep)
    if n == 0:
        return 0.0, 0.0, 0.0
    observed = (b - a) / n
    rng = random.Random(seed)
    diffs = []
    for _ in range(n_resamples):
        # Draw as many invoices as there are, with replacement: some twice, some not at all.
        sample = rng.choices(pairs, k=len(pairs))
        sn, sa, sb = _counts(sample, keep)
        diffs.append((sb - sa) / sn if sn else 0.0)
    diffs.sort()
    low = diffs[int(0.025 * n_resamples)]
    high = diffs[int(0.975 * n_resamples) - 1]
    return round(observed, 4), round(low, 4), round(high, 4)


def _verdict(n: int, low: float, high: float) -> str:
    if n == 0:
        return "—"
    if low > 0:
        return "B meilleur"
    if high < 0:
        return "A meilleur"
    return "pas de différence démontrée"


def compare_records(
    a: list[Record], b: list[Record], *, name_a: str, name_b: str, seed: int = 0
) -> dict[str, Any]:
    pairs = pair_records(a, b)
    groups = {}
    for group, keep in COMPARED_GROUPS.items():
        n, correct_a, correct_b = _counts(pairs, keep)
        diff, low, high = bootstrap_difference(pairs, keep, seed=seed)
        only_a, only_b = discordant(pairs, keep)
        groups[group] = {
            "n": n,
            "a": {"correct": correct_a, "interval": wilson_interval(correct_a, n)},
            "b": {"correct": correct_b, "interval": wilson_interval(correct_b, n)},
            "difference": {"value": diff, "low": low, "high": high},
            "only_a": only_a,
            "only_b": only_b,
            "verdict": _verdict(n, low, high),
        }
    return {"a": name_a, "b": name_b, "n_invoices": len(pairs), "groups": groups}


def _acc(side: dict[str, Any], n: int) -> str:
    low, high = side["interval"]
    return f"{side['correct'] / n:.1%} [{low:.1%} ; {high:.1%}]"


def render_comparison(summary: dict[str, Any]) -> str:
    lines = [
        f"# Comparaison : A = `{summary['a']}`, B = `{summary['b']}`",
        "",
        f"{summary['n_invoices']} factures. Exactitude avec intervalle de Wilson à 95 %."
        " Différence B − A avec intervalle bootstrap apparié par facture (2 000 tirages).",
        "",
        "| Groupe | n champs | A | B | B − A [IC 95 %] | Justes A seul | Justes B seul | Verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for group, g in summary["groups"].items():
        if g["n"] == 0:
            continue
        d = g["difference"]
        lines.append(
            f"| {group} | {g['n']} | {_acc(g['a'], g['n'])} | {_acc(g['b'], g['n'])}"
            f" | {d['value']:+.1%} [{d['low']:+.1%} ; {d['high']:+.1%}]"
            f" | {g['only_a']} | {g['only_b']} | {g['verdict']} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Compare two eval runs on the same dataset.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--a", type=Path, required=True, help="run directory of A (reference)")
    parser.add_argument("--b", type=Path, required=True, help="run directory of B (candidate)")
    parser.add_argument("--out", type=Path, default=None, help="path without extension")
    args = parser.parse_args(argv)

    summary = compare_records(
        load_records(args.data, args.a),
        load_records(args.data, args.b),
        name_a=args.a.name,
        name_b=args.b.name,
    )
    report = render_comparison(summary)
    if args.out:
        args.out.with_suffix(".json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        args.out.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
