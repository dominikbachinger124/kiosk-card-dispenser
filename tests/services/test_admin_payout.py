"""AdminPayoutService over a real migrated database."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiosk.domain.entities import CardStatus, Session
from kiosk.domain.errors import (
    AccountClosedError,
    NotFoundError,
    PayoutNotConfirmedError,
)
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.services.admin_payout import AdminPayoutService, PayoutConfirmation
from kiosk.storage.database import connect
from kiosk.storage.repositories import AccountRepository
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT

DEPOSIT = Money(500)
HASHER = CardIdHasher(TEST_SALT)
CONFIRMED = PayoutConfirmation(
    cash_handed_over=True, open_cards_acknowledged=True, final_confirmed=True
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _book(
    uow_factory: UnitOfWorkFactory,
    *,
    account_id: int,
    entry_type: EntryType,
    amount: int,
    deposit: int,
    now: datetime,
    op: str,
    card_id: int | None = None,
) -> None:
    with uow_factory.begin() as uow:
        uow.sessions.add(Session(id=f"s-{op}", flow="test", started_at=now))
        uow.ledger.append(
            LedgerEntry.new(
                account_id=account_id,
                entry_type=entry_type,
                amount=Money(amount),
                deposit_delta=Money(deposit),
                created_at=now,
                session_id=f"s-{op}",
                operation_id=op,
                card_id=card_id,
            )
        )
        uow.commit()


@pytest.fixture
def service(uow_factory: UnitOfWorkFactory, now: datetime) -> AdminPayoutService:
    return AdminPayoutService(uow_factory, FixedClock(now), deposit=DEPOSIT)


@pytest.fixture
def account_with_active_card(uow_factory: UnitOfWorkFactory, now: datetime) -> int:
    """Account with one active card: topup 2000 paid, Pfand 500 held."""
    with uow_factory.begin() as uow:
        account = uow.accounts.add(HASHER.hash_uid("8388B21A"), now)
        card = uow.cards.add(HASHER.hash_uid("8388B21A"), account.id, now)
        uow.sessions.add(Session(id="issue", flow="issue", started_at=now))
        uow.ledger.append(
            LedgerEntry.new(
                account_id=account.id,
                entry_type=EntryType.CASH_IN_TOPUP,
                amount=Money(2000),
                deposit_delta=Money(0),
                created_at=now,
                session_id="issue",
                operation_id="issue-topup",
                card_id=card.id,
            )
        )
        uow.ledger.append(
            LedgerEntry.new(
                account_id=account.id,
                entry_type=EntryType.CASH_IN_DEPOSIT,
                amount=Money(0),
                deposit_delta=DEPOSIT,
                created_at=now,
                session_id="issue",
                operation_id="issue-deposit",
                card_id=card.id,
            )
        )
        uow.commit()
    return account.id


def test_summary_shows_balance_deposit_and_open_cards(
    service: AdminPayoutService, account_with_active_card: int
) -> None:
    summary = service.summary(account_with_active_card)

    assert summary.balance_cents == 2000
    assert summary.deposit_cents == 500
    assert summary.active_cards == 1
    assert summary.recycled_cards == 0
    assert summary.cancelled_cards == 0
    assert summary.open_deposit_cents == 500
    assert summary.is_closed is False


def test_list_accounts_returns_all_accounts(
    service: AdminPayoutService, account_with_active_card: int
) -> None:
    accounts = service.list_accounts()

    assert [a.account_id for a in accounts] == [account_with_active_card]


def test_summary_of_unknown_account_raises(service: AdminPayoutService) -> None:
    with pytest.raises(NotFoundError):
        service.summary(999)


def test_payout_without_cash_handover_is_rejected(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
) -> None:
    confirmation = PayoutConfirmation(
        cash_handed_over=False, open_cards_acknowledged=True, final_confirmed=True
    )

    with pytest.raises(PayoutNotConfirmedError):
        service.payout(account_with_active_card, confirmation)

    assert service.summary(account_with_active_card).is_closed is False


def test_payout_without_final_confirmation_is_rejected(
    service: AdminPayoutService, account_with_active_card: int
) -> None:
    confirmation = PayoutConfirmation(
        cash_handed_over=True, open_cards_acknowledged=True, final_confirmed=False
    )

    with pytest.raises(PayoutNotConfirmedError):
        service.payout(account_with_active_card, confirmation)


def test_open_cards_require_acknowledged_warning(
    service: AdminPayoutService, account_with_active_card: int
) -> None:
    confirmation = PayoutConfirmation(
        cash_handed_over=True, open_cards_acknowledged=False, final_confirmed=True
    )

    with pytest.raises(PayoutNotConfirmedError):
        service.payout(account_with_active_card, confirmation)


def test_payout_zeroes_balance_cancels_open_cards_and_closes_account(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
    now: datetime,
) -> None:
    receipt = service.payout(account_with_active_card, CONFIRMED)

    assert receipt.paid_cents == 2000
    assert receipt.cancelled_cards == 1
    assert receipt.closed_at == now
    assert receipt.reference
    summary = service.summary(account_with_active_card)
    assert summary.balance_cents == 0
    assert summary.active_cards == 0
    assert summary.cancelled_cards == 1
    assert summary.is_closed is True
    with uow_factory.begin() as uow:
        entries = uow.ledger.list_for_account(account_with_active_card)
    payout = [e for e in entries if e.entry_type is EntryType.PAYOUT]
    assert [e.amount_cents for e in payout] == [-2000]
    assert [e.entry_type for e in entries].count(EntryType.CARD_CANCEL) == 1


def test_payout_keeps_open_pfand_as_not_refunded(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
) -> None:
    service.payout(account_with_active_card, CONFIRMED)

    with uow_factory.begin() as uow:
        card = uow.cards.list_for_account(account_with_active_card)[0]
    assert card.status is CardStatus.CANCELLED
    assert card.cancelled_at is not None
    # Pfand was already paid and is not refunded: no entry gives it back.
    with uow_factory.begin() as uow:
        assert uow.ledger.deposit_cents(account_with_active_card) == 500


def test_recycled_card_pfand_is_paid_out_as_balance(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
    now: datetime,
) -> None:
    with uow_factory.begin() as uow:
        card = uow.cards.list_for_account(account_with_active_card)[0]
        uow.cards.update(card.recycle(now))
        uow.commit()
    _book(
        uow_factory,
        account_id=account_with_active_card,
        entry_type=EntryType.RECYCLE_REFUND,
        amount=500,
        deposit=-500,
        now=now,
        op="recycle:1",
        card_id=card.id,
    )

    confirmation = PayoutConfirmation(
        cash_handed_over=True, open_cards_acknowledged=False, final_confirmed=True
    )
    receipt = service.payout(account_with_active_card, confirmation)

    assert receipt.paid_cents == 2500
    assert receipt.cancelled_cards == 0


def test_second_payout_of_closed_account_is_rejected(
    service: AdminPayoutService, account_with_active_card: int
) -> None:
    service.payout(account_with_active_card, CONFIRMED)

    with pytest.raises(AccountClosedError):
        service.payout(account_with_active_card, CONFIRMED)


def test_payout_writes_audit_without_uid(
    service: AdminPayoutService,
    db_path: Path,
    account_with_active_card: int,
) -> None:
    service.payout(account_with_active_card, CONFIRMED)

    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT action, outcome, detail FROM admin_audit ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    actions = [row["action"] for row in rows]
    assert actions == ["card_cancel", "payout", "account_close"]
    assert all("8388B21A" not in (row["detail"] or "") for row in rows)
    assert all(row["outcome"] == "completed" for row in rows)


def test_failed_payout_rolls_back_everything(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure after cards and ledger were written leaves nothing behind."""

    def failing_close(self: object, account_id: int, closed_at: datetime) -> None:
        raise RuntimeError("simulated failure during account close")

    monkeypatch.setattr(AccountRepository, "close", failing_close)
    with pytest.raises(RuntimeError):
        service.payout(account_with_active_card, CONFIRMED)
    monkeypatch.undo()

    summary = service.summary(account_with_active_card)
    assert summary.active_cards == 1
    assert summary.cancelled_cards == 0
    assert summary.balance_cents == 2000
    assert summary.is_closed is False
    with uow_factory.begin() as uow:
        assert [
            e.entry_type for e in uow.ledger.list_for_account(account_with_active_card)
        ] == [
            EntryType.CASH_IN_TOPUP,
            EntryType.CASH_IN_DEPOSIT,
        ]


def test_closed_account_rejects_new_ledger_bookings(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
    now: datetime,
) -> None:
    """A closed account is locked: a late Pfand refund must not be booked."""
    service.payout(account_with_active_card, CONFIRMED)

    with pytest.raises(AccountClosedError):
        _book(
            uow_factory,
            account_id=account_with_active_card,
            entry_type=EntryType.RECYCLE_REFUND,
            amount=500,
            deposit=-500,
            now=now,
            op="late-recycle",
        )


def test_closed_account_rejects_new_cards(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
    now: datetime,
) -> None:
    service.payout(account_with_active_card, CONFIRMED)

    with pytest.raises(AccountClosedError), uow_factory.begin() as uow:
        uow.cards.add(HASHER.hash_uid("AABBCCDD"), account_with_active_card, now)


def test_closed_at_is_set_immediately_and_retention_is_one_year(
    service: AdminPayoutService,
    uow_factory: UnitOfWorkFactory,
    account_with_active_card: int,
    now: datetime,
) -> None:
    service.payout(account_with_active_card, CONFIRMED)

    with uow_factory.begin() as uow:
        account = uow.accounts.get(account_with_active_card)
    assert account.is_closed is True
    assert account.closed_at == now
    assert account.retention_until() == datetime(
        2027, 1, 15, 10, 0, 0, tzinfo=now.tzinfo
    )


def test_retention_on_leap_day_moves_to_march_first() -> None:
    from kiosk.domain.entities import Account

    leap = datetime(2028, 2, 29, 12, 0, 0, tzinfo=UTC)
    account = Account(id=1, id_hash="x" * 64, created_at=leap, closed_at=leap)

    assert account.retention_until() == datetime(2029, 3, 1, 12, 0, 0, tzinfo=UTC)


def test_open_account_has_no_retention_date(now: datetime) -> None:
    from kiosk.domain.entities import Account

    account = Account(id=1, id_hash="x" * 64, created_at=now)

    assert account.is_closed is False
    assert account.retention_until() is None
