"""
Timezone utilities for AlphaGEX trading system.

All times in AlphaGEX are standardized to Texas Central Time (America/Chicago).
This module provides consistent timezone handling across the entire codebase.

Usage:
    from utils.timezone import CENTRAL_TZ, get_central_time, to_central, format_central_time

    # Get current time in Central
    now = get_central_time()

    # Convert any datetime to Central
    central_dt = to_central(some_datetime)

    # Format for display
    formatted = format_central_time(now)
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Texas Central Time - the standard timezone for AlphaGEX
CENTRAL_TZ = ZoneInfo("America/Chicago")

# UTC timezone for reference
UTC_TZ = timezone.utc


def get_central_time() -> datetime:
    """Get current datetime in Texas Central Time.

    Returns:
        datetime: Current time as timezone-aware datetime in Central Time
    """
    return datetime.now(CENTRAL_TZ)


def to_central(dt: datetime) -> datetime:
    """Convert any datetime to Texas Central Time.

    Args:
        dt: A datetime object (can be naive or timezone-aware)

    Returns:
        datetime: Timezone-aware datetime in Central Time

    Note:
        - If dt is naive (no timezone), it is assumed to be in Central Time
        - If dt is timezone-aware, it is properly converted to Central Time
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        # Naive datetime - assume it's already in Central Time
        return dt.replace(tzinfo=CENTRAL_TZ)
    else:
        # Timezone-aware datetime - convert to Central Time
        return dt.astimezone(CENTRAL_TZ)


def ensure_central_aware(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in Central Time.

    Unlike to_central(), this is explicit about treating naive datetimes
    as Central Time and just attaching the timezone info.

    Args:
        dt: A datetime object

    Returns:
        datetime: Timezone-aware datetime in Central Time
    """
    if dt is None:
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=CENTRAL_TZ)
    return dt.astimezone(CENTRAL_TZ)


def format_central_time(dt: datetime = None, fmt: str = "%Y-%m-%d %H:%M:%S CT") -> str:
    """Format a datetime for display in Central Time.

    Args:
        dt: A datetime object (defaults to current time if None)
        fmt: strftime format string (default includes CT suffix)

    Returns:
        str: Formatted datetime string
    """
    if dt is None:
        dt = get_central_time()
    else:
        dt = to_central(dt)

    return dt.strftime(fmt)


def get_central_date() -> datetime:
    """Get current date at midnight in Texas Central Time.

    Returns:
        datetime: Today at midnight in Central Time
    """
    now = get_central_time()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def is_same_central_day(dt1: datetime, dt2: datetime = None) -> bool:
    """Check if two datetimes are on the same day in Central Time.

    Args:
        dt1: First datetime
        dt2: Second datetime (defaults to current time if None)

    Returns:
        bool: True if both datetimes are on the same Central Time day
    """
    if dt2 is None:
        dt2 = get_central_time()

    ct1 = to_central(dt1)
    ct2 = to_central(dt2)

    return ct1.date() == ct2.date()


# Market hours in Central Time
MARKET_OPEN_HOUR = 8
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 0

# Pre/Post market
PRE_MARKET_HOUR = 7
POST_MARKET_HOUR = 17


def is_market_hours(dt: datetime = None) -> bool:
    """Check if given time is within regular market hours (8:30 AM - 3:00 PM CT).

    Args:
        dt: Datetime to check (defaults to current time if None)

    Returns:
        bool: True if within market hours
    """
    if dt is None:
        dt = get_central_time()
    else:
        dt = to_central(dt)

    market_open = dt.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    market_close = dt.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0)

    return market_open <= dt <= market_close


def get_log_timestamp() -> str:
    """Get a timestamp string suitable for logging.

    Returns:
        str: Formatted timestamp in Central Time
    """
    return format_central_time(fmt="%Y-%m-%d %H:%M:%S")
