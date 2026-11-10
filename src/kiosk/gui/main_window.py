"""QObject bridge between the main QML window and the kiosk flows.

The bridge holds no business rules. It forwards the customer actions to the
flow objects and exposes whether the admin panel is available. Admin is only
offered when an admin service exists, so an incomplete configuration keeps
the admin locked instead of showing a broken login.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

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
    def startIssue(self) -> None:
        self._start_flow(self._customer.start_issue)

    @Slot()
    def startTopup(self) -> None:
        self._start_flow(self._customer.start_topup)

    def _start_flow(self, flow: Callable[[], str]) -> None:
        """Show the ID prompt, then run the flow once the prompt is painted.

        The flow blocks while the reader waits for a card. Deferring it by one
        event-loop pass lets the window show the instruction first.
        """
        self._set_status("present_id")
        QTimer.singleShot(0, lambda: self._set_status(flow()))

    def _set_status(self, key: str) -> None:
        self._status = translate(f"main.status.{key}", self._language)
        self.statusChanged.emit()


__all__ = ["MainWindowBridge"]
