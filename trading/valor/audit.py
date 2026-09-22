"""Non-destructive, versioned paper-result quality screen (not proof of execution)."""
QUALITY_SELECT = r"""
WITH ranked AS (
 SELECT t.*, COUNT(*) OVER (
   PARTITION BY ticker, symbol, direction, contracts, entry_price, exit_price,
     date_trunc('second', open_time), date_trunc('second', close_time)
 ) AS duplicate_cluster_size
 FROM valor_closed_trades t
)
SELECT ranked.*, CASE
 WHEN UPPER(COALESCE(close_reason,'')) LIKE '%RECAP%'
   OR UPPER(COALESCE(trade_reasoning,'')) LIKE '%RECAPITAL%' THEN 'recapitalization'
 WHEN open_time IS NULL OR close_time IS NULL OR close_time < open_time
   OR entry_price <= 0 OR exit_price <= 0 OR contracts <= 0
   OR realized_pnl IS NULL THEN 'invalid_record'
 WHEN UPPER(COALESCE(close_reason,'')) LIKE 'STALE_WATCHDOG%'
   OR close_time - open_time > CASE WHEN ticker IN ('CL','NG')
       THEN INTERVAL '12 hours' ELSE INTERVAL '24 hours' END THEN 'hold_violation'
 WHEN duplicate_cluster_size > 1 THEN 'duplicate_candidate'
 ELSE 'eligible'
 END AS quality_status
FROM ranked
"""

PERFORMANCE_SQL = """
WITH eligible AS (
 SELECT *, SUM(realized_pnl) OVER (PARTITION BY ticker ORDER BY close_time, position_id) AS equity
 FROM valor_trade_quality WHERE quality_status='eligible'
), drawdowns AS (
 SELECT *, GREATEST(0, MAX(equity) OVER (PARTITION BY ticker ORDER BY close_time, position_id)) - equity AS drawdown
 FROM eligible
)
SELECT ticker, COUNT(*) AS trades, SUM(realized_pnl) AS pnl,
 AVG(realized_pnl) AS expectancy_per_trade,
 AVG((realized_pnl > 0)::int) AS win_rate,
 SUM(GREATEST(realized_pnl,0)) / NULLIF(-SUM(LEAST(realized_pnl,0)),0) AS profit_factor,
 MAX(drawdown) AS max_realized_drawdown,
 AVG(mfe_points) AS mean_mfe_points, AVG(mae_points) AS mean_mae_points
FROM drawdowns GROUP BY ticker ORDER BY pnl DESC
"""
