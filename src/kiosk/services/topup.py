"""Top up an existing account with a fixed 20 EUR, paid in advance at the gatekeeper.

Flow (domain.md "Konto aufladen"):

1. The customer's identifier is read at the Flipper Zero and hashed.
2. The account must already exist. An unknown identifier aborts with
   ``NotFoundError``; a top-up never creates an account.
3. The fixed amount is booked as ``cash_in_topup`` in one transaction.

The cash is handed to the gatekeeper before the flow starts. The kiosk has
no confirmation step for it. No card is dispensed and no card row is written.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum

from kiosk.domain.clock import Clock
from kiosk.domain.entities import Session
from kiosk.domain.errors import NotFoundError
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.storage.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.topup")

FLOW_NAME = "topup"


class TopUpOutcome(StrEnum):
    """Result of a top-up attempt."""

    TOPPED_UP = "topped_up"


@dataclass(frozen=True, slots=True)
class TopUpResult:
    """Outcome of one top-up.

    Attributes:
        outcome: Result category.
        account_id: Internal id of the credited account.
        entry_id: Ledger entry that was written.
    """

    outcome: TopUpOutcome
    account_id: int
    entry_id: int


class TopUpService:
    """Credit a fixed amount to an existing account.

    Args:
        uow_factory: Transaction factory for accounts, sessions and ledger.
        clock: Time source for bookings.
        topup: Fixed credit per top-up (2000 cent).
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        *,
        topup: Money,
    ) -> None:
        if topup.cents <= 0:
            raise ValueError("topup must be positive")
        self._uow_factory = uow_factory
        self._clock = clock
        self._topup = topup

    def top_up(self, *, customer_uid_hash: str) -> TopUpResult:
        """Credit the fixed amount to the account behind the identifier.

        Args:
            customer_uid_hash: Salted hash of the identifier read at the
                Flipper Zero. Never the raw UID.

        Returns:
            The booked top-up.

        Raises:
            NotFoundError: If no account exists for the identifier. Nothing
                is booked in that case.
            AccountClosedError: If the account is closed.
        """
        session_id = uuid.uuid4().hex
        now = self._clock.now()
        with self._uow_factory.begin() as uow:
            account = uow.accounts.find_by_hash(customer_uid_hash)
            if account is None:
                logger.warning(
                    "topup_rejected",
                    extra={
                        "session_id": session_id,
                        "flow": FLOW_NAME,
                        "error_code": "NOT_FOUND",
                    },
                )
                raise NotFoundError("no account for this identifier")

            uow.sessions.add(Session(id=session_id, flow=FLOW_NAME, started_at=now))
            entry = uow.ledger.append(
                LedgerEntry.new(
                    account_id=account.id,
                    entry_type=EntryType.CASH_IN_TOPUP,
                    amount=self._topup,
                    deposit_delta=Money(0),
                    created_at=now,
                    session_id=session_id,
                    operation_id=f"topup:{session_id}",
                )
            )
            if entry.id is None:
                raise RuntimeError("ledger append returned no id")
            entry_id = entry.id
            uow.commit()

        logger.info(
            "ledger_entry_created",
            extra={
                "session_id": session_id,
                "flow": FLOW_NAME,
                "account_id": account.id,
                "amount_cents": self._topup.cents,
            },
        )
        return TopUpResult(
            outcome=TopUpOutcome.TOPPED_UP,
            account_id=account.id,
            entry_id=entry_id,
        )


__all__ = ["TopUpOutcome", "TopUpResult", "TopUpService"]
