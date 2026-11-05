"""Edge detection on the K720 sensor bits, independent of Qt.

The driver reports three occupancy bits: user exit (U), read position (L),
and stack (S). Only transitions are meaningful. A card that is present and
unchanged produces no event, so a long-standing state does not wake the
kiosk again and again.

The protocol does not reliably show a card jammed inside the device, so
this module never infers "card in the slot" from a single reading.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SensorEvent(StrEnum):
    """A transition of one sensor bit."""

    USER_EXIT_OCCUPIED = "user_exit_occupied"
    USER_EXIT_FREED = "user_exit_freed"
    READ_POSITION_OCCUPIED = "read_position_occupied"
    READ_POSITION_FREED = "read_position_freed"
    STACK_OCCUPIED = "stack_occupied"
    STACK_FREED = "stack_freed"


@dataclass(frozen=True, slots=True)
class SensorReading:
    """One snapshot of the three occupancy bits.

    Attributes:
        user_exit: Sensor U (card at the user exit).
        read_position: Sensor L (card at the read position).
        stack: Sensor S (card at the stack output).
    """

    user_exit: bool
    read_position: bool
    stack: bool


class SensorEdgeDetector:
    """Reports the edges between consecutive readings.

    The first reading only establishes the baseline and produces no events,
    so a device that is already occupied at start-up does not look like a new
    card.
    """

    def __init__(self) -> None:
        self._previous: SensorReading | None = None

    def update(self, reading: SensorReading) -> tuple[SensorEvent, ...]:
        """Feed one reading and return the transitions since the last one."""
        previous = self._previous
        self._previous = reading
        if previous is None:
            return ()
        events: list[SensorEvent] = []
        _edge(
            events,
            previous.user_exit,
            reading.user_exit,
            SensorEvent.USER_EXIT_OCCUPIED,
            SensorEvent.USER_EXIT_FREED,
        )
        _edge(
            events,
            previous.read_position,
            reading.read_position,
            SensorEvent.READ_POSITION_OCCUPIED,
            SensorEvent.READ_POSITION_FREED,
        )
        _edge(
            events,
            previous.stack,
            reading.stack,
            SensorEvent.STACK_OCCUPIED,
            SensorEvent.STACK_FREED,
        )
        return tuple(events)


def _edge(
    events: list[SensorEvent],
    before: bool,
    after: bool,
    rising: SensorEvent,
    falling: SensorEvent,
) -> None:
    if not before and after:
        events.append(rising)
    elif before and not after:
        events.append(falling)


__all__ = ["SensorEdgeDetector", "SensorEvent", "SensorReading"]
