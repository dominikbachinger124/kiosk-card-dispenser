"""Structured logging: one JSON object per line, rotated, private files.

Each line carries ``ts``, ``level``, ``logger`` and ``event``. Only the extra
fields listed in ``EXTRA_FIELDS`` are copied, so an accidental ``card_uid`` or
PIN passed to ``extra`` never reaches the file. Log directory and file are
created with mode 0700 and 0600.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE_NAME = "kiosk.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
EXTRA_FIELDS = ("session_id", "error_code", "flow", "account_id", "amount_cents")
DIR_MODE = 0o700
FILE_MODE = 0o600


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record, with allow-listed extra fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for field in EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_dir: Path) -> logging.Handler:
    """Attach a rotating JSON file handler to the root logger.

    Args:
        log_dir: Directory for ``kiosk.log``. Created with mode 0700 if missing.

    Returns:
        The attached handler. The caller removes and closes it on shutdown.
    """
    log_dir.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(log_dir, DIR_MODE)
    log_file = log_dir / LOG_FILE_NAME
    if not log_file.exists():
        fd = os.open(log_file, os.O_CREAT | os.O_WRONLY, FILE_MODE)
        os.close(fd)
    os.chmod(log_file, FILE_MODE)

    handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "baseFilename", None) == str(log_file):
            root.removeHandler(existing)
            existing.close()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handler


__all__ = ["JsonFormatter", "configure_logging"]
