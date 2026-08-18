-- Restate EBB's 2026-08-17 settlement.
--
-- WHY: scanner._settlement_value clamped a credit spread's payoff with
-- max(0.0, val), which for a bull put spread IS max profit. EBB sold the
-- 774P/772P for 0.13 and SPY closed 772.67, so the 774 short finished $1.33
-- in the money. Cost to buy back = 1.33, realized = (0.13 - 1.33) * 1 * 100
-- = -120.00. It booked +13.00.
--
-- Code fix: branch on CREDIT_STRATEGIES before the floor (same commit).
-- This file only repairs the rows that fix cannot reach backwards.
--
-- SPY 2026-08-17 official close = 772.67 (ThetaData /v2/hist/stock/eod,
-- O 776.27 / H 776.775 / L 772.51 / C 772.67). EBB_PM's 772/770 finished
-- genuinely out of the money on the same close, so its +$10.00 is CORRECT
-- and is deliberately not touched here.
--
-- Run inside a transaction and read the verification block before COMMIT.

BEGIN;

-- 1. the closed-trade ledger row
UPDATE ebb_closed_trades
   SET close_price  = 1.33,
       realized_pnl = -120.00
 WHERE position_id = 'ebb-2026-08-17-075f5df0'
   AND realized_pnl = 13.00;          -- no-op if already restated

-- 2. the position row's final mark
UPDATE ebb_positions
   SET mtm_value = 1.33,
       mtm_pnl   = -120.00
 WHERE position_id = 'ebb-2026-08-17-075f5df0'
   AND mtm_pnl = 13.00;

-- 3. the equity curve. Every snapshot written since the bad settle carries
--    the wrong cumulative_pnl, and the scanner re-stamps one EVERY MINUTE
--    the bot is enabled — so this grows until the row is fixed.
--    starting_capital 3000 + (-120) = 2880.
UPDATE ebb_equity_snapshots
   SET cumulative_pnl = cumulative_pnl - 133.00,
       equity         = equity - 133.00
 WHERE snapshot_time >= TIMESTAMP '2026-08-17 20:10:00'
   AND cumulative_pnl = 13.00;

-- verification — expect: realized -120.00, equity 2880.00, cumulative -120.00
SELECT 'closed_trade' AS what, close_price::text AS a, realized_pnl::text AS b
  FROM ebb_closed_trades WHERE position_id = 'ebb-2026-08-17-075f5df0'
UNION ALL
SELECT 'position', mtm_value::text, mtm_pnl::text
  FROM ebb_positions WHERE position_id = 'ebb-2026-08-17-075f5df0'
UNION ALL
SELECT 'equity_latest', equity::text, cumulative_pnl::text
  FROM ebb_equity_snapshots ORDER BY 1;

-- COMMIT;
-- ROLLBACK;
