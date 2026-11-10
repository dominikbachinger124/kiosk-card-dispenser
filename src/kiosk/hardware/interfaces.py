"""Hardware interfaces used by the rest of the application.

Domain and services depend only on these protocols. Method names come from
``docs/architecture.md`` and are assumptions until verified against the
device protocol. They must not be read as device commands.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class DispenserEvent(StrEnum):
    """Result of an issue, read, or retract operation as seen by the flow."""

    CARD_ON_USER_SIDE = "card_on_user_side"
    CARD_AT_READ_POSITION = "card_at_read_position"
    CARD_IN_STACK = "card_in_stack"
    EMPTY = "empty"


class CardDispenser(Protocol):
    """Card hardware: issue, position, read and dispose of cards."""

    def issue_card(self) -> None:
        """Move one card to the user exit.

        Raises:
            HardwareError: On timeout, jam, overlap, empty stock or port loss.
        """
        ...

    def move_card_to_read_position(self) -> None:
        """Move a card from the user exit to the read position.

        Raises:
            HardwareError: If no card is at the user exit or the device rejects.
        """
        ...

    def move_card_to_user_exit(self) -> None:
        """Bring a card from the read position back to the user exit (``FC4``).

        Raises:
            HardwareError: If no card is at a position the device accepts.
        """
        ...

    def read_uid(self) -> str:
        """Read the UID of the card in the read position.

        Returns:
            Hexadecimal UID string.

        Raises:
            HardwareError: If no card can be read.
        """
        ...

    def dispose_card(self) -> None:
        """Move a card from the read position to the recycling box.

        Raises:
            HardwareError: If the device rejects or the card cannot be moved.
        """
        ...

    def poll_state(self) -> DispenserState:
        """Read the current device state without moving anything.

        Raises:
            HardwareError: On timeout or port loss.
        """
        ...


class DispenserState(Protocol):
    """Read-only view of the device status."""

    @property
    def user_exit_occupied(self) -> bool: ...

    @property
    def read_position_occupied(self) -> bool: ...

    @property
    def stack_occupied(self) -> bool: ...


class IdReader(Protocol):
    """Reads one card identifier from the USB-HID reader."""

    def read_id(self) -> str:
        """Return the raw identifier typed by the reader.

        Raises:
            HardwareError: On timeout, overflow, or missing device.
        """
        ...
