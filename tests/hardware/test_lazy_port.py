"""Tests for the lazy serial port: nothing is opened before first use."""

from __future__ import annotations

import pytest

from kiosk.domain.errors import PortLostError
from kiosk.hardware.serial_port import LazySerialPort


class FakeSerial:
    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data)

    def read(self, size: int) -> bytes:
        return b""

    def reset_input_buffer(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_construction_does_not_open_the_port() -> None:
    opened: list[str] = []

    def _open(path: str) -> FakeSerial:
        opened.append(path)
        return FakeSerial()

    LazySerialPort("/dev/serial/by-id/test", _open)

    assert opened == []


def test_first_use_opens_the_port_once() -> None:
    opened: list[str] = []
    link = FakeSerial()

    def _open(path: str) -> FakeSerial:
        opened.append(path)
        return link

    port = LazySerialPort("/dev/serial/by-id/test", _open)
    port.write(b"x")
    port.write(b"y")

    assert opened == ["/dev/serial/by-id/test"]
    assert link.written == [b"x", b"y"]


def test_failed_open_raises_port_lost_and_retries_next_time() -> None:
    attempts: list[int] = []

    def _open(path: str) -> FakeSerial:
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("no such device")
        return FakeSerial()

    port = LazySerialPort("/dev/serial/by-id/test", _open)

    with pytest.raises(PortLostError):
        port.write(b"x")
    port.write(b"x")

    assert len(attempts) == 2


def test_close_closes_an_open_link_and_allows_reopen() -> None:
    links: list[FakeSerial] = []

    def _open(path: str) -> FakeSerial:
        link = FakeSerial()
        links.append(link)
        return link

    port = LazySerialPort("/dev/serial/by-id/test", _open)
    port.write(b"x")
    port.close()
    port.write(b"y")

    assert links[0].closed is True
    assert len(links) == 2


class BufferedSerial(FakeSerial):
    def __init__(self, pending: bytes) -> None:
        super().__init__()
        self._pending = pending
        self.read_sizes: list[int] = []

    @property
    def in_waiting(self) -> int:
        return len(self._pending)

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        chunk, self._pending = self._pending[:size], self._pending[size:]
        return chunk


def test_read_available_returns_empty_without_blocking_when_nothing_waits() -> None:
    link = BufferedSerial(b"")
    port = LazySerialPort("/dev/serial/by-id/test", lambda _p: link)

    assert port.read_available() == b""
    assert link.read_sizes == []


def test_read_available_returns_only_buffered_bytes() -> None:
    link = BufferedSerial(b"EM4100 0A1B2C3D4E")
    port = LazySerialPort("/dev/serial/by-id/test", lambda _p: link)

    assert port.read_available() == b"EM4100 0A1B2C3D4E"
    assert link.read_sizes == [len(b"EM4100 0A1B2C3D4E")]
