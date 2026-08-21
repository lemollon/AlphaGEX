-- Restate THREE FLOW trades booked off garbage opening-bell quotes.
--
-- 🚨 WHY. All three entered at exactly 13:30:00 UTC (08:30 CT, the opening
-- bell) and all three closed within three minutes at "profit target". Their
-- short-put legs are provably wrong against the same session's own clean
-- quotes — put prices must rise smoothly with strike, and these do not:
--
--   2026-08-18  763 put booked @ 2.750   while the 764 put, quoted by the same
--                                        bot two minutes later, was 0.695
--   2026-08-12  769 put booked @ 2.155   and the 764 put @ 0.900, while the
--               767 put the same session was 0.655 — the 764 is dearer than a
--               HIGHER strike, which cannot happen
--   2026-08-21  760 put booked @ 1.460   against the same trade's own clean
--               755 leg at 0.310. That is 0.230/strike. Four minutes later the
--               same bot quoted 754 @ 0.285 and 759 @ 0.755 (0.094/strike), and
--               at 16:25 quoted 756 @ 0.205 and 761 @ 0.605 (0.080/strike). The
--               08:30 slope is 2.4-2.9x every other same-day observation, and
--               the 755 leg is in line with them — the 760 leg is the outlier.
--               ⭐ It is dearer DESPITE spot being HIGHER at 13:30 than 13:34
--               (the whole structure shifted down a strike in between), which
--               is the wrong direction for a put.
--
-- The inflated credit made each position look instantly profitable against
-- pt_pct=0.30, so the monitor closed it minutes later and booked the fiction.
--
-- ⛔ THE CORRECTED LEG PRICES ARE RECONSTRUCTIONS, NOT OBSERVATIONS. Each is a
-- linear interpolation across strike from the nearest CLEAN same-session quotes
-- this bot actually recorded. They are stated in full below so the arithmetic
-- can be checked or rejected, and every original value is preserved in
-- flow_restatements so this is reversible with one statement.
--
--   2026-08-18: 759 @ 0.235 and 764 @ 0.695 (13:32) -> 0.0920/strike
--               763 put = 0.695 - 0.0920 = 0.603
--               credit  = (0.603 + 0.440) - (0.115 + 0.225) = 0.703
--               P&L     = (0.703 - 0.840) x 27 x 100 = -369.90
--
--   2026-08-12: 762 @ 0.185 and 767 @ 0.655 (13:33) -> 0.0940/strike
--               769 put = 0.655 + 2(0.0940) = 0.843
--               764 put = 0.185 + 2(0.0940) = 0.373
--               credit  = (0.843 + 0.295) - (0.373 + 0.085) = 0.680
--               P&L     = (0.680 - 0.875) x 14 x 100 = -273.00
--
--   2026-08-21: 754 @ 0.285 and 759 @ 0.755 (13:34) -> 0.0940/strike,
--               anchored on this trade's OWN clean 755 leg @ 0.310
--               760 put = 0.310 + 5(0.0940) = 0.780
--               credit  = (0.780 + 0.465) - (0.310 + 0.065) = 0.870
--               P&L     = (0.870 - 0.800) x 28 x 100 = +196.00
--
-- ⭐ SANITY CHECK ON THE RECONSTRUCTION: the corrected credits land at 14.1%,
-- 13.6% and 17.4% of the $5 wing — all inside the 10.4-17.7% band every clean
-- FLOW fill occupies. The reconstruction produces ORDINARY trades, which is the
-- evidence that it is right. The booked versions were 56.2%, 28.8% and 30.2%.
--
-- 🚨 WHAT THIS RESTATEMENT CANNOT DO. It corrects the ENTRY and re-prices the
-- P&L at the exit mark the bot actually recorded. It cannot recover the
-- counterfactual, because a correct entry would have changed the exit decision
-- itself: on 08-21 the corrected credit puts max_profit at $87/contract, so the
-- 30% profit target sits at $26.10 and the $7/contract gain at 13:33 would NOT
-- have triggered a close — the position would still have been open. The +196.00
-- booked here is "this trade at the mark we saw", not "what this trade would
-- have made". Treat all three restated figures as the best available accounting
-- of a corrupted record, not as clean history.
--
-- Net effect per trade (stable regardless of when this is run):
--   flow-2026-08-18-d2e4ed9e   +5,319.00 -> -369.90   =  -5,688.90
--   flow-2026-08-12-58075fae     +791.00 -> -273.00   =  -1,064.00
--   flow-2026-08-21-7a00471b   +1,988.00 -> +196.00   =  -1,792.00
--                                              TOTAL  =  -8,544.90
--
-- As of 2026-08-21 13:38 CT that takes the August book from -296.00 to
-- -8,840.90 and FLOW from +12,287.00 to +3,742.10. Those two figures move with
-- every new fill; the verification SELECTs at the bottom print the live truth.
--
-- Run inside a transaction. Verify with the SELECTs at the bottom BEFORE COMMIT.

BEGIN;

-- Audit trail first: nothing is overwritten without the original kept.
CREATE TABLE IF NOT EXISTS flow_restatements (
    position_id      TEXT PRIMARY KEY,
    restated_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    reason           TEXT NOT NULL,
    orig_entry_price NUMERIC,
    orig_realized_pnl NUMERIC,
    orig_legs        TEXT,
    new_entry_price  NUMERIC,
    new_realized_pnl NUMERIC
);

INSERT INTO flow_restatements
    (position_id, reason, orig_entry_price, orig_realized_pnl, orig_legs,
     new_entry_price, new_realized_pnl)
SELECT position_id,
       'bad opening-bell quote: short put breaks the same session''s own strike curve; credit was 56%/29%/30% of wing width against 10-18% for every clean fill',
       entry_price, realized_pnl, legs::text,
       CASE position_id WHEN 'flow-2026-08-18-d2e4ed9e' THEN 0.703
                        WHEN 'flow-2026-08-12-58075fae' THEN 0.680
                        WHEN 'flow-2026-08-21-7a00471b' THEN 0.870 END,
       CASE position_id WHEN 'flow-2026-08-18-d2e4ed9e' THEN -369.90
                        WHEN 'flow-2026-08-12-58075fae' THEN -273.00
                        WHEN 'flow-2026-08-21-7a00471b' THEN  196.00 END
FROM flow_closed_trades
WHERE position_id IN ('flow-2026-08-18-d2e4ed9e',
                      'flow-2026-08-12-58075fae',
                      'flow-2026-08-21-7a00471b')
ON CONFLICT (position_id) DO NOTHING;   -- idempotent: re-running never re-stamps

-- Apply. Sourced from the audit row so the script cannot drift from what it logged.
UPDATE flow_closed_trades t
SET entry_price  = r.new_entry_price,
    realized_pnl = r.new_realized_pnl
FROM flow_restatements r
WHERE t.position_id = r.position_id
  AND t.realized_pnl IS DISTINCT FROM r.new_realized_pnl;   -- idempotent

-- ── VERIFY BEFORE COMMIT ────────────────────────────────────────────────────
-- Expect exactly 3 rows, adjustments -5688.90 / -1064.00 / -1792.00.
SELECT t.position_id,
       r.orig_realized_pnl AS was,
       t.realized_pnl      AS now,
       t.realized_pnl - r.orig_realized_pnl AS adjustment
FROM flow_closed_trades t
JOIN flow_restatements r USING (position_id)
ORDER BY t.position_id;

SELECT COUNT(*) AS rows_restated,
       ROUND(SUM(t.realized_pnl - r.orig_realized_pnl)::numeric, 2) AS total_adjustment
FROM flow_closed_trades t JOIN flow_restatements r USING (position_id);

SELECT ROUND(SUM(realized_pnl)::numeric, 2) AS flow_total_after
FROM flow_closed_trades;

-- ⭐ NO OTHER TRADE SHOULD STILL BE ABOVE THE CREDIT CEILING. If this returns
-- rows, there is a fourth phantom and the ceiling in iron_condor.py did not
-- catch it — investigate before committing.
SELECT position_id, entry_time, entry_price, realized_pnl
FROM flow_closed_trades
WHERE entry_price > 0.22 * 5
ORDER BY entry_time;

COMMIT;

-- ── ROLLBACK, if the reconstruction is rejected ─────────────────────────────
-- UPDATE flow_closed_trades t
-- SET entry_price = r.orig_entry_price, realized_pnl = r.orig_realized_pnl
-- FROM flow_restatements r WHERE t.position_id = r.position_id;
-- DELETE FROM flow_restatements;
