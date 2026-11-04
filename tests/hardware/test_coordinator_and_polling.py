"""Coordinator serialization and polling signal path (Qt, offscreen)."""

from __future__ import annotations

import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication

from kiosk.domain.errors import BusyError, HardwareTimeoutError
from kiosk.hardware.coordinator import HardwareCoordinator
from kiosk.hardware.interfaces import DispenserState
from kiosk.hardware.k720_frame import BIT_SENSOR_USER
from kiosk.hardware.polling import CardInsertionDetector, PollingWorker
from tests.hardware.fakes import FakeDispenser


@pytest.fixture(scope="module")
def qapp() -> QCoreApplication:
    app = QCoreApplication.instance()
    return app if isinstance(app, QCoreApplication) else QCoreApplication([])


# --- detector ------------------------------------------------------------------


def test_detector_fires_only_on_rising_edge() -> None:
    detector = CardInsertionDetector()

    readings = [False, True, True, True, False, True]

    assert [detector.update(r) for r in readings] == [
        False,
        True,
        False,
        False,
        False,
        True,
    ]


def test_detector_counts_first_occupied_reading_as_insertion() -> None:
    """Before any reading the sensor is treated as free, so the first hit is an edge."""
    detector = CardInsertionDetector()

    assert detector.update(True) is True
    assert detector.update(True) is False


# --- coordinator -----------------------------------------------------------------


def test_coordinator_runs_operations_and_returns_result() -> None:
    dispenser = FakeDispenser(uid="8388B21A")
    dispenser.issue_card()
    dispenser.move_card_to_read_position()
    coordinator = HardwareCoordinator(dispenser)

    assert coordinator.run(lambda d: d.read_uid()) == "8388B21A"


def test_coordinator_serializes_concurrent_operations() -> None:
    coordinator = HardwareCoordinator(FakeDispenser(), lock_timeout_s=2.0)
    inside = 0
    max_inside = 0
    guard = threading.Lock()

    def operation(_: object) -> None:
        nonlocal inside, max_inside
        with guard:
            inside += 1
            max_inside = max(max_inside, inside)
        time.sleep(0.01)
        with guard:
            inside -= 1

    threads = [
        threading.Thread(target=coordinator.run, args=(operation,)) for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_inside == 1


def test_coordinator_reports_busy_instead_of_hanging() -> None:
    coordinator = HardwareCoordinator(FakeDispenser(), lock_timeout_s=0.05)
    release = threading.Event()

    def blocker(_: object) -> None:
        release.wait(timeout=2.0)

    holder = threading.Thread(target=coordinator.run, args=(blocker,))
    holder.start()
    time.sleep(0.01)
    try:
        with pytest.raises(BusyError) as info:
            coordinator.run(lambda _: None)
        assert info.value.code == "BUSY"
    finally:
        release.set()
        holder.join()


def test_coordinator_releases_lock_after_error() -> None:
    coordinator = HardwareCoordinator(FakeDispenser(), lock_timeout_s=0.5)

    def failing(_: object) -> None:
        raise HardwareTimeoutError("boom")

    with pytest.raises(HardwareTimeoutError):
        coordinator.run(failing)

    assert coordinator.run(lambda _: "free") == "free"


# --- polling worker and signal ---------------------------------------------------


class _DispenserWithInsertion(FakeDispenser):
    """Fake whose user-exit sensor flips on at a chosen poll."""

    def __init__(self, insert_at: set[int]) -> None:
        super().__init__()
        self._insert_at = insert_at
        self._polls = 0

    def poll_state(self) -> DispenserState:
        self._polls += 1
        self._state.user_exit_occupied = self._polls in self._insert_at
        return self._state


def test_polling_worker_emits_card_inserted_on_insertion(
    qapp: QCoreApplication,
) -> None:
    dispenser = _DispenserWithInsertion(insert_at={2})
    worker = PollingWorker(HardwareCoordinator(dispenser), sleep=lambda _: None)
    received: list[bool] = []
    worker.card_inserted.connect(lambda: received.append(True))

    for _ in range(3):
        worker.poll_once()

    assert received == [True]


def test_polling_worker_reports_failures_and_keeps_running(
    qapp: QCoreApplication,
) -> None:
    dispenser = FakeDispenser(failures=[HardwareTimeoutError("no answer")])
    worker = PollingWorker(HardwareCoordinator(dispenser), sleep=lambda _: None)
    codes: list[str] = []
    worker.poll_failed.connect(codes.append)

    worker.poll_once()
    worker.poll_once()

    assert codes == ["HW_TIMEOUT"]


def test_polling_loop_stops_cleanly(qapp: QCoreApplication) -> None:
    dispenser = FakeDispenser()
    worker = PollingWorker(
        HardwareCoordinator(dispenser),
        interval_s=0.0,
        sleep=lambda _: None,
    )
    thread = threading.Thread(target=worker.run)
    thread.start()
    time.sleep(0.02)
    worker.stop()
    thread.join(timeout=2.0)

    assert not thread.is_alive()


def test_status_bit_constant_is_user_exit() -> None:
    assert BIT_SENSOR_USER == 0x0001
