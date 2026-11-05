"""AdminViewModel state transitions, localization and money formatting.

No Qt is needed here: the ViewModel is plain Python and is driven by services
over a real migrated database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from kiosk.domain.entities import Session
from kiosk.domain.errors import AdminSessionExpiredError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.ledger import EntryType, LedgerEntry
from kiosk.domain.money import Money
from kiosk.domain.pin import hash_pin, new_salt
from kiosk.gui.admin_viewmodel import AdminViewModel, format_cents
from kiosk.services.admin_auth import AdminAuthService, AdminCredentials
from kiosk.services.admin_payout import AdminPayoutService, PayoutConfirmation
from kiosk.services.admin_session import AdminSessionGuard
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT

ADMIN_UID = "AD01AD01"
CARD_UID = "8388B21A"
PIN = "4711"
HASHER = CardIdHasher(TEST_SALT)
DEPOSIT = Money(500)
CONFIRMED = PayoutConfirmation(
    cash_handed_over=True, open_cards_acknowledged=True, final_confirmed=True
)


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def viewmodel(uow_factory: UnitOfWorkFactory, clock: MutableClock) -> AdminViewModel:
    credentials = AdminCredentials(
        admin_uid_hashes=(HASHER.hash_uid(ADMIN_UID),),
        pin_hash=hash_pin(PIN, new_salt()),
    )
    return AdminViewModel(
        AdminAuthService(credentials, HASHER, uow_factory, clock),
        AdminPayoutService(uow_factory, clock, deposit=DEPOSIT),
        AdminSessionGuard(clock, idle_timeout=timedelta(seconds=120)),
        clock,
    )


@pytest.fixture
def account_id(uow_factory: UnitOfWorkFactory, now: datetime) -> int:
    with uow_factory.begin() as uow:
        account = uow.accounts.add(HASHER.hash_uid(CARD_UID), now)
        card = uow.cards.add(HASHER.hash_uid(CARD_UID), account.id, now)
        uow.sessions.add(Session(id="issue", flow="issue", started_at=now))
        uow.ledger.append(
            LedgerEntry.new(
                account_id=account.id,
                entry_type=EntryType.CASH_IN_TOPUP,
                amount=Money(2000),
                deposit_delta=Money(0),
                created_at=now,
                session_id="issue",
                operation_id="issue-topup",
                card_id=card.id,
            )
        )
        uow.commit()
    return account.id


# -- money formatting ----------------------------------------------------


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (0, "0,00 EUR"),
        (5, "0,05 EUR"),
        (2000, "20,00 EUR"),
        (1234, "12,34 EUR"),
        (-150, "-1,50 EUR"),
    ],
)
def test_money_is_formatted_from_integer_cents(cents: int, text: str) -> None:
    assert format_cents(cents) == text


def test_money_formatting_rejects_float() -> None:
    with pytest.raises(TypeError):
        format_cents(20.0)  # type: ignore[arg-type]


# -- login ---------------------------------------------------------------


def test_correct_login_opens_panel(viewmodel: AdminViewModel) -> None:
    assert viewmodel.login(ADMIN_UID, PIN) is True
    assert viewmodel.is_logged_in is True
    assert viewmodel.message == ""


def test_wrong_pin_shows_generic_message(viewmodel: AdminViewModel) -> None:
    assert viewmodel.login(ADMIN_UID, "0000") is False

    assert viewmodel.is_logged_in is False
    assert viewmodel.message == "Anmeldung fehlgeschlagen."
    assert PIN not in viewmodel.message


def test_lockout_message_is_shown(viewmodel: AdminViewModel) -> None:
    for _ in range(5):
        viewmodel.login(ADMIN_UID, "0000")

    assert viewmodel.login(ADMIN_UID, PIN) is False
    assert viewmodel.message == "Anmeldung vorübergehend gesperrt."


def test_english_login_message(
    uow_factory: UnitOfWorkFactory, clock: MutableClock
) -> None:
    credentials = AdminCredentials(
        admin_uid_hashes=(HASHER.hash_uid(ADMIN_UID),),
        pin_hash=hash_pin(PIN, new_salt()),
    )
    vm = AdminViewModel(
        AdminAuthService(credentials, HASHER, uow_factory, clock),
        AdminPayoutService(uow_factory, clock, deposit=DEPOSIT),
        AdminSessionGuard(clock),
        clock,
        language="en",
    )

    vm.login(ADMIN_UID, "0000")

    assert vm.message == "Login failed."


# -- session and timeout -------------------------------------------------


def test_timeout_ends_session_and_requires_new_login(
    viewmodel: AdminViewModel, clock: MutableClock, now: datetime
) -> None:
    viewmodel.login(ADMIN_UID, PIN)

    clock.current = now + timedelta(seconds=120)

    assert viewmodel.is_logged_in is False
    assert viewmodel.message == "Sitzung wegen Inaktivität beendet."


def test_activity_keeps_session_alive(
    viewmodel: AdminViewModel, clock: MutableClock, now: datetime, account_id: int
) -> None:
    viewmodel.login(ADMIN_UID, PIN)
    clock.current = now + timedelta(seconds=100)
    viewmodel.accounts()
    clock.current = now + timedelta(seconds=200)

    assert viewmodel.is_logged_in is True


def test_data_access_after_timeout_is_refused(
    viewmodel: AdminViewModel, clock: MutableClock, now: datetime, account_id: int
) -> None:
    viewmodel.login(ADMIN_UID, PIN)
    clock.current = now + timedelta(seconds=500)

    with pytest.raises(AdminSessionExpiredError):
        viewmodel.accounts()
    assert viewmodel.message == "Sitzung wegen Inaktivität beendet."


def test_data_access_without_login_is_refused(
    viewmodel: AdminViewModel, account_id: int
) -> None:
    with pytest.raises(AdminSessionExpiredError):
        viewmodel.accounts()


def test_logout_clears_session(viewmodel: AdminViewModel, account_id: int) -> None:
    viewmodel.login(ADMIN_UID, PIN)

    viewmodel.logout()

    assert viewmodel.is_logged_in is False
    with pytest.raises(AdminSessionExpiredError):
        viewmodel.accounts()


def test_logout_without_login_is_safe(viewmodel: AdminViewModel) -> None:
    viewmodel.logout()

    assert viewmodel.is_logged_in is False


# -- accounts and payout -------------------------------------------------


def test_account_rows_show_status_and_balance(
    viewmodel: AdminViewModel, account_id: int
) -> None:
    viewmodel.login(ADMIN_UID, PIN)

    rows = viewmodel.accounts()

    assert len(rows) == 1
    assert rows[0].account_id == account_id
    assert rows[0].status_text == "offen"
    assert rows[0].balance_text == "20,00 EUR"


def test_detail_fields_are_localized_and_formatted(
    viewmodel: AdminViewModel, account_id: int
) -> None:
    viewmodel.login(ADMIN_UID, PIN)
    summary = viewmodel.account_detail(account_id)

    fields = viewmodel.detail_text(summary)

    assert fields["Guthaben"] == "20,00 EUR"
    assert fields["Offener Pfandbetrag"] == "5,00 EUR"
    assert fields["Ausgegebene Karten"] == "1"


def test_payout_returns_reference_and_closes_account(
    viewmodel: AdminViewModel, account_id: int
) -> None:
    viewmodel.login(ADMIN_UID, PIN)

    reference = viewmodel.payout(account_id, CONFIRMED)

    assert reference
    assert viewmodel.message.startswith("Auszahlung abgeschlossen. Beleg: ")
    assert viewmodel.accounts()[0].status_text == "geschlossen"


def test_rejected_payout_reports_error_and_changes_nothing(
    viewmodel: AdminViewModel, account_id: int
) -> None:
    viewmodel.login(ADMIN_UID, PIN)
    missing = PayoutConfirmation(
        cash_handed_over=False, open_cards_acknowledged=True, final_confirmed=True
    )

    assert viewmodel.payout(account_id, missing) is None
    assert viewmodel.message == "Bitte alle Bestätigungen setzen."
    assert viewmodel.account_detail(account_id).is_closed is False


def test_payout_twice_is_refused_and_no_second_booking(
    viewmodel: AdminViewModel, account_id: int, uow_factory: UnitOfWorkFactory
) -> None:
    viewmodel.login(ADMIN_UID, PIN)
    viewmodel.payout(account_id, CONFIRMED)

    assert viewmodel.payout(account_id, CONFIRMED) is None
    assert viewmodel.message == "Dieses Konto ist geschlossen."
    with uow_factory.begin() as uow:
        payouts = [
            e
            for e in uow.ledger.list_for_account(account_id)
            if e.entry_type is EntryType.PAYOUT
        ]
    assert len(payouts) == 1
