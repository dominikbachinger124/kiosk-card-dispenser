"""The default command starts the bootstrap, without touching hardware."""

from __future__ import annotations

from pathlib import Path

import pytest

from kiosk.__main__ import main
from kiosk.bootstrap import SALT_ENV
from tests.conftest import VALID_CONFIG_TOML


def test_start_runs_bootstrap_and_reports_ok(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(SALT_ENV, "x" * 32)
    monkeypatch.setattr(
        "kiosk.__main__.DEFAULT_DB_PATH_OVERRIDE", tmp_path / "kiosk.db", raising=False
    )
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")

    code = main(["--config", str(path), "--db", str(tmp_path / "kiosk.db")])

    assert code == 0
    assert "bootstrap ok" in capsys.readouterr().out
    assert (tmp_path / "kiosk.db").exists()


def test_start_without_salt_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv(SALT_ENV, raising=False)
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG_TOML, encoding="utf-8")

    code = main(["--config", str(path), "--db", str(tmp_path / "kiosk.db")])

    assert code == 2
    assert "CONFIG_INVALID" in capsys.readouterr().err
    assert not (tmp_path / "kiosk.db").exists()
