"""Minimal TradingVolatility v2 client for TSUNAMI — IV rank only.

Gate G05 requires the LETF's IV rank; per spec the source is TV's
``/tickers/{symbol}/series`` endpoint. This is the only TV call TSUNAMI
makes (underlying GEX comes from the Tradier chain, which was already the
production-proven fallback path in AlphaGEX), so rather than port the full
AlphaGEX TradingVolatilityAPI class this module implements just the one
Bearer-authenticated GET.

Auth: ``TRADING_VOLATILITY_API_TOKEN`` (the v2 Bearer token, sub_xxx
style), falling back to ``TRADING_VOLATILITY_API_KEY`` — per Leron
2026-07-03 that's the name the credential lives under in this
environment. Caution: in AlphaGEX that name historically held the v1
username; if the v2 endpoint rejects it, the 401 is logged and iv_rank
returns None. Unset/invalid → None → G05 fails closed with
INSUFFICIENT_HISTORY, exactly the spec's cold-start behavior.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 60


def _base_url() -> str:
    return (
        os.environ.get("TRADING_VOLATILITY_V2_BASE_URL", "").strip()
        or "https://stocks.tradingvolatility.net/api/v2"
    )


def get_iv_rank(symbol: str) -> Optional[float]:
    """Latest IV rank for ``symbol`` from TV v2 series, or None on failure."""
    token = (
        os.environ.get("TRADING_VOLATILITY_API_TOKEN", "").strip()
        or os.environ.get("TRADING_VOLATILITY_API_KEY", "").strip()
    )
    if not token:
        logger.info(
            "[tv_client] TRADING_VOLATILITY_API_TOKEN / TRADING_VOLATILITY_API_KEY "
            "not set — iv_rank unavailable"
        )
        return None
    try:
        resp = requests.get(
            f"{_base_url().rstrip('/')}/tickers/{symbol}/series",
            params={"metrics": "iv_rank", "window": "5d"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("[tv_client] series %s http %s", symbol, resp.status_code)
            return None
        payload = resp.json()
        data = payload.get("data", payload)
        # Two observed shapes: {"points": [{...,"iv_rank": x}, ...]} and
        # {"series": {"iv_rank": [..]}} — take the most recent non-null.
        points = data.get("points") if isinstance(data, dict) else None
        if isinstance(points, list):
            for pt in reversed(points):
                if isinstance(pt, dict) and pt.get("iv_rank") is not None:
                    return float(pt["iv_rank"])
        series = data.get("series") if isinstance(data, dict) else None
        if isinstance(series, dict):
            for v in reversed(series.get("iv_rank") or []):
                if v is not None:
                    return float(v)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tv_client] iv_rank %s failed: %r", symbol, exc)
        return None
