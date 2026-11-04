"""Tests for booking rules of ledger entries (no database involved)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kiosk.domain.errors import LedgerRuleError
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money

NOW = datetime(2026, 1, 15, tzinfo=UTC)


def _make(
    entry_type: EntryType,
    amount: int,
    deposit: int,
    reversal_of: int | None = None,
    reason: str | None = None,
) -> LedgerEntry:
    return LedgerEntry.new(
        account_id=1,
        entry_type=entry_type,
        amount=Money(amount),
        deposit_delta=Money(deposit),
        created_at=NOW,
        session_id="s1",
        operation_id=f"op-{entry_type}-{amount}-{deposit}",
        reversal_of=reversal_of,
        reason=reason,
    )


def test_topup_credits_balance_without_deposit() -> None:
    entry = _make(EntryType.CASH_IN_TOPUP, 2000, 0)

    assert entry.amount_cents == 2000
    assert entry.deposit_delta_cents == 0


def test_issue_deposit_adds_pfand() -> None:
    entry = _make(EntryType.CASH_IN_DEPOSIT, 0 + 500, 500)

    assert entry.deposit_delta_cents == 500


def test_recycle_refund_credits_balance_and_reduces_deposit() -> None:
    entry = _make(EntryType.RECYCLE_REFUND, 500, -500)

    assert entry.amount_cents == 500
    assert entry.deposit_delta_cents == -500


def test_payment_debits_balance() -> None:
    entry = _make(EntryType.PAYMENT, -200, 0)

    assert entry.amount_cents == -200


def test_payout_debits_balance() -> None:
    entry = _make(EntryType.PAYOUT, -1500, 0)

    assert entry.amount_cents == -1500


def test_card_cancel_moves_no_money() -> None:
    entry = _make(EntryType.CARD_CANCEL, 0, 0)

    assert entry.amount_cents == 0
    assert entry.deposit_delta_cents == 0


@pytest.mark.parametrize(
    ("entry_type", "amount", "deposit"),
    [
        (EntryType.CASH_IN_TOPUP, -2000, 0),  # topup must credit
        (EntryType.CASH_IN_TOPUP, 2000, 500),  # topup must not touch deposit
        (EntryType.CASH_IN_DEPOSIT, 500, 0),  # deposit must raise Pfand
        (EntryType.RECYCLE_REFUND, 500, 500),  # recycling must lower Pfand
        (EntryType.PAYMENT, 200, 0),  # payment must debit
        (EntryType.PAYOUT, -100, 100),  # payout must not change Pfand
        (EntryType.CARD_CANCEL, 100, 0),  # cancel must not move money
    ],
)
def test_wrong_sign_is_rejected(
    entry_type: EntryType, amount: int, deposit: int
) -> None:
    with pytest.raises(LedgerRuleError):
        _make(entry_type, amount, deposit)


def test_reversal_requires_reference_and_reason() -> None:
    with pytest.raises(LedgerRuleError):
        _make(EntryType.REVERSAL, -2000, 0)
    with pytest.raises(LedgerRuleError):
        _make(EntryType.REVERSAL, -2000, 0, reversal_of=5)


def test_non_reversal_cannot_reference_another_entry() -> None:
    with pytest.raises(LedgerRuleError):
        _make(EntryType.PAYMENT, -200, 0, reversal_of=3)
