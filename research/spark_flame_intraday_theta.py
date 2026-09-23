#!/usr/bin/env python3
"""
Research-only Spark/Flame intraday backtest using ThetaData historical option quotes.

No broker/order code. No IronForge customer writes. Emits JSONL to stdout.
Strategy definitions mirror current IronForge Customer EBB settings:
  SPARK 10:05 CT, 0DTE SPY put credit spread, short ~spot-2, $5 wing
  FLAME 13:05 CT, 0DTE SPY put credit spread, short ~spot-1, $2 wing

Entry fill = short bid - long ask.
Settlement proxy = 14:59 CT parity-derived SPY spot and intrinsic spread value.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import date, datetime, timedelta
from statistics import median
from typing import Iterable

import requests

CT_TO_ET_HOURS = 1
THETA = os.getenv("THETADATA_BASE_URL", "http://thetadata-proxy:10000").strip().rstrip("/")
TIMEOUT = int(os.getenv("THETA_TIMEOUT_SECONDS", "90"))

CONFIGS = {
    "spark": {"entry_ct": "10:05:00", "otm": 2.0, "width": 5.0, "min_credit": 0.10},
    "flame": {"entry_ct": "13:05:00", "otm": 1.0, "width": 2.0, "min_credit": 0.10},
}


def get_csv(path: str, params: dict[str, str]) -> list[dict[str, str]]:
    url = f"{THETA}{path}"
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def weekdays(start: date, end: date) -> Iterable[date]:
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def to_et(ct_hms: str) -> str:
    h, m, s = map(int, ct_hms.split(":"))
    h += CT_TO_ET_HOURS
    return f"{h:02d}:{m:02d}:{s:02d}"


def f(row: dict[str, str], key: str) -> float | None:
    try:
        x = float(row.get(key, ""))
        return x if x == x else None
    except Exception:
        return None


def normalize_right(v: str) -> str:
    x = (v or "").strip().lower()
    if x in {"p", "put"}:
        return "put"
    if x in {"c", "call"}:
        return "call"
    return x


def parity_spot(rows: list[dict[str, str]]) -> float | None:
    by = {}
    for r in rows:
        strike = f(r, "strike")
        bid = f(r, "bid")
        ask = f(r, "ask")
        right = normalize_right(r.get("right", ""))
        if strike is None or bid is None or ask is None or bid <= 0 or ask <= 0:
            continue
        by.setdefault(strike, {})[right] = (bid + ask) / 2.0
    vals = []
    for strike, q in by.items():
        if "call" in q and "put" in q:
            vals.append(strike + q["call"] - q["put"])
    return median(vals) if vals else None


def put_quote(rows: list[dict[str, str]], strike: float) -> tuple[float, float] | None:
    best = None
    best_dist = 1e9
    for r in rows:
        if normalize_right(r.get("right", "")) != "put":
            continue
        k = f(r, "strike")
        bid = f(r, "bid")
        ask = f(r, "ask")
        if k is None or bid is None or ask is None or bid < 0 or ask <= 0:
            continue
        dist = abs(k - strike)
        if dist < best_dist:
            best_dist = dist
            best = (bid, ask, k)
    if best is None or best_dist > 0.01:
        return None
    return best[0], best[1]


def option_snapshot(day: date, hms_et: str) -> list[dict[str, str]]:
    ymd = day.strftime("%Y%m%d")
    return get_csv("/v3/option/history/quote", {
        "symbol": "SPY",
        "expiration": ymd,
        "strike": "*",
        "right": "both",
        "date": ymd,
        "interval": "1m",
        "start_time": hms_et,
        "end_time": hms_et,
    })


def run_day(day: date, bot: str) -> dict:
    cfg = CONFIGS[bot]
    entry_rows = option_snapshot(day, to_et(cfg["entry_ct"]))
    settle_rows = option_snapshot(day, "15:59:00")
    entry_spot = parity_spot(entry_rows)
    settle_spot = parity_spot(settle_rows)
    out = {
        "bot": bot,
        "date": day.isoformat(),
        "entry_ct": cfg["entry_ct"],
        "entry_spot": entry_spot,
        "settle_spot": settle_spot,
        "status": "skip",
    }
    if entry_spot is None or settle_spot is None:
        out["reason"] = "missing_parity_spot"
        return out

    short = round(entry_spot - cfg["otm"])
    long = short - cfg["width"]
    sq = put_quote(entry_rows, short)
    lq = put_quote(entry_rows, long)
    out.update({"short": short, "long": long})
    if not sq or not lq:
        out["reason"] = "missing_leg_quote"
        return out

    credit = sq[0] - lq[1]
    out.update({
        "short_bid": sq[0],
        "long_ask": lq[1],
        "credit": credit,
    })
    if credit < cfg["min_credit"]:
        out["reason"] = "credit_low"
        return out

    settle_value = min(max(short - settle_spot, 0.0), cfg["width"])
    pnl = (credit - settle_value) * 100.0
    out.update({
        "status": "trade",
        "settle_value": settle_value,
        "pnl_per_lot": pnl,
    })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--bots", default="spark,flame")
    args = ap.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    bots = [x.strip().lower() for x in args.bots.split(",") if x.strip()]
    for d in weekdays(start, end):
        for bot in bots:
            try:
                rec = run_day(d, bot)
            except requests.HTTPError as e:
                rec = {"bot": bot, "date": d.isoformat(), "status": "error", "reason": f"http_{e.response.status_code}"}
            except Exception as e:
                rec = {"bot": bot, "date": d.isoformat(), "status": "error", "reason": type(e).__name__}
            print(json.dumps(rec, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
