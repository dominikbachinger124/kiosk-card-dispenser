"""Ledger persistence: append-only, balances, reversals, and DB guards."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from kiosk.domain.entities import Session
from kiosk.domain.errors import (
    DuplicateOperationError,
    LedgerIntegrityError,
)
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWork, UnitOfWorkFactory


def _session(uow: UnitOfWork, now: datetime, session_id: str = "s1") -> None:
    uow.sessions.add(Session(id=session_id, flow="test", started_at=now))


def _entry(
    account_id: int,
    now: datetime,
    entry_type: EntryType,
    amount: int,
    deposit: int,
    operation_id: str,
    reversal_of: int | None = None,
    reason: str | None = None,
) -> LedgerEntry:
    return LedgerEntry.new(
        account_id=account_id,
        entry_type=entry_type,
        amount=Money(amount),
        deposit_delta=Money(deposit),
        created_at=now,
        session_id="s1",
        operation_id=operation_id,
        reversal_of=reversal_of,
        reason=reason,
    )


def _new_account(uow_factory: UnitOfWorkFactory, now: datetime) -> int:
    with uow_factory.begin() as uow:
        _session(uow, now)
        account = uow.accounts.add("a" * 64, now)
        uow.commit()
    return account.id


def test_entries_are_stored_and_balances_summed(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    account_id = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-1")
        )
        uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_DEPOSIT, 0, 500, "op-2")
        )
        uow.ledger.append(_entry(account_id, now, EntryType.PAYMENT, -200, 0, "op-3"))
        uow.commit()

    with uow_factory.begin() as uow:
        # Topup 2000 - payment 200; the Fund of 500 is not spendable balance.
        assert uow.ledger.balance_cents(account_id) == 1800
        assert uow.ledger.deposit_cents(account_id) == 500


def test_balance_cannot_become_negative(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    account_id = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-1")
        )
        uow.commit()

    with pytest.raises(LedgerIntegrityError, match="balance would become negative"):  # noqa: SIM117 - error must escape begin() to roll back
        with uow_factory.begin() as uow:
            uow.ledger.append(
                _entry(account_id, now, EntryType.PAYMENT, -2001, 0, "op-2")
            )
            uow.commit()


def test_deposit_per_account_is_not_shared(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    with uow_factory.begin() as uow:
        _session(uow, now)
        first = uow.accounts.add("1" * 64, now).id
        second = uow.accounts.add("2" * 64, now).id
        uow.ledger.append(_entry(first, now, EntryType.CASH_IN_DEPOSIT, 0, 500, "op-a"))
        uow.commit()

    with uow_factory.begin() as uow:
        assert uow.ledger.deposit_cents(first) == 500
        assert uow.ledger.deposit_cents(second) == 0


def test_deposit_cannot_become_negative(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    account_id = _new_account(uow_factory, now)

    with pytest.raises(LedgerIntegrityError, match="deposit would become negative"):  # noqa: SIM117 - error must escape begin() to roll back
        with uow_factory.begin() as uow:
            uow.ledger.append(
                _entry(account_id, now, EntryType.RECYCLE_REFUND, 500, -500, "op-r")
            )
            uow.commit()


def test_update_and_delete_on_ledger_are_rejected(
    uow_factory: UnitOfWorkFactory, now: datetime, db_path: Path
) -> None:
    account_id = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        stored = uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-1")
        )
        uow.commit()
    assert stored.id is not None

    conn = connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute(
                "UPDATE ledger SET amount_cents = 1 WHERE id = ?", (stored.id,)
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM ledger WHERE id = ?", (stored.id,))
    finally:
        conn.close()


def test_repository_exposes_no_update_or_delete() -> None:
    from kiosk.storage.repositories import LedgerRepository

    assert not hasattr(LedgerRepository, "update")
    assert not hasattr(LedgerRepository, "delete")
    assert not hasattr(LedgerRepository, "remove")


def test_reversal_books_counter_entry_and_keeps_original(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    account_id = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        original = uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-1")
        )
        assert original.id is not None
        uow.ledger.append(
            _entry(
                account_id,
                now,
                EntryType.REVERSAL,
                -2000,
                0,
                "op-rev-1",
                reversal_of=original.id,
                reason="Fehlbuchung Gatekeeper",
            )
        )
        uow.commit()

    with uow_factory.begin() as uow:
        assert uow.ledger.balance_cents(account_id) == 0
        assert len(uow.ledger.list_for_account(account_id)) == 2


def test_reversal_is_booked_only_once(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    account_id = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        original = uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-1")
        )
        assert original.id is not None
        uow.ledger.append(
            _entry(
                account_id,
                now,
                EntryType.REVERSAL,
                -2000,
                0,
                "op-rev-1",
                reversal_of=original.id,
                reason="Fehlbuchung",
            )
        )
        # Keep the balance non-negative so only the reversal index can reject.
        uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-2")
        )
        uow.commit()

    with pytest.raises(DuplicateOperationError), uow_factory.begin() as uow:
        uow.ledger.append(
            _entry(
                account_id,
                now,
                EntryType.REVERSAL,
                -2000,
                0,
                "op-rev-2",
                reversal_of=original.id,
                reason="doppelt",
            )
        )
        uow.commit()


def test_reversal_must_reference_same_account(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    first = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        other = uow.accounts.add("c" * 64, now).id
        original = uow.ledger.append(
            _entry(first, now, EntryType.CASH_IN_TOPUP, 2000, 0, "op-x")
        )
        assert original.id is not None
        uow.commit()

    with pytest.raises(LedgerIntegrityError, match="same account"):  # noqa: SIM117 - error must escape begin() to roll back
        with uow_factory.begin() as uow:
            uow.ledger.append(
                _entry(
                    other,
                    now,
                    EntryType.REVERSAL,
                    -2000,
                    0,
                    "op-cross",
                    reversal_of=original.id,
                    reason="falsches Konto",
                )
            )
            uow.commit()


def test_duplicate_operation_id_is_rejected(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    account_id = _new_account(uow_factory, now)
    with uow_factory.begin() as uow:
        uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "same-op")
        )
        uow.commit()

    with pytest.raises(DuplicateOperationError), uow_factory.begin() as uow:
        uow.ledger.append(
            _entry(account_id, now, EntryType.CASH_IN_TOPUP, 2000, 0, "same-op")
        )
        uow.commit()
