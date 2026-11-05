"""Admin PIN hashing with scrypt.

The PIN is never stored or logged in clear text. The stored value carries
its own parameters and salt, so the hash can be verified without any other
secret. Verification fails closed: malformed stored values never match.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16
_PREFIX = "scrypt"


def new_salt() -> bytes:
    """Return a fresh random salt for a PIN hash."""
    return secrets.token_bytes(SALT_BYTES)


def hash_pin(pin: str, salt: bytes) -> str:
    """Hash a PIN for storage in configuration.

    Args:
        pin: The PIN in clear text. Only used for hashing.
        salt: Random salt, at least 16 bytes.

    Returns:
        Encoded string ``scrypt$N$r$p$<salt hex>$<hash hex>``.
    """
    if len(salt) < SALT_BYTES:
        raise ValueError(f"salt must be at least {SALT_BYTES} bytes")
    digest = _derive(pin, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"{_PREFIX}${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, encoded: str) -> bool:
    """Check a PIN against an encoded hash in constant time.

    Args:
        pin: The PIN entered by the admin.
        encoded: Stored value as produced by ``hash_pin``.

    Returns:
        True only if the PIN matches. Malformed ``encoded`` values return False.
    """
    parsed = _parse(encoded)
    if parsed is None:
        return False
    n, r, p, salt, expected = parsed
    candidate = _derive(pin, salt, n, r, p)
    return hmac.compare_digest(candidate, expected)


def _derive(pin: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=SCRYPT_DKLEN,
        maxmem=64 * 1024 * 1024,
    )


def _parse(encoded: str) -> tuple[int, int, int, bytes, bytes] | None:
    parts = encoded.split("$")
    if len(parts) != 6 or parts[0] != _PREFIX:
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = bytes.fromhex(parts[4])
        digest = bytes.fromhex(parts[5])
    except ValueError:
        return None
    if n < 2 or r < 1 or p < 1 or len(salt) < SALT_BYTES or len(digest) != SCRYPT_DKLEN:
        return None
    return n, r, p, salt, digest


__all__ = ["hash_pin", "new_salt", "verify_pin"]
