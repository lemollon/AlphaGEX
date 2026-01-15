-- Performance Optimization Indexes
-- Generated from PERFORMANCE_ANALYSIS.md recommendations
-- Run this migration to improve query performance for common operations
-- Note: Uses IF NOT EXISTS and DO blocks to handle missing columns/tables gracefully

-- ============================================================================
-- CRITICAL: Indexes for frequently queried tables
-- ============================================================================

-- autonomous_open_positions: Used in position management, portfolio views
-- Check if status column exists before creating index
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'autonomous_open_positions' AND column_name = 'status') THEN
        CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_status
            ON autonomous_open_positions(status);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_entry_date
    ON autonomous_open_positions(entry_date DESC);

-- autonomous_closed_trades: Used in P&L calculations, trade history
CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_exit_date
    ON autonomous_closed_trades(exit_date DESC);

CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_strategy
    ON autonomous_closed_trades(strategy);

-- autonomous_trader_logs: Used in logs_routes.py summary
CREATE INDEX IF NOT EXISTS idx_autonomous_trader_logs_timestamp
    ON autonomous_trader_logs(timestamp DESC);

-- ml_decision_logs: Used in AI decision auditing
CREATE INDEX IF NOT EXISTS idx_ml_decision_logs_timestamp
    ON ml_decision_logs(timestamp DESC);

-- ============================================================================
-- HIGH: Indexes for bot-specific tables
-- ============================================================================

-- ares_positions: ARES Iron Condor bot positions
CREATE INDEX IF NOT EXISTS idx_ares_positions_open_time
    ON ares_positions(open_time DESC);

CREATE INDEX IF NOT EXISTS idx_ares_positions_status
    ON ares_positions(status);

-- athena_positions: ATHENA Directional Spreads positions
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'athena_positions') THEN
        CREATE INDEX IF NOT EXISTS idx_athena_positions_open_time
            ON athena_positions(open_time DESC);
        CREATE INDEX IF NOT EXISTS idx_athena_positions_status
            ON athena_positions(status);
    END IF;
END $$;

-- pegasus_positions: PEGASUS SPX Iron Condor positions
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'pegasus_positions') THEN
        CREATE INDEX IF NOT EXISTS idx_pegasus_positions_open_time
            ON pegasus_positions(open_time DESC);
        CREATE INDEX IF NOT EXISTS idx_pegasus_positions_status
            ON pegasus_positions(status);
    END IF;
END $$;

-- ============================================================================
-- MEDIUM: Indexes for historical data tables
-- ============================================================================

-- gex_history: Used in GEX analysis endpoints
CREATE INDEX IF NOT EXISTS idx_gex_history_symbol_timestamp
    ON gex_history(symbol, timestamp DESC);

-- gamma_history: Used in ARGUS gamma visualization (check column name)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'gamma_history' AND column_name = 'recorded_at') THEN
        CREATE INDEX IF NOT EXISTS idx_gamma_history_recorded_at
            ON gamma_history(recorded_at DESC);
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'gamma_history' AND column_name = 'timestamp') THEN
        CREATE INDEX IF NOT EXISTS idx_gamma_history_timestamp
            ON gamma_history(timestamp DESC);
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'gamma_history' AND column_name = 'created_at') THEN
        CREATE INDEX IF NOT EXISTS idx_gamma_history_created_at
            ON gamma_history(created_at DESC);
    END IF;
END $$;

-- regime_classifications: Used in regime detection (check column name)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'regime_classifications' AND column_name = 'timestamp') THEN
        CREATE INDEX IF NOT EXISTS idx_regime_classifications_timestamp
            ON regime_classifications(timestamp DESC);
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'regime_classifications' AND column_name = 'created_at') THEN
        CREATE INDEX IF NOT EXISTS idx_regime_classifications_created_at
            ON regime_classifications(created_at DESC);
    END IF;
END $$;

-- autonomous_equity_snapshots: Used in performance tracking (check column name)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'autonomous_equity_snapshots' AND column_name = 'timestamp') THEN
        CREATE INDEX IF NOT EXISTS idx_autonomous_equity_snapshots_timestamp
            ON autonomous_equity_snapshots(timestamp DESC);
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name = 'autonomous_equity_snapshots' AND column_name = 'created_at') THEN
        CREATE INDEX IF NOT EXISTS idx_autonomous_equity_snapshots_created_at
            ON autonomous_equity_snapshots(created_at DESC);
    END IF;
END $$;

-- ============================================================================
-- LOW: Indexes for scan activity tables (only if tables exist)
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ares_scan_activity') THEN
        CREATE INDEX IF NOT EXISTS idx_ares_scan_activity_timestamp
            ON ares_scan_activity(timestamp DESC);
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'athena_scan_activity') THEN
        CREATE INDEX IF NOT EXISTS idx_athena_scan_activity_timestamp
            ON athena_scan_activity(timestamp DESC);
    END IF;
END $$;

-- ============================================================================
-- Composite indexes for common query patterns
-- ============================================================================

-- For filtering by date range and status
CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_date_strategy
    ON autonomous_closed_trades(exit_date, strategy);

-- For portfolio aggregation queries (check if status column exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name = 'autonomous_open_positions' AND column_name = 'status') THEN
        CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_strategy_status
            ON autonomous_open_positions(strategy, status);
    END IF;
END $$;

-- ============================================================================
-- ANALYZE to update statistics after index creation
-- ============================================================================
ANALYZE autonomous_open_positions;
ANALYZE autonomous_closed_trades;
ANALYZE autonomous_trader_logs;
ANALYZE autonomous_equity_snapshots;

-- Print completion message
DO $$
BEGIN
    RAISE NOTICE 'Performance indexes created successfully';
END $$;
