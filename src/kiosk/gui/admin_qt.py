"""QObject bridge that exposes ``AdminViewModel`` to QML.

This adapter contains no business rules. It forwards calls to the plain
Python ViewModel and turns results into Qt types. It must run on the GUI
thread. Money crosses the boundary only as formatted text or integer cents.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QObject, Signal, Slot

from kiosk.domain.errors import KioskError
from kiosk.gui.admin_viewmodel import AdminViewModel
from kiosk.i18n.texts import translate
from kiosk.services.admin_payout import PayoutConfirmation


class AdminQt(QObject):
    """QML-facing admin panel object.

    Args:
        viewmodel: The plain Python ViewModel that holds all presentation state.
    """

    loggedInChanged = Signal()
    messageChanged = Signal()
    accountsChanged = Signal()

    def __init__(self, viewmodel: AdminViewModel, language: str = "de") -> None:
        super().__init__()
        self._vm = viewmodel
        self._language = language
        self._accounts: list[dict[str, Any]] = []

    @Property(bool, notify=loggedInChanged)
    def loggedIn(self) -> bool:
        return self._vm.is_logged_in

    @Property(str, notify=messageChanged)
    def message(self) -> str:
        return self._vm.message

    @Property("QVariantList", notify=accountsChanged)
    def accounts(self) -> list[dict[str, Any]]:
        return self._accounts

    @Slot(str, result=str)
    def text(self, key: str) -> str:
        """Return a localized UI text. QML never hard-codes German or English."""
        return translate(key, self._language)

    @Slot(str, str)
    def login(self, raw_admin_uid: str, pin: str) -> None:
        self._vm.login(raw_admin_uid, pin)
        self._notify_login()

    @Slot()
    def logout(self) -> None:
        self._vm.logout()
        self._notify_login()

    @Slot()
    def refreshAccounts(self) -> None:
        try:
            rows = self._vm.accounts()
        except KioskError:
            self._accounts = []
        else:
            self._accounts = [
                {
                    "accountId": row.account_id,
                    "statusText": row.status_text,
                    "balanceText": row.balance_text,
                }
                for row in rows
            ]
        self.accountsChanged.emit()
        self.messageChanged.emit()
        self._notify_login()

    @Slot(int, bool, bool, bool, result=str)
    def payout(
        self,
        account_id: int,
        cash_handed_over: bool,
        open_cards_acknowledged: bool,
        final_confirmed: bool,
    ) -> str:
        reference = self._vm.payout(
            account_id,
            PayoutConfirmation(
                cash_handed_over=cash_handed_over,
                open_cards_acknowledged=open_cards_acknowledged,
                final_confirmed=final_confirmed,
            ),
        )
        self.messageChanged.emit()
        self.refreshAccounts()
        return reference or ""

    def _notify_login(self) -> None:
        self.loggedInChanged.emit()
        self.messageChanged.emit()


__all__ = ["AdminQt"]
