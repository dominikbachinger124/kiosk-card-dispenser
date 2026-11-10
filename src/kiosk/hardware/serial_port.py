"""Serial link that opens its device only on first use.

Startup must not touch hardware. ``LazySerialPort`` defers the open call to
the first read or write. If the open fails, it raises ``PortLostError`` and
the next call tries again. This keeps a missing device a visible runtime
fault instead of a startup crash that hides the rest of the kiosk.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from typing import Any, Protocol

from kiosk.domain.errors import PortLostError

SERIAL_LINK_DEFAULTS: dict[str, Any] = {
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 0.2,
}


class _Link(Protocol):
    def write(self, data: bytes) -> int: ...
    def read(self, size: int) -> bytes: ...
    def reset_input_buffer(self) -> None: ...
    def close(self) -> None: ...


class LazySerialPort:
    """Open-on-first-use wrapper around a serial link.

    Args:
        path: Device path, preferably ``/dev/serial/by-id/...``.
        open_link: Factory that opens the link for ``path``. Production code
            passes a pyserial opener; tests pass a fake.
    """

    def __init__(self, path: str, open_link: Callable[[str], _Link]) -> None:
        self._path = path
        self._open_link = open_link
        self._link: _Link | None = None
        self._lock = threading.Lock()

    def write(self, data: bytes) -> int:
        link = self._current()
        try:
            return link.write(data)
        except OSError as exc:
            self._drop(link)
            raise PortLostError("serial port lost") from exc

    def read(self, size: int) -> bytes:
        link = self._current()
        try:
            return link.read(size)
        except OSError as exc:
            self._drop(link)
            raise PortLostError("serial port lost") from exc

    def reset_input_buffer(self) -> None:
        self._current().reset_input_buffer()

    def reset_input(self) -> None:
        """Alias for the Flipper adapter, which names the call differently."""
        self.reset_input_buffer()

    def read_available(self) -> bytes:
        """Return whatever is buffered now, without blocking.

        The Flipper adapter polls this in a loop. A blocking read would stall
        the poll and the timeout logic above it.
        """
        link = self._current()
        waiting = getattr(link, "in_waiting", 0)
        if not waiting:
            return b""
        return link.read(int(waiting))

    def close(self) -> None:
        with self._lock:
            if self._link is not None:
                self._link.close()
                self._link = None

    def _current(self) -> _Link:
        with self._lock:
            if self._link is None:
                try:
                    self._link = self._open_link(self._path)
                except OSError as exc:
                    raise PortLostError("serial port unavailable") from exc
            return self._link

    def _drop(self, failed: _Link) -> None:
        """Forget a link that failed, so the next access reopens the port.

        A cable pulled during operation leaves a dead handle behind. Without this
        reset every later access would fail on the same handle forever.
        """
        with self._lock:
            if self._link is failed:
                self._link = None
        with contextlib.suppress(OSError):
            failed.close()


def open_pyserial(path: str) -> _Link:
    """Open a real pyserial port with the defaults for the K720 (9600 8N1)."""
    import serial  # imported here so tests never need the device stack

    return serial.Serial(path, **SERIAL_LINK_DEFAULTS)  # type: ignore[no-any-return]


__all__ = ["LazySerialPort", "SERIAL_LINK_DEFAULTS", "open_pyserial"]
