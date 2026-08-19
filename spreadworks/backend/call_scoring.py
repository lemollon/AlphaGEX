"""Attach outcomes to logged calls, and score them honestly.

🚨 A HIT RATE WITHOUT A BASE RATE IS A LIE. If a verdict is "right" 55% of the
time and SPY rises on 55% of all days in the same window, the verdict knows
nothing. Every figure here ships with the unconditional base rate over the SAME
days and an `n`, because that is the only form in which a hit rate means
anything.

🚨 THREE WINDOWS, NOT ONE. Leron asked for the day's move and the next open,
and those answer different questions:

    call -> that day's close   what the call was worth from the moment it was made
    close -> next open         the overnight gap, which is the right window for
                               a call made near the bell and the WRONG one for a
                               call made at 10am
    call -> next open          the whole hold, for a call carried overnight

Reporting only one of them would flatter whichever surface happens to call at
the matching time of day.

🚨 MULTIPLE CALLS A DAY BREAK ATTRIBUTION. If Risk flips three times, crediting
all three with the day's close-to-close move makes a signal that flips
constantly look brilliant - one of its calls is always right. So each call is
also scored over its own LIFETIME, from when it was made until the next flip,
and the day's last call is marked as the one that carried overnight.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")

# Which way each verdict expects SPY to go. None = no directional claim, so it
# is reported but never scored for direction.
#
# 🚨 These are premium-selling states, not price forecasts. NO_SELL and
# stand_down say "do not sell premium", which is a bet on MOVEMENT, not on
# direction - so they are scored on absolute move, not on sign.
DIRECTIONAL = {
    "DOWN CONFIRMED": "down",
    "UP CONFIRMED": "up",
}
VOLATILITY = {
    "NO_SELL": "big",           # expects a big move either way
    "stand_down": "big",
    "skip_entry": "big",
    "SQUEEZE_WATCH": "big",
    "SELL_PREMIUM": "small",    # expects a quiet tape
    "normal": "small",
}

# What counts as a "big" day. Set from the sample itself rather than a constant,
# so it means "big for this market", not "big in 2019".
BIG_MOVE_PCTILE = 0.70


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """(b/a - 1) * 100, or None if either side is missing."""
    try:
        if a in (None, 0) or b is None:
            return None
        return (float(b) / float(a) - 1.0) * 100.0
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def attach_outcomes(calls: list[dict], spy: dict[str, dict]) -> list[dict]:
    """Add SPY outcomes to each call, plus its lifetime and last-of-day flag."""
    out = [dict(c) for c in calls]

    # Newest-first on the way in; walk oldest-first so "next flip" is knowable.
    out.sort(key=lambda c: (c.get("call_ts") or "", c.get("id") or 0))

    # Lifetime: a call stands until the same surface says something else.
    nxt_by_surface: dict[str, Optional[dict]] = {}
    for c in reversed(out):
        s = c.get("surface")
        n = nxt_by_surface.get(s)
        c["superseded_at"] = (n or {}).get("call_ts")
        c["superseded_by"] = (n or {}).get("verdict")
        nxt_by_surface[s] = c

    # Last call of the day per surface = the one that carried overnight.
    last_seen: dict[tuple, dict] = {}
    for c in out:
        last_seen[(c.get("surface"), c.get("trade_date"))] = c
    for c in out:
        c["last_of_day"] = (last_seen.get((c.get("surface"), c.get("trade_date")))
                            is c)

    for c in out:
        bar = spy.get(c.get("trade_date") or "") or {}
        close, opn = bar.get("close"), bar.get("open")
        prev_close, next_open = bar.get("prev_close"), bar.get("next_open")

        c["spy_close"] = close
        c["spy_next_open"] = next_open
        # The day's move, close over previous close - the number Leron reads as
        # "SPY that day".
        c["spy_day_pct"] = _pct(prev_close, close)
        # Intraday from the open, for a call made during the session.
        c["spy_open_to_close_pct"] = _pct(opn, close)
        # 🚨 The overnight gap. Only meaningful on the last call of the day;
        # attached to every row so the reader can see that for themselves.
        c["spy_overnight_pct"] = _pct(close, next_open)
        c["spy_close_to_next_open_pct"] = c["spy_overnight_pct"]
    out.reverse()                                  # back to newest-first
    return out


def _big_threshold(calls: list[dict]) -> Optional[float]:
    """|day move| at BIG_MOVE_PCTILE across the window, or None if too thin."""
    moves = sorted(abs(c["spy_day_pct"]) for c in calls
                   if c.get("spy_day_pct") is not None)
    if len(moves) < 10:
        return None                                # 🚨 too thin to define "big"
    i = min(len(moves) - 1, int(len(moves) * BIG_MOVE_PCTILE))
    return moves[i]


def score(calls: list[dict]) -> dict:
    """Per-verdict hit rates WITH the base rate over the same days, and n.

    Returns {} when there is not enough to say anything, rather than a
    confident-looking number built on four observations.
    """
    scored = [c for c in calls if c.get("spy_day_pct") is not None]
    if not scored:
        return {}

    big_cut = _big_threshold(scored)
    days = {c["trade_date"]: c["spy_day_pct"] for c in scored}
    n_days = len(days)

    base_up = (sum(1 for v in days.values() if v > 0) / n_days) if n_days else None
    base_big = ((sum(1 for v in days.values() if abs(v) >= big_cut) / n_days)
                if (n_days and big_cut is not None) else None)

    by: dict[str, dict] = {}
    for c in scored:
        v = c["verdict"]
        b = by.setdefault(v, {"verdict": v, "surface": c["surface"], "n": 0,
                              "hits": 0, "kind": None, "moves": []})
        b["n"] += 1
        b["moves"].append(c["spy_day_pct"])
        d = DIRECTIONAL.get(v)
        vol = VOLATILITY.get(v)
        if d:
            b["kind"] = "direction"
            if (d == "up" and c["spy_day_pct"] > 0) or \
               (d == "down" and c["spy_day_pct"] < 0):
                b["hits"] += 1
        elif vol and big_cut is not None:
            b["kind"] = "volatility"
            big = abs(c["spy_day_pct"]) >= big_cut
            if (vol == "big" and big) or (vol == "small" and not big):
                b["hits"] += 1

    out = []
    for b in by.values():
        moves = b.pop("moves")
        b["avg_move_pct"] = round(sum(moves) / len(moves), 3) if moves else None
        b["avg_abs_move_pct"] = (round(sum(abs(m) for m in moves) / len(moves), 3)
                                 if moves else None)
        if b["kind"] and b["n"]:
            b["hit_rate"] = round(b["hits"] / b["n"], 3)
            # 🚨 The comparison, not the number. A 0.55 hit rate against a 0.55
            # base rate is zero information, and without this line it reads as
            # a win.
            b["base_rate"] = round(
                base_up if b["kind"] == "direction" else (base_big or 0), 3)
            b["edge"] = round(b["hit_rate"] - b["base_rate"], 3)
        else:
            b["hit_rate"] = b["base_rate"] = b["edge"] = None
        # 🚨 Say when it is too thin to mean anything, rather than leaving the
        # reader to notice n=3 for themselves.
        b["thin"] = b["n"] < 10
        out.append(b)

    out.sort(key=lambda b: (-(b["n"] or 0), b["verdict"]))
    return {
        "verdicts": out,
        "days": n_days,
        "base_rate_up": round(base_up, 3) if base_up is not None else None,
        "base_rate_big": round(base_big, 3) if base_big is not None else None,
        "big_move_cut_pct": round(big_cut, 3) if big_cut is not None else None,
    }


def disagreements(calls: list[dict]) -> list[dict]:
    """Days where the surfaces did not agree on risk.

    🚨 THIS IS THE INTERESTING ROW. Squeeze and Risk were shown to be the same
    trade - same underlying, same short strike, same entry minute - and
    SQUEEZE_WATCH is a strict subset of the VIX gate. Two signals that always
    agree add nothing by being stacked; the days they SPLIT are the only days
    the second one earned its place.
    """
    risky = {"NO_SELL", "SQUEEZE_WATCH", "stand_down", "skip_entry"}
    calm = {"SELL_PREMIUM", "normal"}

    by_day: dict[str, dict[str, str]] = {}
    for c in sorted(calls, key=lambda c: (c.get("call_ts") or "")):
        d, s = c.get("trade_date"), c.get("surface")
        if d and s:
            by_day.setdefault(d, {})[s] = c["verdict"]   # last of day wins

    out = []
    for d, verdicts in sorted(by_day.items(), reverse=True):
        stances = {s: ("risk-off" if v in risky else
                       "calm" if v in calm else "other")
                   for s, v in verdicts.items()}
        real = {x for x in stances.values() if x != "other"}
        if len(real) > 1:
            out.append({"trade_date": d, "verdicts": verdicts,
                        "stances": stances})
    return out
