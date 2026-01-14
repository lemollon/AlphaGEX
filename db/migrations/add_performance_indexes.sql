-- Performance Optimization Indexes
-- Generated from PERFORMANCE_ANALYSIS.md recommendations
-- Run this migration to improve query performance for common operations

-- ============================================================================
-- CRITICAL: Indexes for frequently queried tables
-- ============================================================================

-- autonomous_open_positions: Used in position management, portfolio views
CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_status
    ON autonomous_open_positions(status);

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
CREATE INDEX IF NOT EXISTS idx_athena_positions_open_time
    ON athena_positions(open_time DESC);

CREATE INDEX IF NOT EXISTS idx_athena_positions_status
    ON athena_positions(status);

-- pegasus_positions: PEGASUS SPX Iron Condor positions
CREATE INDEX IF NOT EXISTS idx_pegasus_positions_open_time
    ON pegasus_positions(open_time DESC);

CREATE INDEX IF NOT EXISTS idx_pegasus_positions_status
    ON pegasus_positions(status);

-- ============================================================================
-- MEDIUM: Indexes for historical data tables
-- ============================================================================

-- gex_history: Used in GEX analysis endpoints
CREATE INDEX IF NOT EXISTS idx_gex_history_symbol_timestamp
    ON gex_history(symbol, timestamp DESC);

-- gamma_history: Used in ARGUS gamma visualization
CREATE INDEX IF NOT EXISTS idx_gamma_history_recorded_at
    ON gamma_history(recorded_at DESC);

-- regime_classifications: Used in regime detection
CREATE INDEX IF NOT EXISTS idx_regime_classifications_timestamp
    ON regime_classifications(timestamp DESC);

-- autonomous_equity_snapshots: Used in performance tracking
CREATE INDEX IF NOT EXISTS idx_autonomous_equity_snapshots_timestamp
    ON autonomous_equity_snapshots(timestamp DESC);

-- ============================================================================
-- LOW: Indexes for scan activity tables
-- ============================================================================

-- ares_scan_activity: Used in DashboardScanFeed
CREATE INDEX IF NOT EXISTS idx_ares_scan_activity_timestamp
    ON ares_scan_activity(timestamp DESC);

-- athena_scan_activity: Used in DashboardScanFeed
CREATE INDEX IF NOT EXISTS idx_athena_scan_activity_timestamp
    ON athena_scan_activity(timestamp DESC);

-- ============================================================================
-- Composite indexes for common query patterns
-- ============================================================================

-- For filtering by date range and status
CREATE INDEX IF NOT EXISTS idx_autonomous_closed_trades_date_strategy
    ON autonomous_closed_trades(exit_date, strategy);

-- For portfolio aggregation queries
CREATE INDEX IF NOT EXISTS idx_autonomous_open_positions_strategy_status
    ON autonomous_open_positions(strategy, status);

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
