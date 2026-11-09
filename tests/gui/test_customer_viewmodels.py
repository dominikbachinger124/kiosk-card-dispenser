"""Customer flow ViewModels: service results and errors become localized text.

No Qt here. The ViewModels are plain Python so they can be tested without a
display. The Qt signal layer is a thin wrapper and is not tested here.
"""

from __future__ import annotations

from kiosk.domain.errors import CardJammedError, NotFoundError
from kiosk.domain.money import Money
from kiosk.gui.customer_viewmodels import IssueViewModel, TopUpViewModel
from kiosk.services.issue_card import IssueOutcome, IssueResult
from kiosk.services.topup import TopUpOutcome, TopUpResult

CUSTOMER_HASH = "a" * 64


class StubIssue:
    """Stands in for IssueCardService and returns or raises a fixed result."""

    def __init__(self, result: IssueResult | Exception) -> None:
        self._result = result
        self.calls: list[str] = []

    def issue(
        self, *, customer_uid_hash: str, existing_account_id: int | None = None
    ) -> IssueResult:
        self.calls.append(customer_uid_hash)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class StubTopUp:
    def __init__(self, result: TopUpResult | Exception) -> None:
        self._result = result
        self.calls: list[str] = []

    def top_up(self, *, customer_uid_hash: str) -> TopUpResult:
        self.calls.append(customer_uid_hash)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_issue_success_shows_balance_and_deposit_from_cents() -> None:
    service = StubIssue(IssueResult(IssueOutcome.ISSUED, card_id=1, account_id=7))
    vm = IssueViewModel(service, language="de", topup=Money(2000), deposit=Money(500))

    result = vm.start(CUSTOMER_HASH)

    assert result.ok is True
    assert result.text == "Karte ausgegeben. Guthaben 20,00 EUR, Pfand 5,00 EUR."


def test_issue_success_text_english() -> None:
    service = StubIssue(IssueResult(IssueOutcome.ISSUED, card_id=1, account_id=7))
    vm = IssueViewModel(service, language="en", topup=Money(2000), deposit=Money(500))

    assert (
        vm.start(CUSTOMER_HASH).text
        == "Card issued. Balance 20,00 EUR, deposit 5,00 EUR."
    )


def test_empty_stock_shows_staff_notice_and_is_not_ok() -> None:
    service = StubIssue(IssueResult(IssueOutcome.EMPTY, fault_id=3))
    vm = IssueViewModel(service, language="de", topup=Money(2000), deposit=Money(500))

    result = vm.start(CUSTOMER_HASH)

    assert result.ok is False
    assert (
        result.text
        == "Derzeit sind keine Karten verfügbar. Bitte wenden Sie sich an das Personal."
    )


def test_aborted_outcome_shows_jam_notice() -> None:
    service = StubIssue(IssueResult(IssueOutcome.ABORTED, fault_id=4))
    vm = IssueViewModel(service, language="de", topup=Money(2000), deposit=Money(500))

    assert vm.start(CUSTOMER_HASH).ok is False


def test_hardware_error_from_service_maps_to_text_not_raw_message() -> None:
    service = StubIssue(CardJammedError("raw device bytes 0x0006"))
    vm = IssueViewModel(service, language="de", topup=Money(2000), deposit=Money(500))

    result = vm.start(CUSTOMER_HASH)

    assert result.ok is False
    assert "0x0006" not in result.text
    assert "raw device" not in result.text


def test_issue_result_text_never_contains_identifier() -> None:
    service = StubIssue(IssueResult(IssueOutcome.ISSUED, card_id=1, account_id=7))
    vm = IssueViewModel(service, language="de", topup=Money(2000), deposit=Money(500))

    text = vm.start(CUSTOMER_HASH).text

    assert CUSTOMER_HASH not in text
    assert "7" not in text.split()


def test_topup_success_shows_fixed_amount() -> None:
    service = StubTopUp(TopUpResult(TopUpOutcome.TOPPED_UP, account_id=7, entry_id=9))
    vm = TopUpViewModel(service, language="de", topup=Money(2000))

    result = vm.start(CUSTOMER_HASH)

    assert result.ok is True
    assert result.text == "Konto aufgeladen. Guthaben plus 20,00 EUR."


def test_topup_unknown_account_shows_hint_and_is_not_ok() -> None:
    vm = TopUpViewModel(
        StubTopUp(NotFoundError("no account")), language="de", topup=Money(2000)
    )

    result = vm.start(CUSTOMER_HASH)

    assert result.ok is False
    assert (
        result.text == "Für diesen Ausweis gibt es kein Konto. Bitte Personal fragen."
    )
