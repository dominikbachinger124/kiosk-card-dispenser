"""SQLite connection setup and migration runner.

Every connection enables WAL and foreign keys. Migrations are applied in
order, each in its own transaction, and recorded in ``schema_migrations``.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kiosk.domain.errors import MigrationError

logger = logging.getLogger("kiosk.storage.database")

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def connect(path: Path) -> sqlite3.Connection:
    """Open a database file with WAL and foreign keys enabled.

    Args:
        path: Database file. ``:memory:`` is not supported because WAL needs a file.

    Returns:
        An open connection with ``isolation_level=None``; transactions are
        managed explicitly by the unit of work.
    """
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if str(mode).lower() != "wal":
        conn.close()
        raise MigrationError(f"could not enable WAL, got journal_mode={mode}")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@dataclass(frozen=True, slots=True)
class Migration:
    """One numbered SQL migration file.

    Attributes:
        version: Numeric prefix of the file name.
        name: File name, used for the audit trail.
        statements: Complete SQL statements in file order.
    """

    version: int
    name: str
    statements: tuple[str, ...]


def load_migrations(directory: Path) -> list[Migration]:
    """Read all migration files from a directory in ascending version order.

    Raises:
        MigrationError: On malformed names, duplicate versions, or gaps.
    """
    migrations: list[Migration] = []
    for file in sorted(directory.glob("*.sql")):
        match = _MIGRATION_NAME.match(file.name)
        if match is None:
            raise MigrationError(f"invalid migration file name: {file.name}")
        migrations.append(
            Migration(
                version=int(match.group(1)),
                name=file.name,
                statements=_split_statements(file.read_text(encoding="utf-8")),
            )
        )
    versions = [m.version for m in migrations]
    if versions != list(range(1, len(versions) + 1)):
        raise MigrationError(
            f"migration versions must be 1..n without gaps: {versions}"
        )
    return migrations


def _split_statements(sql: str) -> tuple[str, ...]:
    """Split SQL text into complete statements, respecting trigger bodies."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        if not buffer and (not line.strip() or line.lstrip().startswith("--")):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise MigrationError("migration ends with an incomplete statement")
    return tuple(statements)


def migrate(conn: sqlite3.Connection, directory: Path) -> list[str]:
    """Apply all pending migrations.

    Each migration runs in one ``BEGIN IMMEDIATE`` transaction together with
    its ``schema_migrations`` record. A failing migration rolls back fully.

    Returns:
        Names of the migrations applied in this call.

    Raises:
        MigrationError: If a migration fails; earlier ones remain applied.
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL,"
        " applied_at TEXT NOT NULL"
        ") STRICT"
    )
    applied = {
        row["version"] for row in conn.execute("SELECT version FROM schema_migrations")
    }
    newly_applied: list[str] = []
    for migration in load_migrations(directory):
        if migration.version in applied:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in migration.statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) "
                "VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                (migration.version, migration.name),
            )
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            conn.execute("ROLLBACK")
            raise MigrationError(f"migration {migration.name} failed: {exc}") from exc
        logger.info("migration_applied", extra={"migration": migration.name})
        newly_applied.append(migration.name)
    return newly_applied
