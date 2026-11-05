"""Admin view of accounts and the cash payout that closes an account.

Flow (after the admin has authenticated with admin card and PIN):

1. The admin looks at all accounts and opens one account.
2. The summary shows balance, Pfand, card counts and the open Pfand of
   cards that were never returned.
3. If open cards exist, the admin must acknowledge that their Pfand was
   already paid and cannot be refunded.
4. The gatekeeper hands over the cash, and the admin confirms the final
   step. Only then the service books the payout and closes the account.

Everything after the final confirmation runs in one transaction: open cards
are cancelled, the balance is brought to zero with a ``payout`` entry, the
account is closed, and every step is written to the admin audit.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from kiosk.domain.clock import Clock
from kiosk.domain.entities import Account, Card, CardStatus, Session
from kiosk.domain.errors import (
    AccountClosedError,
    PayoutNotConfirmedError,
)
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.storage.unit_of_work import UnitOfWork, UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.admin_payout")

FLOW_NAME = "admin_payout"


class PayoutOutcome(StrEnum):
    """Audit outcome values for admin actions."""

    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class AccountSummary:
    """Read-only overview of one account for the admin panel.

    Attributes:
        account_id: Internal primary key. Never the card UID.
        is_closed: True once the account has been closed.
        balance_cents: Spendable credit.
        deposit_cents: Pfand held for the account.
        active_cards: Cards still outstanding (not returned, not cancelled).
        recycled_cards: Cards returned and recycled.
        cancelled_cards: Cards cancelled by an earlier payout.
        open_deposit_cents: Pfand of active cards that was paid but not refunded.
    """

    account_id: int
    is_closed: bool
    balance_cents: int
    deposit_cents: int
    active_cards: int
    recycled_cards: int
    cancelled_cards: int
    open_deposit_cents: int


@dataclass(frozen=True, slots=True)
class PayoutConfirmation:
    """Explicit confirmations the admin and gatekeeper give before a payout.

    Attributes:
        cash_handed_over: Gatekeeper confirms the cash was handed out.
        open_cards_acknowledged: Admin saw the warning about open cards.
            Required only if open cards exist.
        final_confirmed: Admin confirms the closing step itself.
    """

    cash_handed_over: bool
    open_cards_acknowledged: bool
    final_confirmed: bool


@dataclass(frozen=True, slots=True)
class PayoutReceipt:
    """Result of a completed payout. Contains no personal data.

    Attributes:
        reference: Receipt number for the cash handout record.
        account_id: Internal account id.
        paid_cents: Amount handed out in cash.
        cancelled_cards: Number of open cards cancelled in this payout.
        closed_at: Time the account was closed, UTC.
    """

    reference: str
    account_id: int
    paid_cents: int
    cancelled_cards: int
    closed_at: datetime


class AdminPayoutService:
    """Account overview, cash payout and account closure for the admin panel.

    Admin authentication (admin card UID and PIN) happens before this service
    is called. The service enforces the booking rules and confirmations only.

    Args:
        uow_factory: Transaction factory for all reads and bookings.
        clock: Time source for bookings and audit entries.
        deposit: Pfand per card (500 Cent), used for the open-deposit figure.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        *,
        deposit: Money,
    ) -> None:
        self._uow_factory = uow_factory
        self._clock = clock
        self._deposit = deposit

    def list_accounts(self) -> list[AccountSummary]:
        """Return summaries of all accounts, open and closed, by id."""
        with self._uow_factory.begin() as uow:
            return [
                self._summary(uow, account.id) for account in uow.accounts.list_all()
            ]

    def summary(self, account_id: int) -> AccountSummary:
        """Return the summary of one account.

        Raises:
            NotFoundError: If the account does not exist.
        """
        with self._uow_factory.begin() as uow:
            return self._summary(uow, account_id)

    def payout(
        self,
        account_id: int,
        confirmation: PayoutConfirmation,
    ) -> PayoutReceipt:
        """Pay out the balance in cash, cancel open cards, and close the account.

        Args:
            account_id: Account to close.
            confirmation: Confirmations given by the gatekeeper and admin.

        Returns:
            A receipt with a reference number and no personal data.

        Raises:
            PayoutNotConfirmedError: If a confirmation is missing.
            NotFoundError: If the account does not exist or is already closed.
            AccountClosedError: If the account is already closed.
            DuplicateOperationError: If the payout was already booked.
        """
        if not confirmation.cash_handed_over or not confirmation.final_confirmed:
            raise PayoutNotConfirmedError(
                "cash handover and final confirmation required"
            )

        session_id = uuid.uuid4().hex
        now = self._clock.now()
        with self._uow_factory.begin() as uow:
            account = self._open_account(uow, account_id)
            cards = uow.cards.list_for_account(account.id)
            active = [card for card in cards if card.status is CardStatus.ACTIVE]
            if active and not confirmation.open_cards_acknowledged:
                raise PayoutNotConfirmedError(
                    "open cards exist: warning must be acknowledged"
                )

            uow.sessions.add(
                Session(
                    id=session_id,
                    flow=FLOW_NAME,
                    started_at=now,
                    ended_at=now,
                    outcome=PayoutOutcome.COMPLETED,
                )
            )
            for card in active:
                self._cancel_card(uow, session_id, card, now)

            paid = uow.ledger.balance_cents(account.id)
            if paid > 0:
                uow.ledger.append(
                    LedgerEntry.new(
                        account_id=account.id,
                        entry_type=EntryType.PAYOUT,
                        amount=Money(-paid),
                        deposit_delta=Money(0),
                        created_at=now,
                        session_id=session_id,
                        operation_id=f"payout:{account.id}",
                    )
                )
            uow.accounts.close(account.id, now)
            uow.audit.append(
                occurred_at=now,
                action="payout",
                account_id=account.id,
                outcome=PayoutOutcome.COMPLETED,
                detail=f"paid_cents={paid};cancelled_cards={len(active)}",
            )
            uow.audit.append(
                occurred_at=now,
                action="account_close",
                account_id=account.id,
                outcome=PayoutOutcome.COMPLETED,
            )
            uow.commit()

        logger.info(
            "payout_completed",
            extra={
                "session_id": session_id,
                "flow": FLOW_NAME,
                "account_id": account_id,
                "amount_cents": paid,
            },
        )
        return PayoutReceipt(
            reference=session_id[:8].upper(),
            account_id=account_id,
            paid_cents=paid,
            cancelled_cards=len(active),
            closed_at=now,
        )

    def _summary(self, uow: UnitOfWork, account_id: int) -> AccountSummary:
        account = uow.accounts.get(account_id)
        cards = uow.cards.list_for_account(account_id)
        active = sum(1 for card in cards if card.status is CardStatus.ACTIVE)
        recycled = sum(1 for card in cards if card.status is CardStatus.RECYCLED)
        cancelled = sum(1 for card in cards if card.status is CardStatus.CANCELLED)
        return AccountSummary(
            account_id=account.id,
            is_closed=account.closed_at is not None,
            balance_cents=uow.ledger.balance_cents(account.id),
            deposit_cents=uow.ledger.deposit_cents(account.id),
            active_cards=active,
            recycled_cards=recycled,
            cancelled_cards=cancelled,
            open_deposit_cents=active * self._deposit.cents,
        )

    def _open_account(self, uow: UnitOfWork, account_id: int) -> Account:
        account = uow.accounts.get(account_id)
        if account.closed_at is not None:
            raise AccountClosedError(f"account {account_id} is already closed")
        return account

    def _cancel_card(
        self, uow: UnitOfWork, session_id: str, card: Card, now: datetime
    ) -> None:
        uow.cards.update(card.cancel(now))
        uow.ledger.append(
            LedgerEntry.new(
                account_id=card.account_id,
                entry_type=EntryType.CARD_CANCEL,
                amount=Money(0),
                deposit_delta=Money(0),
                created_at=now,
                session_id=session_id,
                operation_id=f"card_cancel:{card.id}",
                card_id=card.id,
            )
        )
        uow.audit.append(
            occurred_at=now,
            action="card_cancel",
            account_id=card.account_id,
            outcome=PayoutOutcome.COMPLETED,
        )


__all__ = [
    "AccountSummary",
    "AdminPayoutService",
    "PayoutConfirmation",
    "PayoutOutcome",
    "PayoutReceipt",
]
