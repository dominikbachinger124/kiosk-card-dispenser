"""Shared pytest fixtures.

The Qt platform is forced to offscreen before any PySide6 import so that
GUI tests run headless and deterministically.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from kiosk.storage.database import connect, migrate  # noqa: E402
from kiosk.storage.unit_of_work import UnitOfWorkFactory  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO_ROOT / "migrations"

TEST_SALT = b"test-salt-0123456789abcdef"

VALID_CONFIG_TOML = """
[app]
language = "de"
mode = "real"

[money]
topup_cents = 2000
deposit_cents = 500
gatekeeper_collection_cents = 2500
default_payment_cents = 200

[hardware]
mode = "real"
k720_port = "/dev/serial/by-id/test-device"
serial_baudrate = 9600
flipper_port = "/dev/serial/by-id/test-flipper"

[privacy]
id_hash_salt_env = "KIOSK_ID_HASH_SALT"

[admin]
admin_uids = ["AD01AD01"]
pin_hash = ""
"""


@pytest.fixture
def valid_config_path(tmp_path: Path) -> Path:
    """Write a valid configuration file and return its path."""
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")
    return path


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """Create a migrated database file in ``tmp_path``.

    WAL does not work with ``:memory:``, so tests always use a real file.
    """
    path = tmp_path / "kiosk.db"
    conn = connect(path)
    try:
        migrate(conn, MIGRATIONS_DIR)
    finally:
        conn.close()
    return path


@pytest.fixture
def uow_factory(db_path: Path) -> UnitOfWorkFactory:
    """Unit-of-work factory over the migrated test database."""
    return UnitOfWorkFactory(db_path)


@pytest.fixture
def now() -> datetime:
    """A fixed UTC timestamp so tests are deterministic."""
    return datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)
