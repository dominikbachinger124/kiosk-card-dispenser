"""IssueCardService over a fake dispenser and a real migrated database."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiosk.domain.errors import (
    CardJammedError,
    DispenserEmptyError,
    HardwareTimeoutError,
)
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.money import Money
from kiosk.services.admin_session import AdminSessionGuard
from kiosk.services.faults import FaultService
from kiosk.services.issue_card import IssueCardService, IssueOutcome
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT
from tests.hardware.fakes import FakeDispenser

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
TOPUP = Money(2000)
DEPOSIT = Money(500)
COLLECTION = Money(2500)
HASHER = CardIdHasher(TEST_SALT)
CUSTOMER_HASH = HASHER.hash_uid("AABBCCDD")
NEW_CARD_UID = "8388B21A"


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture
def dispenser() -> FakeDispenser:
    return FakeDispenser(uid=NEW_CARD_UID, stock=5)


@pytest.fixture
def service(
    dispenser: FakeDispenser, uow_factory: UnitOfWorkFactory
) -> IssueCardService:
    faults = FaultService(uow_factory, FixedClock(), AdminSessionGuard(FixedClock()))
    return IssueCardService(
        dispenser,
        uow_factory,
        HASHER,
        faults,
        FixedClock(),
        topup=TOPUP,
        deposit=DEPOSIT,
        collection=COLLECTION,
    )


def _count(db_path: Path, table: str) -> int:
    conn = connect(db_path)
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
    finally:
        conn.close()
    return int(row["n"])


def test_successful_issue_books_topup_and_deposit_after_read(
    service: IssueCardService, db_path: Path
) -> None:
    result = service.issue(customer_uid_hash=CUSTOMER_HASH)

    assert result.outcome is IssueOutcome.ISSUED
    assert result.card_id is not None
    assert _count(db_path, "cards") == 1
    assert _count(db_path, "ledger") == 2


def test_new_card_hash_is_the_read_uid_not_the_customer_hash(
    service: IssueCardService, db_path: Path
) -> None:
    service.issue(customer_uid_hash=CUSTOMER_HASH)

    conn = connect(db_path)
    try:
        row = conn.execute("SELECT uid_hash FROM cards").fetchone()
    finally:
        conn.close()
    assert row["uid_hash"] == HASHER.hash_uid(NEW_CARD_UID)


def test_empty_stock_records_fault_and_books_nothing(
    dispenser: FakeDispenser,
    service: IssueCardService,
    db_path: Path,
) -> None:
    dispenser.failures.append(DispenserEmptyError("stock empty"))

    result = service.issue(customer_uid_hash=CUSTOMER_HASH)

    assert result.outcome is IssueOutcome.EMPTY
    assert result.fault_id is not None
    assert _count(db_path, "device_faults") == 1
    assert _count(db_path, "ledger") == 0
    assert _count(db_path, "cards") == 0


def test_jam_during_handout_aborts_without_booking(
    dispenser: FakeDispenser,
    service: IssueCardService,
    db_path: Path,
) -> None:
    dispenser.failures.append(CardJammedError("jam"))

    result = service.issue(customer_uid_hash=CUSTOMER_HASH)

    assert result.outcome is IssueOutcome.ABORTED
    assert result.fault_id is not None
    assert _count(db_path, "device_faults") == 1
    assert _count(db_path, "ledger") == 0
    assert _count(db_path, "cards") == 0


def test_unreadable_card_after_handout_aborts_without_booking(
    dispenser: FakeDispenser,
    service: IssueCardService,
    db_path: Path,
) -> None:
    """Card left the exit, but the UID cannot be read: no booking at all."""
    # The first call (issue_card) succeeds; the read position move fails.
    dispenser.failures.append(HardwareTimeoutError("no card at read position"))

    result = service.issue(customer_uid_hash=CUSTOMER_HASH)

    assert result.outcome is IssueOutcome.ABORTED
    assert _count(db_path, "ledger") == 0
    assert _count(db_path, "cards") == 0


def test_additional_card_uses_existing_account_without_new_account(
    service: IssueCardService, uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    with uow_factory.begin() as uow:
        account = uow.accounts.add(CUSTOMER_HASH, NOW)
        uow.commit()

    result = service.issue(
        customer_uid_hash=CUSTOMER_HASH,
        existing_account_id=account.id,
    )

    assert result.outcome is IssueOutcome.ISSUED
    assert result.account_id == account.id
    assert _count(db_path, "accounts") == 1


def test_collection_must_equal_topup_plus_deposit(
    dispenser: FakeDispenser, uow_factory: UnitOfWorkFactory
) -> None:
    faults = FaultService(uow_factory, FixedClock(), AdminSessionGuard(FixedClock()))
    with pytest.raises(ValueError):
        IssueCardService(
            dispenser,
            uow_factory,
            HASHER,
            faults,
            FixedClock(),
            topup=TOPUP,
            deposit=DEPOSIT,
            collection=Money(2000),
        )
