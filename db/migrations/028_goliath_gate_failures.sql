-- Migration 028: GOLIATH gate-failure audit table
--
-- Per master spec section 2 (gate logging requirements), every failed
-- pre-entry gate evaluation persists a row here for diagnostic review.
-- Phase 9 paper-trading acceptance hinges on these rows being
-- diagnostic-rich enough that "zero successful trades" runs are
-- still informative (see master spec section 9.3).

CREATE TABLE IF NOT EXISTS goliath_gate_failures (
    id                          BIGSERIAL PRIMARY KEY,
    timestamp                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    letf_ticker                 VARCHAR(10) NOT NULL,
    underlying_ticker           VARCHAR(10) NOT NULL,
    failed_gate                 VARCHAR(8)  NOT NULL,
    failure_outcome             VARCHAR(32) NOT NULL,
    gates_passed_before_failure JSONB       NOT NULL DEFAULT '[]'::JSONB,
    attempted_structure         JSONB,
    failure_reason              TEXT        NOT NULL,
    context                     JSONB       NOT NULL DEFAULT '{}'::JSONB
);

-- failed_gate is a CHECK-ish enum at the app layer (G01..G10).
-- failure_outcome mirrors GateOutcome enum: FAIL or INSUFFICIENT_HISTORY.

CREATE INDEX IF NOT EXISTS idx_goliath_gate_failures_letf_ts
    ON goliath_gate_failures (letf_ticker, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_goliath_gate_failures_failed_gate
    ON goliath_gate_failures (failed_gate, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_goliath_gate_failures_underlying_ts
    ON goliath_gate_failures (underlying_ticker, timestamp DESC);

COMMENT ON TABLE goliath_gate_failures IS
    'Audit log: every failed GOLIATH pre-entry gate evaluation. '
    'Per master spec section 2, populated whenever the orchestrator '
    'stops the chain at a non-PASS gate. Read by paper-trading '
    'diagnostic reports (spec section 9.3).';
