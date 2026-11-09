"""Runtime wiring: polling worker feeds the main window, shutdown stops the thread.

Tests run offscreen and use a scripted coordinator. No serial port is opened.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from kiosk.domain.errors import PortLostError  # noqa: E402
from kiosk.hardware.coordinator import HardwareCoordinator  # noqa: E402


class _State:
    def __init__(self, user_exit: bool) -> None:
        self.user_exit_occupied = user_exit
        self.read_position_occupied = False
        self.stack_occupied = True


class _ScriptedDispenser:
    """Returns scripted sensor states. Records calls only; no device."""

    def __init__(self, script: list[bool | Exception]) -> None:
        self._script = list(script)
        self.polls = 0

    def poll_state(self) -> _State:
        self.polls += 1
        if not self._script:
            return _State(user_exit=False)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return _State(user_exit=item)


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def _wait_for(predicate: Callable[[], bool], timeout_s: float = 3.0) -> bool:
    """Wait while processing Qt events, so queued signals reach the bridge."""
    from PySide6.QtCore import QCoreApplication

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_poll_failure_reaches_bridge_as_translated_text(qt_app: Any) -> None:
    from kiosk.gui.main_window import MainWindowBridge
    from kiosk.gui.runtime import PollingRuntime

    bridge = MainWindowBridge(customer=None, admin=None)
    dispenser = _ScriptedDispenser([PortLostError("gone")])
    runtime = PollingRuntime(HardwareCoordinator(dispenser), bridge, interval_s=0.01)

    runtime.start()
    try:
        assert _wait_for(
            lambda: bridge.status == "Geraet nicht erreichbar. Bitte Personal rufen."
        )
    finally:
        runtime.stop()


def test_card_at_exit_is_shown_on_rising_edge(qt_app: Any) -> None:
    from kiosk.gui.main_window import MainWindowBridge
    from kiosk.gui.runtime import PollingRuntime

    bridge = MainWindowBridge(customer=None, admin=None)
    dispenser = _ScriptedDispenser([False, True, True])
    runtime = PollingRuntime(HardwareCoordinator(dispenser), bridge, interval_s=0.01)

    runtime.start()
    try:
        assert _wait_for(lambda: bridge.status == "Karte am Ausgang.")
    finally:
        runtime.stop()


def test_stop_ends_polling_thread(qt_app: Any) -> None:
    from kiosk.gui.main_window import MainWindowBridge
    from kiosk.gui.runtime import PollingRuntime

    bridge = MainWindowBridge(customer=None, admin=None)
    dispenser = _ScriptedDispenser([])
    runtime = PollingRuntime(HardwareCoordinator(dispenser), bridge, interval_s=0.01)

    runtime.start()
    assert _wait_for(lambda: dispenser.polls >= 2)
    runtime.stop()

    assert not runtime.is_running()
    polls_after_stop = dispenser.polls
    time.sleep(0.05)
    assert dispenser.polls == polls_after_stop


def test_stop_without_start_is_safe(qt_app: Any) -> None:
    from kiosk.gui.main_window import MainWindowBridge
    from kiosk.gui.runtime import PollingRuntime

    bridge = MainWindowBridge(customer=None, admin=None)
    runtime = PollingRuntime(
        HardwareCoordinator(_ScriptedDispenser([])), bridge, interval_s=0.01
    )

    runtime.stop()
    assert not runtime.is_running()


def test_no_serial_port_is_opened_without_polling(tmp_path: Path) -> None:
    """Building the runtime must not touch the device; only start() polls."""
    from kiosk.gui.main_window import MainWindowBridge
    from kiosk.gui.runtime import PollingRuntime

    dispenser = _ScriptedDispenser([])
    bridge = MainWindowBridge(customer=None, admin=None)
    PollingRuntime(HardwareCoordinator(dispenser), bridge, interval_s=0.01)

    assert dispenser.polls == 0
    assert threading.active_count() >= 1
