-- Migration: Add extended columns to FORTRESS positions + Fresh Start Reset
-- Version: 013
-- Description: Adds GEX context, Oracle context, and metadata columns for full audit trail
--              Also resets FORTRESS to fresh state for clean deployment
-- Date: 2024-12-31

-- =============================================================================
-- PART 1: FRESH START - Reset all FORTRESS data for clean deployment
-- =============================================================================

-- Clear all FORTRESS positions (trade history)
DELETE FROM fortress_positions;

-- Clear FORTRESS daily performance
DELETE FROM fortress_daily_performance;

-- Clear FORTRESS scan activity if exists
DO $$
BEGIN
    DELETE FROM fortress_scan_activity;
EXCEPTION WHEN undefined_table THEN
    -- Table doesn't exist, skip
END $$;

-- Reset FORTRESS config entries
DELETE FROM autonomous_config WHERE key LIKE 'ares_%';

-- =============================================================================
-- PART 2: GEX CONTEXT COLUMNS (Market conditions at trade entry)
-- =============================================================================

-- GEX regime at time of trade entry
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS gex_regime TEXT;

-- Key GEX levels
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS call_wall REAL;
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS put_wall REAL;
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS flip_point REAL;
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS net_gex REAL;

-- =============================================================================
-- PART 3: ORACLE CONTEXT COLUMNS (AI prediction context)
-- =============================================================================

-- Oracle confidence and win probability
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS oracle_confidence REAL;
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS oracle_win_probability REAL;

-- Oracle advice and reasoning
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS oracle_advice TEXT;
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS oracle_reasoning TEXT;
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS oracle_top_factors TEXT;

-- =============================================================================
-- PART 4: ADDITIONAL METADATA
-- =============================================================================

-- Close reason (expired, profit_target, stop_loss, manual, etc.)
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS close_reason TEXT;

-- Ticker symbol (SPY or SPX)
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS ticker TEXT DEFAULT 'SPY';

-- DTE at entry (for historical tracking)
ALTER TABLE fortress_positions ADD COLUMN IF NOT EXISTS dte_at_entry INTEGER;

-- =============================================================================
-- CONFIRMATION
-- =============================================================================

-- Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 013: FORTRESS extended columns added + data reset for fresh start';
END $$;
