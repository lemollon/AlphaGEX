"""Forward record of what the squeeze signal actually said, and what happened.

WHY THIS EXISTS
---------------
Every number on the squeeze page is a BACKTEST number. +$2.18/trade, 83.3%
win, $1,000 -> $3,728 — all of it measured before the signal went live and
none of it evidence about the signal as it is running now. The page said so
honestly, but "neither trade has a live day" is a gap you close by recording,
not by disclaiming.

WHAT IS AND IS NOT COMPUTABLE HERE
----------------------------------
The trade is a SPY 0DTE put spread entered at 11:05 ET and held to
settlement, so its OUTCOME is decided by that same session's close against
the short strike — and the close is already stored daily in sw_gamma_daily.
So outcome, win rate and breach depth need no new market data at all.

Dollar P&L needs the CREDIT taken at 11:05, which no job used to capture --
so this originally tracked outcome only and said dollars were untrackable.
That was a missing job, not a fact. capture_entry_credit() runs at the entry
clock, quotes the actual spread and stores what it paid, CROSSING the spread
the way the backtest measured it: short sold at the bid, long bought at the
ask. Mid-to-mid would flatter every entry by exactly what a real order gives
up.

    pnl = (credit - breach) * 100        per one-lot, settled at the close

A credit that could not be priced stays NULL and so does its P&L. An assumed
credit would turn "we did not measure this" into a number someone could
average, which is worse than an empty column.

THE ONE-SESSION LAG, AGAIN
--------------------------
A verdict computed from session D-1's close is actionable on the MORNING of
session D, and the trade it implies settles at D's close. So a decision is
recorded under D, and settled once D's own close lands.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

LEDGER_TABLE = "sw_squeeze_ledger"

# The backtest claim this forward record exists to test.
BACKTEST_WIN_RATE = 0.833
BACKTEST_N = 898

_DDL = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    trade_date    DATE PRIMARY KEY,
    verdict       VARCHAR(16) NOT NULL,
    traded        BOOLEAN NOT NULL,
    short_put     DOUBLE PRECISION,
    long_put      DOUBLE PRECISION,
    width         DOUBLE PRECISION,
    spot_decision DOUBLE PRECISION,
    spot_entry    DOUBLE PRECISION,
    credit        DOUBLE PRECISION,
    spot_settle   DOUBLE PRECISION,
    outcome       VARCHAR(12),
    breach        DOUBLE PRECISION,
    pnl           DOUBLE PRECISION,
    note          VARCHAR(200),
    updated_at    TIMESTAMP NOT NULL
)
"""


def ensure_ledger_table(engine: Engine) -> None:
    """Idempotent create, plus the columns added after the table shipped.

    spot_entry / credit / pnl arrived with the 10:05 CT entry-quote job; a
    table created before that has to grow them or every P&L read is NULL.
    """
    with engine.begin() as conn:
        conn.execute(text(_DDL))
        if engine.dialect.name != "sqlite":
            for col, typ in (("spot_entry", "DOUBLE PRECISION"),
                             ("credit", "DOUBLE PRECISION"),
                             ("pnl", "DOUBLE PRECISION")):
                conn.execute(text(
                    f"ALTER TABLE {LEDGER_TABLE} ADD COLUMN IF NOT EXISTS {col} {typ}"))


def capture_entry_credit(engine: Engine, client: Any, trade_date: date,
                         ticker: str = "SPY") -> dict[str, Any]:
    """Quote today's spread at the entry clock and store what it paid.

    This is the piece that turns the ledger from win-rate into dollars. The
    backtest measured "real NBBO fills crossing the spread", so this crosses
    too: the short leg is sold at the BID and the long leg bought at the ASK,
    reconstructed from the mid and half-spread helpers the executor already
    uses. Taking mid-to-mid would flatter every entry by exactly the amount a
    real order gives up.

    Strikes are re-derived from spot AT THIS MOMENT, not from the overnight
    decision — that is what the rule actually says, and the decision row's
    indicative strikes are replaced with the ones a real order would use.

    Never raises. A missing or one-sided book leaves credit NULL, which the
    summary reports as un-priced rather than as zero.
    """
    from .gamma_regime import SHORT_OFFSET, SPREAD_WIDTH

    out: dict[str, Any] = {"credit": None, "spot": None, "reason": None}
    try:
        spot = client._spot(ticker)
        if not spot:
            out["reason"] = "no spot at entry"
            return out
        short_put = round(spot) - SHORT_OFFSET
        long_put = short_put - SPREAD_WIDTH
        legs = [{"expiration": trade_date.isoformat(), "type": "put", "strike": short_put},
                {"expiration": trade_date.isoformat(), "type": "put", "strike": long_put}]
        mids = client.get_leg_mids(ticker=ticker, legs=legs)
        halves = client.get_leg_spreads(ticker=ticker, legs=legs)
        if any(m is None for m in mids) or any(h is None for h in halves):
            out["reason"] = "one-sided or missing book at entry"
            out["spot"] = float(spot)
            return out
        short_bid = mids[0] - halves[0]      # sell the short at the bid
        long_ask = mids[1] + halves[1]       # buy the long at the ask
        credit = short_bid - long_ask
        if credit <= 0:
            out["reason"] = f"non-positive credit ({credit:.2f}) — not a sellable spread"
            out["spot"] = float(spot)
            return out
        out.update({"credit": round(credit, 2), "spot": float(spot),
                    "short_put": short_put, "long_put": long_put})
        with engine.begin() as conn:
            conn.execute(text(
                f"UPDATE {LEDGER_TABLE} SET credit = :c, spot_entry = :s, "
                "short_put = :sp, long_put = :lp, updated_at = CURRENT_TIMESTAMP "
                "WHERE trade_date = :d AND outcome IS NULL"),
                {"c": out["credit"], "s": out["spot"], "sp": short_put,
                 "lp": long_put, "d": trade_date})
    except Exception as e:  # noqa: BLE001
        logger.warning("[SqueezeLedger] entry credit failed: %r", e)
        out["reason"] = f"entry quote error: {e}"
    return out


def record_decision(engine: Engine, trade_date: date, verdict: str,
                    ticket: dict[str, Any] | None, traded: bool,
                    note: str | None = None) -> None:
    """Write what the signal said for `trade_date`, before the outcome exists.

    Recorded even when the answer is "do not trade" — a signal that stands
    down on the day of a large move is doing its job, and a record that only
    contains the days it traded cannot show that.

    Idempotent on trade_date; a re-run before settlement overwrites the
    decision, never the settled outcome.
    """
    ensure_ledger_table(engine)
    sell = (ticket or {}).get("sell") or {}
    params = {
        "d": trade_date, "v": verdict, "t": bool(traded),
        "sp": sell.get("short_put"), "lp": sell.get("long_put"),
        "w": sell.get("width"), "spot": (ticket or {}).get("spot"),
        "n": (note or "")[:200],
    }
    sql = (
        f"INSERT INTO {LEDGER_TABLE} (trade_date, verdict, traded, short_put, "
        "long_put, width, spot_decision, note, updated_at) "
        "VALUES (:d, :v, :t, :sp, :lp, :w, :spot, :n, CURRENT_TIMESTAMP) "
        "ON CONFLICT (trade_date) DO UPDATE SET verdict = EXCLUDED.verdict, "
        "traded = EXCLUDED.traded, short_put = EXCLUDED.short_put, "
        "long_put = EXCLUDED.long_put, width = EXCLUDED.width, "
        "spot_decision = EXCLUDED.spot_decision, note = EXCLUDED.note, "
        "updated_at = CURRENT_TIMESTAMP "
        f"WHERE {LEDGER_TABLE}.outcome IS NULL"
    )
    if engine.dialect.name == "sqlite":
        sql = sql.replace("ON CONFLICT (trade_date)", "ON CONFLICT(trade_date)")
    with engine.begin() as conn:
        conn.execute(text(sql), params)


def settle_open(engine: Engine, gamma_table: str = "sw_gamma_daily") -> int:
    """Settle every decision whose own session close has since landed.

    A 0DTE put spread held to settlement wins outright when the close is at or
    above the short strike. Below it, the loss is the distance breached,
    capped at the width — which is why `breach` is stored rather than a
    boolean: "how badly" is the part that decides whether a live sample
    matches a backtest whose worst day was -$198.
    """
    ensure_ledger_table(engine)
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT l.trade_date, l.short_put, l.width, g.spot, l.credit "
            f"FROM {LEDGER_TABLE} l JOIN {gamma_table} g "
            "ON g.trade_date = l.trade_date "
            "WHERE l.outcome IS NULL AND l.traded = 1 AND g.spot IS NOT NULL"
            if engine.dialect.name == "sqlite" else
            f"SELECT l.trade_date, l.short_put, l.width, g.spot, l.credit "
            f"FROM {LEDGER_TABLE} l JOIN {gamma_table} g "
            "ON g.trade_date = l.trade_date "
            "WHERE l.outcome IS NULL AND l.traded = TRUE AND g.spot IS NOT NULL"
        )).fetchall()

        n = 0
        for d, short_put, width, spot, credit in rows:
            if short_put is None or spot is None:
                continue
            spot, short_put = float(spot), float(short_put)
            width = float(width or 2.0)
            if spot >= short_put:
                outcome, breach = "win", 0.0
            else:
                breach = min(short_put - spot, width)
                outcome = "loss" if breach >= width else "partial"
            # Dollars only when the entry was actually priced. A NULL credit
            # stays NULL: an assumed credit would turn "we did not measure
            # this" into a number someone could average.
            pnl = None if credit is None else round((float(credit) - breach) * 100.0, 2)
            conn.execute(text(
                f"UPDATE {LEDGER_TABLE} SET outcome = :o, breach = :b, "
                "spot_settle = :s, pnl = :p, updated_at = CURRENT_TIMESTAMP "
                "WHERE trade_date = :d"),
                {"o": outcome, "b": breach, "s": spot, "p": pnl, "d": d})
            n += 1
    if n:
        logger.info("[SqueezeLedger] settled %d session(s)", n)
    return n


def ledger_summary(engine: Engine, limit: int = 250) -> dict[str, Any]:
    """The forward record, next to the backtest claim it is testing.

    Dollar totals cover only the sessions whose entry was actually priced;
    `n_priced` says how many that is, so a P&L is never read as covering more
    trades than it does.
    """
    out: dict[str, Any] = {
        "rows": [], "n_decisions": 0, "n_traded": 0, "n_settled": 0,
        "wins": 0, "losses": 0, "partials": 0, "win_rate": None,
        "worst_breach": None, "backtest_win_rate": BACKTEST_WIN_RATE,
        "backtest_n": BACKTEST_N, "first_date": None, "last_date": None,
        "n_priced": 0, "pnl_total": None, "pnl_per_trade": None,
        "worst_day": None, "backtest_per_trade": 2.18, "reason": None,
    }
    try:
        ensure_ledger_table(engine)
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT trade_date, verdict, traded, short_put, long_put, "
                "spot_decision, spot_settle, outcome, breach, note, credit, pnl "
                f"FROM {LEDGER_TABLE} ORDER BY trade_date DESC LIMIT :n"
            ), {"n": limit}).fetchall()
    except Exception as e:  # noqa: BLE001
        out["reason"] = f"ledger query error: {e}"
        return out

    recs = []
    for r in rows:
        recs.append({
            "trade_date": r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0]),
            "verdict": r[1], "traded": bool(r[2]),
            "short_put": r[3], "long_put": r[4],
            "spot_decision": r[5], "spot_settle": r[6],
            "outcome": r[7], "breach": r[8], "note": r[9],
            "credit": r[10], "pnl": r[11],
        })
    recs.reverse()
    out["rows"] = recs
    out["n_decisions"] = len(recs)
    traded = [x for x in recs if x["traded"]]
    settled = [x for x in traded if x["outcome"]]
    out["n_traded"] = len(traded)
    out["n_settled"] = len(settled)
    out["wins"] = sum(1 for x in settled if x["outcome"] == "win")
    out["losses"] = sum(1 for x in settled if x["outcome"] == "loss")
    out["partials"] = sum(1 for x in settled if x["outcome"] == "partial")
    if settled:
        out["win_rate"] = out["wins"] / len(settled)
        out["worst_breach"] = max((x["breach"] or 0.0) for x in settled)
    priced = [x for x in settled if x["pnl"] is not None]
    out["n_priced"] = len(priced)
    if priced:
        total = sum(float(x["pnl"]) for x in priced)
        out["pnl_total"] = round(total, 2)
        out["pnl_per_trade"] = round(total / len(priced), 2)
        out["worst_day"] = round(min(float(x["pnl"]) for x in priced), 2)
    if recs:
        out["first_date"], out["last_date"] = recs[0]["trade_date"], recs[-1]["trade_date"]
    return out
