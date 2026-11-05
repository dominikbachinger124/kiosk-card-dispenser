"""FaultService over a real migrated database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from kiosk.domain.errors import AdminSessionExpiredError, NotFoundError
from kiosk.domain.faults import FaultCode
from kiosk.services.admin_auth import AdminSession
from kiosk.services.admin_session import AdminSessionGuard
from kiosk.services.faults import FaultService
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory

T0 = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
IDLE = timedelta(seconds=120)


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(T0)


@pytest.fixture
def service(uow_factory: UnitOfWorkFactory, clock: MutableClock) -> FaultService:
    return FaultService(uow_factory, clock, AdminSessionGuard(clock, IDLE))


def test_report_records_open_fault(service: FaultService) -> None:
    fault = service.report(FaultCode.CARD_JAMMED, session_id=None)

    assert fault.is_open
    assert service.open_fault() == fault


def test_second_report_returns_existing_fault_without_new_row(
    service: FaultService, db_path: Path
) -> None:
    first = service.report(FaultCode.CARD_JAMMED)
    second = service.report(FaultCode.DISPENSER_EMPTY)

    assert second == first
    assert second.code is FaultCode.CARD_JAMMED
    assert _count(db_path, "device_faults") == 1


def _count(db_path: Path, table_expr: str) -> int:
    row = _query_one(db_path, f"SELECT COUNT(*) AS n FROM {table_expr}", ())
    return int(row["n"])


def _query_one(db_path: Path, sql: str, params: tuple[object, ...]) -> sqlite3.Row:
    conn = connect(db_path)
    try:
        row = conn.execute(sql, params).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row


def test_no_fault_on_clean_device(service: FaultService) -> None:
    assert service.open_fault() is None


def test_acknowledge_requires_active_admin_session(
    service: FaultService, clock: MutableClock
) -> None:
    fault = service.report(FaultCode.CARD_JAMMED)
    guard = AdminSessionGuard(clock, IDLE)
    admin = guard.open(AdminSession(session_id="admin-1", opened_at=T0))

    clock.current = T0 + IDLE + timedelta(seconds=1)
    with pytest.raises(AdminSessionExpiredError):
        service.acknowledge(fault.id, admin)

    assert service.open_fault() is not None


def test_acknowledge_closes_fault_and_writes_audit(
    service: FaultService, clock: MutableClock, db_path: Path
) -> None:
    fault = service.report(FaultCode.CARD_JAMMED)
    guard = AdminSessionGuard(clock, IDLE)
    admin = guard.open(AdminSession(session_id="admin-1", opened_at=T0))

    acked = service.acknowledge(fault.id, admin)

    assert not acked.is_open
    assert acked.acknowledged_audit_id is not None
    assert service.open_fault() is None
    row = _query_one(
        db_path,
        "SELECT action, outcome FROM admin_audit WHERE id = ?",
        (acked.acknowledged_audit_id,),
    )
    assert row["action"] == "fault_ack"
    assert row["outcome"] == "completed"


def test_acknowledge_wrong_id_is_rejected_and_writes_nothing(
    service: FaultService, clock: MutableClock, db_path: Path
) -> None:
    fault = service.report(FaultCode.CARD_JAMMED)
    guard = AdminSessionGuard(clock, IDLE)
    admin = guard.open(AdminSession(session_id="admin-1", opened_at=T0))

    with pytest.raises(NotFoundError):
        service.acknowledge(fault.id + 99, admin)

    assert service.open_fault() is not None
    assert _count(db_path, "admin_audit WHERE action = 'fault_ack'") == 0


def test_acknowledge_twice_is_rejected(
    service: FaultService, clock: MutableClock
) -> None:
    fault = service.report(FaultCode.CARD_JAMMED)
    guard = AdminSessionGuard(clock, IDLE)
    admin = guard.open(AdminSession(session_id="admin-1", opened_at=T0))
    service.acknowledge(fault.id, admin)

    with pytest.raises(NotFoundError):
        service.acknowledge(fault.id, admin)


def test_new_fault_can_be_reported_after_acknowledgement(
    service: FaultService, clock: MutableClock
) -> None:
    fault = service.report(FaultCode.CARD_JAMMED)
    guard = AdminSessionGuard(clock, IDLE)
    admin = guard.open(AdminSession(session_id="admin-1", opened_at=T0))
    service.acknowledge(fault.id, admin)

    again = service.report(FaultCode.DISPENSER_EMPTY)

    assert again.is_open
    assert again.code is FaultCode.DISPENSER_EMPTY
