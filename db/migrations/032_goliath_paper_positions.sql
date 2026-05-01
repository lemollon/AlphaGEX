-- Migration 032: GOLIATH paper-trading positions table
--
-- Per Phase 7+ paper-trading wiring (PR-α 2026-05-01). The audit log
-- (goliath_trade_audit, migration 031) is append-only event history and
-- cannot answer "what positions are open right now?" efficiently. This
-- table holds CURRENT POSITION STATE so the runner can refresh quotes
-- and run management triggers cycle-by-cycle.
--
-- One row per filled paper trade. Lifecycle:
--   ENTRY_FILLED  -> INSERT row, state=OPEN
--   T1-T8 fired   -> UPDATE state=CLOSING (mid-flight broker close)
--   EXIT_FILLED   -> UPDATE state=CLOSED + realized_pnl + closed_at
--
-- v0.2 paper-only; v0.3+ may use this same table for live positions.

CREATE TABLE IF NOT EXISTS goliath_paper_positions (
    id BIGSERIAL PRIMARY KEY,
    position_id VARCHAR(64) NOT NULL UNIQUE,
    instance_name VARCHAR(20) NOT NULL,           -- e.g. GOLIATH-MSTU
    letf_ticker VARCHAR(10) NOT NULL,
    underlying_ticker VARCHAR(10) NOT NULL,

    -- Lifecycle
    state VARCHAR(20) NOT NULL DEFAULT 'OPEN' CHECK (state IN (
        'OPEN', 'MANAGING', 'CLOSING', 'CLOSED'
    )),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    expiration_date DATE NOT NULL,

    -- Strikes (3-leg structure, snapshotted at entry)
    short_put_strike DECIMAL(10, 2) NOT NULL,
    long_put_strike DECIMAL(10, 2) NOT NULL,
    long_call_strike DECIMAL(10, 2) NOT NULL,

    -- Entry economics (snapshotted)
    contracts INTEGER NOT NULL,
    entry_short_put_mid DECIMAL(10, 4) NOT NULL,
    entry_long_put_mid DECIMAL(10, 4) NOT NULL,
    entry_long_call_mid DECIMAL(10, 4) NOT NULL,
    entry_put_spread_credit DECIMAL(10, 4) NOT NULL,
    entry_long_call_cost DECIMAL(10, 4) NOT NULL,
    entry_net_cost DECIMAL(10, 4) NOT NULL,
    defined_max_loss DECIMAL(10, 4) NOT NULL,

    -- Regime context for T8 (GEX flip trigger)
    entry_underlying_gex_regime VARCHAR(20),

    -- Close details (populated on exit)
    close_trigger_id VARCHAR(8),                  -- T1..T8 or MANUAL
    close_short_put_mid DECIMAL(10, 4),
    close_long_put_mid DECIMAL(10, 4),
    close_long_call_mid DECIMAL(10, 4),
    realized_pnl DECIMAL(12, 4),

    -- Audit cross-reference
    entry_audit_id BIGINT,                        -- FK to goliath_trade_audit.id
    exit_audit_id BIGINT
);

-- Hot-path lookups
CREATE INDEX IF NOT EXISTS idx_goliath_paper_positions_open
    ON goliath_paper_positions (instance_name, state)
    WHERE state IN ('OPEN', 'MANAGING', 'CLOSING');

CREATE INDEX IF NOT EXISTS idx_goliath_paper_positions_opened_at
    ON goliath_paper_positions (opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_goliath_paper_positions_closed_at
    ON goliath_paper_positions (closed_at DESC)
    WHERE closed_at IS NOT NULL;

COMMENT ON TABLE goliath_paper_positions IS
    'Current+historical paper-trading position state for GOLIATH. '
    'Append on entry, mutate on close. Distinct from goliath_trade_audit '
    'which is append-only event history.';
