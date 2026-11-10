"""Offscreen tests for the main window: it loads and shows the customer actions."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MAIN_QML = Path(__file__).resolve().parents[2] / "src/kiosk/gui/qml/Main.qml"


class _FakeCustomer:
    """Customer flow stub. Records calls; no device is touched."""

    def __init__(self) -> None:
        self.issue_calls = 0
        self.topup_calls = 0

    def start_issue(self, on_progress: Callable[[str], None] | None = None) -> str:
        self.issue_calls += 1
        return "issued"

    def start_topup(self) -> str:
        self.topup_calls += 1
        return "topped_up"


class _FakeAdmin:
    loggedIn = False
    message = ""


@pytest.fixture(scope="module")
def qt_app() -> object:
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.instance() or QGuiApplication([])


def _process_events() -> None:
    """Run pending events so the deferred flow start executes."""
    from PySide6.QtCore import QCoreApplication

    QCoreApplication.processEvents()
    QCoreApplication.processEvents()


def _create(customer: object, admin: object | None) -> tuple[object, ...]:
    """Build engine, bridge and root object. The caller must keep the tuple alive."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

    from kiosk.gui.main_window import MainWindowBridge

    engine = QQmlApplicationEngine()
    bridge = MainWindowBridge(customer, admin)  # type: ignore[arg-type]
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(MAIN_QML)))
    assert component.status() != QQmlComponent.Status.Error, [
        e.toString() for e in component.errors()
    ]
    obj = component.createWithInitialProperties({"kiosk": bridge}, engine.rootContext())
    assert obj is not None
    return engine, bridge, component, obj


def test_main_qml_loads_offscreen(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), None)

    assert keep[3] is not None


def test_admin_is_not_offered_without_admin_service(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), None)
    bridge = keep[1]

    assert bridge.adminAvailable is False  # type: ignore[attr-defined]


def test_admin_is_offered_when_admin_service_exists(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), _FakeAdmin())
    bridge = keep[1]

    assert bridge.adminAvailable is True  # type: ignore[attr-defined]


def test_issue_action_calls_customer_flow_and_sets_status(qt_app: object) -> None:
    customer = _FakeCustomer()
    keep = _create(customer, None)
    bridge = keep[1]

    bridge.startIssue()
    _process_events()

    assert customer.issue_calls == 1
    assert bridge.status == "Karte ausgegeben."  # type: ignore[attr-defined]


def test_topup_action_calls_customer_flow_and_sets_status(qt_app: object) -> None:
    customer = _FakeCustomer()
    keep = _create(customer, None)
    bridge = keep[1]

    bridge.startTopup()
    _process_events()

    assert customer.topup_calls == 1
    assert bridge.status == "Konto aufgeladen."  # type: ignore[attr-defined]


def test_card_inserted_signal_shows_card_at_exit_status(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), None)
    bridge = keep[1]

    bridge.onCardInserted()

    assert bridge.status == "Karte am Ausgang."  # type: ignore[attr-defined]


def test_poll_failed_shows_error_code_text(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), None)
    bridge = keep[1]

    bridge.onPollFailed("PORT_LOST")

    status = bridge.status  # type: ignore[attr-defined]
    assert "PORT_LOST" not in status
    assert status == "Geraet nicht erreichbar. Bitte Personal rufen."


def test_unknown_poll_error_code_falls_back_to_generic_text(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), None)
    bridge = keep[1]

    bridge.onPollFailed("SOMETHING_NEW")

    status = bridge.status  # type: ignore[attr-defined]
    assert "error." not in status
    assert status == "Geraetefehler. Bitte Personal rufen."


def test_root_is_a_visible_window(qt_app: object) -> None:
    """The kiosk must show a window; a plain Item is loaded but never displayed."""
    from PySide6.QtQuick import QQuickWindow

    keep = _create(_FakeCustomer(), None)
    root = keep[3]

    assert isinstance(root, QQuickWindow)
    assert root.property("visible") is True  # type: ignore[attr-defined]


class _RecordingCustomer(_FakeCustomer):
    """Records the status text that is visible at the moment the flow starts."""

    def __init__(self) -> None:
        super().__init__()
        self.bridge: object | None = None
        self.status_at_call: str | None = None

    def start_issue(self, on_progress: Callable[[str], None] | None = None) -> str:
        assert self.bridge is not None
        self.status_at_call = self.bridge.status  # type: ignore[attr-defined]
        return super().start_issue(on_progress)


def test_issue_shows_present_id_prompt_before_reading(qt_app: object) -> None:
    customer = _RecordingCustomer()
    keep = _create(customer, None)
    bridge = keep[1]
    customer.bridge = bridge

    bridge.startIssue()
    # The read is deferred so the prompt can be painted first.
    _process_events()

    assert customer.status_at_call == "Bitte Ausweis auflegen."
    assert bridge.status == "Karte ausgegeben."  # type: ignore[attr-defined]


def test_card_removed_signal_shows_thanks_status(qt_app: object) -> None:
    keep = _create(_FakeCustomer(), None)
    bridge = keep[1]

    bridge.onCardRemoved()

    assert bridge.status == "Karte entnommen. Danke."  # type: ignore[attr-defined]


class _BlockingCustomer:
    """Customer whose issue flow blocks until the test releases it."""

    def __init__(self) -> None:
        import threading

        self.entered = threading.Event()
        self.release = threading.Event()

    def start_issue(self, on_progress: Callable[[str], None] | None = None) -> str:
        self.entered.set()
        self.release.wait(5)
        return "issued"

    def start_topup(self) -> str:
        return "topped_up"


def test_present_id_hint_is_visible_while_flow_blocks(qt_app: object) -> None:
    """The prompt must be on screen while the reader waits, not after the flow."""
    customer = _BlockingCustomer()
    keep = _create(customer, None)
    bridge = keep[1]

    bridge.startIssue()
    _process_events()
    assert customer.entered.wait(2)

    # The flow is still blocked here: the prompt is what the customer sees.
    assert bridge.status == "Bitte Ausweis auflegen."  # type: ignore[attr-defined]

    customer.release.set()
    for _ in range(50):
        _process_events()
        if bridge.status == "Karte ausgegeben.":  # type: ignore[attr-defined]
            break
    assert bridge.status == "Karte ausgegeben."  # type: ignore[attr-defined]


def _rendered_texts(root: object) -> list[str]:
    """Return the text of every QML Text item in the object tree."""
    from PySide6.QtCore import QObject
    from PySide6.QtQuick import QQuickItem

    items = root.findChildren(QQuickItem)  # type: ignore[attr-defined]
    return [
        str(item.property("text"))
        for item in items
        if isinstance(item, QObject) and item.metaObject().className() == "QQuickText"
    ]


def test_present_id_hint_is_rendered_in_qml_while_flow_blocks(qt_app: object) -> None:
    """The QML Text must show the prompt, not only the bridge property."""
    customer = _BlockingCustomer()
    keep = _create(customer, None)
    bridge = keep[1]
    root = keep[3]

    bridge.startIssue()
    _process_events()
    assert customer.entered.wait(2)

    assert "Bitte Ausweis auflegen." in _rendered_texts(root)

    customer.release.set()
    for _ in range(50):
        _process_events()
        if "Karte ausgegeben." in _rendered_texts(root):
            break
    assert "Karte ausgegeben." in _rendered_texts(root)
    assert "Bitte Ausweis auflegen." not in _rendered_texts(root)


class _ProgressCustomer:
    """Issue flow that reports the checked-card hint, then waits for release."""

    def __init__(self) -> None:
        import threading

        self.checked = threading.Event()
        self.release = threading.Event()

    def start_issue(self, on_progress: Callable[[str], None] | None = None) -> str:
        if on_progress is not None:
            on_progress("card_checked")
        self.checked.set()
        self.release.wait(5)
        return "issued"

    def start_topup(self) -> str:
        return "topped_up"


def test_card_checked_hint_is_rendered_before_flow_ends(qt_app: object) -> None:
    customer = _ProgressCustomer()
    keep = _create(customer, None)
    bridge = keep[1]
    root = keep[3]

    bridge.startIssue()
    assert customer.checked.wait(2)
    for _ in range(50):
        _process_events()
        if "Karte wird geprüft ..." in _rendered_texts(root):
            break

    assert "Karte wird geprüft ..." in _rendered_texts(root)
    assert bridge.status == "Karte wird geprüft ..."  # type: ignore[attr-defined]

    customer.release.set()
    for _ in range(50):
        _process_events()
        if bridge.status == "Karte ausgegeben.":  # type: ignore[attr-defined]
            break
    assert bridge.status == "Karte ausgegeben."  # type: ignore[attr-defined]
