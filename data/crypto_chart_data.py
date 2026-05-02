"""
Crypto chart data aggregator for AGAPE perpetual dashboards.

Pulls 30 days of h4 history for each perp ticker:
  - Price candles from Coinbase (free, no auth)
  - L/S ratio history from CoinGlass v4 (Binance perp pairs)
  - OI history from CoinGlass v4 (aggregated across exchanges)
  - Funding rate history from CoinGlass v4 (OI-weighted)

All four series are returned with epoch-millisecond timestamps so the
frontend can plot them on a shared X-axis. Five-minute cache keeps the
endpoint snappy and avoids re-hitting CoinGlass on every dashboard load.
"""

import logging
import time
from typing import Dict, List, Optional

import requests

from data.crypto_data_provider import get_crypto_data_provider

logger = logging.getLogger(__name__)

# Map ticker → Coinbase product id for spot price candles
_COINBASE_PRODUCT = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "SHIB": "SHIB-USD",
}

# 5-minute cache per ticker. Charts don't need second-by-second freshness;
# CoinGlass tier limit is the binding constraint.
_CACHE: Dict[str, Dict] = {}
_CACHE_TIME: Dict[str, float] = {}
_CACHE_TTL = 300


def _coinbase_candles(
    ticker: str, granularity_seconds: int = 14400, limit: int = 180
) -> List[Dict]:
    """Fetch price candles from Coinbase Exchange public API.

    h4 = 14400s, returns up to 300 per call. We ask for 180 = 30 days.
    Coinbase response shape: [[time, low, high, open, close, volume], ...]
    Newest first, so we reverse to chronological order.
    """
    product = _COINBASE_PRODUCT.get(ticker.upper())
    if not product:
        return []
    try:
        url = f"https://api.exchange.coinbase.com/products/{product}/candles"
        # Coinbase caps `granularity` to a fixed set; 14400 = h4 is allowed.
        resp = requests.get(
            url,
            params={"granularity": granularity_seconds},
            headers={"User-Agent": "AlphaGEX/1.0"},
            timeout=10,
        )
        if resp.status_code != 200:
            logger.debug(f"Coinbase candles HTTP {resp.status_code} for {product}")
            return []
        rows = resp.json()
        if not isinstance(rows, list):
            return []
        # Reverse to chronological + cap to `limit`
        rows = list(reversed(rows))[-limit:]
        return [
            {
                "time": int(r[0]) * 1000,  # epoch seconds → ms
                "open": float(r[3]),
                "high": float(r[2]),
                "low": float(r[1]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
            for r in rows
            if isinstance(r, list) and len(r) >= 6
        ]
    except (requests.RequestException, ValueError, TypeError) as e:
        logger.warning(f"Coinbase candles fetch failed for {ticker}: {e}")
        return []


def _normalize_time_field(records: List[Dict]) -> List[Dict]:
    """CoinGlass v4 history records have a 'time' field in milliseconds.
    Some endpoints return seconds. Normalize to milliseconds.
    """
    out = []
    for r in records:
        t = r.get("time") or r.get("ts") or r.get("timestamp")
        if t is None:
            continue
        t = int(t)
        # Heuristic: anything < 10^12 is seconds, multiply to ms
        if t < 10**12:
            t *= 1000
        out.append({**r, "time": t})
    return out


def get_chart_data(ticker: str) -> Dict:
    """Assemble 30-day h4 chart data for one perp ticker.

    Returns:
      {
        "ticker": str,
        "price": [{time, open, high, low, close, volume}, ...],
        "ls_ratio": [{time, ratio, long_pct, short_pct}, ...],
        "open_interest": [{time, total_usd}, ...],
        "funding": [{time, rate}, ...],
        "fetched_at": epoch_ms,
        "cache_age_seconds": int,
      }
    """
    ticker_upper = ticker.upper()
    now = time.time()

    cached = _CACHE.get(ticker_upper)
    cached_time = _CACHE_TIME.get(ticker_upper, 0)
    if cached and (now - cached_time) < _CACHE_TTL:
        return {**cached, "cache_age_seconds": int(now - cached_time)}

    provider = get_crypto_data_provider()
    cg = provider._coinglass if provider else None

    # 1. Price candles (Coinbase, free)
    price = _coinbase_candles(ticker_upper)

    # 2-4. CoinGlass histories (rate-limited at the client level)
    ls_raw = cg.get_ls_ratio_history(ticker_upper) if cg else []
    oi_raw = cg.get_oi_history(ticker_upper) if cg else []
    funding_raw = cg.get_funding_rate_history(ticker_upper) if cg else []

    ls_records = _normalize_time_field(ls_raw)
    oi_records = _normalize_time_field(oi_raw)
    funding_records = _normalize_time_field(funding_raw)

    # Project each series to a slim shape the frontend can graph directly
    ls_series = [
        {
            "time": r["time"],
            "ratio": float(r.get("global_account_long_short_ratio", r.get("longShortRatio", 0)) or 0),
            "long_pct": float(r.get("global_account_long_percent", r.get("longAccount", 0)) or 0),
            "short_pct": float(r.get("global_account_short_percent", r.get("shortAccount", 0)) or 0),
        }
        for r in ls_records
        if r.get("global_account_long_short_ratio") is not None
        or r.get("longShortRatio") is not None
    ]

    # OI history field names: typical v4 = "aggregated_open_interest_usd" or "open_interest_usd"
    oi_series = [
        {
            "time": r["time"],
            "total_usd": float(
                r.get("aggregated_open_interest_usd",
                    r.get("open_interest_usd", r.get("openInterestUsd", 0))) or 0
            ),
        }
        for r in oi_records
    ]

    # Funding history field names: typical v4 = "close" or "funding_rate"
    funding_series = [
        {
            "time": r["time"],
            "rate": float(
                r.get("close", r.get("funding_rate", r.get("rate", 0))) or 0
            ),
        }
        for r in funding_records
    ]

    payload = {
        "ticker": ticker_upper,
        "price": price,
        "ls_ratio": ls_series,
        "open_interest": oi_series,
        "funding": funding_series,
        "fetched_at": int(now * 1000),
        "interval": "h4",
        "lookback_days": 30,
    }

    _CACHE[ticker_upper] = payload
    _CACHE_TIME[ticker_upper] = now
    return {**payload, "cache_age_seconds": 0}
