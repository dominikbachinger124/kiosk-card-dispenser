"""Dispenser adapter that routes every device call through the coordinator.

Services get a ``CardDispenser`` and do not know about the lock. This adapter
makes sure a flow's device calls never interleave with polling. It adds no
logic of its own and does not change errors.
"""

from __future__ import annotations

from kiosk.hardware.coordinator import HardwareCoordinator
from kiosk.hardware.interfaces import CardDispenser, DispenserState


class CoordinatedDispenser:
    """Forward each ``CardDispenser`` call while holding the coordinator lock.

    Args:
        dispenser: The real or fake device.
        coordinator: Lock shared with the polling worker.
    """

    def __init__(
        self, dispenser: CardDispenser, coordinator: HardwareCoordinator
    ) -> None:
        self._dispenser = dispenser
        self._coordinator = coordinator

    def issue_card(self) -> None:
        self._coordinator.run(lambda d: d.issue_card())

    def move_card_to_read_position(self) -> None:
        self._coordinator.run(lambda d: d.move_card_to_read_position())

    def move_card_to_user_exit(self) -> None:
        self._coordinator.run(lambda d: d.move_card_to_user_exit())

    def read_uid(self) -> str:
        return self._coordinator.run(lambda d: d.read_uid())

    def dispose_card(self) -> None:
        self._coordinator.run(lambda d: d.dispose_card())

    def poll_state(self) -> DispenserState:
        return self._coordinator.run(lambda d: d.poll_state())


__all__ = ["CoordinatedDispenser"]
