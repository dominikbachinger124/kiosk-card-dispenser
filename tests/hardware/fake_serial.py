"""Scripted serial link that simulates a K720 for driver tests.

The link answers each host write with the bytes queued for it. An ACK is
queued before every frame. Status answers come from a status script, so tests
can model sensor changes over time.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from kiosk.hardware.k720_frame import ACK, encode_frame


def status_frame(raw: int, address: int = 0) -> bytes:
    """Return a complete ``AP`` answer frame carrying status ``raw``."""
    return encode_frame(address, b"SF" + f"{raw:04X}".encode("ascii"))


def uid_frame(uid: bytes, address: int = 0) -> bytes:
    """Return a complete ``0x3B 0x31`` answer frame carrying ``P;1`` + UID bytes."""
    return encode_frame(address, b"P;1" + uid)


def search_ok_frame(address: int = 0) -> bytes:
    """Return a complete ``0x3B 0x30`` success answer frame."""
    return encode_frame(address, b"P;0")


@dataclass
class ScriptedLink:
    """Serial link double. Writes are recorded, reads come from ``responses``.

    Attributes:
        responses: Byte strings returned by ``read`` in order.
        writes: Every chunk written by the driver, in order.
        closed: Whether ``close`` was called.
        fail_write: If True, ``write`` raises ``OSError`` (port gone).
    """

    responses: deque[bytes] = field(default_factory=deque)
    writes: list[bytes] = field(default_factory=list)
    closed: bool = False
    fail_write: bool = False
    _pending: bytearray = field(default_factory=bytearray)

    def queue(self, *chunks: bytes) -> None:
        self.responses.extend(chunks)

    def write(self, data: bytes) -> int:
        if self.fail_write:
            raise OSError("port gone")
        self.writes.append(bytes(data))
        return len(data)

    def read(self, size: int) -> bytes:
        if not self._pending and self.responses:
            self._pending.extend(self.responses.popleft())
        if not self._pending:
            return b""
        chunk = bytes(self._pending[:size])
        del self._pending[:size]
        return chunk

    def reset_input_buffer(self) -> None:
        self._pending.clear()

    def close(self) -> None:
        self.closed = True


def handshake(answer_frame: bytes | None = None) -> list[bytes]:
    """Return the device side of one command: ACK, then optional answer frame."""
    chunks = [bytes([ACK, ord("0"), ord("0")])]
    if answer_frame is not None:
        chunks.append(answer_frame)
    return chunks
