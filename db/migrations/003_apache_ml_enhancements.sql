-- APACHE ML Enhancements Migration
-- Adds ML model prediction columns to apache_signals table
-- Run: psql $DATABASE_URL -f db/migrations/003_apache_ml_enhancements.sql

-- ============================================================================
-- ADD ML MODEL PREDICTION COLUMNS TO APACHE_SIGNALS
-- ============================================================================

-- Add signal source tracking
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS signal_source VARCHAR(10) DEFAULT 'prophet';
-- 'ml' or 'prophet'

-- Add ML model predictions (stored as JSONB for flexibility)
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS ml_predictions JSONB;
-- Contains: {direction, flip_gravity, magnet_attraction, pin_zone, volatility}

-- Add individual model outputs for easier querying
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS direction_prediction VARCHAR(10);
-- UP, DOWN, FLAT

ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS direction_probabilities JSONB;
-- {up: 0.4, down: 0.3, flat: 0.3}

ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS flip_gravity_prob FLOAT;
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS magnet_attraction_prob FLOAT;
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS pin_zone_prob FLOAT;
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS expected_volatility_pct FLOAT;

-- Add conviction/edge metrics
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS overall_conviction FLOAT;
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS directional_edge FLOAT;

-- Add VIX at signal time
ALTER TABLE apache_signals ADD COLUMN IF NOT EXISTS vix_at_signal FLOAT;

-- ============================================================================
-- ADD ENHANCED POSITION TRACKING
-- ============================================================================

-- Add ML signal reference to positions
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS ml_signal_used BOOLEAN DEFAULT false;

-- Add win probability at entry
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS win_probability_at_entry FLOAT;

-- Add expected volatility at entry
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS expected_volatility_at_entry FLOAT;

-- Add actual vs expected metrics for ML feedback
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS actual_move_pct FLOAT;
ALTER TABLE apache_positions ADD COLUMN IF NOT EXISTS prediction_correct BOOLEAN;

-- ============================================================================
-- CREATE INDEXES FOR NEW COLUMNS
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_apache_signals_source ON apache_signals(signal_source);
CREATE INDEX IF NOT EXISTS idx_apache_signals_direction ON apache_signals(direction_prediction);
CREATE INDEX IF NOT EXISTS idx_apache_positions_ml ON apache_positions(ml_signal_used);

-- ============================================================================
-- INCREASE REASONING COLUMN SIZES
-- ============================================================================

-- Change reasoning column to TEXT (unlimited) if not already
ALTER TABLE apache_signals ALTER COLUMN reasoning TYPE TEXT;

-- Change oracle_reasoning column to TEXT (unlimited) if not already
ALTER TABLE apache_positions ALTER COLUMN oracle_reasoning TYPE TEXT;

-- ============================================================================
-- VERIFICATION
-- ============================================================================
SELECT 'Apache ML enhancements applied successfully' as status;
