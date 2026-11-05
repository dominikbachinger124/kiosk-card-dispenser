"""Screensaver wake and sleep rules, with an injected clock. No Qt needed."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from kiosk.gui.screensaver import ScreensaverController, WakeReason


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def controller(clock: MutableClock) -> ScreensaverController:
    return ScreensaverController(clock, inactivity_timeout=timedelta(seconds=60))


def test_kiosk_starts_awake(controller: ScreensaverController) -> None:
    assert controller.start().asleep is False


def test_inactivity_starts_screensaver(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()

    clock.current = now + timedelta(seconds=60)

    assert controller.tick(state).asleep is True


def test_no_screensaver_before_timeout(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()

    clock.current = now + timedelta(seconds=59)

    assert controller.tick(state).asleep is False


def test_touch_wakes_the_kiosk(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()
    clock.current = now + timedelta(seconds=120)
    asleep = controller.tick(state)
    assert asleep.asleep is True

    awake = controller.wake(asleep, WakeReason.TOUCH)

    assert awake.asleep is False
    assert awake.last_wake_reason is WakeReason.TOUCH


def test_card_at_the_slot_wakes_the_kiosk(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.tick(controller.start())
    clock.current = now + timedelta(seconds=120)
    asleep = controller.tick(state)

    awake = controller.wake(asleep, WakeReason.CARD)

    assert awake.asleep is False
    assert awake.last_wake_reason is WakeReason.CARD


def test_wake_resets_inactivity_clock(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()
    clock.current = now + timedelta(seconds=120)
    state = controller.wake(controller.tick(state), WakeReason.TOUCH)

    clock.current = now + timedelta(seconds=150)

    assert controller.tick(state).asleep is False


def test_interaction_keeps_kiosk_awake(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()
    clock.current = now + timedelta(seconds=50)
    state = controller.interact(state)

    clock.current = now + timedelta(seconds=100)

    assert controller.tick(state).asleep is False


def test_interaction_while_asleep_does_not_wake(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()
    clock.current = now + timedelta(seconds=120)
    asleep = controller.tick(state)

    assert controller.interact(asleep).asleep is True


def test_waking_an_awake_kiosk_only_refreshes_activity(
    controller: ScreensaverController, clock: MutableClock, now: datetime
) -> None:
    state = controller.start()
    clock.current = now + timedelta(seconds=30)

    state = controller.wake(state, WakeReason.TOUCH)

    assert state.asleep is False
    assert state.last_activity_at == now + timedelta(seconds=30)


def test_non_positive_timeout_is_rejected(clock: MutableClock) -> None:
    with pytest.raises(ValueError):
        ScreensaverController(clock, inactivity_timeout=timedelta(0))
