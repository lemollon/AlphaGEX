-- =============================================================================
-- AlphaGEX Bot Rename ROLLBACK: Biblical Names → Greek Mythology
-- =============================================================================
--
-- This script perfectly reverses every change made by bot_rename_migration.sql.
-- Operations are in REVERSE ORDER of the migration.
--
-- SAFETY:
--   - Wrapped in a single transaction (BEGIN/COMMIT)
--   - If ANY statement fails, the entire rollback aborts
--   - No data is deleted or dropped
--   - Uses IF EXISTS to handle partial migration states
--
-- Date: 2026-02-09
-- PR: #1488
-- =============================================================================

BEGIN;

-- =============================================================================
-- SECTION 3 ROLLBACK: RESTORE OLD BOT_NAME COLUMN VALUES (reverse order)
-- =============================================================================
-- SOLOMON COLLISION: Reverse ATHENA→SOLOMON first, then SOLOMON→PROVERBS
-- This is the opposite order of the forward migration.

-- ---------------------------------------------------------------------------
-- 3h rollback. proverbs_validations
-- ---------------------------------------------------------------------------

UPDATE proverbs_validations SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE proverbs_validations SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3g rollback. proverbs_performance
-- ---------------------------------------------------------------------------

UPDATE proverbs_performance SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE proverbs_performance SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3f rollback. proverbs_versions
-- ---------------------------------------------------------------------------

UPDATE proverbs_versions SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE proverbs_versions SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3e rollback. proverbs_kill_switch
-- ---------------------------------------------------------------------------

UPDATE proverbs_kill_switch SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'PROMETHEUS'
WHERE bot_name = 'JUBILEE' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'HERMES'
WHERE bot_name = 'SHEPHERD' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'ATLAS'
WHERE bot_name = 'CORNERSTONE' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'PHOENIX'
WHERE bot_name = 'LAZARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE proverbs_kill_switch SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3d rollback. proverbs_proposals
-- ---------------------------------------------------------------------------

UPDATE proverbs_proposals SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'PROMETHEUS'
WHERE bot_name = 'JUBILEE' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'HERMES'
WHERE bot_name = 'SHEPHERD' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'ATLAS'
WHERE bot_name = 'CORNERSTONE' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'PHOENIX'
WHERE bot_name = 'LAZARUS' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

UPDATE proverbs_proposals SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3c rollback. ml_decision_logs
-- ---------------------------------------------------------------------------

UPDATE ml_decision_logs SET action = REPLACE(action, 'SOLOMON', 'ATHENA')
WHERE action LIKE '%SOLOMON%' AND action IS NOT NULL;

UPDATE ml_decision_logs SET action = REPLACE(action, 'FORTRESS', 'ARES')
WHERE action LIKE '%FORTRESS%' AND action IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3b rollback. trading_decisions
-- ---------------------------------------------------------------------------

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'VALOR', 'HERACLES')
WHERE strategy LIKE '%VALOR%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'LAZARUS', 'PHOENIX')
WHERE strategy LIKE '%LAZARUS%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'GIDEON', 'ICARUS')
WHERE strategy LIKE '%GIDEON%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'ANCHOR', 'PEGASUS')
WHERE strategy LIKE '%ANCHOR%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'SAMSON', 'TITAN')
WHERE strategy LIKE '%SAMSON%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'SOLOMON', 'ATHENA')
WHERE strategy LIKE '%SOLOMON%' AND strategy IS NOT NULL;

UPDATE trading_decisions SET strategy = REPLACE(strategy, 'FORTRESS', 'ARES')
WHERE strategy LIKE '%FORTRESS%' AND strategy IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3a rollback. bot_decision_logs
-- Reverse order: ATHENA→SOLOMON must be undone BEFORE SOLOMON→PROVERBS
-- So: first revert bot SOLOMON→ATHENA, then revert PROVERBS→SOLOMON
-- ---------------------------------------------------------------------------

UPDATE bot_decision_logs SET bot_name = 'NEXUS'
WHERE bot_name = 'COVENANT' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'APOLLO'
WHERE bot_name = 'DISCERNMENT' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'HYPERION'
WHERE bot_name = 'GLORY' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'KRONOS'
WHERE bot_name = 'CHRONICLES' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'GEXIS'
WHERE bot_name = 'COUNSELOR' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ORION'
WHERE bot_name = 'STARS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ARGUS'
WHERE bot_name = 'WATCHTOWER' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'SAGE'
WHERE bot_name = 'WISDOM' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ORACLE'
WHERE bot_name = 'PROPHET' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'HERACLES'
WHERE bot_name = 'VALOR' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PROMETHEUS'
WHERE bot_name = 'JUBILEE' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'HERMES'
WHERE bot_name = 'SHEPHERD' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ATLAS'
WHERE bot_name = 'CORNERSTONE' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PHOENIX'
WHERE bot_name = 'LAZARUS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ICARUS'
WHERE bot_name = 'GIDEON' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'PEGASUS'
WHERE bot_name = 'ANCHOR' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'TITAN'
WHERE bot_name = 'SAMSON' AND bot_name IS NOT NULL;

-- Reverse ATHENA→SOLOMON BEFORE reversing SOLOMON→PROVERBS
UPDATE bot_decision_logs SET bot_name = 'ATHENA'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

-- Now restore advisory SOLOMON from PROVERBS
UPDATE bot_decision_logs SET bot_name = 'SOLOMON'
WHERE bot_name = 'PROVERBS' AND bot_name IS NOT NULL;

UPDATE bot_decision_logs SET bot_name = 'ARES'
WHERE bot_name = 'FORTRESS' AND bot_name IS NOT NULL;


-- =============================================================================
-- SECTION 2 ROLLBACK: RESTORE OLD CONFIG KEYS
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


-- =============================================================================
-- SECTION 1 ROLLBACK: RESTORE OLD TABLE NAMES (reverse order)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1k rollback. PROVERBS advisory tables → SOLOMON
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS proverbs_validations RENAME TO solomon_validations;
ALTER TABLE IF EXISTS proverbs_health RENAME TO solomon_health;
ALTER TABLE IF EXISTS proverbs_performance RENAME TO solomon_performance;
ALTER TABLE IF EXISTS proverbs_versions RENAME TO solomon_versions;
ALTER TABLE IF EXISTS proverbs_kill_switch RENAME TO solomon_kill_switch;
ALTER TABLE IF EXISTS proverbs_proposals RENAME TO solomon_proposals;

-- ---------------------------------------------------------------------------
-- 1j rollback. DISCERNMENT → APOLLO
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS discernment_scans RENAME TO apollo_scans;
ALTER TABLE IF EXISTS discernment_outcomes RENAME TO apollo_outcomes;

-- ---------------------------------------------------------------------------
-- 1i rollback. WATCHTOWER → ARGUS
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS watchtower_outcomes RENAME TO argus_outcomes;
ALTER TABLE IF EXISTS watchtower_predictions RENAME TO argus_predictions;

-- ---------------------------------------------------------------------------
-- 1h rollback. PROPHET → ORACLE
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS prophet_training_outcomes RENAME TO oracle_training_outcomes;
ALTER TABLE IF EXISTS prophet_predictions RENAME TO oracle_predictions;

-- ---------------------------------------------------------------------------
-- 1g rollback. JUBILEE → PROMETHEUS
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS jubilee_ic_equity_snapshots RENAME TO prometheus_ic_equity_snapshots;
ALTER TABLE IF EXISTS jubilee_ic_config RENAME TO prometheus_ic_config;
ALTER TABLE IF EXISTS jubilee_ic_signals RENAME TO prometheus_ic_signals;
ALTER TABLE IF EXISTS jubilee_ic_closed_trades RENAME TO prometheus_ic_closed_trades;
ALTER TABLE IF EXISTS jubilee_ic_positions RENAME TO prometheus_ic_positions;
ALTER TABLE IF EXISTS jubilee_roll_decisions RENAME TO prometheus_roll_decisions;
ALTER TABLE IF EXISTS jubilee_rate_analysis RENAME TO prometheus_rate_analysis;
ALTER TABLE IF EXISTS jubilee_capital_deployments RENAME TO prometheus_capital_deployments;
ALTER TABLE IF EXISTS jubilee_daily_briefings RENAME TO prometheus_daily_briefings;
ALTER TABLE IF EXISTS jubilee_equity_snapshots RENAME TO prometheus_equity_snapshots;
ALTER TABLE IF EXISTS jubilee_logs RENAME TO prometheus_logs;
ALTER TABLE IF EXISTS jubilee_config RENAME TO prometheus_config;
ALTER TABLE IF EXISTS jubilee_signals RENAME TO prometheus_signals;
ALTER TABLE IF EXISTS jubilee_positions RENAME TO prometheus_positions;

-- ---------------------------------------------------------------------------
-- 1f rollback. VALOR → HERACLES
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS valor_paper_account RENAME TO heracles_paper_account;
ALTER TABLE IF EXISTS valor_win_tracker RENAME TO heracles_win_tracker;
ALTER TABLE IF EXISTS valor_daily_perf RENAME TO heracles_daily_perf;
ALTER TABLE IF EXISTS valor_logs RENAME TO heracles_logs;
ALTER TABLE IF EXISTS valor_config RENAME TO heracles_config;
ALTER TABLE IF EXISTS valor_signals RENAME TO heracles_signals;
ALTER TABLE IF EXISTS valor_scan_activity RENAME TO heracles_scan_activity;
ALTER TABLE IF EXISTS valor_equity_snapshots RENAME TO heracles_equity_snapshots;
ALTER TABLE IF EXISTS valor_closed_trades RENAME TO heracles_closed_trades;
ALTER TABLE IF EXISTS valor_positions RENAME TO heracles_positions;

-- ---------------------------------------------------------------------------
-- 1e rollback. GIDEON → ICARUS
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS gideon_logs RENAME TO icarus_logs;
ALTER TABLE IF EXISTS gideon_daily_perf RENAME TO icarus_daily_perf;
ALTER TABLE IF EXISTS gideon_signals RENAME TO icarus_signals;
ALTER TABLE IF EXISTS gideon_scan_activity RENAME TO icarus_scan_activity;
ALTER TABLE IF EXISTS gideon_equity_snapshots RENAME TO icarus_equity_snapshots;
ALTER TABLE IF EXISTS gideon_closed_trades RENAME TO icarus_closed_trades;
ALTER TABLE IF EXISTS gideon_positions RENAME TO icarus_positions;

-- ---------------------------------------------------------------------------
-- 1d rollback. ANCHOR → PEGASUS
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS anchor_logs RENAME TO pegasus_logs;
ALTER TABLE IF EXISTS anchor_daily_perf RENAME TO pegasus_daily_perf;
ALTER TABLE IF EXISTS anchor_signals RENAME TO pegasus_signals;
ALTER TABLE IF EXISTS anchor_scan_activity RENAME TO pegasus_scan_activity;
ALTER TABLE IF EXISTS anchor_equity_snapshots RENAME TO pegasus_equity_snapshots;
ALTER TABLE IF EXISTS anchor_closed_trades RENAME TO pegasus_closed_trades;
ALTER TABLE IF EXISTS anchor_positions RENAME TO pegasus_positions;

-- ---------------------------------------------------------------------------
-- 1c rollback. SAMSON → TITAN
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS samson_logs RENAME TO titan_logs;
ALTER TABLE IF EXISTS samson_daily_perf RENAME TO titan_daily_perf;
ALTER TABLE IF EXISTS samson_signals RENAME TO titan_signals;
ALTER TABLE IF EXISTS samson_scan_activity RENAME TO titan_scan_activity;
ALTER TABLE IF EXISTS samson_equity_snapshots RENAME TO titan_equity_snapshots;
ALTER TABLE IF EXISTS samson_closed_trades RENAME TO titan_closed_trades;
ALTER TABLE IF EXISTS samson_positions RENAME TO titan_positions;

-- ---------------------------------------------------------------------------
-- 1b rollback. SOLOMON → ATHENA
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS solomon_logs RENAME TO athena_logs;
ALTER TABLE IF EXISTS solomon_daily_perf RENAME TO athena_daily_perf;
ALTER TABLE IF EXISTS solomon_signals RENAME TO athena_signals;
ALTER TABLE IF EXISTS solomon_scan_activity RENAME TO athena_scan_activity;
ALTER TABLE IF EXISTS solomon_equity_snapshots RENAME TO athena_equity_snapshots;
ALTER TABLE IF EXISTS solomon_closed_trades RENAME TO athena_closed_trades;
ALTER TABLE IF EXISTS solomon_positions RENAME TO athena_positions;

-- ---------------------------------------------------------------------------
-- 1a rollback. FORTRESS → ARES
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS fortress_logs RENAME TO ares_logs;
ALTER TABLE IF EXISTS fortress_daily_perf RENAME TO ares_daily_perf;
ALTER TABLE IF EXISTS fortress_signals RENAME TO ares_signals;
ALTER TABLE IF EXISTS fortress_daily_reports RENAME TO ares_daily_reports;
ALTER TABLE IF EXISTS fortress_daily_performance RENAME TO ares_daily_performance;
ALTER TABLE IF EXISTS fortress_scan_activity RENAME TO ares_scan_activity;
ALTER TABLE IF EXISTS fortress_equity_snapshots RENAME TO ares_equity_snapshots;
ALTER TABLE IF EXISTS fortress_closed_trades RENAME TO ares_closed_trades;
ALTER TABLE IF EXISTS fortress_positions RENAME TO ares_positions;

COMMIT;

-- =============================================================================
-- After rollback, deploy the old code version to match the old database schema.
-- =============================================================================
