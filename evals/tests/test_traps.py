"""Trap invoices: each trap must be caught by its own check, and by that check only.

This validates the trap generator and the checks together, before any model is involved:
a perfect reader of a trapped invoice must end up "to_review" for the right reason.
"""

import pytest

from invoice_api.checks import review_status, run_checks
from invoice_evals.generator import CATEGORY_OF, TRAP_CHECK, TRAPS, apply_trap, generate_dataset
from invoice_evals.metrics import perfect_extraction


@pytest.fixture(scope="module")
def french_invoice():  # noqa: ANN201
    return next(inv for inv in generate_dataset(n=6, seed=42) if inv.truth.language == "fr")


def test_untrapped_invoices_pass_every_check() -> None:
    for inv in generate_dataset(n=20, seed=5):
        checks = run_checks(perfect_extraction(inv.truth))
        assert review_status(checks) == "pending", (inv.id, checks)


@pytest.mark.parametrize("trap", sorted(TRAPS))
def test_each_trap_fails_exactly_its_check(french_invoice, trap: str) -> None:  # noqa: ANN001
    trapped = apply_trap(french_invoice, trap)
    failing = {c.name for c in run_checks(perfect_extraction(trapped.truth)) if c.outcome == "fail"}
    assert failing == {TRAP_CHECK[trap]}


def test_apply_trap_keeps_id_and_render(french_invoice) -> None:  # noqa: ANN001
    trapped = apply_trap(french_invoice, "total_mismatch")
    assert trapped.id == french_invoice.id
    assert trapped.render == french_invoice.render
    assert trapped.truth.total_incl_vat != french_invoice.truth.total_incl_vat


def test_every_catalog_item_has_a_category() -> None:
    for inv in generate_dataset(n=20, seed=5):
        for line in inv.truth.lines:
            assert CATEGORY_OF[line.description]
