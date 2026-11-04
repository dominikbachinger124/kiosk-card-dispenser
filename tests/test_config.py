"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from kiosk.config import load_config, parse_config
from kiosk.errors import ConfigError


def _raw(**overrides: object) -> dict[str, dict[str, object]]:
    """Return a valid raw mapping, with optional per-key overrides in [money]."""
    raw: dict[str, dict[str, object]] = {
        "app": {
            "language": "de",
            "mode": "real",
            "cooldown_hours": 24,
            "cooldown_enforced": False,
        },
        "money": {
            "topup_cents": 2000,
            "deposit_cents": 500,
            "gatekeeper_collection_cents": 2500,
            "default_payment_cents": 200,
        },
        "hardware": {
            "mode": "real",
            "k720_port": "/dev/serial/by-id/test-device",
            "serial_baudrate": 9600,
            "id_reader_device": "auto",
        },
        "privacy": {"id_hash_salt_env": "KIOSK_ID_HASH_SALT"},
    }
    raw["money"].update(overrides)
    return raw


def test_valid_file_loads(valid_config_path: Path) -> None:
    config = load_config(valid_config_path)

    assert config.app.language == "de"
    assert config.app.cooldown_hours == 24
    assert config.app.cooldown_enforced is False
    assert config.privacy.id_hash_salt_env == "KIOSK_ID_HASH_SALT"


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("topup_cents", 2000),
        ("deposit_cents", 500),
        ("gatekeeper_collection_cents", 2500),
        ("default_payment_cents", 200),
    ],
)
def test_money_values_are_integer_cents(
    valid_config_path: Path, key: str, expected: int
) -> None:
    value = getattr(load_config(valid_config_path).money, key)

    assert value == expected
    assert type(value) is int


@pytest.mark.parametrize("bad_value", [20.0, 2000.5, "2000", True])
def test_money_rejects_non_integer_values(bad_value: object) -> None:
    with pytest.raises(ConfigError, match="integer number of cents"):
        parse_config(_raw(topup_cents=bad_value))


def test_money_rejects_non_positive_values() -> None:
    with pytest.raises(ConfigError, match="must be positive"):
        parse_config(_raw(deposit_cents=0))


def test_missing_section_is_reported() -> None:
    raw = _raw()
    del raw["hardware"]

    with pytest.raises(ConfigError, match=r"\[hardware\]"):
        parse_config(raw)


def test_missing_key_is_reported() -> None:
    raw = _raw()
    del raw["money"]["topup_cents"]

    with pytest.raises(ConfigError, match=r"money\.topup_cents"):
        parse_config(raw)


def test_fake_mode_is_rejected() -> None:
    raw = _raw()
    raw["hardware"]["mode"] = "fake"

    with pytest.raises(ConfigError, match="hardware.mode"):
        parse_config(raw)


def test_gatekeeper_collection_must_cover_topup() -> None:
    with pytest.raises(ConfigError, match="gatekeeper_collection_cents"):
        parse_config(_raw(gatekeeper_collection_cents=1000))


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "does-not-exist.toml")


def test_invalid_toml_raises_config_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("[app\nlanguage = ", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid TOML"):
        load_config(path)


def test_repository_config_is_valid() -> None:
    """The versioned config.toml must itself pass validation.

    The K720 port and baud rate are placeholders until the device is wired up;
    the baud rate must not be guessed, so only the schema is checked here.
    """
    repo_config = Path(__file__).resolve().parents[1] / "config.toml"

    config = load_config(repo_config)

    assert config.money.topup_cents == 2000
    assert config.money.deposit_cents == 500
    assert config.money.gatekeeper_collection_cents == 2500
    assert config.app.cooldown_hours == 24
    assert config.app.cooldown_enforced is False
