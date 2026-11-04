"""Time source abstraction so that time-dependent rules stay testable."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Provides the current time as timezone-aware UTC."""

    def now(self) -> datetime:
        """Return the current time in UTC."""
        ...


class SystemClock:
    """Clock backed by the operating system time, always in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)
