-- Migration 033: GOLIATH equity snapshots
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

CREATE TABLE IF NOT EXISTS goliath_equity_snapshots (
    id BIGSERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scope VARCHAR(10) NOT NULL CHECK (scope IN ('INSTANCE', 'PLATFORM')),
    instance_name VARCHAR(20),                    -- NULL for scope='PLATFORM'
    starting_capital DECIMAL(12, 2) NOT NULL,
    cumulative_realized_pnl DECIMAL(12, 4) NOT NULL DEFAULT 0,
    unrealized_pnl DECIMAL(12, 4) NOT NULL DEFAULT 0,
    open_position_count INTEGER NOT NULL DEFAULT 0,
    equity DECIMAL(12, 4) NOT NULL,               -- = starting + cumulative + unrealized
    CONSTRAINT goliath_equity_scope_consistency
        CHECK ((scope = 'PLATFORM' AND instance_name IS NULL)
            OR (scope = 'INSTANCE' AND instance_name IS NOT NULL))
);

-- Hot-path: dashboard reads "latest snapshot per instance" and "today's
-- snapshots for the chart". Composite index covers both.
CREATE INDEX IF NOT EXISTS idx_goliath_equity_snapshots_instance_ts
    ON goliath_equity_snapshots (instance_name, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_goliath_equity_snapshots_scope_ts
    ON goliath_equity_snapshots (scope, snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_goliath_equity_snapshots_platform_ts
    ON goliath_equity_snapshots (snapshot_at DESC)
    WHERE scope = 'PLATFORM';

COMMENT ON TABLE goliath_equity_snapshots IS
    'Periodic equity-curve snapshots for GOLIATH instances + platform '
    'aggregate. Read by the dashboard equity-curve endpoints. Written '
    'by the runner each management cycle.';
