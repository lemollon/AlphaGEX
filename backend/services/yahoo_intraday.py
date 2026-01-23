"""
Yahoo Finance Intraday Tick Fetcher

Fetches 1-minute candle data from Yahoo Finance for trade analysis.
Used by the bot report generator to get price action during trades.

Author: AlphaGEX
Date: January 2025
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from zoneinfo import ZoneInfo

import yfinance as yf

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Symbol mapping for each bot
BOT_SYMBOLS = {
    'ares': 'SPY',      # ARES trades SPY
    'athena': 'SPY',    # ATHENA trades SPY
    'icarus': 'SPY',    # ICARUS trades SPY
    'titan': '^SPX',    # TITAN trades SPX
    'pegasus': '^SPX',  # PEGASUS trades SPX
}


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
        start_time: Start of window (timezone-aware)
        end_time: End of window (timezone-aware)
        interval: Candle interval (1m, 5m, etc.)

    Returns:
        List of candle dicts with timestamp, open, high, low, close, volume

    Note:
        Yahoo Finance only provides 1-minute data for the last 7 days.
        For older dates, this will return an empty list.
    """
    try:
        ticker = yf.Ticker(symbol)

        # Yahoo requires dates, will return full day data
        # We filter to our window after fetching
        df = ticker.history(
            start=start_time.date(),
            end=(end_time + timedelta(days=1)).date(),
            interval=interval
        )

        if df.empty:
            logger.warning(f"No data returned from Yahoo for {symbol} on {start_time.date()}")
            return []

        candles = []
        for idx, row in df.iterrows():
            # Convert pandas Timestamp to datetime
            candle_time = idx.to_pydatetime()

            # Make timezone-aware if not already
            if candle_time.tzinfo is None:
                candle_time = candle_time.replace(tzinfo=CENTRAL_TZ)

            # Filter to our window
            if start_time <= candle_time <= end_time:
                candles.append({
                    "timestamp": candle_time.isoformat(),
                    "time_ct": candle_time.astimezone(CENTRAL_TZ).strftime("%H:%M:%S"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]) if "Volume" in row and not row.isna().get("Volume", False) else 0
                })

        logger.info(f"Fetched {len(candles)} candles for {symbol} from {start_time} to {end_time}")
        return candles

    except Exception as e:
        logger.error(f"Yahoo fetch error for {symbol}: {e}")
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
    entry_time = trade.get("open_time")
    exit_time = trade.get("close_time")

    if not entry_time or not exit_time:
        logger.warning(f"Trade missing open_time or close_time: {trade.get('position_id')}")
        return []

    # Parse times if strings
    if isinstance(entry_time, str):
        entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
    if isinstance(exit_time, str):
        exit_time = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))

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
        bot_name: Bot name to determine symbol (ares, titan, etc.)

    Returns:
        Dict mapping position_id to list of candles
    """
    symbol = BOT_SYMBOLS.get(bot_name.lower(), 'SPY')
    result = {}

    for trade in trades:
        position_id = trade.get("position_id")
        if not position_id:
            continue

        candles = fetch_ticks_for_trade(trade, symbol)
        if candles:
            result[position_id] = candles
        else:
            # Store empty list so we know we tried
            result[position_id] = []

    return result


def fetch_vix_history(
    date: datetime,
    interval: str = "5m"
) -> List[Dict[str, Any]]:
    """
    Fetch VIX history for a trading day.

    Args:
        date: Date to fetch VIX for
        interval: Candle interval (5m recommended for VIX)

    Returns:
        List of VIX candles for the day
    """
    try:
        # Market hours: 8:30am - 3:00pm CT
        start_time = datetime.combine(date.date(), datetime.min.time().replace(hour=8, minute=30))
        start_time = start_time.replace(tzinfo=CENTRAL_TZ)

        end_time = datetime.combine(date.date(), datetime.min.time().replace(hour=15, minute=0))
        end_time = end_time.replace(tzinfo=CENTRAL_TZ)

        return fetch_intraday_ticks("^VIX", start_time, end_time, interval)

    except Exception as e:
        logger.error(f"Error fetching VIX history: {e}")
        return []


def get_price_at_time(
    candles: List[Dict[str, Any]],
    target_time: datetime,
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

    # Parse target time if string
    if isinstance(target_time, str):
        target_time = datetime.fromisoformat(target_time.replace("Z", "+00:00"))

    tolerance = timedelta(minutes=tolerance_minutes)

    for candle in candles:
        candle_time = datetime.fromisoformat(candle["timestamp"])
        if abs(candle_time - target_time) <= tolerance:
            return candle["close"]

    return None


def find_high_low_during_trade(
    candles: List[Dict[str, Any]],
    entry_time: datetime,
    exit_time: datetime
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

    # Parse times if strings
    if isinstance(entry_time, str):
        entry_time = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
    if isinstance(exit_time, str):
        exit_time = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))

    high_price = None
    high_time = None
    low_price = None
    low_time = None

    for candle in candles:
        candle_time = datetime.fromisoformat(candle["timestamp"])

        # Only consider candles during the trade
        if entry_time <= candle_time <= exit_time:
            if high_price is None or candle["high"] > high_price:
                high_price = candle["high"]
                high_time = candle["timestamp"]

            if low_price is None or candle["low"] < low_price:
                low_price = candle["low"]
                low_time = candle["timestamp"]

    return {
        "high": {
            "price": high_price,
            "timestamp": high_time
        } if high_price else None,
        "low": {
            "price": low_price,
            "timestamp": low_time
        } if low_price else None
    }


def find_level_tests(
    candles: List[Dict[str, Any]],
    levels: Dict[str, float],
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
            # Check if high or low touched the level
            touched_high = abs(candle["high"] - level_price) <= tolerance
            touched_low = abs(candle["low"] - level_price) <= tolerance

            if touched_high or touched_low:
                # Determine if level held or broke
                broke_above = candle["close"] > level_price + tolerance
                broke_below = candle["close"] < level_price - tolerance

                tests.append({
                    "level": level_name,
                    "level_price": level_price,
                    "timestamp": candle["timestamp"],
                    "candle_high": candle["high"],
                    "candle_low": candle["low"],
                    "candle_close": candle["close"],
                    "result": "broke" if (broke_above or broke_below) else "held"
                })

    return tests
