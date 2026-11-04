"""Unit-of-work semantics, account privacy, and card persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from kiosk.domain.entities import CardStatus
from kiosk.domain.errors import NotFoundError
from kiosk.domain.identity import CardIdHasher
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT


def _row_count(db_path: Path, table: str) -> int:
    conn = connect(db_path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def test_uncommitted_work_is_rolled_back(
    uow_factory: UnitOfWorkFactory, db_path: Path, now: datetime
) -> None:
    with uow_factory.begin() as uow:
        uow.accounts.add("d" * 64, now)
        # no commit: leaving the block must roll back

    assert _row_count(db_path, "accounts") == 0


def test_exception_rolls_back_all_changes(
    uow_factory: UnitOfWorkFactory, db_path: Path, now: datetime
) -> None:
    with pytest.raises(RuntimeError), uow_factory.begin() as uow:
        uow.accounts.add("e" * 64, now)
        raise RuntimeError("boom")

    assert _row_count(db_path, "accounts") == 0


def test_committed_work_persists(
    uow_factory: UnitOfWorkFactory, db_path: Path, now: datetime
) -> None:
    with uow_factory.begin() as uow:
        uow.accounts.add("f" * 64, now)
        uow.commit()

    assert _row_count(db_path, "accounts") == 1


def test_account_is_found_by_hash_and_closed_is_none(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    with uow_factory.begin() as uow:
        account = uow.accounts.add("a" * 64, now)
        uow.commit()

    with uow_factory.begin() as uow:
        found = uow.accounts.find_by_hash("a" * 64)

    assert found == account
    assert found is not None and found.closed_at is None


def test_unknown_account_raises_not_found(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow, pytest.raises(NotFoundError):
        uow.accounts.get(999)


def test_card_status_change_is_persisted(
    uow_factory: UnitOfWorkFactory, now: datetime
) -> None:
    from kiosk.domain.entities import Session

    with uow_factory.begin() as uow:
        uow.sessions.add(Session(id="s1", flow="issue", started_at=now))
        account = uow.accounts.add("a" * 64, now)
        card = uow.cards.add("b" * 64, account.id, now)
        uow.commit()

    with uow_factory.begin() as uow:
        uow.cards.update(card.recycle(now))
        uow.commit()

    with uow_factory.begin() as uow:
        stored = uow.cards.get(card.id)

    assert stored.status is CardStatus.RECYCLED
    assert stored.recycled_at == now


def test_only_salted_hash_is_persisted(
    uow_factory: UnitOfWorkFactory, db_path: Path, now: datetime
) -> None:
    raw_uid = "8388B21A"
    id_hash = CardIdHasher(TEST_SALT).hash_uid(raw_uid)
    with uow_factory.begin() as uow:
        uow.accounts.add(id_hash, now)
        uow.commit()

    conn = connect(db_path)
    try:
        dump = " ".join(
            str(value)
            for row in conn.execute("SELECT * FROM accounts")
            for value in tuple(row)
        )
    finally:
        conn.close()

    assert id_hash in dump
    assert raw_uid not in dump
    assert TEST_SALT.decode() not in dump


def test_audit_table_is_append_only(
    uow_factory: UnitOfWorkFactory, db_path: Path, now: datetime
) -> None:
    with uow_factory.begin() as uow:
        uow.audit.append(occurred_at=now, action="admin_login", outcome="ok")
        uow.commit()

    conn = connect(db_path)
    try:
        with pytest.raises(Exception, match="append-only"):
            conn.execute("DELETE FROM admin_audit")
    finally:
        conn.close()
