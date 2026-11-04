"""Load and validate the non-secret kiosk configuration from TOML.

Money values are validated as integer cents; floats are rejected so that
amounts can never drift through binary floating point arithmetic.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kiosk.domain.errors import ConfigError

_OPERATING_MODE = "real"


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Application-level settings.

    Attributes:
        language: UI language code, ``"de"`` or ``"en"``.
        mode: Operating mode; only ``"real"`` is allowed in production.
        cooldown_hours: Hours between two card issues for the same ID.
        cooldown_enforced: Whether the cooldown blocks issuing (demo: False).
    """

    language: str
    mode: str
    cooldown_hours: int
    cooldown_enforced: bool


@dataclass(frozen=True, slots=True)
class MoneyConfig:
    """Monetary amounts in integer cents.

    Attributes:
        topup_cents: Credit added to the balance per card issue.
        deposit_cents: Deposit (Pfand) per card issue.
        gatekeeper_collection_cents: Cash the gatekeeper collects per issue.
        default_payment_cents: Default demo payment amount.
    """

    topup_cents: int
    deposit_cents: int
    gatekeeper_collection_cents: int
    default_payment_cents: int


@dataclass(frozen=True, slots=True)
class HardwareConfig:
    """Hardware settings. No protocol parameters are guessed here.

    Attributes:
        mode: Operating mode; only ``"real"`` is allowed.
        k720_port: Serial device path, preferably ``/dev/serial/by-id/...``.
        serial_baudrate: Baud rate from the verified vendor protocol.
        id_reader_device: USB-HID reader device or ``"auto"``.
    """

    mode: str
    k720_port: str
    serial_baudrate: int
    id_reader_device: str


@dataclass(frozen=True, slots=True)
class PrivacyConfig:
    """Pointer to the hash salt. The salt itself is never stored in config.

    Attributes:
        id_hash_salt_env: Name of the environment variable holding the salt.
    """

    id_hash_salt_env: str


@dataclass(frozen=True, slots=True)
class KioskConfig:
    """Complete validated configuration."""

    app: AppConfig
    money: MoneyConfig
    hardware: HardwareConfig
    privacy: PrivacyConfig


def load_config(path: Path) -> KioskConfig:
    """Read and validate a TOML configuration file.

    Args:
        path: Location of the TOML file.

    Returns:
        A fully validated, immutable configuration.

    Raises:
        ConfigError: If the file is missing, not valid TOML, or violates
            the schema (missing key, wrong type, float money value).
    """
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"config file is not valid TOML: {path}") from exc
    return parse_config(raw)


def parse_config(raw: dict[str, Any]) -> KioskConfig:
    """Validate an already parsed configuration mapping.

    Args:
        raw: Mapping as returned by ``tomllib``.

    Returns:
        A validated configuration.

    Raises:
        ConfigError: On any schema violation.
    """
    app = _section(raw, "app")
    money = _section(raw, "money")
    hardware = _section(raw, "hardware")
    privacy = _section(raw, "privacy")

    config = KioskConfig(
        app=AppConfig(
            language=_choice(app, "app", "language", ("de", "en")),
            mode=_choice(app, "app", "mode", (_OPERATING_MODE,)),
            cooldown_hours=_positive_int(app, "app", "cooldown_hours"),
            cooldown_enforced=_bool(app, "app", "cooldown_enforced"),
        ),
        money=MoneyConfig(
            topup_cents=_cents(money, "money", "topup_cents"),
            deposit_cents=_cents(money, "money", "deposit_cents"),
            gatekeeper_collection_cents=_cents(
                money, "money", "gatekeeper_collection_cents"
            ),
            default_payment_cents=_cents(money, "money", "default_payment_cents"),
        ),
        hardware=HardwareConfig(
            mode=_choice(hardware, "hardware", "mode", (_OPERATING_MODE,)),
            k720_port=_non_empty_str(hardware, "hardware", "k720_port"),
            serial_baudrate=_non_negative_int(hardware, "hardware", "serial_baudrate"),
            id_reader_device=_non_empty_str(hardware, "hardware", "id_reader_device"),
        ),
        privacy=PrivacyConfig(
            id_hash_salt_env=_non_empty_str(privacy, "privacy", "id_hash_salt_env"),
        ),
    )
    if config.money.gatekeeper_collection_cents < config.money.topup_cents:
        raise ConfigError(
            "money.gatekeeper_collection_cents must not be below money.topup_cents"
        )
    return config


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    value = raw.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"missing config section: [{name}]")
    return value


def _require(section: dict[str, Any], section_name: str, key: str) -> Any:
    if key not in section:
        raise ConfigError(f"missing config key: {section_name}.{key}")
    return section[key]


def _choice(
    section: dict[str, Any], section_name: str, key: str, allowed: tuple[str, ...]
) -> str:
    value = _require(section, section_name, key)
    if not isinstance(value, str) or value not in allowed:
        raise ConfigError(
            f"{section_name}.{key} must be one of {allowed}, got {value!r}"
        )
    return value


def _non_empty_str(section: dict[str, Any], section_name: str, key: str) -> str:
    value = _require(section, section_name, key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section_name}.{key} must be a non-empty string")
    return value


def _bool(section: dict[str, Any], section_name: str, key: str) -> bool:
    value = _require(section, section_name, key)
    if not isinstance(value, bool):
        raise ConfigError(f"{section_name}.{key} must be a boolean")
    return value


def _cents(section: dict[str, Any], section_name: str, key: str) -> int:
    """Read a money value that must be a positive integer number of cents."""
    value = _require(section, section_name, key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(
            f"{section_name}.{key} must be an integer number of cents, "
            f"got {type(value).__name__}"
        )
    if value <= 0:
        raise ConfigError(f"{section_name}.{key} must be positive")
    return value


def _positive_int(section: dict[str, Any], section_name: str, key: str) -> int:
    value = _require(section, section_name, key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{section_name}.{key} must be a positive integer")
    return value


def _non_negative_int(section: dict[str, Any], section_name: str, key: str) -> int:
    value = _require(section, section_name, key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"{section_name}.{key} must be a non-negative integer")
    return value
