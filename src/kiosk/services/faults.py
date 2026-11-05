"""Device fault service: record stops, show them, and admin acknowledgement.

A device fault stops the kiosk until an admin has dealt with it at the
machine and confirmed it here. Reporting and reading a fault need no login,
because the device itself raises the fault and the touch screen must show
why it stopped. Only acknowledgement requires an active admin session.
"""

from __future__ import annotations

import logging

from kiosk.domain.clock import Clock
from kiosk.domain.errors import NotFoundError
from kiosk.domain.faults import DeviceFault, FaultCode
from kiosk.services.admin_session import ActiveAdminSession, AdminSessionGuard
from kiosk.storage.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.faults")

FLOW_NAME = "device_fault"
ACKNOWLEDGE_ACTION = "fault_ack"


class FaultService:
    """Record, read, and acknowledge device faults.

    Args:
        uow_factory: Transaction factory for all reads and writes.
        clock: Time source for fault and audit timestamps.
        session_guard: Checks and extends the admin session on acknowledgement.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        session_guard: AdminSessionGuard,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._guard = session_guard

    def report(
        self,
        code: FaultCode,
        session_id: str | None = None,
        *,
        account_id: int | None = None,
        card_id: int | None = None,
    ) -> DeviceFault:
        """Record a fault, or return the one that is already open.

        The kiosk has only one stop state. If a fault is already open, the
        existing record is returned and nothing new is written, so a repeated
        report cannot hide the first cause.

        Args:
            code: Fault category reported by the hardware layer.
            session_id: Technical session in which the fault occurred.
            account_id: Affected account, if known. Internal id only.
            card_id: Card that caused the stop, if identified. Only linked.
        """
        now = self._clock.now()
        with self._uow_factory.begin() as uow:
            existing = uow.faults.open_fault()
            if existing is not None:
                return existing
            fault = uow.faults.raise_fault(
                code,
                now,
                session_id=session_id,
                account_id=account_id,
                card_id=card_id,
            )
            uow.commit()

        logger.error(
            "device_fault_raised",
            extra={
                "session_id": session_id,
                "flow": FLOW_NAME,
                "error_code": code.value,
            },
        )
        return fault

    def open_fault(self) -> DeviceFault | None:
        """Return the open fault, or None if the device is clear."""
        with self._uow_factory.begin() as uow:
            return uow.faults.open_fault()

    def acknowledge(self, fault_id: int, admin: ActiveAdminSession) -> DeviceFault:
        """Acknowledge an open fault after the admin has cleared it at the device.

        The admin session is checked and extended first. The acknowledgement
        and its audit row are written in one transaction, so a fault is never
        acknowledged without a matching audit entry.

        Args:
            fault_id: Id of the open fault shown on the touch screen.
            admin: Active admin session from the admin login.

        Returns:
            The acknowledged fault, with its audit row id.

        Raises:
            AdminSessionExpiredError: If the admin session timed out.
            NotFoundError: If no open fault has this id.
        """
        now = self._clock.now()
        refreshed = self._guard.touch(admin)
        with self._uow_factory.begin() as uow:
            current = uow.faults.open_fault()
            if current is None or current.id != fault_id:
                raise NotFoundError(f"open device fault {fault_id} not found")
            audit_id = uow.audit.append(
                occurred_at=now,
                action=ACKNOWLEDGE_ACTION,
                outcome="completed",
                detail=f"fault_code={current.code.value}",
            )
            acked = uow.faults.acknowledge(fault_id, now, audit_id)
            uow.commit()

        logger.info(
            "device_fault_acknowledged",
            extra={
                "session_id": refreshed.session.session_id,
                "flow": FLOW_NAME,
                "error_code": acked.code.value,
            },
        )
        return acked


__all__ = ["ACKNOWLEDGE_ACTION", "FaultService"]
