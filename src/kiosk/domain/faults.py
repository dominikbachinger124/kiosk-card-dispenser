"""Device fault entity.

A fault records that the kiosk stopped because of a hardware condition. It
stays open until an admin acknowledges it. Faults are never deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class FaultCode(StrEnum):
    """Fault categories. Values match the database CHECK constraint."""

    CARD_JAMMED = "CARD_JAMMED"
    CARD_OVERLAP = "CARD_OVERLAP"
    DISPENSER_EMPTY = "DISPENSER_EMPTY"
    DISPENSER_STATE = "DISPENSER_STATE"


@dataclass(frozen=True, slots=True)
class DeviceFault:
    """A stop condition of the device.

    Attributes:
        id: Primary key.
        code: Fault category.
        raised_at: Time the fault was recorded, UTC.
        session_id: Session in which the fault occurred, if any.
        acknowledged_at: Time of admin acknowledgement, UTC, or None while open.
        acknowledged_audit_id: Audit row that documents the acknowledgement.
    """

    id: int
    code: FaultCode
    raised_at: datetime
    session_id: str | None = None
    acknowledged_at: datetime | None = None
    acknowledged_audit_id: int | None = None

    @property
    def is_open(self) -> bool:
        """True until an admin has acknowledged the fault."""
        return self.acknowledged_at is None
