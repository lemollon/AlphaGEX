-- HELIOS — bot tables (8) for live paper trading.
-- All idempotent (CREATE TABLE IF NOT EXISTS). New tables only — no existing
-- tables touched. Mirrors the solomon_*/gideon_* shape.

-- 1. config: per-bot config overrides
CREATE TABLE IF NOT EXISTS helios_config (
    key         TEXT        PRIMARY KEY,
    value       JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. paper account state
CREATE TABLE IF NOT EXISTS helios_paper_account (
    id                SERIAL       PRIMARY KEY,
    starting_capital  NUMERIC(12,2) NOT NULL,
    cash              NUMERIC(12,2) NOT NULL,
    realized_pnl      NUMERIC(12,2) NOT NULL DEFAULT 0,
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 3. signals: every scan cycle (TRADE or SKIP)
CREATE TABLE IF NOT EXISTS helios_signals (
    id            BIGSERIAL    PRIMARY KEY,
    cycle_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    action        TEXT         NOT NULL,       -- 'TRADE' or 'SKIP'
    spread_type   TEXT,                        -- 'BULL_CALL' / 'BEAR_PUT' on TRADE
    long_strike   NUMERIC(8,2),
    short_strike  NUMERIC(8,2),
    skip_reason   TEXT,                        -- enum value on SKIP
    detail        TEXT,
    spot          NUMERIC(8,2),
    vix           NUMERIC(6,2)
);
CREATE INDEX IF NOT EXISTS ix_helios_signals_cycle ON helios_signals(cycle_at DESC);

-- 4. positions: open + closed
CREATE TABLE IF NOT EXISTS helios_positions (
    id               BIGSERIAL    PRIMARY KEY,
    spread_type      TEXT         NOT NULL,
    long_symbol      TEXT         NOT NULL,
    short_symbol     TEXT         NOT NULL,
    long_strike      NUMERIC(8,2) NOT NULL,
    short_strike     NUMERIC(8,2) NOT NULL,
    expiration_date  DATE         NOT NULL,
    contracts        INTEGER      NOT NULL,
    debit            NUMERIC(8,4) NOT NULL,
    open_time        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    close_time       TIMESTAMPTZ,
    close_price      NUMERIC(8,4),
    realized_pnl     NUMERIC(10,2),
    exit_reason      TEXT,
    status           TEXT         NOT NULL DEFAULT 'OPEN'
);
CREATE INDEX IF NOT EXISTS ix_helios_positions_status      ON helios_positions(status);
CREATE INDEX IF NOT EXISTS ix_helios_positions_close_time  ON helios_positions(close_time);
CREATE INDEX IF NOT EXISTS ix_helios_positions_open_time   ON helios_positions(open_time DESC);

-- 5. equity snapshots: periodic (every 5-min cycle)
CREATE TABLE IF NOT EXISTS helios_equity_snapshots (
    id                  BIGSERIAL    PRIMARY KEY,
    snapshot_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    equity              NUMERIC(12,2) NOT NULL,
    cash                NUMERIC(12,2) NOT NULL,
    unrealized_pnl      NUMERIC(12,2) NOT NULL,
    open_position_count INTEGER      NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_helios_equity_snapshots_at ON helios_equity_snapshots(snapshot_at DESC);

-- 6. daily perf rollup
CREATE TABLE IF NOT EXISTS helios_daily_perf (
    trade_date     DATE         PRIMARY KEY,
    trades         INTEGER      NOT NULL,
    wins           INTEGER      NOT NULL,
    losses         INTEGER      NOT NULL,
    realized_pnl   NUMERIC(10,2) NOT NULL,
    cumulative_pnl NUMERIC(12,2) NOT NULL
);

-- 7. activity log
CREATE TABLE IF NOT EXISTS helios_logs (
    id         BIGSERIAL    PRIMARY KEY,
    logged_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    level      TEXT         NOT NULL,
    message    TEXT         NOT NULL,
    detail     JSONB
);
CREATE INDEX IF NOT EXISTS ix_helios_logs_at ON helios_logs(logged_at DESC);

-- 8. scan activity (every cycle, both TRADE and SKIP)
CREATE TABLE IF NOT EXISTS helios_scan_activity (
    id         BIGSERIAL    PRIMARY KEY,
    cycle_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    outcome    TEXT         NOT NULL,
    detail     TEXT
);
CREATE INDEX IF NOT EXISTS ix_helios_scan_activity_at ON helios_scan_activity(cycle_at DESC);

-- Seed paper account at $10,000 starting capital (idempotent: skip if any row exists)
INSERT INTO helios_paper_account (starting_capital, cash)
SELECT 10000, 10000
WHERE NOT EXISTS (SELECT 1 FROM helios_paper_account);
