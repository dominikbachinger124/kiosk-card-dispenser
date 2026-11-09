"""Composition root: builds the application from configuration.

This is the only module that knows concrete adapters. Services receive their
dependencies through the constructor. Nothing here opens a serial port:
hardware adapters are created with lazy factories, so a missing device is
reported at the first real operation (fail closed), not at startup.

The card-ID salt comes from the environment, never from the repository.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kiosk.config import KioskConfig, load_config
from kiosk.domain.clock import Clock, SystemClock
from kiosk.domain.errors import ConfigError
from kiosk.domain.identity import MIN_SALT_BYTES, CardIdHasher
from kiosk.domain.money import Money
from kiosk.hardware.coordinated import CoordinatedDispenser
from kiosk.hardware.coordinator import HardwareCoordinator
from kiosk.hardware.flipper_reader import FlipperIdReader
from kiosk.hardware.k720 import K720Dispenser
from kiosk.hardware.serial_port import LazySerialPort, open_pyserial
from kiosk.services.admin_auth import AdminAuthService, AdminCredentials
from kiosk.services.admin_payout import AdminPayoutService
from kiosk.services.admin_session import AdminSessionGuard
from kiosk.services.customer_flows import CustomerFlows
from kiosk.services.faults import FaultService
from kiosk.services.forgotten_card import ForgottenCardService
from kiosk.services.forgotten_watch import ForgottenWatch
from kiosk.services.issue_card import IssueCardService
from kiosk.services.topup import TopUpService
from kiosk.storage.database import connect, migrate
from kiosk.storage.unit_of_work import UnitOfWorkFactory

SALT_ENV = "KIOSK_ID_HASH_SALT"
DEFAULT_DB_PATH = Path("~/.local/share/kiosk/kiosk.db")
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@dataclass(frozen=True, slots=True)
class KioskApp:
    """Wired services for one kiosk process.

    Attributes:
        config: Validated configuration.
        applied_migrations: Migration names applied by this start.
        issue: Issue flow for new and additional cards.
        topup: Fixed top-up flow for existing accounts.
        faults: Device fault recording and admin acknowledgement.
        admin_auth: Admin login with card and PIN, or None while the admin
            configuration is incomplete. Admin stays locked in that case.
        admin_payout: Admin cash payout for the last card.
        admin_session: Idle-timeout tracking for admin sessions.
        customer: Customer actions (new card, top-up) for the main window.
        watch: Background watch for cards left at the exit after an issue.
    """

    config: KioskConfig
    applied_migrations: list[str]
    issue: IssueCardService
    id_reader: FlipperIdReader
    coordinator: HardwareCoordinator
    topup: TopUpService
    faults: FaultService
    admin_auth: AdminAuthService | None
    admin_payout: AdminPayoutService
    admin_session: AdminSessionGuard
    customer: CustomerFlows
    watch: ForgottenWatch


def read_salt(environ: dict[str, str] | None = None) -> bytes:
    """Read the card-ID salt from the environment.

    Args:
        environ: Mapping to read from. Defaults to ``os.environ``.

    Returns:
        The salt as bytes. The value itself is never logged.

    Raises:
        ConfigError: If the variable is missing or shorter than the minimum.
    """
    source = os.environ if environ is None else environ
    value = source.get(SALT_ENV, "")
    if not value:
        raise ConfigError(f"{SALT_ENV} is not set")
    salt = value.encode("utf-8")
    if len(salt) < MIN_SALT_BYTES:
        raise ConfigError(f"{SALT_ENV} must contain at least {MIN_SALT_BYTES} bytes")
    return salt


def build_app(
    config_path: Path,
    *,
    db_path: Path | None = None,
    clock: Clock | None = None,
    open_serial: Callable[[str], Any] | None = None,
) -> KioskApp:
    """Validate configuration, prepare the database and wire the services.

    Args:
        config_path: Location of the TOML configuration.
        db_path: Database file. Defaults to ``~/.local/share/kiosk/kiosk.db``.
        clock: Time source. Defaults to the system clock.
        open_serial: Opener for a serial device path. Defaults to pyserial.
            Stored in lazy ports; never called at startup.

    Returns:
        The wired application.

    Raises:
        ConfigError: If configuration or salt is invalid.
        MigrationError: If a migration fails.
    """
    config = load_config(config_path)
    salt = read_salt()

    resolved_db = (db_path or DEFAULT_DB_PATH).expanduser()
    _prepare_database_dir(resolved_db.parent)
    applied = _migrate(resolved_db)

    clock_impl: Clock = clock or SystemClock()
    uow = UnitOfWorkFactory(resolved_db)
    hasher = CardIdHasher(salt=salt)

    money = config.money
    topup = Money(money.topup_cents)
    deposit = Money(money.deposit_cents)
    collection = Money(money.gatekeeper_collection_cents)
    if topup.cents + deposit.cents != collection.cents:
        raise ConfigError(
            "money.gatekeeper_collection_cents must equal topup_cents + deposit_cents"
        )

    opener = open_serial or open_pyserial
    k720_port = LazySerialPort(config.hardware.k720_port, opener)
    flipper_port = LazySerialPort(config.hardware.flipper_port, opener)
    raw_dispenser = K720Dispenser(k720_port, clock=time.monotonic, sleep=time.sleep)
    coordinator = HardwareCoordinator(raw_dispenser)
    dispenser = CoordinatedDispenser(raw_dispenser, coordinator)
    id_reader = FlipperIdReader(lambda: flipper_port)

    admin_session = AdminSessionGuard(clock_impl)
    faults = FaultService(uow, clock_impl, admin_session)
    issue = IssueCardService(
        dispenser,
        uow,
        hasher,
        faults,
        clock_impl,
        topup=topup,
        deposit=deposit,
        collection=collection,
    )
    # Admin is optional at startup. AdminCredentials refuses an incomplete
    # setup; in that case the admin login is simply not offered and the
    # customer flows keep running (fail closed for admin, not for the kiosk).
    admin_auth: AdminAuthService | None = None
    if config.admin.admin_uids and config.admin.pin_hash:
        credentials = AdminCredentials(
            admin_uid_hashes=tuple(
                hasher.hash_uid(uid) for uid in config.admin.admin_uids
            ),
            pin_hash=config.admin.pin_hash,
        )
        admin_auth = AdminAuthService(credentials, hasher, uow, clock_impl)
    admin_payout = AdminPayoutService(uow, clock_impl, deposit=deposit)
    top_up = TopUpService(uow, clock_impl, topup=topup)
    # The watch uses the coordinated dispenser, so its movement is serialized
    # with polling and the customer flows.
    forgotten = ForgottenCardService(
        dispenser,
        uow,
        hasher,
        clock_impl,
        deposit=deposit,
        sleep=time.sleep,
    )
    watch = ForgottenWatch(forgotten)
    customer = CustomerFlows(
        reader=id_reader,
        issue=issue,
        topup=top_up,
        hasher=hasher,
        watch=watch,
        db=uow,
    )

    return KioskApp(
        config=config,
        applied_migrations=applied,
        issue=issue,
        id_reader=id_reader,
        coordinator=coordinator,
        topup=top_up,
        faults=faults,
        admin_auth=admin_auth,
        admin_payout=admin_payout,
        admin_session=admin_session,
        customer=customer,
        watch=watch,
    )


def _prepare_database_dir(directory: Path) -> None:
    """Create the data directory with owner-only permissions."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)


def _migrate(db_path: Path) -> list[str]:
    """Open the database, apply pending migrations and restrict file mode."""
    conn = connect(db_path)
    try:
        applied = migrate(conn, MIGRATIONS_DIR)
    finally:
        conn.close()
    os.chmod(db_path, 0o600)
    return applied


__all__ = ["KioskApp", "SALT_ENV", "build_app", "read_salt"]
