"""
Shared utility functions for AlphaGEX API.

This module consolidates common functions used across multiple route files
to eliminate code duplication and ensure consistency.
"""

import math
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Optional, Union, Dict, List
from functools import lru_cache


# =============================================================================
# NUMERICAL PRECISION UTILITIES
# =============================================================================

# Precision constants for financial calculations
PRICE_PRECISION = Decimal('0.0001')  # 4 decimal places for option prices
GEX_PRECISION = Decimal('0.01')      # 2 decimal places for GEX values
PERCENT_PRECISION = Decimal('0.01')  # 2 decimal places for percentages
CURRENCY_PRECISION = Decimal('0.01') # 2 decimal places for currency


def safe_round(value: Any, decimals: int = 2, default: float = 0.0) -> float:
    """
    Safely round a value, returning default if inf/nan/None.

    This is the canonical implementation - all other instances should import this.

    Args:
        value: The value to round (can be any numeric type or None)
        decimals: Number of decimal places (default: 2)
        default: Value to return if input is invalid (default: 0.0)

    Returns:
        Rounded float value or default
    """
    if value is None:
        return default
    try:
        float_val = float(value)
        if math.isnan(float_val) or math.isinf(float_val):
            return default
        return round(float_val, decimals)
    except (ValueError, TypeError, OverflowError):
        return default


def safe_decimal(value: Any, precision: Decimal = CURRENCY_PRECISION, default: Decimal = Decimal('0')) -> Decimal:
    """
    Convert value to Decimal with specified precision.

    Args:
        value: The value to convert
        precision: Decimal precision to quantize to
        default: Default value if conversion fails

    Returns:
        Decimal value quantized to specified precision
    """
    if value is None:
        return default
    try:
        if isinstance(value, Decimal):
            dec_val = value
        else:
            dec_val = Decimal(str(value))

        if dec_val.is_nan() or dec_val.is_infinite():
            return default

        return dec_val.quantize(precision, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert to float, returning default if invalid.

    Args:
        value: The value to convert
        default: Default value if conversion fails

    Returns:
        Float value or default
    """
    if value is None:
        return default
    try:
        float_val = float(value)
        if math.isnan(float_val) or math.isinf(float_val):
            return default
        return float_val
    except (ValueError, TypeError, OverflowError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert to int, returning default if invalid.

    Args:
        value: The value to convert
        default: Default value if conversion fails

    Returns:
        Int value or default
    """
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError, OverflowError):
        return default


# =============================================================================
# GEX DATA FORMATTING
# =============================================================================

def format_gex_value(value: Union[int, float, None], short: bool = True) -> str:
    """
    Format GEX value for display (e.g., 2.5B, 500M).

    Args:
        value: GEX value in dollars
        short: If True, use abbreviated format (B, M)

    Returns:
        Formatted string representation
    """
    if value is None:
        return "N/A"

    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return "N/A"

        if short:
            if abs(val) >= 1e9:
                return f"${val / 1e9:.2f}B"
            elif abs(val) >= 1e6:
                return f"${val / 1e6:.1f}M"
            else:
                return f"${val:,.0f}"
        else:
            return f"${val:,.2f}"
    except (ValueError, TypeError):
        return "N/A"


def calculate_pnl_percent(
    entry_price: float,
    current_price: float,
    contracts: int = 1,
    multiplier: int = 100
) -> float:
    """
    Calculate P&L percentage for options position.

    Args:
        entry_price: Entry price per contract
        current_price: Current price per contract
        contracts: Number of contracts
        multiplier: Contract multiplier (default 100 for standard options)

    Returns:
        P&L percentage
    """
    if entry_price <= 0 or contracts <= 0:
        return 0.0

    entry_value = entry_price * contracts * multiplier
    if entry_value == 0:
        return 0.0

    pnl = (current_price - entry_price) * contracts * multiplier
    return safe_round((pnl / entry_value) * 100, 2)


# =============================================================================
# DICTIONARY UTILITIES
# =============================================================================

def clean_dict_for_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean dictionary for JSON serialization by replacing NaN/Inf with None.

    Args:
        data: Dictionary to clean

    Returns:
        Cleaned dictionary safe for JSON serialization
    """
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                cleaned[key] = None
            else:
                cleaned[key] = value
        elif isinstance(value, dict):
            cleaned[key] = clean_dict_for_json(value)
        elif isinstance(value, list):
            cleaned[key] = [
                clean_dict_for_json(item) if isinstance(item, dict)
                else (None if isinstance(item, float) and (math.isnan(item) or math.isinf(item)) else item)
                for item in value
            ]
        elif isinstance(value, Decimal):
            cleaned[key] = float(value)
        else:
            cleaned[key] = value
    return cleaned


def get_nested(data: Dict, *keys, default: Any = None) -> Any:
    """
    Safely get nested dictionary value.

    Args:
        data: Dictionary to search
        *keys: Keys to traverse
        default: Default value if not found

    Returns:
        Value at nested path or default
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current if current is not None else default


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_symbol(symbol: str) -> str:
    """
    Validate and normalize a trading symbol.

    Args:
        symbol: Trading symbol to validate

    Returns:
        Normalized symbol (uppercase, stripped)

    Raises:
        ValueError: If symbol is invalid
    """
    if not symbol or not isinstance(symbol, str):
        raise ValueError("Symbol must be a non-empty string")

    normalized = symbol.strip().upper()

    # Basic validation - alphanumeric only
    if not normalized.isalnum():
        raise ValueError(f"Invalid symbol format: {symbol}")

    if len(normalized) > 10:
        raise ValueError(f"Symbol too long: {symbol}")

    return normalized


def validate_strike(strike: Union[int, float, str]) -> float:
    """
    Validate and convert strike price.

    Args:
        strike: Strike price to validate

    Returns:
        Validated strike price as float

    Raises:
        ValueError: If strike is invalid
    """
    try:
        strike_val = float(strike)
        if strike_val <= 0:
            raise ValueError(f"Strike must be positive: {strike}")
        if math.isnan(strike_val) or math.isinf(strike_val):
            raise ValueError(f"Invalid strike value: {strike}")
        return strike_val
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid strike price: {strike}") from e


def validate_option_type(option_type: str) -> str:
    """
    Validate and normalize option type.

    Args:
        option_type: Option type to validate ('CALL', 'PUT', 'C', 'P')

    Returns:
        Normalized option type ('CALL' or 'PUT')

    Raises:
        ValueError: If option type is invalid
    """
    if not option_type:
        raise ValueError("Option type is required")

    normalized = option_type.strip().upper()

    if normalized in ('CALL', 'C'):
        return 'CALL'
    elif normalized in ('PUT', 'P'):
        return 'PUT'
    else:
        raise ValueError(f"Invalid option type: {option_type}. Must be CALL/C or PUT/P")


# =============================================================================
# DATE/TIME UTILITIES
# =============================================================================

def get_market_time():
    """Get current time in US/Central timezone (market time)."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago"))
    except ImportError:
        import pytz
        return datetime.now(pytz.timezone("America/Chicago"))


def is_market_hours() -> bool:
    """Check if currently within market hours (8:30 AM - 3:00 PM CT, Mon-Fri)."""
    ct_now = get_market_time()

    # Check weekday (0=Monday, 6=Sunday)
    if ct_now.weekday() >= 5:
        return False

    # Check time (8:30 AM to 3:00 PM CT)
    hour = ct_now.hour
    minute = ct_now.minute

    if hour < 8 or (hour == 8 and minute < 30):
        return False
    if hour > 15 or (hour == 15 and minute > 0):
        return False

    return True


def format_timestamp(dt) -> str:
    """Format datetime for display."""
    if dt is None:
        return "N/A"
    try:
        if hasattr(dt, 'strftime'):
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        return str(dt)
    except Exception:
        return str(dt)
