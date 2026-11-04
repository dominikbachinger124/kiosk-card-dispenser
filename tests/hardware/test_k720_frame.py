"""Frame encoding, checksum, and status parsing per docs/k720_protocol.md."""

from __future__ import annotations

import pytest

from kiosk.domain.errors import ProtocolError
from kiosk.hardware.k720_frame import (
    BIT_CARD_STUCK,
    BIT_SENSOR_READ,
    BIT_SENSOR_STACK,
    BIT_SENSOR_USER,
    decode_frame,
    encode_frame,
    parse_status_payload,
    xor_checksum,
)


def test_ap_frame_matches_protocol_example() -> None:
    """Section 2: AP at address 0 is 02 30 30 00 02 41 50 03 BCC."""
    frame = encode_frame(0, b"AP")

    assert frame[:8] == bytes([0x02, 0x30, 0x30, 0x00, 0x02, 0x41, 0x50, 0x03])
    assert frame[-1] == xor_checksum(frame[:-1])


def test_length_is_big_endian_two_bytes() -> None:
    payload = b"x" * 0x0102
    frame = encode_frame(3, payload)

    assert frame[3:5] == bytes([0x01, 0x02])


@pytest.mark.parametrize("address", [-1, 16])
def test_address_outside_range_is_rejected(address: int) -> None:
    with pytest.raises(ProtocolError):
        encode_frame(address, b"AP")


def test_address_is_sent_as_two_ascii_digits() -> None:
    frame = encode_frame(12, b"AP")

    assert frame[1:3] == b"12"


def test_decode_returns_payload_of_valid_frame() -> None:
    frame = encode_frame(0, b"SF0014")

    assert decode_frame(frame) == b"SF0014"


def test_decode_rejects_bad_checksum() -> None:
    frame = bytearray(encode_frame(0, b"SF0014"))
    frame[-1] ^= 0xFF

    with pytest.raises(ProtocolError, match="BCC"):
        decode_frame(bytes(frame))


def test_decode_rejects_wrong_length_field() -> None:
    frame = bytearray(encode_frame(0, b"SF0014"))
    frame[4] += 1

    with pytest.raises(ProtocolError):
        decode_frame(bytes(frame))


def test_decode_rejects_missing_stx() -> None:
    frame = bytearray(encode_frame(0, b"SF0014"))
    frame[0] = 0x00

    with pytest.raises(ProtocolError, match="STX"):
        decode_frame(bytes(frame))


def test_status_payload_decodes_sensor_bits() -> None:
    status = parse_status_payload(b"SF0003")

    assert status.user_exit_occupied
    assert status.read_position_occupied
    assert not status.stack_occupied


def test_status_blocking_bits_are_detected() -> None:
    assert parse_status_payload(f"SF{BIT_CARD_STUCK:04X}".encode()).blocking_bits_set()
    assert not parse_status_payload(
        f"SF{BIT_SENSOR_STACK:04X}".encode()
    ).blocking_bits_set()


@pytest.mark.parametrize(
    "payload",
    [b"SF00", b"XX0014", b"SFZZZZ", b""],
)
def test_malformed_status_is_rejected(payload: bytes) -> None:
    with pytest.raises(ProtocolError):
        parse_status_payload(payload)


def test_sensor_bit_constants_match_protocol() -> None:
    assert BIT_SENSOR_USER == 0x0001
    assert BIT_SENSOR_READ == 0x0002
    assert BIT_SENSOR_STACK == 0x0004
