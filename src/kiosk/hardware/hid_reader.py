"""USB-HID keyboard-emulation ID reader.

The reader types the card identifier followed by a terminator. This module
only parses the character stream. It takes a byte source as input, so tests
can run without a device. Raw identifiers are never logged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from kiosk.domain.errors import (
    HardwareTimeoutError,
    PortLostError,
    ProtocolError,
)
from kiosk.domain.identity import MAX_ID_LENGTH

logger = logging.getLogger("kiosk.hardware.hid_reader")

ByteSource = Callable[[], bytes]
"""Returns the next chunk of bytes; empty bytes means no data right now."""

TERMINATORS = (ord("\r"), ord("\n"))
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_LENGTH = MAX_ID_LENGTH


class HidIdReader:
    """Read one identifier from a keyboard-emulating reader.

    Args:
        source: Callable that returns the next available bytes.
        clock: Monotonic clock in seconds, injected for deterministic tests.
        sleep: Pause function used between empty reads.
        timeout_s: Maximum time to wait for a complete identifier.
        max_length: Maximum accepted identifier length; longer input is rejected.
    """

    def __init__(
        self,
        source: ByteSource,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_length: int = DEFAULT_MAX_LENGTH,
    ) -> None:
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if not 1 <= max_length <= MAX_ID_LENGTH:
            raise ValueError(f"max_length must be between 1 and {MAX_ID_LENGTH}")
        self._source = source
        self._clock = clock
        self._sleep = sleep
        self._timeout_s = timeout_s
        self._max_length = max_length

    def read_id(self) -> str:
        """Return the identifier typed before the next terminator.

        Returns:
            The identifier as typed. Normalization happens in the domain layer.

        Raises:
            HardwareTimeoutError: If no terminator arrives in time.
            ProtocolError: If the input is longer than ``max_length``.
            PortLostError: If the source fails.
        """
        deadline = self._clock() + self._timeout_s
        buffer = bytearray()
        while True:
            try:
                chunk = self._source()
            except OSError as exc:
                logger.error("id_reader_lost", extra={"error_code": "PORT_LOST"})
                raise PortLostError("id reader is not available") from exc
            for byte in chunk:
                if byte in TERMINATORS:
                    if not buffer:
                        continue
                    return _decode(bytes(buffer))
                if len(buffer) >= self._max_length:
                    logger.warning(
                        "id_reader_input_rejected",
                        extra={"error_code": "PROTOCOL_ERROR"},
                    )
                    raise ProtocolError("id input is too long")
                buffer.append(byte)
            if self._clock() >= deadline:
                logger.warning("id_reader_timeout", extra={"error_code": "HW_TIMEOUT"})
                raise HardwareTimeoutError("no id received before timeout")
            if not chunk:
                self._sleep(0.02)


def _decode(data: bytes) -> str:
    try:
        return data.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ProtocolError("id input is not ASCII") from exc
