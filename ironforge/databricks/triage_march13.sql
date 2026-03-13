-- ============================================================
-- IRONFORGE TRIAGE QUERIES — March 13, 2026 (CORRECTED)
-- ============================================================
-- Schema: alpha_prime.ironforge
-- Tables are PER-BOT: flame_positions, spark_positions, inferno_positions
-- NOT shared: there is NO ironforge.positions table
--
-- Column names: position_id (not trade_id), open_time (not entry_time),
--   close_time (not exit_time), total_credit (not entry_price),
--   close_price (not exit_price), realized_pnl (not pnl)
--
-- Run in Databricks SQL Editor. Copy each result before moving to next.
-- ============================================================


-- ============================================================
-- QUERY 0: SCHEMA DISCOVERY — What tables exist?
-- Run this FIRST to verify table names
-- ============================================================
SHOW TABLES IN alpha_prime.ironforge;


-- ============================================================
-- QUERY 1: ALL positions from March 12-13 (all bots)
-- Ground truth — what does the DB say happened?
-- ============================================================
SELECT 'FLAME' AS bot, position_id, dte_mode, status, open_time, close_time,
       total_credit, close_price, realized_pnl, close_reason,
       collateral_required, underlying_at_entry, vix_at_entry,
       sandbox_order_id, sandbox_close_order_id
FROM alpha_prime.ironforge.flame_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-12'
UNION ALL
SELECT 'SPARK', position_id, dte_mode, status, open_time, close_time,
       total_credit, close_price, realized_pnl, close_reason,
       collateral_required, underlying_at_entry, vix_at_entry,
       sandbox_order_id, sandbox_close_order_id
FROM alpha_prime.ironforge.spark_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-12'
UNION ALL
SELECT 'INFERNO', position_id, dte_mode, status, open_time, close_time,
       total_credit, close_price, realized_pnl, close_reason,
       collateral_required, underlying_at_entry, vix_at_entry,
       sandbox_order_id, sandbox_close_order_id
FROM alpha_prime.ironforge.inferno_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-12'
ORDER BY bot, open_time DESC;


-- ============================================================
-- QUERY 2: Position summary last 7 days (catch orphans)
-- ============================================================
SELECT 'FLAME' AS bot, dte_mode, status,
       COUNT(*) AS position_count,
       COALESCE(SUM(collateral_required), 0) AS total_collateral_held,
       MIN(open_time) AS oldest_position,
       MAX(open_time) AS newest_position
FROM alpha_prime.ironforge.flame_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-06'
GROUP BY dte_mode, status
UNION ALL
SELECT 'SPARK', dte_mode, status,
       COUNT(*), COALESCE(SUM(collateral_required), 0),
       MIN(open_time), MAX(open_time)
FROM alpha_prime.ironforge.spark_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-06'
GROUP BY dte_mode, status
UNION ALL
SELECT 'INFERNO', dte_mode, status,
       COUNT(*), COALESCE(SUM(collateral_required), 0),
       MIN(open_time), MAX(open_time)
FROM alpha_prime.ironforge.inferno_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-06'
GROUP BY dte_mode, status
ORDER BY bot, status;


-- ============================================================
-- QUERY 3: Paper account balances + collateral drift check
-- If collateral_drift != 0, there's a leak
-- ============================================================
SELECT
  'FLAME' AS bot,
  pa.dte_mode,
  pa.starting_capital,
  pa.current_balance,
  pa.cumulative_pnl,
  pa.collateral_in_use AS stored_collateral,
  pa.buying_power,
  COALESCE(op.actual_collateral, 0) AS calculated_collateral,
  ROUND(pa.collateral_in_use - COALESCE(op.actual_collateral, 0), 2) AS collateral_drift,
  COALESCE(cl.actual_pnl, 0) AS pnl_from_positions,
  ROUND(pa.current_balance - (pa.starting_capital + COALESCE(cl.actual_pnl, 0)), 2) AS balance_drift
FROM alpha_prime.ironforge.flame_paper_account pa
LEFT JOIN (
    SELECT dte_mode, SUM(collateral_required) AS actual_collateral
    FROM alpha_prime.ironforge.flame_positions WHERE status = 'open' GROUP BY dte_mode
) op ON op.dte_mode = pa.dte_mode
LEFT JOIN (
    SELECT dte_mode, SUM(realized_pnl) AS actual_pnl
    FROM alpha_prime.ironforge.flame_positions
    WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL GROUP BY dte_mode
) cl ON cl.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE
UNION ALL
SELECT
  'SPARK', pa.dte_mode, pa.starting_capital, pa.current_balance, pa.cumulative_pnl,
  pa.collateral_in_use, pa.buying_power,
  COALESCE(op.actual_collateral, 0),
  ROUND(pa.collateral_in_use - COALESCE(op.actual_collateral, 0), 2),
  COALESCE(cl.actual_pnl, 0),
  ROUND(pa.current_balance - (pa.starting_capital + COALESCE(cl.actual_pnl, 0)), 2)
FROM alpha_prime.ironforge.spark_paper_account pa
LEFT JOIN (
    SELECT dte_mode, SUM(collateral_required) AS actual_collateral
    FROM alpha_prime.ironforge.spark_positions WHERE status = 'open' GROUP BY dte_mode
) op ON op.dte_mode = pa.dte_mode
LEFT JOIN (
    SELECT dte_mode, SUM(realized_pnl) AS actual_pnl
    FROM alpha_prime.ironforge.spark_positions
    WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL GROUP BY dte_mode
) cl ON cl.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE
UNION ALL
SELECT
  'INFERNO', pa.dte_mode, pa.starting_capital, pa.current_balance, pa.cumulative_pnl,
  pa.collateral_in_use, pa.buying_power,
  COALESCE(op.actual_collateral, 0),
  ROUND(pa.collateral_in_use - COALESCE(op.actual_collateral, 0), 2),
  COALESCE(cl.actual_pnl, 0),
  ROUND(pa.current_balance - (pa.starting_capital + COALESCE(cl.actual_pnl, 0)), 2)
FROM alpha_prime.ironforge.inferno_paper_account pa
LEFT JOIN (
    SELECT dte_mode, SUM(collateral_required) AS actual_collateral
    FROM alpha_prime.ironforge.inferno_positions WHERE status = 'open' GROUP BY dte_mode
) op ON op.dte_mode = pa.dte_mode
LEFT JOIN (
    SELECT dte_mode, SUM(realized_pnl) AS actual_pnl
    FROM alpha_prime.ironforge.inferno_positions
    WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL GROUP BY dte_mode
) cl ON cl.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE
ORDER BY bot;


-- ============================================================
-- QUERY 4: SPARK March 13 position — the -$190 trade
-- Full details including strikes, sandbox info
-- ============================================================
SELECT *
FROM alpha_prime.ironforge.spark_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-12'
ORDER BY open_time DESC;


-- ============================================================
-- QUERY 5: FLAME — did it open ANY position March 12-13?
-- If empty, confirms sandbox_user_not_filled blocked everything
-- ============================================================
SELECT *
FROM alpha_prime.ironforge.flame_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-12'
ORDER BY open_time DESC;


-- ============================================================
-- QUERY 6: INFERNO positions — find stuck collateral
-- Flag suspicious states
-- ============================================================
SELECT
  position_id, dte_mode, status, open_time, close_time,
  total_credit, close_price, realized_pnl, close_reason,
  collateral_required,
  CASE
    WHEN status IN ('closed', 'expired') AND collateral_required > 0
      THEN 'INFO: closed positions always have collateral_required set (this is normal)'
    WHEN status = 'open' AND close_time IS NOT NULL
      THEN 'BUG: open but has close_time'
    WHEN status = 'open'
      AND CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) < '2026-03-13'
      THEN 'STALE: open position from prior day'
    WHEN dte_mode IS NULL
      THEN 'ORPHAN: no dte_mode'
    ELSE 'OK'
  END AS health_check
FROM alpha_prime.ironforge.inferno_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) >= '2026-03-06'
ORDER BY open_time DESC;


-- ============================================================
-- QUERY 7: FLAME full log March 13
-- THE KEY QUERY — shows whether sandbox orders were placed
-- or if they failed at the buying power pre-check
-- Look for: "BP insufficient", "IC OPEN submitted",
--           "NOT FILLED", "TRADE ABORTED"
-- ============================================================
SELECT log_time, level, message, details
FROM alpha_prime.ironforge.flame_logs
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) = '2026-03-13'
ORDER BY log_time;


-- ============================================================
-- QUERY 8: RECOVERY events — all bots, last 7 days
-- What drift was detected? How often?
-- ============================================================
SELECT 'FLAME' AS bot, log_time, message, details
FROM alpha_prime.ironforge.flame_logs
WHERE level = 'RECOVERY'
  AND log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
UNION ALL
SELECT 'SPARK', log_time, message, details
FROM alpha_prime.ironforge.spark_logs
WHERE level = 'RECOVERY'
  AND log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
UNION ALL
SELECT 'INFERNO', log_time, message, details
FROM alpha_prime.ironforge.inferno_logs
WHERE level = 'RECOVERY'
  AND log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
ORDER BY log_time DESC;


-- ============================================================
-- QUERY 9: FLAME sandbox failure pattern — last 14 days
-- How many days has this been happening?
-- bp_insufficient = failed BEFORE placing order
-- sandbox_blocked = failed AFTER placing order (fill timeout)
-- ============================================================
SELECT
  CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) AS trade_date,
  SUM(CASE WHEN level = 'SCAN' THEN 1 ELSE 0 END) AS total_scans,
  SUM(CASE WHEN message LIKE '%sandbox_user_not_filled%' THEN 1 ELSE 0 END) AS sandbox_not_filled,
  SUM(CASE WHEN message LIKE '%BP%insufficient%' THEN 1 ELSE 0 END) AS bp_insufficient,
  SUM(CASE WHEN message LIKE '%IC OPEN submitted%' THEN 1 ELSE 0 END) AS orders_submitted,
  SUM(CASE WHEN message LIKE '%NOT FILLED%' THEN 1 ELSE 0 END) AS fill_timeouts,
  SUM(CASE WHEN level = 'TRADE_OPEN' THEN 1 ELSE 0 END) AS trades_opened,
  SUM(CASE WHEN level = 'TRADE_CLOSE' THEN 1 ELSE 0 END) AS trades_closed
FROM alpha_prime.ironforge.flame_logs
WHERE log_time > DATEADD(DAY, -14, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;


-- ============================================================
-- QUERY 10: SPY price check — what did each bot see?
-- Heartbeat stores spot price in details JSON
-- ============================================================
SELECT
  bot_name,
  last_heartbeat,
  status,
  details,
  GET_JSON_OBJECT(details, '$.spot') AS spy_price,
  GET_JSON_OBJECT(details, '$.vix') AS vix,
  GET_JSON_OBJECT(details, '$.action') AS last_action,
  GET_JSON_OBJECT(details, '$.reason') AS last_reason
FROM alpha_prime.ironforge.bot_heartbeats
ORDER BY bot_name;


-- ============================================================
-- QUERY 11: Position status distribution
-- What states exist? Are there unexpected ones?
-- ============================================================
SELECT 'FLAME' AS bot, status, COUNT(*) AS cnt
FROM alpha_prime.ironforge.flame_positions GROUP BY status
UNION ALL
SELECT 'SPARK', status, COUNT(*) FROM alpha_prime.ironforge.spark_positions GROUP BY status
UNION ALL
SELECT 'INFERNO', status, COUNT(*) FROM alpha_prime.ironforge.inferno_positions GROUP BY status
ORDER BY bot, status;


-- ============================================================
-- QUERY 12: SPARK log March 13 — monitoring + close details
-- Need to see the full monitoring chain and close event
-- ============================================================
SELECT log_time, level, message, details
FROM alpha_prime.ironforge.spark_logs
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) = '2026-03-13'
  AND level IN ('TRADE_OPEN', 'TRADE_CLOSE', 'RECOVERY', 'ERROR')
ORDER BY log_time;
