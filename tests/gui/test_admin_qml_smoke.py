"""Offscreen smoke test: AdminPanel.qml loads and binds to the Qt bridge."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QML_FILE = Path(__file__).resolve().parents[2] / "src/kiosk/gui/qml/AdminPanel.qml"


class _StubViewModel:
    """Minimal stand-in for the plain ViewModel; no business logic."""

    is_logged_in = False
    message = ""

    def login(self, raw_admin_uid: str, pin: str) -> bool:
        return False

    def logout(self) -> None:
        return None

    def accounts(self) -> list[object]:
        return []

    def payout(self, account_id: int, confirmation: object) -> None:
        return None


@pytest.fixture(scope="module")
def qt_app() -> object:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    return app


def test_admin_panel_qml_loads_offscreen(qt_app: object) -> None:
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

    from kiosk.gui.admin_qt import AdminQt

    engine = QQmlApplicationEngine()
    bridge = AdminQt(_StubViewModel())
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_FILE)))

    assert component.status() != QQmlComponent.Status.Error, [
        e.toString() for e in component.errors()
    ]
    obj = component.createWithInitialProperties({"admin": bridge}, engine.rootContext())

    assert obj is not None
    assert obj.property("visible") is True
