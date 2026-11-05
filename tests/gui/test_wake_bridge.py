"""Wake-up rules: sensor events, card reads, and touch, with no Qt."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from kiosk.gui.screensaver import ScreensaverController, WakeReason
from kiosk.gui.wake_bridge import WakeBridge
from kiosk.hardware.sensor_events import SensorEvent


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def setup(clock: MutableClock) -> tuple[ScreensaverController, WakeBridge]:
    controller = ScreensaverController(clock, inactivity_timeout=timedelta(seconds=60))
    return controller, WakeBridge(controller)


def _asleep(controller: ScreensaverController, clock: MutableClock, now: datetime):  # type: ignore[no-untyped-def]
    state = controller.start()
    clock.current = now + timedelta(seconds=120)
    return controller.tick(state)


def test_card_entering_user_exit_wakes_kiosk(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    asleep = _asleep(controller, clock, now)

    awake = bridge.on_sensor_event(asleep, SensorEvent.USER_EXIT_OCCUPIED.value)

    assert awake.asleep is False
    assert awake.last_wake_reason is WakeReason.CARD


def test_card_at_read_position_wakes_kiosk(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    asleep = _asleep(controller, clock, now)

    awake = bridge.on_sensor_event(asleep, SensorEvent.READ_POSITION_OCCUPIED.value)

    assert awake.asleep is False


def test_card_taken_does_not_wake_kiosk(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    asleep = _asleep(controller, clock, now)

    state = bridge.on_sensor_event(asleep, SensorEvent.USER_EXIT_FREED.value)

    assert state.asleep is True


def test_stack_refill_does_not_wake_kiosk(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    asleep = _asleep(controller, clock, now)

    state = bridge.on_sensor_event(asleep, SensorEvent.STACK_OCCUPIED.value)

    assert state.asleep is True


def test_card_read_at_id_reader_wakes_kiosk(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    asleep = _asleep(controller, clock, now)

    awake = bridge.on_card_read(asleep)

    assert awake.asleep is False
    assert awake.last_wake_reason is WakeReason.CARD


def test_touch_wakes_asleep_kiosk(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    asleep = _asleep(controller, clock, now)

    awake = bridge.on_touch(asleep)

    assert awake.asleep is False
    assert awake.last_wake_reason is WakeReason.TOUCH


def test_touch_while_awake_keeps_kiosk_awake(
    setup: tuple[ScreensaverController, WakeBridge],
    clock: MutableClock,
    now: datetime,
) -> None:
    controller, bridge = setup
    state = controller.start()
    clock.current = now + timedelta(seconds=50)

    state = bridge.on_touch(state)
    clock.current = now + timedelta(seconds=100)

    assert controller.tick(state).asleep is False
