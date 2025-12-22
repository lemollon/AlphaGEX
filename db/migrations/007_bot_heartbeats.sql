-- Bot Heartbeats Table Migration
-- Tracks bot health, scan activity, and status for dashboard visibility
-- Run: psql $DATABASE_URL -f db/migrations/007_bot_heartbeats.sql

-- ============================================================================
-- BOT HEARTBEATS TABLE
-- Stores last scan time, status, and scan count for each trading bot
-- Used by dashboard to show bot health and activity
-- ============================================================================

CREATE TABLE IF NOT EXISTS bot_heartbeats (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(50) NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL,
    scan_count INTEGER DEFAULT 0,
    trades_today INTEGER DEFAULT 0,
    last_trade_time TIMESTAMP,
    details JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bot_name)
);

-- Index for quick lookups by bot name
CREATE INDEX IF NOT EXISTS idx_bot_heartbeats_bot_name
ON bot_heartbeats(bot_name);

-- Index for querying recent heartbeats
CREATE INDEX IF NOT EXISTS idx_bot_heartbeats_last_heartbeat
ON bot_heartbeats(last_heartbeat DESC);

-- ============================================================================
-- DECISION LOGS TABLE ENHANCEMENT
-- Ensure decision_logs table exists for NO_TRADE logging
-- ============================================================================

CREATE TABLE IF NOT EXISTS decision_logs (
    id SERIAL PRIMARY KEY,
    decision_id VARCHAR(100) UNIQUE NOT NULL,
    bot_name VARCHAR(50) NOT NULL,
    symbol VARCHAR(20),
    decision_type VARCHAR(50) NOT NULL,
    action VARCHAR(50),
    what TEXT,
    why TEXT,
    how TEXT,
    timestamp TIMESTAMP NOT NULL,
    actual_pnl DECIMAL(15, 2),
    outcome_notes TEXT,
    underlying_price_at_entry DECIMAL(15, 4),
    underlying_price_at_exit DECIMAL(15, 4),
    market_context JSONB,
    gex_context JSONB,
    oracle_advice JSONB,
    ml_predictions JSONB,
    backtest_stats JSONB,
    position_sizing JSONB,
    risk_checks JSONB,
    alternatives JSONB,
    legs JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for querying decisions by bot
CREATE INDEX IF NOT EXISTS idx_decision_logs_bot_name
ON decision_logs(bot_name);

-- Index for querying recent decisions
CREATE INDEX IF NOT EXISTS idx_decision_logs_timestamp
ON decision_logs(timestamp DESC);

-- Index for querying by decision type (ENTRY_SIGNAL, EXIT_SIGNAL, NO_TRADE)
CREATE INDEX IF NOT EXISTS idx_decision_logs_decision_type
ON decision_logs(decision_type);

-- Composite index for dashboard queries (bot + recent + type)
CREATE INDEX IF NOT EXISTS idx_decision_logs_bot_recent
ON decision_logs(bot_name, timestamp DESC);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'Bot heartbeats and decision logs tables created successfully' as status;

-- Show table structure
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'bot_heartbeats'
ORDER BY ordinal_position;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'decision_logs'
ORDER BY ordinal_position;
