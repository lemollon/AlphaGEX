-- =============================================================================
-- AlphaGEX Bot Rename Migration V3: Greek Mythology → Biblical Names
-- =============================================================================
--
-- V3 fixes the "relation already exists" error from V2 by using a smart
-- rename function that handles ALL cases:
--   1. Only old table exists → RENAME
--   2. Only new table exists → SKIP (already done)
--   3. Both exist, new is empty → DROP new, RENAME old
--   4. Both exist, new has data → keep new, DROP old
--   5. Neither exists → SKIP
--
-- SAFETY:
--   - Wrapped in a single transaction (BEGIN/COMMIT)
--   - If ANY statement fails, the entire migration rolls back
--   - Helper function handles all edge cases
--
-- ROLLBACK: See bot_rename_rollback_v2.sql
--
-- Date: 2026-02-09
-- PR: #1488
-- =============================================================================

BEGIN;

-- =============================================================================
-- HELPER FUNCTION: Safe table rename that handles existing targets
-- =============================================================================
CREATE OR REPLACE FUNCTION _safe_rename(old_name TEXT, new_name TEXT)
RETURNS VOID AS $$
DECLARE
    old_exists BOOLEAN;
    new_exists BOOLEAN;
    old_count BIGINT;
    new_count BIGINT;
BEGIN
    SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=old_name) INTO old_exists;
    SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=new_name) INTO new_exists;

    IF old_exists AND NOT new_exists THEN
        -- Simple rename
        EXECUTE format('ALTER TABLE %I RENAME TO %I', old_name, new_name);
        RAISE NOTICE 'RENAMED % → %', old_name, new_name;

    ELSIF old_exists AND new_exists THEN
        -- Both exist: keep the one with data
        EXECUTE format('SELECT COUNT(*) FROM %I', new_name) INTO new_count;
        EXECUTE format('SELECT COUNT(*) FROM %I', old_name) INTO old_count;

        IF new_count = 0 AND old_count > 0 THEN
            -- New is empty, old has data: drop new, rename old
            EXECUTE format('DROP TABLE %I', new_name);
            EXECUTE format('ALTER TABLE %I RENAME TO %I', old_name, new_name);
            RAISE NOTICE 'REPLACED empty % with % (% rows)', new_name, old_name, old_count;
        ELSIF new_count = 0 AND old_count = 0 THEN
            -- Both empty: drop old, keep new (has correct schema from new code)
            EXECUTE format('DROP TABLE %I', old_name);
            RAISE NOTICE 'DROPPED empty old table %, kept empty %', old_name, new_name;
        ELSE
            -- New has data: keep new, drop old
            EXECUTE format('DROP TABLE %I CASCADE', old_name);
            RAISE NOTICE 'KEPT % (% rows), DROPPED old % (% rows)', new_name, new_count, old_name, old_count;
        END IF;

    ELSIF NOT old_exists AND new_exists THEN
        RAISE NOTICE 'SKIP % already exists (old % not found)', new_name, old_name;

    ELSE
        RAISE NOTICE 'SKIP neither % nor % exists', old_name, new_name;
    END IF;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- SECTION 1: TABLE RENAMES
-- =============================================================================
-- CRITICAL: SOLOMON advisory → PROVERBS must happen BEFORE ATHENA → SOLOMON.

-- ---------------------------------------------------------------------------
-- 1a. PROVERBS (formerly SOLOMON advisory) — MUST BE FIRST
-- ---------------------------------------------------------------------------
-- Rename ALL solomon_* tables to proverbs_* first. This catches both the
-- known advisory tables AND any we missed (like solomon_daily_perf).
-- The _safe_rename function handles tables that don't exist gracefully.

SELECT _safe_rename('solomon_ab_tests', 'proverbs_ab_tests');
SELECT _safe_rename('solomon_audit_log', 'proverbs_audit_log');
SELECT _safe_rename('solomon_bot_configs', 'proverbs_bot_configs');
SELECT _safe_rename('solomon_daily_perf', 'proverbs_daily_perf');
SELECT _safe_rename('solomon_daily_reports', 'proverbs_daily_reports');
SELECT _safe_rename('solomon_equity_snapshots', 'proverbs_equity_snapshots');
SELECT _safe_rename('solomon_health', 'proverbs_health');
SELECT _safe_rename('solomon_kill_switch', 'proverbs_kill_switch');
SELECT _safe_rename('solomon_logs', 'proverbs_logs');
SELECT _safe_rename('solomon_performance', 'proverbs_performance');
SELECT _safe_rename('solomon_positions', 'proverbs_positions');
SELECT _safe_rename('solomon_proposals', 'proverbs_proposals');
SELECT _safe_rename('solomon_rollbacks', 'proverbs_rollbacks');
SELECT _safe_rename('solomon_scan_activity', 'proverbs_scan_activity');
SELECT _safe_rename('solomon_signals', 'proverbs_signals');
SELECT _safe_rename('solomon_strategy_analysis', 'proverbs_strategy_analysis');
SELECT _safe_rename('solomon_validations', 'proverbs_validations');
SELECT _safe_rename('solomon_versions', 'proverbs_versions');
SELECT _safe_rename('solomon_closed_trades', 'proverbs_closed_trades');

-- ---------------------------------------------------------------------------
-- 1b. SOLOMON bot (formerly ATHENA) — Directional Spreads bot
-- ---------------------------------------------------------------------------
-- Safe now that ALL solomon_* tables are renamed to proverbs_*.

SELECT _safe_rename('athena_closed_trades', 'solomon_closed_trades');
SELECT _safe_rename('athena_daily_perf', 'solomon_daily_perf');
SELECT _safe_rename('athena_daily_reports', 'solomon_daily_reports');
SELECT _safe_rename('athena_equity_snapshots', 'solomon_equity_snapshots');
SELECT _safe_rename('athena_logs', 'solomon_logs');
SELECT _safe_rename('athena_positions', 'solomon_positions');
SELECT _safe_rename('athena_scan_activity', 'solomon_scan_activity');
SELECT _safe_rename('athena_signals', 'solomon_signals');

-- ---------------------------------------------------------------------------
-- 1c. FORTRESS (formerly ARES)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('ares_closed_trades', 'fortress_closed_trades');
SELECT _safe_rename('ares_daily_perf', 'fortress_daily_perf');
SELECT _safe_rename('ares_daily_performance', 'fortress_daily_performance');
SELECT _safe_rename('ares_daily_reports', 'fortress_daily_reports');
SELECT _safe_rename('ares_equity_snapshots', 'fortress_equity_snapshots');
SELECT _safe_rename('ares_logs', 'fortress_logs');
SELECT _safe_rename('ares_positions', 'fortress_positions');
SELECT _safe_rename('ares_scan_activity', 'fortress_scan_activity');
SELECT _safe_rename('ares_signals', 'fortress_signals');

-- ---------------------------------------------------------------------------
-- 1d. SAMSON (formerly TITAN)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('titan_closed_trades', 'samson_closed_trades');
SELECT _safe_rename('titan_daily_perf', 'samson_daily_perf');
SELECT _safe_rename('titan_daily_reports', 'samson_daily_reports');
SELECT _safe_rename('titan_equity_snapshots', 'samson_equity_snapshots');
SELECT _safe_rename('titan_logs', 'samson_logs');
SELECT _safe_rename('titan_positions', 'samson_positions');
SELECT _safe_rename('titan_scan_activity', 'samson_scan_activity');
SELECT _safe_rename('titan_signals', 'samson_signals');

-- ---------------------------------------------------------------------------
-- 1e. ANCHOR (formerly PEGASUS)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('pegasus_closed_trades', 'anchor_closed_trades');
SELECT _safe_rename('pegasus_daily_perf', 'anchor_daily_perf');
SELECT _safe_rename('pegasus_daily_reports', 'anchor_daily_reports');
SELECT _safe_rename('pegasus_equity_snapshots', 'anchor_equity_snapshots');
SELECT _safe_rename('pegasus_logs', 'anchor_logs');
SELECT _safe_rename('pegasus_positions', 'anchor_positions');
SELECT _safe_rename('pegasus_scan_activity', 'anchor_scan_activity');
SELECT _safe_rename('pegasus_signals', 'anchor_signals');

-- ---------------------------------------------------------------------------
-- 1f. GIDEON (formerly ICARUS)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('icarus_closed_trades', 'gideon_closed_trades');
SELECT _safe_rename('icarus_daily_perf', 'gideon_daily_perf');
SELECT _safe_rename('icarus_daily_reports', 'gideon_daily_reports');
SELECT _safe_rename('icarus_equity_snapshots', 'gideon_equity_snapshots');
SELECT _safe_rename('icarus_logs', 'gideon_logs');
SELECT _safe_rename('icarus_positions', 'gideon_positions');
SELECT _safe_rename('icarus_scan_activity', 'gideon_scan_activity');
SELECT _safe_rename('icarus_signals', 'gideon_signals');

-- ---------------------------------------------------------------------------
-- 1g. VALOR (formerly HERACLES)
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- 1h. JUBILEE (formerly PROMETHEUS)
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- 1i. PROPHET (formerly ORACLE)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('oracle_bot_interactions', 'prophet_bot_interactions');
SELECT _safe_rename('oracle_predictions', 'prophet_predictions');
SELECT _safe_rename('oracle_strategy_accuracy', 'prophet_strategy_accuracy');
SELECT _safe_rename('oracle_trained_models', 'prophet_trained_models');
SELECT _safe_rename('oracle_training_outcomes', 'prophet_training_outcomes');

-- ---------------------------------------------------------------------------
-- 1j. DISCERNMENT (formerly APOLLO)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('apollo_live_quotes', 'discernment_live_quotes');
SELECT _safe_rename('apollo_model_performance', 'discernment_model_performance');
SELECT _safe_rename('apollo_outcomes', 'discernment_outcomes');
SELECT _safe_rename('apollo_pin_risk_history', 'discernment_pin_risk_history');
SELECT _safe_rename('apollo_predictions', 'discernment_predictions');
SELECT _safe_rename('apollo_scans', 'discernment_scans');

-- ---------------------------------------------------------------------------
-- 1k. WATCHTOWER (formerly ARGUS)
-- ---------------------------------------------------------------------------

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

-- ---------------------------------------------------------------------------
-- 1l. CHRONICLES (formerly KRONOS)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('kronos_jobs', 'chronicles_jobs');

-- ---------------------------------------------------------------------------
-- 1m. GLORY (formerly HYPERION)
-- ---------------------------------------------------------------------------

SELECT _safe_rename('hyperion_gamma_history', 'glory_gamma_history');


-- =============================================================================
-- SECTION 2: CONFIG KEY UPDATES
-- =============================================================================

UPDATE autonomous_config SET key = 'fortress_starting_capital'
WHERE key = 'ares_starting_capital';

UPDATE autonomous_config SET key = 'solomon_starting_capital'
WHERE key = 'athena_starting_capital';

UPDATE autonomous_config SET key = 'samson_starting_capital'
WHERE key = 'titan_starting_capital';

UPDATE autonomous_config SET key = 'anchor_starting_capital'
WHERE key = 'pegasus_starting_capital';

UPDATE autonomous_config SET key = 'gideon_starting_capital'
WHERE key = 'icarus_starting_capital';

UPDATE autonomous_config SET key = 'valor_starting_capital'
WHERE key = 'heracles_starting_capital';

UPDATE autonomous_config SET key = 'fortress_mode'
WHERE key = 'ares_mode';

UPDATE autonomous_config SET key = 'fortress_ticker'
WHERE key = 'ares_ticker';


-- =============================================================================
-- SECTION 2B: ML_MODELS MODEL_NAME UPDATES
-- =============================================================================

UPDATE ml_models SET model_name = 'fortress_ml'
WHERE model_name = 'ares_ml';

UPDATE ml_models SET model_name = 'valor_ml'
WHERE model_name = 'heracles_ml';


-- =============================================================================
-- SECTION 3: BOT_NAME COLUMN VALUE UPDATES
-- =============================================================================
-- SOLOMON→PROVERBS must happen BEFORE ATHENA→SOLOMON.

-- ---------------------------------------------------------------------------
-- 3a. bot_decision_logs
-- ---------------------------------------------------------------------------

-- Advisory rename first
UPDATE bot_decision_logs SET bot_name = 'PROVERBS'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

-- Bot + advisory renames
UPDATE bot_decision_logs SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'LAZARUS'
WHERE bot_name = 'PHOENIX' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'CORNERSTONE'
WHERE bot_name = 'ATLAS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'SHEPHERD'
WHERE bot_name = 'HERMES' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'JUBILEE'
WHERE bot_name = 'PROMETHEUS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PROPHET'
WHERE bot_name = 'ORACLE' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'WISDOM'
WHERE bot_name = 'SAGE' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'WATCHTOWER'
WHERE bot_name = 'ARGUS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'STARS'
WHERE bot_name = 'ORION' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'COUNSELOR'
WHERE bot_name = 'GEXIS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'CHRONICLES'
WHERE bot_name = 'KRONOS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'GLORY'
WHERE bot_name = 'HYPERION' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'DISCERNMENT'
WHERE bot_name = 'APOLLO' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'COVENANT'
WHERE bot_name = 'NEXUS' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3b. trading_decisions — strategy column
-- ---------------------------------------------------------------------------

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ARES', 'FORTRESS')
WHERE strategy LIKE '%ARES%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ATHENA', 'SOLOMON')
WHERE strategy LIKE '%ATHENA%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'TITAN', 'SAMSON')
WHERE strategy LIKE '%TITAN%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'PEGASUS', 'ANCHOR')
WHERE strategy LIKE '%PEGASUS%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ICARUS', 'GIDEON')
WHERE strategy LIKE '%ICARUS%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'PHOENIX', 'LAZARUS')
WHERE strategy LIKE '%PHOENIX%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'HERACLES', 'VALOR')
WHERE strategy LIKE '%HERACLES%' AND strategy IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3c. ml_decision_logs — action column
-- ---------------------------------------------------------------------------

UPDATE ml_decision_logs SET action = REPLACE(action, 'ARES', 'FORTRESS')
WHERE action LIKE '%ARES%' AND action IS NOT NULL;

UPDATE ml_decision_logs SET action = REPLACE(action, 'ATHENA', 'SOLOMON')
WHERE action LIKE '%ATHENA%' AND action IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3d-3k. proverbs_* tables — bot_name columns
-- Uses DO blocks to handle tables that may not exist.
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    -- proverbs_proposals
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='proverbs_proposals') THEN
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
        RAISE NOTICE 'Updated proverbs_proposals bot_name values';
    END IF;

    -- proverbs_kill_switch
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='proverbs_kill_switch') THEN
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
        RAISE NOTICE 'Updated proverbs_kill_switch bot_name values';
    END IF;

    -- proverbs_versions
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='proverbs_versions') THEN
        UPDATE proverbs_versions SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_versions SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_versions SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_versions SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_versions SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_versions SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
        RAISE NOTICE 'Updated proverbs_versions bot_name values';
    END IF;

    -- proverbs_performance
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='proverbs_performance') THEN
        UPDATE proverbs_performance SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_performance SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_performance SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_performance SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_performance SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_performance SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
        RAISE NOTICE 'Updated proverbs_performance bot_name values';
    END IF;

    -- proverbs_validations
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='proverbs_validations') THEN
        UPDATE proverbs_validations SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_validations SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_validations SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_validations SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_validations SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_validations SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
        RAISE NOTICE 'Updated proverbs_validations bot_name values';
    END IF;

    -- proverbs_bot_configs
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='proverbs_bot_configs') THEN
        UPDATE proverbs_bot_configs SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_bot_configs SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_bot_configs SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_bot_configs SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_bot_configs SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_bot_configs SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
        RAISE NOTICE 'Updated proverbs_bot_configs bot_name values';
    END IF;

    -- proverbs_strategy_analysis (if bot_name column exists)
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_strategy_analysis' AND column_name='bot_name') THEN
        UPDATE proverbs_strategy_analysis SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_strategy_analysis SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_strategy_analysis SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_strategy_analysis SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_strategy_analysis SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_strategy_analysis SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
        RAISE NOTICE 'Updated proverbs_strategy_analysis bot_name values';
    END IF;

    -- proverbs_audit_log (if bot_name column exists)
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='proverbs_audit_log' AND column_name='bot_name') THEN
        UPDATE proverbs_audit_log SET bot_name = 'FORTRESS' WHERE bot_name = 'ARES';
        UPDATE proverbs_audit_log SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';
        UPDATE proverbs_audit_log SET bot_name = 'SAMSON' WHERE bot_name = 'TITAN';
        UPDATE proverbs_audit_log SET bot_name = 'ANCHOR' WHERE bot_name = 'PEGASUS';
        UPDATE proverbs_audit_log SET bot_name = 'GIDEON' WHERE bot_name = 'ICARUS';
        UPDATE proverbs_audit_log SET bot_name = 'VALOR' WHERE bot_name = 'HERACLES';
        RAISE NOTICE 'Updated proverbs_audit_log bot_name values';
    END IF;
END $$;


-- =============================================================================
-- SECTION 4: VERIFICATION
-- =============================================================================

-- 4a. Verify no old-name tables remain
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
        RAISE NOTICE 'PASS: Zero old-name tables remain';
    ELSE
        RAISE WARNING 'FAIL: % old tables still exist: %', old_count, old_tables;
    END IF;
END $$;

-- 4b. Verify no old bot names in bot_decision_logs
DO $$
DECLARE
    old_count INTEGER;
    old_names TEXT;
BEGIN
    SELECT COUNT(*), STRING_AGG(DISTINCT bot_name, ', ')
    INTO old_count, old_names
    FROM bot_decision_logs
    WHERE bot_name IN (
        'ARES', 'ATHENA', 'TITAN', 'PEGASUS', 'ICARUS',
        'PHOENIX', 'ATLAS', 'HERMES', 'PROMETHEUS', 'HERACLES',
        'ORACLE', 'SAGE', 'ARGUS', 'GEXIS', 'KRONOS',
        'HYPERION', 'APOLLO', 'ORION', 'NEXUS', 'SOLOMON'
    );

    IF old_count = 0 THEN
        RAISE NOTICE 'PASS: Zero old bot names in bot_decision_logs';
    ELSE
        RAISE WARNING 'FAIL: % rows with old names: %', old_count, old_names;
    END IF;
END $$;

-- 4c. Show current bot_name values
DO $$
DECLARE
    names TEXT;
BEGIN
    SELECT STRING_AGG(DISTINCT bot_name, ', ' ORDER BY bot_name)
    INTO names
    FROM bot_decision_logs;
    RAISE NOTICE 'bot_decision_logs values: %', COALESCE(names, '(empty)');
END $$;

-- 4d. Verify config keys
DO $$
DECLARE
    old_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO old_count
    FROM autonomous_config
    WHERE key IN (
        'ares_starting_capital', 'athena_starting_capital',
        'titan_starting_capital', 'pegasus_starting_capital',
        'icarus_starting_capital', 'heracles_starting_capital',
        'ares_mode', 'ares_ticker'
    );
    IF old_count = 0 THEN
        RAISE NOTICE 'PASS: All config keys renamed';
    ELSE
        RAISE WARNING 'FAIL: % old config keys remain', old_count;
    END IF;
END $$;

-- 4e. Verify ml_models
DO $$
DECLARE
    old_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO old_count
    FROM ml_models
    WHERE model_name IN ('ares_ml', 'heracles_ml');
    IF old_count = 0 THEN
        RAISE NOTICE 'PASS: All ML model names updated';
    ELSE
        RAISE WARNING 'FAIL: % old ML model names remain', old_count;
    END IF;
END $$;

-- Cleanup helper function
DROP FUNCTION IF EXISTS _safe_rename(TEXT, TEXT);

COMMIT;
