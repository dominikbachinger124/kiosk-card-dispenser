"""ForgottenCardService over a fake dispenser and a real migrated database."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest

from kiosk.domain.entities import Card, CardStatus, Session
from kiosk.domain.errors import HardwareError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.services.forgotten_card import ForgottenCardOutcome, ForgottenCardService
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT

DEPOSIT = Money(500)
OTHER_UID = "DEADBEEF"
CARD_UID = "8388B21A"


@dataclass
class FakeState:
    user_exit_occupied: bool
    read_position_occupied: bool = False
    stack_occupied: bool = False


@dataclass
class FakeDispenser:
    """Scripted dispenser. ``user_exit`` says whether the card is still at U."""

    user_exit: bool = True
    read_uid_value: str = CARD_UID
    calls: list[str] = field(default_factory=list)
    fail_on: str | None = None

    def poll_state(self) -> FakeState:
        self.calls.append("poll")
        return FakeState(user_exit_occupied=self.user_exit)

    def move_card_to_read_position(self) -> None:
        self.calls.append("FC7")
        self.user_exit = False
        if self.fail_on == "FC7":
            raise HardwareError("fail")

    def read_uid(self) -> str:
        self.calls.append("READ")
        return self.read_uid_value

    def dispose_card(self) -> None:
        self.calls.append("CP")
        if self.fail_on == "CP":
            raise HardwareError("fail")


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class Sleeper:
    """Records sleeps; ``remove_on_sleep`` simulates the user taking the card."""

    def __init__(
        self, dispenser: FakeDispenser, *, remove_on_sleep: bool = False
    ) -> None:
        self._dispenser = dispenser
        self._remove = remove_on_sleep
        self.durations: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.durations.append(seconds)
        if self._remove:
            self._dispenser.user_exit = False


@pytest.fixture
def hasher() -> CardIdHasher:
    return CardIdHasher(TEST_SALT)


@pytest.fixture
def issued_card(
    uow_factory: UnitOfWorkFactory, hasher: CardIdHasher, now: datetime
) -> Card:
    """One account with one active card, as after a normal issue."""
    with uow_factory.begin() as uow:
        account = uow.accounts.add(hasher.hash_uid(CARD_UID), now)
        card = uow.cards.add(hasher.hash_uid(CARD_UID), account.id, now)
        uow.sessions.add(Session(id="issue-1", flow="issue", started_at=now))
        # Issue books the spendable 2000 (topup) and the Fund 500 separately.
        uow.ledger.append(
            LedgerEntry.new(
                account_id=account.id,
                entry_type=EntryType.CASH_IN_TOPUP,
                amount=Money(2000),
                deposit_delta=Money(0),
                created_at=now,
                session_id="issue-1",
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
                session_id="issue-1",
                operation_id="issue-deposit",
                card_id=card.id,
            )
        )
        uow.commit()
    return card


def _service(
    dispenser: FakeDispenser,
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    sleeper: Sleeper,
) -> ForgottenCardService:
    return ForgottenCardService(
        dispenser,
        uow_factory,
        hasher,
        FixedClock(now),
        deposit=DEPOSIT,
        sleep=sleeper,
    )


def _account_state(uow_factory: UnitOfWorkFactory, account_id: int) -> tuple[int, int]:
    with uow_factory.begin() as uow:
        return uow.ledger.balance_cents(account_id), uow.ledger.deposit_cents(
            account_id
        )


def test_card_taken_within_wait_is_not_recycled(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=False)
    sleeper = Sleeper(dispenser)
    service = _service(dispenser, uow_factory, hasher, now, sleeper)

    outcome = service.watch(issued_card)

    assert outcome is ForgottenCardOutcome.TAKEN_BY_USER
    assert sleeper.durations == [1.0]
    assert "CP" not in dispenser.calls


def test_user_takes_card_during_wait_is_not_recycled(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True)
    sleeper = Sleeper(dispenser, remove_on_sleep=True)
    service = _service(dispenser, uow_factory, hasher, now, sleeper)

    outcome = service.watch(issued_card)

    assert outcome is ForgottenCardOutcome.TAKEN_BY_USER
    assert "CP" not in dispenser.calls


def test_forgotten_card_is_read_disposed_and_refunded(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True)
    service = _service(dispenser, uow_factory, hasher, now, Sleeper(dispenser))

    outcome = service.watch(issued_card)

    assert outcome is ForgottenCardOutcome.RECYCLED
    assert dispenser.calls[-3:] == ["FC7", "READ", "CP"]
    with uow_factory.begin() as uow:
        card = uow.cards.get(issued_card.id)
        assert card.status is CardStatus.RECYCLED
        assert card.recycled_at == now
        entries = uow.ledger.list_for_account(issued_card.account_id)
    refunds = [e for e in entries if e.entry_type is EntryType.RECYCLE_REFUND]
    assert len(refunds) == 1
    assert refunds[0].amount_cents == 500
    assert refunds[0].deposit_delta_cents == -500


def test_refund_moves_balance_and_deposit_as_specified(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True)
    service = _service(dispenser, uow_factory, hasher, now, Sleeper(dispenser))

    service.watch(issued_card)

    balance, deposit = _account_state(uow_factory, issued_card.account_id)
    # Issue: topup 2000 spendable, Fund 500 held apart. Recycling moves the
    # Fund of this card into the spendable balance as recycle_refund.
    assert deposit == 0  # Fund released
    assert balance == 2500


def test_wrong_card_at_read_position_is_not_disposed(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True, read_uid_value=OTHER_UID)
    service = _service(dispenser, uow_factory, hasher, now, Sleeper(dispenser))

    outcome = service.watch(issued_card)

    assert outcome is ForgottenCardOutcome.WRONG_CARD
    assert "CP" not in dispenser.calls
    with uow_factory.begin() as uow:
        assert uow.cards.get(issued_card.id).status is CardStatus.ACTIVE
        assert uow.ledger.deposit_cents(issued_card.account_id) == 500


def test_hardware_error_during_dispose_books_nothing(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True, fail_on="CP")
    service = _service(dispenser, uow_factory, hasher, now, Sleeper(dispenser))

    with pytest.raises(HardwareError):
        service.watch(issued_card)

    with uow_factory.begin() as uow:
        assert uow.cards.get(issued_card.id).status is CardStatus.ACTIVE
        assert uow.ledger.deposit_cents(issued_card.account_id) == 500


def test_second_recycling_of_same_card_does_not_refund_twice(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    first = FakeDispenser(user_exit=True)
    service = _service(first, uow_factory, hasher, now, Sleeper(first))
    assert service.watch(issued_card) is ForgottenCardOutcome.RECYCLED

    second = FakeDispenser(user_exit=True)
    service2 = _service(second, uow_factory, hasher, now, Sleeper(second))
    # The card is no longer active: the second attempt must neither dispose
    # nor book a second refund.
    assert service2.watch(issued_card) is ForgottenCardOutcome.NOT_RECYCLABLE
    assert "CP" not in second.calls

    balance, deposit = _account_state(uow_factory, issued_card.account_id)
    assert deposit == 0
    assert balance == 2500  # topup 2000 + one refund 500, not two refunds


def test_wait_must_be_positive(
    uow_factory: UnitOfWorkFactory, hasher: CardIdHasher, now: datetime
) -> None:
    dispenser = FakeDispenser()
    with pytest.raises(ValueError, match="wait_s must be positive"):
        ForgottenCardService(
            dispenser,
            uow_factory,
            hasher,
            FixedClock(now),
            deposit=DEPOSIT,
            sleep=lambda _s: None,
            wait_s=0.0,
        )


def test_taken_early_ends_watch_without_full_wait(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    """A card taken after the first check ends the watch; no further waiting."""
    dispenser = FakeDispenser(user_exit=True)
    sleeper = Sleeper(dispenser, remove_on_sleep=True)
    service = _service(dispenser, uow_factory, hasher, now, sleeper)

    outcome = service.watch(issued_card)

    assert outcome is ForgottenCardOutcome.TAKEN_BY_USER
    assert sleeper.durations == [1.0]
    assert "CP" not in dispenser.calls


def test_card_left_for_full_wait_is_recycled(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    """Left at the exit for all 45 s: polled each second, then recycled."""
    dispenser = FakeDispenser(user_exit=True)
    sleeper = Sleeper(dispenser)
    service = _service(dispenser, uow_factory, hasher, now, sleeper)

    outcome = service.watch(issued_card)

    assert outcome is ForgottenCardOutcome.RECYCLED
    assert len(sleeper.durations) == 45
    assert sum(sleeper.durations) == 45.0


class _FaultSpy:
    """Records fault reports; stands in for FaultService."""

    def __init__(self) -> None:
        self.reports: list[object] = []

    def report(
        self,
        code: object,
        session_id: str | None = None,
        *,
        account_id: int | None = None,
        card_id: int | None = None,
    ) -> object:
        self.reports.append((code, card_id))
        return object()


def _clear_service(
    dispenser: FakeDispenser,
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    faults: _FaultSpy | None,
) -> ForgottenCardService:
    return ForgottenCardService(
        dispenser,
        uow_factory,
        hasher,
        FixedClock(now),
        deposit=DEPOSIT,
        sleep=lambda _s: None,
        faults=faults,
    )


def test_clear_exit_recycles_when_uid_matches(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True)
    faults = _FaultSpy()
    service = _clear_service(dispenser, uow_factory, hasher, now, faults)

    outcome = service.clear_exit_before_issue(issued_card)

    assert outcome is ForgottenCardOutcome.RECYCLED
    assert dispenser.calls[-3:] == ["FC7", "READ", "CP"]
    assert faults.reports == []


def test_clear_exit_with_other_card_disposes_nothing_and_reports_fault(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    dispenser = FakeDispenser(user_exit=True, read_uid_value=OTHER_UID)
    faults = _FaultSpy()
    service = _clear_service(dispenser, uow_factory, hasher, now, faults)

    outcome = service.clear_exit_before_issue(issued_card)

    assert outcome is ForgottenCardOutcome.WRONG_CARD
    assert "CP" not in dispenser.calls
    assert len(faults.reports) == 1
    code, card_id = faults.reports[0]  # type: ignore[misc]
    assert str(code) == "CARD_UID_AMBIGUOUS"
    assert card_id == issued_card.id


def test_cancel_during_wait_recycles_now_after_uid_check(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    """A touch during the wait disposes of the watched card at once."""
    import threading

    dispenser = FakeDispenser(user_exit=True)
    cancel = threading.Event()
    sleeper = Sleeper(dispenser)

    def sleep_then_touch(seconds: float) -> None:
        sleeper(seconds)
        cancel.set()

    service = ForgottenCardService(
        dispenser,
        uow_factory,
        hasher,
        FixedClock(now),
        deposit=DEPOSIT,
        sleep=sleep_then_touch,
    )

    outcome = service.watch(issued_card, cancel)

    assert outcome is ForgottenCardOutcome.RECYCLED
    assert sleeper.durations == [1.0]
    assert dispenser.calls[-3:] == ["FC7", "READ", "CP"]


def test_cancel_with_other_card_disposes_nothing(
    uow_factory: UnitOfWorkFactory,
    hasher: CardIdHasher,
    now: datetime,
    issued_card: Card,
) -> None:
    """A touch never disposes of a card whose UID does not match."""
    import threading

    dispenser = FakeDispenser(user_exit=True, read_uid_value=OTHER_UID)
    cancel = threading.Event()
    cancel.set()
    service = ForgottenCardService(
        dispenser,
        uow_factory,
        hasher,
        FixedClock(now),
        deposit=DEPOSIT,
        sleep=lambda _s: None,
    )

    outcome = service.watch(issued_card, cancel)

    assert outcome is ForgottenCardOutcome.WRONG_CARD
    assert "CP" not in dispenser.calls
