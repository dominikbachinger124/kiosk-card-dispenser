"""Background polling of the dispenser state.

``CardInsertionDetector`` holds the pure decision logic and has no Qt
dependency, so it is fully testable. ``PollingWorker`` wraps it in a QThread
and emits ``card_inserted`` to the GUI thread. The worker never touches
widgets.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal, Slot

from kiosk.domain.errors import HardwareError
from kiosk.hardware.coordinator import HardwareCoordinator
from kiosk.hardware.interfaces import CardDispenser, DispenserState
from kiosk.hardware.sensor_events import SensorEdgeDetector, SensorReading

logger = logging.getLogger("kiosk.hardware.polling")

POLL_INTERVAL_S = 0.5


class CardInsertionDetector:
    """Detects a card newly placed at the user exit.

    A card insertion is a rising edge of the user-exit sensor: the sensor was
    free on the previous poll and is occupied now. Repeated readings of an
    occupied sensor do not fire again.
    """

    def __init__(self) -> None:
        self._previously_occupied = False

    def update(self, occupied: bool) -> bool:
        """Feed one reading and return True exactly on the rising edge."""
        rising = occupied and not self._previously_occupied
        self._previously_occupied = occupied
        return rising


class CardRemovalDetector:
    """Detects that the card at the user exit has been taken.

    A removal is a falling edge of the user-exit sensor: occupied on the
    previous poll, free now. The customer takes the card, so this closes the
    "card at the exit" status.
    """

    def __init__(self) -> None:
        self._previously_occupied = False

    def update(self, occupied: bool) -> bool:
        """Feed one reading and return True exactly on the falling edge."""
        falling = not occupied and self._previously_occupied
        self._previously_occupied = occupied
        return falling


class PollingWorker(QObject):
    """Polls the dispenser in a background thread and emits card events.

    Signals:
        card_inserted: Emitted once per new card at the user exit.
        sensor_event: Emitted with the event name for every sensor transition
            (see ``SensorEvent``), so the GUI can wake the screensaver.
        poll_failed: Emitted with an error code when a poll fails. The worker
            keeps running and retries, so a short fault does not end polling.
    """

    card_inserted = Signal()
    card_removed = Signal()
    sensor_event = Signal(str)
    poll_failed = Signal(str)

    def __init__(
        self,
        coordinator: HardwareCoordinator,
        *,
        interval_s: float = POLL_INTERVAL_S,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._interval_s = interval_s
        self._sleep = sleep
        self._stop = threading.Event()
        self._detector = CardInsertionDetector()
        self._remover = CardRemovalDetector()
        self._edges = SensorEdgeDetector()

    @Slot()
    def run(self) -> None:
        """Poll until ``stop()`` is called. Intended as the thread target."""
        while not self._stop.is_set():
            self._poll_once()
            self._sleep(self._interval_s)

    def stop(self) -> None:
        """Request a clean shutdown. The loop ends after the current poll."""
        self._stop.set()

    def poll_once(self) -> bool:
        """Run one poll and return True if a card was inserted. Used in tests."""
        return self._poll_once()

    def _poll_once(self) -> bool:
        try:
            state = self._coordinator.run(_read_state)
        except HardwareError as exc:
            logger.warning("poll_failed", extra={"error_code": exc.code})
            self.poll_failed.emit(exc.code)
            return False
        reading = SensorReading(
            user_exit=state.user_exit_occupied,
            read_position=state.read_position_occupied,
            stack=state.stack_occupied,
        )
        for event in self._edges.update(reading):
            # Only the event name leaves the worker. No device bytes, no card data.
            self.sensor_event.emit(event.value)
        inserted = self._detector.update(state.user_exit_occupied)
        if inserted:
            logger.info("card_inserted", extra={"flow": "read"})
            self.card_inserted.emit()
        if self._remover.update(state.user_exit_occupied):
            logger.info("card_removed", extra={"flow": "read"})
            self.card_removed.emit()
        return inserted


def _read_state(dispenser: CardDispenser) -> DispenserState:
    return dispenser.poll_state()


__all__ = [
    "CardInsertionDetector",
    "CardRemovalDetector",
    "PollingWorker",
    "POLL_INTERVAL_S",
]
