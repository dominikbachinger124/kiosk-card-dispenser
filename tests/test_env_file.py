"""Tests for the minimal .env loader (stdlib only, no new runtime dependency)."""

from __future__ import annotations

from pathlib import Path

import pytest

from kiosk.env_file import load_env_file, parse_env_text


def test_parse_reads_key_value_pairs() -> None:
    text = "KIOSK_ID_HASH_SALT=abcdefgh12345678\nOTHER=value\n"

    assert parse_env_text(text) == {
        "KIOSK_ID_HASH_SALT": "abcdefgh12345678",
        "OTHER": "value",
    }


def test_parse_ignores_comments_blank_lines_and_export_prefix() -> None:
    text = "# comment\n\nexport A=1\n   \nB=2\n"

    assert parse_env_text(text) == {"A": "1", "B": "2"}


def test_parse_strips_matching_quotes() -> None:
    text = "A=\"with spaces\"\nB='single'\n"

    assert parse_env_text(text) == {"A": "with spaces", "B": "single"}


def test_parse_keeps_equals_sign_in_value() -> None:
    assert parse_env_text("A=x=y==\n") == {"A": "x=y=="}


def test_parse_rejects_line_without_equals_sign() -> None:
    with pytest.raises(ValueError, match="line 2"):
        parse_env_text("A=1\nnot-a-pair\n")


def test_load_sets_missing_variables(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=1\n", encoding="utf-8")
    environ: dict[str, str] = {}

    load_env_file(env_file, environ)

    assert environ == {"A": "1"}


def test_load_does_not_override_existing_variables(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=from_file\n", encoding="utf-8")
    environ = {"A": "from_shell"}

    load_env_file(env_file, environ)

    assert environ == {"A": "from_shell"}


def test_load_missing_file_is_noop(tmp_path: Path) -> None:
    environ: dict[str, str] = {}

    load_env_file(tmp_path / "absent.env", environ)

    assert environ == {}


def test_load_never_reports_values_in_errors(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_VALUE_WITHOUT_EQUALS\n", encoding="utf-8")

    with pytest.raises(ValueError) as info:
        load_env_file(env_file, {})

    assert "SECRET_VALUE_WITHOUT_EQUALS" not in str(info.value)
