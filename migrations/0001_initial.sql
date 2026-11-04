-- Initial schema for Kiosk Card Dispenser.
-- Money is stored as INTEGER cents only. Ledger rows are append-only:
-- UPDATE and DELETE on ledger are rejected by triggers below.

CREATE TABLE accounts (
    id          INTEGER PRIMARY KEY,
    id_hash     TEXT    NOT NULL UNIQUE CHECK (length(id_hash) = 64),
    created_at  TEXT    NOT NULL,
    closed_at   TEXT
) STRICT;

CREATE INDEX idx_accounts_id_hash ON accounts (id_hash);

CREATE TABLE cards (
    id           INTEGER PRIMARY KEY,
    uid_hash     TEXT    NOT NULL UNIQUE CHECK (length(uid_hash) = 64),
    account_id   INTEGER NOT NULL REFERENCES accounts (id),
    status       TEXT    NOT NULL CHECK (status IN ('active', 'recycled', 'cancelled')),
    issued_at    TEXT    NOT NULL,
    recycled_at  TEXT,
    cancelled_at TEXT,
    CHECK (
        (status = 'recycled'  AND recycled_at  IS NOT NULL AND cancelled_at IS NULL) OR
        (status = 'cancelled' AND cancelled_at IS NOT NULL AND recycled_at  IS NULL) OR
        (status = 'active'    AND recycled_at  IS NULL     AND cancelled_at IS NULL)
    )
) STRICT;

CREATE INDEX idx_cards_account_status ON cards (account_id, status);

CREATE TABLE sessions (
    id          TEXT    PRIMARY KEY,
    flow        TEXT    NOT NULL,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT,
    outcome     TEXT
) STRICT;

CREATE TABLE ledger (
    id                   INTEGER PRIMARY KEY,
    account_id           INTEGER NOT NULL REFERENCES accounts (id),
    card_id              INTEGER REFERENCES cards (id),
    entry_type           TEXT    NOT NULL CHECK (entry_type IN (
                             'cash_in_topup', 'cash_in_deposit', 'recycle_refund',
                             'payment', 'payout', 'card_cancel', 'reversal')),
    amount_cents         INTEGER NOT NULL,
    deposit_delta_cents  INTEGER NOT NULL,
    created_at           TEXT    NOT NULL,
    session_id           TEXT    NOT NULL REFERENCES sessions (id),
    operation_id         TEXT    NOT NULL UNIQUE,
    reversal_of          INTEGER REFERENCES ledger (id),
    reason               TEXT,
    CHECK (entry_type <> 'reversal' OR (reversal_of IS NOT NULL AND reason IS NOT NULL)),
    CHECK (entry_type <> 'reversal' OR reversal_of <> id)
) STRICT;

CREATE INDEX idx_ledger_account ON ledger (account_id);
CREATE UNIQUE INDEX idx_ledger_reversal_of ON ledger (reversal_of) WHERE reversal_of IS NOT NULL;

-- Append-only enforcement on the database level.
CREATE TRIGGER ledger_no_update
BEFORE UPDATE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only: UPDATE rejected');
END;

CREATE TRIGGER ledger_no_delete
BEFORE DELETE ON ledger
BEGIN
    SELECT RAISE(ABORT, 'ledger is append-only: DELETE rejected');
END;

-- Balance may never become negative. The check is evaluated per insert
-- against the running sum of all earlier entries of the same account.
CREATE TRIGGER ledger_balance_not_negative
BEFORE INSERT ON ledger
WHEN (
    SELECT COALESCE(SUM(amount_cents), 0) FROM ledger WHERE account_id = NEW.account_id
) + NEW.amount_cents < 0
BEGIN
    SELECT RAISE(ABORT, 'balance would become negative');
END;

-- Pfand must not become negative per account.
CREATE TRIGGER ledger_deposit_not_negative
BEFORE INSERT ON ledger
WHEN (
    SELECT COALESCE(SUM(deposit_delta_cents), 0) FROM ledger WHERE account_id = NEW.account_id
) + NEW.deposit_delta_cents < 0
BEGIN
    SELECT RAISE(ABORT, 'deposit would become negative');
END;

-- A reversal may only correct an entry of the same account.
CREATE TRIGGER ledger_reversal_same_account
BEFORE INSERT ON ledger
WHEN NEW.reversal_of IS NOT NULL AND (
    SELECT account_id FROM ledger WHERE id = NEW.reversal_of
) IS NOT NEW.account_id
BEGIN
    SELECT RAISE(ABORT, 'reversal must reference an entry of the same account');
END;

CREATE TABLE admin_audit (
    id           INTEGER PRIMARY KEY,
    occurred_at  TEXT    NOT NULL,
    action       TEXT    NOT NULL,
    account_id   INTEGER REFERENCES accounts (id),
    outcome      TEXT    NOT NULL,
    detail       TEXT
) STRICT;

CREATE TRIGGER admin_audit_no_update
BEFORE UPDATE ON admin_audit
BEGIN
    SELECT RAISE(ABORT, 'admin_audit is append-only: UPDATE rejected');
END;

CREATE TRIGGER admin_audit_no_delete
BEFORE DELETE ON admin_audit
BEGIN
    SELECT RAISE(ABORT, 'admin_audit is append-only: DELETE rejected');
END;
