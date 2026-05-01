-- Migration 031: GOLIATH trade audit log
--
-- Per master spec section 10.1 + Leron Q2: append-only Postgres audit
-- of every trade event (entry eval, entry filled, mgmt eval, exit filled).
-- Append-only is enforced at the application layer (no UPDATE/DELETE
-- in the recorder); future v0.3 may add chain-integrity hashes.
--
-- position_id is a string identifier (not yet an FK -- positions table
-- lands with Phase 6 main runner; will retrofit FK in a later migration
-- once the runner persists positions to its own table).

CREATE TABLE IF NOT EXISTS goliath_trade_audit (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    instance    VARCHAR(20) NOT NULL,
    event_type  VARCHAR(32) NOT NULL CHECK (event_type IN (
        'ENTRY_EVAL', 'ENTRY_FILLED', 'MANAGEMENT_EVAL', 'EXIT_FILLED'
    )),
    data        JSONB NOT NULL DEFAULT '{}'::JSONB,
    position_id VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_goliath_trade_audit_instance_ts
    ON goliath_trade_audit (instance, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_goliath_trade_audit_position
    ON goliath_trade_audit (position_id, timestamp ASC)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_goliath_trade_audit_event_type_ts
    ON goliath_trade_audit (event_type, timestamp DESC);

COMMENT ON TABLE goliath_trade_audit IS
    'Append-only audit log of every GOLIATH trade event. Per master '
    'spec section 10.1: entry inputs, gate outcomes, strike selection, '
    'broker interactions, management decisions, exit P&L. Replayable '
    'via trading.goliath.audit.replayer for post-hoc analysis.';
