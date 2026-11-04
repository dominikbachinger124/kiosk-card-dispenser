"""Monetary amounts as integer cents.

Floats are rejected at construction so that no binary rounding error can
reach the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering

from kiosk.domain.errors import InvalidAmountError


@total_ordering
@dataclass(frozen=True, slots=True)
class Money:
    """Monetary amount in integer cents. Negative values are allowed for debits.

    Attributes:
        cents: Amount in cents (e.g. ``2000`` is 20.00 EUR).
    """

    cents: int

    def __post_init__(self) -> None:
        if type(self.cents) is not int:
            raise TypeError(f"cents must be int, got {type(self.cents).__name__}")

    def __add__(self, other: Money) -> Money:
        return Money(self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        return Money(self.cents - other.cents)

    def __neg__(self) -> Money:
        return Money(-self.cents)

    def __lt__(self, other: Money) -> bool:
        return self.cents < other.cents

    def require_positive(self) -> Money:
        """Return this amount if it is strictly positive.

        Raises:
            InvalidAmountError: If the amount is zero or negative.
        """
        if self.cents <= 0:
            raise InvalidAmountError("amount must be positive")
        return self
