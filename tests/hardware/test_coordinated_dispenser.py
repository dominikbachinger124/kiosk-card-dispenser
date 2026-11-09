"""CoordinatedDispenser: every device call goes through the coordinator lock."""

from __future__ import annotations

import threading

import pytest

from kiosk.domain.errors import BusyError, DispenserEmptyError
from kiosk.hardware.coordinated import CoordinatedDispenser
from kiosk.hardware.coordinator import HardwareCoordinator
from tests.hardware.fakes import FakeDispenser


def test_issue_and_read_are_forwarded_in_order() -> None:
    fake = FakeDispenser(uid="8388B21A", stock=3)
    dispenser = CoordinatedDispenser(fake, HardwareCoordinator(fake))

    dispenser.issue_card()
    dispenser.move_card_to_read_position()

    assert dispenser.read_uid() == "8388B21A"
    assert fake.calls == ["issue_card", "move_card_to_read_position", "read_uid"]


def test_device_errors_pass_through_unchanged() -> None:
    fake = FakeDispenser(stock=0)
    dispenser = CoordinatedDispenser(fake, HardwareCoordinator(fake))

    with pytest.raises(DispenserEmptyError):
        dispenser.issue_card()


def test_busy_lock_raises_busy_without_touching_device() -> None:
    fake = FakeDispenser()
    coordinator = HardwareCoordinator(fake, lock_timeout_s=0.05)
    dispenser = CoordinatedDispenser(fake, coordinator)

    holder_ready = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        def op(_: object) -> None:
            holder_ready.set()
            release.wait(timeout=2)

        coordinator.run(op)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    try:
        assert holder_ready.wait(timeout=2)
        with pytest.raises(BusyError):
            dispenser.issue_card()
        assert fake.calls == []
    finally:
        release.set()
        thread.join(timeout=2)
