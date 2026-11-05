"""Admin panel session with an inactivity timeout.

The panel stays open only while the admin keeps interacting. After the
timeout the session is closed and every further action must log in again.
Timeout checks use the injected clock, so the behaviour is testable without Qt.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from kiosk.domain.clock import Clock
from kiosk.domain.errors import AdminSessionExpiredError
from kiosk.services.admin_auth import AdminSession

DEFAULT_IDLE_TIMEOUT = timedelta(seconds=120)


@dataclass(frozen=True, slots=True)
class ActiveAdminSession:
    """An admin session with its last activity time.

    Attributes:
        session: The authenticated session from ``AdminAuthService.login``.
        last_activity_at: Time of the last admin interaction, UTC.
    """

    session: AdminSession
    last_activity_at: datetime


class AdminSessionGuard:
    """Tracks the idle time of one admin session.

    Args:
        clock: Time source.
        idle_timeout: Inactivity after which the session expires.
    """

    def __init__(
        self, clock: Clock, idle_timeout: timedelta = DEFAULT_IDLE_TIMEOUT
    ) -> None:
        if idle_timeout <= timedelta(0):
            raise ValueError("idle_timeout must be positive")
        self._clock = clock
        self._idle_timeout = idle_timeout

    def open(self, session: AdminSession) -> ActiveAdminSession:
        """Start tracking a freshly authenticated session."""
        return ActiveAdminSession(session=session, last_activity_at=session.opened_at)

    def touch(self, active: ActiveAdminSession) -> ActiveAdminSession:
        """Record an admin interaction and extend the session.

        Raises:
            AdminSessionExpiredError: If the session already timed out. An
                expired session is never revived by activity.
        """
        self.require_active(active)
        return replace(active, last_activity_at=self._clock.now())

    def require_active(self, active: ActiveAdminSession) -> None:
        """Raise if the session has been idle for too long.

        Raises:
            AdminSessionExpiredError: If idle time reached the timeout.
        """
        if self._clock.now() - active.last_activity_at >= self._idle_timeout:
            raise AdminSessionExpiredError("admin session timed out")

    def is_active(self, active: ActiveAdminSession) -> bool:
        """Non-raising variant of ``require_active``."""
        return self._clock.now() - active.last_activity_at < self._idle_timeout


__all__ = ["DEFAULT_IDLE_TIMEOUT", "ActiveAdminSession", "AdminSessionGuard"]
