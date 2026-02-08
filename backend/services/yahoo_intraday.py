"""
Yahoo Finance Intraday Tick Fetcher

Fetches 1-minute candle data from Yahoo Finance for trade analysis.
Used by the bot report generator to get price action during trades.

Author: AlphaGEX
Date: January 2025
"""

import logging
import time as time_module
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Any, Union
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Timezones
CENTRAL_TZ = ZoneInfo("America/Chicago")
EASTERN_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

# Try to import yfinance - graceful fallback if not available
try:
    import yfinance as yf
    import pandas as pd
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    yf = None
    pd = None
    logger.warning("yfinance not installed - Yahoo Finance features disabled")

# Symbol mapping for each bot
BOT_SYMBOLS = {
    'fortress': 'SPY',      # FORTRESS trades SPY
    'solomon': 'SPY',    # SOLOMON trades SPY
    'icarus': 'SPY',    # ICARUS trades SPY
    'samson': '^SPX',    # SAMSON trades SPX (use ^GSPC as backup)
    'pegasus': '^SPX',  # PEGASUS trades SPX
}

# Rate limiting - Yahoo can block if too many requests
_last_request_time = 0
_MIN_REQUEST_INTERVAL = 0.5  # seconds between requests


def _rate_limit():
    """Enforce rate limiting between Yahoo requests."""
    global _last_request_time
    now = time_module.time()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time_module.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time_module.time()


def _parse_datetime(dt: Union[str, datetime, None]) -> Optional[datetime]:
    """
    Parse a datetime from various formats into timezone-aware datetime.

    Handles:
    - ISO format strings (with or without timezone)
    - datetime objects (naive or aware)
    - None (returns None)

    Returns datetime in Central Time.
    """
    if dt is None:
        return None

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            # Assume naive datetimes are Central Time
            return dt.replace(tzinfo=CENTRAL_TZ)
        else:
            return dt.astimezone(CENTRAL_TZ)

    if isinstance(dt, str):
        try:
            # Handle various ISO formats
            dt_str = dt.strip()

            # Handle 'Z' suffix (UTC)
            if dt_str.endswith('Z'):
                dt_str = dt_str[:-1] + '+00:00'

            # Try parsing with fromisoformat
            parsed = datetime.fromisoformat(dt_str)

            if parsed.tzinfo is None:
                # Assume Central Time for naive strings
                parsed = parsed.replace(tzinfo=CENTRAL_TZ)

            return parsed.astimezone(CENTRAL_TZ)

        except ValueError as e:
            logger.warning(f"Could not parse datetime '{dt}': {e}")
            return None

    logger.warning(f"Unexpected datetime type: {type(dt)}")
    return None


def _normalize_to_central(dt: datetime) -> datetime:
    """Ensure datetime is in Central Time."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=CENTRAL_TZ)
    return dt.astimezone(CENTRAL_TZ)


def fetch_intraday_ticks(
    symbol: str,
    start_time: datetime,
    end_time: datetime,
    interval: str = "1m"
) -> List[Dict[str, Any]]:
    """
    Fetch intraday tick data from Yahoo Finance.

    Args:
        symbol: Ticker symbol (SPY, ^SPX, ^VIX)
        start_time: Start of window (timezone-aware preferred)
        end_time: End of window (timezone-aware preferred)
        interval: Candle interval (1m, 5m, etc.)

    Returns:
        List of candle dicts with timestamp, open, high, low, close, volume

    Note:
        Yahoo Finance only provides 1-minute data for the last 7 days.
        For older dates, this will return an empty list.
    """
    if not YFINANCE_AVAILABLE:
        logger.warning("yfinance not available - returning empty list")
        return []

    try:
        # Normalize times to Central
        start_ct = _normalize_to_central(start_time)
        end_ct = _normalize_to_central(end_time)

        # Rate limit requests
        _rate_limit()

        ticker = yf.Ticker(symbol)

        # Yahoo requires dates for the period
        # We fetch full days and filter afterwards
        # Use the date in the START timezone to avoid off-by-one errors
        fetch_start = start_ct.date()
        fetch_end = end_ct.date() + timedelta(days=1)

        logger.debug(f"Fetching {symbol} from {fetch_start} to {fetch_end} interval={interval}")

        df = ticker.history(
            start=fetch_start,
            end=fetch_end,
            interval=interval
        )

        if df is None or df.empty:
            logger.warning(f"No data returned from Yahoo for {symbol} on {fetch_start}")
            return []

        candles = []
        for idx, row in df.iterrows():
            try:
                # Convert pandas Timestamp to datetime
                # Yahoo returns timestamps in exchange timezone (Eastern for US)
                candle_time = idx.to_pydatetime()

                # Make timezone-aware if not already
                if candle_time.tzinfo is None:
                    # Yahoo sometimes returns naive timestamps in Eastern Time
                    candle_time = candle_time.replace(tzinfo=EASTERN_TZ)

                # Convert to Central for consistent comparison
                candle_time_ct = candle_time.astimezone(CENTRAL_TZ)

                # Filter to our window (all in Central Time now)
                if start_ct <= candle_time_ct <= end_ct:
                    # Safe volume extraction
                    volume = 0
                    if "Volume" in row.index:
                        vol_value = row["Volume"]
                        if pd.notna(vol_value):
                            try:
                                volume = int(vol_value)
                            except (ValueError, TypeError):
                                volume = 0

                    candles.append({
                        "timestamp": candle_time_ct.isoformat(),
                        "time_ct": candle_time_ct.strftime("%H:%M:%S"),
                        "open": round(float(row["Open"]), 2),
                        "high": round(float(row["High"]), 2),
                        "low": round(float(row["Low"]), 2),
                        "close": round(float(row["Close"]), 2),
                        "volume": volume
                    })
            except Exception as row_err:
                logger.warning(f"Error processing candle row: {row_err}")
                continue

        logger.info(f"Fetched {len(candles)} candles for {symbol} from {start_ct.strftime('%Y-%m-%d %H:%M')} to {end_ct.strftime('%Y-%m-%d %H:%M')}")
        return candles

    except Exception as e:
        logger.error(f"Yahoo fetch error for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        return []


def fetch_ticks_for_trade(
    trade: Dict[str, Any],
    symbol: str,
    buffer_minutes: int = 30
) -> List[Dict[str, Any]]:
    """
    Fetch intraday ticks for a single trade with buffer on each side.

    Args:
        trade: Trade dict with open_time and close_time
        symbol: Ticker symbol
        buffer_minutes: Minutes of context before entry and after exit

    Returns:
        List of candles covering the trade window
    """
    entry_time = _parse_datetime(trade.get("open_time"))
    exit_time = _parse_datetime(trade.get("close_time"))

    if not entry_time or not exit_time:
        logger.warning(f"Trade missing or invalid open_time/close_time: {trade.get('position_id')}")
        return []

    # Add buffer on each side for context
    start = entry_time - timedelta(minutes=buffer_minutes)
    end = exit_time + timedelta(minutes=buffer_minutes)

    return fetch_intraday_ticks(symbol, start, end)


def fetch_ticks_for_trades(
    trades: List[Dict[str, Any]],
    bot_name: str
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch intraday ticks for all trades from a bot.

    Args:
        trades: List of trade dicts
        bot_name: Bot name to determine symbol (fortress, samson, etc.)

    Returns:
        Dict mapping position_id to list of candles
    """
    if not YFINANCE_AVAILABLE:
        logger.warning("yfinance not available - returning empty dict")
        return {}

    symbol = BOT_SYMBOLS.get(bot_name.lower(), 'SPY')
    result = {}

    for trade in trades:
        position_id = trade.get("position_id")
        if not position_id:
            continue

        candles = fetch_ticks_for_trade(trade, symbol)
        result[position_id] = candles  # Store even if empty

    return result


def fetch_vix_history(
    target_date: Union[datetime, date],
    interval: str = "5m"
) -> List[Dict[str, Any]]:
    """
    Fetch VIX history for a trading day.

    Args:
        target_date: Date to fetch VIX for
        interval: Candle interval (5m recommended for VIX)

    Returns:
        List of VIX candles for the day
    """
    if not YFINANCE_AVAILABLE:
        return []

    try:
        # Handle both datetime and date inputs
        if isinstance(target_date, datetime):
            the_date = target_date.date()
        else:
            the_date = target_date

        # Market hours: 8:30am - 3:00pm CT
        start_time = datetime(the_date.year, the_date.month, the_date.day, 8, 30, tzinfo=CENTRAL_TZ)
        end_time = datetime(the_date.year, the_date.month, the_date.day, 15, 0, tzinfo=CENTRAL_TZ)

        return fetch_intraday_ticks("^VIX", start_time, end_time, interval)

    except Exception as e:
        logger.error(f"Error fetching VIX history: {e}")
        return []


def get_price_at_time(
    candles: List[Dict[str, Any]],
    target_time: Union[str, datetime],
    tolerance_minutes: int = 2
) -> Optional[float]:
    """
    Find the price at or near a specific time.

    Args:
        candles: List of candles
        target_time: Time to find price for
        tolerance_minutes: How many minutes of tolerance

    Returns:
        Close price at that time, or None if not found
    """
    if not candles:
        return None

    target = _parse_datetime(target_time)
    if not target:
        return None

    tolerance = timedelta(minutes=tolerance_minutes)

    for candle in candles:
        candle_time = _parse_datetime(candle.get("timestamp"))
        if candle_time and abs(candle_time - target) <= tolerance:
            return candle.get("close")

    return None


def find_high_low_during_trade(
    candles: List[Dict[str, Any]],
    entry_time: Union[str, datetime, None],
    exit_time: Union[str, datetime, None]
) -> Dict[str, Any]:
    """
    Find the high and low prices during a trade window.

    Args:
        candles: List of candles
        entry_time: Trade entry time
        exit_time: Trade exit time

    Returns:
        Dict with high/low prices and their timestamps
    """
    if not candles:
        return {"high": None, "low": None}

    entry = _parse_datetime(entry_time)
    exit = _parse_datetime(exit_time)

    if not entry or not exit:
        return {"high": None, "low": None}

    high_price = None
    high_time = None
    low_price = None
    low_time = None

    for candle in candles:
        candle_time = _parse_datetime(candle.get("timestamp"))
        if not candle_time:
            continue

        # Only consider candles during the trade
        if entry <= candle_time <= exit:
            candle_high = candle.get("high")
            candle_low = candle.get("low")

            if candle_high is not None:
                if high_price is None or candle_high > high_price:
                    high_price = candle_high
                    high_time = candle.get("timestamp")

            if candle_low is not None:
                if low_price is None or candle_low < low_price:
                    low_price = candle_low
                    low_time = candle.get("timestamp")

    return {
        "high": {
            "price": high_price,
            "timestamp": high_time
        } if high_price is not None else None,
        "low": {
            "price": low_price,
            "timestamp": low_time
        } if low_price is not None else None
    }


def find_level_tests(
    candles: List[Dict[str, Any]],
    levels: Dict[str, Optional[float]],
    tolerance_pct: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Find when price tested key levels (call wall, put wall, flip point).

    Args:
        candles: List of candles
        levels: Dict of level names to prices (e.g., {"call_wall": 6020, "put_wall": 5940})
        tolerance_pct: How close price must get to count as a test (default 0.1%)

    Returns:
        List of level test events with timestamp, level, price, and result
    """
    tests = []

    for level_name, level_price in levels.items():
        if level_price is None or level_price == 0:
            continue

        tolerance = level_price * (tolerance_pct / 100)

        for candle in candles:
            candle_high = candle.get("high")
            candle_low = candle.get("low")
            candle_close = candle.get("close")

            if candle_high is None or candle_low is None or candle_close is None:
                continue

            # Check if high or low touched the level
            touched_high = abs(candle_high - level_price) <= tolerance
            touched_low = abs(candle_low - level_price) <= tolerance

            if touched_high or touched_low:
                # Determine if level held or broke
                broke_above = candle_close > level_price + tolerance
                broke_below = candle_close < level_price - tolerance

                tests.append({
                    "level": level_name,
                    "level_price": level_price,
                    "timestamp": candle.get("timestamp"),
                    "candle_high": candle_high,
                    "candle_low": candle_low,
                    "candle_close": candle_close,
                    "result": "broke" if (broke_above or broke_below) else "held"
                })

    return tests
