"""The kiosk process ends on SIGINT and SIGTERM within a bounded time.

The kiosk runs as a real subprocess with its own session. It uses a temporary
configuration whose device paths do not exist, so no real serial port is
opened and no device command is sent. Polling then fails closed with
``poll_failed``, which is the expected state without hardware.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.conftest import VALID_CONFIG_TOML

STARTUP_WAIT_S = 3.0
EXIT_LIMIT_S = 10.0
SALT = "test-only-salt-not-a-secret-value"


def _start_kiosk(tmp_path: Path) -> subprocess.Popen[bytes]:
    config = tmp_path / "config.toml"
    config.write_text(VALID_CONFIG_TOML, encoding="utf-8")
    env = {
        **os.environ,
        "KIOSK_ID_HASH_SALT": SALT,
        "QT_QPA_PLATFORM": "offscreen",
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "kiosk",
            "--config",
            str(config),
            "--db",
            str(tmp_path / "kiosk.db"),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )


@pytest.mark.parametrize(
    "sig", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"]
)
def test_kiosk_exits_cleanly_on_signal(tmp_path: Path, sig: signal.Signals) -> None:
    proc = _start_kiosk(tmp_path)
    try:
        time.sleep(STARTUP_WAIT_S)
        assert proc.poll() is None, "kiosk exited before the signal was sent"

        sent_at = time.monotonic()
        proc.send_signal(sig)
        try:
            returncode = proc.wait(timeout=EXIT_LIMIT_S)
        except subprocess.TimeoutExpired:
            pytest.fail(f"kiosk still running {EXIT_LIMIT_S}s after {sig.name}")
        elapsed = time.monotonic() - sent_at
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

    assert returncode == 0, f"exit code {returncode} after {sig.name}"
    assert elapsed < EXIT_LIMIT_S
