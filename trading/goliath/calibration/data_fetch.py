"""Data fetching with parquet caching for GOLIATH Phase 1.5 calibration.

Two upstream sources:
    1. Trading Volatility v2 /series — historical scalar GEX metrics per
       underlying. Accessed via the public method
       ``TradingVolatilityAPI.get_historical_gamma(symbol, days_back)`` which
       internally pulls ``[price, gex_flip, gex_usd_per_1_pct_move, pcr_oi,
       iv_rank, atm_iv]`` and returns parsed per-day dicts.
    2. yfinance — daily OHLC for both underlyings AND LETFs (TV does not
       carry GEX for LETF tickers, but we need LETF prices to compute the
       observed leverage ratio that drives drag/tracking-error calibration).

Cache layout: ``.goliath_cache/{ticker}_{kind}_{YYYY-MM-DD}.parquet`` with
per-day invalidation. Re-runs same day reuse cached frames; a new day
forces a fresh fetch.

This module is the only one in the calibration package that touches
the network. Metric modules (wall_concentration / tracking_error /
vol_drag / vol_window) consume DataFrames produced here and never call
TV or yfinance directly. That isolation makes the metric modules unit-
testable with synthetic inputs.
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

# Repo root on sys.path so `from core_classes_and_engines import ...` works
# regardless of how the calling script invokes this module.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# --- Universe ---------------------------------------------------------------

# 5 LETF -> underlying pairs per the recovery doc. All current LETFs are 2x.
LETF_PAIRS: Dict[str, str] = {
    "MSTU": "MSTR",
    "TSLL": "TSLA",
    "NVDL": "NVDA",
    "CONL": "COIN",
    "AMDL": "AMD",
}

# Spec default lookback for Phase 1.5 calibration.
LOOKBACK_DAYS = 90


# --- Cache helpers ----------------------------------------------------------

CACHE_DIR = Path(".goliath_cache")


def _cache_path(ticker: str, kind: str) -> Path:
    """Return the parquet cache path for (ticker, kind) on today's date.

    Different `kind` values for the same ticker get separate cache files,
    so e.g. price history and GEX history for MSTR don't collide.
    """
    today = date.today().isoformat()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{ticker}_{kind}_{today}.parquet"


def _load_cache(path: Path) -> Optional[pd.DataFrame]:
    """Return cached frame if path exists and is readable, else None.
    Never raises — corrupt cache files just trigger a refetch.
    """
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path)
    except Exception as exc:
        print(f"  [cache] read failed for {path.name}: {exc!r} — refetching")
        return None


def _save_cache(path: Path, df: pd.DataFrame) -> None:
    """Best-effort parquet write. Never raises — failed cache writes just
    mean the next call will refetch."""
    if df is None or df.empty:
        return
    try:
        df.to_parquet(path)
    except Exception as exc:
        print(f"  [cache] write failed for {path.name}: {exc!r}")


# --- Public fetchers --------------------------------------------------------

def fetch_gex_history(underlying: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Fetch historical GEX metrics for an underlying ticker via TV v2 /series.

    Uses the public ``TradingVolatilityAPI.get_historical_gamma`` method
    (not the underscore-prefixed ``_v2_series``), which already parses the
    nested v2 response into per-day dicts.

    Returns a DataFrame indexed by datetime with columns:
        price, gex_flip, net_gex, pcr_oi, iv_rank, atm_iv,
        plus ``put_call_ratio_open_interest`` and ``implied_volatility``
        which are aliases the public method emits for v1 caller compat.

    Empty DataFrame on any failure (TV unreachable, no token, ticker
    unsupported, etc.). Caller is responsible for treating empty as a
    [GOLIATH-BLOCKED] signal per the universe failure rule.
    """
    cache = _cache_path(underlying, f"gex_history_{days}d")
    cached = _load_cache(cache)
    if cached is not None:
        return cached

    try:
        from core_classes_and_engines import TradingVolatilityAPI  # type: ignore
    except ImportError as exc:
        print(f"  [data_fetch] cannot import TradingVolatilityAPI: {exc!r}")
        return pd.DataFrame()

    client = TradingVolatilityAPI()
    rows = client.get_historical_gamma(underlying, days_back=days)
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()

    _save_cache(cache, df)
    return df


def fetch_price_history(ticker: str, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Fetch daily auto-adjusted OHLC from yfinance.

    Used for both underlyings AND LETFs. The ``days + 30`` buffer covers
    weekends/holidays so a 90-day lookback reliably yields ~90 trading days.

    Returns a DataFrame indexed by tz-naive datetime with the standard
    yfinance columns (Open, High, Low, Close, Volume). Empty DataFrame on
    any failure.
    """
    cache = _cache_path(ticker, f"price_{days}d")
    cached = _load_cache(cache)
    if cached is not None:
        return cached

    try:
        import yfinance as yf  # type: ignore
    except ImportError as exc:
        print(f"  [data_fetch] yfinance unavailable: {exc!r}")
        return pd.DataFrame()

    end = date.today()
    start = end - timedelta(days=days + 30)

    try:
        df = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            actions=False,
        )
    except Exception as exc:
        print(f"  [data_fetch] yfinance fetch failed for {ticker}: {exc!r}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # yfinance returns tz-aware index; strip tz so parquet round-trips cleanly.
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    _save_cache(cache, df)
    return df


def fetch_all_universe(
    days: int = LOOKBACK_DAYS,
    pairs: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, pd.DataFrame], Dict[str, pd.DataFrame]]:
    """Fetch GEX history (TV) for all underlyings + price history (yfinance)
    for all underlyings AND LETFs.

    Returns
    -------
    gex_history : dict[str, pd.DataFrame]
        Keyed by underlying ticker (MSTR, TSLA, ...). Each value is the
        TV /series response as a date-indexed DataFrame.
    price_history : dict[str, pd.DataFrame]
        Keyed by both underlying and LETF tickers. Each value is the yfinance
        OHLC frame, date-indexed.

    Both dicts may contain empty DataFrames for tickers where the upstream
    fetch failed; the caller decides how to surface that.
    """
    if pairs is None:
        pairs = LETF_PAIRS

    gex_history: Dict[str, pd.DataFrame] = {}
    price_history: Dict[str, pd.DataFrame] = {}

    for letf, underlying in pairs.items():
        gex_history[underlying] = fetch_gex_history(underlying, days=days)
        price_history[underlying] = fetch_price_history(underlying, days=days)
        price_history[letf] = fetch_price_history(letf, days=days)

    return gex_history, price_history
