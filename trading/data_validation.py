"""
Data Validation Utilities for Trading Bots

Provides stale data detection, sanity checks, and validation for market data.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Configuration
MAX_DATA_AGE_SECONDS = 300  # 5 minutes max age for market data
MIN_VALID_PRICE = 1.0  # Minimum valid price for SPY/SPX
MAX_SPY_PRICE = 1000.0  # Maximum reasonable SPY price
MAX_SPX_PRICE = 10000.0  # Maximum reasonable SPX price
MIN_VIX = 5.0
MAX_VIX = 100.0


class StaleDataError(Exception):
    """Raised when market data is too old to trade on."""
    pass


class InvalidDataError(Exception):
    """Raised when market data fails sanity checks."""
    pass


def validate_market_data(
    data: Dict[str, Any],
    max_age_seconds: int = MAX_DATA_AGE_SECONDS,
    require_timestamp: bool = True
) -> Tuple[bool, Optional[str]]:
    """
    Validate market data for staleness and sanity.

    Args:
        data: Market data dictionary (should contain 'timestamp' or 'last_updated')
        max_age_seconds: Maximum age of data in seconds
        require_timestamp: If True, require timestamp field

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not data:
        return False, "No market data provided"

    # Check for timestamp
    timestamp = data.get('timestamp') or data.get('last_updated') or data.get('quote_time')

    if timestamp:
        try:
            # Parse timestamp if string
            if isinstance(timestamp, str):
                parsed = None
                original_timestamp = timestamp

                # Clean up potentially malformed timestamps
                import re

                # Pattern 1: "2025-12-29T09:01:08032+06:00" (5+ digits concatenated - missing dot before microseconds)
                malformed_match = re.match(r'(.+T\d{2}:\d{2}:)(\d{5,})([+-]\d{2}:\d{2})', timestamp)
                if malformed_match:
                    prefix, bad_part, tz = malformed_match.groups()
                    # Take first 2 digits as seconds, rest as microseconds
                    seconds = bad_part[:2]
                    micros = bad_part[2:].ljust(6, '0')[:6]
                    timestamp = f"{prefix}{seconds}.{micros}{tz}"
                    logger.debug(f"Fixed malformed timestamp (pattern 1): {original_timestamp} -> {timestamp}")

                # Pattern 2: "2025-12-29T08:33:00:044882-06:00" (colon before microseconds instead of period)
                elif re.match(r'.+T\d{2}:\d{2}:\d{2}:\d+[+-]\d{2}:\d{2}', timestamp):
                    # Replace the third colon (after seconds) with a period
                    parts = timestamp.split('T')
                    if len(parts) == 2:
                        time_part = parts[1]
                        # Find pattern HH:MM:SS:microseconds and fix it
                        time_fixed = re.sub(r'^(\d{2}:\d{2}:\d{2}):(\d+)', r'\1.\2', time_part)
                        timestamp = f"{parts[0]}T{time_fixed}"
                        logger.debug(f"Fixed malformed timestamp (pattern 2): {original_timestamp} -> {timestamp}")

                # Pattern 3: "2025-12-29T08:09:38448Z-05:00" (Z embedded in middle)
                elif 'Z-' in timestamp or 'Z+' in timestamp:
                    # Remove the Z, keep the offset
                    timestamp = timestamp.replace('Z-', '-').replace('Z+', '+')
                    # Also fix any concatenated seconds+microseconds
                    malformed_match2 = re.match(r'(.+T\d{2}:\d{2}:)(\d{5,})([+-]\d{2}:\d{2})', timestamp)
                    if malformed_match2:
                        prefix, bad_part, tz = malformed_match2.groups()
                        seconds = bad_part[:2]
                        micros = bad_part[2:].ljust(6, '0')[:6]
                        timestamp = f"{prefix}{seconds}.{micros}{tz}"
                    logger.debug(f"Fixed malformed timestamp (pattern 3): {original_timestamp} -> {timestamp}")

                # Pattern 4: Just "Z" at the end without offset (valid UTC format)
                elif timestamp.endswith('Z'):
                    # Convert Z to +00:00 for consistent parsing
                    timestamp = timestamp[:-1] + '+00:00'
                    logger.debug(f"Fixed UTC timestamp: {original_timestamp} -> {timestamp}")

                # First try fromisoformat which handles ISO 8601 with timezone (e.g., 2025-12-29T08:55:01.587153-06:00)
                try:
                    parsed = datetime.fromisoformat(timestamp)
                except ValueError:
                    # Fall back to common formats without timezone
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                                '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S%z']:
                        try:
                            parsed = datetime.strptime(timestamp, fmt)
                            break
                        except ValueError:
                            continue

                if parsed is None:
                    # Could not parse timestamp - log the issue but don't fail the validation
                    logger.warning(f"Could not parse timestamp: {original_timestamp}")
                    if require_timestamp:
                        return False, f"Could not parse timestamp: {original_timestamp}"
                    timestamp = None
                else:
                    timestamp = parsed

            if timestamp:
                # Make timezone-aware if needed
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=CENTRAL_TZ)

                now = datetime.now(CENTRAL_TZ)
                age_seconds = (now - timestamp).total_seconds()

                if age_seconds > max_age_seconds:
                    return False, f"Data is {age_seconds:.0f} seconds old (max: {max_age_seconds})"

                if age_seconds < -60:  # Allow 1 minute clock skew
                    return False, f"Data timestamp is in the future by {-age_seconds:.0f} seconds"

        except Exception as e:
            if require_timestamp:
                return False, f"Error validating timestamp: {e}"
    elif require_timestamp:
        return False, "No timestamp found in market data"

    # Validate price if present
    spot_price = data.get('spot_price') or data.get('last') or data.get('price')
    if spot_price is not None:
        if spot_price <= MIN_VALID_PRICE:
            return False, f"Invalid spot price: {spot_price} (too low)"

        # Determine if SPY or SPX based on price
        max_price = MAX_SPX_PRICE if spot_price > 1000 else MAX_SPY_PRICE
        if spot_price > max_price:
            return False, f"Invalid spot price: {spot_price} (too high, max: {max_price})"

    # Validate VIX if present
    vix = data.get('vix')
    if vix is not None:
        if vix < MIN_VIX or vix > MAX_VIX:
            return False, f"Invalid VIX: {vix} (must be between {MIN_VIX} and {MAX_VIX})"

    return True, None


def validate_spot_price(
    price: float,
    symbol: str = 'SPY'
) -> Tuple[bool, Optional[str]]:
    """
    Validate a spot price.

    Args:
        price: The price to validate
        symbol: The underlying symbol (SPY, SPX, etc.)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if price is None:
        return False, "Price is None"

    if price <= MIN_VALID_PRICE:
        return False, f"Price {price} is below minimum {MIN_VALID_PRICE}"

    max_price = MAX_SPX_PRICE if symbol.upper() in ['SPX', '$SPX.X'] else MAX_SPY_PRICE
    if price > max_price:
        return False, f"Price {price} exceeds maximum {max_price} for {symbol}"

    return True, None


def validate_greeks(
    delta: Optional[float] = None,
    gamma: Optional[float] = None,
    theta: Optional[float] = None,
    vega: Optional[float] = None
) -> Tuple[bool, Optional[str]]:
    """
    Validate option Greeks for sanity.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if delta is not None:
        if delta < -1.5 or delta > 1.5:  # Allow small overshoot for approximations
            return False, f"Invalid delta: {delta} (must be between -1 and 1)"

    if gamma is not None:
        if gamma < 0 or gamma > 1:
            return False, f"Invalid gamma: {gamma} (must be between 0 and 1)"

    if theta is not None:
        # Theta is usually negative (time decay), but can be small positive
        if theta < -100 or theta > 10:
            return False, f"Invalid theta: {theta} (out of reasonable range)"

    if vega is not None:
        if vega < 0 or vega > 100:
            return False, f"Invalid vega: {vega} (out of reasonable range)"

    return True, None


def validate_iron_condor_strikes(
    put_long: float,
    put_short: float,
    call_short: float,
    call_long: float,
    spot_price: float,
    min_spread_width: float = 1.0
) -> Tuple[bool, Optional[str]]:
    """
    Validate Iron Condor strikes for sanity.

    Args:
        put_long: Long put strike (lowest)
        put_short: Short put strike
        call_short: Short call strike
        call_long: Long call strike (highest)
        spot_price: Current underlying price
        min_spread_width: Minimum spread width

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check ordering
    if not (put_long < put_short < call_short < call_long):
        return False, f"Invalid strike ordering: {put_long}/{put_short}/{call_short}/{call_long}"

    # Check spread widths
    put_width = put_short - put_long
    call_width = call_long - call_short

    if put_width < min_spread_width:
        return False, f"Put spread width {put_width} is below minimum {min_spread_width}"

    if call_width < min_spread_width:
        return False, f"Call spread width {call_width} is below minimum {min_spread_width}"

    # Check that spot is within the condor wings
    if spot_price <= put_long or spot_price >= call_long:
        return False, f"Spot price {spot_price} is outside condor range [{put_long}, {call_long}]"

    # Check that short strikes aren't too close to spot
    min_distance_pct = 0.5  # At least 0.5% away from spot
    min_distance = spot_price * (min_distance_pct / 100)

    put_distance = spot_price - put_short
    call_distance = call_short - spot_price

    if put_distance < min_distance:
        return False, f"Put short strike {put_short} is too close to spot {spot_price}"

    if call_distance < min_distance:
        return False, f"Call short strike {call_short} is too close to spot {spot_price}"

    return True, None


def validate_spread_strikes(
    long_strike: float,
    short_strike: float,
    spot_price: float,
    spread_type: str,  # 'BULL_CALL', 'BEAR_PUT', etc.
    min_spread_width: float = 1.0
) -> Tuple[bool, Optional[str]]:
    """
    Validate vertical spread strikes.

    Returns:
        Tuple of (is_valid, error_message)
    """
    spread_width = abs(long_strike - short_strike)

    if spread_width < min_spread_width:
        return False, f"Spread width {spread_width} is below minimum {min_spread_width}"

    # Validate strike ordering based on spread type
    if 'BULL_CALL' in spread_type.upper():
        # Bull call spread: buy lower strike, sell higher strike
        if long_strike >= short_strike:
            return False, f"Bull call spread requires long_strike < short_strike"
    elif 'BEAR_PUT' in spread_type.upper():
        # Bear put spread: buy higher strike, sell lower strike
        if long_strike <= short_strike:
            return False, f"Bear put spread requires long_strike > short_strike"

    # Check strikes are reasonable relative to spot
    max_distance_pct = 20  # Max 20% from spot
    max_distance = spot_price * (max_distance_pct / 100)

    if abs(long_strike - spot_price) > max_distance:
        return False, f"Long strike {long_strike} is too far from spot {spot_price}"

    if abs(short_strike - spot_price) > max_distance:
        return False, f"Short strike {short_strike} is too far from spot {spot_price}"

    return True, None


def add_timestamp_to_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add current timestamp to market data if not present.

    Args:
        data: Market data dictionary

    Returns:
        Updated dictionary with timestamp
    """
    if not data.get('timestamp') and not data.get('last_updated'):
        data['timestamp'] = datetime.now(CENTRAL_TZ).isoformat()
    return data


def check_trading_hours(
    current_time: Optional[datetime] = None,
    market_open: str = "09:30",
    market_close: str = "16:00"
) -> Tuple[bool, Optional[str]]:
    """
    Check if current time is within trading hours.

    Args:
        current_time: Time to check (defaults to now)
        market_open: Market open time (HH:MM)
        market_close: Market close time (HH:MM)

    Returns:
        Tuple of (is_trading_hours, message)
    """
    if current_time is None:
        current_time = datetime.now(CENTRAL_TZ)

    # Parse market hours
    open_hour, open_min = map(int, market_open.split(':'))
    close_hour, close_min = map(int, market_close.split(':'))

    market_open_time = current_time.replace(hour=open_hour, minute=open_min, second=0, microsecond=0)
    market_close_time = current_time.replace(hour=close_hour, minute=close_min, second=0, microsecond=0)

    if current_time < market_open_time:
        return False, f"Market not yet open (opens at {market_open} CT)"

    if current_time > market_close_time:
        return False, f"Market closed (closed at {market_close} CT)"

    # Check if weekend
    if current_time.weekday() >= 5:
        return False, "Market closed (weekend)"

    return True, None
