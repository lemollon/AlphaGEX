-- =============================================================================
-- AlphaGEX Bot Rename Migration V4: IDEMPOTENT
-- =============================================================================
-- Safe to run multiple times. Skips renames where:
--   - The source table doesn't exist (already renamed), OR
--   - The target table already exists (already renamed)
--
-- Also handles config key updates and bot_name value updates idempotently.
--
-- Usage:
--   psql "$DB" -f bot_rename_migration_v4_idempotent.sql
-- =============================================================================

BEGIN;

-- Helper function: rename table only if source exists and target doesn't
CREATE OR REPLACE FUNCTION _safe_rename(src TEXT, dst TEXT) RETURNS VOID AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=src)
       AND NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=dst)
    THEN
        EXECUTE format('ALTER TABLE %I RENAME TO %I', src, dst);
        RAISE NOTICE 'RENAMED: % -> %', src, dst;
    ELSIF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=dst) THEN
        RAISE NOTICE 'SKIP (target exists): % -> %', src, dst;
    ELSE
        RAISE NOTICE 'SKIP (source missing): % -> %', src, dst;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SECTION 1: TABLE RENAMES
-- =============================================================================
-- CRITICAL: SOLOMON advisory -> PROVERBS must happen BEFORE ATHENA -> SOLOMON

-- 1a. PROVERBS (formerly SOLOMON advisory) — MUST BE FIRST
SELECT _safe_rename('solomon_ab_tests', 'proverbs_ab_tests');
SELECT _safe_rename('solomon_audit_log', 'proverbs_audit_log');
SELECT _safe_rename('solomon_bot_configs', 'proverbs_bot_configs');
SELECT _safe_rename('solomon_health', 'proverbs_health');
SELECT _safe_rename('solomon_kill_switch', 'proverbs_kill_switch');
SELECT _safe_rename('solomon_performance', 'proverbs_performance');
SELECT _safe_rename('solomon_proposals', 'proverbs_proposals');
SELECT _safe_rename('solomon_rollbacks', 'proverbs_rollbacks');
SELECT _safe_rename('solomon_strategy_analysis', 'proverbs_strategy_analysis');
SELECT _safe_rename('solomon_validations', 'proverbs_validations');
SELECT _safe_rename('solomon_versions', 'proverbs_versions');

-- 1b. SOLOMON bot (formerly ATHENA) — Safe now that advisory tables are proverbs_*
SELECT _safe_rename('athena_closed_trades', 'solomon_closed_trades');
SELECT _safe_rename('athena_daily_perf', 'solomon_daily_perf');
SELECT _safe_rename('athena_daily_reports', 'solomon_daily_reports');
SELECT _safe_rename('athena_equity_snapshots', 'solomon_equity_snapshots');
SELECT _safe_rename('athena_logs', 'solomon_logs');
SELECT _safe_rename('athena_positions', 'solomon_positions');
SELECT _safe_rename('athena_scan_activity', 'solomon_scan_activity');
SELECT _safe_rename('athena_signals', 'solomon_signals');

-- 1c. FORTRESS (formerly ARES)
SELECT _safe_rename('ares_closed_trades', 'fortress_closed_trades');
SELECT _safe_rename('ares_daily_perf', 'fortress_daily_perf');
SELECT _safe_rename('ares_daily_performance', 'fortress_daily_performance');
SELECT _safe_rename('ares_daily_reports', 'fortress_daily_reports');
SELECT _safe_rename('ares_equity_snapshots', 'fortress_equity_snapshots');
SELECT _safe_rename('ares_logs', 'fortress_logs');
SELECT _safe_rename('ares_positions', 'fortress_positions');
SELECT _safe_rename('ares_scan_activity', 'fortress_scan_activity');
SELECT _safe_rename('ares_signals', 'fortress_signals');

-- 1d. SAMSON (formerly TITAN)
SELECT _safe_rename('titan_closed_trades', 'samson_closed_trades');
SELECT _safe_rename('titan_daily_perf', 'samson_daily_perf');
SELECT _safe_rename('titan_daily_reports', 'samson_daily_reports');
SELECT _safe_rename('titan_equity_snapshots', 'samson_equity_snapshots');
SELECT _safe_rename('titan_logs', 'samson_logs');
SELECT _safe_rename('titan_positions', 'samson_positions');
SELECT _safe_rename('titan_scan_activity', 'samson_scan_activity');
SELECT _safe_rename('titan_signals', 'samson_signals');

-- 1e. ANCHOR (formerly PEGASUS)
SELECT _safe_rename('pegasus_closed_trades', 'anchor_closed_trades');
SELECT _safe_rename('pegasus_daily_perf', 'anchor_daily_perf');
SELECT _safe_rename('pegasus_daily_reports', 'anchor_daily_reports');
SELECT _safe_rename('pegasus_equity_snapshots', 'anchor_equity_snapshots');
SELECT _safe_rename('pegasus_logs', 'anchor_logs');
SELECT _safe_rename('pegasus_positions', 'anchor_positions');
SELECT _safe_rename('pegasus_scan_activity', 'anchor_scan_activity');
SELECT _safe_rename('pegasus_signals', 'anchor_signals');

-- 1f. GIDEON (formerly ICARUS)
SELECT _safe_rename('icarus_closed_trades', 'gideon_closed_trades');
SELECT _safe_rename('icarus_daily_perf', 'gideon_daily_perf');
SELECT _safe_rename('icarus_daily_reports', 'gideon_daily_reports');
SELECT _safe_rename('icarus_equity_snapshots', 'gideon_equity_snapshots');
SELECT _safe_rename('icarus_logs', 'gideon_logs');
SELECT _safe_rename('icarus_positions', 'gideon_positions');
SELECT _safe_rename('icarus_scan_activity', 'gideon_scan_activity');
SELECT _safe_rename('icarus_signals', 'gideon_signals');

-- 1g. VALOR (formerly HERACLES)
SELECT _safe_rename('heracles_closed_trades', 'valor_closed_trades');
SELECT _safe_rename('heracles_config', 'valor_config');
SELECT _safe_rename('heracles_daily_perf', 'valor_daily_perf');
SELECT _safe_rename('heracles_equity_snapshots', 'valor_equity_snapshots');
SELECT _safe_rename('heracles_logs', 'valor_logs');
SELECT _safe_rename('heracles_paper_account', 'valor_paper_account');
SELECT _safe_rename('heracles_positions', 'valor_positions');
SELECT _safe_rename('heracles_scan_activity', 'valor_scan_activity');
SELECT _safe_rename('heracles_signals', 'valor_signals');
SELECT _safe_rename('heracles_win_tracker', 'valor_win_tracker');

-- 1h. JUBILEE (formerly PROMETHEUS)
SELECT _safe_rename('prometheus_capital_deployments', 'jubilee_capital_deployments');
SELECT _safe_rename('prometheus_config', 'jubilee_config');
SELECT _safe_rename('prometheus_daily_briefings', 'jubilee_daily_briefings');
SELECT _safe_rename('prometheus_equity_snapshots', 'jubilee_equity_snapshots');
SELECT _safe_rename('prometheus_ic_closed_trades', 'jubilee_ic_closed_trades');
SELECT _safe_rename('prometheus_ic_config', 'jubilee_ic_config');
SELECT _safe_rename('prometheus_ic_equity_snapshots', 'jubilee_ic_equity_snapshots');
SELECT _safe_rename('prometheus_ic_positions', 'jubilee_ic_positions');
SELECT _safe_rename('prometheus_ic_signals', 'jubilee_ic_signals');
SELECT _safe_rename('prometheus_live_model', 'jubilee_live_model');
SELECT _safe_rename('prometheus_logs', 'jubilee_logs');
SELECT _safe_rename('prometheus_models', 'jubilee_models');
SELECT _safe_rename('prometheus_positions', 'jubilee_positions');
SELECT _safe_rename('prometheus_predictions', 'jubilee_predictions');
SELECT _safe_rename('prometheus_rate_analysis', 'jubilee_rate_analysis');
SELECT _safe_rename('prometheus_roll_decisions', 'jubilee_roll_decisions');
SELECT _safe_rename('prometheus_signals', 'jubilee_signals');
SELECT _safe_rename('prometheus_training_history', 'jubilee_training_history');

-- 1i. PROPHET (formerly ORACLE)
SELECT _safe_rename('oracle_bot_interactions', 'prophet_bot_interactions');
SELECT _safe_rename('oracle_predictions', 'prophet_predictions');
SELECT _safe_rename('oracle_strategy_accuracy', 'prophet_strategy_accuracy');
SELECT _safe_rename('oracle_trained_models', 'prophet_trained_models');
SELECT _safe_rename('oracle_training_outcomes', 'prophet_training_outcomes');

-- 1j. DISCERNMENT (formerly APOLLO)
SELECT _safe_rename('apollo_live_quotes', 'discernment_live_quotes');
SELECT _safe_rename('apollo_model_performance', 'discernment_model_performance');
SELECT _safe_rename('apollo_outcomes', 'discernment_outcomes');
SELECT _safe_rename('apollo_pin_risk_history', 'discernment_pin_risk_history');
SELECT _safe_rename('apollo_predictions', 'discernment_predictions');
SELECT _safe_rename('apollo_scans', 'discernment_scans');

-- 1k. WATCHTOWER (formerly ARGUS)
SELECT _safe_rename('argus_accuracy', 'watchtower_accuracy');
SELECT _safe_rename('argus_alerts', 'watchtower_alerts');
SELECT _safe_rename('argus_commentary', 'watchtower_commentary');
SELECT _safe_rename('argus_danger_zone_logs', 'watchtower_danger_zone_logs');
SELECT _safe_rename('argus_gamma_flips', 'watchtower_gamma_flips');
SELECT _safe_rename('argus_gamma_history', 'watchtower_gamma_history');
SELECT _safe_rename('argus_order_flow_history', 'watchtower_order_flow_history');
SELECT _safe_rename('argus_outcomes', 'watchtower_outcomes');
SELECT _safe_rename('argus_pin_predictions', 'watchtower_pin_predictions');
SELECT _safe_rename('argus_predictions', 'watchtower_predictions');
SELECT _safe_rename('argus_snapshots', 'watchtower_snapshots');
SELECT _safe_rename('argus_strikes', 'watchtower_strikes');
SELECT _safe_rename('argus_trade_signals', 'watchtower_trade_signals');

-- 1l. CHRONICLES (formerly KRONOS)
SELECT _safe_rename('kronos_jobs', 'chronicles_jobs');

-- 1m. GLORY (formerly HYPERION)
SELECT _safe_rename('hyperion_gamma_history', 'glory_gamma_history');

-- Cleanup helper function
DROP FUNCTION _safe_rename(TEXT, TEXT);


-- =============================================================================
-- SECTION 2: CONFIG KEY UPDATES (idempotent — WHERE key = old_name)
-- =============================================================================

UPDATE autonomous_config SET key = 'fortress_starting_capital' WHERE key = 'ares_starting_capital';
UPDATE autonomous_config SET key = 'solomon_starting_capital' WHERE key = 'athena_starting_capital';
UPDATE autonomous_config SET key = 'samson_starting_capital' WHERE key = 'titan_starting_capital';
UPDATE autonomous_config SET key = 'anchor_starting_capital' WHERE key = 'pegasus_starting_capital';
UPDATE autonomous_config SET key = 'gideon_starting_capital' WHERE key = 'icarus_starting_capital';
UPDATE autonomous_config SET key = 'valor_starting_capital' WHERE key = 'heracles_starting_capital';
UPDATE autonomous_config SET key = 'fortress_mode' WHERE key = 'ares_mode';
UPDATE autonomous_config SET key = 'fortress_ticker' WHERE key = 'ares_ticker';


-- =============================================================================
-- SECTION 2B: ML_MODELS MODEL_NAME UPDATES (idempotent)
-- =============================================================================

UPDATE ml_models SET model_name = 'fortress_ml' WHERE model_name = 'ares_ml';
UPDATE ml_models SET model_name = 'valor_ml' WHERE model_name = 'heracles_ml';


-- =============================================================================
-- SECTION 3: BOT_NAME COLUMN VALUE UPDATES (idempotent)
-- =============================================================================

-- 3a. bot_decision_logs
-- Advisory rename first (SOLOMON advisory -> PROVERBS)
UPDATE bot_decision_logs SET bot_name = 'PROVERBS' WHERE bot_name = 'SOLOMON';
UPDATE bot_decision_logs SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
UPDATE bot_decision_logs SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
UPDATE bot_decision_logs SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
UPDATE bot_decision_logs SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
UPDATE bot_decision_logs SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
UPDATE bot_decision_logs SET bot_name = 'LAZARUS' WHERE bot_name = 'PHOENIX';
UPDATE bot_decision_logs SET bot_name = 'CORNERSTONE' WHERE bot_name = 'ATLAS';
UPDATE bot_decision_logs SET bot_name = 'SHEPHERD' WHERE bot_name = 'HERMES';
UPDATE bot_decision_logs SET bot_name = 'JUBILEE' WHERE bot_name = 'PROMETHEUS';
UPDATE bot_decision_logs SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
UPDATE bot_decision_logs SET bot_name = 'PROPHET' WHERE bot_name = 'ORACLE';
UPDATE bot_decision_logs SET bot_name = 'WISDOM' WHERE bot_name = 'SAGE';
UPDATE bot_decision_logs SET bot_name = 'WATCHTOWER' WHERE bot_name = 'ARGUS';
UPDATE bot_decision_logs SET bot_name = 'STARS' WHERE bot_name = 'ORION';
UPDATE bot_decision_logs SET bot_name = 'COUNSELOR' WHERE bot_name = 'GEXIS';
UPDATE bot_decision_logs SET bot_name = 'CHRONICLES' WHERE bot_name = 'KRONOS';
UPDATE bot_decision_logs SET bot_name = 'GLORY' WHERE bot_name = 'HYPERION';
UPDATE bot_decision_logs SET bot_name = 'DISCERNMENT' WHERE bot_name = 'APOLLO';
UPDATE bot_decision_logs SET bot_name = 'COVENANT' WHERE bot_name = 'NEXUS';

-- 3b. trading_decisions strategy column
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ARES', 'FORTRESS')
WHERE strategy LIKE '%ARES%';
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ATHENA', 'SOLOMON')
WHERE strategy LIKE '%ATHENA%';
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'TITAN', 'SAMSON')
WHERE strategy LIKE '%TITAN%';
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'PEGASUS', 'ANCHOR')
WHERE strategy LIKE '%PEGASUS%';
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ICARUS', 'GIDEON')
WHERE strategy LIKE '%ICARUS%';
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'PHOENIX', 'LAZARUS')
WHERE strategy LIKE '%PHOENIX%';
UPDATE trading_decisions SET strategy = REPLACE(strategy, 'HERACLES', 'VALOR')
WHERE strategy LIKE '%HERACLES%';

-- 3c. ml_decision_logs action column
UPDATE ml_decision_logs SET action = REPLACE(action, 'ARES', 'FORTRESS')
WHERE action LIKE '%ARES%';
UPDATE ml_decision_logs SET action = REPLACE(action, 'ATHENA', 'SOLOMON')
WHERE action LIKE '%ATHENA%';

-- 3d-3k. proverbs_* tables bot_name columns (safe — tables may or may not exist)
DO $$ BEGIN
    -- proverbs_proposals
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_proposals' AND column_name='bot_name') THEN
        UPDATE proverbs_proposals SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_proposals SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_proposals SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_proposals SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_proposals SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_proposals SET bot_name = 'LAZARUS' WHERE bot_name = 'PHOENIX';
        UPDATE proverbs_proposals SET bot_name = 'CORNERSTONE' WHERE bot_name = 'ATLAS';
        UPDATE proverbs_proposals SET bot_name = 'SHEPHERD' WHERE bot_name = 'HERMES';
        UPDATE proverbs_proposals SET bot_name = 'JUBILEE' WHERE bot_name = 'PROMETHEUS';
        UPDATE proverbs_proposals SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_kill_switch
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_kill_switch' AND column_name='bot_name') THEN
        UPDATE proverbs_kill_switch SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_kill_switch SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_kill_switch SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_kill_switch SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_kill_switch SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_kill_switch SET bot_name = 'LAZARUS' WHERE bot_name = 'PHOENIX';
        UPDATE proverbs_kill_switch SET bot_name = 'CORNERSTONE' WHERE bot_name = 'ATLAS';
        UPDATE proverbs_kill_switch SET bot_name = 'SHEPHERD' WHERE bot_name = 'HERMES';
        UPDATE proverbs_kill_switch SET bot_name = 'JUBILEE' WHERE bot_name = 'PROMETHEUS';
        UPDATE proverbs_kill_switch SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_versions
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_versions' AND column_name='bot_name') THEN
        UPDATE proverbs_versions SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_versions SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_versions SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_versions SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_versions SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_versions SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_performance
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_performance' AND column_name='bot_name') THEN
        UPDATE proverbs_performance SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_performance SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_performance SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_performance SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_performance SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_performance SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_validations
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_validations' AND column_name='bot_name') THEN
        UPDATE proverbs_validations SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_validations SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_validations SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_validations SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_validations SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_validations SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_bot_configs
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_bot_configs' AND column_name='bot_name') THEN
        UPDATE proverbs_bot_configs SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_bot_configs SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_bot_configs SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_bot_configs SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_bot_configs SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_bot_configs SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_strategy_analysis
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_strategy_analysis' AND column_name='bot_name') THEN
        UPDATE proverbs_strategy_analysis SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_strategy_analysis SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_strategy_analysis SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_strategy_analysis SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_strategy_analysis SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_strategy_analysis SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;

    -- proverbs_audit_log
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_audit_log' AND column_name='bot_name') THEN
        UPDATE proverbs_audit_log SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_audit_log SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_audit_log SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_audit_log SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_audit_log SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_audit_log SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
    END IF;
END $$;


-- =============================================================================
-- SECTION 4: VERIFICATION
-- =============================================================================

-- 4a. Old-name tables remaining
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
        RAISE NOTICE '  PASS: Zero old-name tables remain';
    ELSE
        RAISE WARNING '  FAIL: % old tables still exist: %', old_count, old_tables;
    END IF;
END $$;

-- 4b. Old bot names in bot_decision_logs
DO $$
DECLARE
    old_count INTEGER;
    old_names TEXT;
BEGIN
    SELECT COUNT(*), STRING_AGG(DISTINCT bot_name, ', ')
    INTO old_count, old_names
    FROM bot_decision_logs
    WHERE bot_name IN (
        'ARES','ATHENA','TITAN','PEGASUS','ICARUS',
        'PHOENIX','ATLAS','HERMES','PROMETHEUS','HERACLES',
        'ORACLE','SAGE','ARGUS','GEXIS','KRONOS',
        'HYPERION','APOLLO','ORION','NEXUS','SOLOMON'
    );
    IF old_count = 0 THEN
        RAISE NOTICE '  PASS: Zero old bot names in bot_decision_logs';
    ELSE
        RAISE WARNING '  FAIL: % rows with old names: %', old_count, old_names;
    END IF;
END $$;

-- 4c. Old config keys
DO $$
DECLARE
    old_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO old_count
    FROM autonomous_config
    WHERE key IN (
        'ares_starting_capital','athena_starting_capital',
        'titan_starting_capital','pegasus_starting_capital',
        'icarus_starting_capital','heracles_starting_capital',
        'ares_mode','ares_ticker'
    );
    IF old_count = 0 THEN
        RAISE NOTICE '  PASS: All config keys renamed';
    ELSE
        RAISE WARNING '  FAIL: % old config keys remain', old_count;
    END IF;
END $$;

-- 4d. Old ML model names
DO $$
DECLARE
    old_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO old_count
    FROM ml_models
    WHERE model_name IN ('ares_ml', 'heracles_ml');
    IF old_count = 0 THEN
        RAISE NOTICE '  PASS: All ML model names updated';
    ELSE
        RAISE WARNING '  FAIL: % old ML model names remain', old_count;
    END IF;
END $$;

COMMIT;

-- Final summary outside transaction
\echo ''
\echo '==========================================='
\echo '  MIGRATION V4 COMPLETE'
\echo '  All checks above should show PASS.'
\echo '==========================================='
