"""Free, keyless funding-rate fallback for the AGAPE perp bots.

CoinGlass is the primary source, but it needs a paid plan; when it returns
nothing the bots lose funding_regime and fall back to degraded
momentum-only trading. Funding itself is public on every perp venue, so this
module reads it straight from exchange APIs, no key required:

  1. Hyperliquid (``/info`` metaAndAssetCtxs) - already used in production by
     trading/shared/perp_realism.py, so it is known reachable from Render.
     Funding is paid hourly.
  2. OKX (``/api/v5/public/funding-rate``) - backup. Funding per its own
     interval (usually 8h).

Rates are returned in CoinGlass units - PERCENT per 8h (0.01 == 0.01%) - so
FundingRate.regime thresholds apply unchanged.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")
OKX_URL = "https://www.okx.com/api/v5/public/funding-rate"
TIMEOUT = 5.0


def _hyperliquid_pct_8h(symbol: str) -> Optional[float]:
    from data.hyperliquid_perp_provider import get_hyperliquid_perp_provider

    market = get_hyperliquid_perp_provider().get_market(symbol.upper())
    if market is None:
        return None
    # Hyperliquid quotes the current HOURLY rate as a decimal.
    return float(market.funding_rate) * 100.0 * 8.0


def _okx_pct_8h(symbol: str) -> Optional[float]:
    resp = requests.get(
        OKX_URL, params={"instId": f"{symbol.upper()}-USDT-SWAP"}, timeout=TIMEOUT
    )
    resp.raise_for_status()
    body = resp.json()
    rows = body.get("data") or []
    if body.get("code") not in ("0", 0) or not rows:
        return None
    row = rows[0]
    rate = row.get("fundingRate")
    if rate in (None, ""):
        return None
    interval_h = 8.0
    try:
        span_ms = int(row["nextFundingTime"]) - int(row["fundingTime"])
        if span_ms > 0:
            interval_h = span_ms / 3_600_000
    except (KeyError, TypeError, ValueError):
        pass
    return float(rate) * 100.0 * (8.0 / interval_h)


SOURCES: List[Tuple[str, Callable[[str], Optional[float]]]] = [
    ("hyperliquid", _hyperliquid_pct_8h),
    ("okx", _okx_pct_8h),
]


def get_free_funding_rate(symbol: str):
    """First available free funding rate as a FundingRate, else None."""
    from data.crypto_data_provider import FundingRate

    for name, fetch in SOURCES:
        try:
            pct_8h = fetch(symbol)
        except Exception as exc:  # noqa: BLE001 - any venue failure -> next venue
            logger.debug(f"free funding: {name} failed for {symbol}: {exc}")
            continue
        if pct_8h is None:
            continue
        return FundingRate(
            symbol=symbol,
            rate=pct_8h,
            predicted_rate=pct_8h,
            exchange=name,
            interval_hours=8,
            annualized_rate=pct_8h * 3 * 365,
            timestamp=datetime.now(CENTRAL_TZ),
        )
    logger.warning(f"free funding: no source returned a rate for {symbol}")
    return None
