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


class HardwareError(KioskError):
    """Base class for failures of a physical device.

    Hardware errors stop the affected flow. No ledger entry is booked unless
    the device confirmed the operation.
    """

    code = "HW_ERROR"


class HardwareTimeoutError(HardwareError):
    """The device did not answer within the allowed time."""

    code = "HW_TIMEOUT"


class PortLostError(HardwareError):
    """The serial port or USB device disappeared or cannot be opened."""

    code = "PORT_LOST"


class CardJammedError(HardwareError):
    """Card jam: stack and read position are occupied together (S+L).

    Stops the device. Recovery is manual: admin login, red button, removal,
    then confirmation in the software.
    """

    code = "CARD_JAMMED"


class CardOverlapError(HardwareError):
    """Card overlap (overlap bit 0x0040). Stops the device like a jam.

    Recovery is the same admin procedure as for ``CardJammedError``.
    """

    code = "CARD_OVERLAP"


class DispenserEmptyError(HardwareError):
    """The card stock is empty."""

    code = "DISPENSER_EMPTY"


class DispenserStateError(HardwareError):
    """The device reports a state that does not allow the requested action."""

    code = "DISPENSER_STATE"


class ProtocolError(HardwareError):
    """A device frame is malformed, has a wrong checksum, or is unexpected."""

    code = "PROTOCOL_ERROR"


class DeviceNotConfiguredError(HardwareError):
    """Real hardware is required but no device is configured."""

    code = "DEVICE_NOT_CONFIGURED"


class BusyError(HardwareError):
    """The device is occupied by another operation and did not become free."""

    code = "BUSY"


class AccountClosedError(KioskError):
    """The account is already closed and accepts no further bookings."""

    code = "ACCOUNT_CLOSED"


class PayoutNotConfirmedError(KioskError):
    """The payout was started without the explicit admin confirmation."""

    code = "PAYOUT_NOT_CONFIRMED"


class AdminAuthError(KioskError):
    """Admin card or PIN is wrong. The message is deliberately generic."""

    code = "ADMIN_AUTH_FAILED"


class AdminLockedError(KioskError):
    """Too many failed admin logins; access is blocked for a while."""

    code = "ADMIN_LOCKED"


class DeviceFaultAlreadyOpenError(KioskError):
    """A device fault is already open; a second one cannot be recorded."""

    code = "DEVICE_FAULT_OPEN"


class AdminSessionExpiredError(KioskError):
    """The admin session timed out or was never opened."""

    code = "ADMIN_SESSION_EXPIRED"
