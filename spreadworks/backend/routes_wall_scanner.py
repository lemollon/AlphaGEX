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


# ── Edge-discovery round 3 (2026-09-11) — straight to held-out, no triage ─
# Round 1 (gamma regime) and round 2 (5-hypothesis triage) both died; the
# one triage survivor died on a genuine train/test split. Going straight to
# the strict version this time -- tercile cutoffs fit on the first 70% of
# each ticker's history, real-vs-placebo significance tested ONLY on the
# last 30% -- for three genuinely new mechanisms, none of them gamma
# regime/wall-proximity again (see gamma-regime-vs-move-size-fails.md,
# single-name-edge-discovery-2026-09-11-hunted-dry.md):
#   1. put_call_ratio_oi_30day_change -- the CHANGE in options positioning
#      over the last month (flow of sentiment, not a snapshot level).
#   2. speculative_interest_score -- TV's own crowding/hype measure;
#      thesis is FROTH REVERSION (crowded names underperform after), a
#      documented behavioral effect distinct from anything tried so far.
#   3. gex_volume_ratio -- gamma exposure relative to real trading volume;
#      thesis is that a high ratio means dealer hedging has outsized price
#      impact per dollar actually traded (amplification via thin real flow,
#      not just gamma sign).
# Remove this route once the result is reported and acted on.
_ROUND3_HYPOTHESES = {
    "positioning_shift": {
        "feature": "put_call_ratio_oi_30day_change",
        "target_kind": "signed",
        "thesis": "A large recent INCREASE in put OI relative to calls (fresh "
                  "bearish positioning building) predicts a NEGATIVE next-day "
                  "return -- informed flow continuing, not a one-day snapshot.",
    },
    "speculative_froth": {
        "feature": "speculative_interest_score",
        "target_kind": "signed",
        "thesis": "High TV speculative_interest_score (crowded/hyped options "
                  "activity) predicts a NEGATIVE next-day return -- froth/crowding "
                  "reversion, a documented behavioral effect.",
    },
    "gamma_vs_volume": {
        "feature": "gex_volume_ratio",
        "target_kind": "abs",
        "thesis": "High gamma-to-real-volume ratio means dealer hedging can move "
                  "price more per dollar of actual trading -- predicts a BIGGER "
                  "next-day |return| (tested as abs, direction-agnostic).",
    },
}


@router.get("/_debug/edge-discovery-round3")
async def _debug_edge_discovery_round3(window: str = "2y", min_days: int = 30, train_frac: float = 0.7):
    import statistics
    import random

    from .bots.wall_scanner import _get, fetch_universe

    features = sorted({h["feature"] for h in _ROUND3_HYPOTHESES.values()})
    metrics_param = ",".join(["price"] + features)

    tickers = fetch_universe()
    panels: dict[str, list[dict]] = {}
    for t in tickers:
        payload = _get(f"/tickers/{t}/series", {"metrics": metrics_param, "window": window})
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

    def _bucket_rows(points: list[dict], feature: str, target_kind: str, lo_cut: float, hi_cut: float) -> list[dict]:
        out = []
        for i in range(len(points) - 1):
            p0, p1 = points[i], points[i + 1]
            f0, price0, price1 = p0.get(feature), p0.get("price"), p1.get("price")
            if f0 is None or price0 is None or price1 is None or price0 == 0:
                continue
            if f0 >= hi_cut:
                bucket = "high"
            elif f0 <= lo_cut:
                bucket = "low"
            else:
                continue
            ret = (price1 - price0) / price0
            target = ret if target_kind == "signed" else abs(ret)
            out.append({"bucket": bucket, "target": target})
        return out

    def _summarize(sample: list[dict]) -> dict:
        by_bucket: dict[str, list[float]] = {"high": [], "low": []}
        for r in sample:
            by_bucket[r["bucket"]].append(r["target"])
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
        return out

    def _run(feature: str, target_kind: str) -> dict:
        test_rows_by_ticker: dict[str, list[dict]] = {}
        for t, points in panels.items():
            split_i = int(len(points) * train_frac)
            train_points, test_points = points[:split_i], points[split_i:]
            train_fvals = [p.get(feature) for p in train_points if p.get(feature) is not None]
            if len(train_fvals) < min_days // 2:
                continue
            lo_cut, hi_cut = _terciles(train_fvals)
            if lo_cut == hi_cut:
                continue
            rows = _bucket_rows(test_points, feature, target_kind, lo_cut, hi_cut)
            if rows:
                test_rows_by_ticker[t] = rows

        all_rows = [{"ticker": t, **r} for t, rows in test_rows_by_ticker.items() for r in rows]
        held_out = _summarize(all_rows)

        rnd = random.Random(20260911)
        placebo_rows = []
        for t, rows in test_rows_by_ticker.items():
            buckets = [r["bucket"] for r in rows]
            rnd.shuffle(buckets)
            for r, b in zip(rows, buckets):
                placebo_rows.append({**r, "bucket": b})
        held_out_placebo = _summarize(placebo_rows)

        return {
            "n_tickers_used": len(test_rows_by_ticker),
            "n_test_rows": len(all_rows),
            "held_out_test": held_out,
            "held_out_placebo": held_out_placebo,
        }

    results = {}
    for name, spec in _ROUND3_HYPOTHESES.items():
        target_kind = "abs" if "abs" in spec["thesis"].lower().split("tested as ")[-1][:5] else "signed"
        results[name] = {
            "thesis": spec["thesis"],
            "feature": spec["feature"],
            **_run(spec["feature"], target_kind),
        }

    return {
        "tickers_in_universe": len(tickers),
        "tickers_with_usable_series": len(panels),
        "train_frac": train_frac,
        "results": results,
    }
