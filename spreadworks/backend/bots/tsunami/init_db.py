"""Idempotent schema bootstrap for TSUNAMI's six tables.

The AlphaGEX original applied these as SQL migrations 028-033
(scripts/apply_goliath_migrations.py). SpreadWorks has no migration
framework -- its convention is ensure-at-startup (see backend._ensure_schema)
-- so the same DDL, renamed tsunami_*, runs here behind CREATE TABLE IF NOT
EXISTS. Called once from the scheduler hook before jobs are registered.
Shares alphagex-db with the rest of the platform; the retired goliath_*
tables are left untouched.
"""
from __future__ import annotations

import logging

from backend.bots.tsunami.db_compat import get_connection, is_database_available

logger = logging.getLogger(__name__)

_SCHEMA_SQL = """
-- from migrations\028_goliath_gate_failures.sql
-- Migration 028: TSUNAMI gate-failure audit table
--
-- Per master spec section 2 (gate logging requirements), every failed
-- pre-entry gate evaluation persists a row here for diagnostic review.
-- Phase 9 paper-trading acceptance hinges on these rows being
-- diagnostic-rich enough that "zero successful trades" runs are
-- still informative (see master spec section 9.3).

CREATE TABLE IF NOT EXISTS tsunami_gate_failures (
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

CREATE INDEX IF NOT EXISTS idx_tsunami_gate_failures_letf_ts
    ON tsunami_gate_failures (letf_ticker, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tsunami_gate_failures_failed_gate
    ON tsunami_gate_failures (failed_gate, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tsunami_gate_failures_underlying_ts
    ON tsunami_gate_failures (underlying_ticker, timestamp DESC);

COMMENT ON TABLE tsunami_gate_failures IS
    'Audit log: every failed TSUNAMI pre-entry gate evaluation. '
    'Per master spec section 2, populated whenever the orchestrator '
    'stops the chain at a non-PASS gate. Read by paper-trading '
    'diagnostic reports (spec section 9.3).';

-- from migrations\029_goliath_news_flags.sql
-- Migration 029: TSUNAMI material-news flag table
--
-- Per master spec section 4 trigger 6 + Leron Q5 (2026-04-29):
-- material-news flagging is a manual CLI action on the Render shell.
-- A flag persists until manually cleared; while present, T6 fires
-- on every management cycle for any open position on that ticker.
--
-- Ticker is the *underlying* per spec (TSLA news -> close TSLL position).

CREATE TABLE IF NOT EXISTS tsunami_news_flags (
    ticker      VARCHAR(10) PRIMARY KEY,
    reason      TEXT NOT NULL DEFAULT '',
    flagged_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    flagged_by  TEXT NOT NULL DEFAULT 'cli'
);

COMMENT ON TABLE tsunami_news_flags IS
    'Manual material-news flags driving T6 trigger fires. '
    'CLI-managed (trading.tsunami.management.cli). One row per '
    'ticker; presence = active flag; row removal = unflag.';

-- from migrations\030_goliath_kill_state.sql
-- Migration 030: TSUNAMI kill-switch state
--
-- Per master spec section 6 + Phase 5 acceptance criteria:
-- kill state must persist across process restarts. One active row per
-- (scope, instance_name); manual override clears active flag.
--
-- scope = 'INSTANCE'  -> instance_name is one of MSTU/TSLL/NVDL/CONL/AMDL
-- scope = 'PLATFORM'  -> instance_name is NULL (kill applies to all instances)

CREATE TABLE IF NOT EXISTS tsunami_kill_state (
    id              BIGSERIAL PRIMARY KEY,
    scope           VARCHAR(10) NOT NULL CHECK (scope IN ('INSTANCE', 'PLATFORM')),
    instance_name   VARCHAR(20),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    trigger_id      VARCHAR(8) NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    context         JSONB NOT NULL DEFAULT '{}'::JSONB,
    killed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at      TIMESTAMPTZ,
    cleared_by      TEXT,
    CONSTRAINT tsunami_kill_scope_consistency
        CHECK ((scope = 'PLATFORM' AND instance_name IS NULL)
            OR (scope = 'INSTANCE' AND instance_name IS NOT NULL))
);

-- Fast lookup: "is this scope currently killed?"
CREATE INDEX IF NOT EXISTS idx_tsunami_kill_state_active
    ON tsunami_kill_state (scope, instance_name)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_tsunami_kill_state_killed_at
    ON tsunami_kill_state (killed_at DESC);

COMMENT ON TABLE tsunami_kill_state IS
    'Persistent kill-switch state per master spec section 6. '
    'One active row per (scope, instance_name); manual override '
    'sets active=FALSE + cleared_at/cleared_by.';

-- from migrations\031_goliath_trade_audit.sql
-- Migration 031: TSUNAMI trade audit log
--
-- Per master spec section 10.1 + Leron Q2: append-only Postgres audit
-- of every trade event (entry eval, entry filled, mgmt eval, exit filled).
-- Append-only is enforced at the application layer (no UPDATE/DELETE
-- in the recorder); future v0.3 may add chain-integrity hashes.
--
-- position_id is a string identifier (not yet an FK -- positions table
-- lands with Phase 6 main runner; will retrofit FK in a later migration
-- once the runner persists positions to its own table).

CREATE TABLE IF NOT EXISTS tsunami_trade_audit (
    id          BIGSERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    instance    VARCHAR(20) NOT NULL,
    event_type  VARCHAR(32) NOT NULL CHECK (event_type IN (
        'ENTRY_EVAL', 'ENTRY_FILLED', 'MANAGEMENT_EVAL', 'EXIT_FILLED'
    )),
    data        JSONB NOT NULL DEFAULT '{}'::JSONB,
    position_id VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_tsunami_trade_audit_instance_ts
    ON tsunami_trade_audit (instance, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_tsunami_trade_audit_position
    ON tsunami_trade_audit (position_id, timestamp ASC)
    WHERE position_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tsunami_trade_audit_event_type_ts
    ON tsunami_trade_audit (event_type, timestamp DESC);

COMMENT ON TABLE tsunami_trade_audit IS
    'Append-only audit log of every TSUNAMI trade event. Per master '
    'spec section 10.1: entry inputs, gate outcomes, strike selection, '
    'broker interactions, management decisions, exit P&L. Replayable '
    'via trading.tsunami.audit.replayer for post-hoc analysis.';

-- from migrations\032_goliath_paper_positions.sql
-- Migration 032: TSUNAMI paper-trading positions table
--
-- Per Phase 7+ paper-trading wiring (PR-α 2026-05-01). The audit log
-- (tsunami_trade_audit, migration 031) is append-only event history and
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

CREATE TABLE IF NOT EXISTS tsunami_paper_positions (
    id BIGSERIAL PRIMARY KEY,
    position_id VARCHAR(64) NOT NULL UNIQUE,
    instance_name VARCHAR(20) NOT NULL,           -- e.g. TSUNAMI-MSTU
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
    entry_audit_id BIGINT,                        -- FK to tsunami_trade_audit.id
    exit_audit_id BIGINT
);

-- Hot-path lookups
CREATE INDEX IF NOT EXISTS idx_tsunami_paper_positions_open
    ON tsunami_paper_positions (instance_name, state)
    WHERE state IN ('OPEN', 'MANAGING', 'CLOSING');

CREATE INDEX IF NOT EXISTS idx_tsunami_paper_positions_opened_at
    ON tsunami_paper_positions (opened_at DESC);

CREATE INDEX IF NOT EXISTS idx_tsunami_paper_positions_closed_at
    ON tsunami_paper_positions (closed_at DESC)
    WHERE closed_at IS NOT NULL;

COMMENT ON TABLE tsunami_paper_positions IS
    'Current+historical paper-trading position state for TSUNAMI. '
    'Append on entry, mutate on close. Distinct from tsunami_trade_audit '
    'which is append-only event history.';

-- from migrations\033_goliath_equity_snapshots.sql
-- Migration 033: TSUNAMI equity snapshots
--
-- Per master spec section 9.2 + AlphaGEX bot-completeness (every bot
-- must have an equity-curve/intraday endpoint that reads snapshots).
-- This table holds periodic equity points so the dashboard can render
-- intraday + historical equity curves.
--
-- Per-instance + platform-aggregate rows. Writer is the Phase 7+
-- monitoring path -- one snapshot per management cycle (~5 min during
-- market hours).
--
-- equity = starting_capital + cumulative_realized_pnl + unrealized_pnl
-- where unrealized_pnl is mark-to-market of currently-open positions.

CREATE TABLE IF NOT EXISTS tsunami_equity_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scope VARCHAR(10) NOT NULL CHECK (scope IN ('INSTANCE', 'PLATFORM')),
    instance_name VARCHAR(20),                    -- NULL for scope='PLATFORM'
    starting_capital DECIMAL(12, 2) NOT NULL,
    cumulative_realized_pnl DECIMAL(12, 4) NOT NULL DEFAULT 0,
    unrealized_pnl DECIMAL(12, 4) NOT NULL DEFAULT 0,
    open_position_count INTEGER NOT NULL DEFAULT 0,
    equity DECIMAL(12, 4) NOT NULL,               -- = starting + cumulative + unrealized
    CONSTRAINT tsunami_equity_scope_consistency
        CHECK ((scope = 'PLATFORM' AND instance_name IS NULL)
            OR (scope = 'INSTANCE' AND instance_name IS NOT NULL))
);

-- Hot-path: dashboard reads "latest snapshot per instance" and "today's
-- snapshots for the chart". Composite index covers both.
CREATE INDEX IF NOT EXISTS idx_tsunami_equity_snapshots_instance_ts
    ON tsunami_equity_snapshots (instance_name, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_tsunami_equity_snapshots_scope_ts
    ON tsunami_equity_snapshots (scope, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_tsunami_equity_snapshots_platform_ts
    ON tsunami_equity_snapshots (snapshot_at DESC)
    WHERE scope = 'PLATFORM';

COMMENT ON TABLE tsunami_equity_snapshots IS
    'Periodic equity-curve snapshots for TSUNAMI instances + platform '
    'aggregate. Read by the dashboard equity-curve endpoints. Written '
    'by the runner each management cycle.';
"""


def ensure_tables() -> bool:
    """Create TSUNAMI tables if missing. Returns True on success."""
    if not is_database_available():
        logger.warning("[tsunami.init_db] database unavailable -- tables not ensured")
        return False
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(_SCHEMA_SQL)
        conn.commit()
        logger.info("[tsunami.init_db] schema ensured (6 tables)")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami.init_db] schema ensure failed: %r", exc)
        try:
            if conn is not None:
                conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001
            pass
