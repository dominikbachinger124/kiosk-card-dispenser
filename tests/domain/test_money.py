"""Tests for integer-cent money values."""

from __future__ import annotations

import pytest

from kiosk.domain.errors import InvalidAmountError
from kiosk.domain.money import Money


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError):
        Money(20.0)  # type: ignore[arg-type]


@pytest.mark.parametrize("cents", [0, 500, 2000])
def test_money_stores_integer_cents(cents: int) -> None:
    assert Money(cents).cents == cents


def test_money_arithmetic_stays_integer() -> None:
    total = Money(2000) + Money(500) - Money(200)

    assert total == Money(2300)
    assert type(total.cents) is int


def test_require_positive_rejects_zero_and_negative() -> None:
    with pytest.raises(InvalidAmountError):
        Money(0).require_positive()
    with pytest.raises(InvalidAmountError):
        Money(-1).require_positive()


def test_require_positive_accepts_positive() -> None:
    assert Money(1).require_positive() == Money(1)
