-- ═══════════════════════════════════════════════════════════════════
-- JUBILEE IC POST-FIX VALIDATION — CONSOLIDATED SQL
-- Run via: render psql dpg-d4132pje5dus738rkoug-a < jubilee_tests/validate_all.sql
-- Or paste directly into: render psql dpg-d4132pje5dus738rkoug-a
-- ALL READ-ONLY — no data modification
-- ═══════════════════════════════════════════════════════════════════

\echo ''
\echo '╔══════════════════════════════════════════════════════════════╗'
\echo '║   JUBILEE IC POST-FIX VALIDATION — FULL SCORECARD           ║'
\echo '╚══════════════════════════════════════════════════════════════╝'
\echo ''

-- ──────────────────────────────────────────────────────────────────
-- TEST 1: DATABASE SCHEMA — Do all expected tables exist?
-- ──────────────────────────────────────────────────────────────────
\echo '══════════════════════════════════════'
\echo 'TEST 1: Database Schema'
\echo '══════════════════════════════════════'

\echo '--- 1A: All jubilee tables ---'
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE 'jubilee%'
ORDER BY table_name;

\echo '--- 1B: IC Positions columns ---'
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'jubilee_ic_positions'
ORDER BY ordinal_position;

\echo '--- 1C: IC Closed Trades columns ---'
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'jubilee_ic_closed_trades'
ORDER BY ordinal_position;

\echo '--- 1D: IC Signals columns ---'
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'jubilee_ic_signals'
ORDER BY ordinal_position;

\echo '--- 1E: IC Config ---'
SELECT config_key, LEFT(config_data::text, 500) AS config_preview
FROM jubilee_ic_config
ORDER BY config_key
LIMIT 10;

-- ──────────────────────────────────────────────────────────────────
-- TEST 2: DATA STATE — Current positions, trades, distributions
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 2: Data State'
\echo '══════════════════════════════════════'

\echo '--- 2A: Open IC Positions ---'
SELECT position_id, ticker, status, entry_credit, contracts,
       open_time,
       put_short_strike, put_long_strike, call_short_strike, call_long_strike,
       ROUND(EXTRACT(EPOCH FROM (NOW() - open_time)) / 3600.0, 1) AS age_hours
FROM jubilee_ic_positions
WHERE status IN ('OPEN', 'open')
ORDER BY open_time DESC;

\echo '--- 2B: Closed Trades Summary (last 7 days) ---'
SELECT COUNT(*) AS trades_7d,
       ROUND(MIN(entry_credit)::numeric, 2) AS min_credit,
       ROUND(MAX(entry_credit)::numeric, 2) AS max_credit,
       ROUND(AVG(entry_credit)::numeric, 2) AS avg_credit,
       ROUND(MIN(EXTRACT(EPOCH FROM (close_time - open_time))/3600)::numeric, 1) AS min_hold_h,
       ROUND(MAX(EXTRACT(EPOCH FROM (close_time - open_time))/3600)::numeric, 1) AS max_hold_h,
       ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time))/3600)::numeric, 1) AS avg_hold_h,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM jubilee_ic_closed_trades
WHERE close_time > NOW() - INTERVAL '7 days';

\echo '--- 2C: Closed Trades Summary (all time) ---'
SELECT COUNT(*) AS total_trades,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
       ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl,
       COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS wins,
       COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) AS losses,
       ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)::numeric /
             NULLIF(COUNT(*), 0) * 100, 1) AS win_rate_pct
FROM jubilee_ic_closed_trades;

\echo '--- 2D: Exit Reason Distribution ---'
SELECT close_reason,
       COUNT(*) AS cnt,
       ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100, 1) AS pct
FROM jubilee_ic_closed_trades
GROUP BY close_reason
ORDER BY cnt DESC;

-- ──────────────────────────────────────────────────────────────────
-- TEST 3: SAFETY RAIL VALUES
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 3: Safety Rail Values'
\echo '══════════════════════════════════════'

\echo '--- 3A: Today daily IC P&L ---'
SELECT COALESCE(SUM(realized_pnl), 0) AS today_ic_pnl
FROM jubilee_ic_closed_trades
WHERE close_time::date = (NOW() AT TIME ZONE 'America/Chicago')::date;

\echo '--- 3B: Total IC P&L (all time, for drawdown calc) ---'
SELECT COALESCE(SUM(realized_pnl), 0) AS total_ic_pnl
FROM jubilee_ic_closed_trades;

\echo '--- 3C: Borrowed capital from open box positions ---'
SELECT COUNT(*) AS open_box_positions,
       COALESCE(SUM(total_cash_deployed), 0) AS total_borrowed
FROM jubilee_positions
WHERE status IN ('OPEN', 'open');

\echo '--- 3D: Safety rail decision (would new trade be allowed?) ---'
WITH safety AS (
    SELECT
        (SELECT COALESCE(SUM(realized_pnl), 0) FROM jubilee_ic_closed_trades
         WHERE close_time::date = (NOW() AT TIME ZONE 'America/Chicago')::date) AS daily_pnl,
        (SELECT COALESCE(SUM(realized_pnl), 0) FROM jubilee_ic_closed_trades) AS total_pnl,
        (SELECT COALESCE(SUM(total_cash_deployed), 0) FROM jubilee_positions
         WHERE status IN ('OPEN', 'open')) AS borrowed,
        25000.0 AS daily_limit,
        10.0 AS dd_limit_pct
)
SELECT
    daily_pnl,
    total_pnl,
    borrowed,
    daily_limit,
    dd_limit_pct,
    CASE WHEN daily_pnl < -daily_limit THEN 'BLOCKED' ELSE 'OK' END AS daily_check,
    CASE WHEN borrowed > 0 AND ABS(LEAST(total_pnl, 0)) / borrowed * 100 >= dd_limit_pct
         THEN 'BLOCKED' ELSE 'OK' END AS drawdown_check,
    CASE WHEN borrowed > 0
         THEN ROUND((ABS(LEAST(total_pnl::numeric, 0)) / borrowed * 100), 2)
         ELSE 0 END AS current_drawdown_pct
FROM safety;

-- ──────────────────────────────────────────────────────────────────
-- TEST 4: SAMSON vs JUBILEE COMPARISON
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 4: SAMSON vs JUBILEE Comparison'
\echo '══════════════════════════════════════'

\echo '--- JUBILEE IC stats ---'
SELECT 'JUBILEE' AS bot,
       COUNT(*) AS trades,
       ROUND(AVG(entry_credit)::numeric, 2) AS avg_credit,
       ROUND(AVG(contracts)::numeric, 1) AS avg_contracts,
       ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time))/3600)::numeric, 1) AS avg_hold_h,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
       COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS wins,
       ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 1) AS win_rate
FROM jubilee_ic_closed_trades;

\echo '--- SAMSON stats ---'
SELECT 'SAMSON' AS bot,
       COUNT(*) AS trades,
       ROUND(AVG(entry_credit)::numeric, 2) AS avg_credit,
       ROUND(AVG(contracts)::numeric, 1) AS avg_contracts,
       ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time))/3600)::numeric, 1) AS avg_hold_h,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
       COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS wins,
       ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 1) AS win_rate
FROM samson_positions
WHERE status = 'CLOSED';

-- ──────────────────────────────────────────────────────────────────
-- TEST 5: POSITION SIZING — Kelly trade count check
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 5: Kelly Trade Count'
\echo '══════════════════════════════════════'

\echo '--- 5A: Closed trades in last 90 days (Kelly needs 20+) ---'
SELECT COUNT(*) AS trades_90d,
       CASE WHEN COUNT(*) >= 20 THEN 'KELLY ACTIVE' ELSE 'KELLY INACTIVE (< 20 trades)' END AS kelly_status
FROM jubilee_ic_closed_trades
WHERE close_time > NOW() - INTERVAL '90 days';

\echo '--- 5B: Kelly inputs (if active) ---'
SELECT
    COUNT(*) AS sample_size,
    ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 1) AS win_rate_pct,
    ROUND(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END)::numeric, 2) AS avg_win,
    ROUND(AVG(CASE WHEN realized_pnl <= 0 THEN ABS(realized_pnl) END)::numeric, 2) AS avg_loss,
    ROUND(AVG(entry_credit)::numeric, 2) AS avg_entry_credit,
    ROUND(AVG(contracts)::numeric, 1) AS avg_contracts
FROM jubilee_ic_closed_trades
WHERE close_time > NOW() - INTERVAL '90 days';

-- ──────────────────────────────────────────────────────────────────
-- TEST 6: SIGNALS & EXECUTION LOGGING
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 6: Signals & Execution'
\echo '══════════════════════════════════════'

\echo '--- 6A: Total signals ---'
SELECT COUNT(*) AS total_signals,
       COUNT(CASE WHEN was_executed = TRUE THEN 1 END) AS executed,
       COUNT(CASE WHEN was_executed = FALSE OR was_executed IS NULL THEN 1 END) AS not_executed
FROM jubilee_ic_signals;

\echo '--- 6B: Recent 10 signals ---'
SELECT signal_id, signal_time, ticker,
       total_credit, contracts,
       oracle_approved, was_executed,
       execution_position_id,
       LEFT(skip_reason, 60) AS skip_reason
FROM jubilee_ic_signals
ORDER BY signal_time DESC
LIMIT 10;

\echo '--- 6C: Orphaned signals (executed but no position ref) ---'
SELECT COUNT(*) AS orphaned_signals
FROM jubilee_ic_signals
WHERE was_executed = TRUE
  AND (execution_position_id IS NULL OR execution_position_id = '');

\echo '--- 6D: Skip reason distribution ---'
SELECT skip_reason, COUNT(*) AS cnt
FROM jubilee_ic_signals
WHERE skip_reason IS NOT NULL AND skip_reason != ''
GROUP BY skip_reason
ORDER BY cnt DESC
LIMIT 15;

\echo '--- 6E: Todays signals ---'
SELECT COUNT(*) AS today_signals,
       MIN(signal_time) AS first_signal,
       MAX(signal_time) AS last_signal
FROM jubilee_ic_signals
WHERE signal_time::date = (NOW() AT TIME ZONE 'America/Chicago')::date;

-- ──────────────────────────────────────────────────────────────────
-- TEST 7: ACTIVITY LOG & EQUITY SNAPSHOTS
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 7: Activity Log & Equity'
\echo '══════════════════════════════════════'

\echo '--- 7A: Activity log (last 10 entries) ---'
SELECT log_id, timestamp, action, LEFT(message, 100) AS message, level
FROM jubilee_logs
ORDER BY timestamp DESC
LIMIT 10;

\echo '--- 7B: Activity log total count ---'
SELECT COUNT(*) AS total_log_entries FROM jubilee_logs;

\echo '--- 7C: IC equity snapshots per day (last 7 days) ---'
SELECT (snapshot_time AT TIME ZONE 'America/Chicago')::date AS day,
       COUNT(*) AS snapshots
FROM jubilee_ic_equity_snapshots
WHERE snapshot_time > NOW() - INTERVAL '7 days'
GROUP BY day
ORDER BY day DESC;

\echo '--- 7D: Latest IC equity snapshot ---'
SELECT snapshot_time, total_equity, total_capital, realized_pnl, unrealized_pnl
FROM jubilee_ic_equity_snapshots
ORDER BY snapshot_time DESC
LIMIT 1;

\echo '--- 7E: Box equity snapshots per day (last 7 days) ---'
SELECT (snapshot_time AT TIME ZONE 'America/Chicago')::date AS day,
       COUNT(*) AS snapshots
FROM jubilee_equity_snapshots
WHERE snapshot_time > NOW() - INTERVAL '7 days'
GROUP BY day
ORDER BY day DESC;

\echo '--- 7F: Latest box equity snapshot ---'
SELECT snapshot_time, total_equity, total_capital, realized_pnl, unrealized_pnl
FROM jubilee_equity_snapshots
ORDER BY snapshot_time DESC
LIMIT 1;

-- ──────────────────────────────────────────────────────────────────
-- TEST 8: ENTRY CREDIT AUDIT
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 8: Entry Credit Audit'
\echo '══════════════════════════════════════'

\echo '--- 8A: Entry credit distribution (closed trades) ---'
SELECT
    CASE
        WHEN entry_credit >= 0 AND entry_credit < 0.10 THEN 'BROKEN ($0.00-$0.09)'
        WHEN entry_credit >= 0.10 AND entry_credit < 0.50 THEN 'SUSPICIOUS ($0.10-$0.49)'
        WHEN entry_credit >= 0.50 AND entry_credit < 1.00 THEN 'LOW ($0.50-$0.99)'
        WHEN entry_credit >= 1.00 AND entry_credit < 10.00 THEN 'NORMAL ($1.00-$9.99)'
        WHEN entry_credit >= 10.00 THEN 'HIGH ($10.00+)'
        ELSE 'NULL/NEGATIVE'
    END AS bucket,
    COUNT(*) AS cnt,
    MIN(open_time) AS earliest,
    MAX(open_time) AS latest
FROM jubilee_ic_closed_trades
GROUP BY bucket
ORDER BY MIN(entry_credit);

\echo '--- 8B: Entry credit distribution (open positions) ---'
SELECT
    CASE
        WHEN entry_credit >= 0 AND entry_credit < 0.10 THEN 'BROKEN ($0.00-$0.09)'
        WHEN entry_credit >= 0.10 AND entry_credit < 0.50 THEN 'SUSPICIOUS ($0.10-$0.49)'
        WHEN entry_credit >= 0.50 AND entry_credit < 1.00 THEN 'LOW ($0.50-$0.99)'
        WHEN entry_credit >= 1.00 AND entry_credit < 10.00 THEN 'NORMAL ($1.00-$9.99)'
        WHEN entry_credit >= 10.00 THEN 'HIGH ($10.00+)'
        ELSE 'NULL/NEGATIVE'
    END AS bucket,
    COUNT(*) AS cnt
FROM jubilee_ic_positions
WHERE status IN ('OPEN', 'open')
GROUP BY bucket
ORDER BY MIN(entry_credit);

\echo '--- 8C: P&L math check (5 most recent closed trades) ---'
SELECT position_id,
       entry_credit,
       close_price,
       contracts,
       realized_pnl AS stored_pnl,
       ROUND(((entry_credit - close_price) * contracts * 100)::numeric, 2) AS calculated_pnl,
       ROUND(ABS(realized_pnl - (entry_credit - close_price) * contracts * 100)::numeric, 2) AS diff,
       CASE WHEN ABS(realized_pnl - (entry_credit - close_price) * contracts * 100) < 1.0
            THEN 'MATCH' ELSE 'MISMATCH' END AS verdict,
       close_reason
FROM jubilee_ic_closed_trades
ORDER BY close_time DESC
LIMIT 5;

\echo '--- 8D: Daily avg entry credit timeline (last 14 days) ---'
SELECT (open_time AT TIME ZONE 'America/Chicago')::date AS day,
       COUNT(*) AS trades,
       ROUND(AVG(entry_credit)::numeric, 2) AS avg_credit,
       ROUND(MIN(entry_credit)::numeric, 2) AS min_credit,
       ROUND(MAX(entry_credit)::numeric, 2) AS max_credit
FROM jubilee_ic_closed_trades
GROUP BY day
ORDER BY day DESC
LIMIT 14;

-- ──────────────────────────────────────────────────────────────────
-- TEST 9: E2E TRADE LIFECYCLE TRACE
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 9: E2E Trade Lifecycle'
\echo '══════════════════════════════════════'

\echo '--- 9A: Most recent closed position ---'
SELECT position_id, ticker, entry_credit, close_price, contracts,
       realized_pnl, close_reason, open_time, close_time,
       put_short_strike, put_long_strike, call_short_strike, call_long_strike
FROM jubilee_ic_closed_trades
ORDER BY close_time DESC
LIMIT 1;

\echo '--- 9B: Signal for most recent closed position ---'
SELECT s.*
FROM jubilee_ic_signals s
JOIN (SELECT position_id FROM jubilee_ic_closed_trades ORDER BY close_time DESC LIMIT 1) p
ON s.execution_position_id = p.position_id;

\echo '--- 9C: Activity log for most recent closed position ---'
SELECT log_id, timestamp, action, LEFT(message, 120) AS message
FROM jubilee_logs
WHERE message LIKE '%' || (SELECT position_id FROM jubilee_ic_closed_trades ORDER BY close_time DESC LIMIT 1) || '%'
   OR details::text LIKE '%' || (SELECT position_id FROM jubilee_ic_closed_trades ORDER BY close_time DESC LIMIT 1) || '%'
ORDER BY timestamp
LIMIT 20;

\echo '--- 9D: Equity snapshots during most recent trade ---'
SELECT snapshot_time, total_equity, realized_pnl, unrealized_pnl
FROM jubilee_ic_equity_snapshots
WHERE snapshot_time BETWEEN
    (SELECT open_time FROM jubilee_ic_closed_trades ORDER BY close_time DESC LIMIT 1)
    AND
    (SELECT close_time + INTERVAL '5 minutes' FROM jubilee_ic_closed_trades ORDER BY close_time DESC LIMIT 1)
ORDER BY snapshot_time;

-- ──────────────────────────────────────────────────────────────────
-- TEST 10: CRITICAL GAPS (13A-13H)
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'TEST 10: Critical Gap Checks'
\echo '══════════════════════════════════════'

\echo '--- 13A: Account equity source (box positions count + value) ---'
SELECT
    (SELECT COUNT(*) FROM jubilee_positions WHERE status IN ('OPEN', 'open')) AS open_box_count,
    (SELECT COALESCE(SUM(total_cash_deployed), 0) FROM jubilee_positions WHERE status IN ('OPEN', 'open')) AS box_capital,
    CASE WHEN (SELECT COUNT(*) FROM jubilee_positions WHERE status IN ('OPEN', 'open')) > 0
         THEN 'LIVE BOX DATA' ELSE 'FALLBACK TO CONFIG' END AS equity_source;

\echo '--- 13F: Signal → Position cross-check (last 5 executed signals) ---'
SELECT s.signal_id, s.signal_time, s.execution_position_id,
       CASE WHEN p.position_id IS NOT NULL THEN 'LINKED' ELSE 'ORPHAN' END AS link_status,
       p.entry_credit AS pos_credit, s.total_credit AS sig_credit
FROM jubilee_ic_signals s
LEFT JOIN jubilee_ic_closed_trades p ON s.execution_position_id = p.position_id
WHERE s.was_executed = TRUE
ORDER BY s.signal_time DESC
LIMIT 5;

\echo '--- 13G: Positions without signals (ghost positions) ---'
SELECT c.position_id, c.open_time, c.entry_credit, c.close_reason,
       CASE WHEN s.execution_position_id IS NOT NULL THEN 'HAS SIGNAL' ELSE 'NO SIGNAL' END AS signal_status
FROM jubilee_ic_closed_trades c
LEFT JOIN jubilee_ic_signals s ON s.execution_position_id = c.position_id
ORDER BY c.close_time DESC
LIMIT 10;

\echo '--- 13H: IC config vs defaults comparison ---'
SELECT config_key, config_data
FROM jubilee_ic_config
ORDER BY config_key;

-- ──────────────────────────────────────────────────────────────────
-- FINAL SUMMARY COUNTS
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════'
\echo 'FINAL SUMMARY'
\echo '══════════════════════════════════════'

SELECT
    (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'jubilee%') AS jubilee_tables,
    (SELECT COUNT(*) FROM jubilee_ic_positions WHERE status IN ('OPEN','open')) AS open_positions,
    (SELECT COUNT(*) FROM jubilee_ic_closed_trades) AS closed_trades,
    (SELECT ROUND(COALESCE(SUM(realized_pnl),0)::numeric, 2) FROM jubilee_ic_closed_trades) AS total_pnl,
    (SELECT COUNT(*) FROM jubilee_ic_signals) AS total_signals,
    (SELECT COUNT(*) FROM jubilee_ic_signals WHERE was_executed = TRUE) AS executed_signals,
    (SELECT COUNT(*) FROM jubilee_ic_signals WHERE was_executed = TRUE AND (execution_position_id IS NULL OR execution_position_id = '')) AS orphan_signals,
    (SELECT COUNT(*) FROM jubilee_logs) AS log_entries,
    (SELECT COUNT(*) FROM jubilee_ic_equity_snapshots WHERE snapshot_time > NOW() - INTERVAL '7 days') AS equity_snaps_7d,
    (SELECT COUNT(*) FROM jubilee_ic_closed_trades WHERE entry_credit > 0 AND entry_credit < 0.10) AS broken_credits;

\echo ''
\echo 'VALIDATION COMPLETE — Review output above for PASS/FAIL determination'
\echo 'Key things to check:'
\echo '  1. No BROKEN entry credits ($0.00-$0.09)'
\echo '  2. Exit reasons include PROFIT_TARGET + STOP_LOSS (not 100% TIME_STOP)'
\echo '  3. Safety rail daily_pnl and drawdown are within limits'
\echo '  4. Zero orphaned signals'
\echo '  5. Equity snapshots recording daily'
\echo '  6. E2E lifecycle chain: Signal -> Position -> Log -> Equity'
\echo ''
