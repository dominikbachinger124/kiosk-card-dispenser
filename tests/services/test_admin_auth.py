"""AdminAuthService: card plus PIN, lockout, and audit minimisation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kiosk.domain.errors import AdminAuthError, AdminLockedError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.pin import hash_pin, new_salt, verify_pin
from kiosk.services.admin_auth import (
    MAX_FAILED_ATTEMPTS,
    AdminAuthService,
    AdminCredentials,
)
from kiosk.storage.database import connect
from kiosk.storage.unit_of_work import UnitOfWorkFactory
from tests.conftest import TEST_SALT

ADMIN_UID = "AD01AD01"
OTHER_UID = "8388B21A"
PIN = "4711"
HASHER = CardIdHasher(TEST_SALT)
PIN_HASH = hash_pin(PIN, new_salt())


@dataclass
class MutableClock:
    current: datetime

    def now(self) -> datetime:
        return self.current


@pytest.fixture
def clock(now: datetime) -> MutableClock:
    return MutableClock(now)


@pytest.fixture
def auth(uow_factory: UnitOfWorkFactory, clock: MutableClock) -> AdminAuthService:
    credentials = AdminCredentials(
        admin_uid_hashes=(HASHER.hash_uid(ADMIN_UID),),
        pin_hash=PIN_HASH,
    )
    return AdminAuthService(credentials, HASHER, uow_factory, clock)


def test_correct_card_and_pin_opens_session(auth: AdminAuthService) -> None:
    session = auth.login(ADMIN_UID, PIN)

    assert session.session_id
    assert session.opened_at.tzinfo is not None


def test_wrong_pin_is_rejected_with_generic_error(auth: AdminAuthService) -> None:
    with pytest.raises(AdminAuthError) as excinfo:
        auth.login(ADMIN_UID, "0000")

    assert excinfo.value.code == "ADMIN_AUTH_FAILED"
    assert "PIN" not in excinfo.value.message
    assert ADMIN_UID not in excinfo.value.message


def test_wrong_card_is_rejected_even_with_correct_pin(auth: AdminAuthService) -> None:
    with pytest.raises(AdminAuthError):
        auth.login(OTHER_UID, PIN)


def test_malformed_uid_is_rejected_without_crash(auth: AdminAuthService) -> None:
    with pytest.raises(AdminAuthError):
        auth.login("not-hex!", PIN)


def test_lockout_after_max_failed_attempts(auth: AdminAuthService) -> None:
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AdminAuthError):
            auth.login(ADMIN_UID, "0000")

    with pytest.raises(AdminLockedError):
        auth.login(ADMIN_UID, PIN)


def test_lockout_blocks_even_correct_credentials(auth: AdminAuthService) -> None:
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AdminAuthError):
            auth.login(OTHER_UID, PIN)

    with pytest.raises(AdminLockedError):
        auth.login(ADMIN_UID, PIN)


def test_lockout_expires_after_window(
    auth: AdminAuthService, clock: MutableClock
) -> None:
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AdminAuthError):
            auth.login(ADMIN_UID, "0000")

    clock.current = clock.current + timedelta(minutes=16)

    assert auth.login(ADMIN_UID, PIN).session_id


def test_lockout_survives_restart(
    uow_factory: UnitOfWorkFactory, clock: MutableClock
) -> None:
    credentials = AdminCredentials(
        admin_uid_hashes=(HASHER.hash_uid(ADMIN_UID),), pin_hash=PIN_HASH
    )
    first = AdminAuthService(credentials, HASHER, uow_factory, clock)
    for _ in range(MAX_FAILED_ATTEMPTS):
        with pytest.raises(AdminAuthError):
            first.login(ADMIN_UID, "0000")

    restarted = AdminAuthService(credentials, HASHER, uow_factory, clock)

    with pytest.raises(AdminLockedError):
        restarted.login(ADMIN_UID, PIN)


def test_audit_contains_no_uid_pin_or_hash(
    auth: AdminAuthService, db_path: Path
) -> None:
    with pytest.raises(AdminAuthError):
        auth.login(OTHER_UID, "0000")
    auth.login(ADMIN_UID, PIN)

    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT action, outcome, detail FROM admin_audit"
        ).fetchall()
        dump = repr([tuple(row) for row in rows])
    finally:
        conn.close()

    assert [row["outcome"] for row in rows] == ["failed", "succeeded"]
    for forbidden in (OTHER_UID, ADMIN_UID, PIN, "0000", PIN_HASH):
        assert forbidden not in dump


def test_wrong_attempts_are_audited_as_failed(
    auth: AdminAuthService, db_path: Path
) -> None:
    with pytest.raises(AdminAuthError):
        auth.login(ADMIN_UID, "0000")

    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT action, outcome FROM admin_audit").fetchall()
    finally:
        conn.close()
    assert [(r["action"], r["outcome"]) for r in rows] == [("admin_login", "failed")]


def test_pin_hash_roundtrip_and_format() -> None:
    encoded = hash_pin("1234", new_salt())

    assert encoded.startswith("scrypt$")
    assert verify_pin("1234", encoded)
    assert not verify_pin("1235", encoded)
    assert "1234" not in encoded


@pytest.mark.parametrize("bad", ["", "plain", "scrypt$x$8$1$00$00", "md5$1$2$3$4$5"])
def test_malformed_stored_hash_never_matches(bad: str) -> None:
    assert verify_pin("1234", bad) is False


def test_two_admin_cards_are_both_accepted(
    uow_factory: UnitOfWorkFactory, clock: MutableClock
) -> None:
    credentials = AdminCredentials(
        admin_uid_hashes=(HASHER.hash_uid(ADMIN_UID), HASHER.hash_uid("AD02AD02")),
        pin_hash=PIN_HASH,
    )
    service = AdminAuthService(credentials, HASHER, uow_factory, clock)

    assert service.login("AD02AD02", PIN).session_id


def test_more_than_two_admin_cards_are_rejected() -> None:
    with pytest.raises(ValueError):
        AdminCredentials(admin_uid_hashes=("a" * 64, "b" * 64, "c" * 64), pin_hash="x")
