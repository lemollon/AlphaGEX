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

Dollar P&L does NOT follow, because it needs the CREDIT taken at 11:05 and
nothing captures an intraday quote. Recording a made-up credit to produce a
tidy P&L line would be worse than having none: it would look like evidence.
So this tracks what it can measure — did the short strike hold, and by how
much did it fail — and says plainly that dollars are not being tracked.

Win rate alone is still the sharpest forward test available: the backtest
claims 83.3% over 898 trades, and that is a number a live sample can
contradict.

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
    spot_settle   DOUBLE PRECISION,
    outcome       VARCHAR(12),
    breach        DOUBLE PRECISION,
    note          VARCHAR(200),
    updated_at    TIMESTAMP NOT NULL
)
"""


def ensure_ledger_table(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(_DDL))


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
            f"SELECT l.trade_date, l.short_put, l.width, g.spot "
            f"FROM {LEDGER_TABLE} l JOIN {gamma_table} g "
            "ON g.trade_date = l.trade_date "
            "WHERE l.outcome IS NULL AND l.traded = 1 AND g.spot IS NOT NULL"
            if engine.dialect.name == "sqlite" else
            f"SELECT l.trade_date, l.short_put, l.width, g.spot "
            f"FROM {LEDGER_TABLE} l JOIN {gamma_table} g "
            "ON g.trade_date = l.trade_date "
            "WHERE l.outcome IS NULL AND l.traded = TRUE AND g.spot IS NOT NULL"
        )).fetchall()

        n = 0
        for d, short_put, width, spot in rows:
            if short_put is None or spot is None:
                continue
            spot, short_put = float(spot), float(short_put)
            width = float(width or 2.0)
            if spot >= short_put:
                outcome, breach = "win", 0.0
            else:
                breach = min(short_put - spot, width)
                outcome = "loss" if breach >= width else "partial"
            conn.execute(text(
                f"UPDATE {LEDGER_TABLE} SET outcome = :o, breach = :b, "
                "spot_settle = :s, updated_at = CURRENT_TIMESTAMP "
                "WHERE trade_date = :d"),
                {"o": outcome, "b": breach, "s": spot, "d": d})
            n += 1
    if n:
        logger.info("[SqueezeLedger] settled %d session(s)", n)
    return n


def ledger_summary(engine: Engine, limit: int = 250) -> dict[str, Any]:
    """The forward record, next to the backtest claim it is testing.

    `pnl` is deliberately absent. See the module docstring: the entry credit
    is not captured, and inventing one would manufacture evidence.
    """
    out: dict[str, Any] = {
        "rows": [], "n_decisions": 0, "n_traded": 0, "n_settled": 0,
        "wins": 0, "losses": 0, "partials": 0, "win_rate": None,
        "worst_breach": None, "backtest_win_rate": BACKTEST_WIN_RATE,
        "backtest_n": BACKTEST_N, "first_date": None, "last_date": None,
        "tracks_dollars": False, "reason": None,
    }
    try:
        ensure_ledger_table(engine)
        with engine.begin() as conn:
            rows = conn.execute(text(
                f"SELECT trade_date, verdict, traded, short_put, long_put, "
                "spot_decision, spot_settle, outcome, breach, note "
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
    if recs:
        out["first_date"], out["last_date"] = recs[0]["trade_date"], recs[-1]["trade_date"]
    return out
