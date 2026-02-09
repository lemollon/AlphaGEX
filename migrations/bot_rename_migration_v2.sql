-- =============================================================================
-- AlphaGEX Bot Rename Migration V2: Greek Mythology → Biblical Names
-- =============================================================================
--
-- COMPLETE migration covering ALL 95 production tables plus safety coverage
-- for tables that may exist in other environments.
--
-- SCOPE:
--   Section 1: ~106 table renames (all old-name tables, with IF EXISTS)
--   Section 2: Config key updates in autonomous_config
--   Section 2B: ml_models model_name updates
--   Section 3: bot_name column value updates in 7+ tables
--   Section 4: Verification queries
--
-- CRITICAL ORDERING:
--   SOLOMON advisory tables → PROVERBS (Section 1h)
--   MUST run BEFORE
--   ATHENA tables → SOLOMON (Section 1b)
--
-- SAFETY:
--   - Wrapped in a single transaction (BEGIN/COMMIT)
--   - If ANY statement fails, the entire migration rolls back
--   - No data is deleted or dropped
--   - Uses IF EXISTS to handle tables that may not exist
--
-- ROLLBACK: See bot_rename_rollback_v2.sql
--
-- Date: 2026-02-09
-- PR: #1488
-- =============================================================================

BEGIN;

-- =============================================================================
-- SECTION 1: TABLE RENAMES
-- =============================================================================
-- CRITICAL: SOLOMON advisory → PROVERBS must happen BEFORE ATHENA → SOLOMON.
-- This prevents the ATHENA bot tables from colliding with old advisory tables.

-- ---------------------------------------------------------------------------
-- 1a. PROVERBS (formerly SOLOMON advisory) — MUST BE FIRST
-- ---------------------------------------------------------------------------
-- The advisory system "SOLOMON" was renamed to "PROVERBS" in code.
-- The bot "ATHENA" will then be renamed to "SOLOMON" in Section 1b.
-- Renaming these first prevents name collisions.

ALTER TABLE IF EXISTS solomon_ab_tests RENAME TO proverbs_ab_tests;
ALTER TABLE IF EXISTS solomon_audit_log RENAME TO proverbs_audit_log;
ALTER TABLE IF EXISTS solomon_bot_configs RENAME TO proverbs_bot_configs;
ALTER TABLE IF EXISTS solomon_health RENAME TO proverbs_health;
ALTER TABLE IF EXISTS solomon_kill_switch RENAME TO proverbs_kill_switch;
ALTER TABLE IF EXISTS solomon_performance RENAME TO proverbs_performance;
ALTER TABLE IF EXISTS solomon_proposals RENAME TO proverbs_proposals;
ALTER TABLE IF EXISTS solomon_rollbacks RENAME TO proverbs_rollbacks;
ALTER TABLE IF EXISTS solomon_strategy_analysis RENAME TO proverbs_strategy_analysis;
ALTER TABLE IF EXISTS solomon_validations RENAME TO proverbs_validations;
ALTER TABLE IF EXISTS solomon_versions RENAME TO proverbs_versions;

-- ---------------------------------------------------------------------------
-- 1b. SOLOMON bot (formerly ATHENA) — Directional Spreads bot
-- ---------------------------------------------------------------------------
-- Safe to run now that solomon_* advisory tables are renamed to proverbs_*.

ALTER TABLE IF EXISTS athena_closed_trades RENAME TO solomon_closed_trades;
ALTER TABLE IF EXISTS athena_daily_perf RENAME TO solomon_daily_perf;
ALTER TABLE IF EXISTS athena_daily_reports RENAME TO solomon_daily_reports;
ALTER TABLE IF EXISTS athena_equity_snapshots RENAME TO solomon_equity_snapshots;
ALTER TABLE IF EXISTS athena_logs RENAME TO solomon_logs;
ALTER TABLE IF EXISTS athena_positions RENAME TO solomon_positions;
ALTER TABLE IF EXISTS athena_scan_activity RENAME TO solomon_scan_activity;
ALTER TABLE IF EXISTS athena_signals RENAME TO solomon_signals;

-- ---------------------------------------------------------------------------
-- 1c. FORTRESS (formerly ARES) — Aggressive Iron Condor bot
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS ares_closed_trades RENAME TO fortress_closed_trades;
ALTER TABLE IF EXISTS ares_daily_perf RENAME TO fortress_daily_perf;
ALTER TABLE IF EXISTS ares_daily_performance RENAME TO fortress_daily_performance;
ALTER TABLE IF EXISTS ares_daily_reports RENAME TO fortress_daily_reports;
ALTER TABLE IF EXISTS ares_equity_snapshots RENAME TO fortress_equity_snapshots;
ALTER TABLE IF EXISTS ares_logs RENAME TO fortress_logs;
ALTER TABLE IF EXISTS ares_positions RENAME TO fortress_positions;
ALTER TABLE IF EXISTS ares_scan_activity RENAME TO fortress_scan_activity;
ALTER TABLE IF EXISTS ares_signals RENAME TO fortress_signals;

-- ---------------------------------------------------------------------------
-- 1d. SAMSON (formerly TITAN) — Aggressive SPX Iron Condor bot
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS titan_closed_trades RENAME TO samson_closed_trades;
ALTER TABLE IF EXISTS titan_daily_perf RENAME TO samson_daily_perf;
ALTER TABLE IF EXISTS titan_daily_reports RENAME TO samson_daily_reports;
ALTER TABLE IF EXISTS titan_equity_snapshots RENAME TO samson_equity_snapshots;
ALTER TABLE IF EXISTS titan_logs RENAME TO samson_logs;
ALTER TABLE IF EXISTS titan_positions RENAME TO samson_positions;
ALTER TABLE IF EXISTS titan_scan_activity RENAME TO samson_scan_activity;
ALTER TABLE IF EXISTS titan_signals RENAME TO samson_signals;

-- ---------------------------------------------------------------------------
-- 1e. ANCHOR (formerly PEGASUS) — SPX Weekly Iron Condor bot
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS pegasus_closed_trades RENAME TO anchor_closed_trades;
ALTER TABLE IF EXISTS pegasus_daily_perf RENAME TO anchor_daily_perf;
ALTER TABLE IF EXISTS pegasus_daily_reports RENAME TO anchor_daily_reports;
ALTER TABLE IF EXISTS pegasus_equity_snapshots RENAME TO anchor_equity_snapshots;
ALTER TABLE IF EXISTS pegasus_logs RENAME TO anchor_logs;
ALTER TABLE IF EXISTS pegasus_positions RENAME TO anchor_positions;
ALTER TABLE IF EXISTS pegasus_scan_activity RENAME TO anchor_scan_activity;
ALTER TABLE IF EXISTS pegasus_signals RENAME TO anchor_signals;

-- ---------------------------------------------------------------------------
-- 1f. GIDEON (formerly ICARUS) — Aggressive Directional bot
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS icarus_closed_trades RENAME TO gideon_closed_trades;
ALTER TABLE IF EXISTS icarus_daily_perf RENAME TO gideon_daily_perf;
ALTER TABLE IF EXISTS icarus_daily_reports RENAME TO gideon_daily_reports;
ALTER TABLE IF EXISTS icarus_equity_snapshots RENAME TO gideon_equity_snapshots;
ALTER TABLE IF EXISTS icarus_logs RENAME TO gideon_logs;
ALTER TABLE IF EXISTS icarus_positions RENAME TO gideon_positions;
ALTER TABLE IF EXISTS icarus_scan_activity RENAME TO gideon_scan_activity;
ALTER TABLE IF EXISTS icarus_signals RENAME TO gideon_signals;

-- ---------------------------------------------------------------------------
-- 1g. VALOR (formerly HERACLES) — Options trading bot
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS heracles_closed_trades RENAME TO valor_closed_trades;
ALTER TABLE IF EXISTS heracles_config RENAME TO valor_config;
ALTER TABLE IF EXISTS heracles_daily_perf RENAME TO valor_daily_perf;
ALTER TABLE IF EXISTS heracles_equity_snapshots RENAME TO valor_equity_snapshots;
ALTER TABLE IF EXISTS heracles_logs RENAME TO valor_logs;
ALTER TABLE IF EXISTS heracles_paper_account RENAME TO valor_paper_account;
ALTER TABLE IF EXISTS heracles_positions RENAME TO valor_positions;
ALTER TABLE IF EXISTS heracles_scan_activity RENAME TO valor_scan_activity;
ALTER TABLE IF EXISTS heracles_signals RENAME TO valor_signals;
ALTER TABLE IF EXISTS heracles_win_tracker RENAME TO valor_win_tracker;

-- ---------------------------------------------------------------------------
-- 1h. JUBILEE (formerly PROMETHEUS) — Box Spread Synthetic Borrowing + IC
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS prometheus_capital_deployments RENAME TO jubilee_capital_deployments;
ALTER TABLE IF EXISTS prometheus_config RENAME TO jubilee_config;
ALTER TABLE IF EXISTS prometheus_daily_briefings RENAME TO jubilee_daily_briefings;
ALTER TABLE IF EXISTS prometheus_equity_snapshots RENAME TO jubilee_equity_snapshots;
ALTER TABLE IF EXISTS prometheus_ic_closed_trades RENAME TO jubilee_ic_closed_trades;
ALTER TABLE IF EXISTS prometheus_ic_config RENAME TO jubilee_ic_config;
ALTER TABLE IF EXISTS prometheus_ic_equity_snapshots RENAME TO jubilee_ic_equity_snapshots;
ALTER TABLE IF EXISTS prometheus_ic_positions RENAME TO jubilee_ic_positions;
ALTER TABLE IF EXISTS prometheus_ic_signals RENAME TO jubilee_ic_signals;
ALTER TABLE IF EXISTS prometheus_live_model RENAME TO jubilee_live_model;
ALTER TABLE IF EXISTS prometheus_logs RENAME TO jubilee_logs;
ALTER TABLE IF EXISTS prometheus_models RENAME TO jubilee_models;
ALTER TABLE IF EXISTS prometheus_positions RENAME TO jubilee_positions;
ALTER TABLE IF EXISTS prometheus_predictions RENAME TO jubilee_predictions;
ALTER TABLE IF EXISTS prometheus_rate_analysis RENAME TO jubilee_rate_analysis;
ALTER TABLE IF EXISTS prometheus_roll_decisions RENAME TO jubilee_roll_decisions;
ALTER TABLE IF EXISTS prometheus_signals RENAME TO jubilee_signals;
ALTER TABLE IF EXISTS prometheus_training_history RENAME TO jubilee_training_history;

-- ---------------------------------------------------------------------------
-- 1i. PROPHET (formerly ORACLE) — ML Advisory system
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS oracle_bot_interactions RENAME TO prophet_bot_interactions;
ALTER TABLE IF EXISTS oracle_predictions RENAME TO prophet_predictions;
ALTER TABLE IF EXISTS oracle_strategy_accuracy RENAME TO prophet_strategy_accuracy;
ALTER TABLE IF EXISTS oracle_trained_models RENAME TO prophet_trained_models;
ALTER TABLE IF EXISTS oracle_training_outcomes RENAME TO prophet_training_outcomes;

-- ---------------------------------------------------------------------------
-- 1j. DISCERNMENT (formerly APOLLO) — ML Scanner
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS apollo_live_quotes RENAME TO discernment_live_quotes;
ALTER TABLE IF EXISTS apollo_model_performance RENAME TO discernment_model_performance;
ALTER TABLE IF EXISTS apollo_outcomes RENAME TO discernment_outcomes;
ALTER TABLE IF EXISTS apollo_pin_risk_history RENAME TO discernment_pin_risk_history;
ALTER TABLE IF EXISTS apollo_predictions RENAME TO discernment_predictions;
ALTER TABLE IF EXISTS apollo_scans RENAME TO discernment_scans;

-- ---------------------------------------------------------------------------
-- 1k. WATCHTOWER (formerly ARGUS) — Real-time Gamma Visualization
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS argus_accuracy RENAME TO watchtower_accuracy;
ALTER TABLE IF EXISTS argus_alerts RENAME TO watchtower_alerts;
ALTER TABLE IF EXISTS argus_commentary RENAME TO watchtower_commentary;
ALTER TABLE IF EXISTS argus_danger_zone_logs RENAME TO watchtower_danger_zone_logs;
ALTER TABLE IF EXISTS argus_gamma_flips RENAME TO watchtower_gamma_flips;
ALTER TABLE IF EXISTS argus_gamma_history RENAME TO watchtower_gamma_history;
ALTER TABLE IF EXISTS argus_order_flow_history RENAME TO watchtower_order_flow_history;
ALTER TABLE IF EXISTS argus_outcomes RENAME TO watchtower_outcomes;
ALTER TABLE IF EXISTS argus_pin_predictions RENAME TO watchtower_pin_predictions;
ALTER TABLE IF EXISTS argus_predictions RENAME TO watchtower_predictions;
ALTER TABLE IF EXISTS argus_snapshots RENAME TO watchtower_snapshots;
ALTER TABLE IF EXISTS argus_strikes RENAME TO watchtower_strikes;
ALTER TABLE IF EXISTS argus_trade_signals RENAME TO watchtower_trade_signals;

-- ---------------------------------------------------------------------------
-- 1l. CHRONICLES (formerly KRONOS) — Background job tracking
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS kronos_jobs RENAME TO chronicles_jobs;

-- ---------------------------------------------------------------------------
-- 1m. GLORY (formerly HYPERION) — Weekly gamma history
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS hyperion_gamma_history RENAME TO glory_gamma_history;

-- ---------------------------------------------------------------------------
-- Note: These bots do NOT have dedicated tables (confirmed):
--   LAZARUS (formerly PHOENIX) — Uses shared autonomous_* tables
--   CORNERSTONE (formerly ATLAS) — Uses shared wheel_* tables
--   SHEPHERD (formerly HERMES) — UI-only, no database tables
-- ---------------------------------------------------------------------------


-- =============================================================================
-- SECTION 2: CONFIG KEY UPDATES
-- =============================================================================
-- The autonomous_config table stores key-value pairs. Bot-specific config keys
-- need their prefix updated to match the new bot names.

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
-- Multiple tables store bot/advisor names as string values in columns.
-- Historical rows have old Greek names that need updating to Biblical names.
--
-- SOLOMON COLLISION NOTE:
-- The advisory system "SOLOMON" was renamed to "PROVERBS".
-- The bot "ATHENA" was then renamed to "SOLOMON".
-- We update SOLOMON→PROVERBS first, then ATHENA→SOLOMON, to preserve ordering.

-- ---------------------------------------------------------------------------
-- 3a. bot_decision_logs — Master audit trail for all bot decisions
-- ---------------------------------------------------------------------------

-- Advisory rename first (SOLOMON advisory → PROVERBS)
UPDATE bot_decision_logs SET bot_name = 'PROVERBS'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

-- Then all bot + advisory renames
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
-- 3b. trading_decisions — strategy column may contain bot references
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
-- 3d. proverbs_proposals — bot_name column (target bot for proposals)
-- ---------------------------------------------------------------------------

UPDATE proverbs_proposals SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'LAZARUS'
WHERE bot_name = 'PHOENIX' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'CORNERSTONE'
WHERE bot_name = 'ATLAS' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'SHEPHERD'
WHERE bot_name = 'HERMES' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'JUBILEE'
WHERE bot_name = 'PROMETHEUS' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3e. proverbs_kill_switch — bot_name column
-- ---------------------------------------------------------------------------

UPDATE proverbs_kill_switch SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'LAZARUS'
WHERE bot_name = 'PHOENIX' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'CORNERSTONE'
WHERE bot_name = 'ATLAS' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'SHEPHERD'
WHERE bot_name = 'HERMES' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'JUBILEE'
WHERE bot_name = 'PROMETHEUS' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3f. proverbs_versions — bot_name column
-- ---------------------------------------------------------------------------

UPDATE proverbs_versions SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3g. proverbs_performance — bot_name column
-- ---------------------------------------------------------------------------

UPDATE proverbs_performance SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3h. proverbs_validations — bot_name column
-- ---------------------------------------------------------------------------

UPDATE proverbs_validations SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3i. proverbs_bot_configs — bot_name column
-- ---------------------------------------------------------------------------

UPDATE proverbs_bot_configs SET bot_name = 'FORTRESS'
WHERE bot_name = 'ARES' AND bot_name IS NOT NULL;

UPDATE proverbs_bot_configs SET bot_name = 'SOLOMON'
WHERE bot_name = 'ATHENA' AND bot_name IS NOT NULL;

UPDATE proverbs_bot_configs SET bot_name = 'SAMSON'
WHERE bot_name = 'TITAN' AND bot_name IS NOT NULL;

UPDATE proverbs_bot_configs SET bot_name = 'ANCHOR'
WHERE bot_name = 'PEGASUS' AND bot_name IS NOT NULL;

UPDATE proverbs_bot_configs SET bot_name = 'GIDEON'
WHERE bot_name = 'ICARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_bot_configs SET bot_name = 'VALOR'
WHERE bot_name = 'HERACLES' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3j. proverbs_strategy_analysis — bot_name column (if exists)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'proverbs_strategy_analysis' AND column_name = 'bot_name'
    ) THEN
        EXECUTE 'UPDATE proverbs_strategy_analysis SET bot_name = ''FORTRESS'' WHERE bot_name = ''ARES''';
        EXECUTE 'UPDATE proverbs_strategy_analysis SET bot_name = ''SOLOMON'' WHERE bot_name = ''ATHENA''';
        EXECUTE 'UPDATE proverbs_strategy_analysis SET bot_name = ''SAMSON'' WHERE bot_name = ''TITAN''';
        EXECUTE 'UPDATE proverbs_strategy_analysis SET bot_name = ''ANCHOR'' WHERE bot_name = ''PEGASUS''';
        EXECUTE 'UPDATE proverbs_strategy_analysis SET bot_name = ''GIDEON'' WHERE bot_name = ''ICARUS''';
        EXECUTE 'UPDATE proverbs_strategy_analysis SET bot_name = ''VALOR'' WHERE bot_name = ''HERACLES''';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3k. proverbs_audit_log — bot_name column (if exists)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'proverbs_audit_log' AND column_name = 'bot_name'
    ) THEN
        EXECUTE 'UPDATE proverbs_audit_log SET bot_name = ''FORTRESS'' WHERE bot_name = ''ARES''';
        EXECUTE 'UPDATE proverbs_audit_log SET bot_name = ''SOLOMON'' WHERE bot_name = ''ATHENA''';
        EXECUTE 'UPDATE proverbs_audit_log SET bot_name = ''SAMSON'' WHERE bot_name = ''TITAN''';
        EXECUTE 'UPDATE proverbs_audit_log SET bot_name = ''ANCHOR'' WHERE bot_name = ''PEGASUS''';
        EXECUTE 'UPDATE proverbs_audit_log SET bot_name = ''GIDEON'' WHERE bot_name = ''ICARUS''';
        EXECUTE 'UPDATE proverbs_audit_log SET bot_name = ''VALOR'' WHERE bot_name = ''HERACLES''';
    END IF;
END $$;


-- =============================================================================
-- SECTION 4: VERIFICATION QUERIES
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

-- 4b. Verify solomon_* tables are now the ATHENA bot tables (not advisory)
DO $$
DECLARE
    sol_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO sol_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE 'solomon_%';

    IF sol_count > 0 THEN
        RAISE NOTICE 'PASS: % solomon_* tables exist (these are the ATHENA bot tables)', sol_count;
    ELSE
        RAISE WARNING 'NOTE: No solomon_* tables found (ATHENA bot may not have had tables)';
    END IF;
END $$;

-- 4c. Verify no old bot names in bot_decision_logs
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

-- 4d. Show current distinct bot_name values
DO $$
DECLARE
    names TEXT;
BEGIN
    SELECT STRING_AGG(DISTINCT bot_name, ', ' ORDER BY bot_name)
    INTO names
    FROM bot_decision_logs;

    RAISE NOTICE 'bot_decision_logs bot_name values: %', COALESCE(names, '(empty)');
END $$;

-- 4e. Verify config keys updated
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

-- 4f. Verify ml_models updated
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

COMMIT;

-- =============================================================================
-- POST-MIGRATION NOTES:
-- =============================================================================
-- 1. Tables NOT renamed (by design):
--    - autonomous_open_positions, autonomous_closed_trades (shared, no bot prefix)
--    - autonomous_config (shared table, only key VALUES were updated)
--    - gex_history, gamma_history, regime_classifications (data tables)
--    - bot_decision_logs (shared table, only bot_name VALUES were updated)
--    - wheel_cycles, wheel_config (CORNERSTONE/ATLAS uses these, no prefix)
--
-- 2. JSONB columns (full_decision, details, supporting_metrics) are NOT updated.
--    They may contain old bot name strings as embedded data. This is acceptable
--    as JSONB is used for historical context, not lookup keys.
--
-- 3. DB column names (oracle_confidence, oracle_advice, argus_pattern_match,
--    etc.) are NOT renamed. The application code reads these columns by their
--    existing names. Renaming columns would require ALTER TABLE + code changes.
--
-- 4. Indexes are automatically renamed with their parent tables in PostgreSQL.
--    Custom index names may retain old prefixes (cosmetic only).
-- =============================================================================
