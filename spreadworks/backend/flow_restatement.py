"""One-shot, idempotent restatement of three FLOW trades booked off garbage
opening-bell quotes.

🚨 WHY THIS EXISTS AS CODE AND NOT A HAND-RUN SCRIPT. The equivalent SQL lives
at `spreadworks/scripts/restate_flow_bad_quotes.sql` and is the readable
version of this, but a correction to booked history that only ever runs when
somebody remembers to paste it into a shell is a correction that silently
doesn't happen. This runs on boot, no-ops forever after the first time, and is
reviewable in git like anything else.

WHAT WAS WRONG. All three trades entered at exactly 13:30:00 UTC — 08:30 CT,
the opening bell, where marks are wide, one-sided and frequently stale — and
all three closed within three minutes at "profit target". Their short-put legs
break the same session's own strike curve:

  2026-08-18  763 put booked @ 2.750, while the 764 put quoted by the same bot
              two minutes later was 0.695. A LOWER strike cannot cost 4x a
              HIGHER one; arbitrage-free monotonicity is a hard constraint.
  2026-08-12  769 put @ 2.155 and 764 put @ 0.900, while the 767 put the same
              session was 0.655 — the 764 is dearer than a higher strike.
  2026-08-21  760 put @ 1.460 against this trade's OWN clean 755 leg at 0.310,
              i.e. 0.230/strike. Four minutes later the same bot quoted
              0.094/strike, and at 16:25 quoted 0.080/strike. The 755 leg is in
              line with those; the 760 leg is the outlier — and it is dearer
              despite spot being HIGHER at 13:30 than at 13:34, which is the
              wrong direction for a put.

The inflated credit made each position look instantly profitable against
pt_pct=0.30, so the monitor closed it minutes later and booked the fiction.

⛔ THE CORRECTED LEG PRICES ARE RECONSTRUCTIONS, NOT OBSERVATIONS — linear
interpolation across strike from the nearest CLEAN same-session quotes this bot
actually recorded. The arithmetic is stated in full in RESTATEMENTS below so it
can be checked or rejected, and every original value is preserved in
`flow_restatements` so this is reversible with one UPDATE.

⭐ SANITY CHECK: the corrected credits land at 14.1%, 13.6% and 17.4% of the $5
wing — all inside the 10.4-17.7% band every clean FLOW fill occupies. The
reconstruction produces ORDINARY trades, which is the evidence it is right. The
booked versions were 56.2%, 28.8% and 30.2%.

🚨 WHAT THIS CANNOT DO. It corrects the entry and re-prices P&L at the exit mark
the bot actually recorded. It cannot recover the counterfactual, because a
correct entry would have changed the exit decision itself: on 08-21 the
corrected credit puts max_profit at $87/contract, so the 30% target sits at
$26.10 and the $7/contract gain at 13:33 would NOT have closed the position.
These are the best available accounting of a corrupted record, not clean
history.

Net effect: -$8,544.90 off FLOW and off the August book.
"""
from __future__ import annotations

import logging

from sqlalchemy import text

logger = logging.getLogger(__name__)

TABLE = "flow_closed_trades"
AUDIT = "flow_restatements"

REASON = (
    "bad opening-bell quote: short put breaks the same session's own strike "
    "curve; credit was 56%/29%/30% of wing width against 10-18% for every "
    "clean fill"
)

# ⛔ `expect_pnl` IS A GUARD, NOT DOCUMENTATION. Each row is only rewritten if
# the ledger still holds exactly the value this analysis was performed against.
# If someone has already edited a row by hand, or the bot somehow re-books it,
# the guard misses and that row is SKIPPED and logged rather than silently
# overwritten with a number derived from a state that no longer exists.
RESTATEMENTS = [
    {
        # 759 @ 0.235 and 764 @ 0.695 (13:32) -> 0.0920/strike
        #   763 put = 0.695 - 0.0920                       = 0.603
        #   credit  = (0.603 + 0.440) - (0.115 + 0.225)    = 0.703
        #   P&L     = (0.703 - 0.840) x 27 x 100           = -369.90
        "position_id": "flow-2026-08-18-d2e4ed9e",
        "expect_pnl": 5319.00,
        "new_entry_price": 0.703,
        "new_realized_pnl": -369.90,
    },
    {
        # 762 @ 0.185 and 767 @ 0.655 (13:33) -> 0.0940/strike
        #   769 put = 0.655 + 2(0.0940)                    = 0.843
        #   764 put = 0.185 + 2(0.0940)                    = 0.373
        #   credit  = (0.843 + 0.295) - (0.373 + 0.085)    = 0.680
        #   P&L     = (0.680 - 0.875) x 14 x 100           = -273.00
        "position_id": "flow-2026-08-12-58075fae",
        "expect_pnl": 791.00,
        "new_entry_price": 0.680,
        "new_realized_pnl": -273.00,
    },
    {
        # 754 @ 0.285 and 759 @ 0.755 (13:34) -> 0.0940/strike, anchored on
        # this trade's OWN clean 755 leg @ 0.310
        #   760 put = 0.310 + 5(0.0940)                    = 0.780
        #   credit  = (0.780 + 0.465) - (0.310 + 0.065)    = 0.870
        #   P&L     = (0.870 - 0.800) x 28 x 100           = +196.00
        "position_id": "flow-2026-08-21-7a00471b",
        "expect_pnl": 1988.00,
        "new_entry_price": 0.870,
        "new_realized_pnl": 196.00,
    },
]

_AUDIT_DDL = f"""
CREATE TABLE IF NOT EXISTS {AUDIT} (
    position_id       TEXT PRIMARY KEY,
    -- CURRENT_TIMESTAMP, not NOW(): identical on Postgres and portable to the
    -- SQLite engine the tests build, so the tested DDL is the shipped DDL.
    restated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason            TEXT NOT NULL,
    orig_entry_price  NUMERIC,
    orig_realized_pnl NUMERIC,
    orig_legs         TEXT,
    new_entry_price   NUMERIC,
    new_realized_pnl  NUMERIC
)
"""


def apply_flow_restatements(engine) -> dict:
    """Apply the restatements. Idempotent, never raises.

    Returns a summary dict: how many rows were rewritten this call, how many
    were already done, and how many were skipped because the ledger no longer
    matched what the analysis was performed against.
    """
    out = {"applied": 0, "already": 0, "skipped": [], "missing": [],
           "total_adjustment": 0.0}
    if engine is None:
        return out
    try:
        with engine.begin() as conn:
            conn.execute(text(_AUDIT_DDL))
            for r in RESTATEMENTS:
                pid = r["position_id"]
                # Already restated? The audit row is the record of record.
                done = conn.execute(
                    text(f"SELECT 1 FROM {AUDIT} WHERE position_id = :p"),
                    {"p": pid}).first()
                if done:
                    out["already"] += 1
                    continue
                row = conn.execute(
                    text(f"SELECT entry_price, realized_pnl, legs "
                         f"FROM {TABLE} WHERE position_id = :p"),
                    {"p": pid}).first()
                if row is None:
                    out["missing"].append(pid)
                    continue
                orig_entry, orig_pnl, orig_legs = row
                # The guard. Compare in cents to sidestep NUMERIC/float noise.
                if round(float(orig_pnl), 2) != round(r["expect_pnl"], 2):
                    out["skipped"].append(
                        f"{pid}: ledger has {float(orig_pnl):+.2f}, analysis "
                        f"was performed against {r['expect_pnl']:+.2f}")
                    continue
                conn.execute(text(
                    f"INSERT INTO {AUDIT} (position_id, reason, "
                    "orig_entry_price, orig_realized_pnl, orig_legs, "
                    "new_entry_price, new_realized_pnl) VALUES "
                    "(:p, :reason, :oe, :op, :ol, :ne, :np)"),
                    {"p": pid, "reason": REASON, "oe": orig_entry,
                     "op": orig_pnl, "ol": orig_legs,
                     "ne": r["new_entry_price"], "np": r["new_realized_pnl"]})
                conn.execute(text(
                    f"UPDATE {TABLE} SET entry_price = :ne, realized_pnl = :np "
                    "WHERE position_id = :p"),
                    {"p": pid, "ne": r["new_entry_price"],
                     "np": r["new_realized_pnl"]})
                out["applied"] += 1
                out["total_adjustment"] += r["new_realized_pnl"] - float(orig_pnl)
    except Exception as e:  # noqa: BLE001
        logger.warning("[FlowRestatement] failed (non-fatal): %r", e)
        out["error"] = repr(e)
        return out

    if out["applied"]:
        logger.warning(
            "[FlowRestatement] rewrote %d phantom trade(s), total adjustment "
            "%+.2f", out["applied"], out["total_adjustment"])
    for s in out["skipped"]:
        logger.warning("[FlowRestatement] SKIPPED %s", s)
    for m in out["missing"]:
        logger.warning("[FlowRestatement] position not found: %s", m)
    return out
