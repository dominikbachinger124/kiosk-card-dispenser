"""Unit of work: one database transaction per service call.

The transaction starts with ``BEGIN IMMEDIATE`` so concurrent writers wait
instead of failing mid-way. Leaving the block without ``commit()`` rolls back.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from kiosk.storage.database import connect
from kiosk.storage.repositories import (
    AccountRepository,
    AuditRepository,
    CardRepository,
    LedgerRepository,
    SessionRepository,
)


class UnitOfWork:
    """Repositories bound to one open transaction.

    Use via ``UnitOfWorkFactory.begin()``; direct construction is for tests.
    """

    accounts: AccountRepository
    cards: CardRepository
    sessions: SessionRepository
    ledger: LedgerRepository
    audit: AuditRepository

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.accounts = AccountRepository(conn)
        self.cards = CardRepository(conn)
        self.sessions = SessionRepository(conn)
        self.ledger = LedgerRepository(conn)
        self.audit = AuditRepository(conn)
        self._committed = False

    @property
    def committed(self) -> bool:
        """Whether ``commit()`` has succeeded for this transaction."""
        return self._committed

    def commit(self) -> None:
        """Commit the transaction. Only the first call has an effect."""
        if not self._committed:
            self._conn.execute("COMMIT")
            self._committed = True


class UnitOfWorkFactory:
    """Creates units of work over a database file."""

    def __init__(self, database_path: Path) -> None:
        self._path = database_path

    @contextmanager
    def begin(self) -> Iterator[UnitOfWork]:
        """Open a connection and a write transaction for one service call.

        Yields:
            A unit of work. Changes persist only if ``commit()`` is called.
        """
        conn = connect(self._path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            uow = UnitOfWork(conn)
            try:
                yield uow
            except BaseException:
                _rollback(conn)
                raise
            if not uow.committed:
                _rollback(conn)
        finally:
            conn.close()


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("ROLLBACK")


__all__ = ["UnitOfWork", "UnitOfWorkFactory"]
