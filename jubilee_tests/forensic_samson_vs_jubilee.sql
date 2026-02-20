-- ═══════════════════════════════════════════════════════════════════
-- FORENSIC: SAMSON vs JUBILEE DIVERGENCE — WHY $138K vs -$5,870?
-- Run via: render psql dpg-d4132pje5dus738rkoug-a < jubilee_tests/forensic_samson_vs_jubilee.sql
-- ALL READ-ONLY — no data modification
-- ═══════════════════════════════════════════════════════════════════

\echo ''
\echo '╔══════════════════════════════════════════════════════════════════╗'
\echo '║  FORENSIC: SAMSON vs JUBILEE — ROOT CAUSE INVESTIGATION         ║'
\echo '║  Date: 2026-02-20                                               ║'
\echo '╚══════════════════════════════════════════════════════════════════╝'
\echo ''

-- ──────────────────────────────────────────────────────────────────
-- PART 1: SAMSON — Today's 74 trades
-- ──────────────────────────────────────────────────────────────────
\echo '══════════════════════════════════════════════════════'
\echo 'PART 1A: SAMSON — All trades today (2/20)'
\echo '══════════════════════════════════════════════════════'

SELECT position_id,
       open_time AT TIME ZONE 'America/Chicago' AS open_ct,
       close_time AT TIME ZONE 'America/Chicago' AS close_ct,
       ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/60, 1) AS hold_min,
       total_credit, close_price,
       realized_pnl, contracts,
       close_reason, status,
       put_short_strike, put_long_strike,
       call_short_strike, call_long_strike,
       expiration
FROM samson_positions
WHERE open_time::date = '2026-02-20' OR close_time::date = '2026-02-20'
ORDER BY open_time;

\echo ''
\echo 'PART 1B: SAMSON — Today summary'
\echo '───────────────────────────────'

SELECT
    COUNT(*) AS total_trades,
    COUNT(CASE WHEN status = 'closed' THEN 1 END) AS closed,
    COUNT(CASE WHEN status = 'open' THEN 1 END) AS still_open,
    COUNT(CASE WHEN status = 'expired' THEN 1 END) AS expired,
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    ROUND(AVG(total_credit)::numeric, 4) AS avg_entry_credit,
    ROUND(AVG(close_price)::numeric, 4) AS avg_exit_price,
    ROUND(AVG(contracts)::numeric, 0) AS avg_contracts,
    ROUND(AVG(EXTRACT(EPOCH FROM (close_time - open_time))/60)::numeric, 1) AS avg_hold_min,
    MIN(open_time AT TIME ZONE 'America/Chicago')::time AS first_open,
    MAX(close_time AT TIME ZONE 'America/Chicago')::time AS last_close
FROM samson_positions
WHERE open_time::date = '2026-02-20' OR close_time::date = '2026-02-20';

\echo ''
\echo 'PART 1C: SAMSON — Exit reason breakdown today'
\echo '───────────────────────────────────────────────'

SELECT close_reason, COUNT(*) AS cnt,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
       ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl
FROM samson_positions
WHERE (open_time::date = '2026-02-20' OR close_time::date = '2026-02-20')
  AND status IN ('closed', 'expired')
GROUP BY close_reason
ORDER BY cnt DESC;

\echo ''
\echo 'PART 1D: SAMSON — Expiration dates of today trades'
\echo '──────────────────────────────────────────────────'

SELECT expiration, COUNT(*) AS cnt,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM samson_positions
WHERE open_time::date = '2026-02-20' OR close_time::date = '2026-02-20'
GROUP BY expiration
ORDER BY expiration;

-- ──────────────────────────────────────────────────────────────────
-- PART 2: JUBILEE IC — Current open positions + closed today
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 2A: JUBILEE — Open IC positions right now'
\echo '══════════════════════════════════════════════════════'

SELECT position_id,
       open_time AT TIME ZONE 'America/Chicago' AS open_ct,
       ROUND(EXTRACT(EPOCH FROM (NOW() - open_time))/3600, 1) AS age_hours,
       entry_credit, unrealized_pnl, contracts,
       put_short_strike, put_long_strike,
       call_short_strike, call_long_strike,
       expiration, dte_at_entry, current_dte, time_stop_dte,
       status
FROM jubilee_ic_positions
WHERE status IN ('OPEN', 'open')
ORDER BY open_time;

\echo ''
\echo 'PART 2B: JUBILEE — Any IC trades closed today (2/20)?'
\echo '─────────────────────────────────────────────────────'

SELECT position_id,
       open_time AT TIME ZONE 'America/Chicago' AS open_ct,
       close_time AT TIME ZONE 'America/Chicago' AS close_ct,
       ROUND(EXTRACT(EPOCH FROM (close_time - open_time))/3600, 1) AS hold_hours,
       entry_credit, exit_price, realized_pnl,
       contracts, close_reason
FROM jubilee_ic_closed_trades
WHERE close_time::date = '2026-02-20'
ORDER BY close_time;

\echo ''
\echo 'PART 2C: JUBILEE — Any IC trades opened today (2/20)?'
\echo '─────────────────────────────────────────────────────'

SELECT position_id, open_time AT TIME ZONE 'America/Chicago' AS open_ct,
       entry_credit, contracts, status,
       put_short_strike, call_short_strike, expiration, dte_at_entry
FROM jubilee_ic_positions
WHERE open_time::date = '2026-02-20'
ORDER BY open_time;

\echo ''
\echo 'PART 2D: JUBILEE — Any IC signals today (2/20)?'
\echo '───────────────────────────────────────────────'

SELECT signal_id, signal_time AT TIME ZONE 'America/Chicago' AS signal_ct,
       total_credit, contracts, oracle_approved, was_executed,
       execution_position_id, LEFT(skip_reason, 80) AS skip_reason
FROM jubilee_ic_signals
WHERE signal_time::date = '2026-02-20'
ORDER BY signal_time DESC
LIMIT 20;

-- ──────────────────────────────────────────────────────────────────
-- PART 3: THE $0.02 ENTRY CREDIT MYSTERY
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 3A: JUBILEE — Entry credit: positions vs closed_trades'
\echo 'If the SAME position_id shows $4.80 in positions and $0.02 in'
\echo 'closed_trades, the close process is corrupting the data.'
\echo '══════════════════════════════════════════════════════'

SELECT
    p.position_id,
    p.entry_credit AS positions_credit,
    c.entry_credit AS closed_credit,
    ROUND((p.entry_credit - c.entry_credit)::numeric, 4) AS credit_diff,
    CASE WHEN ABS(p.entry_credit - c.entry_credit) > 0.10
         THEN 'MISMATCH' ELSE 'MATCH' END AS verdict,
    c.exit_price AS closed_exit_price,
    c.realized_pnl,
    c.close_reason
FROM jubilee_ic_positions p
JOIN jubilee_ic_closed_trades c ON p.position_id = c.position_id
ORDER BY c.close_time DESC
LIMIT 20;

\echo ''
\echo 'PART 3B: JUBILEE — Entry credit distribution in closed_trades'
\echo '─────────────────────────────────────────────────────────────'

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
    ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
    MIN(close_time) AS earliest,
    MAX(close_time) AS latest
FROM jubilee_ic_closed_trades
GROUP BY bucket
ORDER BY MIN(entry_credit);

\echo ''
\echo 'PART 3C: JUBILEE — Entry credit distribution in positions table (open + closed)'
\echo '───────────────────────────────────────────────────────────────────────────────'

SELECT
    CASE
        WHEN entry_credit >= 0 AND entry_credit < 0.10 THEN 'BROKEN ($0.00-$0.09)'
        WHEN entry_credit >= 0.10 AND entry_credit < 0.50 THEN 'SUSPICIOUS ($0.10-$0.49)'
        WHEN entry_credit >= 0.50 AND entry_credit < 1.00 THEN 'LOW ($0.50-$0.99)'
        WHEN entry_credit >= 1.00 AND entry_credit < 10.00 THEN 'NORMAL ($1.00-$9.99)'
        WHEN entry_credit >= 10.00 THEN 'HIGH ($10.00+)'
        ELSE 'NULL/NEGATIVE'
    END AS bucket,
    status,
    COUNT(*) AS cnt
FROM jubilee_ic_positions
GROUP BY bucket, status
ORDER BY MIN(entry_credit), status;

-- ──────────────────────────────────────────────────────────────────
-- PART 4: WHY ARE POSITIONS OPEN FOR 7 DAYS?
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 4A: JUBILEE — Activity log today (was the bot running?)'
\echo '══════════════════════════════════════════════════════'

SELECT timestamp AT TIME ZONE 'America/Chicago' AS ts_ct,
       action, LEFT(message, 120) AS message, level
FROM jubilee_logs
WHERE timestamp::date = '2026-02-20'
ORDER BY timestamp DESC
LIMIT 30;

\echo ''
\echo 'PART 4B: JUBILEE — Activity log yesterday (2/19)'
\echo '────────────────────────────────────────────────'

SELECT timestamp AT TIME ZONE 'America/Chicago' AS ts_ct,
       action, LEFT(message, 120) AS message
FROM jubilee_logs
WHERE timestamp::date = '2026-02-19'
ORDER BY timestamp DESC
LIMIT 20;

\echo ''
\echo 'PART 4C: JUBILEE — Last 10 log entries (any date)'
\echo '────────────────────────────────────────────────'

SELECT timestamp AT TIME ZONE 'America/Chicago' AS ts_ct,
       action, LEFT(message, 120) AS message
FROM jubilee_logs
ORDER BY timestamp DESC
LIMIT 10;

\echo ''
\echo 'PART 4D: JUBILEE — Bot heartbeat (is scheduler running?)'
\echo '─────────────────────────────────────────────────────────'

SELECT *
FROM bot_heartbeats
WHERE LOWER(bot_name) LIKE '%jubilee%'
ORDER BY last_check DESC
LIMIT 5;

\echo ''
\echo 'PART 4E: SAMSON — Bot heartbeat for comparison'
\echo '──────────────────────────────────────────────'

SELECT *
FROM bot_heartbeats
WHERE LOWER(bot_name) LIKE '%samson%'
ORDER BY last_check DESC
LIMIT 5;

-- ──────────────────────────────────────────────────────────────────
-- PART 5: DTE COMPARISON — 0DTE vs 7DTE
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 5A: SAMSON — DTE at entry distribution'
\echo '══════════════════════════════════════════════════════'

SELECT expiration,
       (expiration - open_time::date) AS dte_at_open,
       COUNT(*) AS cnt,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM samson_positions
WHERE close_time IS NOT NULL
GROUP BY expiration, (expiration - open_time::date)
ORDER BY expiration DESC
LIMIT 20;

\echo ''
\echo 'PART 5B: JUBILEE — DTE at entry for all IC positions'
\echo '────────────────────────────────────────────────────'

SELECT position_id, expiration, dte_at_entry, current_dte,
       open_time::date AS open_date, status,
       entry_credit
FROM jubilee_ic_positions
ORDER BY open_time DESC
LIMIT 30;

\echo ''
\echo 'PART 5C: JUBILEE — DTE at entry for closed trades'
\echo '────────────────────────────────────────────────'

SELECT dte_at_entry, COUNT(*) AS cnt,
       ROUND(AVG(entry_credit)::numeric, 4) AS avg_credit,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM jubilee_ic_closed_trades
GROUP BY dte_at_entry
ORDER BY dte_at_entry;

-- ──────────────────────────────────────────────────────────────────
-- PART 6: EXIT REASON COMPARISON
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 6A: SAMSON — Exit reason distribution (all time)'
\echo '══════════════════════════════════════════════════════'

SELECT close_reason, COUNT(*) AS cnt,
       ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM samson_positions
WHERE status IN ('closed', 'expired')
GROUP BY close_reason
ORDER BY cnt DESC;

\echo ''
\echo 'PART 6B: JUBILEE IC — Exit reason distribution (all time)'
\echo '─────────────────────────────────────────────────────────'

SELECT close_reason, COUNT(*) AS cnt,
       ROUND(AVG(realized_pnl)::numeric, 2) AS avg_pnl,
       ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl,
       ROUND(AVG(entry_credit)::numeric, 4) AS avg_entry_credit
FROM jubilee_ic_closed_trades
GROUP BY close_reason
ORDER BY cnt DESC;

-- ──────────────────────────────────────────────────────────────────
-- PART 7: DAILY P&L COMPARISON (last 14 days)
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 7: SAMSON vs JUBILEE — Daily P&L (14 days)'
\echo '══════════════════════════════════════════════════════'

SELECT
    COALESCE(s.trade_date, j.trade_date) AS trade_date,
    COALESCE(s.samson_trades, 0) AS samson_trades,
    COALESCE(s.samson_pnl, 0) AS samson_pnl,
    COALESCE(j.jubilee_trades, 0) AS jubilee_trades,
    COALESCE(j.jubilee_pnl, 0) AS jubilee_pnl,
    COALESCE(s.samson_pnl, 0) - COALESCE(j.jubilee_pnl, 0) AS gap
FROM (
    SELECT close_time::date AS trade_date,
           COUNT(*) AS samson_trades,
           ROUND(SUM(realized_pnl)::numeric, 2) AS samson_pnl
    FROM samson_positions
    WHERE status IN ('closed', 'expired')
      AND close_time > CURRENT_DATE - INTERVAL '14 days'
    GROUP BY close_time::date
) s
FULL OUTER JOIN (
    SELECT close_time::date AS trade_date,
           COUNT(*) AS jubilee_trades,
           ROUND(SUM(realized_pnl)::numeric, 2) AS jubilee_pnl
    FROM jubilee_ic_closed_trades
    WHERE close_time > CURRENT_DATE - INTERVAL '14 days'
    GROUP BY close_time::date
) j ON s.trade_date = j.trade_date
ORDER BY trade_date DESC;

-- ──────────────────────────────────────────────────────────────────
-- PART 8: CONFIG COMPARISON
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 8A: SAMSON config'
\echo '══════════════════════════════════════════════════════'

SELECT key, LEFT(config_data::text, 300) AS config_preview
FROM autonomous_config
WHERE key LIKE 'samson%'
ORDER BY key;

\echo ''
\echo 'PART 8B: JUBILEE IC config'
\echo '──────────────────────────'

SELECT config_key, LEFT(config_data::text, 300) AS config_preview
FROM jubilee_ic_config
ORDER BY config_key;

-- ──────────────────────────────────────────────────────────────────
-- PART 9: ALL-TIME SUMMARY
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 9: SAMSON vs JUBILEE — All-time summary'
\echo '══════════════════════════════════════════════════════'

SELECT 'SAMSON' AS bot,
       COUNT(*) AS total_trades,
       COUNT(CASE WHEN status = 'closed' THEN 1 END) AS closed,
       COUNT(CASE WHEN status = 'open' THEN 1 END) AS open,
       COUNT(CASE WHEN status = 'expired' THEN 1 END) AS expired,
       ROUND(SUM(CASE WHEN status IN ('closed','expired') THEN realized_pnl ELSE 0 END)::numeric, 2) AS total_pnl,
       ROUND(AVG(CASE WHEN status IN ('closed','expired') THEN realized_pnl END)::numeric, 2) AS avg_pnl,
       COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) AS wins,
       ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(CASE WHEN status IN ('closed','expired') THEN 1 END),0) * 100, 1) AS win_rate,
       ROUND(AVG(total_credit)::numeric, 4) AS avg_entry_credit,
       MIN(open_time)::date AS first_trade,
       MAX(open_time)::date AS last_trade
FROM samson_positions

UNION ALL

SELECT 'JUBILEE_IC',
       (SELECT COUNT(*) FROM jubilee_ic_positions),
       (SELECT COUNT(*) FROM jubilee_ic_closed_trades),
       (SELECT COUNT(*) FROM jubilee_ic_positions WHERE status IN ('OPEN','open')),
       0,
       (SELECT ROUND(COALESCE(SUM(realized_pnl),0)::numeric, 2) FROM jubilee_ic_closed_trades),
       (SELECT ROUND(AVG(realized_pnl)::numeric, 2) FROM jubilee_ic_closed_trades),
       (SELECT COUNT(*) FROM jubilee_ic_closed_trades WHERE realized_pnl > 0),
       (SELECT ROUND(COUNT(CASE WHEN realized_pnl > 0 THEN 1 END)::numeric / NULLIF(COUNT(*),0) * 100, 1) FROM jubilee_ic_closed_trades),
       (SELECT ROUND(AVG(entry_credit)::numeric, 4) FROM jubilee_ic_closed_trades),
       (SELECT MIN(open_time)::date FROM jubilee_ic_positions),
       (SELECT MAX(open_time)::date FROM jubilee_ic_positions);

-- ──────────────────────────────────────────────────────────────────
-- PART 10: JUBILEE's last 20 closed trades (full detail)
-- ──────────────────────────────────────────────────────────────────
\echo ''
\echo '══════════════════════════════════════════════════════'
\echo 'PART 10: JUBILEE — Last 20 closed trades with full detail'
\echo '══════════════════════════════════════════════════════'

SELECT position_id,
       open_time AT TIME ZONE 'America/Chicago' AS open_ct,
       close_time AT TIME ZONE 'America/Chicago' AS close_ct,
       dte_at_entry,
       entry_credit, exit_price,
       ROUND(((entry_credit - exit_price) * contracts * 100)::numeric, 2) AS calc_pnl,
       realized_pnl AS stored_pnl,
       contracts, close_reason,
       put_short_strike, put_long_strike,
       call_short_strike, call_long_strike,
       expiration
FROM jubilee_ic_closed_trades
ORDER BY close_time DESC
LIMIT 20;

\echo ''
\echo '═══════════════════════════════════════════════════════════'
\echo 'FORENSIC INVESTIGATION COMPLETE'
\echo ''
\echo 'KEY THINGS TO CHECK IN OUTPUT:'
\echo '  1. Part 1D: Are SAMSON trades 0DTE (expiration = today)?'
\echo '  2. Part 2A: Are JUBILEE open positions 7DTE (exp = today)?'
\echo '  3. Part 3A: Does entry_credit MATCH between tables?'
\echo '  4. Part 4A: Did JUBILEE log ANY activity today?'
\echo '  5. Part 4D: Is JUBILEE heartbeat recent?'
\echo '  6. Part 5: DTE comparison confirms 0DTE vs 7DTE split'
\echo '  7. Part 7: When did JUBILEE last close a trade?'
\echo '═══════════════════════════════════════════════════════════'
