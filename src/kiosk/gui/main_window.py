"""QObject bridge between the main QML window and the kiosk flows.

The bridge holds no business rules. It forwards the customer actions to the
flow objects and exposes whether the admin panel is available. Admin is only
offered when an admin service exists, so an incomplete configuration keeps
the admin locked instead of showing a broken login.
"""

from __future__ import annotations

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
    def startIssue(self) -> None:
        self._set_status(self._customer.start_issue())

    @Slot()
    def startTopup(self) -> None:
        self._set_status(self._customer.start_topup())

    def _set_status(self, key: str) -> None:
        self._status = translate(f"main.status.{key}", self._language)
        self.statusChanged.emit()


__all__ = ["MainWindowBridge"]
