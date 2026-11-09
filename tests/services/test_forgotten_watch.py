"""Forgotten-card watch runs in its own thread and can be stopped.

The 30-second wait must never block the polling thread. These tests use a
real ForgottenCardService with a fake dispenser and an injected sleep, so no
time is spent and no device is opened.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime

from kiosk.services.forgotten_watch import ForgottenWatch

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class _Recorder:
    """Stands in for ForgottenCardService.watch and records the card it got."""

    def __init__(self, block: threading.Event | None = None) -> None:
        self.calls: list[object] = []
        self._block = block

    def watch(self, card: object) -> str:
        self.calls.append(card)
        if self._block is not None:
            self._block.wait(5)
        return "taken_by_user"


def test_watch_runs_in_background_and_returns_immediately() -> None:
    release = threading.Event()
    service = _Recorder(block=release)
    watch = ForgottenWatch(service)

    started = time.monotonic()
    watch.start(card="card-1")
    elapsed = time.monotonic() - started

    try:
        assert elapsed < 0.5, "start() must not wait for the 30-second timeout"
        assert watch.is_running()
    finally:
        release.set()
        watch.stop()


def test_stop_ends_watch_thread() -> None:
    release = threading.Event()
    service = _Recorder(block=release)
    watch = ForgottenWatch(service)

    watch.start(card="card-1")
    release.set()
    assert watch.stop() is True
    assert not watch.is_running()


def test_stop_without_start_is_safe() -> None:
    watch = ForgottenWatch(_Recorder())
    assert watch.stop() is True


def test_start_twice_while_running_keeps_first_card() -> None:
    release = threading.Event()
    service = _Recorder(block=release)
    watch = ForgottenWatch(service)

    watch.start(card="card-1")
    watch.start(card="card-2")
    release.set()
    watch.stop()

    assert service.calls == ["card-1"]


def test_outcome_is_kept_after_finish() -> None:
    service = _Recorder()
    watch = ForgottenWatch(service)

    watch.start(card="card-1")
    assert watch.stop() is True
    assert watch.last_outcome == "taken_by_user"
