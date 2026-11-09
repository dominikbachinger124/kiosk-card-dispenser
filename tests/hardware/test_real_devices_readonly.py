"""Read-only checks against the real K720 and Flipper Zero.

Run only on demand with ``uv run pytest -m hardware`` on this file.
Both devices must be connected. The K720 is queried with the documented status
command ``AP`` only. No movement, no card output and no FC0 are sent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kiosk.config import load_config
from kiosk.hardware.coordinator import HardwareCoordinator
from kiosk.hardware.flipper_reader import FlipperIdReader
from kiosk.hardware.k720 import K720Dispenser
from kiosk.hardware.serial_port import LazySerialPort, open_pyserial

CONFIG = Path(__file__).resolve().parents[2] / "config.toml"


@pytest.mark.hardware
def test_k720_status_is_readable_without_movement() -> None:
    """Query the status word once. Nothing is moved and no card is issued."""
    config = load_config(CONFIG)
    port = LazySerialPort(config.hardware.k720_port, open_pyserial)
    dispenser = K720Dispenser(port)
    state = HardwareCoordinator(dispenser).run(lambda d: d.poll_state())
    assert state is not None


@pytest.mark.hardware
def test_flipper_reader_returns_card_identifier_in_hex_format() -> None:
    """A card on the Flipper is read and returned as hexadecimal identifier.

    The test checks only the format. The identifier itself is never printed,
    asserted against a fixed value, or written to logs.
    """
    config = load_config(CONFIG)
    port = LazySerialPort(config.hardware.flipper_port, open_pyserial)
    reader = FlipperIdReader(lambda: port, timeout_s=8)
    identifier = reader.read_id()
    assert re.fullmatch(r"[0-9A-F]{10}", identifier), "unexpected identifier format"
