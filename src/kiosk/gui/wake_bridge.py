"""Maps hardware and input events to screensaver wake-ups.

Any of these wakes the kiosk: a card entering the K720 user exit, a card read
at the ID reader, touch, or key input. Events that do not wake (a card leaving
the exit) are ignored here. The bridge holds no business rules and no device
access.
"""

from __future__ import annotations

from kiosk.gui.screensaver import ScreensaverController, ScreensaverState, WakeReason
from kiosk.hardware.sensor_events import SensorEvent

# Sensor transitions that show a card is at or entering the device output.
_WAKING_SENSOR_EVENTS: frozenset[str] = frozenset(
    {
        SensorEvent.USER_EXIT_OCCUPIED.value,
        SensorEvent.READ_POSITION_OCCUPIED.value,
    }
)


class WakeBridge:
    """Applies wake-up rules to a screensaver state.

    Args:
        controller: Screensaver state machine.
    """

    def __init__(self, controller: ScreensaverController) -> None:
        self._controller = controller

    def on_sensor_event(self, state: ScreensaverState, event: str) -> ScreensaverState:
        """Wake on a card entering the K720 output; ignore other transitions."""
        if event in _WAKING_SENSOR_EVENTS:
            return self._controller.wake(state, WakeReason.CARD)
        return state

    def on_card_read(self, state: ScreensaverState) -> ScreensaverState:
        """Wake on a card read at the ID reader."""
        return self._controller.wake(state, WakeReason.CARD)

    def on_touch(self, state: ScreensaverState) -> ScreensaverState:
        """Wake on touch while asleep, or refresh activity while awake."""
        if state.asleep:
            return self._controller.wake(state, WakeReason.TOUCH)
        return self._controller.interact(state)


__all__ = ["WakeBridge"]
