"""K720 card dispenser driver over pyserial.

Implements only the commands listed in ``docs/k720_protocol.md``:
``AP``, ``DC``, ``FC7``, ``FC4``, ``CP``, ``RS`` and the card search
and UID commands ``0x3B 0x30`` / ``0x3B 0x31``.

Deliberately NOT implemented: ``FC0`` (ejects a card that then jams the
chute), ``FC6`` (only valid from stack alone, not part of the flow) and
``CS0``..``CS5`` (changes the baud rate and drops the link).

Every command follows the handshake from section 3: frame, wait for ACK,
send ENQ. Movement commands return no payload, so their result is read with
``AP``. Status polls are at least 200 ms apart (section 4).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from kiosk.domain.errors import (
    CardJammedError,
    CardOverlapError,
    DispenserEmptyError,
    DispenserStateError,
    HardwareError,
    HardwareTimeoutError,
    PortLostError,
    ProtocolError,
)
from kiosk.hardware.k720_frame import (
    ACK,
    BIT_CARD_OVERLAP,
    BIT_CARD_STUCK,
    BIT_DISPENSE_ERROR,
    BIT_RECORD_ERROR,
    BIT_STOCK_EMPTY,
    ENQ,
    NAK,
    DeviceStatus,
    decode_frame,
    encode_frame,
    parse_status_payload,
)

logger = logging.getLogger("kiosk.hardware.k720")

K720_BAUDRATE = 9600
STATUS_POLL_INTERVAL_S = 0.2
MOVEMENT_SETTLE_S = 1.0
HANDSHAKE_GAP_S = 0.05
RESPONSE_TIMEOUT_S = 2.0
READ_RETRY_INTERVAL_S = 0.01
COMMAND_SETTLE_TIMEOUT_S = 15.0
MAX_UID_BYTES = 4

# Commands as payload bytes, exactly as listed in the protocol document.
CMD_STATUS_LONG = b"AP"
CMD_MOVE_STACK_TO_USER = b"DC"
CMD_MOVE_USER_TO_READ = b"FC7"
CMD_MOVE_READ_TO_USER = b"FC4"
CMD_DISPOSE = b"CP"
CMD_SEARCH_CARD = b"\x3b\x30"
CMD_READ_UID = b"\x3b\x31"

Transport = Callable[[bytes], None]


class SerialLink(Protocol):
    """Minimal serial port surface used by the driver (pyserial compatible)."""

    def write(self, data: bytes) -> int: ...

    def read(self, size: int) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


class K720Dispenser:
    """Driver for the TTCE K720 over a serial link.

    The link is injected. Production code passes a ``serial.Serial`` opened
    with the configured port and 9600 8N1; tests pass a scripted link.

    Args:
        link: Open serial link.
        address: Device address 0..15 (default 0).
        clock: Monotonic clock in seconds.
        sleep: Pause function.
    """

    def __init__(
        self,
        link: SerialLink,
        *,
        address: int = 0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._link = link
        self._address = address
        self._clock = clock
        self._sleep = sleep
        self._last_status_at: float | None = None

    # --- public interface -------------------------------------------------

    def issue_card(self) -> None:
        """Move one card from the stack to the user exit (``DC``).

        Raises:
            DispenserEmptyError: If the stock is empty.
            CardJammedError: If the card is stuck.
            CardOverlapError: If two cards overlap.
            HardwareTimeoutError: If the device does not settle in time.
        """
        status = self._check_before_command()
        if status.stock_empty:
            raise DispenserEmptyError("stock empty")
        self._send_movement(CMD_MOVE_STACK_TO_USER)
        self._wait_for_status(
            lambda s: s.user_exit_occupied,
            failure_message="card did not reach user exit",
        )

    def move_card_to_read_position(self) -> None:
        """Move a card to the read position (``FC7``).

        Accepted from S, U, L and L+S (protocol matrix). Refused from L+U.

        Raises:
            DispenserStateError: If no card is present, or the card is already
                at the read position together with the user exit.
        """
        status = self._check_before_command()
        if not (
            status.stack_occupied
            or status.user_exit_occupied
            or status.read_position_occupied
        ):
            raise DispenserStateError("no card to move to read position")
        if status.user_exit_occupied and status.read_position_occupied:
            # Matrix: FC7 is refused from L+U (0x4013). Nothing to do.
            raise DispenserStateError("card already at read position")
        self._send_movement(CMD_MOVE_USER_TO_READ)
        self._wait_for_status(
            lambda s: s.read_position_occupied and s.user_exit_occupied,
            failure_message="card did not reach read position",
        )

    def move_card_to_user_exit(self) -> None:
        """Bring a card from any position to the user exit (``FC4``).

        This is the standard step before reading: the card is taken from the
        stack or read position and presented at the user exit. Per the
        protocol matrix, ``FC4`` is accepted from S, L, U, L+U and L+S.

        Raises:
            DispenserStateError: If no card is present at any position.
            HardwareTimeoutError: If the device does not settle in time.
        """
        status = self._check_before_command()
        if not (
            status.stack_occupied
            or status.read_position_occupied
            or status.user_exit_occupied
        ):
            raise DispenserStateError("no card to move to user exit")
        self._send_movement(CMD_MOVE_READ_TO_USER)
        # Sensor User goes high at once when the card arrives. Once it has been
        # seen, the card is at the exit; the user removing it afterwards is the
        # normal flow, so no second stable read is required here.
        self._wait_for_status(
            lambda s: s.user_exit_occupied and not s.read_position_occupied,
            failure_message="card did not reach user exit",
            require_stable=False,
        )

    def read_uid(self) -> str:
        """Search and read the UID of the card at the read position.

        Returns:
            Upper-case hexadecimal UID.

        Raises:
            HardwareTimeoutError: If no card is found or the response is short.
            ProtocolError: If the answer does not follow section 5.
        """
        search = self._transact(CMD_SEARCH_CARD)
        if not search.startswith(b"P;"):
            raise HardwareTimeoutError("no card found at read position")
        answer = self._transact(CMD_READ_UID)
        if not answer.startswith(b"P;1"):
            raise ProtocolError("unexpected UID answer")
        uid_bytes = answer[len(b"P;1") :]
        if len(uid_bytes) != MAX_UID_BYTES:
            raise ProtocolError("UID answer does not contain four bytes")
        return uid_bytes.hex().upper()

    def dispose_card(self) -> None:
        """Move the card from the read position into the recycling box (``CP``).

        Raises:
            DispenserStateError: If no card is in a position that can be disposed.
        """
        status = self._check_before_command()
        if not (status.read_position_occupied or status.user_exit_occupied):
            raise DispenserStateError("no card to dispose")
        self._send_movement(CMD_DISPOSE)
        self._wait_for_status(
            lambda s: not s.read_position_occupied and not s.user_exit_occupied,
            failure_message="card was not disposed",
        )

    def poll_state(self) -> DeviceStatus:
        """Read the long status word (``AP``) and return it decoded."""
        return self._read_status()

    def close(self) -> None:
        """Close the serial link."""
        self._link.close()

    # --- internals ----------------------------------------------------------

    def _transact(self, payload: bytes) -> bytes:
        """Send a query frame, complete the handshake, and return the answer payload."""
        self._send_with_handshake(payload)
        response = self._read_frame()
        return decode_frame(response)

    def _send_movement(self, payload: bytes) -> None:
        """Send a movement command, then wait before the first status poll.

        The motor runs for a device-determined time. Polling directly after the
        command was observed to change the card position, so the driver waits
        ``MOVEMENT_SETTLE_S`` before it reads the status again.
        """
        self._send_with_handshake(payload)
        self._sleep(MOVEMENT_SETTLE_S)
        self._last_status_at = self._clock()

    def _send_with_handshake(self, payload: bytes) -> None:
        frame = encode_frame(self._address, payload)
        self._link.reset_input_buffer()
        self._write(frame)
        answer = self._read_exact(3)
        if answer[0] == NAK:
            raise ProtocolError("device rejected the frame (NAK)")
        if answer[0] != ACK:
            raise ProtocolError("device did not acknowledge the frame")
        self._sleep(HANDSHAKE_GAP_S)
        self._write(
            bytes(
                [ENQ, _address_byte(self._address, 0), _address_byte(self._address, 1)]
            )
        )

    def _check_before_command(self) -> DeviceStatus:
        status = self._read_status()
        if status.blocking_bits_set() or status.jam_by_sensors():
            raise _blocking_error(status)
        return status

    def _wait_for_status(
        self,
        done: Callable[[DeviceStatus], bool],
        *,
        failure_message: str,
        require_stable: bool = True,
    ) -> DeviceStatus:
        """Poll ``AP`` every 200 ms until ``done`` holds.

        With ``require_stable`` (default, section 4) the target must be read in
        two consecutive polls with the same status word. Without it, the first
        read that satisfies ``done`` completes the command. Use that only for
        targets that are reached instantly and may be left by a user afterwards.
        """
        deadline = self._clock() + COMMAND_SETTLE_TIMEOUT_S
        previous: DeviceStatus | None = None
        while self._clock() < deadline:
            status = self._read_status()
            if status.blocking_bits_set() or status.jam_by_sensors():
                raise _blocking_error(status)
            if status.command_rejected:
                # Transient (section 6): the status is not final, so poll again.
                previous = None
                continue
            if not done(status):
                previous = None
                continue
            if not require_stable:
                return status
            # Section 4: the command is complete only when the status is stable,
            # i.e. two consecutive reads show the same word.
            if previous is not None and status.raw == previous.raw:
                return status
            previous = status
        logger.error("k720_command_timeout", extra={"error_code": "HW_TIMEOUT"})
        raise HardwareTimeoutError(failure_message)

    def _read_status(self) -> DeviceStatus:
        """Send ``AP`` and decode the answer. Enforces 200 ms between polls."""
        self._respect_poll_interval()
        payload = self._transact(CMD_STATUS_LONG)
        self._last_status_at = self._clock()
        return parse_status_payload(payload)

    def _respect_poll_interval(self) -> None:
        if self._last_status_at is None:
            return
        elapsed = self._clock() - self._last_status_at
        if elapsed < STATUS_POLL_INTERVAL_S:
            self._sleep(STATUS_POLL_INTERVAL_S - elapsed)

    def _read_frame(self) -> bytes:
        """Read one complete response frame using its length field."""
        header = self._read_exact(5)
        if header[0] != 0x02:
            raise ProtocolError("response does not start with STX")
        length = int.from_bytes(header[3:5], "big")
        # Payload, ETX and BCC follow the five header bytes.
        rest = self._read_exact(length + 2)
        return header + rest

    def _read_exact(self, size: int) -> bytes:
        """Read exactly ``size`` bytes, or fail on timeout or link loss."""
        buffer = bytearray()
        deadline = self._clock() + RESPONSE_TIMEOUT_S
        while len(buffer) < size:
            try:
                chunk = self._link.read(size - len(buffer))
            except OSError as exc:
                logger.error("k720_port_lost", extra={"error_code": "PORT_LOST"})
                raise PortLostError("serial port lost") from exc
            if chunk:
                buffer.extend(chunk)
                continue
            if self._clock() >= deadline:
                logger.warning("k720_read_timeout", extra={"error_code": "HW_TIMEOUT"})
                raise HardwareTimeoutError("device did not answer in time")
            # Empty read: wait briefly so the deadline also advances when the
            # port returns immediately (no blocking read timeout configured).
            self._sleep(READ_RETRY_INTERVAL_S)
        return bytes(buffer)

    def _write(self, data: bytes) -> None:
        try:
            self._link.write(data)
        except OSError as exc:
            logger.error("k720_port_lost", extra={"error_code": "PORT_LOST"})
            raise PortLostError("serial port lost") from exc


def _address_byte(address: int, position: int) -> int:
    """Return one ASCII digit of the two-digit device address."""
    return ord(f"{address:02d}"[position])


def _blocking_error(status: DeviceStatus) -> HardwareError:
    """Map a blocking status word to the typed error that stops the flow."""
    if status.raw & BIT_STOCK_EMPTY:
        return DispenserEmptyError("stock empty")
    if status.raw & BIT_CARD_OVERLAP:
        return CardOverlapError("cards overlap")
    if status.raw & BIT_CARD_STUCK or status.jam_by_sensors():
        return CardJammedError("card is stuck")
    if status.raw & (BIT_DISPENSE_ERROR | BIT_RECORD_ERROR):
        return DispenserStateError("dispense or record error reported")
    return DispenserStateError("device reports a blocking state")


__all__ = [
    "ACK",
    "CMD_DISPOSE",
    "CMD_MOVE_READ_TO_USER",
    "CMD_MOVE_STACK_TO_USER",
    "CMD_MOVE_USER_TO_READ",
    "CMD_READ_UID",
    "CMD_SEARCH_CARD",
    "CMD_STATUS_LONG",
    "K720_BAUDRATE",
    "K720Dispenser",
    "SerialLink",
]
