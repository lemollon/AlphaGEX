-- Migration 027: Prophet Multi-Prediction Support
-- Removes UNIQUE(trade_date, bot_name) constraints that limit storage to 1 prediction
-- per bot per day, enabling full intraday prediction capture for richer training data.
--
-- IMPACT:
--   prophet_predictions: Can now store multiple predictions per bot per day
--   prophet_training_outcomes: Can now store multiple outcomes per bot per day
--
-- ROLLBACK: See DOWN section at bottom of this file
--
-- ESTIMATED STORAGE: 5 bots × 80 scans × 252 days = ~100K rows/year (trivial)

-- ============================================================================
-- 1. PROPHET_PREDICTIONS - Add new columns + fix constraints
-- ============================================================================

-- Add scan_timestamp for intraday prediction tracking
ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS scan_timestamp TIMESTAMPTZ DEFAULT NOW();

-- Add model_type to track which sub-model made the prediction (Phase 3 prep)
ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS model_type VARCHAR(50) DEFAULT 'combined_v3';

-- Add strategy_type if not already present (Migration 023 may have added it partially)
ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(20);

-- Add feature_snapshot for debugging and offline analysis
ALTER TABLE prophet_predictions ADD COLUMN IF NOT EXISTS feature_snapshot JSONB;

-- Drop the original UNIQUE constraint if it still exists
-- (Migration 023 may have already dropped it, but this is idempotent)
DROP INDEX IF EXISTS unique_prediction;
DROP INDEX IF EXISTS prophet_predictions_trade_date_bot_name_key;

-- Keep the position-based unique index from Migration 023
-- This prevents duplicate predictions for the SAME position (good)
-- but allows multiple predictions per bot per day (also good)
-- No change needed to prophet_predictions_position_unique

-- Add composite index for efficient training data queries
CREATE INDEX IF NOT EXISTS idx_prophet_pred_bot_date_scan
    ON prophet_predictions(bot_name, trade_date, scan_timestamp DESC);

-- Add index for model_type queries (Phase 3: sub-model training)
CREATE INDEX IF NOT EXISTS idx_prophet_pred_model_type
    ON prophet_predictions(model_type, trade_date);

-- Add index for strategy_type queries
CREATE INDEX IF NOT EXISTS idx_prophet_pred_strategy_type
    ON prophet_predictions(strategy_type);

-- ============================================================================
-- 2. PROPHET_TRAINING_OUTCOMES - Fix the data-losing UNIQUE constraint
-- ============================================================================

-- Drop the UNIQUE(trade_date, bot_name) that discards multi-trade days
-- This is the critical fix: bots that trade 3x/day were losing 2 outcomes
DROP INDEX IF EXISTS prophet_training_outcomes_trade_date_bot_name_key;

-- Add prediction_id column if not already present (links outcome to specific prediction)
ALTER TABLE prophet_training_outcomes ADD COLUMN IF NOT EXISTS prediction_id INTEGER;

-- Add model_type for sub-model training feedback
ALTER TABLE prophet_training_outcomes ADD COLUMN IF NOT EXISTS model_type VARCHAR(50);

-- Add scan_timestamp to match predictions
ALTER TABLE prophet_training_outcomes ADD COLUMN IF NOT EXISTS scan_timestamp TIMESTAMPTZ;

-- New unique constraint: one outcome per prediction (not per bot per day)
-- This allows multiple outcomes per bot per day while preventing duplicates
CREATE UNIQUE INDEX IF NOT EXISTS idx_training_outcomes_prediction_unique
    ON prophet_training_outcomes(prediction_id)
    WHERE prediction_id IS NOT NULL;

-- Fallback constraint for records without prediction_id (legacy data):
-- Keep one per (trade_date, bot_name, outcome) to prevent exact duplicates
-- but allow different outcomes on the same day (e.g., 2 IC trades: 1 win, 1 loss)
CREATE UNIQUE INDEX IF NOT EXISTS idx_training_outcomes_legacy_unique
    ON prophet_training_outcomes(trade_date, bot_name, outcome, COALESCE(net_pnl::TEXT, ''))
    WHERE prediction_id IS NULL;

-- Add indexes for efficient sub-model training queries
CREATE INDEX IF NOT EXISTS idx_training_outcomes_strategy
    ON prophet_training_outcomes(strategy_type);

CREATE INDEX IF NOT EXISTS idx_training_outcomes_model_type
    ON prophet_training_outcomes(model_type);

CREATE INDEX IF NOT EXISTS idx_training_outcomes_prediction_id
    ON prophet_training_outcomes(prediction_id);

-- ============================================================================
-- 3. VERIFICATION
-- ============================================================================
SELECT 'Migration 027 applied: Prophet multi-prediction support' AS status;

-- Verify constraints
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('prophet_predictions', 'prophet_training_outcomes')
AND indexname LIKE '%unique%' OR indexname LIKE '%prediction%'
ORDER BY tablename, indexname;


-- ============================================================================
-- DOWN (ROLLBACK) - Restores original UNIQUE constraints
-- Run this section manually if rollback is needed
-- ============================================================================
-- WARNING: Rolling back will lose intraday prediction granularity
--
-- DROP INDEX IF EXISTS idx_prophet_pred_bot_date_scan;
-- DROP INDEX IF EXISTS idx_prophet_pred_model_type;
-- DROP INDEX IF EXISTS idx_prophet_pred_strategy_type;
-- DROP INDEX IF EXISTS idx_training_outcomes_prediction_unique;
-- DROP INDEX IF EXISTS idx_training_outcomes_legacy_unique;
-- DROP INDEX IF EXISTS idx_training_outcomes_strategy;
-- DROP INDEX IF EXISTS idx_training_outcomes_model_type;
-- DROP INDEX IF EXISTS idx_training_outcomes_prediction_id;
--
-- -- Restore original constraints (will fail if duplicate data exists)
-- -- Must deduplicate first: DELETE using ctid to keep latest per (trade_date, bot_name)
-- CREATE UNIQUE INDEX IF NOT EXISTS prophet_predictions_trade_date_bot_name_key
--     ON prophet_predictions(trade_date, bot_name);
-- CREATE UNIQUE INDEX IF NOT EXISTS prophet_training_outcomes_trade_date_bot_name_key
--     ON prophet_training_outcomes(trade_date, bot_name);
--
-- ALTER TABLE prophet_predictions DROP COLUMN IF EXISTS scan_timestamp;
-- ALTER TABLE prophet_predictions DROP COLUMN IF EXISTS model_type;
-- ALTER TABLE prophet_predictions DROP COLUMN IF EXISTS feature_snapshot;
-- ALTER TABLE prophet_training_outcomes DROP COLUMN IF EXISTS model_type;
-- ALTER TABLE prophet_training_outcomes DROP COLUMN IF EXISTS scan_timestamp;
