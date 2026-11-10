"""The entry point loads a local .env before the bootstrap reads the salt."""

from __future__ import annotations

from pathlib import Path

import pytest

from kiosk.__main__ import main
from kiosk.bootstrap import SALT_ENV
from tests.conftest import VALID_CONFIG_TOML


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv(SALT_ENV, raising=False)
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG_TOML, encoding="utf-8")
    return config


def test_start_reads_salt_from_dotenv_in_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _setup(tmp_path, monkeypatch)
    (tmp_path / ".env").write_text(f"{SALT_ENV}={'y' * 32}\n", encoding="utf-8")

    code = main(
        [
            "--config",
            str(config),
            "--db",
            str(tmp_path / "kiosk.db"),
            "--bootstrap-only",
        ]
    )

    assert code == 0
    assert "bootstrap ok" in capsys.readouterr().out


def test_shell_salt_wins_over_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _setup(tmp_path, monkeypatch)
    monkeypatch.setenv(SALT_ENV, "z" * 32)
    (tmp_path / ".env").write_text(f"{SALT_ENV}={'y' * 32}\n", encoding="utf-8")

    main(
        [
            "--config",
            str(config),
            "--db",
            str(tmp_path / "kiosk.db"),
            "--bootstrap-only",
        ]
    )

    import os

    assert os.environ[SALT_ENV] == "z" * 32


def test_missing_dotenv_and_no_salt_still_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _setup(tmp_path, monkeypatch)

    code = main(
        [
            "--config",
            str(config),
            "--db",
            str(tmp_path / "kiosk.db"),
            "--bootstrap-only",
        ]
    )

    assert code == 2
    assert "CONFIG_INVALID" in capsys.readouterr().err
    assert not (tmp_path / "kiosk.db").exists()
