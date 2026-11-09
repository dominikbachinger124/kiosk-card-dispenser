"""Qt application start: loads the main window and runs the event loop.

The window is built from the bootstrap result. The polling worker runs in its
own thread and reaches the GUI only through signals. ``run_smoke`` loads the
window and returns at once, so a start can be checked without an event loop.
"""

from __future__ import annotations

from pathlib import Path

from kiosk.bootstrap import KioskApp

MAIN_QML = Path(__file__).resolve().parent / "qml" / "Main.qml"


class _NoCustomerFlows:
    """Placeholder until the customer flows are wired to the hardware.

    Actions report a neutral result instead of touching a device. This keeps
    the window usable without hardware and never books anything.
    """

    def start_issue(self) -> str:
        return "aborted"

    def start_topup(self) -> str:
        return "aborted"


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
    bridge = MainWindowBridge(_NoCustomerFlows(), admin)
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
