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


@router.get("/_debug/gamma-regime-preregtest")
async def _debug_gamma_regime_preregtest(window: str = "2y", min_days: int = 20):
    """TEMPORARY research route (2026-09-11).

    PRE-REGISTRATION (written before results are seen, per Leron's own
    research discipline -- meltup/PREREG_*.md convention):

    HYPOTHESIS: On days a stock closes with spot > TV's gamma_flip_price
    ("positive gamma"), the NEXT trading day's |return| is smaller than on
    days it closes with spot < flip ("negative gamma") -- i.e. positive
    gamma dampens realized moves, negative gamma amplifies them. This is
    the textbook mechanic behind the (now-removed) PIN-PRONE/AMPLIFIED
    labels; this test checks whether it actually holds, pooled across
    TV's covered universe, instead of asserting it.

    DATA: TV's /tickers/{t}/series (gex_flip, price), which tops out at
    ~125 trading days regardless of window requested (confirmed empirically
    2026-09-11 -- TV's own retention limit, not something we can pull
    around). No existing warehouse data covers single-name gamma/GEX at
    all (backtest-data skill, uv_*.duckdb pilots have no OI/IV). This is a
    SHORT, SINGLE-REGIME window -- one specific 6-month market environment,
    not a multi-year, multi-regime test. A result here is a first-pass
    filter, not a validated edge.

    METHOD: pool (ticker, day) rows across the whole scanned universe.
    regime_t = sign(price_t - gex_flip_t). target = |return from close_t to
    close_{t+1}|. Compare mean target by regime (Welch's t-test, no scipy
    dependency -- computed by hand). PLACEBO: the same comparison with
    regime labels randomly shuffled within each ticker (fixed seed) --
    if the real split and the placebo split produce similarly-sized gaps,
    there is nothing here.

    Remove this route once the result is reported and acted on.
    """
    import random
    import statistics

    from .bots.wall_scanner import _get, fetch_universe

    tickers = fetch_universe()
    rows: list[dict] = []  # {ticker, regime, target}
    per_ticker_series: dict[str, list[dict]] = {}

    for t in tickers:
        payload = _get(f"/tickers/{t}/series", {"metrics": "gex_flip,price", "window": window})
        if payload is None:
            continue
        data = payload.get("data", payload) if isinstance(payload, dict) else None
        points = data.get("points") if isinstance(data, dict) else None
        if not isinstance(points, list) or len(points) < min_days:
            continue
        points = sorted(points, key=lambda p: p.get("date", ""))
        per_ticker_series[t] = points
        for i in range(len(points) - 1):
            p0, p1 = points[i], points[i + 1]
            price0, flip0, price1 = p0.get("price"), p0.get("gex_flip"), p1.get("price")
            if price0 is None or flip0 is None or price1 is None or price0 == 0:
                continue
            regime = "positive" if price0 > flip0 else ("negative" if price0 < flip0 else None)
            if regime is None:
                continue
            target = abs((price1 - price0) / price0)
            rows.append({"ticker": t, "date": p0.get("date"), "regime": regime, "target": target})

    def _summarize(sample: list[dict]) -> dict:
        by_regime: dict[str, list[float]] = {"positive": [], "negative": []}
        for r in sample:
            by_regime[r["regime"]].append(r["target"])
        out = {}
        for k, vals in by_regime.items():
            out[k] = {
                "n": len(vals),
                "mean_abs_return": round(statistics.mean(vals), 5) if vals else None,
                "stdev": round(statistics.stdev(vals), 5) if len(vals) > 1 else None,
            }
        pos, neg = out.get("positive"), out.get("negative")
        t_stat = None
        if pos and neg and pos["n"] > 1 and neg["n"] > 1 and pos["stdev"] and neg["stdev"]:
            se = ((pos["stdev"] ** 2) / pos["n"] + (neg["stdev"] ** 2) / neg["n"]) ** 0.5
            if se > 0:
                t_stat = round((pos["mean_abs_return"] - neg["mean_abs_return"]) / se, 3)
        out["welch_t_pos_minus_neg"] = t_stat
        return out

    real = _summarize(rows)

    # Placebo: shuffle regime labels within each ticker (breaks the true
    # correspondence between a day's actual regime and its forward return,
    # while preserving each ticker's own regime/return marginal distributions).
    rnd = random.Random(20260911)
    by_ticker: dict[str, list[dict]] = {}
    for r in rows:
        by_ticker.setdefault(r["ticker"], []).append(r)
    placebo_rows: list[dict] = []
    for t, trows in by_ticker.items():
        regimes = [r["regime"] for r in trows]
        rnd.shuffle(regimes)
        for r, shuffled_regime in zip(trows, regimes):
            placebo_rows.append({**r, "regime": shuffled_regime})
    placebo = _summarize(placebo_rows)

    return {
        "window_requested": window,
        "tickers_in_universe": len(tickers),
        "tickers_with_usable_series": len(per_ticker_series),
        "n_ticker_days": len(rows),
        "real": real,
        "placebo": placebo,
        "note": "welch_t_pos_minus_neg compares mean |forward return| in positive- vs "
                "negative-gamma days. Hypothesis predicts NEGATIVE t (positive gamma "
                "-> smaller moves). Compare 'real' t against 'placebo' t: if they look "
                "similar, the real split isn't doing anything the shuffle doesn't.",
    }
