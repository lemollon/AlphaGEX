-- Migration: Add extended columns to ARES positions
-- Version: 013
-- Description: Adds GEX context, Oracle context, and metadata columns for full audit trail
-- Date: 2024-12-31

-- =============================================================================
-- GEX CONTEXT COLUMNS (Market conditions at trade entry)
-- =============================================================================

-- GEX regime at time of trade entry
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS gex_regime TEXT;

-- Key GEX levels
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_wall REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_wall REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS flip_point REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS net_gex REAL;

-- =============================================================================
-- ORACLE CONTEXT COLUMNS (AI prediction context)
-- =============================================================================

-- Oracle confidence and win probability
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_confidence REAL;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_win_probability REAL;

-- Oracle advice and reasoning
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_advice TEXT;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_reasoning TEXT;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_top_factors TEXT;

-- =============================================================================
-- ADDITIONAL METADATA
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
    RAISE NOTICE 'Migration 013: ARES extended columns added successfully';
END $$;
