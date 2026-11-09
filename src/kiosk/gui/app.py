"""Qt application start: loads the main window and runs the event loop.

The window is built from the bootstrap result. The polling worker runs in its
own thread and reaches the GUI only through signals. ``run_smoke`` loads the
window and returns at once, so a start can be checked without an event loop.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from kiosk.bootstrap import KioskApp

logger = logging.getLogger("kiosk.gui.app")

MAIN_QML = Path(__file__).resolve().parent / "qml" / "Main.qml"


def build_window(app: KioskApp) -> tuple[object, ...]:
    """Create the Qt engine, bridge and root window for the given kiosk app.

    Returns:
        A tuple that must be kept alive by the caller, otherwise Qt deletes the
        objects. Element 3 is the root object.
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

    from kiosk.gui.main_window import MainWindowBridge

    admin = app.admin_auth
    bridge = MainWindowBridge(app.customer, admin)
    engine = QQmlApplicationEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(MAIN_QML)))
    if component.status() == QQmlComponent.Status.Error:
        messages = [e.toString() for e in component.errors()]
        raise RuntimeError(f"QML failed to load: {messages}")
    root = component.createWithInitialProperties(
        {"kiosk": bridge}, engine.rootContext()
    )
    if root is None:
        raise RuntimeError("QML root could not be created")
    return engine, bridge, component, root


def request_quit() -> None:
    """End the Qt event loop. Safe to call from a slot or a timer.

    Signal handlers must not call Qt directly; they go through this function
    via the event loop.
    """
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.quit()


def install_signal_handlers() -> None:
    """Route SIGINT and SIGTERM to a clean quit of the event loop.

    Qt blocks Python's signal handling while it runs. A short periodic timer
    gives Python a chance to run the handler, so Ctrl-C works in the kiosk.
    """
    import signal

    def _handle(_signum: int, _frame: object) -> None:
        request_quit()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)


def stop_background(runtime: _Stoppable, watch: _Stoppable) -> bool:
    """Stop the polling runtime and the forgotten-card watch.

    Both are attempted even if one times out.

    Returns:
        True if both ended within their timeouts.
    """
    polling_clean = runtime.stop()
    watch_clean = watch.stop()
    return polling_clean and watch_clean


class _Stoppable(Protocol):
    def stop(self) -> bool: ...


def run_app(app: KioskApp) -> int:
    """Run the kiosk: window, polling thread and Qt event loop until quit.

    The polling thread and the forgotten-card watch are started before the
    event loop and stopped and joined before the function returns, so the
    process exits without a live device thread.

    Returns:
        The Qt event-loop exit code.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication

    from kiosk.gui.main_window import MainWindowBridge
    from kiosk.gui.runtime import PollingRuntime, shutdown_threads

    qapp = QGuiApplication.instance() or QGuiApplication([])
    window = build_window(app)
    bridge = window[1]
    if not isinstance(bridge, MainWindowBridge):
        raise RuntimeError("main window bridge missing")
    runtime = PollingRuntime(app.coordinator, bridge)
    runtime.start()
    install_signal_handlers()
    # Qt does not run Python signal handlers while blocked in exec(). This
    # timer wakes the interpreter about every 200 ms so Ctrl-C is seen.
    wakeup = QTimer()
    wakeup.timeout.connect(lambda: None)
    wakeup.start(200)
    try:
        return int(qapp.exec())
    finally:
        wakeup.stop()
        if not shutdown_threads(runtime, app.watch):
            # A thread did not end in time. Exit anyway so the kiosk stays
            # responsive; the device keeps its last state (fail closed).
            logger.error("shutdown_timeout", extra={"error_code": "HW_TIMEOUT"})
        del window


def run_smoke(app: KioskApp) -> int:
    """Load the window offscreen and return 0. No event loop, no hardware.

    Returns:
        0 when the window loaded. Raises on a broken QML file.
    """
    from PySide6.QtGui import QGuiApplication

    qapp = QGuiApplication.instance() or QGuiApplication([])
    keep = build_window(app)
    qapp.processEvents()
    del keep
    return 0


__all__ = ["build_window", "run_smoke"]
