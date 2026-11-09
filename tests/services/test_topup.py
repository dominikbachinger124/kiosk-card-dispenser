"""TopUpService: fixed 20 EUR credit to an existing account, no hardware."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiosk.domain.errors import AccountClosedError, NotFoundError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.ledger import EntryType
from kiosk.domain.money import Money
from kiosk.services.topup import TopUpOutcome, TopUpService
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
TOPUP = Money(2000)
HASHER = CardIdHasher(TEST_SALT)
CUSTOMER_HASH = HASHER.hash_uid("AABBCCDD")
OTHER_HASH = HASHER.hash_uid("11223344")


class FixedClock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture
def service(uow_factory: UnitOfWorkFactory) -> TopUpService:
    return TopUpService(uow_factory, FixedClock(), topup=TOPUP)


def _add_account(uow_factory: UnitOfWorkFactory, id_hash: str) -> int:
    with uow_factory.begin() as uow:
        account = uow.accounts.add(id_hash, NOW)
        uow.commit()
    return account.id


def _ledger_rows(db_path: Path) -> list[dict[str, object]]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT account_id, entry_type, amount_cents, deposit_delta_cents "
            "FROM ledger ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def test_topup_credits_exactly_2000_cent_as_cash_in_topup(
    service: TopUpService, uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    account_id = _add_account(uow_factory, CUSTOMER_HASH)

    result = service.top_up(customer_uid_hash=CUSTOMER_HASH)

    assert result.outcome is TopUpOutcome.TOPPED_UP
    assert result.account_id == account_id
    rows = _ledger_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["entry_type"] == EntryType.CASH_IN_TOPUP.value
    assert rows[0]["amount_cents"] == 2000
    assert rows[0]["deposit_delta_cents"] == 0


def test_topup_does_not_touch_deposit_or_create_card(
    service: TopUpService, uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    _add_account(uow_factory, CUSTOMER_HASH)

    service.top_up(customer_uid_hash=CUSTOMER_HASH)

    conn = connect(db_path)
    try:
        cards = conn.execute("SELECT COUNT(*) AS n FROM cards").fetchone()["n"]
    finally:
        conn.close()
    assert cards == 0


def test_unknown_account_aborts_without_booking(
    service: TopUpService, db_path: Path
) -> None:
    with pytest.raises(NotFoundError):
        service.top_up(customer_uid_hash=OTHER_HASH)

    assert _ledger_rows(db_path) == []


def test_closed_account_is_rejected_without_booking(
    service: TopUpService, uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    account_id = _add_account(uow_factory, CUSTOMER_HASH)
    with uow_factory.begin() as uow:
        uow.accounts.close(account_id, NOW)
        uow.commit()

    with pytest.raises(AccountClosedError):
        service.top_up(customer_uid_hash=CUSTOMER_HASH)

    assert _ledger_rows(db_path) == []


def test_each_call_books_one_more_topup(
    service: TopUpService, uow_factory: UnitOfWorkFactory, db_path: Path
) -> None:
    _add_account(uow_factory, CUSTOMER_HASH)

    service.top_up(customer_uid_hash=CUSTOMER_HASH)
    service.top_up(customer_uid_hash=CUSTOMER_HASH)

    rows = _ledger_rows(db_path)
    assert [row["amount_cents"] for row in rows] == [2000, 2000]
