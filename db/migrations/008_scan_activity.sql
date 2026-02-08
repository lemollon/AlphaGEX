-- Scan Activity Table Migration
-- Logs EVERY scan from FORTRESS and SOLOMON with full context
-- This provides complete visibility into bot behavior
-- Run: psql $DATABASE_URL -f db/migrations/008_scan_activity.sql

-- ============================================================================
-- SCAN ACTIVITY TABLE
-- Stores EVERY scan attempt with full reasoning and market context
-- This is the primary table for understanding bot behavior
-- ============================================================================

CREATE TABLE IF NOT EXISTS scan_activity (
    id SERIAL PRIMARY KEY,

    -- Identification
    bot_name VARCHAR(50) NOT NULL,  -- FORTRESS, SOLOMON
    scan_id VARCHAR(100) NOT NULL UNIQUE,  -- Unique scan identifier
    scan_number INTEGER NOT NULL,  -- Scan number for the day

    -- Timing
    timestamp TIMESTAMP NOT NULL,
    date DATE NOT NULL,
    time_ct VARCHAR(20) NOT NULL,  -- Human readable Central Time

    -- Outcome
    outcome VARCHAR(50) NOT NULL,  -- TRADED, NO_TRADE, SKIP, ERROR, MARKET_CLOSED, BEFORE_WINDOW
    action_taken VARCHAR(100),  -- What was done (e.g., "Opened Iron Condor", "Skipped - low confidence")

    -- Decision Summary (Human Readable)
    decision_summary TEXT NOT NULL,  -- One-line summary of what happened
    full_reasoning TEXT,  -- Detailed reasoning for the decision

    -- Market Conditions at Scan Time
    underlying_price DECIMAL(15, 4),
    underlying_symbol VARCHAR(10),
    vix DECIMAL(10, 4),
    expected_move DECIMAL(10, 4),

    -- GEX Context (if available)
    gex_regime VARCHAR(50),
    net_gex DECIMAL(20, 2),
    call_wall DECIMAL(15, 4),
    put_wall DECIMAL(15, 4),
    distance_to_call_wall_pct DECIMAL(10, 4),
    distance_to_put_wall_pct DECIMAL(10, 4),

    -- Signal Data
    signal_source VARCHAR(50),  -- ML, Oracle, GEX, None
    signal_direction VARCHAR(20),  -- BULLISH, BEARISH, NEUTRAL, NONE
    signal_confidence DECIMAL(5, 4),  -- 0-1
    signal_win_probability DECIMAL(5, 4),  -- 0-1

    -- Oracle Advice (if consulted)
    oracle_advice VARCHAR(50),  -- TRADE, SKIP_TODAY, REDUCE_SIZE, etc.
    oracle_reasoning TEXT,

    -- Checks Performed
    checks_performed JSONB,  -- Array of {check: string, passed: boolean, reason: string}
    all_checks_passed BOOLEAN DEFAULT TRUE,

    -- Trade Details (if traded)
    trade_executed BOOLEAN DEFAULT FALSE,
    position_id VARCHAR(100),
    strike_selection JSONB,  -- {put_strike: x, call_strike: y, etc.}
    contracts INTEGER,
    premium_collected DECIMAL(15, 4),
    max_risk DECIMAL(15, 4),

    -- Error Details (if error)
    error_message TEXT,
    error_type VARCHAR(100),

    -- Full Context (JSON blob for detailed analysis)
    full_context JSONB,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_scan_activity_bot_date ON scan_activity(bot_name, date DESC);
CREATE INDEX IF NOT EXISTS idx_scan_activity_timestamp ON scan_activity(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_scan_activity_outcome ON scan_activity(outcome);
CREATE INDEX IF NOT EXISTS idx_scan_activity_bot_timestamp ON scan_activity(bot_name, timestamp DESC);

-- ============================================================================
-- SCAN ACTIVITY SUMMARY VIEW
-- Quick view for dashboard showing recent activity
-- ============================================================================

CREATE OR REPLACE VIEW scan_activity_summary AS
SELECT
    bot_name,
    date,
    COUNT(*) as total_scans,
    COUNT(CASE WHEN trade_executed THEN 1 END) as trades_executed,
    COUNT(CASE WHEN outcome = 'NO_TRADE' THEN 1 END) as no_trade_scans,
    COUNT(CASE WHEN outcome = 'ERROR' THEN 1 END) as error_scans,
    MAX(timestamp) as last_scan,
    AVG(signal_confidence) as avg_confidence,
    AVG(vix) as avg_vix
FROM scan_activity
GROUP BY bot_name, date
ORDER BY date DESC, bot_name;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'Scan activity table created successfully' as status;

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'scan_activity'
ORDER BY ordinal_position;
