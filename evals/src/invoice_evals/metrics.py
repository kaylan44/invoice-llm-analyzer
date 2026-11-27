"""Field-level extraction metrics.

Pipeline: normalize both sides, compare field by field, classify each comparison into one
outcome, then aggregate outcomes into scores.

Outcomes (expected = ground truth, got = extraction):

    correct       both present and equal after normalization
    wrong         both present, different
    missed        expected present, got absent
    hallucinated  expected absent, got present
    both_absent   both absent (e.g. no SIRET on an English invoice, and none extracted)

Scores per field:

    accuracy   (correct + both_absent) / n           "how often is this field right?"
    precision  correct / (correct + wrong + halluc.)  "when it gives a value, is it right?"
    recall     correct / (correct + wrong + missed)   "when there is a value, does it find it?"

Precision and recall matter for optional fields (SIRET, VAT number, due date): accuracy
alone mixes "invented a SIRET" and "missed a SIRET" into one number.
"""

import re
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from invoice_api.schema import InvoiceExtraction, InvoiceTruth
from invoice_api.text import normalize_text

Outcome = Literal["correct", "wrong", "missed", "hallucinated", "both_absent"]

__all__ = ["normalize_text"]  # re-exported: free text is normalized as in retrieval

# --- Normalization ---------------------------------------------------------------------


def normalize_identifier(value: str) -> str:
    """Identifiers (VAT, SIRET, invoice number, currency): spaces and dots removed, upper case.

    Hyphens are kept: in an invoice number they are part of the identifier.
    """
    return re.sub(r"[\s.]", "", value).upper()


def normalize_number(value: Decimal) -> str:
    """98, 98.0 and 98.00 are the same amount: compare and display them as "98"."""
    return format(value.normalize(), "f")


def normalize_date(value: date) -> str:
    return value.isoformat()


# --- Comparison ------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldResult:
    field: str
    outcome: Outcome
    expected: str | None  # normalized, kept for error analysis in the report
    got: str | None
    line: int | None = None  # 1-based line number for "lines.*" fields


def _compare[T](
    field: str,
    expected: T | None,
    got: T | None,
    normalize: Callable[[T], str],
    line: int | None = None,
) -> FieldResult:
    exp = normalize(expected) if expected is not None else None
    act = normalize(got) if got is not None else None
    outcome: Outcome
    if exp is None and act is None:
        outcome = "both_absent"
    elif exp is None:
        outcome = "hallucinated"
    elif act is None:
        outcome = "missed"
    else:
        outcome = "correct" if exp == act else "wrong"
    return FieldResult(field, outcome, exp, act, line)


# Header fields and how to normalize each one.
HEADER_FIELDS: dict[str, Callable] = {
    "supplier_name": normalize_text,
    "supplier_vat_number": normalize_identifier,
    "supplier_siret": normalize_identifier,
    "invoice_number": normalize_identifier,
    "issue_date": normalize_date,
    "due_date": normalize_date,
    "currency": normalize_identifier,
    "total_excl_vat": normalize_number,
    "total_vat": normalize_number,
    "total_incl_vat": normalize_number,
    "language": str,
}

LINE_FIELDS: dict[str, Callable] = {
    "description": normalize_text,
    "quantity": normalize_number,
    "unit_price": normalize_number,
    "vat_rate": normalize_number,
    "amount": normalize_number,
}


def compare_invoice(truth: InvoiceTruth, extraction: InvoiceExtraction | None) -> list[FieldResult]:
    """Compare one extraction with its ground truth.

    ``extraction=None`` means the extraction failed (API error, invalid JSON, refusal):
    every field is then compared with "absent", so it counts as missed.
    Lines are aligned by position (v1): line 1 with line 1, and so on.
    """
    got = extraction if extraction is not None else InvoiceExtraction()

    results = [
        _compare(field, getattr(truth, field), getattr(got, field), normalize)
        for field, normalize in HEADER_FIELDS.items()
    ]

    results.append(
        _compare("line_count", len(truth.lines), len(got.lines) if extraction else None, str)
    )

    for i in range(max(len(truth.lines), len(got.lines))):
        expected_line = truth.lines[i] if i < len(truth.lines) else None
        got_line = got.lines[i] if i < len(got.lines) else None
        for field, normalize in LINE_FIELDS.items():
            results.append(
                _compare(
                    f"lines.{field}",
                    getattr(expected_line, field) if expected_line else None,
                    getattr(got_line, field) if got_line else None,
                    normalize,
                    line=i + 1,
                )
            )
    return results


def perfect_extraction(truth: InvoiceTruth) -> InvoiceExtraction:
    """The extraction a perfect model would return: used to test the metrics themselves."""
    return InvoiceExtraction.model_validate(truth.model_dump())


# --- Aggregation -----------------------------------------------------------------------


@dataclass(frozen=True)
class FieldScore:
    field: str
    n: int
    correct: int
    wrong: int
    missed: int
    hallucinated: int
    both_absent: int

    @property
    def accuracy(self) -> float:
        return (self.correct + self.both_absent) / self.n

    @property
    def precision(self) -> float | None:
        predicted = self.correct + self.wrong + self.hallucinated
        return self.correct / predicted if predicted else None

    @property
    def recall(self) -> float | None:
        actual = self.correct + self.wrong + self.missed
        return self.correct / actual if actual else None


def aggregate(results: Iterable[FieldResult]) -> dict[str, FieldScore]:
    """Count outcomes per field. Filter ``results`` first to score a segment (FR, degraded)."""
    counts: dict[str, Counter[str]] = {}
    for r in results:
        counts.setdefault(r.field, Counter())[r.outcome] += 1
    return {
        field: FieldScore(
            field=field,
            n=sum(c.values()),
            correct=c["correct"],
            wrong=c["wrong"],
            missed=c["missed"],
            hallucinated=c["hallucinated"],
            both_absent=c["both_absent"],
        )
        for field, c in counts.items()
    }
