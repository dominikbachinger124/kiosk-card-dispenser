"""ViewModels for the customer flows Neue/Weitere Karte and Konto aufladen.

Services do all booking rules. These classes only translate the service
result or a typed error into one localized line of text, formatted from
integer cents. They run on the GUI thread and never log identifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kiosk.domain.errors import KioskError
from kiosk.domain.money import Money
from kiosk.gui.admin_viewmodel import format_cents
from kiosk.i18n.texts import translate
from kiosk.services.issue_card import IssueOutcome, IssueResult
from kiosk.services.topup import TopUpResult


@dataclass(frozen=True, slots=True)
class CustomerResult:
    """One outcome for the customer screen.

    Attributes:
        ok: True only if the service booked the flow successfully.
        text: Localized line for the screen. Never raw exception text.
    """

    ok: bool
    text: str


class IssueViewModel:
    """Presents the result of an issue attempt.

    Args:
        service: Issue service, or any object with the same ``issue`` method.
        language: UI language code.
        topup: Balance credit per card, for display.
        deposit: Deposit per card, for display.
    """

    def __init__(
        self,
        service: _IssueService,
        *,
        language: str,
        topup: Money,
        deposit: Money,
    ) -> None:
        self._service = service
        self._language = language
        self._topup = topup
        self._deposit = deposit

    def start(self, customer_uid_hash: str) -> CustomerResult:
        """Run the issue flow for the identifier and return a screen line."""
        try:
            result = self._service.issue(customer_uid_hash=customer_uid_hash)
        except KioskError as exc:
            return CustomerResult(False, translate(f"error.{exc.code}", self._language))
        return self._from_result(result)

    def _from_result(self, result: IssueResult) -> CustomerResult:
        if result.outcome is IssueOutcome.ISSUED:
            return CustomerResult(
                True,
                translate(
                    "issue.success",
                    self._language,
                    balance=format_cents(self._topup.cents),
                    deposit=format_cents(self._deposit.cents),
                ),
            )
        if result.outcome is IssueOutcome.EMPTY:
            return CustomerResult(
                False, translate("issue.empty_notice", self._language)
            )
        return CustomerResult(False, translate("issue.jam_notice", self._language))


class TopUpViewModel:
    """Presents the result of a fixed top-up.

    Args:
        service: Top-up service, or any object with the same ``top_up`` method.
        language: UI language code.
        topup: Fixed top-up amount, for display.
    """

    def __init__(self, service: _TopUpService, *, language: str, topup: Money) -> None:
        self._service = service
        self._language = language
        self._topup = topup

    def start(self, customer_uid_hash: str) -> CustomerResult:
        """Run the top-up for the identifier and return a screen line."""
        try:
            self._service.top_up(customer_uid_hash=customer_uid_hash)
        except KioskError as exc:
            if exc.code == "NOT_FOUND":
                return CustomerResult(
                    False, translate("topup.unknown_account", self._language)
                )
            return CustomerResult(False, translate(f"error.{exc.code}", self._language))
        return CustomerResult(
            True,
            translate(
                "topup.success",
                self._language,
                amount=format_cents(self._topup.cents),
            ),
        )


class _IssueService(Protocol):
    """Structural type of the issue service used here."""

    def issue(
        self, *, customer_uid_hash: str, existing_account_id: int | None = None
    ) -> IssueResult: ...


class _TopUpService(Protocol):
    """Structural type of the top-up service used here."""

    def top_up(self, *, customer_uid_hash: str) -> TopUpResult: ...


__all__ = ["CustomerResult", "IssueViewModel", "TopUpViewModel"]
