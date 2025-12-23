-- ARGUS Danger Zone Logs Migration
-- Creates table for tracking danger zone history over time
-- Run: psql $DATABASE_URL -f db/migrations/007_argus_danger_zone_logs.sql

-- ============================================================================
-- ARGUS DANGER ZONE LOGS TABLE
-- Stores historical danger zone events for real-time display
-- ============================================================================
CREATE TABLE IF NOT EXISTS argus_danger_zone_logs (
    id SERIAL PRIMARY KEY,

    -- Event timing
    detected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expiration_date DATE NOT NULL,

    -- Strike data
    strike DECIMAL(10,2) NOT NULL,
    danger_type VARCHAR(20) NOT NULL,  -- BUILDING, COLLAPSING, SPIKE

    -- Rate of change at detection
    roc_1min DECIMAL(10,4),
    roc_5min DECIMAL(10,4),
    net_gamma DECIMAL(20,4),

    -- Price context
    spot_price DECIMAL(10,2),
    distance_from_spot_pct DECIMAL(5,2),

    -- Status tracking
    resolved_at TIMESTAMP WITH TIME ZONE,  -- When danger zone cleared
    is_active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_danger_zone_logs_detected ON argus_danger_zone_logs(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_danger_zone_logs_active ON argus_danger_zone_logs(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_danger_zone_logs_strike ON argus_danger_zone_logs(strike);
CREATE INDEX IF NOT EXISTS idx_danger_zone_logs_type ON argus_danger_zone_logs(danger_type);
CREATE INDEX IF NOT EXISTS idx_danger_zone_logs_date ON argus_danger_zone_logs(expiration_date);

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'ARGUS danger zone logs table created successfully' as status;
