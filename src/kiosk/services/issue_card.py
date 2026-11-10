"""Issue a new or additional card: hardware first, booking only after a read.

Flow (domain.md "Neue Karte" / "Weitere Karte"):

1. The dispenser presents a card from the stack at the user exit (``FC4``).
   Empty stock or a stop condition aborts the flow, with a fault record.
2. The card is moved to the read position (``FC7``) and its UID is read. Then
   the card is brought back to the user exit (``FC4``). The UID must be
   readable, otherwise the flow aborts.
3. Only now are the account and card written and the 2000 cent balance and
   500 cent Pfand booked, in one transaction. The user then takes the card;
   the forgotten-card watch handles a card left at the exit.

No booking ever exists for a card whose UID was not read. Every abort ends
without a ledger entry and without a partial card row.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from kiosk.domain.clock import Clock
from kiosk.domain.entities import Account, Card, Session
from kiosk.domain.errors import (
    DispenserEmptyError,
    HardwareError,
)
from kiosk.domain.faults import FaultCode
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.hardware.interfaces import CardDispenser
from kiosk.services.faults import FaultService
from kiosk.storage.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.issue_card")

FLOW_NAME = "issue_card"


class IssueOutcome(StrEnum):
    """Result of an issue attempt."""

    ISSUED = "issued"
    EMPTY = "empty"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class IssueResult:
    """Outcome of one issue attempt.

    Attributes:
        outcome: Result category.
        card_id: Booked card, only for ``ISSUED``.
        account_id: Account the flow belongs to, if known.
        fault_id: Recorded fault, if the hardware stopped the flow.
    """

    outcome: IssueOutcome
    card_id: int | None = None
    account_id: int | None = None
    fault_id: int | None = None


class IssueCardService:
    """Hand out a card and book the purchase after its UID has been read.

    Args:
        dispenser: Card hardware, reached through the hardware coordinator.
        uow_factory: Transaction factory for accounts, cards and ledger.
        hasher: Salted UID hasher. The raw UID is never stored or logged.
        faults: Fault service that records hardware stops.
        clock: Time source for bookings.
        topup: Balance credit per card (2000 cent).
        deposit: Pfand per card (500 cent).
        collection: Cash collected by the gatekeeper per card (2500 cent).
    """

    def __init__(
        self,
        dispenser: CardDispenser,
        uow_factory: UnitOfWorkFactory,
        hasher: CardIdHasher,
        faults: FaultService,
        clock: Clock,
        *,
        topup: Money,
        deposit: Money,
        collection: Money,
    ) -> None:
        if topup.cents + deposit.cents != collection.cents:
            raise ValueError("collection must equal topup plus deposit")
        self._dispenser = dispenser
        self._uow_factory = uow_factory
        self._hasher = hasher
        self._faults = faults
        self._clock = clock
        self._topup = topup
        self._deposit = deposit
        self._collection = collection

    def issue(
        self,
        *,
        customer_uid_hash: str,
        existing_account_id: int | None = None,
        on_card_checked: Callable[[], None] | None = None,
    ) -> IssueResult:
        """Run the issue flow for one new card.

        The customer's identity (``customer_uid_hash``) comes from the identifier
        read at the start of the flow. It is the hash of the customer's own
        card UID, never the raw value. A new card's UID is read from the
        dispensed card, not from this input.

        Args:
            customer_uid_hash: Salted hash of the identifier that started the flow.
            existing_account_id: Account for an additional card, or None to
                find or create the account by ``customer_uid_hash``.
            on_card_checked: Called once the dispensed card's UID was read and
                before the card moves to the exit. Optional progress hint.

        Returns:
            The outcome. An abort never leaves a ledger entry or card row.
        """
        session_id = uuid.uuid4().hex
        # The session row must exist before any fault can reference it
        # (device_faults.session_id is a foreign key). It is written in its
        # own transaction, so it survives an abort; bookings do not.
        with self._uow_factory.begin() as uow:
            uow.sessions.add(
                Session(
                    id=session_id,
                    flow=FLOW_NAME,
                    started_at=self._clock.now(),
                )
            )
            uow.commit()

        try:
            # FC7 from the stack brings the card to the read position; the UID
            # is read there; FC4 then brings the card to the user exit. The
            # booking comes only after the UID.
            self._dispenser.move_card_to_read_position()
            new_uid_hash = self._hasher.hash_uid(self._dispenser.read_uid())
            if on_card_checked is not None:
                on_card_checked()
            self._dispenser.move_card_to_user_exit()
        except DispenserEmptyError:
            fault = self._faults.report(
                FaultCode.DISPENSER_EMPTY,
                session_id=session_id,
                account_id=existing_account_id,
            )
            return IssueResult(
                IssueOutcome.EMPTY,
                account_id=existing_account_id,
                fault_id=fault.id,
            )
        except HardwareError as exc:
            fault = self._faults.report(
                _fault_code_for(exc),
                session_id=session_id,
                account_id=existing_account_id,
            )
            logger.error(
                "issue_aborted",
                extra={
                    "session_id": session_id,
                    "flow": FLOW_NAME,
                    "error_code": exc.code,
                },
            )
            return IssueResult(
                IssueOutcome.ABORTED,
                account_id=existing_account_id,
                fault_id=fault.id,
            )

        card_id, account = self._book(
            session_id=session_id,
            new_uid_hash=new_uid_hash,
            customer_uid_hash=customer_uid_hash,
            existing_account_id=existing_account_id,
        )
        logger.info(
            "card_issued",
            extra={
                "session_id": session_id,
                "flow": FLOW_NAME,
                "account_id": account.id,
            },
        )
        return IssueResult(IssueOutcome.ISSUED, card_id=card_id, account_id=account.id)

    def _book(
        self,
        *,
        session_id: str,
        new_uid_hash: str,
        customer_uid_hash: str,
        existing_account_id: int | None,
    ) -> tuple[int, Account]:
        """Create the card and both bookings in one transaction."""
        now = self._clock.now()
        with self._uow_factory.begin() as uow:
            if existing_account_id is None:
                account = uow.accounts.find_by_hash(customer_uid_hash)
                if account is None:
                    account = uow.accounts.add(customer_uid_hash, now)
            else:
                account = uow.accounts.get(existing_account_id)

            card: Card = uow.cards.add(new_uid_hash, account.id, now)
            uow.ledger.append(
                LedgerEntry.new(
                    account_id=account.id,
                    entry_type=EntryType.CASH_IN_TOPUP,
                    amount=self._topup,
                    deposit_delta=Money(0),
                    created_at=now,
                    session_id=session_id,
                    operation_id=f"issue_topup:{session_id}",
                    card_id=card.id,
                )
            )
            uow.ledger.append(
                LedgerEntry.new(
                    account_id=account.id,
                    entry_type=EntryType.CASH_IN_DEPOSIT,
                    amount=Money(0),
                    deposit_delta=self._deposit,
                    created_at=now,
                    session_id=session_id,
                    operation_id=f"issue_deposit:{session_id}",
                    card_id=card.id,
                )
            )
            uow.commit()
        return card.id, account


def _fault_code_for(exc: HardwareError) -> FaultCode:
    """Map a hardware error to the stored fault category."""
    if exc.code == "CARD_JAMMED":
        return FaultCode.CARD_JAMMED
    if exc.code == "CARD_OVERLAP":
        return FaultCode.CARD_OVERLAP
    return FaultCode.DISPENSER_STATE


__all__ = ["IssueCardService", "IssueOutcome", "IssueResult"]
