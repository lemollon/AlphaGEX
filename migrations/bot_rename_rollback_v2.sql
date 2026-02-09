-- =============================================================================
-- AlphaGEX Bot Rename ROLLBACK V2: Biblical Names → Greek Mythology
-- =============================================================================
--
-- Perfect reverse of bot_rename_migration_v2.sql.
-- Restores ALL tables, config keys, and bot_name values to Greek names.
--
-- CRITICAL ORDERING:
--   SOLOMON bot tables → ATHENA (Section 1b)
--   MUST run BEFORE
--   PROVERBS tables → SOLOMON advisory (Section 1a-final)
--
-- SAFETY:
--   - Wrapped in a single transaction (BEGIN/COMMIT)
--   - Uses IF EXISTS for safety
--
-- Date: 2026-02-09
-- =============================================================================

BEGIN;

-- =============================================================================
-- SECTION 1: TABLE RENAMES (reverse)
-- =============================================================================
-- CRITICAL: SOLOMON (bot) → ATHENA must happen BEFORE PROVERBS → SOLOMON.
-- This is the reverse of the migration ordering.

-- ---------------------------------------------------------------------------
-- 1a. ATHENA (reverse from SOLOMON bot) — MUST BE FIRST
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS solomon_closed_trades RENAME TO athena_closed_trades;
ALTER TABLE IF EXISTS solomon_daily_perf RENAME TO athena_daily_perf;
ALTER TABLE IF EXISTS solomon_daily_reports RENAME TO athena_daily_reports;
ALTER TABLE IF EXISTS solomon_equity_snapshots RENAME TO athena_equity_snapshots;
ALTER TABLE IF EXISTS solomon_logs RENAME TO athena_logs;
ALTER TABLE IF EXISTS solomon_positions RENAME TO athena_positions;
ALTER TABLE IF EXISTS solomon_scan_activity RENAME TO athena_scan_activity;
ALTER TABLE IF EXISTS solomon_signals RENAME TO athena_signals;

-- ---------------------------------------------------------------------------
-- 1a-final. SOLOMON advisory (reverse from PROVERBS) — AFTER bot rollback
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS proverbs_ab_tests RENAME TO solomon_ab_tests;
ALTER TABLE IF EXISTS proverbs_audit_log RENAME TO solomon_audit_log;
ALTER TABLE IF EXISTS proverbs_bot_configs RENAME TO solomon_bot_configs;
ALTER TABLE IF EXISTS proverbs_health RENAME TO solomon_health;
ALTER TABLE IF EXISTS proverbs_kill_switch RENAME TO solomon_kill_switch;
ALTER TABLE IF EXISTS proverbs_performance RENAME TO solomon_performance;
ALTER TABLE IF EXISTS proverbs_proposals RENAME TO solomon_proposals;
ALTER TABLE IF EXISTS proverbs_rollbacks RENAME TO solomon_rollbacks;
ALTER TABLE IF EXISTS proverbs_strategy_analysis RENAME TO solomon_strategy_analysis;
ALTER TABLE IF EXISTS proverbs_validations RENAME TO solomon_validations;
ALTER TABLE IF EXISTS proverbs_versions RENAME TO solomon_versions;

-- ---------------------------------------------------------------------------
-- 1b. ARES (reverse from FORTRESS)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS fortress_closed_trades RENAME TO ares_closed_trades;
ALTER TABLE IF EXISTS fortress_daily_perf RENAME TO ares_daily_perf;
ALTER TABLE IF EXISTS fortress_daily_performance RENAME TO ares_daily_performance;
ALTER TABLE IF EXISTS fortress_daily_reports RENAME TO ares_daily_reports;
ALTER TABLE IF EXISTS fortress_equity_snapshots RENAME TO ares_equity_snapshots;
ALTER TABLE IF EXISTS fortress_logs RENAME TO ares_logs;
ALTER TABLE IF EXISTS fortress_positions RENAME TO ares_positions;
ALTER TABLE IF EXISTS fortress_scan_activity RENAME TO ares_scan_activity;
ALTER TABLE IF EXISTS fortress_signals RENAME TO ares_signals;

-- ---------------------------------------------------------------------------
-- 1c. TITAN (reverse from SAMSON)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS samson_closed_trades RENAME TO titan_closed_trades;
ALTER TABLE IF EXISTS samson_daily_perf RENAME TO titan_daily_perf;
ALTER TABLE IF EXISTS samson_daily_reports RENAME TO titan_daily_reports;
ALTER TABLE IF EXISTS samson_equity_snapshots RENAME TO titan_equity_snapshots;
ALTER TABLE IF EXISTS samson_logs RENAME TO titan_logs;
ALTER TABLE IF EXISTS samson_positions RENAME TO titan_positions;
ALTER TABLE IF EXISTS samson_scan_activity RENAME TO titan_scan_activity;
ALTER TABLE IF EXISTS samson_signals RENAME TO titan_signals;

-- ---------------------------------------------------------------------------
-- 1d. PEGASUS (reverse from ANCHOR)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS anchor_closed_trades RENAME TO pegasus_closed_trades;
ALTER TABLE IF EXISTS anchor_daily_perf RENAME TO pegasus_daily_perf;
ALTER TABLE IF EXISTS anchor_daily_reports RENAME TO pegasus_daily_reports;
ALTER TABLE IF EXISTS anchor_equity_snapshots RENAME TO pegasus_equity_snapshots;
ALTER TABLE IF EXISTS anchor_logs RENAME TO pegasus_logs;
ALTER TABLE IF EXISTS anchor_positions RENAME TO pegasus_positions;
ALTER TABLE IF EXISTS anchor_scan_activity RENAME TO pegasus_scan_activity;
ALTER TABLE IF EXISTS anchor_signals RENAME TO pegasus_signals;

-- ---------------------------------------------------------------------------
-- 1e. ICARUS (reverse from GIDEON)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS gideon_closed_trades RENAME TO icarus_closed_trades;
ALTER TABLE IF EXISTS gideon_daily_perf RENAME TO icarus_daily_perf;
ALTER TABLE IF EXISTS gideon_daily_reports RENAME TO icarus_daily_reports;
ALTER TABLE IF EXISTS gideon_equity_snapshots RENAME TO icarus_equity_snapshots;
ALTER TABLE IF EXISTS gideon_logs RENAME TO icarus_logs;
ALTER TABLE IF EXISTS gideon_positions RENAME TO icarus_positions;
ALTER TABLE IF EXISTS gideon_scan_activity RENAME TO icarus_scan_activity;
ALTER TABLE IF EXISTS gideon_signals RENAME TO icarus_signals;

-- ---------------------------------------------------------------------------
-- 1f. HERACLES (reverse from VALOR)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS valor_closed_trades RENAME TO heracles_closed_trades;
ALTER TABLE IF EXISTS valor_config RENAME TO heracles_config;
ALTER TABLE IF EXISTS valor_daily_perf RENAME TO heracles_daily_perf;
ALTER TABLE IF EXISTS valor_equity_snapshots RENAME TO heracles_equity_snapshots;
ALTER TABLE IF EXISTS valor_logs RENAME TO heracles_logs;
ALTER TABLE IF EXISTS valor_paper_account RENAME TO heracles_paper_account;
ALTER TABLE IF EXISTS valor_positions RENAME TO heracles_positions;
ALTER TABLE IF EXISTS valor_scan_activity RENAME TO heracles_scan_activity;
ALTER TABLE IF EXISTS valor_signals RENAME TO heracles_signals;
ALTER TABLE IF EXISTS valor_win_tracker RENAME TO heracles_win_tracker;

-- ---------------------------------------------------------------------------
-- 1g. PROMETHEUS (reverse from JUBILEE)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS jubilee_capital_deployments RENAME TO prometheus_capital_deployments;
ALTER TABLE IF EXISTS jubilee_config RENAME TO prometheus_config;
ALTER TABLE IF EXISTS jubilee_daily_briefings RENAME TO prometheus_daily_briefings;
ALTER TABLE IF EXISTS jubilee_equity_snapshots RENAME TO prometheus_equity_snapshots;
ALTER TABLE IF EXISTS jubilee_ic_closed_trades RENAME TO prometheus_ic_closed_trades;
ALTER TABLE IF EXISTS jubilee_ic_config RENAME TO prometheus_ic_config;
ALTER TABLE IF EXISTS jubilee_ic_equity_snapshots RENAME TO prometheus_ic_equity_snapshots;
ALTER TABLE IF EXISTS jubilee_ic_positions RENAME TO prometheus_ic_positions;
ALTER TABLE IF EXISTS jubilee_ic_signals RENAME TO prometheus_ic_signals;
ALTER TABLE IF EXISTS jubilee_live_model RENAME TO prometheus_live_model;
ALTER TABLE IF EXISTS jubilee_logs RENAME TO prometheus_logs;
ALTER TABLE IF EXISTS jubilee_models RENAME TO prometheus_models;
ALTER TABLE IF EXISTS jubilee_positions RENAME TO prometheus_positions;
ALTER TABLE IF EXISTS jubilee_predictions RENAME TO prometheus_predictions;
ALTER TABLE IF EXISTS jubilee_rate_analysis RENAME TO prometheus_rate_analysis;
ALTER TABLE IF EXISTS jubilee_roll_decisions RENAME TO prometheus_roll_decisions;
ALTER TABLE IF EXISTS jubilee_signals RENAME TO prometheus_signals;
ALTER TABLE IF EXISTS jubilee_training_history RENAME TO prometheus_training_history;

-- ---------------------------------------------------------------------------
-- 1h. ORACLE (reverse from PROPHET)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS prophet_bot_interactions RENAME TO oracle_bot_interactions;
ALTER TABLE IF EXISTS prophet_predictions RENAME TO oracle_predictions;
ALTER TABLE IF EXISTS prophet_strategy_accuracy RENAME TO oracle_strategy_accuracy;
ALTER TABLE IF EXISTS prophet_trained_models RENAME TO oracle_trained_models;
ALTER TABLE IF EXISTS prophet_training_outcomes RENAME TO oracle_training_outcomes;

-- ---------------------------------------------------------------------------
-- 1i. APOLLO (reverse from DISCERNMENT)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS discernment_live_quotes RENAME TO apollo_live_quotes;
ALTER TABLE IF EXISTS discernment_model_performance RENAME TO apollo_model_performance;
ALTER TABLE IF EXISTS discernment_outcomes RENAME TO apollo_outcomes;
ALTER TABLE IF EXISTS discernment_pin_risk_history RENAME TO apollo_pin_risk_history;
ALTER TABLE IF EXISTS discernment_predictions RENAME TO apollo_predictions;
ALTER TABLE IF EXISTS discernment_scans RENAME TO apollo_scans;

-- ---------------------------------------------------------------------------
-- 1j. ARGUS (reverse from WATCHTOWER)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS watchtower_accuracy RENAME TO argus_accuracy;
ALTER TABLE IF EXISTS watchtower_alerts RENAME TO argus_alerts;
ALTER TABLE IF EXISTS watchtower_commentary RENAME TO argus_commentary;
ALTER TABLE IF EXISTS watchtower_danger_zone_logs RENAME TO argus_danger_zone_logs;
ALTER TABLE IF EXISTS watchtower_gamma_flips RENAME TO argus_gamma_flips;
ALTER TABLE IF EXISTS watchtower_gamma_history RENAME TO argus_gamma_history;
ALTER TABLE IF EXISTS watchtower_order_flow_history RENAME TO argus_order_flow_history;
ALTER TABLE IF EXISTS watchtower_outcomes RENAME TO argus_outcomes;
ALTER TABLE IF EXISTS watchtower_pin_predictions RENAME TO argus_pin_predictions;
ALTER TABLE IF EXISTS watchtower_predictions RENAME TO argus_predictions;
ALTER TABLE IF EXISTS watchtower_snapshots RENAME TO argus_snapshots;
ALTER TABLE IF EXISTS watchtower_strikes RENAME TO argus_strikes;
ALTER TABLE IF EXISTS watchtower_trade_signals RENAME TO argus_trade_signals;

-- ---------------------------------------------------------------------------
-- 1k. KRONOS (reverse from CHRONICLES)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS chronicles_jobs RENAME TO kronos_jobs;

-- ---------------------------------------------------------------------------
-- 1l. HYPERION (reverse from GLORY)
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS glory_gamma_history RENAME TO hyperion_gamma_history;


-- =============================================================================
-- SECTION 2: CONFIG KEY ROLLBACK
-- =============================================================================

UPDATE autonomous_config SET key = 'ares_starting_capital'
WHERE key = 'fortress_starting_capital';

UPDATE autonomous_config SET key = 'athena_starting_capital'
WHERE key = 'solomon_starting_capital';

UPDATE autonomous_config SET key = 'titan_starting_capital'
WHERE key = 'samson_starting_capital';

UPDATE autonomous_config SET key = 'pegasus_starting_capital'
WHERE key = 'anchor_starting_capital';

UPDATE autonomous_config SET key = 'icarus_starting_capital'
WHERE key = 'gideon_starting_capital';

UPDATE autonomous_config SET key = 'heracles_starting_capital'
WHERE key = 'valor_starting_capital';

UPDATE autonomous_config SET key = 'ares_mode'
WHERE key = 'fortress_mode';

UPDATE autonomous_config SET key = 'ares_ticker'
WHERE key = 'fortress_ticker';


-- =============================================================================
-- SECTION 2B: ML_MODELS ROLLBACK
-- =============================================================================

UPDATE ml_models SET model_name = 'ares_ml'
WHERE model_name = 'fortress_ml';

UPDATE ml_models SET model_name = 'heracles_ml'
WHERE model_name = 'valor_ml';


-- =============================================================================
-- SECTION 3: BOT_NAME COLUMN VALUE ROLLBACK
-- =============================================================================
-- CRITICAL: ATHENA → SOLOMON (bot) must be reversed first,
-- then PROVERBS → SOLOMON (advisory).

-- ---------------------------------------------------------------------------
-- 3a. bot_decision_logs
-- ---------------------------------------------------------------------------

-- Reverse bot renames first (SOLOMON bot → ATHENA)
UPDATE bot_decision_logs SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

-- Then reverse advisory rename (PROVERBS → SOLOMON advisory)
UPDATE bot_decision_logs SET bot_name = 'SOLOMON'
WHERE bot_name = 'PROVERBS' AND bot_name IS NOT NULL;

-- All other bot renames
UPDATE bot_decision_logs SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PHOENIX'
WHERE bot_name = 'LAZARUS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ATLAS'
WHERE bot_name = 'CORNERSTONE' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'HERMES'
WHERE bot_name = 'SHEPHERD' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PROMETHEUS'
WHERE bot_name = 'JUBILEE' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ORACLE'
WHERE bot_name = 'PROPHET' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'SAGE'
WHERE bot_name = 'WISDOM' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ARGUS'
WHERE bot_name = 'WATCHTOWER' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ORION'
WHERE bot_name = 'STARS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'GEXIS'
WHERE bot_name = 'COUNSELOR' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'KRONOS'
WHERE bot_name = 'CHRONICLES' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'HYPERION'
WHERE bot_name = 'GLORY' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'APOLLO'
WHERE bot_name = 'DISCERNMENT' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'NEXUS'
WHERE bot_name = 'COVENANT' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3b. trading_decisions — strategy column
-- ---------------------------------------------------------------------------

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'FORTRESS', 'ARES')
WHERE strategy LIKE '%FORTRESS%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'SOLOMON', 'ATHENA')
WHERE strategy LIKE '%SOLOMON%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'SAMSON', 'TITAN')
WHERE strategy LIKE '%SAMSON%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ANCHOR', 'PEGASUS')
WHERE strategy LIKE '%ANCHOR%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'GIDEON', 'ICARUS')
WHERE strategy LIKE '%GIDEON%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'LAZARUS', 'PHOENIX')
WHERE strategy LIKE '%LAZARUS%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'VALOR', 'HERACLES')
WHERE strategy LIKE '%VALOR%' AND strategy IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3c. ml_decision_logs — action column
-- ---------------------------------------------------------------------------

UPDATE ml_decision_logs SET action = REPLACE(action, 'FORTRESS', 'ARES')
WHERE action LIKE '%FORTRESS%' AND action IS NOT NULL;

UPDATE ml_decision_logs SET action = REPLACE(action, 'SOLOMON', 'ATHENA')
WHERE action LIKE '%SOLOMON%' AND action IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3d. solomon_proposals (rolled back from proverbs_proposals)
-- ---------------------------------------------------------------------------

UPDATE solomon_proposals SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'PHOENIX'
WHERE bot_name = 'LAZARUS' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'ATLAS'
WHERE bot_name = 'CORNERSTONE' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'HERMES'
WHERE bot_name = 'SHEPHERD' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'PROMETHEUS'
WHERE bot_name = 'JUBILEE' AND bot_name IS NOT NULL;

UPDATE solomon_proposals SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3e. solomon_kill_switch
-- ---------------------------------------------------------------------------

UPDATE solomon_kill_switch SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'PHOENIX'
WHERE bot_name = 'LAZARUS' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'ATLAS'
WHERE bot_name = 'CORNERSTONE' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'HERMES'
WHERE bot_name = 'SHEPHERD' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'PROMETHEUS'
WHERE bot_name = 'JUBILEE' AND bot_name IS NOT NULL;

UPDATE solomon_kill_switch SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3f. solomon_versions
-- ---------------------------------------------------------------------------

UPDATE solomon_versions SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE solomon_versions SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE solomon_versions SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE solomon_versions SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE solomon_versions SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE solomon_versions SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3g. solomon_performance
-- ---------------------------------------------------------------------------

UPDATE solomon_performance SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE solomon_performance SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE solomon_performance SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE solomon_performance SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE solomon_performance SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE solomon_performance SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3h. solomon_validations
-- ---------------------------------------------------------------------------

UPDATE solomon_validations SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE solomon_validations SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE solomon_validations SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE solomon_validations SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE solomon_validations SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE solomon_validations SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3i. solomon_bot_configs
-- ---------------------------------------------------------------------------

UPDATE solomon_bot_configs SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

UPDATE solomon_bot_configs SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE solomon_bot_configs SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE solomon_bot_configs SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE solomon_bot_configs SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE solomon_bot_configs SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3j. solomon_strategy_analysis (if bot_name column exists)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'solomon_strategy_analysis' AND column_name = 'bot_name'
    ) THEN
        EXECUTE 'UPDATE solomon_strategy_analysis SET bot_name = ''ARES'' WHERE bot_name = ''FORTRESS''';
        EXECUTE 'UPDATE solomon_strategy_analysis SET bot_name = ''ATHENA'' WHERE bot_name = ''SOLOMON''';
        EXECUTE 'UPDATE solomon_strategy_analysis SET bot_name = ''TITAN'' WHERE bot_name = ''SAMSON''';
        EXECUTE 'UPDATE solomon_strategy_analysis SET bot_name = ''PEGASUS'' WHERE bot_name = ''ANCHOR''';
        EXECUTE 'UPDATE solomon_strategy_analysis SET bot_name = ''ICARUS'' WHERE bot_name = ''GIDEON''';
        EXECUTE 'UPDATE solomon_strategy_analysis SET bot_name = ''HERACLES'' WHERE bot_name = ''VALOR''';
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3k. solomon_audit_log (if bot_name column exists)
-- ---------------------------------------------------------------------------

DO $$ BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'solomon_audit_log' AND column_name = 'bot_name'
    ) THEN
        EXECUTE 'UPDATE solomon_audit_log SET bot_name = ''ARES'' WHERE bot_name = ''FORTRESS''';
        EXECUTE 'UPDATE solomon_audit_log SET bot_name = ''ATHENA'' WHERE bot_name = ''SOLOMON''';
        EXECUTE 'UPDATE solomon_audit_log SET bot_name = ''TITAN'' WHERE bot_name = ''SAMSON''';
        EXECUTE 'UPDATE solomon_audit_log SET bot_name = ''PEGASUS'' WHERE bot_name = ''ANCHOR''';
        EXECUTE 'UPDATE solomon_audit_log SET bot_name = ''ICARUS'' WHERE bot_name = ''GIDEON''';
        EXECUTE 'UPDATE solomon_audit_log SET bot_name = ''HERACLES'' WHERE bot_name = ''VALOR''';
    END IF;
END $$;


-- =============================================================================
-- SECTION 4: VERIFICATION
-- =============================================================================

DO $$
DECLARE
    old_tables TEXT;
BEGIN
    SELECT STRING_AGG(table_name, ', ')
    INTO old_tables
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE ANY(ARRAY[
        'ares_%', 'athena_%', 'titan_%', 'pegasus_%', 'icarus_%',
        'heracles_%', 'prometheus_%', 'oracle_%', 'apollo_%', 'argus_%',
        'kronos_%', 'hyperion_%', 'solomon_%'
    ]);

    IF old_tables IS NOT NULL THEN
        RAISE NOTICE 'ROLLBACK PASS: Old-name tables restored: %', old_tables;
    ELSE
        RAISE WARNING 'ROLLBACK ISSUE: No old-name tables found';
    END IF;
END $$;

COMMIT;
