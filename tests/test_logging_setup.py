"""JSON logging: one object per line, extra fields kept, private files."""

from __future__ import annotations

import json
import logging
import stat
from pathlib import Path

import pytest

from kiosk.logging_setup import JsonFormatter, configure_logging


def _record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="kiosk.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_formatter_emits_one_json_object_with_required_fields() -> None:
    line = JsonFormatter().format(_record("customer_id_read_failed"))

    payload = json.loads(line)
    assert payload["event"] == "customer_id_read_failed"
    assert payload["level"] == "ERROR"
    assert payload["logger"] == "kiosk.test"
    assert payload["ts"].endswith("+00:00")


def test_formatter_keeps_allowed_extra_fields() -> None:
    line = JsonFormatter().format(
        _record("customer_id_read_failed", error_code="HW_TIMEOUT", session_id="s1")
    )

    payload = json.loads(line)
    assert payload["error_code"] == "HW_TIMEOUT"
    assert payload["session_id"] == "s1"


def test_formatter_drops_unknown_extra_fields() -> None:
    line = JsonFormatter().format(_record("x", card_uid="AABBCCDD"))

    assert "card_uid" not in json.loads(line)
    assert "AABBCCDD" not in line


def test_configure_logging_writes_json_file_with_private_modes(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "logs"
    handler = configure_logging(log_dir)
    try:
        logging.getLogger("kiosk.test").error(
            "customer_id_read_failed", extra={"error_code": "HW_TIMEOUT"}
        )
        handler.flush()
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()

    log_file = log_dir / "kiosk.log"
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["error_code"] == "HW_TIMEOUT"
    assert stat.S_IMODE(log_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(log_file.stat().st_mode) == 0o600


def test_configure_logging_does_not_duplicate_handlers(tmp_path: Path) -> None:
    first = configure_logging(tmp_path / "logs")
    second = configure_logging(tmp_path / "logs")
    try:
        file_handlers = [
            h
            for h in logging.getLogger().handlers
            if getattr(h, "baseFilename", "").endswith("kiosk.log")
        ]
        assert len(file_handlers) == 1
    finally:
        for handler in {first, second}:
            logging.getLogger().removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def _reset_root_handlers() -> None:
    """Keep the root logger clean between tests."""
    yield
    for handler in list(logging.getLogger().handlers):
        if getattr(handler, "baseFilename", "").endswith("kiosk.log"):
            logging.getLogger().removeHandler(handler)
            handler.close()
