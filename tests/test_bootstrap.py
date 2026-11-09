"""Tests for the composition root: config, salt, database, services.

No test here opens a serial port. Hardware adapters are only constructed with
lazy factories, so the bootstrap can run without any device attached.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from kiosk.bootstrap import SALT_ENV, build_app, read_salt
from kiosk.domain.errors import ConfigError
from tests.conftest import VALID_CONFIG_TOML

SALT_VALUE = "x" * 32


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")
    return path


def test_missing_salt_env_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(SALT_ENV, raising=False)

    with pytest.raises(ConfigError, match=SALT_ENV):
        read_salt()


def test_short_salt_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SALT_ENV, "short")

    with pytest.raises(ConfigError, match="at least"):
        read_salt()


def test_salt_is_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SALT_ENV, SALT_VALUE)

    assert read_salt() == SALT_VALUE.encode("ascii")


def test_missing_salt_aborts_before_database_is_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(SALT_ENV, raising=False)
    db_path = tmp_path / "kiosk.db"

    with pytest.raises(ConfigError):
        build_app(_config(tmp_path), db_path=db_path)

    assert not db_path.exists()


def test_build_creates_database_with_private_permissions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SALT_ENV, SALT_VALUE)
    db_dir = tmp_path / "data"
    db_path = db_dir / "kiosk.db"

    build_app(_config(tmp_path), db_path=db_path)

    assert db_path.exists()
    assert stat.S_IMODE(os.stat(db_dir).st_mode) == 0o700
    assert stat.S_IMODE(os.stat(db_path).st_mode) == 0o600


def test_build_applies_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SALT_ENV, SALT_VALUE)
    db_path = tmp_path / "kiosk.db"

    app = build_app(_config(tmp_path), db_path=db_path)

    assert app.applied_migrations == [
        "0001_initial.sql",
        "0002_device_fault.sql",
        "0003_device_fault_context.sql",
    ]


def test_second_build_applies_no_migrations_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SALT_ENV, SALT_VALUE)
    db_path = tmp_path / "kiosk.db"
    build_app(_config(tmp_path), db_path=db_path)

    app = build_app(_config(tmp_path), db_path=db_path)

    assert app.applied_migrations == []


def test_build_exposes_services_without_opening_hardware(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SALT_ENV, SALT_VALUE)

    app = build_app(_config(tmp_path), db_path=tmp_path / "kiosk.db")

    # The issue flow needs a CardDispenser. That adapter is wired in the next
    # step, so it is explicitly absent here instead of silently faked.
    assert app.issue is None
    assert app.topup is not None
    assert app.faults is not None
    assert app.admin_auth is not None
    assert app.admin_payout is not None
