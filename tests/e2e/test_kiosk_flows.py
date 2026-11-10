"""End-to-end flows through the real composition root, with fake hardware.

``build_app`` wires the real services, the real database and the real
coordinator. Only the card dispenser and the ID reader are test fakes, passed
in by the test. Fakes never reach the production start path.

Covered: issue (new card), top-up, balance, recycling refund, admin payout,
and the polling detection of a card at the exit.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from kiosk.bootstrap import SALT_ENV, build_app
from kiosk.domain.errors import HardwareTimeoutError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.money import Money
from kiosk.services.forgotten_card import ForgottenCardOutcome, ForgottenCardService
from kiosk.storage.database import connect
from tests.conftest import VALID_CONFIG_TOML
from tests.hardware.fakes import FakeDispenser, FakeIdReader

CUSTOMER_UID = "AABBCCDD"
E2E_SALT = "x" * 32
# Must match the salt the bootstrap reads from the environment (see the salt fixture).
HASHER = CardIdHasher(E2E_SALT.encode("utf-8"))


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")
    return path


@pytest.fixture
def salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SALT_ENV, E2E_SALT)


def _app(
    config_path: Path,
    db_path: Path,
    dispenser: FakeDispenser,
    reader: FakeIdReader,
) -> object:
    return build_app(
        config_path,
        db_path=db_path,
        dispenser=dispenser,
        id_reader=reader,
    )


def _balances(db_path: Path) -> dict[str, int]:
    """Sum of ledger cents per account, read straight from the database."""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT account_id, SUM(amount_cents) AS bal, "
            "SUM(deposit_delta_cents) AS dep FROM ledger GROUP BY account_id"
        ).fetchall()
    finally:
        conn.close()
    return {f"{r[0]}": r[1] for r in rows} | {"deposit_total": sum(r[2] for r in rows)}


def _count(db_path: Path, table: str) -> int:
    conn = connect(db_path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def test_new_card_books_topup_and_deposit(
    config_path: Path, tmp_path: Path, salt: None
) -> None:
    db = tmp_path / "kiosk.db"
    dispenser = FakeDispenser(uid="8388B21A")
    reader = FakeIdReader(responses=[CUSTOMER_UID])
    app = _app(config_path, db, dispenser, reader)

    assert app.customer.start_issue() == "issued"  # type: ignore[attr-defined]

    assert _count(db, "cards") == 1
    totals = _balances(db)
    assert totals["deposit_total"] == 500
    assert sum(v for k, v in totals.items() if k != "deposit_total") == 2000


def test_topup_for_known_account_adds_2000_cent(
    config_path: Path, tmp_path: Path, salt: None
) -> None:
    db = tmp_path / "kiosk.db"
    dispenser = FakeDispenser()
    app = _app(
        config_path,
        db,
        dispenser,
        FakeIdReader(responses=[CUSTOMER_UID, CUSTOMER_UID]),
    )
    app.customer.start_issue()  # type: ignore[attr-defined]
    # The customer takes the issued card from the exit before the next flow.
    dispenser.exit_occupied = False
    before = sum(v for k, v in _balances(db).items() if k != "deposit_total")

    assert app.customer.start_topup() == "topped_up"  # type: ignore[attr-defined]

    after = sum(v for k, v in _balances(db).items() if k != "deposit_total")
    assert after - before == 2000


def test_topup_unknown_customer_books_nothing(
    config_path: Path, tmp_path: Path, salt: None
) -> None:
    db = tmp_path / "kiosk.db"
    app = _app(config_path, db, FakeDispenser(), FakeIdReader(responses=[CUSTOMER_UID]))

    assert app.customer.start_topup() == "unknown_account"  # type: ignore[attr-defined]
    assert _count(db, "ledger") == 0


def test_issue_without_customer_read_dispenses_nothing(
    config_path: Path, tmp_path: Path, salt: None
) -> None:
    db = tmp_path / "kiosk.db"
    dispenser = FakeDispenser()
    reader = FakeIdReader(responses=[HardwareTimeoutError("no card")])
    app = _app(config_path, db, dispenser, reader)

    assert app.customer.start_issue() == "aborted"  # type: ignore[attr-defined]
    # Only the exit check runs before the read; no movement is commanded.
    assert "issue_card" not in dispenser.calls
    assert "move_card_to_read_position" not in dispenser.calls
    assert _count(db, "ledger") == 0


def test_recycled_forgotten_card_refunds_deposit_to_balance(
    config_path: Path, tmp_path: Path, salt: None
) -> None:
    """A forgotten card is recycled and its 500 cent Pfand moves to Guthaben."""
    db = tmp_path / "kiosk.db"
    dispenser = FakeDispenser(uid="8388B21A")
    app = _app(config_path, db, dispenser, FakeIdReader(responses=[CUSTOMER_UID]))
    app.customer.start_issue()  # type: ignore[attr-defined]

    conn = connect(db)
    try:
        card_id = conn.execute("SELECT id FROM cards").fetchone()[0]
    finally:
        conn.close()
    with app.uow.begin() as uow:  # type: ignore[attr-defined]
        card = uow.cards.get(card_id)

    # The card is still at the exit after the wait: the watch recycles it.
    # The wait is skipped here; the real 45 s timer is covered elsewhere.
    dispenser.exit_occupied = True
    no_wait = ForgottenCardService(
        dispenser,
        app.uow,  # type: ignore[attr-defined]
        HASHER,
        FixedClock(),
        deposit=Money(500),
        sleep=lambda _: None,
    )
    outcome = no_wait.watch(card)

    assert outcome is ForgottenCardOutcome.RECYCLED
    assert _count(db, "ledger") == 3  # topup, deposit, recycle_refund


def test_admin_payout_pays_balance_and_closes_account(
    config_path: Path, tmp_path: Path, salt: None
) -> None:
    """Payout zeroes the balance, closes the account and books one payout entry."""
    from kiosk.services.admin_payout import PayoutConfirmation

    db = tmp_path / "kiosk.db"
    app = _app(config_path, db, FakeDispenser(), FakeIdReader(responses=[CUSTOMER_UID]))
    app.customer.start_issue()  # type: ignore[attr-defined]

    conn = connect(db)
    try:
        account_id = conn.execute("SELECT id FROM accounts").fetchone()[0]
    finally:
        conn.close()

    receipt = app.admin_payout.payout(  # type: ignore[attr-defined]
        account_id,
        PayoutConfirmation(
            cash_handed_over=True,
            open_cards_acknowledged=True,
            final_confirmed=True,
        ),
    )

    # Only the Guthaben is paid out. The open Pfand of the unrecycled card stays
    # unpaid, so the payout is exactly the 2000 cent balance.
    assert receipt.paid_cents == 2000
    assert receipt.account_id == account_id
    conn = connect(db)
    try:
        closed = conn.execute(
            "SELECT closed_at FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert closed is not None


def test_card_at_exit_is_detected_once_on_rising_edge() -> None:
    """The polling detector reports a card once, not on every poll while it waits."""
    from kiosk.hardware.polling import CardInsertionDetector

    detector = CardInsertionDetector()
    readings = [False, True, True, True, False, True]
    fired = [detector.update(r) for r in readings]

    assert fired == [False, True, False, False, False, True]
