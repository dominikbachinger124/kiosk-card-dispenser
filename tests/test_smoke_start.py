"""Smoke start: the GUI loads offscreen and exits cleanly, without hardware."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from kiosk.bootstrap import SALT_ENV
from tests.conftest import VALID_CONFIG_TOML

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_smoke_flag_loads_window_and_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from kiosk.__main__ import main

    monkeypatch.setenv(SALT_ENV, "x" * 32)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")

    code = main(["--config", str(path), "--db", str(tmp_path / "kiosk.db"), "--smoke"])

    assert code == 0
    assert "smoke ok" in capsys.readouterr().out


def test_smoke_without_salt_still_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from kiosk.__main__ import main

    monkeypatch.delenv(SALT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)  # no project .env here
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")

    code = main(["--config", str(path), "--db", str(tmp_path / "kiosk.db"), "--smoke"])

    assert code == 2
    assert "CONFIG_INVALID" in capsys.readouterr().err
