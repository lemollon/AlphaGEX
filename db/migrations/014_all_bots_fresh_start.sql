-- Migration: Fresh Start Reset for ALL Trading Bots
-- Version: 014
-- Description: Resets all bot trading data for clean deployment
-- Date: 2024-12-31
--
-- This migration clears ALL bot data:
-- - FORTRESS (Iron Condor)
-- - SOLOMON (Directional Spreads)
-- - PEGASUS (SPX Iron Condor)
--
-- Run this after major updates to start fresh with 0 trades, 0 P&L

-- =============================================================================
-- FORTRESS RESET (Iron Condor Bot)
-- =============================================================================

DELETE FROM fortress_positions;
DELETE FROM fortress_daily_performance;

DO $$
BEGIN
    DELETE FROM fortress_scan_activity;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DELETE FROM autonomous_config WHERE key LIKE 'ares_%';

-- =============================================================================
-- SOLOMON RESET (Directional Spreads Bot)
-- =============================================================================

DELETE FROM solomon_positions;

-- Legacy apache_positions table
DO $$
BEGIN
    DELETE FROM apache_positions;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DELETE FROM solomon_scan_activity;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DELETE FROM bot_scan_activity WHERE bot_name = 'SOLOMON';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DELETE FROM autonomous_config WHERE key LIKE 'solomon_%';

-- =============================================================================
-- PEGASUS RESET (SPX Iron Condor Bot)
-- =============================================================================

DELETE FROM pegasus_positions;

DO $$
BEGIN
    DELETE FROM pegasus_scan_activity;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DELETE FROM pegasus_daily_perf;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DELETE FROM bot_scan_activity WHERE bot_name = 'PEGASUS';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DELETE FROM autonomous_config WHERE key LIKE 'pegasus_%';

-- =============================================================================
-- UNIFIED BOT TABLES RESET
-- =============================================================================

-- Clear unified bot heartbeats (they'll regenerate on next scan)
DO $$
BEGIN
    DELETE FROM bot_heartbeats WHERE bot_name IN ('FORTRESS', 'SOLOMON', 'PEGASUS');
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- Clear unified scan activity for all bots
DO $$
BEGIN
    DELETE FROM bot_scan_activity WHERE bot_name IN ('FORTRESS', 'SOLOMON', 'PEGASUS');
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- =============================================================================
-- CONFIRMATION
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 014: All bots reset to fresh state (FORTRESS, SOLOMON, PEGASUS)';
END $$;
