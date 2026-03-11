-- ============================================================
-- IronForge Live Smoke Test — Databricks SQL Edition
-- ============================================================
-- Run these queries in Databricks SQL Editor or a notebook.
-- Each query is a self-contained check. Look for PASS/FAIL.
--
-- The scanner reads PDT config from the SHARED table:
--   alpha_prime.ironforge.ironforge_pdt_config
-- NOT from per-bot tables (inferno_pdt_config, etc.)
-- ============================================================

-- ── 1. INFERNO PDT: Must be DISABLED (SHARED table) ────────
-- CRITICAL: This is the table the scanner ACTUALLY reads
SELECT
  bot_name,
  pdt_enabled,
  day_trade_count,
  max_day_trades,
  max_trades_per_day,
  CASE
    WHEN pdt_enabled = FALSE AND max_day_trades = 0 THEN 'PASS - PDT disabled for INFERNO'
    WHEN pdt_enabled = FALSE AND max_day_trades > 0 THEN 'WARN - pdt_enabled=false but max_day_trades should be 0'
    ELSE 'FAIL - PDT should be disabled for INFERNO!'
  END AS check_result
FROM alpha_prime.ironforge.ironforge_pdt_config
WHERE bot_name = 'INFERNO';


-- ── 2. FLAME PDT: Can it trade? ─────────────────────────────
SELECT
  bot_name,
  pdt_enabled,
  day_trade_count,
  max_day_trades,
  CASE
    WHEN day_trade_count < max_day_trades THEN 'PASS - FLAME can trade (' || day_trade_count || '/' || max_day_trades || ')'
    ELSE 'BLOCKED - FLAME at PDT limit (' || day_trade_count || '/' || max_day_trades || ')'
  END AS check_result
FROM alpha_prime.ironforge.ironforge_pdt_config
WHERE bot_name = 'FLAME';


-- ── 3. SPARK PDT: Can it trade? ─────────────────────────────
SELECT
  bot_name,
  pdt_enabled,
  day_trade_count,
  max_day_trades,
  CASE
    WHEN day_trade_count < max_day_trades THEN 'PASS - SPARK can trade (' || day_trade_count || '/' || max_day_trades || ')'
    ELSE 'BLOCKED - SPARK at PDT limit (' || day_trade_count || '/' || max_day_trades || ')'
  END AS check_result
FROM alpha_prime.ironforge.ironforge_pdt_config
WHERE bot_name = 'SPARK';


-- ── 4. Scanner heartbeats (is it alive?) ─────────────────────
SELECT
  bot_name,
  scan_count,
  last_heartbeat,
  TIMESTAMPDIFF(MINUTE, last_heartbeat, CURRENT_TIMESTAMP()) AS mins_ago,
  CASE
    WHEN TIMESTAMPDIFF(MINUTE, last_heartbeat, CURRENT_TIMESTAMP()) <= 10 THEN 'PASS - Scanner alive'
    WHEN TIMESTAMPDIFF(MINUTE, last_heartbeat, CURRENT_TIMESTAMP()) <= 60 THEN 'WARN - Stale (market may be closed)'
    ELSE 'INFO - Last heartbeat ' || CAST(TIMESTAMPDIFF(HOUR, last_heartbeat, CURRENT_TIMESTAMP()) AS STRING) || 'h ago'
  END AS check_result
FROM alpha_prime.ironforge.bot_heartbeats
ORDER BY bot_name;


-- ── 5. Paper account balances ────────────────────────────────
SELECT
  'FLAME' AS bot,
  current_balance,
  buying_power,
  collateral_in_use,
  cumulative_pnl,
  is_active,
  CASE WHEN buying_power > 200 THEN 'PASS' ELSE 'FAIL - Low buying power' END AS check_result
FROM alpha_prime.ironforge.flame_paper_account
WHERE is_active = TRUE
UNION ALL
SELECT
  'SPARK',
  current_balance,
  buying_power,
  collateral_in_use,
  cumulative_pnl,
  is_active,
  CASE WHEN buying_power > 200 THEN 'PASS' ELSE 'FAIL - Low buying power' END
FROM alpha_prime.ironforge.spark_paper_account
WHERE is_active = TRUE
UNION ALL
SELECT
  'INFERNO',
  current_balance,
  buying_power,
  collateral_in_use,
  cumulative_pnl,
  is_active,
  CASE WHEN buying_power > 200 THEN 'PASS' ELSE 'FAIL - Low buying power' END
FROM alpha_prime.ironforge.inferno_paper_account
WHERE is_active = TRUE;


-- ── 6. INFERNO PDT blocks: historical vs post-fix ───────────
-- All blocks should be BEFORE the fix. Zero blocks after fix = PASS.
SELECT
  COUNT(*) AS total_pdt_blocks,
  SUM(CASE WHEN log_time > '2026-03-11T00:00:00Z' THEN 1 ELSE 0 END) AS blocks_after_fix,
  CASE
    WHEN SUM(CASE WHEN log_time > '2026-03-11T00:00:00Z' THEN 1 ELSE 0 END) = 0
      THEN 'PASS - No PDT blocks after fix'
    ELSE 'FAIL - Still blocking after fix!'
  END AS check_result
FROM alpha_prime.ironforge.inferno_logs
WHERE message LIKE '%pdt_blocked%';


-- ── 7. Recent scan activity (last 20 per bot) ───────────────
-- FLAME
SELECT 'FLAME' AS bot, log_time, level, message
FROM alpha_prime.ironforge.flame_logs
WHERE level = 'SCAN'
ORDER BY log_time DESC
LIMIT 20;

-- SPARK
SELECT 'SPARK' AS bot, log_time, level, message
FROM alpha_prime.ironforge.spark_logs
WHERE level = 'SCAN'
ORDER BY log_time DESC
LIMIT 20;

-- INFERNO
SELECT 'INFERNO' AS bot, log_time, level, message
FROM alpha_prime.ironforge.inferno_logs
WHERE level = 'SCAN'
ORDER BY log_time DESC
LIMIT 20;


-- ── 8. Open positions (should be empty outside market hours) ─
SELECT 'FLAME' AS bot, position_id, status, open_time, entry_credit, expiration
FROM alpha_prime.ironforge.flame_positions
WHERE status = 'OPEN'
UNION ALL
SELECT 'SPARK', position_id, status, open_time, entry_credit, expiration
FROM alpha_prime.ironforge.spark_positions
WHERE status = 'OPEN'
UNION ALL
SELECT 'INFERNO', position_id, status, open_time, entry_credit, expiration
FROM alpha_prime.ironforge.inferno_positions
WHERE status = 'OPEN';


-- ── 9. Recent closed trades (last 10 per bot) ───────────────
SELECT 'FLAME' AS bot, position_id, close_reason, realized_pnl, open_time, close_time
FROM alpha_prime.ironforge.flame_positions
WHERE status IN ('CLOSED', 'EXPIRED') AND close_time IS NOT NULL
ORDER BY close_time DESC LIMIT 10;

SELECT 'SPARK' AS bot, position_id, close_reason, realized_pnl, open_time, close_time
FROM alpha_prime.ironforge.spark_positions
WHERE status IN ('CLOSED', 'EXPIRED') AND close_time IS NOT NULL
ORDER BY close_time DESC LIMIT 10;

SELECT 'INFERNO' AS bot, position_id, close_reason, realized_pnl, open_time, close_time
FROM alpha_prime.ironforge.inferno_positions
WHERE status IN ('CLOSED', 'EXPIRED') AND close_time IS NOT NULL
ORDER BY close_time DESC LIMIT 10;


-- ── 10. PDT audit trail (look for accidental re-enables) ────
SELECT *
FROM alpha_prime.ironforge.inferno_pdt_audit_log
ORDER BY audit_time DESC
LIMIT 20;


-- ── 11. PDT rolling window detail (FLAME) ───────────────────
SELECT
  trade_date,
  dte_mode,
  is_day_trade,
  opened_at,
  closed_at
FROM alpha_prime.ironforge.flame_pdt_log
WHERE trade_date >= DATE_ADD(CURRENT_DATE(), -6)
ORDER BY opened_at DESC;


-- ── 12. PDT rolling window detail (SPARK) ───────────────────
SELECT
  trade_date,
  dte_mode,
  is_day_trade,
  opened_at,
  closed_at
FROM alpha_prime.ironforge.spark_pdt_log
WHERE trade_date >= DATE_ADD(CURRENT_DATE(), -6)
ORDER BY opened_at DESC;


-- ── 13. Equity snapshots today (intraday chart data) ─────────
SELECT 'FLAME' AS bot, COUNT(*) AS snapshots_today
FROM alpha_prime.ironforge.flame_equity_snapshots
WHERE snapshot_time >= CURRENT_DATE()
UNION ALL
SELECT 'SPARK', COUNT(*)
FROM alpha_prime.ironforge.spark_equity_snapshots
WHERE snapshot_time >= CURRENT_DATE()
UNION ALL
SELECT 'INFERNO', COUNT(*)
FROM alpha_prime.ironforge.inferno_equity_snapshots
WHERE snapshot_time >= CURRENT_DATE();


-- ── 14. Config overrides (any DB-level config changes?) ──────
SELECT 'FLAME' AS bot, * FROM alpha_prime.ironforge.flame_config;
SELECT 'SPARK' AS bot, * FROM alpha_prime.ironforge.spark_config;
SELECT 'INFERNO' AS bot, * FROM alpha_prime.ironforge.inferno_config;


-- ── QUICK FIX: If INFERNO PDT is wrong, run this ────────────
-- UPDATE alpha_prime.ironforge.ironforge_pdt_config
-- SET pdt_enabled = FALSE, max_day_trades = 0, day_trade_count = 0
-- WHERE bot_name = 'INFERNO';

-- ── QUICK FIX: If FLAME/SPARK max_day_trades is 3 (should be 4) ─
-- UPDATE alpha_prime.ironforge.ironforge_pdt_config
-- SET max_day_trades = 4
-- WHERE bot_name IN ('FLAME', 'SPARK');


-- ── SUMMARY ──────────────────────────────────────────────────
-- Run queries 1-6 first. If all show PASS, the system is healthy.
-- Queries 7-14 are for deeper investigation if something looks off.
--
-- Key things to watch:
--   Query 1: INFERNO PDT MUST be disabled in ironforge_pdt_config
--   Query 4: Scanner heartbeats < 10 min old during market hours
--   Query 6: Zero pdt_blocked entries AFTER the fix date
--   Query 8: No stale open positions outside market hours
--
-- IMPORTANT: The scanner reads from ironforge_pdt_config (shared table),
-- NOT from inferno_pdt_config / flame_pdt_config / spark_pdt_config.
-- Always check/fix the shared table!
