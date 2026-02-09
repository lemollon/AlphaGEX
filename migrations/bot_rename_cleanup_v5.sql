-- =============================================================================
-- AlphaGEX Bot Rename Cleanup V5: DROP OLD-NAME TABLES
-- =============================================================================
-- After v4 migration, 58 old-name tables still exist because the new-name
-- tables were already present (created by application code). Both old and new
-- coexist. This script drops the stale old-name tables after verifying each
-- new-name counterpart exists.
--
-- IDEMPOTENT: Safe to run multiple times. Uses DROP TABLE IF EXISTS.
--
-- Usage:
--   psql "$DB" -f bot_rename_cleanup_v5.sql
-- =============================================================================

BEGIN;

-- =============================================================================
-- SECTION 1: PRE-DROP SAFETY CHECK
-- =============================================================================
-- Verify all expected new-name tables exist before dropping anything.

DO $$
DECLARE
    missing TEXT;
    missing_count INTEGER;
BEGIN
    SELECT COUNT(*), STRING_AGG(expected, ', ' ORDER BY expected)
    INTO missing_count, missing
    FROM (
        VALUES
            -- FORTRESS (was ARES)
            ('fortress_daily_perf'), ('fortress_daily_performance'),
            ('fortress_daily_reports'), ('fortress_equity_snapshots'),
            ('fortress_logs'), ('fortress_positions'), ('fortress_signals'),
            -- SOLOMON (was ATHENA)
            ('solomon_daily_perf'), ('solomon_daily_reports'),
            ('solomon_equity_snapshots'), ('solomon_logs'),
            ('solomon_positions'), ('solomon_signals'),
            -- SAMSON (was TITAN)
            ('samson_daily_perf'), ('samson_daily_reports'),
            ('samson_equity_snapshots'), ('samson_logs'),
            ('samson_positions'), ('samson_signals'),
            -- ANCHOR (was PEGASUS)
            ('anchor_daily_perf'), ('anchor_daily_reports'),
            ('anchor_equity_snapshots'), ('anchor_logs'),
            ('anchor_positions'), ('anchor_signals'),
            -- GIDEON (was ICARUS)
            ('gideon_daily_perf'), ('gideon_daily_reports'),
            ('gideon_equity_snapshots'), ('gideon_logs'),
            ('gideon_positions'), ('gideon_signals'),
            -- VALOR (was HERACLES)
            ('valor_closed_trades'), ('valor_config'), ('valor_daily_perf'),
            ('valor_equity_snapshots'), ('valor_logs'), ('valor_paper_account'),
            ('valor_positions'), ('valor_scan_activity'), ('valor_signals'),
            ('valor_win_tracker'),
            -- PROPHET (was ORACLE)
            ('prophet_predictions'), ('prophet_trained_models'),
            ('prophet_training_outcomes'),
            -- DISCERNMENT (was APOLLO)
            ('discernment_live_quotes'), ('discernment_model_performance'),
            ('discernment_outcomes'), ('discernment_pin_risk_history'),
            ('discernment_predictions'), ('discernment_scans'),
            -- WATCHTOWER (was ARGUS)
            ('watchtower_accuracy'), ('watchtower_alerts'),
            ('watchtower_danger_zone_logs'), ('watchtower_gamma_history'),
            ('watchtower_order_flow_history'), ('watchtower_pin_predictions'),
            ('watchtower_snapshots'), ('watchtower_trade_signals')
    ) AS expected_tables(expected)
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = expected
    );

    IF missing_count > 0 THEN
        RAISE EXCEPTION 'ABORT: % new-name tables missing: %. Run v4 migration first!', missing_count, missing;
    ELSE
        RAISE NOTICE 'SAFETY CHECK PASSED: All new-name tables exist. Proceeding with cleanup.';
    END IF;
END $$;

-- =============================================================================
-- SECTION 2: DROP OLD-NAME TABLES
-- =============================================================================
-- CASCADE handles any dependent objects (views, foreign keys, etc.)

-- 2a. ARES -> FORTRESS (7 old tables)
DROP TABLE IF EXISTS ares_daily_perf CASCADE;
DROP TABLE IF EXISTS ares_daily_performance CASCADE;
DROP TABLE IF EXISTS ares_daily_reports CASCADE;
DROP TABLE IF EXISTS ares_equity_snapshots CASCADE;
DROP TABLE IF EXISTS ares_logs CASCADE;
DROP TABLE IF EXISTS ares_positions CASCADE;
DROP TABLE IF EXISTS ares_signals CASCADE;

-- 2b. ATHENA -> SOLOMON (6 old tables)
DROP TABLE IF EXISTS athena_daily_perf CASCADE;
DROP TABLE IF EXISTS athena_daily_reports CASCADE;
DROP TABLE IF EXISTS athena_equity_snapshots CASCADE;
DROP TABLE IF EXISTS athena_logs CASCADE;
DROP TABLE IF EXISTS athena_positions CASCADE;
DROP TABLE IF EXISTS athena_signals CASCADE;

-- 2c. TITAN -> SAMSON (6 old tables)
DROP TABLE IF EXISTS titan_daily_perf CASCADE;
DROP TABLE IF EXISTS titan_daily_reports CASCADE;
DROP TABLE IF EXISTS titan_equity_snapshots CASCADE;
DROP TABLE IF EXISTS titan_logs CASCADE;
DROP TABLE IF EXISTS titan_positions CASCADE;
DROP TABLE IF EXISTS titan_signals CASCADE;

-- 2d. PEGASUS -> ANCHOR (6 old tables)
DROP TABLE IF EXISTS pegasus_daily_perf CASCADE;
DROP TABLE IF EXISTS pegasus_daily_reports CASCADE;
DROP TABLE IF EXISTS pegasus_equity_snapshots CASCADE;
DROP TABLE IF EXISTS pegasus_logs CASCADE;
DROP TABLE IF EXISTS pegasus_positions CASCADE;
DROP TABLE IF EXISTS pegasus_signals CASCADE;

-- 2e. ICARUS -> GIDEON (6 old tables)
DROP TABLE IF EXISTS icarus_daily_perf CASCADE;
DROP TABLE IF EXISTS icarus_daily_reports CASCADE;
DROP TABLE IF EXISTS icarus_equity_snapshots CASCADE;
DROP TABLE IF EXISTS icarus_logs CASCADE;
DROP TABLE IF EXISTS icarus_positions CASCADE;
DROP TABLE IF EXISTS icarus_signals CASCADE;

-- 2f. HERACLES -> VALOR (10 old tables)
DROP TABLE IF EXISTS heracles_closed_trades CASCADE;
DROP TABLE IF EXISTS heracles_config CASCADE;
DROP TABLE IF EXISTS heracles_daily_perf CASCADE;
DROP TABLE IF EXISTS heracles_equity_snapshots CASCADE;
DROP TABLE IF EXISTS heracles_logs CASCADE;
DROP TABLE IF EXISTS heracles_paper_account CASCADE;
DROP TABLE IF EXISTS heracles_positions CASCADE;
DROP TABLE IF EXISTS heracles_scan_activity CASCADE;
DROP TABLE IF EXISTS heracles_signals CASCADE;
DROP TABLE IF EXISTS heracles_win_tracker CASCADE;

-- 2g. ORACLE -> PROPHET (3 old tables)
DROP TABLE IF EXISTS oracle_predictions CASCADE;
DROP TABLE IF EXISTS oracle_trained_models CASCADE;
DROP TABLE IF EXISTS oracle_training_outcomes CASCADE;

-- 2h. APOLLO -> DISCERNMENT (6 old tables)
DROP TABLE IF EXISTS apollo_live_quotes CASCADE;
DROP TABLE IF EXISTS apollo_model_performance CASCADE;
DROP TABLE IF EXISTS apollo_outcomes CASCADE;
DROP TABLE IF EXISTS apollo_pin_risk_history CASCADE;
DROP TABLE IF EXISTS apollo_predictions CASCADE;
DROP TABLE IF EXISTS apollo_scans CASCADE;

-- 2i. ARGUS -> WATCHTOWER (8 old tables)
DROP TABLE IF EXISTS argus_accuracy CASCADE;
DROP TABLE IF EXISTS argus_alerts CASCADE;
DROP TABLE IF EXISTS argus_danger_zone_logs CASCADE;
DROP TABLE IF EXISTS argus_gamma_history CASCADE;
DROP TABLE IF EXISTS argus_order_flow_history CASCADE;
DROP TABLE IF EXISTS argus_pin_predictions CASCADE;
DROP TABLE IF EXISTS argus_snapshots CASCADE;
DROP TABLE IF EXISTS argus_trade_signals CASCADE;

-- =============================================================================
-- SECTION 3: VERIFICATION
-- =============================================================================

DO $$
DECLARE
    old_tables TEXT;
    old_count INTEGER;
BEGIN
    SELECT COUNT(*), STRING_AGG(table_name, ', ' ORDER BY table_name)
    INTO old_count, old_tables
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE ANY(ARRAY[
        'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
        'heracles_%', 'prometheus_%',
        'oracle_%', 'apollo_%', 'argus_%',
        'kronos_%', 'hyperion_%'
    ]);
    IF old_count = 0 THEN
        RAISE NOTICE 'CLEANUP PASS: Zero old-name tables remain!';
    ELSE
        RAISE WARNING 'CLEANUP PARTIAL: % old tables still exist: %', old_count, old_tables;
    END IF;
END $$;

COMMIT;

\echo ''
\echo '==========================================='
\echo '  CLEANUP V5 COMPLETE'
\echo '  58 stale old-name tables dropped.'
\echo '==========================================='
