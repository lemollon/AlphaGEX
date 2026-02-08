-- ============================================================
-- Migration 026: Rename ATHENA bot to SOLOMON
-- Date: 2026-02-08
--
-- Renames all ATHENA database objects and references to SOLOMON.
-- The ATHENA directional spreads bot is now called SOLOMON.
-- ============================================================

-- Rename tables
ALTER TABLE IF EXISTS solomon_positions RENAME TO solomon_positions;
ALTER TABLE IF EXISTS solomon_closed_trades RENAME TO solomon_closed_trades;
ALTER TABLE IF EXISTS solomon_equity_snapshots RENAME TO solomon_equity_snapshots;
ALTER TABLE IF EXISTS solomon_scan_activity RENAME TO solomon_scan_activity;
ALTER TABLE IF EXISTS solomon_signals RENAME TO solomon_signals;
ALTER TABLE IF EXISTS solomon_logs RENAME TO solomon_logs;
ALTER TABLE IF EXISTS solomon_daily_perf RENAME TO solomon_daily_perf;
ALTER TABLE IF EXISTS solomon_config RENAME TO solomon_config;
ALTER TABLE IF EXISTS solomon_open_positions RENAME TO solomon_open_positions;

-- Update bot_name references in autonomous_config
UPDATE autonomous_config SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';

-- Update bot_name references in unified_trades
UPDATE unified_trades SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';

-- Update bot_name references in trading_decisions
UPDATE trading_decisions SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';

-- Update bot_name references in prophet_predictions
UPDATE prophet_predictions SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';

-- Update bot_name references in ml_decision_logs
UPDATE ml_decision_logs SET bot_name = 'SOLOMON' WHERE bot_name = 'ATHENA';

-- Update any index names that reference athena
-- (PostgreSQL renames indexes automatically with ALTER TABLE RENAME, but explicit ones may remain)
DO $$
DECLARE
    idx RECORD;
BEGIN
    FOR idx IN
        SELECT indexname FROM pg_indexes
        WHERE indexname LIKE '%athena%'
    LOOP
        EXECUTE format('ALTER INDEX IF EXISTS %I RENAME TO %I',
            idx.indexname,
            replace(idx.indexname, 'athena', 'solomon'));
    END LOOP;
END $$;
