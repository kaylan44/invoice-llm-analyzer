"""Evaluation harness: run the extraction on a dataset, save every answer, score it.

Two separate phases, so the model is never called just to recompute a score:

1. ``extract_dataset``: one extraction per invoice, each saved as ``<run_dir>/<id>.json``
   (answer, error, tokens, latency). This is the only phase that calls the API.
2. ``load_records`` + ``summarize``: compare the saved answers with the ground truth and
   aggregate scores per field, per field group and per segment (language, clean or scan).

``render_report`` turns the summary into Markdown, including the list of every error so
they can be read one by one: the number says how often, the list says why.
"""

import json
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from invoice_api.checks import Status, review_status, run_checks
from invoice_api.extraction import PROMPT_VERSION, extract, mime_type_for
from invoice_api.schema import InvoiceExtraction
from invoice_evals.generator import GeneratedInvoice
from invoice_evals.metrics import FieldResult, aggregate, compare_invoice

# Paid-tier prices in USD per million tokens (input, output), read on 2026-11-26 from
# https://ai.google.dev/gemini-api/docs/pricing. Thinking tokens are billed as output.
# The free tier costs nothing: this estimates what the same run would cost once billed.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
}

# Field groups of the eval table in docs/architecture.md (micro-averaged: every field
# comparison in the group counts once).
GROUPS: dict[str, Callable[[str], bool]] = {
    "Fournisseur": lambda f: f in {"supplier_name", "supplier_vat_number", "supplier_siret"},
    "Date et n° de facture": lambda f: f in {"invoice_number", "issue_date", "due_date"},
    "Totaux et devise": lambda f: (
        f in {"total_excl_vat", "total_vat", "total_incl_vat", "currency"}
    ),
    "Lignes": lambda f: f.startswith("lines.") or f == "line_count",
}


@dataclass(frozen=True)
class Record:
    """One invoice of a run: where it comes from, what the model said, how it scored."""

    id: str
    language: str
    condition: str  # "clean", "light", "heavy" or "illegible"
    saved: dict[str, Any]  # the saved extraction result
    results: list[FieldResult]
    # Review detection (week 2): what the checks decided vs what they should decide.
    trap: str | None = None
    expected_status: Status = "pending"
    predicted_status: Status = "pending"
    failed_checks: tuple[str, ...] = ()


SEGMENTS: dict[str, Callable[[Record], bool]] = {
    "all": lambda r: True,
    "fr": lambda r: r.language == "fr",
    "en": lambda r: r.language == "en",
    "clean": lambda r: r.condition == "clean",
    "scan": lambda r: r.condition != "clean",
}


def load_manifest(data_dir: Path) -> list[dict[str, Any]]:
    lines = (data_dir / "manifest.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


# --- Phase 1: extraction ---------------------------------------------------------------


def extract_dataset(data_dir: Path, run_dir: Path, *, client: Any, model: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for entry in load_manifest(data_dir):
        document = data_dir / entry["document"]
        result = extract(document.read_bytes(), mime_type_for(document), client=client, model=model)
        saved = {
            "id": entry["id"],
            "model": result.model,
            "prompt_version": result.prompt_version,
            "error": result.error,
            "latency_s": result.latency_s,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "thinking_tokens": result.thinking_tokens,
            "raw_text": result.raw_text,
            "extraction": result.extraction.model_dump(mode="json") if result.extraction else None,
        }
        (run_dir / f"{entry['id']}.json").write_text(
            json.dumps(saved, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        status = result.error or "ok"
        print(f"{entry['id']}: {status} ({result.latency_s}s)", flush=True)


# --- Phase 2: scoring ------------------------------------------------------------------


def load_records(data_dir: Path, run_dir: Path) -> list[Record]:
    records = []
    for entry in load_manifest(data_dir):
        truth = GeneratedInvoice.model_validate_json((data_dir / entry["file"]).read_text()).truth
        saved = json.loads((run_dir / f"{entry['id']}.json").read_text())
        extraction = (
            InvoiceExtraction.model_validate(saved["extraction"]) if saved["extraction"] else None
        )
        degradation = entry.get("degradation")
        condition = degradation["level"] if degradation else "clean"
        trap = entry.get("trap")
        # A trapped invoice must be flagged; so must an unreadable one (nothing to validate).
        expected: Status = "to_review" if trap or condition == "illegible" else "pending"
        if extraction is None:  # failed extraction: nothing to check, a human must look
            predicted: Status = "to_review"
            failed: tuple[str, ...] = ("extraction_failed",)
        else:
            checks = run_checks(extraction)
            predicted = review_status(checks)
            failed = tuple(c.name for c in checks if c.outcome == "fail")
        records.append(
            Record(
                id=entry["id"],
                language=entry["language"],
                condition=condition,
                saved=saved,
                results=compare_invoice(truth, extraction),
                trap=trap,
                expected_status=expected,
                predicted_status=predicted,
                failed_checks=failed,
            )
        )
    return records


def review_detection(records: list[Record]) -> dict[str, Any]:
    """Precision and recall of the "to_review" status (positive class = to_review).

    precision: of the invoices sent to review, how many had to be?  (wasted human time)
    recall:    of the invoices that had to be reviewed, how many were? (errors let through)
    """
    tp = sum(r.predicted_status == r.expected_status == "to_review" for r in records)
    fp = sum(r.predicted_status == "to_review" != r.expected_status for r in records)
    fn = sum(r.expected_status == "to_review" != r.predicted_status for r in records)
    tn = len(records) - tp - fp - fn
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "invoices": [
            {
                "id": r.id,
                "trap": r.trap,
                "condition": r.condition,
                "expected": r.expected_status,
                "predicted": r.predicted_status,
                "failed_checks": list(r.failed_checks),
            }
            for r in records
        ],
    }


def _group_score(results: list[FieldResult], in_group: Callable[[str], bool]) -> dict[str, Any]:
    selected = [r for r in results if in_group(r.field)]
    correct = sum(r.outcome in ("correct", "both_absent") for r in selected)
    n = len(selected)
    return {"accuracy": round(correct / n, 4) if n else None, "correct": correct, "n": n}


def _round(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def summarize(records: list[Record], *, model: str, dataset: str, run_id: str) -> dict[str, Any]:
    segments = {}
    for name, belongs in SEGMENTS.items():
        members = [r for r in records if belongs(r)]
        results = [res for r in members for res in r.results]
        segments[name] = {
            "n_invoices": len(members),
            "groups": {g: _group_score(results, in_group) for g, in_group in GROUPS.items()},
        }

    fields = {
        name: {
            "n": s.n,
            "accuracy": _round(s.accuracy),
            "precision": _round(s.precision),
            "recall": _round(s.recall),
            "correct": s.correct,
            "wrong": s.wrong,
            "missed": s.missed,
            "hallucinated": s.hallucinated,
            "both_absent": s.both_absent,
        }
        for name, s in sorted(aggregate(res for r in records for res in r.results).items())
    }

    def total(key: str) -> int:
        return sum(r.saved.get(key) or 0 for r in records)

    input_tokens, output_tokens = total("input_tokens"), total("output_tokens")
    thinking_tokens = total("thinking_tokens")
    price = PRICES_PER_MTOK.get(model)
    cost = (
        round((input_tokens * price[0] + (output_tokens + thinking_tokens) * price[1]) / 1e6, 5)
        if price
        else None
    )
    latencies = [r.saved["latency_s"] for r in records]

    return {
        "run_id": run_id,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "dataset": dataset,
        "n_invoices": len(records),
        "errors": {r.id: r.saved["error"] for r in records if r.saved["error"]},
        "segments": segments,
        "fields": fields,
        "review_detection": review_detection(records),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
            "estimated_cost_usd_paid_tier": cost,
            "latency_s": {
                "mean": round(statistics.mean(latencies), 3),
                "max": round(max(latencies), 3),
            },
        },
        "mistakes": [
            {
                "id": r.id,
                "language": r.language,
                "condition": r.condition,
                "field": res.field,
                "line": res.line,
                "outcome": res.outcome,
                "expected": res.expected,
                "got": res.got,
            }
            for r in records
            for res in r.results
            if res.outcome not in ("correct", "both_absent")
        ],
    }


# --- Report ----------------------------------------------------------------------------


def _cell(score: dict[str, Any]) -> str:
    if score["accuracy"] is None:
        return "—"
    return f"{score['accuracy']:.0%} ({score['correct']}/{score['n']})"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def render_report(summary: dict[str, Any]) -> str:
    seg = summary["segments"]
    columns = ["all", "fr", "en", "clean", "scan"]
    header_names = {
        "all": "Tout",
        "fr": "Français",
        "en": "Anglais",
        "clean": "Propres",
        "scan": "Scans dégradés",
    }
    lines = [
        f"# Évaluation {summary['run_id']}",
        "",
        f"Modèle `{summary['model']}`, prompt `{summary['prompt_version']}`, "
        f"jeu `{summary['dataset']}` ({summary['n_invoices']} factures : "
        + ", ".join(f"{seg[c]['n_invoices']} {header_names[c].lower()}" for c in columns[1:])
        + ").",
        "",
        "## Exactitude par groupe de champs",
        "",
        "| Groupe | "
        + " | ".join(f"{header_names[c]} (n={seg[c]['n_invoices']})" for c in columns)
        + " |",
        "| --- |" + " --- |" * len(columns),
    ]
    for group in GROUPS:
        cells = " | ".join(_cell(seg[c]["groups"][group]) for c in columns)
        lines.append(f"| {group} | {cells} |")

    lines += [
        "",
        "## Détail par champ (toutes factures)",
        "",
        "| Champ | Exactitude | Précision | Rappel | Faux | Manqués | Inventés |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, f in summary["fields"].items():
        lines.append(
            f"| `{name}` | {_pct(f['accuracy'])} | {_pct(f['precision'])} | {_pct(f['recall'])}"
            f" | {f['wrong']} | {f['missed']} | {f['hallucinated']} |"
        )

    usage = summary["usage"]
    cost = usage["estimated_cost_usd_paid_tier"]
    lines += [
        "",
        "## Coût et latence",
        "",
        f"- Tokens : {usage['input_tokens']} en entrée, {usage['output_tokens']} en sortie, "
        f"{usage['thinking_tokens']} de réflexion.",
        f"- Coût estimé sur l'offre payante : {'inconnu' if cost is None else f'{cost:.4f} $'}"
        " (0 $ sur l'offre gratuite).",
        f"- Latence par facture : {usage['latency_s']['mean']} s en moyenne, "
        f"{usage['latency_s']['max']} s au maximum.",
        "",
    ]
    rd = summary["review_detection"]
    lines += [
        "## Détection « à vérifier » (contrôles de cohérence)",
        "",
        f"- Précision : {_pct(rd['precision'])} ({rd['true_positive']} justes sur "
        f"{rd['true_positive'] + rd['false_positive']} factures envoyées en revue).",
        f"- Rappel : {_pct(rd['recall'])} ({rd['true_positive']} détectées sur "
        f"{rd['true_positive'] + rd['false_negative']} factures à revoir).",
        "",
        "| Facture | Piège | État | Attendu | Obtenu | Contrôles en échec |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for inv in rd["invoices"]:
        mark = "" if inv["expected"] == inv["predicted"] else " ✗"
        lines.append(
            f"| {inv['id']} | {inv['trap'] or '—'} | {inv['condition']} | {inv['expected']}"
            f" | {inv['predicted']}{mark} | {', '.join(inv['failed_checks']) or '—'} |"
        )
    lines += [
        "",
        "## Échecs d'extraction",
        "",
    ]
    errors = summary["errors"]
    lines += [f"- `{i}` : {e}" for i, e in errors.items()] or ["Aucun."]

    lines += ["", "## Analyse des erreurs (chaque champ faux, manqué ou inventé)", ""]
    mistakes = [m for m in summary["mistakes"] if m["id"] not in errors]
    if not mistakes:
        lines.append("Aucune.")
    else:
        lines += [
            "| Facture | Segment | Champ | Résultat | Attendu | Obtenu |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for m in mistakes:
            field = m["field"] + (f" (ligne {m['line']})" if m["line"] else "")
            lines.append(
                f"| {m['id']} | {m['language']}, {m['condition']} | `{field}` | {m['outcome']}"
                f" | {m['expected']!r} | {m['got']!r} |"
            )
    return "\n".join(lines) + "\n"
