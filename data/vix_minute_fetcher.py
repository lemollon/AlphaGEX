"""
VIX Minute Data Fetcher - Intraday VIX history via the thetadata-proxy service

Provides REAL intraday/minute-level VIX price history for backtesting. This is
the historical counterpart to data/vix_fetcher.py, which only returns a single
CURRENT spot price for live trading signal generation - that module is NOT
historical and is out of scope here.

Source: thetadata-proxy, an existing Render private service reachable internally
via THETADATA_BASE_URL. Same env-var/HTTP pattern already used by
spreadworks/backend/ember/legacy/tv_scanner.py and
spreadworks/backend/ember/legacy/spike.py:

    THETA = os.getenv("THETADATA_BASE_URL", "http://127.0.0.1:25503").strip().rstrip("/")
    urllib.request.urlopen(f"{THETA}/v3/...")

Confirmed working endpoint: GET /v3/index/history/ohlc?symbol=VIX&start_date=...
&end_date=...&interval=1m&start_time=09:30:00&end_time=16:00:00
CSV columns: timestamp,open,high,low,close,volume,count,vwap

ThetaData Standard-tier subscription serves VIX 1-minute history back to at
least 2022-01-01. Older history requires a Professional-tier subscription and
the proxy returns PERMISSION_DENIED - callers must not assume anything older
than 2022 will work.

Error handling follows data/polygon_data_fetcher.py's convention: missing
configuration raises immediately (programmer error), while a failed/empty
request is logged and returns None (data unavailable). It does NOT follow
vix_fetcher.py's "never raises, always returns a value" pattern - a backtest
that silently substitutes a fake VIX for missing history produces a number
nobody can trust, so this module never invents a default VIX value.
"""

import os
import csv
import io
import logging
import urllib.request
import urllib.error
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class VixMinuteDataError(RuntimeError):
    """Raised when the thetadata-proxy is not configured for historical VIX access."""


def _theta_base_url() -> str:
    """Resolve the thetadata-proxy base URL - same pattern as tv_scanner.py/spike.py."""
    url = os.getenv("THETADATA_BASE_URL", "http://127.0.0.1:25503").strip().rstrip("/")
    if url and "://" not in url:
        url = f"http://{url}"
    return url


def get_vix_minute_history(
    start_date: str,
    end_date: str,
    interval: str = "1m",
    start_time: str = "09:30:00",
    end_time: str = "16:00:00",
    timeout: int = 30,
) -> Optional[pd.DataFrame]:
    """
    Fetch intraday VIX OHLC history from the thetadata-proxy.

    Args:
        start_date: 'YYYY-MM-DD'
        end_date: 'YYYY-MM-DD'
        interval: bar interval accepted by the proxy, e.g. '1m' (default), '5m'
        start_time: session start 'HH:MM:SS'
        end_time: session end 'HH:MM:SS'
        timeout: HTTP timeout in seconds

    Returns:
        DataFrame indexed by timestamp with columns open, high, low, close,
        volume, count, vwap - or None if the request failed or returned no data.
        A backtest MUST check for None; this never returns a fake/default value.

    Raises:
        VixMinuteDataError: if THETADATA_BASE_URL is not configured at all.
    """
    base_url = _theta_base_url()
    if not base_url:
        raise VixMinuteDataError("THETADATA_BASE_URL not configured - cannot fetch historical VIX")

    url = (
        f"{base_url}/v3/index/history/ohlc?symbol=VIX"
        f"&start_date={start_date}&end_date={end_date}"
        f"&interval={interval}&start_time={start_time}&end_time={end_time}"
    )

    try:
        req = urllib.request.Request(url, headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        logger.error(f"thetadata-proxy HTTP {e.code} for VIX {start_date}..{end_date}: {e.reason}")
        return None
    except urllib.error.URLError as e:
        logger.error(f"thetadata-proxy unreachable at {base_url}: {e.reason}")
        return None
    except Exception as e:
        logger.error(f"thetadata-proxy request failed for VIX {start_date}..{end_date}: {e}")
        return None

    if not raw.strip():
        logger.error(f"thetadata-proxy returned an empty response for VIX {start_date}..{end_date}")
        return None

    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        logger.warning(
            f"No VIX {interval} bars for {start_date}..{end_date} - "
            f"check the date range (Standard-tier ThetaData covers ~2022-01-01 onward)"
        )
        return None

    try:
        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for col in ("open", "high", "low", "close", "volume", "count", "vwap"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.set_index("timestamp").sort_index()
    except Exception as e:
        logger.error(f"Failed to parse thetadata-proxy VIX CSV for {start_date}..{end_date}: {e}")
        return None

    logger.info(f"Fetched {len(df)} VIX {interval} bars for {start_date}..{end_date} from thetadata-proxy")
    return df


def get_vix_at_open(start_date: str, end_date: str) -> dict:
    """
    Convenience wrapper: real intraday VIX value in the opening minutes
    (09:30-09:35 ET) for every trading day in range, keyed by date string.

    For 0DTE backtests that currently key VIX off a single DAILY close (e.g.
    yfinance ^VIX) even though the position is entered intraday at the open,
    this gives the actual VIX level at entry instead.

    Returns:
        Dict[str, float] mapping 'YYYY-MM-DD' -> VIX close of the first
        available bar that day. Empty dict if the fetch failed - callers must
        fall back to their existing (lower-fidelity) VIX source, never to a
        hardcoded constant.
    """
    df = get_vix_minute_history(
        start_date, end_date, interval="1m", start_time="09:30:00", end_time="09:35:00"
    )
    if df is None or df.empty:
        return {}

    out: dict = {}
    for ts, row in df.iterrows():
        date_str = ts.strftime("%Y-%m-%d")
        if date_str not in out:
            out[date_str] = float(row["close"])
    return out
