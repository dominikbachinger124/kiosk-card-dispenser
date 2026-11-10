"""Customer flows Neue Karte and Konto aufladen: read the ID, then book.

Both flows start with the customer reading their card at the Flipper Zero.
Only a successful read leads to a service call. The raw UID is hashed at once
and never stored, logged or returned. The result is a short key that the GUI
translates; no exception text leaves this module.

Result keys: ``issued``, ``empty``, ``aborted``, ``topped_up``,
``unknown_account``, ``exit_occupied``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from kiosk.domain.entities import Card
from kiosk.domain.errors import KioskError, NotFoundError
from kiosk.domain.identity import CardIdHasher
from kiosk.services.issue_card import IssueOutcome, IssueResult
from kiosk.services.topup import TopUpResult
from kiosk.storage.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.customer_flows")

RESULT_ISSUED = "issued"
RESULT_EMPTY = "empty"
RESULT_ABORTED = "aborted"
RESULT_TOPPED_UP = "topped_up"
RESULT_UNKNOWN_ACCOUNT = "unknown_account"
RESULT_EXIT_OCCUPIED = "exit_occupied"
PROGRESS_CARD_CHECKED = "card_checked"


class _IdReader(Protocol):
    def read_id(self) -> str: ...


class _Issue(Protocol):
    def issue(
        self,
        *,
        customer_uid_hash: str,
        on_card_checked: Callable[[], None] | None = None,
    ) -> IssueResult: ...


class _TopUp(Protocol):
    def top_up(self, *, customer_uid_hash: str) -> TopUpResult: ...


class _Watch(Protocol):
    def start(self, card: Card) -> bool: ...

    def cancel(self) -> None: ...


class _ExitSensor(Protocol):
    def exit_occupied(self) -> bool: ...


class CustomerFlows:
    """Entry points for the customer actions shown on the main window.

    Args:
        reader: Identifier reader (Flipper Zero). Raises on timeout or loss.
        issue: Issue service for new cards.
        topup: Top-up service for existing accounts.
        hasher: Salted hasher for the customer identifier.
        watch: Starts the forgotten-card watch for an issued card. Optional.
        db: Reads the issued card for the watch. Required with ``watch``.
        exit_sensor: Reports whether a card waits at the user exit. When it is
            occupied, the ID is not read at all. Optional.
    """

    def __init__(
        self,
        *,
        reader: _IdReader,
        issue: _Issue,
        topup: _TopUp,
        hasher: CardIdHasher,
        watch: _Watch | None = None,
        db: UnitOfWorkFactory | None = None,
        exit_sensor: _ExitSensor | None = None,
    ) -> None:
        self._reader = reader
        self._exit_sensor = exit_sensor
        self._issue = issue
        self._topup = topup
        self._hasher = hasher
        self._watch = watch
        self._db = db

    def start_issue(self, on_progress: Callable[[str], None] | None = None) -> str:
        """Read the customer ID, then issue one card. Returns a result key.

        Args:
            on_progress: Optional hook called with ``PROGRESS_CARD_CHECKED``
                once the dispensed card was checked. Runs on the flow's thread.
        """
        if self._exit_occupied():
            return RESULT_EXIT_OCCUPIED
        customer_hash = self._read_customer_hash()
        if customer_hash is None:
            return RESULT_ABORTED
        on_card_checked = (
            None if on_progress is None else lambda: on_progress(PROGRESS_CARD_CHECKED)
        )
        try:
            result = self._issue.issue(
                customer_uid_hash=customer_hash,
                on_card_checked=on_card_checked,
            )
        except KioskError as exc:
            logger.error(
                "customer_issue_failed",
                extra={"flow": "issue_card", "error_code": exc.code},
            )
            return RESULT_ABORTED
        if result.outcome is IssueOutcome.ISSUED and result.card_id is not None:
            self._start_watch(result.card_id)
        return _issue_key(result.outcome)

    def _start_watch(self, card_id: int) -> None:
        """Hand the issued card to the watch. Never blocks the flow."""
        if self._watch is None or self._db is None:
            return
        with self._db.begin() as uow:
            card = uow.cards.get(card_id)
        self._watch.start(card)

    def interrupt_watch(self) -> None:
        """Customer touched a button: dispose of a waiting card now.

        Safe to call from the GUI thread. It only sets the watch's cancel event;
        the disposal itself runs in the watch thread through the UID check.
        """
        if self._watch is not None:
            self._watch.cancel()

    def start_topup(self) -> str:
        """Read the customer ID, then top up the existing account."""
        if self._exit_occupied():
            return RESULT_EXIT_OCCUPIED
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

    def _exit_occupied(self) -> bool:
        """True if a card waits at the exit. The ID reader must not run then.

        A card still waiting for the forgotten-card watch is disposed of at once,
        through the watch's UID check, so the customer does not wait for the timer.
        """
        if self._exit_sensor is None:
            return False
        occupied = self._exit_sensor.exit_occupied()
        if occupied and self._watch is not None:
            self._watch.cancel()
        return occupied

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
