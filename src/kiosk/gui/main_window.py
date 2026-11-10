"""QObject bridge between the main QML window and the kiosk flows.

The bridge holds no business rules. It forwards the customer actions to the
flow objects and exposes whether the admin panel is available. Admin is only
offered when an admin service exists, so an incomplete configuration keeps
the admin locked instead of showing a broken login.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from kiosk.i18n.texts import translate


class MainWindowBridge(QObject):
    """QML-facing object for the main window.

    Args:
        customer: Object with ``start_issue()`` and ``start_topup()``.
            Each returns a short result key that the screen translates.
        admin: Admin object, or None when admin is not configured.
        language: UI language code.
    """

    adminAvailableChanged = Signal()
    statusChanged = Signal()
    _flowFinished = Signal(str)
    _flowProgress = Signal(str)

    def __init__(
        self,
        customer: Any,
        admin: Any | None,
        language: str = "de",
    ) -> None:
        super().__init__()
        self._customer = customer
        self._admin = admin
        self._language = language
        self._status = ""
        # Flows block on the reader, so they run in a worker thread. The result
        # comes back to the GUI thread through this signal only.
        self._flowFinished.connect(self._set_flow_result)
        self._flowProgress.connect(self._set_flow_result)

    @Property(bool, notify=adminAvailableChanged)
    def adminAvailable(self) -> bool:
        return self._admin is not None

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Slot(str, result=str)
    def text(self, key: str) -> str:
        """Return a localized UI text. QML never hard-codes German or English."""
        return translate(key, self._language)

    @Slot()
    def onCardInserted(self) -> None:
        """Show that a card is waiting at the exit. Called from the worker signal."""
        self._status = translate("main.poll.card_at_exit", self._language)
        self.statusChanged.emit()

    @Slot()
    def onCardRemoved(self) -> None:
        """Confirm that the customer took the card from the exit."""
        self._status = translate("main.poll.card_removed", self._language)
        self.statusChanged.emit()

    @Slot(str)
    def onPollFailed(self, error_code: str) -> None:
        """Show a translated text for a failed hardware poll. Never the raw code."""
        key = f"error.{error_code}"
        text = translate(key, self._language)
        # Unknown codes fall back to the key itself; show the generic line instead.
        self._status = (
            text if text != key else translate("error.HW_ERROR", self._language)
        )
        self.statusChanged.emit()

    @Slot()
    def interruptWatch(self) -> None:
        """Called on every button touch. Ends a running forgotten-card wait."""
        self._customer.interrupt_watch()

    @Slot()
    def startIssue(self) -> None:
        self._start_flow(self._customer.start_issue, with_progress=True)

    @Slot()
    def startTopup(self) -> None:
        self._start_flow(self._customer.start_topup)

    def _start_flow(
        self, flow: Callable[..., str], *, with_progress: bool = False
    ) -> None:
        """Show the ID prompt, then run the flow in a worker thread.

        The flow blocks while the reader waits for a card. Running it on the GUI
        thread would freeze the window, so the prompt would never be painted.
        Progress keys come from the worker and reach the GUI only via signal.
        """
        self._set_status("present_id")

        def _run() -> None:
            if with_progress:
                result = flow(on_progress=self._flowProgress.emit)
            else:
                result = flow()
            self._flowFinished.emit(result)

        threading.Thread(target=_run, name="customer-flow", daemon=True).start()

    @Slot(str)
    def _set_flow_result(self, key: str) -> None:
        self._set_status(key)

    def _set_status(self, key: str) -> None:
        self._status = translate(f"main.status.{key}", self._language)
        self.statusChanged.emit()


__all__ = ["MainWindowBridge"]
