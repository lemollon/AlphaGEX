"""Wall Scanner — descriptive-only GEX wall distances (2026-09-11).

CLOSED DECISION, do not relitigate: single-name flow-mix continuation FAILS
placebo (memory `flowmix-singlename-fails.md`, PREREG_FLOWMIX_SINGLENAME).
GEX walls are also not levels — SPY placebo-tested 5x, single names now
tested too, same conclusion. So this module makes NO directional call. It
reports, per ticker: spot, the nearest call wall above spot and put wall
below spot (by |net GEX|), and the $ / % distance to each. That is the
entire feature. If a future signal earns a directional call, it ships as a
separate, explicitly-validated surface — never bolted onto this one.

Data source: TradingVolatility v2 `/tickers/{ticker}/curves/gex_by_strike`
(same base URL + Bearer auth pattern as `tsunami/data/tv_client.py`).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 30

# GME (the research trigger) + the 7 tickers flow-mix continuation was tested
# and failed on. Every ticker here is descriptive-only for the same reason —
# GME inherits that by default, it is not a special case.
TICKERS: list[str] = ["GME", "AMD", "COIN", "NVDA", "MSTR", "PLTR", "SMCI", "TSLA"]


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


def _fetch_gex_by_strike(ticker: str) -> Optional[dict[str, Any]]:
    token = _token()
    if not token:
        logger.info("[wall_scanner] no TV token set — %s unavailable", ticker)
        return None
    try:
        resp = requests.get(
            f"{_base_url().rstrip('/')}/tickers/{ticker}/curves/gex_by_strike",
            params={"exp": "combined"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[wall_scanner] %s http %s", ticker, resp.status_code)
            return None
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[wall_scanner] %s fetch failed: %r", ticker, exc)
        return None


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
    payload = _fetch_gex_by_strike(ticker)
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


def scan_all(tickers: Optional[list[str]] = None) -> list[dict[str, Any]]:
    return [scan_ticker(t) for t in (tickers or TICKERS)]
