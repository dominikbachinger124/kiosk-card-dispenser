"""Card identity: normalization and salted SHA-256 hashing.

Only the hash of a card UID is ever persisted or logged. The raw UID exists
in memory for the duration of one hardware read.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from kiosk.domain.errors import InvalidCardIdError

MAX_ID_LENGTH = 32
MIN_SALT_BYTES = 16
_UID_PATTERN = re.compile(r"^[0-9A-F]{1,32}$")


def normalize_card_uid(raw_uid: str) -> str:
    """Return the canonical upper-case hex form of a card UID.

    Args:
        raw_uid: UID as read from the reader, surrounding whitespace allowed.

    Returns:
        Upper-case hexadecimal string of 1 to 32 characters.

    Raises:
        InvalidCardIdError: If the value is not hexadecimal or too long.
    """
    candidate = raw_uid.strip().upper()
    if not _UID_PATTERN.fullmatch(candidate):
        raise InvalidCardIdError("card id must be 1-32 hexadecimal characters")
    return candidate


@dataclass(frozen=True, slots=True)
class CardIdHasher:
    """Salted SHA-256 hasher for card UIDs.

    Attributes:
        salt: Secret salt, at least 16 bytes. Provided from local configuration.
    """

    salt: bytes

    def __post_init__(self) -> None:
        if len(self.salt) < MIN_SALT_BYTES:
            raise ValueError(f"salt must be at least {MIN_SALT_BYTES} bytes")

    def __repr__(self) -> str:
        return "CardIdHasher(salt=<redacted>)"

    def hash_uid(self, raw_uid: str) -> str:
        """Return the 64-character hex digest of salt and normalized UID.

        Args:
            raw_uid: UID as read from the reader.

        Returns:
            Lower-case SHA-256 hex digest.

        Raises:
            InvalidCardIdError: If the UID is malformed.
        """
        uid = normalize_card_uid(raw_uid)
        digest = hashlib.sha256()
        digest.update(self.salt)
        digest.update(b"\x00")
        digest.update(uid.encode("ascii"))
        return digest.hexdigest()
