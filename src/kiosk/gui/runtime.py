"""Runs the hardware polling in a QThread and connects it to the main window.

The thread runs the polling loop in its own ``run()``. That loop ends as soon
as ``stop()`` sets the flag, so ``stop()`` can join the thread without relying
on a Qt event loop inside the thread. The worker only emits signals. The bridge
lives in the GUI thread, and its slots are reached through queued connections,
so no widget is touched from the polling thread.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread

from kiosk.gui.main_window import MainWindowBridge
from kiosk.hardware.coordinator import HardwareCoordinator
from kiosk.hardware.polling import POLL_INTERVAL_S, PollingWorker

STOP_TIMEOUT_MS = 3000


class _PollingThread(QThread):
    """Thread that runs the polling loop until the worker is stopped."""

    def __init__(self, worker: PollingWorker) -> None:
        super().__init__()
        self._worker = worker

    def run(self) -> None:
        self._worker.run()


class PollingRuntime:
    """Owns the polling thread and its connection to the GUI bridge.

    Args:
        coordinator: Serializes device access with the customer flows.
        bridge: GUI-side bridge that receives card and error signals.
        interval_s: Pause between two polls.
    """

    def __init__(
        self,
        coordinator: HardwareCoordinator,
        bridge: MainWindowBridge,
        *,
        interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._worker = PollingWorker(coordinator, interval_s=interval_s)
        self._thread = _PollingThread(self._worker)
        self._worker.card_inserted.connect(
            bridge.onCardInserted, Qt.ConnectionType.QueuedConnection
        )
        self._worker.poll_failed.connect(
            bridge.onPollFailed, Qt.ConnectionType.QueuedConnection
        )

    def start(self) -> None:
        """Start polling in the background thread. Calling it twice is a no-op."""
        if not self._thread.isRunning():
            self._thread.start()

    def stop(self) -> bool:
        """Stop the worker and wait for the thread to finish.

        The thread is never terminated forcibly: a serial read may be in
        progress, and killing it could leave the device mid-movement.

        Returns:
            True if the thread ended within the timeout, False otherwise.
            Safe to call repeatedly and without a prior ``start()``.
        """
        if not self._thread.isRunning():
            return True
        self._worker.stop()
        return bool(self._thread.wait(STOP_TIMEOUT_MS))

    def is_running(self) -> bool:
        """True while the polling thread is alive."""
        return bool(self._thread.isRunning())
