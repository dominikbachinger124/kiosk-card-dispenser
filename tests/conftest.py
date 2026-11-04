"""Shared pytest fixtures.

The Qt platform is forced to offscreen before any PySide6 import so that
GUI tests run headless and deterministically.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

VALID_CONFIG_TOML = """
[app]
language = "de"
mode = "real"
cooldown_hours = 24
cooldown_enforced = false

[money]
topup_cents = 2000
deposit_cents = 500
gatekeeper_collection_cents = 2500
default_payment_cents = 200

[hardware]
mode = "real"
k720_port = "/dev/serial/by-id/test-device"
serial_baudrate = 9600
id_reader_device = "auto"

[privacy]
id_hash_salt_env = "KIOSK_ID_HASH_SALT"
"""


@pytest.fixture
def valid_config_path(tmp_path: Path) -> Path:
    """Write a valid configuration file and return its path."""
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")
    return path
