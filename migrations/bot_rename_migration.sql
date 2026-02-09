-- =============================================================================
-- AlphaGEX Bot Rename Migration: Greek Mythology → Biblical Names
-- =============================================================================
--
-- This migration renames all database objects from Greek mythology names to
-- Biblical names as part of the platform-wide rebranding.
--
-- SCOPE:
--   Section 1: 40 table renames (10 bots + advisory tables)
--   Section 2: 6 config key updates in autonomous_config
--   Section 3: bot_name column value updates in 5 tables (20 name mappings)
--   Section 4: Verification queries
--
-- SAFETY:
--   - Wrapped in a single transaction (BEGIN/COMMIT)
--   - If ANY statement fails, the entire migration rolls back
--   - No data is deleted or dropped
--   - Uses IF EXISTS to handle tables that may not exist in all environments
--
-- ROLLBACK: See bot_rename_rollback.sql
--
-- Date: 2026-02-09
-- PR: #1488
-- =============================================================================

BEGIN;

-- =============================================================================
-- SECTION 1: TABLE RENAMES
-- =============================================================================
-- Rename all bot-prefixed tables from Greek to Biblical names.
-- Using ALTER TABLE ... RENAME TO which is transactional in PostgreSQL.
-- IF EXISTS prevents failure in environments where some tables don't exist.

-- ---------------------------------------------------------------------------
-- 1a. FORTRESS (formerly ARES) - Aggressive Iron Condor bot
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS ares_positions RENAME TO fortress_positions;
ALTER TABLE IF EXISTS ares_closed_trades RENAME TO fortress_closed_trades;
ALTER TABLE IF EXISTS ares_equity_snapshots RENAME TO fortress_equity_snapshots;
ALTER TABLE IF EXISTS ares_scan_activity RENAME TO fortress_scan_activity;
ALTER TABLE IF EXISTS ares_daily_performance RENAME TO fortress_daily_performance;
ALTER TABLE IF EXISTS ares_daily_reports RENAME TO fortress_daily_reports;
ALTER TABLE IF EXISTS ares_signals RENAME TO fortress_signals;
ALTER TABLE IF EXISTS ares_daily_perf RENAME TO fortress_daily_perf;
ALTER TABLE IF EXISTS ares_logs RENAME TO fortress_logs;

-- ---------------------------------------------------------------------------
-- 1b. SOLOMON (formerly ATHENA) - Directional Spreads bot
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS athena_positions RENAME TO solomon_positions;
ALTER TABLE IF EXISTS athena_closed_trades RENAME TO solomon_closed_trades;
ALTER TABLE IF EXISTS athena_equity_snapshots RENAME TO solomon_equity_snapshots;
ALTER TABLE IF EXISTS athena_scan_activity RENAME TO solomon_scan_activity;
ALTER TABLE IF EXISTS athena_signals RENAME TO solomon_signals;
ALTER TABLE IF EXISTS athena_daily_perf RENAME TO solomon_daily_perf;
ALTER TABLE IF EXISTS athena_logs RENAME TO solomon_logs;

-- ---------------------------------------------------------------------------
-- 1c. SAMSON (formerly TITAN) - Aggressive SPX Iron Condor bot
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS titan_positions RENAME TO samson_positions;
ALTER TABLE IF EXISTS titan_closed_trades RENAME TO samson_closed_trades;
ALTER TABLE IF EXISTS titan_equity_snapshots RENAME TO samson_equity_snapshots;
ALTER TABLE IF EXISTS titan_scan_activity RENAME TO samson_scan_activity;
ALTER TABLE IF EXISTS titan_signals RENAME TO samson_signals;
ALTER TABLE IF EXISTS titan_daily_perf RENAME TO samson_daily_perf;
ALTER TABLE IF EXISTS titan_logs RENAME TO samson_logs;

-- ---------------------------------------------------------------------------
-- 1d. ANCHOR (formerly PEGASUS) - SPX Weekly Iron Condor bot
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS pegasus_positions RENAME TO anchor_positions;
ALTER TABLE IF EXISTS pegasus_closed_trades RENAME TO anchor_closed_trades;
ALTER TABLE IF EXISTS pegasus_equity_snapshots RENAME TO anchor_equity_snapshots;
ALTER TABLE IF EXISTS pegasus_scan_activity RENAME TO anchor_scan_activity;
ALTER TABLE IF EXISTS pegasus_signals RENAME TO anchor_signals;
ALTER TABLE IF EXISTS pegasus_daily_perf RENAME TO anchor_daily_perf;
ALTER TABLE IF EXISTS pegasus_logs RENAME TO anchor_logs;

-- ---------------------------------------------------------------------------
-- 1e. GIDEON (formerly ICARUS) - Aggressive Directional bot
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS icarus_positions RENAME TO gideon_positions;
ALTER TABLE IF EXISTS icarus_closed_trades RENAME TO gideon_closed_trades;
ALTER TABLE IF EXISTS icarus_equity_snapshots RENAME TO gideon_equity_snapshots;
ALTER TABLE IF EXISTS icarus_scan_activity RENAME TO gideon_scan_activity;
ALTER TABLE IF EXISTS icarus_signals RENAME TO gideon_signals;
ALTER TABLE IF EXISTS icarus_daily_perf RENAME TO gideon_daily_perf;
ALTER TABLE IF EXISTS icarus_logs RENAME TO gideon_logs;

-- ---------------------------------------------------------------------------
-- 1f. VALOR (formerly HERACLES) - Options trading bot
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS heracles_positions RENAME TO valor_positions;
ALTER TABLE IF EXISTS heracles_closed_trades RENAME TO valor_closed_trades;
ALTER TABLE IF EXISTS heracles_equity_snapshots RENAME TO valor_equity_snapshots;
ALTER TABLE IF EXISTS heracles_scan_activity RENAME TO valor_scan_activity;
ALTER TABLE IF EXISTS heracles_signals RENAME TO valor_signals;
ALTER TABLE IF EXISTS heracles_config RENAME TO valor_config;
ALTER TABLE IF EXISTS heracles_logs RENAME TO valor_logs;
ALTER TABLE IF EXISTS heracles_daily_perf RENAME TO valor_daily_perf;
ALTER TABLE IF EXISTS heracles_win_tracker RENAME TO valor_win_tracker;
ALTER TABLE IF EXISTS heracles_paper_account RENAME TO valor_paper_account;

-- ---------------------------------------------------------------------------
-- 1g. JUBILEE (formerly PROMETHEUS) - Box Spread Synthetic Borrowing + IC
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS prometheus_positions RENAME TO jubilee_positions;
ALTER TABLE IF EXISTS prometheus_signals RENAME TO jubilee_signals;
ALTER TABLE IF EXISTS prometheus_config RENAME TO jubilee_config;
ALTER TABLE IF EXISTS prometheus_logs RENAME TO jubilee_logs;
ALTER TABLE IF EXISTS prometheus_equity_snapshots RENAME TO jubilee_equity_snapshots;
ALTER TABLE IF EXISTS prometheus_daily_briefings RENAME TO jubilee_daily_briefings;
ALTER TABLE IF EXISTS prometheus_capital_deployments RENAME TO jubilee_capital_deployments;
ALTER TABLE IF EXISTS prometheus_rate_analysis RENAME TO jubilee_rate_analysis;
ALTER TABLE IF EXISTS prometheus_roll_decisions RENAME TO jubilee_roll_decisions;
ALTER TABLE IF EXISTS prometheus_ic_positions RENAME TO jubilee_ic_positions;
ALTER TABLE IF EXISTS prometheus_ic_closed_trades RENAME TO jubilee_ic_closed_trades;
ALTER TABLE IF EXISTS prometheus_ic_signals RENAME TO jubilee_ic_signals;
ALTER TABLE IF EXISTS prometheus_ic_config RENAME TO jubilee_ic_config;
ALTER TABLE IF EXISTS prometheus_ic_equity_snapshots RENAME TO jubilee_ic_equity_snapshots;

-- ---------------------------------------------------------------------------
-- 1h. PROPHET (formerly ORACLE) - ML Advisory system
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS oracle_predictions RENAME TO prophet_predictions;
ALTER TABLE IF EXISTS oracle_training_outcomes RENAME TO prophet_training_outcomes;

-- ---------------------------------------------------------------------------
-- 1i. WATCHTOWER (formerly ARGUS) - Real-time Gamma Visualization
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS argus_predictions RENAME TO watchtower_predictions;
ALTER TABLE IF EXISTS argus_outcomes RENAME TO watchtower_outcomes;

-- ---------------------------------------------------------------------------
-- 1j. DISCERNMENT (formerly APOLLO) - ML Scanner
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS apollo_outcomes RENAME TO discernment_outcomes;
ALTER TABLE IF EXISTS apollo_scans RENAME TO discernment_scans;

-- ---------------------------------------------------------------------------
-- 1k. PROVERBS (formerly SOLOMON advisory) - Feedback Loop system
-- Note: The SOLOMON advisory was renamed to PROVERBS FIRST, before the
-- ATHENA bot was renamed to SOLOMON. These tables should already be named
-- proverbs_* if the code-level rename created them. This handles the case
-- where old solomon_* advisory tables still exist in the database.
-- ---------------------------------------------------------------------------
ALTER TABLE IF EXISTS solomon_proposals RENAME TO proverbs_proposals;
ALTER TABLE IF EXISTS solomon_kill_switch RENAME TO proverbs_kill_switch;
ALTER TABLE IF EXISTS solomon_versions RENAME TO proverbs_versions;
ALTER TABLE IF EXISTS solomon_performance RENAME TO proverbs_performance;
ALTER TABLE IF EXISTS solomon_health RENAME TO proverbs_health;
ALTER TABLE IF EXISTS solomon_validations RENAME TO proverbs_validations;

-- ---------------------------------------------------------------------------
-- Note: These bots do NOT have dedicated tables (confirmed):
--   LAZARUS (formerly PHOENIX) - Uses shared autonomous_* tables
--   CORNERSTONE (formerly ATLAS) - Uses shared wheel_* tables
--   SHEPHERD (formerly HERMES) - UI-only, no database tables
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 1l. Additional tables discovered in verification sweep (2026-02-09)
--     These tables were missed in the initial inventory because they don't
--     follow the standard bot_positions/bot_closed_trades pattern.
-- ---------------------------------------------------------------------------

-- WATCHTOWER (formerly ARGUS) - additional data tables
ALTER TABLE IF EXISTS argus_gamma_history RENAME TO watchtower_gamma_history;
ALTER TABLE IF EXISTS argus_pin_predictions RENAME TO watchtower_pin_predictions;
ALTER TABLE IF EXISTS argus_accuracy RENAME TO watchtower_accuracy;
ALTER TABLE IF EXISTS argus_order_flow_history RENAME TO watchtower_order_flow_history;
ALTER TABLE IF EXISTS argus_trade_signals RENAME TO watchtower_trade_signals;
ALTER TABLE IF EXISTS argus_strikes RENAME TO watchtower_strikes;
ALTER TABLE IF EXISTS argus_gamma_flips RENAME TO watchtower_gamma_flips;

-- CHRONICLES (formerly KRONOS) - background job tracking
ALTER TABLE IF EXISTS kronos_jobs RENAME TO chronicles_jobs;

-- PROPHET (formerly ORACLE) - additional ML tables
ALTER TABLE IF EXISTS oracle_bot_interactions RENAME TO prophet_bot_interactions;
ALTER TABLE IF EXISTS oracle_trained_models RENAME TO prophet_trained_models;

-- GLORY (formerly HYPERION) - weekly gamma history
ALTER TABLE IF EXISTS hyperion_gamma_history RENAME TO glory_gamma_history;


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


-- =============================================================================
-- SECTION 3: BOT_NAME COLUMN VALUE UPDATES
-- =============================================================================
-- Multiple tables store bot/advisor names as string values in a bot_name column.
-- Historical rows have old Greek names that need updating to Biblical names.
--
-- SOLOMON COLLISION NOTE:
-- The advisory system "SOLOMON" was renamed to "PROVERBS".
-- The bot "ATHENA" was then renamed to "SOLOMON".
-- In bot_decision_logs and trading_decisions, "ATHENA" entries → "SOLOMON" (the bot).
-- "SOLOMON" entries (if any exist) in these tables would refer to the OLD advisory
-- system and should become "PROVERBS". This is safe because:
--   1. The advisory system rarely logged to bot_decision_logs (it's not a trading bot)
--   2. We update SOLOMON→PROVERBS first, then ATHENA→SOLOMON, to preserve ordering
--
-- UPDATE order matters: SOLOMON→PROVERBS must happen BEFORE ATHENA→SOLOMON
-- to avoid accidentally converting old advisory SOLOMON entries to bot SOLOMON.

-- ---------------------------------------------------------------------------
-- 3a. bot_decision_logs - Master audit trail for all bot decisions
-- ---------------------------------------------------------------------------

-- Advisory rename first (SOLOMON advisory → PROVERBS)
UPDATE bot_decision_logs SET bot_name = 'PROVERBS'
WHERE bot_name = 'SOLOMON' AND bot_name IS NOT NULL;

-- Then bot renames (including ATHENA → SOLOMON)
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

-- Advisory system names
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
-- 3b. trading_decisions - Decision audit trail
--     Note: This table does NOT have an explicit bot_name column.
--     Bot name may be embedded in the full_decision JSONB column, but we
--     do not update JSONB fields in this migration to avoid data corruption.
--     The strategy column may contain bot references — update if present.
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
-- 3c. ml_decision_logs - ML decision audit trail
--     Note: This table does NOT have an explicit bot_name column.
--     The action/details columns may contain bot references.
--     Skipping JSONB (details) to avoid data corruption.
-- ---------------------------------------------------------------------------

UPDATE ml_decision_logs SET action = REPLACE(action, 'ARES', 'FORTRESS')
WHERE action LIKE '%ARES%' AND action IS NOT NULL;

UPDATE ml_decision_logs SET action = REPLACE(action, 'ATHENA', 'SOLOMON')
WHERE action LIKE '%ATHENA%' AND action IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3d. proverbs_proposals - Optimization proposals targeting specific bots
--     The bot_name column stores which TRADING BOT the proposal modifies.
--     Advisory SOLOMON never appeared as a target here (it analyzed bots,
--     it wasn't analyzed BY the feedback loop). Safe to rename directly.
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
-- 3e. proverbs_kill_switch - Emergency stop state per bot
--     Same logic as proverbs_proposals — stores trading bot names only.
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
-- 3f. proverbs_versions - Version history (stores bot_name for target bot)
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
-- 3g. proverbs_performance - Performance snapshots (stores bot_name)
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
-- 3h. proverbs_validations - Proposal validation tracking (stores bot_name)
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


-- =============================================================================
-- SECTION 4: VERIFICATION QUERIES
-- =============================================================================
-- These queries confirm the migration succeeded. Run inside the transaction
-- so we can abort if anything looks wrong.

-- 4a. Verify renamed tables exist (SELECT 1 confirms table is accessible)
DO $$
DECLARE
    tbl TEXT;
    missing_tables TEXT[] := '{}';
BEGIN
    -- Core bot tables that MUST exist after migration
    FOREACH tbl IN ARRAY ARRAY[
        'fortress_positions', 'solomon_positions', 'samson_positions',
        'anchor_positions', 'gideon_positions', 'valor_positions',
        'jubilee_positions',
        'fortress_equity_snapshots', 'solomon_equity_snapshots',
        'samson_equity_snapshots', 'anchor_equity_snapshots',
        'gideon_equity_snapshots', 'valor_equity_snapshots',
        'prophet_predictions',
        -- Additional tables from verification sweep
        'watchtower_gamma_history', 'watchtower_pin_predictions',
        'watchtower_accuracy', 'watchtower_trade_signals',
        'chronicles_jobs', 'prophet_bot_interactions',
        'prophet_trained_models', 'glory_gamma_history'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = tbl AND table_schema = 'public'
        ) THEN
            missing_tables := missing_tables || tbl;
        END IF;
    END LOOP;

    IF array_length(missing_tables, 1) > 0 THEN
        RAISE WARNING 'Missing tables after migration: %', missing_tables;
    ELSE
        RAISE NOTICE 'PASS: All core renamed tables exist';
    END IF;
END $$;

-- 4b. Verify no old bot names remain in bot_decision_logs
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
        RAISE WARNING 'FAIL: % rows with old names in bot_decision_logs: %', old_count, old_names;
    END IF;
END $$;

-- 4c. Show current distinct bot_name values (should only be new Biblical names)
DO $$
DECLARE
    names TEXT;
BEGIN
    SELECT STRING_AGG(DISTINCT bot_name, ', ' ORDER BY bot_name)
    INTO names
    FROM bot_decision_logs;

    RAISE NOTICE 'Current bot_decision_logs bot_name values: %', COALESCE(names, '(empty table)');
END $$;

-- 4d. Verify config keys updated
DO $$
DECLARE
    old_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO old_count
    FROM autonomous_config
    WHERE key IN (
        'ares_starting_capital', 'athena_starting_capital',
        'titan_starting_capital', 'pegasus_starting_capital',
        'icarus_starting_capital', 'heracles_starting_capital'
    );

    IF old_count = 0 THEN
        RAISE NOTICE 'PASS: All config keys renamed';
    ELSE
        RAISE WARNING 'FAIL: % old config keys remain', old_count;
    END IF;
END $$;

-- 4e. Verify no old table names exist
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
        'heracles_%', 'prometheus_%', 'oracle_%', 'argus_%', 'apollo_%',
        'solomon_%', 'kronos_%', 'hyperion_%'
    ]);

    IF old_tables IS NULL THEN
        RAISE NOTICE 'PASS: No old-name tables remain';
    ELSE
        RAISE WARNING 'Old tables still exist: %', old_tables;
    END IF;
END $$;

COMMIT;

-- =============================================================================
-- POST-MIGRATION NOTES:
-- =============================================================================
-- 1. Tables NOT renamed (by design):
--    - autonomous_open_positions (shared table, no bot prefix)
--    - autonomous_closed_trades (shared table, no bot prefix)
--    - autonomous_config (shared table, only key VALUES were updated)
--    - gex_history, gamma_history, regime_classifications (data tables)
--    - All proverbs_* tables (already have correct name from code rename)
--
-- 2. JSONB columns (full_decision, details, supporting_metrics, etc.) are
--    NOT updated. They may contain old bot name strings as embedded data.
--    This is acceptable as JSONB is used for historical context, not lookups.
--
-- 3. Indexes are automatically renamed with their parent tables in PostgreSQL.
--    Custom index names (e.g., idx_ares_*) will retain old prefixes. This is
--    cosmetic only and does not affect functionality. To rename indexes:
--    ALTER INDEX IF EXISTS idx_ares_positions_status RENAME TO idx_fortress_positions_status;
-- =============================================================================
