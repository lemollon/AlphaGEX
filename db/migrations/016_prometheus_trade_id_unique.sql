-- Migration 016: Add UNIQUE constraint on prometheus_predictions.trade_id
-- Required for ON CONFLICT (trade_id) clause in prometheus_ml.py
-- Run: psql $DATABASE_URL -f db/migrations/016_prometheus_trade_id_unique.sql

-- Add UNIQUE constraint to trade_id column
-- Using CREATE UNIQUE INDEX which is idempotent with IF NOT EXISTS
DO $$
BEGIN
    -- First, remove any duplicate trade_ids (keep the most recent)
    DELETE FROM prometheus_predictions a
    USING prometheus_predictions b
    WHERE a.id < b.id
    AND a.trade_id = b.trade_id
    AND a.trade_id IS NOT NULL;

    -- Now add the unique constraint if it doesn't exist
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'prometheus_predictions_trade_id_key'
    ) THEN
        ALTER TABLE prometheus_predictions
        ADD CONSTRAINT prometheus_predictions_trade_id_key UNIQUE (trade_id);
    END IF;
END $$;

-- Verify
SELECT 'UNIQUE constraint added to prometheus_predictions.trade_id' as status;
