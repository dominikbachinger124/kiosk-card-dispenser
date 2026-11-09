"""Tests for the command-line entry point, limited to --check-config."""

from __future__ import annotations

from pathlib import Path

import pytest

from kiosk.__main__ import main
from tests.conftest import VALID_CONFIG_TOML


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_check_config_accepts_valid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, VALID_CONFIG_TOML)

    code = main(["--check-config", "--config", str(path)])

    assert code == 0
    out = capsys.readouterr().out
    assert "config ok" in out


def test_check_config_output_contains_no_device_paths_or_secrets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, VALID_CONFIG_TOML)

    main(["--check-config", "--config", str(path)])

    out = capsys.readouterr()
    assert "/dev/serial" not in out.out + out.err
    assert "AD01AD01" not in out.out + out.err


def test_check_config_rejects_invalid_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, '[app]\nlanguage = "de"\n')

    code = main(["--check-config", "--config", str(path)])

    assert code != 0
    err = capsys.readouterr().err
    assert "CONFIG_INVALID" in err


def test_check_config_rejects_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--check-config", "--config", str(tmp_path / "missing.toml")])

    assert code != 0
    assert "CONFIG_INVALID" in capsys.readouterr().err


def test_check_config_rejects_fake_mode(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = VALID_CONFIG_TOML.replace('mode = "real"', 'mode = "fake"', 1)
    path = _write(tmp_path, text)

    code = main(["--check-config", "--config", str(path)])

    assert code != 0
    assert "CONFIG_INVALID" in capsys.readouterr().err
