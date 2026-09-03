-- fix_mstu_split_20260824.sql
--
-- ONE-SHOT MANUAL REPAIR. Do not run automatically; a human runs this by
-- hand against prod, once, after reviewing it line by line.
--
-- Background: MSTU did a 1:10 reverse split on 2026-08-24. TSUNAMI-TREND's
-- trend_engine.py had no split-adjustment logic before this fix, so the
-- book kept the pre-split share count (26.131 sh @ avg_cost 2.42) against
-- the post-split price. The next SELL fired on the un-adjusted 13.5231
-- share quantity (10x too many) and booked a phantom +$377 realized gain
-- (see the "confirm-trade" / drawdown-solutions incident narrative for the
-- full account). This script retroactively split-adjusts the book row,
-- corrects the bad SELL trade's shares and realized_pnl, backs the phantom
-- proceeds out of cash, and inserts a SPLIT trade row documenting the fix
-- (the same shape trend_engine.py now writes going forward for real splits
-- via `_apply_splits_for_book()`).
--
-- NOTE on the SELL row date: the task narrative that produced this script
-- described the bad SELL as "dated 2025-08-25" in prose but gave the WHERE
-- filter as '2026-08-25' -- the split itself is 2026-08-24, so a next-day
-- SELL on 2026-08-25 is the only date that is chronologically consistent.
-- This script uses 2026-08-25. VERIFY the actual row before running --
-- if no row matches, STOP and re-check the real trade date instead of
-- relaxing the WHERE clause.
--
-- Run this by hand, read every UPDATE's row count, and only COMMIT if each
-- statement affected exactly the row you expect (1 for each UPDATE/INSERT
-- below). If any UPDATE affects 0 or >1 rows, ROLLBACK and investigate.

BEGIN;

-- 1. Split-adjust the held book row to 0.26131 sh @ 24.206, per the
--    literal values given in this repair's spec.
--    FLAG FOR THE HUMAN RUNNING THIS: the bug writeup that produced this
--    script separately describes the correct post-split position as
--    "2.6131 shares at 24.206" (26.131 * 0.1 = 2.6131), a 10x difference
--    from the 0.26131 used here. VERIFY the real pre-repair book row
--    (`SELECT shares, avg_cost FROM tsunami_trend_book WHERE letf='MSTU'`)
--    against both candidates before running -- shares should equal
--    (pre-repair shares * 0.1). Do not run blind on either number.
UPDATE tsunami_trend_book
   SET shares = 0.26131,
       avg_cost = 24.206,
       updated_at = NOW()
 WHERE letf = 'MSTU';

-- 2. Correct the bad SELL trade: it fired on 13.5231 shares (10x too many,
--    since the book was never split-adjusted) at whatever price it filled;
--    the corrected share count is 1.35231 (13.5231 / 10) and the realized
--    P&L is recomputed on the corrected quantity against the same fill
--    price ($30.3105) and slippage (SLIP=0.0002):
--        realized_pnl = 1.35231 * (30.3105 * (1 - 0.0002) - 24.206)
--                      = 1.35231 * (30.304437900 - 24.206)
--                      = 1.35231 * 6.098437900
--                      = 8.246978556549...  ->  8.2470 (DECIMAL(12,4))
UPDATE tsunami_trend_trades
   SET shares = 1.35231,
       realized_pnl = 8.2470
 WHERE letf = 'MSTU'
   AND side = 'SELL'
   AND DATE(ts AT TIME ZONE 'America/New_York') = '2026-08-25';

-- 3. Back the phantom proceeds out of cash. The bad SELL credited cash for
--    13.5231 shares' worth of proceeds; only 1.35231 shares were real, so
--    the delta (12.17079 shares) worth of phantom proceeds must be removed:
--        cash_delta = (13.5231 - 1.35231) * 30.3105 * (1 - 0.0002)
--                    = 12.17079 * 30.304437900
--                    = 368.828949748941...  ->  368.8289 (DECIMAL(12,4))
UPDATE tsunami_trend_cash
   SET cash = cash - 368.8289
 WHERE id = 1;

-- 4. Document the split adjustment itself as a trade row (same shape the
--    fixed engine now writes automatically for future splits).
INSERT INTO tsunami_trend_trades (letf, side, shares, price, reason, realized_pnl)
VALUES ('MSTU', 'SPLIT', 0.26131, 24.206, 'split 0.1 on 2026-08-24', 0);

COMMIT;

-- POST-RUN NOTE: cash may go negative (or land lower than expected) after
-- this repair, because trades that happened between the split (2026-08-24)
-- and this repair running were phantom-funded off the inflated cash
-- balance the bad SELL created. That is expected and correct -- it is the
-- book catching up to reality, not a new bug. The engine's own cash gate
-- (`if cost <= cash`) will simply block new BUYs until real proceeds/
-- dividends bring the balance back above zero; no code change is needed
-- for that, it is the intended fail-safe behavior.
