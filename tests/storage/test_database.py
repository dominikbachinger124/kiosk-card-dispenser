"""Tests for SQLite setup, pragmas, and the migration runner."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from kiosk.domain.errors import MigrationError
from kiosk.storage.database import connect, load_migrations, migrate
from tests.conftest import MIGRATIONS_DIR


def test_connection_enables_wal_and_foreign_keys(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.db")
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_migrations_apply_once_and_are_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "x.db")
    try:
        first = migrate(conn, MIGRATIONS_DIR)
        second = migrate(conn, MIGRATIONS_DIR)
    finally:
        conn.close()

    assert first == ["0001_initial.sql", "0002_device_fault.sql"]
    assert second == []


def test_schema_contains_required_tables(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()

    assert {"accounts", "cards", "ledger", "sessions", "admin_audit"} <= tables


def test_migration_files_are_contiguous() -> None:
    versions = [m.version for m in load_migrations(MIGRATIONS_DIR)]

    assert versions == list(range(1, len(versions) + 1))


def test_gap_in_migration_versions_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text(
        "CREATE TABLE a (x INTEGER);", encoding="utf-8"
    )
    (tmp_path / "0003_c.sql").write_text(
        "CREATE TABLE c (x INTEGER);", encoding="utf-8"
    )

    with pytest.raises(MigrationError, match="without gaps"):
        load_migrations(tmp_path)


def test_failing_migration_rolls_back_and_is_not_recorded(tmp_path: Path) -> None:
    (tmp_path / "0001_ok.sql").write_text(
        "CREATE TABLE ok (x INTEGER);", encoding="utf-8"
    )
    (tmp_path / "0002_bad.sql").write_text(
        "CREATE TABLE half (x INTEGER);\nINSERT INTO nope VALUES (1);",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "x.db")
    try:
        with pytest.raises(MigrationError, match="0002_bad.sql"):
            migrate(conn, tmp_path)
        versions = [
            row[0] for row in conn.execute("SELECT version FROM schema_migrations")
        ]
        half = conn.execute(
            "SELECT name FROM sqlite_master WHERE name = 'half'"
        ).fetchone()
    finally:
        conn.close()

    assert versions == [1]
    assert half is None


def test_invalid_migration_file_name_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "init.sql").write_text("SELECT 1;", encoding="utf-8")

    with pytest.raises(MigrationError, match="invalid migration file name"):
        load_migrations(tmp_path)


def test_foreign_key_violation_is_rejected(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cards (uid_hash, account_id, status, issued_at) "
                "VALUES (?, 999, 'active', '2026-01-01T00:00:00.000000Z')",
                ("a" * 64,),
            )
    finally:
        conn.close()
