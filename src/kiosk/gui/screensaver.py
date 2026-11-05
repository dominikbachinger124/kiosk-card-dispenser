"""Screensaver state: asleep or awake, driven by inactivity and wake events.

Touch, key input, and a card at the slot wake the kiosk. Inactivity sends it
back to sleep. The state is pure Python with an injected clock, so it can be
tested without Qt. Hardware polling is not affected by this state: the
screensaver never blocks a device operation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum

from kiosk.domain.clock import Clock

DEFAULT_INACTIVITY_TIMEOUT = timedelta(seconds=60)


class WakeReason(StrEnum):
    """What woke the kiosk. Used for logging only, never for business rules."""

    TOUCH = "touch"
    KEY = "key"
    CARD = "card"


@dataclass(frozen=True, slots=True)
class ScreensaverState:
    """Current screensaver state.

    Attributes:
        asleep: True while the screensaver is shown.
        last_activity_at: Time of the last wake or interaction, UTC.
        last_wake_reason: Why the kiosk last woke, or None before the first wake.
    """

    asleep: bool
    last_activity_at: datetime
    last_wake_reason: WakeReason | None = None


class ScreensaverController:
    """Tracks wake and sleep transitions.

    Args:
        clock: Time source.
        inactivity_timeout: Time without interaction before the screensaver starts.
    """

    def __init__(
        self,
        clock: Clock,
        inactivity_timeout: timedelta = DEFAULT_INACTIVITY_TIMEOUT,
    ) -> None:
        if inactivity_timeout <= timedelta(0):
            raise ValueError("inactivity_timeout must be positive")
        self._clock = clock
        self._timeout = inactivity_timeout

    def start(self) -> ScreensaverState:
        """Return the initial state: awake, with the current time as activity."""
        return ScreensaverState(asleep=False, last_activity_at=self._clock.now())

    def wake(self, state: ScreensaverState, reason: WakeReason) -> ScreensaverState:
        """Wake the kiosk because of touch, key input, or a card at the slot.

        Waking an awake kiosk only refreshes the activity time.
        """
        return replace(
            state,
            asleep=False,
            last_activity_at=self._clock.now(),
            last_wake_reason=reason,
        )

    def interact(self, state: ScreensaverState) -> ScreensaverState:
        """Record a user interaction while awake. Does nothing while asleep."""
        if state.asleep:
            return state
        return replace(state, last_activity_at=self._clock.now())

    def tick(self, state: ScreensaverState) -> ScreensaverState:
        """Return the state after checking inactivity. Call this periodically."""
        if state.asleep:
            return state
        if self._clock.now() - state.last_activity_at >= self._timeout:
            return replace(state, asleep=True)
        return state


__all__ = [
    "DEFAULT_INACTIVITY_TIMEOUT",
    "ScreensaverController",
    "ScreensaverState",
    "WakeReason",
]
