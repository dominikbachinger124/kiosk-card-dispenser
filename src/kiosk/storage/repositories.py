"""Repositories for accounts, cards, sessions, ledger, and audit.

Repositories work on one open transaction owned by the unit of work. They
never commit. The ledger repository exposes ``append`` only.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

from kiosk.domain.entities import Account, Card, CardStatus, Session
from kiosk.domain.errors import (
    AccountClosedError,
    DuplicateOperationError,
    LedgerIntegrityError,
    NotFoundError,
)
from kiosk.domain.ledger import EntryType, LedgerEntry


def _ts(value: datetime) -> str:
    """Serialize a UTC datetime as ISO 8601 with a Z suffix."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _parse_required(value: str) -> datetime:
    """Parse a mandatory timestamp; a stored NULL here is a data error."""
    parsed = _parse(value)
    if parsed is None:
        raise LedgerIntegrityError("mandatory timestamp is missing in database")
    return parsed


class AccountRepository:
    """Persistence for ``Account`` aggregates."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, id_hash: str, created_at: datetime) -> Account:
        cursor = self._conn.execute(
            "INSERT INTO accounts (id_hash, created_at) VALUES (?, ?)",
            (id_hash, _ts(created_at)),
        )
        return Account(id=_require_id(cursor), id_hash=id_hash, created_at=created_at)

    def get(self, account_id: int) -> Account:
        row = self._conn.execute(
            "SELECT id, id_hash, created_at, closed_at FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"account {account_id} not found")
        return _account(row)

    def list_all(self) -> list[Account]:
        rows = self._conn.execute(
            "SELECT id, id_hash, created_at, closed_at FROM accounts ORDER BY id"
        ).fetchall()
        return [_account(row) for row in rows]

    def close(self, account_id: int, closed_at: datetime) -> None:
        """Mark an open account as closed. Accounts are never deleted.

        Raises:
            NotFoundError: If the account does not exist or is already closed.
        """
        cursor = self._conn.execute(
            "UPDATE accounts SET closed_at = ? WHERE id = ? AND closed_at IS NULL",
            (_ts(closed_at), account_id),
        )
        if cursor.rowcount != 1:
            raise NotFoundError(f"open account {account_id} not found")

    def find_by_hash(self, id_hash: str) -> Account | None:
        row = self._conn.execute(
            "SELECT id, id_hash, created_at, closed_at FROM accounts WHERE id_hash = ?",
            (id_hash,),
        ).fetchone()
        return None if row is None else _account(row)


class CardRepository:
    """Persistence for ``Card`` aggregates."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, uid_hash: str, account_id: int, issued_at: datetime) -> Card:
        closed = self._conn.execute(
            "SELECT closed_at FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if closed is None:
            raise NotFoundError(f"account {account_id} not found")
        if closed["closed_at"] is not None:
            raise AccountClosedError(f"account {account_id} is closed")
        cursor = self._conn.execute(
            "INSERT INTO cards (uid_hash, account_id, status, issued_at) "
            "VALUES (?, ?, 'active', ?)",
            (uid_hash, account_id, _ts(issued_at)),
        )
        return Card(
            id=_require_id(cursor),
            uid_hash=uid_hash,
            account_id=account_id,
            status=CardStatus.ACTIVE,
            issued_at=issued_at,
        )

    def get(self, card_id: int) -> Card:
        row = self._conn.execute(_CARD_SELECT + " WHERE id = ?", (card_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"card {card_id} not found")
        return _card(row)

    def find_by_hash(self, uid_hash: str) -> Card | None:
        row = self._conn.execute(
            _CARD_SELECT + " WHERE uid_hash = ?", (uid_hash,)
        ).fetchone()
        return None if row is None else _card(row)

    def list_for_account(self, account_id: int) -> list[Card]:
        rows = self._conn.execute(
            _CARD_SELECT + " WHERE account_id = ? ORDER BY id", (account_id,)
        ).fetchall()
        return [_card(row) for row in rows]

    def update(self, card: Card) -> None:
        """Persist a status change produced by ``Card.recycle`` or ``Card.cancel``."""
        cursor = self._conn.execute(
            "UPDATE cards SET status = ?, recycled_at = ?, cancelled_at = ? "
            "WHERE id = ?",
            (
                card.status.value,
                _ts(card.recycled_at) if card.recycled_at else None,
                _ts(card.cancelled_at) if card.cancelled_at else None,
                card.id,
            ),
        )
        if cursor.rowcount != 1:
            raise NotFoundError(f"card {card.id} not found")


class SessionRepository:
    """Persistence for technical session metadata."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, session: Session) -> None:
        self._conn.execute(
            "INSERT INTO sessions (id, flow, started_at, ended_at, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                session.id,
                session.flow,
                _ts(session.started_at),
                _ts(session.ended_at) if session.ended_at else None,
                session.outcome,
            ),
        )


class LedgerRepository:
    """Append-only access to ledger bookings. No update or delete exists."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, entry: LedgerEntry) -> LedgerEntry:
        """Insert one entry and return it with its database id.

        Raises:
            DuplicateOperationError: If ``operation_id`` was already booked or
                the entry was already reversed.
            LedgerIntegrityError: If a trigger or constraint rejects the row.
        """
        if self._is_closed(entry.account_id):
            raise AccountClosedError(f"account {entry.account_id} is closed")
        try:
            cursor = self._conn.execute(
                "INSERT INTO ledger (account_id, card_id, entry_type, amount_cents, "
                "deposit_delta_cents, created_at, session_id, operation_id, "
                "reversal_of, reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.account_id,
                    entry.card_id,
                    entry.entry_type.value,
                    entry.amount_cents,
                    entry.deposit_delta_cents,
                    _ts(entry.created_at),
                    entry.session_id,
                    entry.operation_id,
                    entry.reversal_of,
                    entry.reason,
                ),
            )
        except sqlite3.IntegrityError as exc:
            message = str(exc)
            if "ledger.operation_id" in message or "ledger.reversal_of" in message:
                raise DuplicateOperationError("operation already booked") from exc
            raise LedgerIntegrityError(_safe_db_message(message)) from exc
        except sqlite3.DatabaseError as exc:
            raise LedgerIntegrityError(_safe_db_message(str(exc))) from exc
        return _with_id(entry, _require_id(cursor))

    def _is_closed(self, account_id: int) -> bool:
        row = self._conn.execute(
            "SELECT closed_at FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        return row is not None and row["closed_at"] is not None

    def balance_cents(self, account_id: int) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) AS total "
            "FROM ledger WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        return int(row["total"])

    def deposit_cents(self, account_id: int) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(deposit_delta_cents), 0) AS total "
            "FROM ledger WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        return int(row["total"])

    def get(self, entry_id: int) -> LedgerEntry:
        row = self._conn.execute(
            _LEDGER_SELECT + " WHERE id = ?", (entry_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"ledger entry {entry_id} not found")
        return _entry(row)

    def list_for_account(self, account_id: int) -> list[LedgerEntry]:
        rows = self._conn.execute(
            _LEDGER_SELECT + " WHERE account_id = ? ORDER BY id", (account_id,)
        ).fetchall()
        return [_entry(row) for row in rows]


class AuditRepository:
    """Append-only admin audit trail. Stores no PINs and no raw UIDs."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(
        self,
        *,
        occurred_at: datetime,
        action: str,
        outcome: str,
        account_id: int | None = None,
        detail: str | None = None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO admin_audit "
            "(occurred_at, action, account_id, outcome, detail) VALUES (?, ?, ?, ?, ?)",
            (_ts(occurred_at), action, account_id, outcome, detail),
        )

    def count_failed_logins(self, since: datetime) -> int:
        """Count failed admin logins at or after ``since``.

        The count lives in the audit table, so a restart cannot reset a lockout.
        """
        row = self._conn.execute(
            "SELECT COUNT(*) AS total FROM admin_audit "
            "WHERE action = 'admin_login' AND outcome = 'failed' AND occurred_at >= ?",
            (_ts(since),),
        ).fetchone()
        return int(row["total"])


_CARD_SELECT = (
    "SELECT id, uid_hash, account_id, status, issued_at, recycled_at, cancelled_at "
    "FROM cards"
)

_LEDGER_SELECT = (
    "SELECT id, account_id, card_id, entry_type, amount_cents, deposit_delta_cents, "
    "created_at, session_id, operation_id, reversal_of, reason FROM ledger"
)


def _require_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise LedgerIntegrityError("insert returned no row id")
    return int(cursor.lastrowid)


def _safe_db_message(message: str) -> str:
    """Return a DB error message that cannot carry card data.

    SQLite messages only name tables and triggers, never row values, so the
    text is safe. It is still limited in length.
    """
    return message[:200]


def _account(row: sqlite3.Row) -> Account:
    return Account(
        id=row["id"],
        id_hash=row["id_hash"],
        created_at=_parse_required(row["created_at"]),
        closed_at=_parse(row["closed_at"]),
    )


def _card(row: sqlite3.Row) -> Card:
    return Card(
        id=row["id"],
        uid_hash=row["uid_hash"],
        account_id=row["account_id"],
        status=CardStatus(row["status"]),
        issued_at=_parse_required(row["issued_at"]),
        recycled_at=_parse(row["recycled_at"]),
        cancelled_at=_parse(row["cancelled_at"]),
    )


def _entry(row: sqlite3.Row) -> LedgerEntry:
    return LedgerEntry(
        id=row["id"],
        account_id=row["account_id"],
        card_id=row["card_id"],
        entry_type=EntryType(row["entry_type"]),
        amount_cents=row["amount_cents"],
        deposit_delta_cents=row["deposit_delta_cents"],
        created_at=_parse_required(row["created_at"]),
        session_id=row["session_id"],
        operation_id=row["operation_id"],
        reversal_of=row["reversal_of"],
        reason=row["reason"],
    )


def _with_id(entry: LedgerEntry, entry_id: int) -> LedgerEntry:
    return replace(entry, id=entry_id)
