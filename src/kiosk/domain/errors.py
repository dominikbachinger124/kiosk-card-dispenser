"""Typed exceptions for all expected kiosk failures.

Every error carries a stable ``code`` so the GUI can map it to a localized
message. Raw exception text is never shown to the user.
"""

from __future__ import annotations


class KioskError(Exception):
    """Base class for all expected kiosk errors.

    Attributes:
        code: Stable, machine-readable error code.
        message: Developer-facing description; never contains UIDs or PINs.
    """

    code: str = "KIOSK_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(KioskError):
    """Configuration is missing, unreadable, or violates the schema."""

    code = "CONFIG_INVALID"


class InvalidAmountError(KioskError):
    """A money amount is zero or has the wrong sign for the operation."""

    code = "INVALID_AMOUNT"


class InvalidCardIdError(KioskError):
    """A card UID does not match the accepted format."""

    code = "INVALID_CARD_ID"


class InvalidCardStateError(KioskError):
    """A card status transition is not allowed."""

    code = "INVALID_CARD_STATE"


class InsufficientBalanceError(KioskError):
    """An operation would make a balance negative."""

    code = "INSUFFICIENT_BALANCE"


class LedgerRuleError(KioskError):
    """A ledger entry violates the booking rules for its type."""

    code = "LEDGER_RULE_VIOLATION"


class DuplicateOperationError(KioskError):
    """An operation id was already booked, or an entry was already reversed."""

    code = "DUPLICATE_OPERATION"


class LedgerIntegrityError(KioskError):
    """The database rejected a ledger write (constraint or trigger)."""

    code = "LEDGER_INTEGRITY"


class NotFoundError(KioskError):
    """A referenced account, card, or ledger entry does not exist."""

    code = "NOT_FOUND"


class MigrationError(KioskError):
    """A schema migration could not be read or applied."""

    code = "MIGRATION_FAILED"
