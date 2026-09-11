"""Wall Scanner API: /api/spreadworks/wall-scanner

DESCRIPTIVE ONLY — $ to break, $ gap, % gap to the nearest call/put GEX wall,
scanned across TradingVolatility's covered universe (liquid, optionable
names — see `backend/bots/wall_scanner.py` module docstring for why that's
the market-wide filter, not a fixed basket). Sorted tightest-gap-first.
NO directional fade/breakout call anywhere in this surface, by design: see
memory `flowmix-singlename-fails.md`. This is not re-litigated here.

Also serves the closest wall's OI/GEX 1h delta (composed here from the
history table — see attach_history_deltas) and a full intraday+multi-day
history series per ticker for charting (`/{ticker}/history`). History only
exists from whenever the scheduled capture job (backend/__init__.py,
`wall_scanner_capture`) started running — a fresh deploy has none yet.

Read-only; import-guarded in `backend/__init__.py` like the other advisory
surfaces (Squeeze, Risk, Book Risk) so a TradingVolatility outage never
takes down the API. A full scan is a cached ~100-call pass (see
`_CACHE_TTL` in the bot module) — do not add a way to force it on every
request without a cache-bust guard.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .bots.wall_scanner import (
    attach_history_deltas,
    scan_all,
    scan_ticker,
    wall_history_series,
)
from .db import engine as _engine

router = APIRouter(prefix="/api/spreadworks/wall-scanner", tags=["Wall Scanner"])


@router.get("")
async def get_wall_scanner():
    result = scan_all()
    data = result.get("data", [])
    attach_history_deltas(_engine, data)
    return {
        "tickers_scanned": result.get("tickers_scanned", 0),
        "data": data,
        "elapsed_sec": result.get("elapsed_sec"),
        "descriptive_only": True,
    }


@router.get("/{ticker}")
async def get_wall_scanner_ticker(ticker: str):
    row = scan_ticker(ticker.upper())
    attach_history_deltas(_engine, [row])
    return {"data": row, "descriptive_only": True}


@router.get("/{ticker}/history")
async def get_wall_scanner_history(
    ticker: str,
    side: str = Query(..., pattern="^(call|put)$"),
    strike: float = Query(...),
    days: int = Query(5, ge=1, le=30),
):
    series = wall_history_series(_engine, ticker.upper(), side, strike, days_back=days)
    return {"ticker": ticker.upper(), "side": side, "strike": strike, "days": days, "series": series}


# ── quant-edge confirmation: 1-day trend_score reversal (2026-09-11) ────
# Survivor from the edge-discovery triage (5 hypotheses; this was the only
# one where real (t=-3.06) diverged from placebo (t=+0.34) -- see memory
# gamma-regime-vs-move-size-fails.md for the 4 that died and the sibling
# writeup this test confirms/refutes. This route runs the quant-edge
# gauntlet the triage did NOT: a genuine chronological train/test split
# (tercile cutoffs fit on train only, significance tested on unseen test
# days only -- the triage tested on the same data it discovered on, which
# is exactly the multiplicity/overfitting risk this route exists to rule
# out) plus a fee-hurdle check and a market-wide-vs-idiosyncratic check.
# Remove this route once the result is reported and acted on.
@router.get("/_debug/quant-edge-confirm-reversal")
async def _debug_quant_edge_confirm_reversal(
    window: str = "2y", min_days: int = 30, train_frac: float = 0.7, round_trip_bps: float = 15.0
):
    import statistics
    import random

    from .bots.wall_scanner import _get, fetch_universe

    tickers = fetch_universe()
    panels: dict[str, list[dict]] = {}
    for t in tickers:
        payload = _get(f"/tickers/{t}/series", {"metrics": "price,trend_score", "window": window})
        if payload is None:
            continue
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        points = data.get("points") if isinstance(data, dict) else None
        if not isinstance(points, list) or len(points) < min_days:
            continue
        panels[t] = sorted(points, key=lambda p: p.get("date", ""))

    def _terciles(vals: list[float]) -> tuple[float, float]:
        s = sorted(vals)
        n = len(s)
        return s[n // 3], s[(2 * n) // 3]

    def _bucket_rows(points: list[dict], lo_cut: float, hi_cut: float) -> list[dict]:
        out = []
        for i in range(len(points) - 1):
            p0, p1 = points[i], points[i + 1]
            f0, price0, price1 = p0.get("trend_score"), p0.get("price"), p1.get("price")
            if f0 is None or price0 is None or price1 is None or price0 == 0:
                continue
            if f0 >= hi_cut:
                bucket = "high"
            elif f0 <= lo_cut:
                bucket = "low"
            else:
                continue
            out.append({"date": p0.get("date"), "bucket": bucket, "ret": (price1 - price0) / price0})
        return out

    train_rows_by_ticker: dict[str, list[dict]] = {}
    test_rows: list[dict] = []
    market_wide_rows: list[dict] = []  # {date, bucket, ret} pooled, for the day-clustering check

    for t, points in panels.items():
        split_i = int(len(points) * train_frac)
        train_points, test_points = points[:split_i], points[split_i:]
        train_fvals = [p.get("trend_score") for p in train_points if p.get("trend_score") is not None]
        if len(train_fvals) < min_days // 2:
            continue
        lo_cut, hi_cut = _terciles(train_fvals)
        if lo_cut == hi_cut:
            continue
        # In-sample (train) reference -- same statistic the triage reported, on this ticker's train slice only.
        train_rows_by_ticker[t] = _bucket_rows(train_points, lo_cut, hi_cut)
        # Held-out: cutoffs fit on TRAIN, bucketing + returns computed on TEST days never used to fit anything.
        for r in _bucket_rows(test_points, lo_cut, hi_cut):
            test_rows.append({"ticker": t, **r})
            market_wide_rows.append(r)

    def _summarize(sample: list[dict]) -> dict:
        by_bucket: dict[str, list[float]] = {"high": [], "low": []}
        for r in sample:
            by_bucket[r["bucket"]].append(r["ret"])
        out = {}
        for k, vals in by_bucket.items():
            out[k] = {
                "n": len(vals),
                "mean_pct": round(statistics.mean(vals) * 100, 4) if vals else None,
                "stdev": round(statistics.stdev(vals), 5) if len(vals) > 1 else None,
            }
        hi, lo = out.get("high"), out.get("low")
        t_stat = None
        if hi and lo and hi["n"] > 1 and lo["n"] > 1 and hi["stdev"] and lo["stdev"]:
            se = ((hi["stdev"] ** 2) / hi["n"] + (lo["stdev"] ** 2) / lo["n"]) ** 0.5
            if se > 0:
                t_stat = round(((hi["mean_pct"] - lo["mean_pct"]) / 100) / se, 3)
        out["welch_t_high_minus_low"] = t_stat
        out["gross_spread_pct"] = round((hi["mean_pct"] - lo["mean_pct"]), 4) if hi and lo else None
        return out

    held_out = _summarize(test_rows)

    # Placebo on the held-out set: shuffle bucket labels within ticker, same as before.
    rnd = random.Random(20260911)
    by_ticker: dict[str, list[dict]] = {}
    for r in test_rows:
        by_ticker.setdefault(r["ticker"], []).append(r)
    placebo_rows = []
    for t, trows in by_ticker.items():
        buckets = [r["bucket"] for r in trows]
        rnd.shuffle(buckets)
        for r, b in zip(trows, buckets):
            placebo_rows.append({**r, "bucket": b})
    held_out_placebo = _summarize(placebo_rows)

    # Day-clustering check: is "high" mostly the SAME calendar days across
    # tickers (-> this is a market-wide move, not stock-specific), or spread
    # across different days per ticker (-> idiosyncratic, actually a
    # cross-sectional stock-picking signal)? Report the top 5 most common
    # dates in the "high" bucket and what fraction of high-bucket rows they
    # cover -- if a handful of dates dominate, the "spread" is largely one
    # or two market-wide events, not a repeatable per-stock effect.
    high_dates = [r["date"] for r in test_rows if r["bucket"] == "high"]
    date_counts: dict[str, int] = {}
    for d in high_dates:
        date_counts[d] = date_counts.get(d, 0) + 1
    top_dates = sorted(date_counts.items(), key=lambda kv: -kv[1])[:5]
    top5_share = round(sum(c for _, c in top_dates) / len(high_dates), 3) if high_dates else None

    gross_spread = held_out.get("gross_spread_pct")
    fee_hurdle_pct = round_trip_bps / 100.0  # e.g. 15bps = 0.15%
    survives_fees = gross_spread is not None and abs(gross_spread) > fee_hurdle_pct

    return {
        "tickers_in_universe": len(tickers),
        "tickers_with_usable_series": len(panels),
        "train_frac": train_frac,
        "held_out_test": held_out,
        "held_out_placebo": held_out_placebo,
        "day_clustering_check": {
            "n_high_bucket_rows": len(high_dates),
            "n_distinct_dates": len(date_counts),
            "top5_dates_by_count": top_dates,
            "top5_share_of_high_bucket": top5_share,
            "note": "If top5_share is large (e.g. >0.3-0.4 for ~35 test days/ticker), "
                    "the 'high' bucket is dominated by a few market-wide days, not a "
                    "repeatable per-stock signal.",
        },
        "fee_hurdle": {
            "round_trip_bps_assumed": round_trip_bps,
            "gross_spread_pct_high_minus_low": gross_spread,
            "survives_assumed_fee": survives_fees,
            "note": "Gross spread is high-bucket minus low-bucket mean return, both "
                    "legs would need trading (long low, short high, or vice versa) "
                    "-- so the ROUND TRIP cost applies to the SPREAD, not each leg "
                    "separately; this is a simplification worth revisiting before sizing.",
        },
    }
