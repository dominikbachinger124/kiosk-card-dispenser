"""Tests for card status transitions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from kiosk.domain.entities import Card, CardStatus
from kiosk.domain.errors import InvalidCardStateError

T0 = datetime(2026, 1, 1, tzinfo=UTC)
T1 = datetime(2026, 1, 2, tzinfo=UTC)


def _active() -> Card:
    return Card(
        id=1, uid_hash="h" * 64, account_id=1, status=CardStatus.ACTIVE, issued_at=T0
    )


def test_active_card_can_be_recycled() -> None:
    card = _active().recycle(T1)

    assert card.status is CardStatus.RECYCLED
    assert card.recycled_at == T1
    assert card.cancelled_at is None


def test_active_card_can_be_cancelled() -> None:
    card = _active().cancel(T1)

    assert card.status is CardStatus.CANCELLED
    assert card.cancelled_at == T1


def test_recycled_card_cannot_be_recycled_again() -> None:
    recycled = _active().recycle(T1)

    with pytest.raises(InvalidCardStateError):
        recycled.recycle(T1)


def test_cancelled_card_cannot_be_recycled() -> None:
    cancelled = _active().cancel(T1)

    with pytest.raises(InvalidCardStateError):
        cancelled.recycle(T1)
