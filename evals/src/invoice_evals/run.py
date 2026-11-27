"""CLI: run the evaluation on a dataset.

    # Call the model on every invoice, save answers in evals/results/<run_id>/, score them:
    uv run python -m invoice_evals.run --data evals/data/week1

    # Same, and also write the versioned baseline (summary JSON + Markdown report):
    uv run python -m invoice_evals.run --data evals/data/week1 --baseline evals/baselines/week1

    # Same with the agent (v2) instead of the single call (v1):
    uv run python -m invoice_evals.run --data evals/data/week3 --pipeline v2

    # Re-extract only the invoices that failed in a saved run (quota, 5xx), then score it:
    uv run python -m invoice_evals.run --data evals/data/week3 --retry-errors evals/results/<run_id>

    # Re-score saved answers without calling the model (e.g. after changing the metrics):
    uv run python -m invoice_evals.run --data evals/data/week1 --rescore evals/results/<run_id>

evals/results/ is git-ignored; only baselines are committed.
"""

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from invoice_api.agent import AGENT_VERSION, extract_with_agent
from invoice_api.extraction import PROMPT_VERSION, extract, make_client
from invoice_evals.harness import (
    extract_dataset,
    failed_ids,
    load_records,
    render_report,
    summarize,
)

DEFAULT_MODEL = "gemini-3.5-flash-lite"


def git_sha() -> str:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        return sha + ("-dirty" if dirty.stdout.strip() else "")
    except (OSError, subprocess.CalledProcessError):
        return "nogit"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the extraction eval.")
    parser.add_argument("--data", type=Path, required=True, help="dataset directory")
    parser.add_argument("--model", default=None, help="overrides EXTRACTION_MODEL")
    parser.add_argument("--results", type=Path, default=Path("evals/results"))
    parser.add_argument(
        "--pipeline", choices=["v1", "v2"], default="v1", help="v1: one call; v2: agent"
    )
    parser.add_argument("--rescore", type=Path, default=None, help="saved run directory")
    parser.add_argument(
        "--retry-errors", type=Path, default=None, help="saved run: re-extract failed invoices"
    )
    parser.add_argument("--baseline", type=Path, default=None, help="path without extension")
    args = parser.parse_args(argv)

    load_dotenv()
    if args.retry_errors:
        # Same run, same version: only the invoices that failed (e.g. quota) are sent again.
        run_dir = args.retry_errors
        first = json.loads(next(run_dir.glob("inv-*.json")).read_text())
        model, run_id = first["model"], run_dir.name
        extractor = extract_with_agent if first["prompt_version"] == AGENT_VERSION else extract
        failed = failed_ids(run_dir)
        print(f"retrying {sorted(failed)}")
        extract_dataset(
            args.data, run_dir, client=make_client(), model=model, extractor=extractor, only=failed
        )
    elif args.rescore:
        run_dir = args.rescore
        first = json.loads(next(run_dir.glob("inv-*.json")).read_text())
        model, run_id = first["model"], run_dir.name
    else:
        if not os.environ.get("GEMINI_API_KEY"):
            raise SystemExit("GEMINI_API_KEY is not set (put it in .env, see .env.example)")
        model = args.model or os.environ.get("EXTRACTION_MODEL", DEFAULT_MODEL)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        extractor, version = (
            (extract, PROMPT_VERSION)
            if args.pipeline == "v1"
            else (extract_with_agent, AGENT_VERSION)
        )
        run_id = f"{stamp}_{model}_{version}_{git_sha()}"
        run_dir = args.results / run_id
        extract_dataset(args.data, run_dir, client=make_client(), model=model, extractor=extractor)

    summary = summarize(
        load_records(args.data, run_dir), model=model, dataset=str(args.data), run_id=run_id
    )
    report = render_report(summary)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    (run_dir / "report.md").write_text(report, encoding="utf-8")
    if args.baseline:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.with_suffix(".json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        args.baseline.with_suffix(".md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
