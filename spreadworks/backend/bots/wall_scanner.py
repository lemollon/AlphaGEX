"""Wall Scanner — descriptive-only GEX wall distances, MARKET-WIDE (2026-09-11).

CLOSED DECISION, do not relitigate: single-name flow-mix continuation FAILS
placebo (memory `flowmix-singlename-fails.md`, PREREG_FLOWMIX_SINGLENAME).
GEX walls are also not levels — SPY placebo-tested 5x, single names now
tested too, same conclusion. So this module makes NO directional call. It
reports, per ticker: spot, the nearest call wall above spot and put wall
below spot (by |net GEX|), and the $ / % distance to each. That is the
entire feature. If a future signal earns a directional call, it ships as a
separate, explicitly-validated surface — never bolted onto this one.

SCANNER, not a fixed basket (corrected 2026-09-11 — the original 8-ticker
list from the flowmix research was a dashboard, not a scanner). The
universe is TradingVolatility's own `/top-setups` cross-sectional roster:
that endpoint only carries names TV actively snapshots options structure
for, which is itself a liquid/optionable filter — "the whole stock market
that has options and is liquid" as far as any data vendor can define it.
Results are sorted by tightest $ gap to either wall first (the closest
thing to "scan for something notable" this descriptive-only page can do
without making a call).

Data source: TradingVolatility v2 `/top-setups` (universe) and
`/tickers/{ticker}/curves/gex_by_strike` (per-ticker wall data) — same base
URL + Bearer auth pattern as `tsunami/data/tv_client.py`.
"""
from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 20
# TV's documented max for /top-setups.
_UNIVERSE_LIMIT = 200
# Independent per-ticker calls; TV is the constraint here, not our CPU.
_MAX_WORKERS = 20
# A full scan is ~200 sequential-cost HTTP calls even with concurrency — cache
# it rather than pay that on every page load. Same lazy-refresh shape as
# routes_squeeze.py's _INTRADAY_CACHE.
_CACHE_TTL = 300
_cache: dict[str, Any] = {"ts": 0.0, "payload": None}


def _base_url() -> str:
    return (
        os.environ.get("TRADING_VOLATILITY_V2_BASE_URL", "").strip()
        or "https://stocks.tradingvolatility.net/api/v2"
    )


def _token() -> str:
    return (
        os.environ.get("TRADING_VOLATILITY_API_TOKEN", "").strip()
        or os.environ.get("TRADING_VOLATILITY_API_KEY", "").strip()
    )


def _get(path: str, params: dict[str, Any]) -> Optional[dict[str, Any]]:
    token = _token()
    if not token:
        logger.info("[wall_scanner] no TV token set — %s unavailable", path)
        return None
    try:
        resp = requests.get(
            f"{_base_url().rstrip('/')}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[wall_scanner] %s http %s", path, resp.status_code)
            return None
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wall_scanner] %s failed: %r", path, exc)
        return None


def fetch_universe(limit: int = _UNIVERSE_LIMIT) -> list[str]:
    """TV's covered, liquid, optionable universe — the scan target.

    /top-setups returns TV's most recent snapshot per ticker (36h recency
    window); we only want which tickers exist, not the opportunity ranking
    it computes (that's a different, directional feature this page does not
    make). min_score=0 + no other filters pulls the full roster it tracks.
    """
    payload = _get("/top-setups", {"limit": limit, "min_score": 0})
    if payload is None:
        return []
    data = payload.get("data", payload) if isinstance(payload, dict) else None
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        # Silent-empty is the failure mode a 200-with-unexpected-shape produces
        # (e.g. a tier/scope restriction returning an empty/different body
        # instead of an HTTP error) — log what we actually got instead of
        # guessing at the schema a second time.
        logger.warning(
            "[wall_scanner] /top-setups: no items[] found. top-level keys=%r, "
            "data type=%r, sample=%r",
            list(payload.keys()) if isinstance(payload, dict) else type(payload),
            type(data),
            str(payload)[:500],
        )
        return []
    tickers = [it.get("ticker") for it in items if isinstance(it, dict) and it.get("ticker")]
    if not tickers:
        logger.warning("[wall_scanner] /top-setups: items[] present but empty of tickers, len=%d", len(items))
    return sorted(set(tickers))


def _nearest_walls(
    points: list[dict[str, Any]], spot: float
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Nearest call wall above spot, nearest put wall below spot.

    'Wall' = the strike with the largest |net GEX| on that side of spot —
    where dealer positioning currently concentrates, not a predicted
    turning point (see module docstring).
    """
    above = [p for p in points if p.get("strike") is not None and p.get("net") is not None and p["strike"] > spot]
    below = [p for p in points if p.get("strike") is not None and p.get("net") is not None and p["strike"] < spot]
    call_wall = max(above, key=lambda p: p["net"]) if above else None
    put_wall = min(below, key=lambda p: p["net"]) if below else None  # most negative net
    return call_wall, put_wall


def scan_ticker(ticker: str) -> dict[str, Any]:
    payload = _get(f"/tickers/{ticker}/curves/gex_by_strike", {"exp": "combined"})
    if payload is None:
        return {"ticker": ticker, "available": False}

    data = payload.get("data", payload) if isinstance(payload, dict) else None
    points = data.get("points") if isinstance(data, dict) else None
    spot = data.get("price") if isinstance(data, dict) else None
    asof = data.get("asof") if isinstance(data, dict) else None

    if not spot or not points:
        return {"ticker": ticker, "available": False}

    call_wall, put_wall = _nearest_walls(points, spot)

    result: dict[str, Any] = {
        "ticker": ticker,
        "available": True,
        "spot": spot,
        "asof": asof,
    }

    if call_wall is not None:
        dollars = call_wall["strike"] - spot
        result["call_wall"] = {
            "strike": call_wall["strike"],
            "net_gex": call_wall["net"],
            "dollars_to_break": round(dollars, 2),
            "pct_to_break": round(dollars / spot * 100, 2),
        }
    else:
        result["call_wall"] = None

    if put_wall is not None:
        dollars = spot - put_wall["strike"]
        result["put_wall"] = {
            "strike": put_wall["strike"],
            "net_gex": put_wall["net"],
            "dollars_to_break": round(dollars, 2),
            "pct_to_break": round(dollars / spot * 100, 2),
        }
    else:
        result["put_wall"] = None

    return result


def _tightest_pct(row: dict[str, Any]) -> float:
    """Sort key: smallest % distance to EITHER wall. Missing data sorts last."""
    pcts = [
        w["pct_to_break"]
        for w in (row.get("call_wall"), row.get("put_wall"))
        if w is not None
    ]
    return min(pcts) if pcts else float("inf")


def run_scan(limit: int = _UNIVERSE_LIMIT) -> dict[str, Any]:
    """Scan TV's covered universe, sorted tightest-gap-first."""
    started = time.monotonic()
    tickers = fetch_universe(limit)
    if not tickers:
        return {"tickers_scanned": 0, "data": [], "generated_at": None}

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {pool.submit(scan_ticker, t): t for t in tickers}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                logger.warning("[wall_scanner] scan_ticker %s raised: %r", futures[fut], exc)
                results.append({"ticker": futures[fut], "available": False})

    available = [r for r in results if r.get("available")]
    unavailable = [r for r in results if not r.get("available")]
    available.sort(key=_tightest_pct)

    elapsed = round(time.monotonic() - started, 1)
    logger.info(
        "[wall_scanner] scanned %d tickers (%d available) in %ss",
        len(tickers), len(available), elapsed,
    )
    return {
        "tickers_scanned": len(tickers),
        "data": available + unavailable,
        "elapsed_sec": elapsed,
    }


def scan_all(limit: int = _UNIVERSE_LIMIT, force: bool = False) -> dict[str, Any]:
    """Cached market-wide scan — a full pass is ~200 external calls."""
    now = time.monotonic()
    if not force and _cache["payload"] is not None and (now - _cache["ts"]) < _CACHE_TTL:
        return _cache["payload"]

    payload = run_scan(limit)
    _cache["payload"] = payload
    _cache["ts"] = now
    return payload
