#!/bin/bash
# Debug FLAME IC Return % — run in Render shell
# Paste entire script into Render shell

echo "=== FLAME CLOSED TRADES TODAY ==="
psql $DATABASE_URL -c "
SELECT position_id, close_reason, total_credit, close_price, contracts, realized_pnl,
  ROUND(((total_credit - close_price) / NULLIF(total_credit, 0) * 100)::numeric, 2) as ic_return_direct,
  ROUND((realized_pnl / NULLIF(total_credit * contracts * 100, 0) * 100)::numeric, 2) as ic_return_from_pnl,
  (total_credit - close_price) * contracts * 100 as pnl_check
FROM flame_positions
WHERE status IN ('closed', 'expired')
  AND realized_pnl IS NOT NULL
  AND (close_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date
ORDER BY close_time ASC;
"

echo ""
echo "=== FLAME OPEN POSITIONS NOW ==="
psql $DATABASE_URL -c "
SELECT position_id, total_credit, contracts, collateral_required,
  put_short_strike, put_long_strike, call_short_strike, call_long_strike,
  open_time AT TIME ZONE 'America/Chicago' as open_ct
FROM flame_positions
WHERE status = 'open'
ORDER BY open_time DESC;
"

echo ""
echo "=== FLAME LATEST EQUITY SNAPSHOT (unrealized IC return) ==="
psql $DATABASE_URL -c "
SELECT snapshot_time AT TIME ZONE 'America/Chicago' as snap_ct,
  open_positions, unrealized_pnl, balance
FROM flame_equity_snapshots
ORDER BY snapshot_time DESC
LIMIT 3;
"

echo ""
echo "=== FLAME CONFIG (starting_capital, profit_target_pct) ==="
psql $DATABASE_URL -c "
SELECT starting_capital, profit_target_pct, stop_loss_pct, spread_width, max_contracts
FROM flame_config
LIMIT 1;
"

echo ""
echo "=== SUMMARY ==="
psql $DATABASE_URL -c "
SELECT
  COUNT(*) as trades_today,
  ROUND(SUM(realized_pnl)::numeric, 2) as total_pnl,
  ROUND(SUM(total_credit * contracts * 100)::numeric, 2) as total_credit_exposure,
  ROUND((SUM(realized_pnl) / NULLIF(SUM(total_credit * contracts * 100), 0) * 100)::numeric, 2) as aggregate_ic_return_from_pnl,
  ROUND(AVG(CASE WHEN total_credit > 0 THEN ((total_credit - close_price) / total_credit * 100) END)::numeric, 2) as avg_ic_return_direct
FROM flame_positions
WHERE status IN ('closed', 'expired')
  AND realized_pnl IS NOT NULL
  AND (close_time AT TIME ZONE 'America/Chicago')::date = (NOW() AT TIME ZONE 'America/Chicago')::date;
"
