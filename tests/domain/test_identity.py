"""Tests for card UID normalization and salted hashing."""

from __future__ import annotations

import hashlib

import pytest

from kiosk.domain.errors import InvalidCardIdError
from kiosk.domain.identity import CardIdHasher, normalize_card_uid

SALT = b"test-salt-0123456789abcdef"


def test_normalize_uppercases_and_strips() -> None:
    assert normalize_card_uid("  8388b21a \n") == "8388B21A"


@pytest.mark.parametrize("bad", ["", "XYZ", "12 34", "A" * 33, "0x1234"])
def test_normalize_rejects_malformed_uids(bad: str) -> None:
    with pytest.raises(InvalidCardIdError):
        normalize_card_uid(bad)


def test_hash_is_salted_sha256_of_normalized_uid() -> None:
    hasher = CardIdHasher(SALT)

    expected = hashlib.sha256(SALT + b"\x00" + b"8388B21A").hexdigest()

    assert hasher.hash_uid("8388b21a") == expected


def test_hash_does_not_contain_raw_uid() -> None:
    digest = CardIdHasher(SALT).hash_uid("8388B21A")

    assert len(digest) == 64
    assert "8388B21A" not in digest.upper()


def test_different_salts_produce_different_hashes() -> None:
    other = b"another-salt-0123456789abcdef"

    assert CardIdHasher(SALT).hash_uid("8388B21A") != CardIdHasher(other).hash_uid(
        "8388B21A"
    )


def test_short_salt_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least 16 bytes"):
        CardIdHasher(b"short")


def test_repr_hides_salt() -> None:
    assert "test-salt" not in repr(CardIdHasher(SALT))
