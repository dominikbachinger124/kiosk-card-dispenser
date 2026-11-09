"""CustomerFlows: read the identifier, then run the issue or top-up service.

Uses the real services over a temporary database and test fakes for the
reader and dispenser. No device is opened.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiosk.domain.errors import HardwareTimeoutError, PortLostError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.money import Money
from kiosk.services.admin_session import AdminSessionGuard
from kiosk.services.customer_flows import CustomerFlows
from kiosk.services.faults import FaultService
from kiosk.services.issue_card import IssueCardService
from kiosk.services.topup import TopUpService
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT
from tests.hardware.fakes import FakeDispenser, FakeIdReader

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
TOPUP = Money(2000)
DEPOSIT = Money(500)
COLLECTION = Money(2500)
HASHER = CardIdHasher(TEST_SALT)
CUSTOMER_UID = "AABBCCDD"


class FixedClock:
    def now(self) -> datetime:
        return NOW


class _WatchSpy:
    """Records the cards handed to the forgotten-card watch."""

    def __init__(self) -> None:
        self.started: list[int] = []

    def start(self, card: object) -> bool:
        self.started.append(card.id)  # type: ignore[attr-defined]
        return True


def _flows(
    db: UnitOfWorkFactory,
    reader: FakeIdReader,
    dispenser: FakeDispenser,
    watch: _WatchSpy | None = None,
) -> CustomerFlows:
    faults = FaultService(db, FixedClock(), AdminSessionGuard(FixedClock()))
    issue = IssueCardService(
        dispenser,
        db,
        HASHER,
        faults,
        FixedClock(),
        topup=TOPUP,
        deposit=DEPOSIT,
        collection=COLLECTION,
    )
    topup = TopUpService(db, FixedClock(), topup=TOPUP)
    return CustomerFlows(
        reader=reader,
        issue=issue,
        topup=topup,
        hasher=HASHER,
        watch=watch,
        db=db,
    )


def _ledger_count(db_path: Path) -> int:
    conn = connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM ledger").fetchone()[0])
    finally:
        conn.close()


def _card_count(db_path: Path) -> int:
    conn = connect(db_path)
    try:
        return int(conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0])
    finally:
        conn.close()


def test_issue_reads_customer_id_then_books_card(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    reader = FakeIdReader(responses=[CUSTOMER_UID])
    dispenser = FakeDispenser(uid="8388B21A")
    flows = _flows(uow_factory, reader, dispenser)

    result = flows.start_issue()

    assert result == "issued"
    assert _card_count(db_path) == 1
    assert _ledger_count(db_path) == 2  # topup + deposit


def test_issued_card_is_handed_to_forgotten_watch(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    watch = _WatchSpy()
    flows = _flows(
        uow_factory,
        FakeIdReader(responses=[CUSTOMER_UID]),
        FakeDispenser(),
        watch,
    )

    assert flows.start_issue() == "issued"
    assert len(watch.started) == 1


def test_aborted_issue_starts_no_watch(uow_factory: UnitOfWorkFactory) -> None:
    watch = _WatchSpy()
    flows = _flows(
        uow_factory,
        FakeIdReader(responses=[HardwareTimeoutError("no card")]),
        FakeDispenser(),
        watch,
    )

    assert flows.start_issue() == "aborted"
    assert watch.started == []


def test_issue_without_customer_card_books_nothing(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    reader = FakeIdReader(responses=[HardwareTimeoutError("no card")])
    dispenser = FakeDispenser()
    flows = _flows(uow_factory, reader, dispenser)

    result = flows.start_issue()

    assert result == "aborted"
    assert dispenser.calls == []  # no card is dispensed without an identifier
    assert _card_count(db_path) == 0
    assert _ledger_count(db_path) == 0


def test_issue_port_loss_books_nothing_and_is_reported(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    reader = FakeIdReader(responses=[PortLostError("gone")])
    flows = _flows(uow_factory, reader, FakeDispenser())

    assert flows.start_issue() == "aborted"
    assert _ledger_count(db_path) == 0


def test_topup_for_known_account_books_topup(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    # Give the account a card first, so the top-up has a known account.
    first = _flows(uow_factory, FakeIdReader(responses=[CUSTOMER_UID]), FakeDispenser())
    assert first.start_issue() == "issued"
    before = _ledger_count(db_path)

    flows = _flows(uow_factory, FakeIdReader(responses=[CUSTOMER_UID]), FakeDispenser())
    assert flows.start_topup() == "topped_up"
    assert _ledger_count(db_path) == before + 1


def test_topup_unknown_account_books_nothing(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    flows = _flows(uow_factory, FakeIdReader(responses=[CUSTOMER_UID]), FakeDispenser())

    assert flows.start_topup() == "unknown_account"
    assert _ledger_count(db_path) == 0


def test_topup_without_customer_card_books_nothing(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    flows = _flows(
        uow_factory,
        FakeIdReader(responses=[HardwareTimeoutError("no card")]),
        FakeDispenser(),
    )

    assert flows.start_topup() == "aborted"
    assert _ledger_count(db_path) == 0


def test_no_raw_uid_in_logs(
    uow_factory: UnitOfWorkFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("DEBUG")
    flows = _flows(uow_factory, FakeIdReader(responses=[CUSTOMER_UID]), FakeDispenser())

    flows.start_issue()

    assert CUSTOMER_UID not in caplog.text
    assert HASHER.hash_uid(CUSTOMER_UID) not in caplog.text


def test_dispenser_jam_books_nothing(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    from kiosk.domain.errors import CardJammedError

    dispenser = FakeDispenser(failures=[CardJammedError("jam")])
    flows = _flows(uow_factory, FakeIdReader(responses=[CUSTOMER_UID]), dispenser)

    assert flows.start_issue() == "aborted"
    assert _ledger_count(db_path) == 0
    assert _card_count(db_path) == 0


def test_empty_stock_reports_empty_and_books_nothing(
    uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    flows = _flows(
        uow_factory,
        FakeIdReader(responses=[CUSTOMER_UID]),
        FakeDispenser(stock=0),
    )

    assert flows.start_issue() == "empty"
    assert _ledger_count(db_path) == 0
