"""Handling of a card the user left at the exit after a card issue.

This watch runs only while a card-output movement (FC4 or another issue step)
is active. It starts once the card has reached the user exit (Sensor U).

The exit is polled while waiting. If the card is taken earlier, the watch ends
at once as taken by the user. After ``wait_s`` seconds, if the card is still
at the exit:

* the card is moved to the read position (FC7) and its UID is read,
* the UID must match the expected card, otherwise nothing is disposed,
* the card is disposed of with ``CP``,
* the Fund (500 Cent) moves from the Fund account to the balance account as
  ``recycle_refund``, and the card is set to ``recycled``.

Cards are never deleted: ledger and card history stay append-only, so the
card row changes its status instead.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

from kiosk.domain.clock import Clock
from kiosk.domain.entities import Card, CardStatus, Session
from kiosk.domain.faults import FaultCode
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.hardware.interfaces import CardDispenser
from kiosk.storage.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.forgotten_card")

FLOW_NAME = "forgotten_card"


class ForgottenCardOutcome(StrEnum):
    """Result of watching a card left at the user exit."""

    TAKEN_BY_USER = "taken_by_user"
    RECYCLED = "recycled"
    WRONG_CARD = "wrong_card"
    NOT_RECYCLABLE = "not_recyclable"


class _FaultReporter(Protocol):
    def report(
        self,
        code: FaultCode,
        session_id: str | None = None,
        *,
        account_id: int | None = None,
        card_id: int | None = None,
    ) -> object: ...


class ForgottenCardService:
    """Alert and recycle a card that the user forgot at the exit.

    Args:
        dispenser: Card hardware. Calls go through the hardware coordinator.
        uow_factory: Transaction factory for ledger and card booking.
        hasher: Salted UID hasher used to match the read UID to the card.
        clock: Time source for booking timestamps.
        deposit: Fund amount moved to the balance on recycling (500 Cent).
        sleep: Pause function, injected for tests.
        wait_s: Seconds the user has to take the card before recycling.
        check_interval_s: Seconds between exit checks while waiting.
    """

    def __init__(
        self,
        dispenser: CardDispenser,
        uow_factory: UnitOfWorkFactory,
        hasher: CardIdHasher,
        clock: Clock,
        *,
        deposit: Money,
        sleep: Callable[[float], None],
        wait_s: float = 45.0,
        check_interval_s: float = 1.0,
        faults: _FaultReporter | None = None,
    ) -> None:
        if wait_s <= 0:
            raise ValueError("wait_s must be positive")
        if check_interval_s <= 0:
            raise ValueError("check_interval_s must be positive")
        self._dispenser = dispenser
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._clock = clock
        self._deposit = deposit
        self._sleep = sleep
        self._wait_s = wait_s
        self._faults = faults
        self._check_interval_s = min(check_interval_s, wait_s)

    def watch(
        self, card: Card, cancel: threading.Event | None = None
    ) -> ForgottenCardOutcome:
        """Wait for the user to take the card; recycle it if forgotten.

        Args:
            card: The card that was just issued and is expected at the exit.
            cancel: Set by the GUI when the customer touches a button. The wait
                ends at the next check, and the card is disposed of at once,
                through the same UID check as a forgotten card.

        Returns:
            The outcome. Hardware errors propagate as ``HardwareError``.
        """
        session_id = uuid.uuid4().hex
        # Poll the exit while waiting. A card taken early ends the watch at once,
        # so a different card placed at the exit later is never treated as forgotten.
        waited = 0.0
        while waited < self._wait_s:
            self._sleep(self._check_interval_s)
            waited += self._check_interval_s
            if not self._at_exit():
                return self._finish(session_id, ForgottenCardOutcome.TAKEN_BY_USER)
            if cancel is not None and cancel.is_set():
                # Interrupted by a touch: the card is still at the exit, so it is
                # checked and disposed of now instead of after the full wait.
                return self._recycle(session_id, card)
        return self._recycle(session_id, card)

    def _at_exit(self) -> bool:
        return self._dispenser.poll_state().user_exit_occupied

    def clear_exit_before_issue(self, card: Card) -> ForgottenCardOutcome:
        """Dispose of a card left at the exit before a new issue starts.

        The card is recycled only if the UID at the read position matches the
        watched card. Any other result is a fault: nothing is disposed of, and
        an admin has to clear the situation.

        Args:
            card: The card the watch was started for.

        Returns:
            The outcome. ``WRONG_CARD`` means the card was not disposed of and
            a ``CARD_UID_AMBIGUOUS`` fault was recorded if a fault service is set.
        """
        session_id = uuid.uuid4().hex
        outcome = self._recycle(session_id, card)
        if outcome is ForgottenCardOutcome.WRONG_CARD and self._faults is not None:
            self._faults.report(
                FaultCode.CARD_UID_AMBIGUOUS,
                session_id=session_id,
                card_id=card.id,
            )
        return outcome

    def _recycle(self, session_id: str, card: Card) -> ForgottenCardOutcome:
        # Move to the read position so the UID can be checked before disposal.
        self._dispenser.move_card_to_read_position()
        uid_hash = self._hasher.hash_uid(self._dispenser.read_uid())
        if uid_hash != card.uid_hash:
            # Card at the read position is not the expected one: do not dispose.
            logger.error(
                "forgotten_card_wrong_card",
                extra={
                    "session_id": session_id,
                    "flow": FLOW_NAME,
                    "error_code": "WRONG_CARD",
                },
            )
            return ForgottenCardOutcome.WRONG_CARD

        with self._uow_factory.begin() as uow:
            current = uow.cards.get(card.id)
        if current.status is not CardStatus.ACTIVE:
            logger.error(
                "forgotten_card_not_recyclable",
                extra={
                    "session_id": session_id,
                    "flow": FLOW_NAME,
                    "error_code": "NOT_RECYCLABLE",
                },
            )
            return ForgottenCardOutcome.NOT_RECYCLABLE

        self._dispenser.dispose_card()
        # From here the card is physically gone. A booking failure must be
        # visible to an admin; it is never silently ignored.
        try:
            self._book_refund(session_id, card.id)
        except Exception:
            logger.exception(
                "forgotten_card_booking_failed",
                extra={
                    "session_id": session_id,
                    "flow": FLOW_NAME,
                    "error_code": "DB_BOOKING_FAILED",
                },
            )
            raise
        return self._finish(session_id, ForgottenCardOutcome.RECYCLED)

    def _book_refund(self, session_id: str, card_id: int) -> None:
        now = self._clock.now()
        with self._uow_factory.begin() as uow:
            card = uow.cards.get(card_id)
            # Card.recycle raises if the card is no longer active. Checked inside
            # the transaction, so a repeated attempt cannot credit the Pfand twice.
            uow.cards.update(card.recycle(now))
            uow.sessions.add(
                Session(
                    id=session_id,
                    flow=FLOW_NAME,
                    started_at=now,
                    ended_at=now,
                    outcome=ForgottenCardOutcome.RECYCLED,
                )
            )
            entry = uow.ledger.append(
                LedgerEntry.new(
                    account_id=card.account_id,
                    entry_type=EntryType.RECYCLE_REFUND,
                    amount=self._deposit,
                    deposit_delta=-self._deposit,
                    created_at=now,
                    session_id=session_id,
                    operation_id=f"recycle:{card.id}",
                    card_id=card.id,
                )
            )
            uow.commit()
        logger.info(
            "ledger_entry_created",
            extra={
                "session_id": session_id,
                "flow": FLOW_NAME,
                "account_id": entry.account_id,
                "amount_cents": entry.amount_cents,
            },
        )

    def _finish(
        self, session_id: str, outcome: ForgottenCardOutcome
    ) -> ForgottenCardOutcome:
        logger.info(
            "forgotten_card_finished",
            extra={"session_id": session_id, "flow": FLOW_NAME},
        )
        return outcome


__all__ = ["ForgottenCardOutcome", "ForgottenCardService"]
