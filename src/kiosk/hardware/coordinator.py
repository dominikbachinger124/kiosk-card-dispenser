"""Serializes all access to the physical dispenser.

Polling and interactive commands share one serial link. Without a lock they
would interleave frames on the wire. The coordinator holds a single lock, so
only one operation talks to the device at a time.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

from kiosk.domain.errors import BusyError
from kiosk.hardware.interfaces import CardDispenser

T = TypeVar("T")


class HardwareCoordinator:
    """Run device operations one after another.

    Args:
        dispenser: The card dispenser to protect.
        lock_timeout_s: How long an operation waits for the device before
            failing with ``BUSY``. Interactive flows must not hang forever.
    """

    def __init__(
        self, dispenser: CardDispenser, *, lock_timeout_s: float = 5.0
    ) -> None:
        self._dispenser = dispenser
        self._lock = threading.Lock()
        self._lock_timeout_s = lock_timeout_s

    def run(self, operation: Callable[[CardDispenser], T]) -> T:
        """Execute one operation while holding the device lock.

        Raises:
            BusyError: If the device stays locked longer than ``lock_timeout_s``.
        """
        if not self._lock.acquire(timeout=self._lock_timeout_s):
            raise BusyError("hardware is busy")
        try:
            return operation(self._dispenser)
        finally:
            self._lock.release()


__all__ = ["HardwareCoordinator"]
