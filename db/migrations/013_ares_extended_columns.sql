-- Migration: Add extended columns to ARES positions + Fresh Start Reset
-- Version: 013
-- Description: Adds GEX context, Oracle context, and metadata columns for full audit trail
--              Also resets ARES to fresh state for clean deployment
-- Date: 2024-12-31

-- =============================================================================
-- PART 1: FRESH START - Reset all ARES data for clean deployment
-- =============================================================================

-- Clear all ARES positions (trade history)
DELETE FROM ares_positions;

-- Clear ARES daily performance
DELETE FROM ares_daily_performance;

-- Clear ARES scan activity if exists
DO $$
BEGIN
    DELETE FROM ares_scan_activity;
EXCEPTION WHEN undefined_table THEN
    -- Table doesn't exist, skip
END $$;

-- Reset ARES config entries
DELETE FROM autonomous_config WHERE key LIKE 'ares_%';

-- =============================================================================
-- PART 2: GEX CONTEXT COLUMNS (Market conditions at trade entry)
-- =============================================================================

-- GEX regime at time of trade entry
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS gex_regime TEXT;

-- Key GEX levels
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_wall REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_wall REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS flip_point REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS net_gex REAL;

-- =============================================================================
-- PART 3: ORACLE CONTEXT COLUMNS (AI prediction context)
-- =============================================================================

-- Oracle confidence and win probability
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_confidence REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_win_probability REAL;

-- Oracle advice and reasoning
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_advice TEXT;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_reasoning TEXT;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_top_factors TEXT;

-- =============================================================================
-- PART 4: ADDITIONAL METADATA
-- =============================================================================

-- Close reason (expired, profit_target, stop_loss, manual, etc.)
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS close_reason TEXT;

-- Ticker symbol (SPY or SPX)
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS ticker TEXT DEFAULT 'SPY';

-- DTE at entry (for historical tracking)
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS dte_at_entry INTEGER;

-- =============================================================================
-- CONFIRMATION
-- =============================================================================

-- Log migration completion
DO $$
BEGIN
    RAISE NOTICE 'Migration 013: ARES extended columns added + data reset for fresh start';
END $$;
