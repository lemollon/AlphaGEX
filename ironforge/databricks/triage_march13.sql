-- ============================================================
-- IronForge Deep Triage — March 13, 2026
-- ============================================================
-- Run ALL queries in Databricks SQL Editor.
-- Each query is self-contained. Run in order.
-- Save results for analysis.
-- ============================================================

-- ── Q1: CURRENT STATE — Paper account balances + drift check ──
-- Shows stored balance vs expected balance (starting_capital + sum of realized PnL)
-- If drift != 0, the paper_account is out of sync
SELECT
  'FLAME' AS bot,
  pa.dte_mode,
  pa.starting_capital,
  pa.current_balance AS stored_balance,
  pa.cumulative_pnl AS stored_pnl,
  pa.collateral_in_use AS stored_collateral,
  pa.buying_power AS stored_bp,
  COALESCE(p.total_pnl, 0) AS actual_pnl_from_positions,
  COALESCE(c.actual_collateral, 0) AS actual_collateral_from_positions,
  pa.starting_capital + COALESCE(p.total_pnl, 0) AS expected_balance,
  ROUND(pa.current_balance - (pa.starting_capital + COALESCE(p.total_pnl, 0)), 2) AS balance_drift,
  ROUND(pa.collateral_in_use - COALESCE(c.actual_collateral, 0), 2) AS collateral_drift
FROM alpha_prime.ironforge.flame_paper_account pa
LEFT JOIN (
    SELECT dte_mode, SUM(realized_pnl) AS total_pnl
    FROM alpha_prime.ironforge.flame_positions
    WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
    GROUP BY dte_mode
) p ON p.dte_mode = pa.dte_mode
LEFT JOIN (
    SELECT dte_mode, SUM(collateral_required) AS actual_collateral
    FROM alpha_prime.ironforge.flame_positions
    WHERE status = 'open'
    GROUP BY dte_mode
) c ON c.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE
UNION ALL
SELECT
  'SPARK', pa.dte_mode, pa.starting_capital, pa.current_balance, pa.cumulative_pnl,
  pa.collateral_in_use, pa.buying_power,
  COALESCE(p.total_pnl, 0), COALESCE(c.actual_collateral, 0),
  pa.starting_capital + COALESCE(p.total_pnl, 0),
  ROUND(pa.current_balance - (pa.starting_capital + COALESCE(p.total_pnl, 0)), 2),
  ROUND(pa.collateral_in_use - COALESCE(c.actual_collateral, 0), 2)
FROM alpha_prime.ironforge.spark_paper_account pa
LEFT JOIN (
    SELECT dte_mode, SUM(realized_pnl) AS total_pnl
    FROM alpha_prime.ironforge.spark_positions
    WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
    GROUP BY dte_mode
) p ON p.dte_mode = pa.dte_mode
LEFT JOIN (
    SELECT dte_mode, SUM(collateral_required) AS actual_collateral
    FROM alpha_prime.ironforge.spark_positions
    WHERE status = 'open'
    GROUP BY dte_mode
) c ON c.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE
UNION ALL
SELECT
  'INFERNO', pa.dte_mode, pa.starting_capital, pa.current_balance, pa.cumulative_pnl,
  pa.collateral_in_use, pa.buying_power,
  COALESCE(p.total_pnl, 0), COALESCE(c.actual_collateral, 0),
  pa.starting_capital + COALESCE(p.total_pnl, 0),
  ROUND(pa.current_balance - (pa.starting_capital + COALESCE(p.total_pnl, 0)), 2),
  ROUND(pa.collateral_in_use - COALESCE(c.actual_collateral, 0), 2)
FROM alpha_prime.ironforge.inferno_paper_account pa
LEFT JOIN (
    SELECT dte_mode, SUM(realized_pnl) AS total_pnl
    FROM alpha_prime.ironforge.inferno_positions
    WHERE status IN ('closed', 'expired') AND realized_pnl IS NOT NULL
    GROUP BY dte_mode
) p ON p.dte_mode = pa.dte_mode
LEFT JOIN (
    SELECT dte_mode, SUM(collateral_required) AS actual_collateral
    FROM alpha_prime.ironforge.inferno_positions
    WHERE status = 'open'
    GROUP BY dte_mode
) c ON c.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE;


-- ── Q2: ORPHAN POSITIONS — Any positions still 'open'? ────────
-- These hold collateral and may be from prior days
SELECT 'FLAME' AS bot, position_id, dte_mode, status, open_time, expiration,
       collateral_required, total_credit, underlying_at_entry
FROM alpha_prime.ironforge.flame_positions WHERE status = 'open'
UNION ALL
SELECT 'SPARK', position_id, dte_mode, status, open_time, expiration,
       collateral_required, total_credit, underlying_at_entry
FROM alpha_prime.ironforge.spark_positions WHERE status = 'open'
UNION ALL
SELECT 'INFERNO', position_id, dte_mode, status, open_time, expiration,
       collateral_required, total_credit, underlying_at_entry
FROM alpha_prime.ironforge.inferno_positions WHERE status = 'open';


-- ── Q3: SPY PRICE CHECK — Heartbeat spot prices for all bots ──
-- Checks for the reported SPY price discrepancy between bots
SELECT
  bot_name,
  last_heartbeat,
  GET_JSON_OBJECT(details, '$.spot') AS spy_price,
  GET_JSON_OBJECT(details, '$.vix') AS vix,
  GET_JSON_OBJECT(details, '$.action') AS action,
  GET_JSON_OBJECT(details, '$.reason') AS reason
FROM alpha_prime.ironforge.bot_heartbeats
ORDER BY bot_name;


-- ── Q4: MARCH 13 COMPLETE LOG — FLAME (ALL entries, not truncated) ──
-- The screenshot only showed partial logs. Get everything.
SELECT log_time, level, message,
       GET_JSON_OBJECT(details, '$.action') AS action,
       GET_JSON_OBJECT(details, '$.spot') AS spy_price,
       GET_JSON_OBJECT(details, '$.vix') AS vix
FROM alpha_prime.ironforge.flame_logs
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) = '2026-03-13'
ORDER BY log_time;


-- ── Q5: MARCH 13 COMPLETE LOG — SPARK (ALL entries) ──────────
SELECT log_time, level, message,
       GET_JSON_OBJECT(details, '$.action') AS action,
       GET_JSON_OBJECT(details, '$.spot') AS spy_price,
       GET_JSON_OBJECT(details, '$.vix') AS vix
FROM alpha_prime.ironforge.spark_logs
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) = '2026-03-13'
ORDER BY log_time;


-- ── Q6: MARCH 13 COMPLETE LOG — INFERNO (ALL entries) ────────
SELECT log_time, level, message,
       GET_JSON_OBJECT(details, '$.action') AS action,
       GET_JSON_OBJECT(details, '$.spot') AS spy_price,
       GET_JSON_OBJECT(details, '$.vix') AS vix
FROM alpha_prime.ironforge.inferno_logs
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) = '2026-03-13'
ORDER BY log_time;


-- ── Q7: MARCH 13 POSITIONS — All positions opened/closed on March 13 ──
SELECT 'FLAME' AS bot, position_id, dte_mode, status, open_time, close_time,
       total_credit, close_price, realized_pnl, close_reason,
       underlying_at_entry, vix_at_entry, collateral_required,
       sandbox_order_id, sandbox_close_order_id
FROM alpha_prime.ironforge.flame_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) = '2026-03-13'
   OR CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', close_time) AS DATE) = '2026-03-13'
UNION ALL
SELECT 'SPARK', position_id, dte_mode, status, open_time, close_time,
       total_credit, close_price, realized_pnl, close_reason,
       underlying_at_entry, vix_at_entry, collateral_required,
       sandbox_order_id, sandbox_close_order_id
FROM alpha_prime.ironforge.spark_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) = '2026-03-13'
   OR CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', close_time) AS DATE) = '2026-03-13'
UNION ALL
SELECT 'INFERNO', position_id, dte_mode, status, open_time, close_time,
       total_credit, close_price, realized_pnl, close_reason,
       underlying_at_entry, vix_at_entry, collateral_required,
       sandbox_order_id, sandbox_close_order_id
FROM alpha_prime.ironforge.inferno_positions
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', open_time) AS DATE) = '2026-03-13'
   OR CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', close_time) AS DATE) = '2026-03-13'
ORDER BY bot, open_time;


-- ── Q8: SANDBOX FAILURE PATTERN — FLAME last 7 days ──────────
-- How many days has FLAME been blocked by sandbox_user_not_filled?
SELECT
  CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', log_time) AS DATE) AS trade_date,
  COUNT(*) AS total_scans,
  SUM(CASE WHEN message LIKE '%sandbox_user_not_filled%' THEN 1 ELSE 0 END) AS sandbox_blocked,
  SUM(CASE WHEN level = 'TRADE_OPEN' THEN 1 ELSE 0 END) AS trades_opened,
  SUM(CASE WHEN level = 'TRADE_CLOSE' THEN 1 ELSE 0 END) AS trades_closed,
  SUM(CASE WHEN level = 'RECOVERY' THEN 1 ELSE 0 END) AS recoveries
FROM alpha_prime.ironforge.flame_logs
WHERE log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;


-- ── Q9: RECOVERY EVENTS — All reconciliation events last 7 days ──
-- Shows when balance/collateral drift was detected and corrected
SELECT 'FLAME' AS bot, log_time, message, details
FROM alpha_prime.ironforge.flame_logs
WHERE level = 'RECOVERY' AND log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
UNION ALL
SELECT 'SPARK', log_time, message, details
FROM alpha_prime.ironforge.spark_logs
WHERE level = 'RECOVERY' AND log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
UNION ALL
SELECT 'INFERNO', log_time, message, details
FROM alpha_prime.ironforge.inferno_logs
WHERE level = 'RECOVERY' AND log_time > DATEADD(DAY, -7, CURRENT_TIMESTAMP())
ORDER BY log_time DESC;


-- ── Q10: TRADE HISTORY — Last 20 closed trades per bot ────────
-- Check for patterns: all eod_cutoff? Sandbox close results?
SELECT 'FLAME' AS bot, position_id, close_reason, realized_pnl,
       open_time, close_time, total_credit, close_price,
       underlying_at_entry
FROM alpha_prime.ironforge.flame_positions
WHERE status IN ('closed', 'expired') AND close_time IS NOT NULL
ORDER BY close_time DESC LIMIT 20;

SELECT 'SPARK' AS bot, position_id, close_reason, realized_pnl,
       open_time, close_time, total_credit, close_price,
       underlying_at_entry
FROM alpha_prime.ironforge.spark_positions
WHERE status IN ('closed', 'expired') AND close_time IS NOT NULL
ORDER BY close_time DESC LIMIT 20;

SELECT 'INFERNO' AS bot, position_id, close_reason, realized_pnl,
       open_time, close_time, total_credit, close_price,
       underlying_at_entry
FROM alpha_prime.ironforge.inferno_positions
WHERE status IN ('closed', 'expired') AND close_time IS NOT NULL
ORDER BY close_time DESC LIMIT 20;


-- ── Q11: EQUITY SNAPSHOTS — March 13 intraday data ────────────
-- Verify equity snapshots are being saved each cycle
SELECT 'FLAME' AS bot, snapshot_time, balance, realized_pnl, unrealized_pnl,
       open_positions, note
FROM alpha_prime.ironforge.flame_equity_snapshots
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', snapshot_time) AS DATE) = '2026-03-13'
ORDER BY snapshot_time
LIMIT 200;

SELECT 'SPARK' AS bot, snapshot_time, balance, realized_pnl, unrealized_pnl,
       open_positions, note
FROM alpha_prime.ironforge.spark_equity_snapshots
WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', snapshot_time) AS DATE) = '2026-03-13'
ORDER BY snapshot_time
LIMIT 200;


-- ── Q12: INFERNO STUCK COLLATERAL — Check current state ───────
-- The reported issue: INFERNO had stuck collateral
SELECT
  pa.dte_mode,
  pa.current_balance,
  pa.collateral_in_use AS stored_collateral,
  pa.buying_power,
  COALESCE(oc.actual_collateral, 0) AS actual_collateral,
  ROUND(pa.collateral_in_use - COALESCE(oc.actual_collateral, 0), 2) AS collateral_drift,
  COALESCE(oc.open_count, 0) AS open_position_count
FROM alpha_prime.ironforge.inferno_paper_account pa
LEFT JOIN (
    SELECT dte_mode,
           SUM(collateral_required) AS actual_collateral,
           COUNT(*) AS open_count
    FROM alpha_prime.ironforge.inferno_positions
    WHERE status = 'open'
    GROUP BY dte_mode
) oc ON oc.dte_mode = pa.dte_mode
WHERE pa.is_active = TRUE;
