"""K720 driver tests over a scripted serial link. No device required."""

from __future__ import annotations

import pytest

from kiosk.domain.errors import (
    CardJammedError,
    CardOverlapError,
    DispenserEmptyError,
    DispenserStateError,
    HardwareTimeoutError,
    PortLostError,
    ProtocolError,
)
from kiosk.hardware.k720 import K720Dispenser
from kiosk.hardware.k720_frame import (
    BIT_CARD_OVERLAP,
    BIT_CARD_STUCK,
    BIT_SENSOR_READ,
    BIT_SENSOR_USER,
    BIT_STOCK_EMPTY,
    ENQ,
    encode_frame,
)
from tests.hardware.fake_serial import (
    ScriptedLink,
    handshake,
    search_ok_frame,
    status_frame,
    uid_frame,
)


class FakeClock:
    """Manual clock; ``sleep`` advances it so polling logic stays deterministic."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _driver(link: ScriptedLink, clock: FakeClock) -> K720Dispenser:
    return K720Dispenser(link, clock=clock.clock, sleep=clock.sleep)


def _sent_commands(link: ScriptedLink) -> list[bytes]:
    """Return the payload of every command frame the driver sent, in order.

    ENQ writes are three bytes and start with 0x05, so they are skipped.
    """
    payloads: list[bytes] = []
    for chunk in link.writes:
        if chunk[:1] == bytes([0x02]):
            length = int.from_bytes(chunk[3:5], "big")
            payloads.append(chunk[5 : 5 + length])
    return payloads


# --- handshake -------------------------------------------------------------


def test_every_command_sends_frame_then_enq() -> None:
    link = ScriptedLink()
    clock = FakeClock()
    link.queue(*handshake(status_frame(0x0000)))
    _driver(link, clock).poll_state()

    frame, enq = link.writes[0], link.writes[1]
    assert frame == encode_frame(0, b"AP")
    assert enq == bytes([ENQ, ord("0"), ord("0")])


def test_nak_from_device_is_a_protocol_error() -> None:
    link = ScriptedLink()
    link.queue(bytes([0x15, ord("0"), ord("0")]))

    with pytest.raises(ProtocolError, match="NAK"):
        _driver(link, FakeClock()).poll_state()


def test_missing_ack_is_a_protocol_error() -> None:
    link = ScriptedLink()
    link.queue(bytes([0x99, ord("0"), ord("0")]))

    with pytest.raises(ProtocolError, match="acknowledge"):
        _driver(link, FakeClock()).poll_state()


# --- status polling --------------------------------------------------------


def test_poll_state_returns_decoded_status() -> None:
    link = ScriptedLink()
    link.queue(*handshake(status_frame(BIT_SENSOR_USER)))

    status = _driver(link, FakeClock()).poll_state()

    assert status.user_exit_occupied
    assert not status.read_position_occupied


def test_status_polls_are_spaced_by_at_least_200_ms() -> None:
    link = ScriptedLink()
    clock = FakeClock()
    link.queue(*handshake(status_frame(0)), *handshake(status_frame(0)))
    driver = _driver(link, clock)

    driver.poll_state()
    driver.poll_state()

    assert clock.sleeps and clock.sleeps[0] >= 0.2 - 1e-9


# --- issuing ---------------------------------------------------------------


def test_issue_sends_dc_and_waits_for_user_exit() -> None:
    link = ScriptedLink()
    clock = FakeClock()
    # Pre-check, then DC (handshake only), then two equal reads at the exit.
    link.queue(
        *handshake(status_frame(0)),  # pre-check: stock ok, nothing blocking
        *handshake(),  # DC handshake, no answer frame
        *handshake(status_frame(BIT_SENSOR_USER)),
        *handshake(status_frame(BIT_SENSOR_USER)),
    )

    _driver(link, clock).issue_card()

    assert b"DC" in _sent_commands(link)


def test_issue_with_empty_stock_raises_before_sending_dc() -> None:
    link = ScriptedLink()
    link.queue(*handshake(status_frame(BIT_STOCK_EMPTY)))

    with pytest.raises(DispenserEmptyError):
        _driver(link, FakeClock()).issue_card()

    assert b"DC" not in _sent_commands(link)


def test_jammed_card_stops_the_flow_with_typed_error() -> None:
    link = ScriptedLink()
    link.queue(
        *handshake(status_frame(0)),
        *handshake(),
        *handshake(status_frame(BIT_CARD_STUCK)),
    )

    with pytest.raises(CardJammedError) as info:
        _driver(link, FakeClock()).issue_card()

    assert info.value.code == "CARD_JAMMED"


def test_overlapping_cards_raise_typed_error() -> None:
    link = ScriptedLink()
    link.queue(*handshake(status_frame(BIT_CARD_OVERLAP)))

    with pytest.raises(CardOverlapError):
        _driver(link, FakeClock()).issue_card()


def test_status_that_never_settles_times_out() -> None:
    link = ScriptedLink()
    clock = FakeClock()
    link.queue(
        *handshake(status_frame(0)),
        *handshake(),
        *[chunk for _ in range(200) for chunk in handshake(status_frame(0))],
    )

    with pytest.raises(HardwareTimeoutError):
        _driver(link, clock).issue_card()


# --- reading -----------------------------------------------------------------


def test_read_uid_uses_search_then_uid_command() -> None:
    link = ScriptedLink()
    link.queue(
        *handshake(search_ok_frame()),
        *handshake(uid_frame(bytes([0x83, 0x88, 0xB2, 0x1A]))),
    )

    uid = _driver(link, FakeClock()).read_uid()

    assert uid == "8388B21A"
    assert _sent_commands(link) == [b"\x3b\x30", b"\x3b\x31"]


def test_no_card_at_read_position_is_a_timeout_not_a_uid() -> None:
    link = ScriptedLink()
    link.queue(*handshake(encode_frame(0, b"N;00")))

    with pytest.raises(HardwareTimeoutError):
        _driver(link, FakeClock()).read_uid()


def test_uid_answer_with_wrong_length_is_rejected() -> None:
    link = ScriptedLink()
    link.queue(
        *handshake(search_ok_frame()),
        *handshake(encode_frame(0, b"P;1\x83\x88")),
    )

    with pytest.raises(ProtocolError, match="four bytes"):
        _driver(link, FakeClock()).read_uid()


def test_move_to_read_position_uses_fc7_from_user_exit() -> None:
    link = ScriptedLink()
    link.queue(
        *handshake(status_frame(BIT_SENSOR_USER)),
        *handshake(),
        *handshake(status_frame(BIT_SENSOR_READ | BIT_SENSOR_USER)),
        *handshake(status_frame(BIT_SENSOR_READ | BIT_SENSOR_USER)),
    )

    _driver(link, FakeClock()).move_card_to_read_position()

    assert b"FC7" in _sent_commands(link)


def test_move_to_read_position_without_card_at_exit_is_refused() -> None:
    link = ScriptedLink()
    link.queue(*handshake(status_frame(0)))

    with pytest.raises(DispenserStateError):
        _driver(link, FakeClock()).move_card_to_read_position()

    assert b"FC7" not in _sent_commands(link)


# --- disposal ----------------------------------------------------------------


def test_dispose_uses_cp_and_waits_until_positions_are_empty() -> None:
    link = ScriptedLink()
    link.queue(
        *handshake(status_frame(BIT_SENSOR_READ)),
        *handshake(),
        *handshake(status_frame(0)),
        *handshake(status_frame(0)),
    )

    _driver(link, FakeClock()).dispose_card()

    assert b"CP" in _sent_commands(link)


# --- port and forbidden commands ---------------------------------------------


def test_lost_port_on_write_raises_port_lost() -> None:
    link = ScriptedLink(fail_write=True)

    with pytest.raises(PortLostError):
        _driver(link, FakeClock()).poll_state()


def test_silent_device_times_out_instead_of_hanging() -> None:
    link = ScriptedLink()

    with pytest.raises(HardwareTimeoutError):
        _driver(link, FakeClock()).poll_state()


@pytest.mark.parametrize(
    "forbidden",
    [b"FC0", b"CS0", b"CS1", b"CS2", b"CS3", b"CS4", b"CS5", b"DB"],
)
def test_forbidden_commands_are_never_sent(forbidden: bytes) -> None:
    """FC0 ejects a card into a jam; CS* changes baud and drops the link.

    The driver runs a full scenario and must not emit any of these payloads.
    """
    link = ScriptedLink()
    clock = FakeClock()
    link.queue(
        *handshake(status_frame(BIT_SENSOR_USER)),
        *handshake(),
        *handshake(status_frame(BIT_SENSOR_READ | BIT_SENSOR_USER)),
        *handshake(status_frame(BIT_SENSOR_READ | BIT_SENSOR_USER)),
        *handshake(search_ok_frame()),
        *handshake(uid_frame(bytes([1, 2, 3, 4]))),
        *handshake(),
    )
    driver = _driver(link, clock)
    driver.move_card_to_read_position()
    driver.read_uid()

    assert forbidden not in _sent_commands(link)


def test_nothing_is_sent_after_a_fatal_status() -> None:
    """A blocking status must stop the flow before the next movement command."""
    link = ScriptedLink()
    link.queue(*handshake(status_frame(BIT_CARD_STUCK)))

    with pytest.raises(CardJammedError):
        _driver(link, FakeClock()).issue_card()

    assert _sent_commands(link) == [b"AP"]


def test_enq_follows_every_command_frame() -> None:
    """Section 3: without ENQ the device does not execute the command.

    Every command frame must be directly followed by the exact ENQ write
    ``05 30 30`` for address 0. A missing ENQ fails this check.
    """
    link = ScriptedLink()
    clock = FakeClock()
    link.queue(
        *handshake(status_frame(BIT_SENSOR_USER)),
        *handshake(),
        *handshake(status_frame(BIT_SENSOR_READ | BIT_SENSOR_USER)),
        *handshake(status_frame(BIT_SENSOR_READ | BIT_SENSOR_USER)),
    )

    _driver(link, clock).move_card_to_read_position()

    expected_enq = bytes([ENQ, ord("0"), ord("0")])
    frame_indexes = [
        i for i, chunk in enumerate(link.writes) if chunk[:1] == bytes([0x02])
    ]
    assert frame_indexes
    for index in frame_indexes:
        assert index + 1 < len(link.writes), "frame was not followed by ENQ"
        assert link.writes[index + 1] == expected_enq
