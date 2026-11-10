"""Offscreen tests for the main window: it loads and shows the customer actions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MAIN_QML = Path(__file__).resolve().parents[2] / "src/kiosk/gui/qml/Main.qml"


class _FakeCustomer:
    """Customer flow stub. Records calls; no device is touched."""

    def __init__(self) -> None:
        self.issue_calls = 0
        self.topup_calls = 0

    def start_issue(self) -> str:
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

    def start_issue(self) -> str:
        assert self.bridge is not None
        self.status_at_call = self.bridge.status  # type: ignore[attr-defined]
        return super().start_issue()


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
