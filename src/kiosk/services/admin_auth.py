"""Admin login: admin card UID plus PIN, with a lockout after failed attempts.

Both factors must match. A failed attempt never reveals which factor was
wrong. Every attempt is written to the admin audit without the UID and
without the PIN. The failure count lives in the database, so a restart
does not reset the lockout.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from kiosk.domain.clock import Clock
from kiosk.domain.errors import AdminAuthError, AdminLockedError, InvalidCardIdError
from kiosk.domain.identity import CardIdHasher
from kiosk.domain.pin import verify_pin
from kiosk.storage.unit_of_work import UnitOfWorkFactory

logger = logging.getLogger("kiosk.services.admin_auth")

FLOW_NAME = "admin_login"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_WINDOW = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class AdminCredentials:
    """Configured admin secrets. Loaded from local config, never committed.

    Attributes:
        admin_uid_hashes: Salted hashes of one or two admin card UIDs.
        pin_hash: Encoded scrypt hash of the admin PIN.
    """

    admin_uid_hashes: tuple[str, ...]
    pin_hash: str

    def __post_init__(self) -> None:
        if not 1 <= len(self.admin_uid_hashes) <= 2:
            raise ValueError("configure one or two admin card UIDs")


@dataclass(frozen=True, slots=True)
class AdminSession:
    """Proof of a successful admin login for the duration of one panel session.

    Attributes:
        session_id: Technical session identifier. Not derived from any secret.
        opened_at: Login time, UTC.
    """

    session_id: str
    opened_at: datetime


class AdminAuthService:
    """Authenticate an admin with card and PIN.

    Args:
        credentials: Configured admin card hashes and PIN hash.
        hasher: Salted UID hasher, used to hash the presented admin card.
        uow_factory: Transaction factory for the audit trail.
        clock: Time source.
    """

    def __init__(
        self,
        credentials: AdminCredentials,
        hasher: CardIdHasher,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._credentials = credentials
        self._hasher = hasher
        self._uow_factory = uow_factory
        self._clock = clock

    def login(self, raw_admin_uid: str, pin: str) -> AdminSession:
        """Verify admin card and PIN and open an admin session.

        Args:
            raw_admin_uid: UID read from the presented card. Never logged.
            pin: PIN entered on the touch screen. Never logged or stored.

        Returns:
            An admin session on success.

        Raises:
            AdminLockedError: If too many attempts failed recently. No check
                is performed while locked.
            AdminAuthError: On any wrong factor. The message is generic.
        """
        now = self._clock.now()
        session_id = uuid.uuid4().hex
        if self._is_locked(now):
            self._audit(now, "failed", "locked")
            logger.warning(
                "admin_login_locked",
                extra={
                    "session_id": session_id,
                    "flow": FLOW_NAME,
                    "error_code": "ADMIN_LOCKED",
                },
            )
            raise AdminLockedError("admin login is temporarily locked")

        if self._matches(raw_admin_uid, pin):
            self._audit(now, "succeeded", None)
            logger.info(
                "admin_login_succeeded",
                extra={"session_id": session_id, "flow": FLOW_NAME},
            )
            return AdminSession(session_id=session_id, opened_at=now)

        self._audit(now, "failed", "credentials")
        logger.warning(
            "admin_login_failed",
            extra={
                "session_id": session_id,
                "flow": FLOW_NAME,
                "error_code": "ADMIN_AUTH_FAILED",
            },
        )
        raise AdminAuthError("admin login failed")

    def _matches(self, raw_admin_uid: str, pin: str) -> bool:
        # Both checks always run, so the timing does not reveal which one failed.
        uid_ok = self._uid_ok(raw_admin_uid)
        pin_ok = verify_pin(pin, self._credentials.pin_hash)
        return uid_ok and pin_ok

    def _uid_ok(self, raw_admin_uid: str) -> bool:
        try:
            candidate = self._hasher.hash_uid(raw_admin_uid)
        except InvalidCardIdError:
            return False
        return candidate in self._credentials.admin_uid_hashes

    def _is_locked(self, now: datetime) -> bool:
        with self._uow_factory.begin() as uow:
            failures = uow.audit.count_failed_logins(now - LOCKOUT_WINDOW)
        return failures >= MAX_FAILED_ATTEMPTS

    def _audit(self, now: datetime, outcome: str, detail: str | None) -> None:
        # Stores no UID, no PIN, no hash. Only the outcome and a generic reason.
        with self._uow_factory.begin() as uow:
            uow.audit.append(
                occurred_at=now,
                action="admin_login",
                outcome=outcome,
                detail=detail,
            )
            uow.commit()


__all__ = ["AdminAuthService", "AdminCredentials", "AdminSession"]
