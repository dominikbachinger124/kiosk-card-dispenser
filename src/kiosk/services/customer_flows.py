"""Customer flows Neue Karte and Konto aufladen: read the ID, then book.

Both flows start with the customer reading their card at the Flipper Zero.
Only a successful read leads to a service call. The raw UID is hashed at once
and never stored, logged or returned. The result is a short key that the GUI
translates; no exception text leaves this module.

Result keys: ``issued``, ``empty``, ``aborted``, ``topped_up``,
``unknown_account``.
"""

from __future__ import annotations

import logging
from typing import Protocol

from kiosk.domain.errors import KioskError, NotFoundError
from kiosk.domain.identity import CardIdHasher
from kiosk.services.issue_card import IssueOutcome, IssueResult
from kiosk.services.topup import TopUpResult

logger = logging.getLogger("kiosk.services.customer_flows")

RESULT_ISSUED = "issued"
RESULT_EMPTY = "empty"
RESULT_ABORTED = "aborted"
RESULT_TOPPED_UP = "topped_up"
RESULT_UNKNOWN_ACCOUNT = "unknown_account"


class _IdReader(Protocol):
    def read_id(self) -> str: ...


class _Issue(Protocol):
    def issue(self, *, customer_uid_hash: str) -> IssueResult: ...


class _TopUp(Protocol):
    def top_up(self, *, customer_uid_hash: str) -> TopUpResult: ...


class CustomerFlows:
    """Entry points for the customer actions shown on the main window.

    Args:
        reader: Identifier reader (Flipper Zero). Raises on timeout or loss.
        issue: Issue service for new cards.
        topup: Top-up service for existing accounts.
        hasher: Salted hasher for the customer identifier.
    """

    def __init__(
        self,
        *,
        reader: _IdReader,
        issue: _Issue,
        topup: _TopUp,
        hasher: CardIdHasher,
    ) -> None:
        self._reader = reader
        self._issue = issue
        self._topup = topup
        self._hasher = hasher

    def start_issue(self) -> str:
        """Read the customer ID, then issue one card. Returns a result key."""
        customer_hash = self._read_customer_hash()
        if customer_hash is None:
            return RESULT_ABORTED
        try:
            result = self._issue.issue(customer_uid_hash=customer_hash)
        except KioskError as exc:
            logger.error(
                "customer_issue_failed",
                extra={"flow": "issue_card", "error_code": exc.code},
            )
            return RESULT_ABORTED
        return _issue_key(result.outcome)

    def start_topup(self) -> str:
        """Read the customer ID, then top up the existing account."""
        customer_hash = self._read_customer_hash()
        if customer_hash is None:
            return RESULT_ABORTED
        try:
            self._topup.top_up(customer_uid_hash=customer_hash)
        except NotFoundError:
            return RESULT_UNKNOWN_ACCOUNT
        except KioskError as exc:
            logger.error(
                "customer_topup_failed",
                extra={"flow": "topup", "error_code": exc.code},
            )
            return RESULT_ABORTED
        return RESULT_TOPPED_UP

    def _read_customer_hash(self) -> str | None:
        """Read and hash the customer ID. None means the flow is aborted."""
        try:
            raw = self._reader.read_id()
        except KioskError as exc:
            logger.error(
                "customer_id_read_failed",
                extra={"error_code": exc.code},
            )
            return None
        return self._hasher.hash_uid(raw)


def _issue_key(outcome: IssueOutcome) -> str:
    if outcome is IssueOutcome.ISSUED:
        return RESULT_ISSUED
    if outcome is IssueOutcome.EMPTY:
        return RESULT_EMPTY
    return RESULT_ABORTED


__all__ = [
    "CustomerFlows",
    "RESULT_ABORTED",
    "RESULT_EMPTY",
    "RESULT_ISSUED",
    "RESULT_TOPPED_UP",
    "RESULT_UNKNOWN_ACCOUNT",
]
