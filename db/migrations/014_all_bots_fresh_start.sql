-- Migration: Fresh Start Reset for ALL Trading Bots
-- Version: 014
-- Description: Resets all bot trading data for clean deployment
-- Date: 2024-12-31
--
-- This migration clears ALL bot data:
-- - ARES (Iron Condor)
-- - ATHENA (Directional Spreads)
-- - PEGASUS (SPX Iron Condor)
--
-- Run this after major updates to start fresh with 0 trades, 0 P&L

-- =============================================================================
-- ARES RESET (Iron Condor Bot)
-- =============================================================================

DELETE FROM ares_positions;
DELETE FROM ares_daily_performance;

DO $$
BEGIN
    DELETE FROM ares_scan_activity;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DELETE FROM autonomous_config WHERE key LIKE 'ares_%';

-- =============================================================================
-- ATHENA RESET (Directional Spreads Bot)
-- =============================================================================

DELETE FROM athena_positions;

-- Legacy apache_positions table
DO $$
BEGIN
    DELETE FROM apache_positions;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DELETE FROM athena_scan_activity;
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DO $$
BEGIN
    DELETE FROM bot_scan_activity WHERE bot_name = 'ATHENA';
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

DELETE FROM autonomous_config WHERE key LIKE 'athena_%';

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
    DELETE FROM bot_heartbeats WHERE bot_name IN ('ARES', 'ATHENA', 'PEGASUS');
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- Clear unified scan activity for all bots
DO $$
BEGIN
    DELETE FROM bot_scan_activity WHERE bot_name IN ('ARES', 'ATHENA', 'PEGASUS');
EXCEPTION WHEN undefined_table THEN NULL;
END $$;

-- =============================================================================
-- CONFIRMATION
-- =============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Migration 014: All bots reset to fresh state (ARES, ATHENA, PEGASUS)';
END $$;
