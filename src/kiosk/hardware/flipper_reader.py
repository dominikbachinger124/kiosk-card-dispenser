"""ID reader adapter for a Flipper Zero, driven over its serial CLI.

The Flipper runs ``rfid read``, which blocks until a card is found or the
Ctrl-C is sent. This adapter parses only the card identifier line and,
when a card is found, signals it with the device vibration motor.

Raw identifiers are never logged, and the parsed value never leaves this
module except as the return value of ``read_id``.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Protocol

from kiosk.domain.errors import (
    HardwareTimeoutError,
    PortLostError,
    ProtocolError,
    ReadCancelledError,
)

logger = logging.getLogger("kiosk.hardware.flipper_reader")

DEFAULT_TIMEOUT_S = 5.0
CTRL_C = b"\x03"
_ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")
_EM4100 = re.compile(rb"EM4100\s+([0-9A-F]{10})")


class SerialLink(Protocol):
    """Minimal serial interface, so tests can use a fake."""

    def write(self, data: bytes) -> int: ...
    def read_available(self) -> bytes: ...
    def reset_input(self) -> None: ...
    def close(self) -> None: ...


class FlipperIdReader:
    """Read one 125 kHz card identifier from a Flipper Zero.

    Args:
        open_link: Factory that opens the serial link. Injected for tests.
        clock: Monotonic time in seconds.
        sleep: Pause function between polls.
        timeout_s: Maximum time to wait for a card. Default 5 seconds.
    """

    def __init__(
        self,
        open_link: Callable[[], SerialLink],
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._open = open_link
        self._clock = clock
        self._sleep = sleep
        self._timeout_s = timeout_s

    def read_id(self, cancel: threading.Event | None = None) -> str:
        """Wait for one card and return its identifier.

        Args:
            cancel: Optional event. When set, the read stops early, the CLI is
                interrupted and the port is closed. No signal is sent.

        Returns:
            Upper-case hexadecimal card identifier.

        Raises:
            PortLostError: If the serial port cannot be opened or breaks.
            HardwareTimeoutError: If no card appears within the timeout.
            ProtocolError: If the device answers with an unexpected format.
            ReadCancelledError: If ``cancel`` was set before a card was found.
        """
        link = self._open_link()
        try:
            link.reset_input()
            link.write(b"rfid read\r\n")
            found = self._wait_for_card(link, cancel)
            self._stop(link)
            if found is None:
                raise HardwareTimeoutError("no card within timeout")
            self._signal(link)
            return found
        finally:
            link.close()

    def _open_link(self) -> SerialLink:
        try:
            return self._open()
        except OSError as exc:
            raise PortLostError("flipper serial port unavailable") from exc

    def _wait_for_card(
        self, link: SerialLink, cancel: threading.Event | None
    ) -> str | None:
        buffer = b""
        deadline = self._clock() + self._timeout_s
        while self._clock() < deadline:
            if cancel is not None and cancel.is_set():
                self._stop(link)
                raise ReadCancelledError("card read cancelled")
            try:
                chunk = link.read_available()
            except OSError as exc:
                raise PortLostError("flipper serial port lost") from exc
            buffer += chunk
            match = _EM4100.search(_ANSI.sub(b"", buffer))
            if match:
                return match.group(1).decode("ascii")
            if len(buffer) > 4096:
                raise ProtocolError("unexpected device output")
            self._sleep(0.1)
        return None

    def _stop(self, link: SerialLink) -> None:
        try:
            link.write(CTRL_C)
        except OSError as exc:
            raise PortLostError("flipper serial port lost") from exc

    def _signal(self, link: SerialLink) -> None:
        # Short vibration confirms a found card. No sound: the CLI has no audio command.
        try:
            link.write(b"vibro 1\r\n")
            self._sleep(0.2)
            link.write(b"vibro 0\r\n")
        except OSError:
            logger.warning("flipper_signal_failed", extra={"error_code": "PORT_LOST"})


__all__ = ["DEFAULT_TIMEOUT_S", "FlipperIdReader", "SerialLink"]
