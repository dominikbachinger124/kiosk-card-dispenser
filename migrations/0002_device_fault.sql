-- Persistent device faults (card jam, overlap, empty stock, invalid state).
-- A fault stops the kiosk until an admin acknowledges it. At most one fault
-- may be open at any time. Rows are never deleted; acknowledgement is the
-- only permitted update and happens once.

CREATE TABLE device_faults (
    id                     INTEGER PRIMARY KEY,
    fault_code             TEXT    NOT NULL CHECK (fault_code IN (
                               'CARD_JAMMED', 'CARD_OVERLAP',
                               'DISPENSER_EMPTY', 'DISPENSER_STATE')),
    raised_at              TEXT    NOT NULL,
    session_id             TEXT    REFERENCES sessions (id),
    acknowledged_at        TEXT,
    acknowledged_audit_id  INTEGER REFERENCES admin_audit (id),
    CHECK ((acknowledged_at IS NULL) = (acknowledged_audit_id IS NULL))
) STRICT;

-- Expression index on a constant: all open rows share one key, so a second
-- open fault is rejected by the database.
CREATE UNIQUE INDEX idx_device_faults_one_open ON device_faults ((1))
WHERE acknowledged_at IS NULL;

CREATE TRIGGER device_faults_no_delete
BEFORE DELETE ON device_faults
BEGIN
    SELECT RAISE(ABORT, 'device_faults is append-only: DELETE rejected');
END;

-- Only the open -> acknowledged transition is allowed; the fault content
-- and an acknowledged fault stay unchanged.
CREATE TRIGGER device_faults_update_only_ack
BEFORE UPDATE ON device_faults
WHEN OLD.acknowledged_at IS NOT NULL
  OR NEW.fault_code IS NOT OLD.fault_code
  OR NEW.raised_at IS NOT OLD.raised_at
  OR NEW.session_id IS NOT OLD.session_id
BEGIN
    SELECT RAISE(ABORT, 'device fault may only be acknowledged once');
END;

-- An acknowledgement must point at an audit row written for the fault
-- acknowledgement itself, not at an arbitrary audit entry.
CREATE TRIGGER device_faults_ack_audit_action
BEFORE UPDATE ON device_faults
WHEN NEW.acknowledged_audit_id IS NOT NULL
 AND (
    SELECT action FROM admin_audit WHERE id = NEW.acknowledged_audit_id
 ) IS NOT 'fault_ack'
BEGIN
    SELECT RAISE(ABORT, 'acknowledgement must reference a fault_ack audit row');
END;
