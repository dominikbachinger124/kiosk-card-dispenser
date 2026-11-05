"""FlipperIdReader over a fake serial link. No device is needed."""

from __future__ import annotations

import pytest

from kiosk.domain.errors import HardwareTimeoutError, PortLostError, ProtocolError
from kiosk.hardware.flipper_reader import FlipperIdReader


class FakeLink:
    """Serial link that replays scripted device output and records writes."""

    def __init__(self, chunks: list[bytes], *, fail_read: bool = False) -> None:
        self._chunks = list(chunks)
        self._fail_read = fail_read
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def read_available(self) -> bytes:
        if self._fail_read:
            raise OSError("port gone")
        return self._chunks.pop(0) if self._chunks else b""

    def reset_input(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeClock:
    """Advances by a fixed step each time it is read, so loops terminate."""

    def __init__(self, step: float = 0.5) -> None:
        self._now = 0.0
        self._step = step

    def __call__(self) -> float:
        self._now += self._step
        return self._now


def _reader(link: FakeLink, *, timeout_s: float = 5.0) -> FlipperIdReader:
    return FlipperIdReader(
        lambda: link,
        clock=FakeClock(),
        sleep=lambda _s: None,
        timeout_s=timeout_s,
    )


def test_card_found_returns_identifier_and_stops_reader() -> None:
    link = FakeLink([b"Reading RFID...\r\nEM4100 2A00CC99ED\r\n"])

    assert _reader(link).read_id() == "2A00CC99ED"
    assert b"\x03" in link.writes
    assert link.closed is True


def test_ansi_escape_sequences_are_ignored() -> None:
    link = FakeLink([b"\x1b[0mEM4100 \x1b[1m2A00CC99ED\x1b[0m\r\n"])

    assert _reader(link).read_id() == "2A00CC99ED"


def test_identifier_split_across_reads_is_joined() -> None:
    link = FakeLink([b"EM4100 2A00", b"CC99ED\r\n"])

    assert _reader(link).read_id() == "2A00CC99ED"


def test_card_found_triggers_vibration() -> None:
    link = FakeLink([b"EM4100 2A00CC99ED\r\n"])

    _reader(link).read_id()

    assert b"vibro 1\r\n" in link.writes
    assert b"vibro 0\r\n" in link.writes


def test_no_card_within_timeout_raises_and_closes_port() -> None:
    link = FakeLink([b"Reading RFID...\r\n"] * 100)

    with pytest.raises(HardwareTimeoutError):
        _reader(link, timeout_s=2.0).read_id()
    assert link.closed is True
    assert b"vibro 1\r\n" not in link.writes


def test_default_timeout_is_five_seconds() -> None:
    link = FakeLink([b""] * 100)
    reader = FlipperIdReader(lambda: link, clock=FakeClock(0.5), sleep=lambda _s: None)

    with pytest.raises(HardwareTimeoutError):
        reader.read_id()

    # FakeClock advances 0.5 per read; a 5 s deadline allows at most about 10 polls.
    assert link.writes.count(b"\x03") == 1


def test_port_that_cannot_be_opened_raises_port_lost() -> None:
    def broken() -> FakeLink:
        raise OSError("no such device")

    reader = FlipperIdReader(broken, clock=FakeClock(), sleep=lambda _s: None)

    with pytest.raises(PortLostError):
        reader.read_id()


def test_port_lost_during_read_raises_and_closes() -> None:
    link = FakeLink([], fail_read=True)

    with pytest.raises(PortLostError):
        _reader(link).read_id()
    assert link.closed is True


def test_unbounded_garbage_output_is_a_protocol_error() -> None:
    link = FakeLink([b"x" * 5000])

    with pytest.raises(ProtocolError):
        _reader(link).read_id()


def test_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(ValueError):
        FlipperIdReader(lambda: FakeLink([]), timeout_s=0)
