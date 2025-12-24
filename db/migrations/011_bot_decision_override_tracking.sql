-- Migration: Add signal source and override tracking to bot_decision_logs
-- This allows tracking when a trade was made despite one signal saying SKIP
-- (e.g., Oracle overriding ML STAY_OUT)

-- Add signal_source column
ALTER TABLE bot_decision_logs ADD COLUMN IF NOT EXISTS signal_source VARCHAR(100);

-- Add override tracking columns
ALTER TABLE bot_decision_logs ADD COLUMN IF NOT EXISTS override_occurred BOOLEAN DEFAULT FALSE;
ALTER TABLE bot_decision_logs ADD COLUMN IF NOT EXISTS override_details JSONB;

-- Add index for filtering overridden decisions
CREATE INDEX IF NOT EXISTS idx_bot_decision_logs_override
ON bot_decision_logs (bot_name, override_occurred)
WHERE override_occurred = TRUE;

-- Comment for documentation
COMMENT ON COLUMN bot_decision_logs.signal_source IS 'Signal source: ML, Oracle, Oracle (override ML), ML+Oracle, Manual';
COMMENT ON COLUMN bot_decision_logs.override_occurred IS 'True if trade was made despite one signal saying SKIP';
COMMENT ON COLUMN bot_decision_logs.override_details IS 'JSON with override details: overridden_signal, overridden_advice, override_reason, override_confidence';
