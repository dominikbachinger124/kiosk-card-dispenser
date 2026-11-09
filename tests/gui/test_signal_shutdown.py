"""Signals end the kiosk event loop cleanly, and the threads are stopped first.

The real signal path is exercised through ``request_quit``, which the signal
handler calls. No device is opened: the runtime and watch are fakes.
"""

from __future__ import annotations

import os
import signal
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _FakeRuntime:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> bool:
        self.stopped = True
        return True

    def is_running(self) -> bool:
        return False


class _FakeWatch:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> bool:
        self.stopped = True
        return True


@pytest.fixture(scope="module")
def qt_app() -> Any:
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def test_request_quit_ends_event_loop_with_zero(qt_app: Any) -> None:
    from PySide6.QtCore import QTimer

    from kiosk.gui.app import request_quit

    QTimer.singleShot(0, request_quit)
    assert qt_app.exec() == 0


def test_install_signal_handlers_maps_sigint_and_sigterm(qt_app: Any) -> None:
    from kiosk.gui.app import install_signal_handlers

    previous_int = signal.getsignal(signal.SIGINT)
    previous_term = signal.getsignal(signal.SIGTERM)
    try:
        install_signal_handlers()
        assert callable(signal.getsignal(signal.SIGINT))
        assert callable(signal.getsignal(signal.SIGTERM))
    finally:
        signal.signal(signal.SIGINT, previous_int)
        signal.signal(signal.SIGTERM, previous_term)


def test_shutdown_stops_threads_after_quit(qt_app: Any) -> None:
    from kiosk.gui.app import stop_background

    runtime = _FakeRuntime()
    watch = _FakeWatch()

    assert stop_background(runtime, watch) is True
    assert runtime.stopped and watch.stopped
