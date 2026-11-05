"""ViewModel for the admin panel. Holds presentation state; no business rules.

Services do all checks. The ViewModel translates their typed errors into
localized text keys, formats money from integer cents, and tracks the
admin session timeout. It runs on the GUI thread only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from kiosk.domain.clock import Clock
from kiosk.domain.errors import AdminSessionExpiredError, KioskError
from kiosk.i18n.texts import translate
from kiosk.services.admin_auth import AdminAuthService, AdminSession
from kiosk.services.admin_payout import (
    AccountSummary,
    AdminPayoutService,
    PayoutConfirmation,
)
from kiosk.services.admin_session import ActiveAdminSession, AdminSessionGuard

logger = logging.getLogger("kiosk.gui.admin")

FLOW_NAME = "admin_panel"


@dataclass(frozen=True, slots=True)
class AccountRow:
    """One line of the account list, already formatted for display.

    Attributes:
        account_id: Internal id used to open the detail view.
        status_text: Localized open/closed label.
        balance_text: Balance formatted with a euro sign, e.g. ``20,00 EUR``.
    """

    account_id: int
    status_text: str
    balance_text: str


def format_cents(cents: int) -> str:
    """Format integer cents as German money text, e.g. ``1234`` -> ``12,34 EUR``.

    Args:
        cents: Amount in cents. Negative values keep their sign.

    Raises:
        TypeError: If ``cents`` is not an int. Floats are never displayed.
    """
    if type(cents) is not int:
        raise TypeError("money must be integer cents")
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole},{frac:02d} EUR"


class AdminViewModel:
    """Admin panel state machine.

    Args:
        auth: Admin login service.
        payout: Payout and account overview service.
        guard: Session inactivity guard.
        clock: Time source, used only for timeout display.
        language: UI language code.
    """

    def __init__(
        self,
        auth: AdminAuthService,
        payout: AdminPayoutService,
        guard: AdminSessionGuard,
        clock: Clock,
        *,
        language: str = "de",
    ) -> None:
        self._auth = auth
        self._payout = payout
        self._guard = guard
        self._clock = clock
        self._language = language
        self._session: ActiveAdminSession | None = None
        self._message = ""

    # -- state -----------------------------------------------------------

    @property
    def is_logged_in(self) -> bool:
        """True while an admin session is open and not timed out."""
        if self._session is None:
            return False
        if self._guard.is_active(self._session):
            return True
        self._end_session(translate("admin.session.timeout", self._language))
        return False

    @property
    def message(self) -> str:
        """Last localized message for the admin (error or success)."""
        return self._message

    # -- login -----------------------------------------------------------

    def login(self, raw_admin_uid: str, pin: str) -> bool:
        """Try to open the admin panel. Returns True on success.

        The UID and PIN are passed on to the service and never stored here.
        """
        try:
            session: AdminSession = self._auth.login(raw_admin_uid, pin)
        except KioskError as exc:
            self._message = translate(f"error.{exc.code}", self._language)
            return False
        self._session = self._guard.open(session)
        self._message = ""
        return True

    def logout(self) -> None:
        """Close the admin session. Safe to call when not logged in."""
        self._end_session("")

    # -- accounts --------------------------------------------------------

    def accounts(self) -> list[AccountRow]:
        """Return the formatted account list. Requires an active session."""
        self._touch()
        return [self._row(summary) for summary in self._payout.list_accounts()]

    def account_detail(self, account_id: int) -> AccountSummary:
        """Return one account summary. Requires an active session."""
        self._touch()
        return self._payout.summary(account_id)

    def detail_text(self, summary: AccountSummary) -> dict[str, str]:
        """Return labelled, formatted fields for the detail view."""
        t = self._t
        return {
            t("admin.account.balance"): format_cents(summary.balance_cents),
            t("admin.account.deposit"): format_cents(summary.deposit_cents),
            t("admin.account.active_cards"): str(summary.active_cards),
            t("admin.account.recycled_cards"): str(summary.recycled_cards),
            t("admin.account.cancelled_cards"): str(summary.cancelled_cards),
            t("admin.account.open_deposit"): format_cents(summary.open_deposit_cents),
        }

    # -- payout ----------------------------------------------------------

    def payout(self, account_id: int, confirmation: PayoutConfirmation) -> str | None:
        """Run the payout. Returns the receipt reference, or None on failure.

        Warnings are shown by the view before this is called. The service
        re-checks every confirmation and the account state.
        """
        self._touch()
        try:
            receipt = self._payout.payout(account_id, confirmation)
        except KioskError as exc:
            self._message = translate(f"error.{exc.code}", self._language)
            return None
        self._message = translate(
            "admin.payout.done", self._language, reference=receipt.reference
        )
        return receipt.reference

    # -- internals -------------------------------------------------------

    @property
    def _t(self) -> _Translator:
        return _Translator(self._language)

    def _row(self, summary: AccountSummary) -> AccountRow:
        return AccountRow(
            account_id=summary.account_id,
            status_text=translate(
                "admin.account.closed" if summary.is_closed else "admin.account.open",
                self._language,
            ),
            balance_text=format_cents(summary.balance_cents),
        )

    def _touch(self) -> None:
        """Refresh activity; raise a typed error if no live session exists.

        Raises:
            AdminSessionExpiredError: If there is no session or it timed out.
        """
        if self._session is None or not self._guard.is_active(self._session):
            self._end_session(translate("admin.session.timeout", self._language))
            raise AdminSessionExpiredError("admin session required")
        self._session = self._guard.touch(self._session)

    def _end_session(self, message: str) -> None:
        self._session = None
        self._message = message


class _Translator:
    """Callable shorthand for ``translate`` bound to one language."""

    def __init__(self, language: str) -> None:
        self._language = language

    def __call__(self, key: str) -> str:
        return translate(key, self._language)


__all__ = ["AccountRow", "AdminViewModel", "format_cents"]
