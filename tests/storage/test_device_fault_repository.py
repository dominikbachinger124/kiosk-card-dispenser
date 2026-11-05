"""Device fault persistence: single open fault, acknowledgement, DB guards."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiosk.domain.errors import (
    DeviceFaultAlreadyOpenError,
    LedgerIntegrityError,
    NotFoundError,
)
from kiosk.domain.faults import FaultCode
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def test_raise_and_read_open_fault(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow:
        fault = uow.faults.raise_fault(FaultCode.CARD_JAMMED, NOW)
        uow.commit()

    with uow_factory.begin() as uow:
        loaded = uow.faults.open_fault()

    assert loaded == fault
    assert loaded is not None and loaded.is_open


def test_second_open_fault_is_rejected(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow:
        uow.faults.raise_fault(FaultCode.CARD_JAMMED, NOW)
        uow.commit()

    with pytest.raises(DeviceFaultAlreadyOpenError), uow_factory.begin() as uow:
        uow.faults.raise_fault(FaultCode.DISPENSER_EMPTY, NOW)
        uow.commit()


def test_no_open_fault_on_clean_device(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow:
        assert uow.faults.open_fault() is None


def test_acknowledge_closes_fault_and_allows_next(
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory.begin() as uow:
        fault = uow.faults.raise_fault(FaultCode.CARD_OVERLAP, NOW)
        audit_id = uow.audit.append(occurred_at=NOW, action="fault_ack", outcome="ok")
        acked = uow.faults.acknowledge(fault.id, NOW, audit_id)
        uow.commit()

    assert not acked.is_open
    assert acked.acknowledged_audit_id == audit_id

    with uow_factory.begin() as uow:
        assert uow.faults.open_fault() is None
        uow.faults.raise_fault(FaultCode.DISPENSER_EMPTY, NOW)
        uow.commit()


def test_acknowledge_twice_is_rejected(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow:
        fault = uow.faults.raise_fault(FaultCode.CARD_JAMMED, NOW)
        audit_id = uow.audit.append(occurred_at=NOW, action="fault_ack", outcome="ok")
        uow.faults.acknowledge(fault.id, NOW, audit_id)
        uow.commit()

    with pytest.raises(NotFoundError), uow_factory.begin() as uow:
        uow.faults.acknowledge(fault.id, NOW, audit_id)
        uow.commit()


def test_fault_rows_cannot_be_deleted_or_rewritten(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO device_faults (fault_code, raised_at) "
            "VALUES ('CARD_JAMMED', ?)",
            ("2026-11-05T10:00:00.000000Z",),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM device_faults")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE device_faults SET fault_code = 'DISPENSER_EMPTY'")
    finally:
        conn.close()


def test_fault_code_is_restricted_by_schema(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO device_faults (fault_code, raised_at) "
                "VALUES ('UNKNOWN', ?)",
                ("2026-11-05T10:00:00.000000Z",),
            )
    finally:
        conn.close()


def test_unknown_session_is_not_reported_as_open_fault(
    uow_factory: UnitOfWorkFactory,
) -> None:
    with pytest.raises(LedgerIntegrityError), uow_factory.begin() as uow:
        uow.faults.raise_fault(FaultCode.CARD_JAMMED, NOW, session_id="missing")
        uow.commit()


def test_acknowledgement_requires_fault_ack_audit_row(
    uow_factory: UnitOfWorkFactory,
) -> None:
    with uow_factory.begin() as uow:
        fault = uow.faults.raise_fault(FaultCode.CARD_JAMMED, NOW)
        other_id = uow.audit.append(occurred_at=NOW, action="admin_login", outcome="ok")
        uow.commit()

    with pytest.raises(sqlite3.IntegrityError), uow_factory.begin() as uow:
        uow.faults.acknowledge(fault.id, NOW, other_id)
        uow.commit()


def test_fault_links_account_and_card(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow:
        account = uow.accounts.add("a" * 64, NOW)
        card = uow.cards.add("b" * 64, account.id, NOW)
        fault = uow.faults.raise_fault(
            FaultCode.CARD_JAMMED, NOW, account_id=account.id, card_id=card.id
        )
        uow.commit()

    with uow_factory.begin() as uow:
        loaded = uow.faults.open_fault()

    assert loaded == fault
    assert loaded is not None
    assert (loaded.account_id, loaded.card_id) == (account.id, card.id)


def test_fault_without_known_card_has_no_link(uow_factory: UnitOfWorkFactory) -> None:
    with uow_factory.begin() as uow:
        fault = uow.faults.raise_fault(FaultCode.DISPENSER_EMPTY, NOW)
        uow.commit()

    assert fault.account_id is None
    assert fault.card_id is None


def test_card_link_cannot_be_changed_after_the_fact(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "INSERT INTO accounts (id_hash, created_at) VALUES (?, ?)",
            ("c" * 64, "2026-11-05T10:00:00.000000Z"),
        )
        conn.execute(
            "INSERT INTO cards (uid_hash, account_id, status, issued_at) "
            "VALUES (?, 1, 'active', ?)",
            ("d" * 64, "2026-11-05T10:00:00.000000Z"),
        )
        conn.execute(
            "INSERT INTO device_faults (fault_code, raised_at) "
            "VALUES ('CARD_JAMMED', ?)",
            ("2026-11-05T10:00:00.000000Z",),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE device_faults SET card_id = 1")
    finally:
        conn.close()
