"""K720 frame encoding, decoding, and status parsing.

Implements the frame layout and status bits from ``docs/k720_protocol.md``.
This module performs no IO. It only converts bytes and checks them.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce

from kiosk.domain.errors import ProtocolError

STX = 0x02
ETX = 0x03
ACK = 0x06
NAK = 0x15
ENQ = 0x05

MAX_ADDRESS = 15

# Status bits from docs/k720_protocol.md, section 6.
BIT_SENSOR_USER = 0x0001
BIT_SENSOR_READ = 0x0002
BIT_SENSOR_STACK = 0x0004
BIT_STOCK_EMPTY = 0x0008
BIT_STOCK_LOW = 0x0010
BIT_CARD_STUCK = 0x0020
BIT_CARD_OVERLAP = 0x0040
BIT_NO_CAPTURE = 0x0080
BIT_RECORD_ERROR = 0x0100
BIT_DISPENSE_ERROR = 0x0200
BIT_PREPARING = 0x1000
BIT_COMMAND_REJECTED = 0x4000

# Bits that stop the flow before a command is sent (section 9, step 1).
# Overlap (0x0040) is not listed: it is only transient evidence of a possible
# jam and is judged by the driver after a settle window (protocol 10.1).
BLOCKING_BITS = (
    BIT_DISPENSE_ERROR,
    BIT_RECORD_ERROR,
    BIT_CARD_STUCK,
    BIT_STOCK_EMPTY,
)


def xor_checksum(data: bytes) -> int:
    """Return the BCC: XOR over all given bytes."""
    return reduce(lambda acc, byte: acc ^ byte, data, 0)


def encode_frame(address: int, payload: bytes) -> bytes:
    """Build a complete frame: STX, address, length, payload, ETX, BCC.

    Args:
        address: Device address, 0..15, sent as two ASCII digits.
        payload: Command code and parameters.

    Returns:
        Frame bytes ready for the serial port.

    Raises:
        ProtocolError: If the address is out of range or the payload is too long.
    """
    if not 0 <= address <= MAX_ADDRESS:
        raise ProtocolError(f"device address out of range: {address}")
    if len(payload) > 0xFFFF:
        raise ProtocolError("payload too long for a 16-bit length field")
    body = (
        bytes([STX])
        + f"{address:02d}".encode("ascii")
        + len(payload).to_bytes(2, "big")
        + payload
        + bytes([ETX])
    )
    return body + bytes([xor_checksum(body)])


def decode_frame(frame: bytes) -> bytes:
    """Validate a response frame and return its payload.

    Args:
        frame: Complete frame including BCC.

    Returns:
        The payload bytes.

    Raises:
        ProtocolError: On wrong framing, length, or checksum.
    """
    if len(frame) < 7 or frame[0] != STX:
        raise ProtocolError("frame does not start with STX")
    length = int.from_bytes(frame[3:5], "big")
    if len(frame) != 5 + length + 2:
        raise ProtocolError("frame length does not match the length field")
    if frame[5 + length] != ETX:
        raise ProtocolError("frame does not end with ETX")
    if xor_checksum(frame[:-1]) != frame[-1]:
        raise ProtocolError("BCC checksum mismatch")
    return frame[5 : 5 + length]


@dataclass(frozen=True, slots=True)
class DeviceStatus:
    """Decoded 16-bit status word from ``AP``.

    Attributes:
        raw: The full status word.
    """

    raw: int

    @property
    def user_exit_occupied(self) -> bool:
        return bool(self.raw & BIT_SENSOR_USER)

    @property
    def read_position_occupied(self) -> bool:
        return bool(self.raw & BIT_SENSOR_READ)

    @property
    def stack_occupied(self) -> bool:
        return bool(self.raw & BIT_SENSOR_STACK)

    @property
    def stock_empty(self) -> bool:
        return bool(self.raw & BIT_STOCK_EMPTY)

    @property
    def stock_low(self) -> bool:
        return bool(self.raw & BIT_STOCK_LOW)

    @property
    def command_rejected(self) -> bool:
        return bool(self.raw & BIT_COMMAND_REJECTED)

    @property
    def preparing(self) -> bool:
        return bool(self.raw & BIT_PREPARING)

    def blocking_bits_set(self) -> bool:
        """Return True if any bit that forbids a new command is set."""
        return any(self.raw & bit for bit in BLOCKING_BITS)

    def jam_by_sensors(self) -> bool:
        """Return True if the sensor pattern is a jam (protocol section 10.1).

        Stack and read position together (S+L) is a jam. So is all three
        sensors together (U+L+S). The status bits alone do not show a jam
        reliably, so the sensor pattern is checked as well.
        """
        stack_and_read = self.stack_occupied and self.read_position_occupied
        return stack_and_read or self.raw & 0x0007 == 0x0007


def parse_status_payload(payload: bytes) -> DeviceStatus:
    """Parse the answer to ``AP``: ``SF`` followed by four hex digits.

    Raises:
        ProtocolError: If the answer does not have the expected form.
    """
    if len(payload) != 6 or not payload.startswith(b"SF"):
        raise ProtocolError("unexpected status payload")
    try:
        raw = int(payload[2:].decode("ascii"), 16)
    except ValueError as exc:
        raise ProtocolError("status is not hexadecimal") from exc
    return DeviceStatus(raw)
