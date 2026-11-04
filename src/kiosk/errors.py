"""Typed exceptions shared across layers.

Every error carries a stable ``code`` so that the GUI can map it to a
localized message without showing raw exception text.
"""

from __future__ import annotations


class KioskError(Exception):
    """Base class for all expected kiosk errors.

    Attributes:
        code: Stable, machine-readable error code (e.g. ``CONFIG_INVALID``).
    """

    code: str = "KIOSK_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ConfigError(KioskError):
    """Configuration is missing, unreadable, or violates the schema."""

    code = "CONFIG_INVALID"
