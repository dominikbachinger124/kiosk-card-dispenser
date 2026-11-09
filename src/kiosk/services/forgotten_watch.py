"""Runs ForgottenCardService.watch in a background thread.

``watch()`` waits up to 30 seconds for the user to take the card. Run on the
polling thread, that wait would stop card detection. This wrapper starts it
on a thread of its own, so the polling and the GUI keep running.

``watch()`` cannot be interrupted safely: the card may be mid-movement. So
``stop()`` does not cancel the watch. It waits for it to finish, with a
timeout, and reports whether it ended.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Protocol

from kiosk.domain.errors import KioskError

logger = logging.getLogger("kiosk.services.forgotten_watch")

STOP_TIMEOUT_S = 35.0


class _Watchable(Protocol):
    def watch(self, card: Any) -> str: ...


class ForgottenWatch:
    """Starts one forgotten-card watch at a time in its own thread.

    Args:
        service: Object with ``watch(card)`` that returns an outcome string.
        stop_timeout_s: How long ``stop()`` waits for a running watch.
    """

    def __init__(
        self,
        service: _Watchable,
        *,
        stop_timeout_s: float = STOP_TIMEOUT_S,
    ) -> None:
        self._service = service
        self._stop_timeout_s = stop_timeout_s
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.last_outcome: str | None = None

    def start(self, card: Any) -> bool:
        """Start watching ``card``. Returns False if a watch is already running.

        A second card does not replace the first one: the running watch keeps
        the card it was started with.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            thread = threading.Thread(
                target=self._run,
                args=(card,),
                name="forgotten-watch",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return True

    def is_running(self) -> bool:
        """True while a watch thread is alive."""
        thread = self._thread
        return thread is not None and thread.is_alive()

    def stop(self) -> bool:
        """Wait for a running watch to finish.

        Returns:
            True if no watch is running afterwards, False if it outlasted the
            timeout. Safe to call repeatedly and without a prior ``start()``.
        """
        thread = self._thread
        if thread is None:
            return True
        thread.join(self._stop_timeout_s)
        return not thread.is_alive()

    def _run(self, card: Any) -> None:
        try:
            self.last_outcome = self._service.watch(card)
        except KioskError as exc:
            # Typed errors are expected stop conditions. Record the code only.
            logger.error(
                "forgotten_watch_failed",
                extra={"flow": "forgotten_card", "error_code": exc.code},
            )
            self.last_outcome = "failed"


__all__ = ["ForgottenWatch", "STOP_TIMEOUT_S"]
