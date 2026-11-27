"""Retrieval eval tests: query variants and metrics (pure functions, no database)."""

import random

import pytest

from invoice_evals.retrieval import category_queries, name_variants, rank_of, scores


def test_name_variants() -> None:
    variants = dict(name_variants("Lemaître Bouvier S.A.S.", random.Random(1)))
    assert variants["upper"] == "LEMAÎTRE BOUVIER S.A.S."
    assert variants["no_legal_form"] == "Lemaître Bouvier"
    typo = variants["typo"]
    assert typo != "Lemaître Bouvier S.A.S." and len(typo) == len("Lemaître Bouvier S.A.S.") - 1


def test_name_without_legal_form_has_no_such_variant() -> None:
    kinds = [kind for kind, _ in name_variants("Dias", random.Random(1))]
    assert kinds == ["upper", "typo"]


def test_rank_and_scores() -> None:
    assert rank_of("b", ["a", "b", "c"]) == 2
    assert rank_of("z", ["a"]) is None
    s = scores([1, 2, None, 5])
    assert s["recall@1"] == 0.25
    assert s["recall@3"] == 0.5
    assert s["recall@5"] == 0.75
    assert s["mrr"] == pytest.approx((1 + 0.5 + 0 + 0.2) / 4, abs=1e-4)


def test_category_queries_cover_catalog_and_unseen_labels() -> None:
    kinds = {q.kind for q in category_queries()}
    assert kinds == {"catalog", "unseen"}
