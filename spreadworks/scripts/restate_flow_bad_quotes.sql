-- Restate two FLOW trades booked off garbage opening-bell quotes.
--
-- 🚨 WHY. Both entered at exactly 13:30:00 UTC (08:30 CT, the opening bell) and
-- both closed one minute later at "profit target". Their short-put legs are
-- provably wrong by arbitrage-free monotonicity — a lower-strike put cannot
-- cost more than a higher-strike one in the same session:
--
--   2026-08-18  763 put booked @ 2.750   while the 764 put, quoted by the same
--                                        bot two minutes later, was 0.695
--   2026-08-12  769 put booked @ 2.155   and the 764 put @ 0.900, while the
--               767 put the same session was 0.655 — the 764 is dearer than a
--               HIGHER strike, which cannot happen
--
-- The inflated credit made each position look instantly profitable against
-- pt_pct=0.30, so the monitor closed it a minute later and booked the fiction.
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
-- ⭐ SANITY CHECK ON THE RECONSTRUCTION: both corrected credits (0.703, 0.680)
-- land at 14% of the $5 wing — inside the 13-18% band every other FLOW fill
-- occupies. The reconstruction produces ordinary trades, which is the evidence
-- that it is right. The booked versions were 56% and 29%.
--
-- Net effect: FLOW +9,561.50 -> +2,808.60. August book -2,940.50 -> -9,693.40.
--
-- Run inside a transaction. Verify with the SELECT at the bottom BEFORE COMMIT.

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
       'bad opening-bell quote: short put violates strike monotonicity vs same-session quotes; credit was 56%/29% of wing width against 13-18% for every clean fill',
       entry_price, realized_pnl, legs,
       CASE position_id WHEN 'flow-2026-08-18-d2e4ed9e' THEN 0.703
                        WHEN 'flow-2026-08-12-58075fae' THEN 0.680 END,
       CASE position_id WHEN 'flow-2026-08-18-d2e4ed9e' THEN -369.90
                        WHEN 'flow-2026-08-12-58075fae' THEN -273.00 END
FROM flow_closed_trades
WHERE position_id IN ('flow-2026-08-18-d2e4ed9e', 'flow-2026-08-12-58075fae')
ON CONFLICT (position_id) DO NOTHING;   -- idempotent: re-running never re-stamps

-- Apply. Sourced from the audit row so the script cannot drift from what it logged.
UPDATE flow_closed_trades t
SET entry_price  = r.new_entry_price,
    realized_pnl = r.new_realized_pnl
FROM flow_restatements r
WHERE t.position_id = r.position_id
  AND t.realized_pnl IS DISTINCT FROM r.new_realized_pnl;   -- idempotent

-- ── VERIFY BEFORE COMMIT ────────────────────────────────────────────────────
SELECT t.position_id,
       r.orig_realized_pnl AS was,
       t.realized_pnl      AS now,
       t.realized_pnl - r.orig_realized_pnl AS adjustment
FROM flow_closed_trades t
JOIN flow_restatements r USING (position_id)
ORDER BY t.position_id;

SELECT ROUND(SUM(realized_pnl)::numeric, 2) AS flow_total_after
FROM flow_closed_trades;

COMMIT;

-- ── ROLLBACK, if the reconstruction is rejected ─────────────────────────────
-- UPDATE flow_closed_trades t
-- SET entry_price = r.orig_entry_price, realized_pnl = r.orig_realized_pnl
-- FROM flow_restatements r WHERE t.position_id = r.position_id;
-- DELETE FROM flow_restatements;
