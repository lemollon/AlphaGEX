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


# ── Edge-discovery triage (2026-09-11) ──────────────────────────────────
# Five candidates, each a DIFFERENT mechanism from gamma/dealer-hedging
# (gamma-regime-vs-move-size-fails.md already killed that one 3 ways --
# flow continuation, wall proximity, regime sign). Cheap triage per
# edge-discovery skill: rank leads with real-vs-placebo, don't call them
# dead on one look. Same harness (pooled panel, Welch's t, within-ticker
# shuffle placebo) proven on the gamma test, one data pull (all metrics in
# one /series call per ticker), five hypotheses tested against it at once.
_TRIAGE_HYPOTHESES = {
    "put_call_iv_skew": {
        "feature": "put_call_iv_spread",
        "target": "signed",
        "thesis": "Extreme put-over-call IV skew (fear priced into puts) predicts a "
                   "POSITIVE next-day return -- informed/behavioral overreaction unwind "
                   "(published equity-options anomaly; mechanism is options-market "
                   "information asymmetry, NOT dealer gamma hedging).",
        "expect_high_minus_low_sign": "+",
    },
    "put_call_volume_sentiment": {
        "feature": "pcr_volume",
        "target": "signed",
        "thesis": "High put/call VOLUME ratio that day (capitulation-style put buying) "
                   "predicts a POSITIVE next-day return; low ratio (call-heavy, greed) "
                   "predicts negative -- contrarian sentiment, tested single-name rather "
                   "than the usual index-level version.",
        "expect_high_minus_low_sign": "+",
    },
    "iv_rank_fear": {
        "feature": "iv_rank",
        "target": "signed",
        "thesis": "Extreme high IV rank (options expensive vs the stock's own history, "
                   "fear priced in) predicts a POSITIVE next-day return.",
        "expect_high_minus_low_sign": "+",
    },
    "tv_opportunity_score": {
        "feature": "opportunity_score",
        "target": "abs",
        "thesis": "META-TEST: does TV's own composite opportunity_score (0-10, "
                   "direction-agnostic -- a high score can back a short setup too, hence "
                   "testing |return| not signed) actually predict a bigger next-day move? "
                   "If not, the vendor's own ranking is descriptive marketing, not signal.",
        "expect_high_minus_low_sign": "+",
    },
    "momentum_continuation": {
        "feature": "trend_score",
        "target": "signed",
        "thesis": "EXPECTED TO FAIL (included per edge-discovery's 'include the weird "
                   "ones' -- momentum at a 1-day single-stock horizon is dominated by "
                   "short-term REVERSAL in the literature, not continuation). High "
                   "trend_score predicting a positive next-day return would be the "
                   "surprise; the more likely outcome is negative or null.",
        "expect_high_minus_low_sign": "+",
    },
}


@router.get("/_debug/edge-discovery-triage")
async def _debug_edge_discovery_triage(window: str = "2y", min_days: int = 20):
    """TEMPORARY research route (2026-09-11) -- edge-discovery cheap-triage
    pass, five hypotheses (see _TRIAGE_HYPOTHESES), one data pull. Each
    hypothesis: split each ticker's own history into top/bottom terciles of
    its feature, compare mean target (signed or |return|) high vs low tercile,
    Welch's t, real split vs a within-ticker-shuffled placebo -- identical
    discipline to the gamma-regime test (memory
    gamma-regime-vs-move-size-fails.md). This is TRIAGE (rank, don't kill) --
    a weak real-vs-placebo gap still gets reported and reframed before being
    called dead. Remove this route once results are reported and acted on.
    """
    import statistics
    import random

    from .bots.wall_scanner import _get, fetch_universe

    features = sorted({h["feature"] for h in _TRIAGE_HYPOTHESES.values()})
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

    def _run_hypothesis(feature: str, target_kind: str) -> dict:
        # Build per-ticker (feature_t, fwd_return_t) then bucket by that
        # ticker's OWN tercile cutoffs (avoids cross-ticker scale issues).
        rows = []
        for t, points in panels.items():
            fvals = [p.get(feature) for p in points if p.get(feature) is not None]
            if len(fvals) < min_days:
                continue
            lo_cut, hi_cut = _terciles(fvals)
            if lo_cut == hi_cut:
                continue
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
                rows.append({"ticker": t, "bucket": bucket, "target": target})

        def _summarize(sample: list[dict]) -> dict:
            by_bucket: dict[str, list[float]] = {"high": [], "low": []}
            for r in sample:
                by_bucket[r["bucket"]].append(r["target"])
            out = {}
            for k, vals in by_bucket.items():
                out[k] = {
                    "n": len(vals),
                    "mean": round(statistics.mean(vals), 5) if vals else None,
                    "stdev": round(statistics.stdev(vals), 5) if len(vals) > 1 else None,
                }
            hi, lo = out.get("high"), out.get("low")
            t_stat = None
            if hi and lo and hi["n"] > 1 and lo["n"] > 1 and hi["stdev"] and lo["stdev"]:
                se = ((hi["stdev"] ** 2) / hi["n"] + (lo["stdev"] ** 2) / lo["n"]) ** 0.5
                if se > 0:
                    t_stat = round((hi["mean"] - lo["mean"]) / se, 3)
            out["welch_t_high_minus_low"] = t_stat
            return out

        real = _summarize(rows)

        rnd = random.Random(20260911)
        by_ticker: dict[str, list[dict]] = {}
        for r in rows:
            by_ticker.setdefault(r["ticker"], []).append(r)
        placebo_rows = []
        for t, trows in by_ticker.items():
            buckets = [r["bucket"] for r in trows]
            rnd.shuffle(buckets)
            for r, b in zip(trows, buckets):
                placebo_rows.append({**r, "bucket": b})
        placebo = _summarize(placebo_rows)

        return {"n_rows": len(rows), "real": real, "placebo": placebo}

    results = {}
    for name, spec in _TRIAGE_HYPOTHESES.items():
        results[name] = {
            "thesis": spec["thesis"],
            "feature": spec["feature"],
            "target": spec["target"],
            "expected_sign": spec["expect_high_minus_low_sign"],
            **_run_hypothesis(spec["feature"], spec["target"]),
        }

    return {
        "tickers_in_universe": len(tickers),
        "tickers_with_usable_series": len(panels),
        "results": results,
    }
