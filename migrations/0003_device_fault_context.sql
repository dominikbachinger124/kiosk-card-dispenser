-- Adds the affected account and card to device faults.
-- Both are optional: a jam during FC4 or before the card is read has no
-- known card. The card is only linked, never cancelled, by the fault itself.
-- SQLite cannot add a constrained column in place, so the table is rebuilt.
-- Existing rows are copied; the open-fault index and triggers are recreated.

DROP TRIGGER device_faults_ack_audit_action;
DROP TRIGGER device_faults_update_only_ack;
DROP TRIGGER device_faults_no_delete;
DROP INDEX idx_device_faults_one_open;

ALTER TABLE device_faults RENAME TO device_faults_old;

CREATE TABLE device_faults (
    id                     INTEGER PRIMARY KEY,
    fault_code             TEXT    NOT NULL CHECK (fault_code IN (
                               'CARD_JAMMED', 'CARD_OVERLAP',
                               'DISPENSER_EMPTY', 'DISPENSER_STATE')),
    raised_at              TEXT    NOT NULL,
    session_id             TEXT    REFERENCES sessions (id),
    account_id             INTEGER REFERENCES accounts (id),
    card_id                INTEGER REFERENCES cards (id),
    acknowledged_at        TEXT,
    acknowledged_audit_id  INTEGER REFERENCES admin_audit (id),
    CHECK ((acknowledged_at IS NULL) = (acknowledged_audit_id IS NULL))
) STRICT;

INSERT INTO device_faults (id, fault_code, raised_at, session_id,
                           acknowledged_at, acknowledged_audit_id)
SELECT id, fault_code, raised_at, session_id,
       acknowledged_at, acknowledged_audit_id
FROM device_faults_old;

DROP TABLE device_faults_old;

CREATE UNIQUE INDEX idx_device_faults_one_open ON device_faults ((1))
WHERE acknowledged_at IS NULL;

CREATE TRIGGER device_faults_no_delete
BEFORE DELETE ON device_faults
BEGIN
    SELECT RAISE(ABORT, 'device_faults is append-only: DELETE rejected');
END;

-- Only the open -> acknowledged transition is allowed. Content, including
-- the linked account and card, stays unchanged.
CREATE TRIGGER device_faults_update_only_ack
BEFORE UPDATE ON device_faults
WHEN OLD.acknowledged_at IS NOT NULL
  OR NEW.fault_code IS NOT OLD.fault_code
  OR NEW.raised_at IS NOT OLD.raised_at
  OR NEW.session_id IS NOT OLD.session_id
  OR NEW.account_id IS NOT OLD.account_id
  OR NEW.card_id IS NOT OLD.card_id
BEGIN
    SELECT RAISE(ABORT, 'device fault may only be acknowledged once');
END;

CREATE TRIGGER device_faults_ack_audit_action
BEFORE UPDATE ON device_faults
WHEN NEW.acknowledged_audit_id IS NOT NULL
 AND (
    SELECT action FROM admin_audit WHERE id = NEW.acknowledged_audit_id
 ) IS NOT 'fault_ack'
BEGIN
    SELECT RAISE(ABORT, 'acknowledgement must reference a fault_ack audit row');
END;
