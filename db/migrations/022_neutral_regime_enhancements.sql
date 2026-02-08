-- Migration 022: NEUTRAL Regime Enhancements
-- Adds trend tracking and strategy suitability fields for enhanced NEUTRAL GEX regime handling
-- Created: 2025-01
-- Run: psql $DATABASE_URL -f db/migrations/022_neutral_regime_enhancements.sql

-- ============================================================================
-- SCAN_ACTIVITY TABLE ENHANCEMENTS
-- Add columns for NEUTRAL regime direction determination and strategy suitability
-- ============================================================================

-- NEUTRAL Regime Derived Direction
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS neutral_derived_direction VARCHAR(20);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS neutral_confidence DECIMAL(5, 4);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS neutral_reasoning TEXT;

-- Strategy Suitability Scores (0-100 scale)
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS ic_suitability DECIMAL(5, 2);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS bullish_suitability DECIMAL(5, 2);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS bearish_suitability DECIMAL(5, 2);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS recommended_strategy VARCHAR(50);

-- Trend Analysis Data (from 5-min scan history)
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS trend_direction VARCHAR(20);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS trend_strength DECIMAL(5, 4);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS position_in_range_pct DECIMAL(5, 2);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS is_contained BOOLEAN DEFAULT TRUE;
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS wall_filter_passed BOOLEAN;

-- Historical Price Points for Trend Analysis
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS price_5m_ago DECIMAL(15, 4);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS price_30m_ago DECIMAL(15, 4);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS price_60m_ago DECIMAL(15, 4);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS high_of_day DECIMAL(15, 4);
ALTER TABLE scan_activity ADD COLUMN IF NOT EXISTS low_of_day DECIMAL(15, 4);

-- Comments for documentation
COMMENT ON COLUMN scan_activity.neutral_derived_direction IS 'Direction derived for NEUTRAL GEX regime (BULLISH, BEARISH, NEUTRAL)';
COMMENT ON COLUMN scan_activity.neutral_confidence IS 'Confidence level (0-1) for NEUTRAL regime direction';
COMMENT ON COLUMN scan_activity.neutral_reasoning IS 'Human-readable explanation of NEUTRAL direction determination';
COMMENT ON COLUMN scan_activity.ic_suitability IS 'Iron Condor strategy suitability score (0-100)';
COMMENT ON COLUMN scan_activity.bullish_suitability IS 'Bullish spread strategy suitability score (0-100)';
COMMENT ON COLUMN scan_activity.bearish_suitability IS 'Bearish spread strategy suitability score (0-100)';
COMMENT ON COLUMN scan_activity.recommended_strategy IS 'Recommended strategy based on suitability scores';
COMMENT ON COLUMN scan_activity.trend_direction IS 'Price trend over rolling window (UPTREND, DOWNTREND, SIDEWAYS)';
COMMENT ON COLUMN scan_activity.trend_strength IS 'Strength of the trend (0-1)';
COMMENT ON COLUMN scan_activity.position_in_range_pct IS 'Position in put-call wall range (0=put wall, 100=call wall)';
COMMENT ON COLUMN scan_activity.is_contained IS 'Whether price is contained within put/call walls';
COMMENT ON COLUMN scan_activity.wall_filter_passed IS 'Whether wall proximity filter passed';
COMMENT ON COLUMN scan_activity.price_5m_ago IS 'Price 5 minutes ago for trend calculation';
COMMENT ON COLUMN scan_activity.price_30m_ago IS 'Price 30 minutes ago for trend calculation';
COMMENT ON COLUMN scan_activity.price_60m_ago IS 'Price 60 minutes ago for trend calculation';
COMMENT ON COLUMN scan_activity.high_of_day IS 'High of day at scan time';
COMMENT ON COLUMN scan_activity.low_of_day IS 'Low of day at scan time';

-- ============================================================================
-- ORACLE_PREDICTIONS TABLE ENHANCEMENTS (if table exists)
-- Add same fields for consistency
-- ============================================================================

DO $$
BEGIN
    -- Check if prophet_predictions table exists before adding columns
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'prophet_predictions') THEN
        -- NEUTRAL Regime Analysis
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS neutral_derived_direction VARCHAR(20);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS neutral_confidence DECIMAL(5, 4);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS neutral_reasoning TEXT;

        -- Strategy Suitability Scores
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS ic_suitability DECIMAL(5, 2);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS bullish_suitability DECIMAL(5, 2);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS bearish_suitability DECIMAL(5, 2);

        -- Trend Data
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS trend_direction VARCHAR(20);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS trend_strength DECIMAL(5, 4);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS position_in_range_pct DECIMAL(5, 2);
        ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS wall_filter_passed BOOLEAN;

        RAISE NOTICE 'Added NEUTRAL regime columns to prophet_predictions table';
    END IF;
END $$;

-- ============================================================================
-- INDEXES FOR EFFICIENT QUERYING
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_scan_activity_trend ON scan_activity(trend_direction);
CREATE INDEX IF NOT EXISTS idx_scan_activity_neutral_direction ON scan_activity(neutral_derived_direction);
CREATE INDEX IF NOT EXISTS idx_scan_activity_ic_suitability ON scan_activity(ic_suitability DESC);
CREATE INDEX IF NOT EXISTS idx_scan_activity_contained ON scan_activity(is_contained);

-- ============================================================================
-- VERIFICATION
-- ============================================================================

SELECT 'NEUTRAL regime enhancement columns added successfully' as status;

-- Show new columns in scan_activity
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'scan_activity'
  AND column_name IN (
    'neutral_derived_direction', 'neutral_confidence', 'neutral_reasoning',
    'ic_suitability', 'bullish_suitability', 'bearish_suitability', 'recommended_strategy',
    'trend_direction', 'trend_strength', 'position_in_range_pct', 'is_contained',
    'wall_filter_passed', 'price_5m_ago', 'price_30m_ago', 'price_60m_ago',
    'high_of_day', 'low_of_day'
  )
ORDER BY column_name;
