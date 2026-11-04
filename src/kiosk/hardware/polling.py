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


class PollingWorker(QObject):
    """Polls the dispenser in a background thread and emits card events.

    Signals:
        card_inserted: Emitted once per new card at the user exit.
        poll_failed: Emitted with an error code when a poll fails. The worker
            keeps running and retries, so a short fault does not end polling.
    """

    card_inserted = Signal()
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
        if self._detector.update(state.user_exit_occupied):
            logger.info("card_inserted", extra={"flow": "read"})
            self.card_inserted.emit()
            return True
        return False


def _read_state(dispenser: CardDispenser) -> DispenserState:
    return dispenser.poll_state()


__all__ = ["CardInsertionDetector", "PollingWorker", "POLL_INTERVAL_S"]
