"""Admin session inactivity timeout and expiry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from kiosk.domain.errors import AdminSessionExpiredError
from kiosk.services.admin_auth import AdminSession
from kiosk.services.admin_session import AdminSessionGuard


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def guard(clock: MutableClock) -> AdminSessionGuard:
    return AdminSessionGuard(clock, idle_timeout=timedelta(seconds=120))


def test_fresh_session_is_active(guard: AdminSessionGuard, now: datetime) -> None:
    active = guard.open(AdminSession(session_id="s1", opened_at=now))

    assert guard.is_active(active)
    guard.require_active(active)


def test_session_expires_after_idle_timeout(
    guard: AdminSessionGuard, clock: MutableClock, now: datetime
) -> None:
    active = guard.open(AdminSession(session_id="s1", opened_at=now))

    clock.current = now + timedelta(seconds=120)

    assert not guard.is_active(active)
    with pytest.raises(AdminSessionExpiredError):
        guard.require_active(active)


def test_activity_extends_the_session(
    guard: AdminSessionGuard, clock: MutableClock, now: datetime
) -> None:
    active = guard.open(AdminSession(session_id="s1", opened_at=now))
    clock.current = now + timedelta(seconds=100)
    active = guard.touch(active)

    clock.current = now + timedelta(seconds=200)

    assert guard.is_active(active)


def test_expired_session_cannot_be_revived_by_touch(
    guard: AdminSessionGuard, clock: MutableClock, now: datetime
) -> None:
    active = guard.open(AdminSession(session_id="s1", opened_at=now))
    clock.current = now + timedelta(seconds=500)

    with pytest.raises(AdminSessionExpiredError):
        guard.touch(active)


def test_non_positive_timeout_is_rejected(clock: MutableClock) -> None:
    with pytest.raises(ValueError):
        AdminSessionGuard(clock, idle_timeout=timedelta(0))
