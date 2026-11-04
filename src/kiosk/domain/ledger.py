"""Append-only ledger entries and the booking rules per entry type.

Two independent per-account quantities exist:

* ``balance``: spendable credit (payments reduce it, never below zero).
* ``deposit``: outstanding Pfand per account, not shared between accounts.

Corrections are never edits. They are new entries that reference the
original via ``reversal_of``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kiosk.domain.errors import LedgerRuleError
from kiosk.domain.money import Money


class EntryType(StrEnum):
    """Kinds of ledger bookings."""

    CASH_IN_TOPUP = "cash_in_topup"
    CASH_IN_DEPOSIT = "cash_in_deposit"
    RECYCLE_REFUND = "recycle_refund"
    PAYMENT = "payment"
    PAYOUT = "payout"
    CARD_CANCEL = "card_cancel"
    REVERSAL = "reversal"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One immutable booking.

    Attributes:
        id: Primary key, None until persisted.
        account_id: Account the booking belongs to.
        entry_type: Kind of booking.
        amount_cents: Signed amount: positive credits, negative debits.
        deposit_delta_cents: Signed change of the account's Pfand.
        created_at: Booking time, UTC.
        session_id: Session that produced the booking.
        operation_id: Caller-supplied id; unique per booking to stop duplicates.
        card_id: Affected card, if any.
        reversal_of: Id of the entry this entry corrects, if any.
        reason: Short, non-personal reason for corrections.
    """

    id: int | None
    account_id: int
    entry_type: EntryType
    amount_cents: int
    deposit_delta_cents: int
    created_at: datetime
    session_id: str
    operation_id: str
    card_id: int | None = None
    reversal_of: int | None = None
    reason: str | None = None

    @staticmethod
    def new(
        *,
        account_id: int,
        entry_type: EntryType,
        amount: Money,
        deposit_delta: Money,
        created_at: datetime,
        session_id: str,
        operation_id: str,
        card_id: int | None = None,
        reversal_of: int | None = None,
        reason: str | None = None,
    ) -> LedgerEntry:
        """Build an entry and validate it against the booking rules.

        Raises:
            LedgerRuleError: If the amount sign or deposit change does not
                match the entry type.
        """
        _validate_rules(entry_type, amount, deposit_delta, reversal_of, reason)
        return LedgerEntry(
            id=None,
            account_id=account_id,
            entry_type=entry_type,
            amount_cents=amount.cents,
            deposit_delta_cents=deposit_delta.cents,
            created_at=created_at,
            session_id=session_id,
            operation_id=operation_id,
            card_id=card_id,
            reversal_of=reversal_of,
            reason=reason,
        )


def _validate_rules(
    entry_type: EntryType,
    amount: Money,
    deposit_delta: Money,
    reversal_of: int | None,
    reason: str | None,
) -> None:
    if entry_type is EntryType.REVERSAL:
        if reversal_of is None or not reason:
            raise LedgerRuleError("reversal needs reversal_of and a reason")
        return
    if reversal_of is not None:
        raise LedgerRuleError("only reversal entries may set reversal_of")

    expected: dict[EntryType, tuple[int, int]] = {
        # (amount sign, deposit delta sign); 0 means "must be zero".
        EntryType.CASH_IN_TOPUP: (1, 0),
        EntryType.CASH_IN_DEPOSIT: (1, 1),
        EntryType.RECYCLE_REFUND: (1, -1),
        EntryType.PAYMENT: (-1, 0),
        EntryType.PAYOUT: (-1, 0),
        EntryType.CARD_CANCEL: (0, 0),
    }
    amount_sign, deposit_sign = expected[entry_type]
    if _sign(amount.cents) != amount_sign:
        raise LedgerRuleError(f"{entry_type} requires amount sign {amount_sign}")
    if _sign(deposit_delta.cents) != deposit_sign:
        raise LedgerRuleError(f"{entry_type} requires deposit sign {deposit_sign}")


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0
