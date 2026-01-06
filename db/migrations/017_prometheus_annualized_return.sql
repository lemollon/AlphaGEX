-- Migration 017: Add annualized_return column to spx_wheel_ml_outcomes
-- Required for prometheus_outcome_tracker.py INSERT statement
-- Run: psql $DATABASE_URL -f db/migrations/017_prometheus_annualized_return.sql

-- Add annualized_return column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'spx_wheel_ml_outcomes'
        AND column_name = 'annualized_return'
    ) THEN
        ALTER TABLE spx_wheel_ml_outcomes
        ADD COLUMN annualized_return DECIMAL(8,2);
    END IF;
END $$;

-- Verify
SELECT 'annualized_return column added to spx_wheel_ml_outcomes' as status;
