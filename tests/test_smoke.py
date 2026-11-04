"""Smoke tests: package imports and the project's entry layout."""

from __future__ import annotations

import importlib

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "kiosk",
        "kiosk.config",
        "kiosk.domain.errors",
        "kiosk.domain",
        "kiosk.storage",
        "kiosk.hardware",
        "kiosk.services",
        "kiosk.gui",
        "kiosk.i18n",
    ],
)
def test_package_layers_import(module: str) -> None:
    importlib.import_module(module)


def test_package_exposes_version() -> None:
    from kiosk import __version__

    assert __version__ == "0.1.0"
