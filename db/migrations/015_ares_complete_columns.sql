-- Migration: Complete ARES positions table with ALL required columns
-- Version: 015
-- Description: Adds missing columns that prevent ARES from saving positions
-- Date: 2025-01-02

-- =============================================================================
-- MISSING CORE COLUMNS (required for INSERT to succeed)
-- =============================================================================

-- Market context at entry (REQUIRED by save_position)
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS underlying_at_entry DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS vix_at_entry DECIMAL(6, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS expected_move DECIMAL(10, 2);

-- Position financials (max_profit should already exist, but ensure it does)
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS max_profit DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS max_loss DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS spread_width DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS contracts INTEGER;

-- Credit details
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_credit DECIMAL(10, 4);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_credit DECIMAL(10, 4);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS total_credit DECIMAL(10, 4);

-- Strike prices
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_short_strike DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_long_strike DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_short_strike DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_long_strike DECIMAL(10, 2);

-- =============================================================================
-- GEX CONTEXT COLUMNS
-- =============================================================================

ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS gex_regime VARCHAR(30);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_wall DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_wall DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS flip_point DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS net_gex DECIMAL(15, 2);

-- =============================================================================
-- ORACLE CONTEXT COLUMNS
-- =============================================================================

ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_confidence DECIMAL(5, 4);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_win_probability DECIMAL(5, 4);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_advice VARCHAR(20);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_reasoning TEXT;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_top_factors TEXT;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS oracle_use_gex_walls BOOLEAN DEFAULT FALSE;

-- =============================================================================
-- ORDER TRACKING
-- =============================================================================

ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS put_order_id VARCHAR(50);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS call_order_id VARCHAR(50);

-- =============================================================================
-- STATUS AND TIMESTAMPS
-- =============================================================================

ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'open';
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS open_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS close_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS close_price DECIMAL(10, 4);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS close_reason VARCHAR(100);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS realized_pnl DECIMAL(10, 2);
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE ares_positions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- =============================================================================
-- FIX SCAN_ACTIVITY NUMERIC PRECISION
-- DECIMAL(5,4) can only hold -9.9999 to 9.9999
-- Change to DECIMAL(8,4) to handle percentages (0-100) safely
-- =============================================================================

-- Fix confidence/probability fields that may receive percentage values
DO $$
BEGIN
    -- signal_confidence: 0-1 or 0-100 format
    ALTER TABLE scan_activity ALTER COLUMN signal_confidence TYPE DECIMAL(8, 4);
    RAISE NOTICE 'Fixed signal_confidence precision';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'signal_confidence already correct or table missing';
END $$;

DO $$
BEGIN
    -- signal_win_probability: 0-1 or 0-100 format
    ALTER TABLE scan_activity ALTER COLUMN signal_win_probability TYPE DECIMAL(8, 4);
    RAISE NOTICE 'Fixed signal_win_probability precision';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'signal_win_probability already correct or table missing';
END $$;

-- Also fix oracle_confidence in ares_positions if it was created with wrong precision
DO $$
BEGIN
    ALTER TABLE ares_positions ALTER COLUMN oracle_confidence TYPE DECIMAL(8, 4);
    RAISE NOTICE 'Fixed ares_positions.oracle_confidence precision';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ares_positions.oracle_confidence already correct';
END $$;

DO $$
BEGIN
    ALTER TABLE ares_positions ALTER COLUMN oracle_win_probability TYPE DECIMAL(8, 4);
    RAISE NOTICE 'Fixed ares_positions.oracle_win_probability precision';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'ares_positions.oracle_win_probability already correct';
END $$;

-- =============================================================================
-- PEGASUS - SPX IRON CONDOR (Same schema as ARES)
-- =============================================================================

-- Core columns for PEGASUS
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS underlying_at_entry DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS vix_at_entry DECIMAL(6, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS expected_move DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS max_profit DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS max_loss DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS spread_width DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS contracts INTEGER;
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS put_credit DECIMAL(10, 4);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS call_credit DECIMAL(10, 4);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS total_credit DECIMAL(10, 4);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS put_short_strike DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS put_long_strike DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS call_short_strike DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS call_long_strike DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS gex_regime VARCHAR(30);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS call_wall DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS put_wall DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS flip_point DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS net_gex DECIMAL(15, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_confidence DECIMAL(8, 4);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_win_probability DECIMAL(8, 4);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_advice VARCHAR(20);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_reasoning TEXT;
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_top_factors TEXT;
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS oracle_use_gex_walls BOOLEAN DEFAULT FALSE;
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS put_order_id VARCHAR(50);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS call_order_id VARCHAR(50);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'open';
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS open_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS close_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS close_price DECIMAL(10, 4);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS close_reason VARCHAR(100);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS realized_pnl DECIMAL(10, 2);
ALTER TABLE pegasus_positions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Fix PEGASUS precision
DO $$
BEGIN
    ALTER TABLE pegasus_positions ALTER COLUMN oracle_confidence TYPE DECIMAL(8, 4);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE pegasus_positions ALTER COLUMN oracle_win_probability TYPE DECIMAL(8, 4);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- =============================================================================
-- ATHENA - DIRECTIONAL SPREADS
-- =============================================================================

-- Core columns for ATHENA
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS underlying_at_entry DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS vix_at_entry DECIMAL(6, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS max_profit DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS max_loss DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS entry_debit DECIMAL(10, 4);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS long_strike DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS short_strike DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS spread_type VARCHAR(30);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS contracts INTEGER;
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS gex_regime VARCHAR(30);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS call_wall DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS put_wall DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS flip_point DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS net_gex DECIMAL(15, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS oracle_confidence DECIMAL(8, 4);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS ml_direction VARCHAR(20);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS ml_confidence DECIMAL(8, 4);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS ml_model_name VARCHAR(100);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS ml_win_probability DECIMAL(8, 4);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS ml_top_features TEXT;
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS wall_type VARCHAR(20);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS wall_distance_pct DECIMAL(6, 4);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS trade_reasoning TEXT;
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS order_id VARCHAR(50);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'open';
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS open_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS close_time TIMESTAMP WITH TIME ZONE;
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS close_price DECIMAL(10, 4);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS close_reason VARCHAR(100);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS realized_pnl DECIMAL(10, 2);
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE athena_positions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Fix ATHENA precision
DO $$
BEGIN
    ALTER TABLE athena_positions ALTER COLUMN oracle_confidence TYPE DECIMAL(8, 4);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE athena_positions ALTER COLUMN ml_confidence TYPE DECIMAL(8, 4);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE athena_positions ALTER COLUMN ml_win_probability TYPE DECIMAL(8, 4);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- Also fix ATHENA signals table
DO $$
BEGIN
    ALTER TABLE athena_signals ALTER COLUMN confidence TYPE DECIMAL(8, 4);
EXCEPTION WHEN OTHERS THEN NULL;
END $$;

-- =============================================================================
-- CONFIRMATION
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 015: ARES, PEGASUS, ATHENA columns added and precision fixed';
END $$;
