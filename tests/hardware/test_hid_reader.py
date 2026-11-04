"""HID reader: buffer limit, timeout, terminators, and no identifier leakage."""

from __future__ import annotations

import logging

import pytest

from kiosk.domain.errors import HardwareTimeoutError, PortLostError, ProtocolError
from kiosk.hardware.hid_reader import HidIdReader


class Script:
    """Byte source that returns queued chunks, then empty reads."""

    def __init__(self, *chunks: bytes | OSError) -> None:
        self._chunks = list(chunks)

    def __call__(self) -> bytes:
        if not self._chunks:
            return b""
        item = self._chunks.pop(0)
        if isinstance(item, OSError):
            raise item
        return item


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _reader(source: Script, clock: FakeClock, **kwargs: object) -> HidIdReader:
    return HidIdReader(source, clock=clock.clock, sleep=clock.sleep, **kwargs)  # type: ignore[arg-type]


def test_reads_identifier_up_to_carriage_return() -> None:
    clock = FakeClock()

    assert _reader(Script(b"8388B21A\r"), clock).read_id() == "8388B21A"


def test_identifier_split_over_several_chunks_is_joined() -> None:
    clock = FakeClock()

    assert _reader(Script(b"83", b"88", b"B21A\n"), clock).read_id() == "8388B21A"


def test_leading_terminators_are_ignored() -> None:
    clock = FakeClock()

    assert _reader(Script(b"\r\n8388B21A\r"), clock).read_id() == "8388B21A"


def test_overlong_input_is_rejected_without_echoing_it() -> None:
    clock = FakeClock()
    reader = _reader(Script(b"A" * 40 + b"\r"), clock, max_length=32)

    with pytest.raises(ProtocolError) as info:
        reader.read_id()

    assert "A" * 5 not in info.value.message


def test_no_terminator_within_timeout_raises_timeout() -> None:
    clock = FakeClock()
    reader = _reader(Script(b"8388"), clock, timeout_s=1.0)

    with pytest.raises(HardwareTimeoutError):
        reader.read_id()


def test_source_failure_becomes_port_lost() -> None:
    clock = FakeClock()
    reader = _reader(Script(OSError("unplugged")), clock)

    with pytest.raises(PortLostError):
        reader.read_id()


def test_non_ascii_input_is_rejected() -> None:
    clock = FakeClock()

    with pytest.raises(ProtocolError, match="ASCII"):
        _reader(Script(b"\xff\xfe\r"), clock).read_id()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timeout_s": 0}, "timeout_s"),
        ({"max_length": 0}, "max_length"),
        ({"max_length": 33}, "max_length"),
    ],
)
def test_invalid_limits_are_rejected(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        HidIdReader(Script(), **kwargs)  # type: ignore[arg-type]


def test_identifier_never_appears_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    clock = FakeClock()
    caplog.set_level(logging.DEBUG)

    _reader(Script(b"8388B21A\r"), clock).read_id()
    with pytest.raises(ProtocolError):
        _reader(Script(b"CAFEBABE" * 5 + b"\r"), clock, max_length=32).read_id()

    text = "\n".join(
        record.getMessage() + str(record.__dict__) for record in caplog.records
    )
    assert "8388B21A" not in text
    assert "CAFEBABE" not in text
