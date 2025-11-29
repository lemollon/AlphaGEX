"""
Expiration Date Utilities
Calculate and display options expiration dates for strategies
"""

from datetime import datetime, timedelta
from typing import Dict, Tuple

# Streamlit is only needed for display functions, make it optional
try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None


def get_next_friday(from_date: datetime = None) -> datetime:
    """
    Get the next Friday from a given date

    Args:
        from_date: Starting date (defaults to today)

    Returns:
        datetime object of next Friday
    """
    if from_date is None:
        from_date = datetime.now()

    # Friday is weekday 4
    days_until_friday = (4 - from_date.weekday()) % 7

    # If today is Friday and market is closed, get next Friday
    if days_until_friday == 0 and from_date.hour >= 16:
        days_until_friday = 7

    # If days_until_friday is 0 and we're before close, return today
    if days_until_friday == 0:
        return from_date

    return from_date + timedelta(days=days_until_friday)


def get_third_friday_of_month(year: int, month: int) -> datetime:
    """
    Get the third Friday of a given month (monthly expiration)

    Args:
        year: Year
        month: Month (1-12)

    Returns:
        datetime object of third Friday
    """
    # Get first day of month
    first_day = datetime(year, month, 1)

    # Find first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)

    # Third Friday is 14 days after first Friday
    third_friday = first_friday + timedelta(days=14)

    return third_friday


def get_expiration_for_dte(dte_target: int, from_date: datetime = None) -> Tuple[datetime, str, int]:
    """
    Get expiration date for a target DTE

    Args:
        dte_target: Target days to expiration
        from_date: Starting date (defaults to today)

    Returns:
        (expiration_date, expiration_type, actual_dte) tuple
    """
    if from_date is None:
        from_date = datetime.now()

    # 0DTE: Today (if before close) or next trading day
    if dte_target == 0:
        if from_date.weekday() == 4 and from_date.hour >= 16:  # Friday after close
            exp_date = from_date + timedelta(days=3)  # Monday
            exp_type = "1DTE (Monday)"
            actual_dte = 1
        elif from_date.weekday() == 4:  # Friday before close
            exp_date = from_date
            exp_type = "0DTE"
            actual_dte = 0
        else:
            exp_date = from_date
            exp_type = "0DTE"
            actual_dte = 0

    # 1-7 DTE: Next Friday (weekly)
    elif dte_target <= 7:
        exp_date = get_next_friday(from_date)
        actual_dte = (exp_date - from_date).days
        exp_type = f"Weekly ({actual_dte}DTE)"

    # 8-14 DTE: Friday next week
    elif dte_target <= 14:
        next_friday = get_next_friday(from_date)
        exp_date = next_friday + timedelta(days=7)
        actual_dte = (exp_date - from_date).days
        exp_type = f"Weekly+ ({actual_dte}DTE)"

    # 15-35 DTE: Monthly (third Friday of next month)
    elif dte_target <= 35:
        # Get next month's third Friday
        if from_date.month == 12:
            next_month_year = from_date.year + 1
            next_month = 1
        else:
            next_month_year = from_date.year
            next_month = from_date.month + 1

        exp_date = get_third_friday_of_month(next_month_year, next_month)

        # If that's too soon, go to following month
        if (exp_date - from_date).days < 15:
            if next_month == 12:
                next_month_year += 1
                next_month = 1
            else:
                next_month += 1
            exp_date = get_third_friday_of_month(next_month_year, next_month)

        actual_dte = (exp_date - from_date).days
        exp_type = f"Monthly ({actual_dte}DTE)"

    # 36+ DTE: Monthly, two months out
    else:
        # Get third Friday of month two months from now
        target_month = from_date.month + 2
        target_year = from_date.year

        if target_month > 12:
            target_year += 1
            target_month -= 12

        exp_date = get_third_friday_of_month(target_year, target_month)
        actual_dte = (exp_date - from_date).days
        exp_type = f"Monthly+ ({actual_dte}DTE)"

    return exp_date, exp_type, actual_dte


def format_expiration_display(exp_date: datetime, dte: int) -> str:
    """
    Format expiration for display

    Args:
        exp_date: Expiration datetime
        dte: Days to expiration

    Returns:
        Formatted string like "Jan 12 (7 DTE)"
    """
    date_str = exp_date.strftime('%b %d')
    return f"{date_str} ({dte} DTE)"


def get_expiration_color(dte: int) -> str:
    """
    Get color coding for expiration based on DTE

    Args:
        dte: Days to expiration

    Returns:
        Color string for Streamlit
    """
    if dte <= 2:
        return "🔴"  # Red - very short term
    elif dte <= 7:
        return "🟡"  # Yellow - short term
    elif dte <= 14:
        return "🟢"  # Green - medium term
    else:
        return "🔵"  # Blue - long term


def is_market_hours() -> bool:
    """
    Check if it's currently market hours (9:30 AM - 4:00 PM ET, Mon-Fri)

    Returns:
        True if market is open
    """
    now = datetime.now()

    # Check if weekend
    if now.weekday() >= 5:  # Saturday or Sunday
        return False

    # Check time (simplified - doesn't account for holidays or time zones)
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    return market_open <= now <= market_close


def get_time_until_expiration(exp_date: datetime) -> str:
    """
    Get human-readable time until expiration

    Args:
        exp_date: Expiration datetime

    Returns:
        String like "2 days, 3 hours" or "Expired"
    """
    now = datetime.now()

    if exp_date < now:
        return "Expired"

    delta = exp_date - now

    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60

    if days > 0:
        if hours > 0:
            return f"{days}d {hours}h"
        else:
            return f"{days}d"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"


def add_expiration_to_setup(setup: Dict) -> Dict:
    """
    Add expiration date information to a strategy setup

    Args:
        setup: Strategy setup dictionary

    Returns:
        Setup with added expiration fields
    """
    # Parse DTE from best_time or default
    dte_target = 7  # Default
    best_time = setup.get('best_time', '')

    if 'DTE' in best_time:
        # Extract DTE number
        import re
        dte_match = re.search(r'(\d+)[-]?(\d+)?\s*DTE', best_time)
        if dte_match:
            low = int(dte_match.group(1))
            high = int(dte_match.group(2)) if dte_match.group(2) else low
            dte_target = (low + high) // 2
    elif '0DTE' in str(setup.get('strategy', '')) or '0-2 DTE' in best_time:
        dte_target = 0

    # Get expiration
    exp_date, exp_type, actual_dte = get_expiration_for_dte(dte_target)

    # Add to setup
    setup['expiration_date'] = exp_date
    setup['expiration_str'] = exp_date.strftime('%Y-%m-%d')
    setup['expiration_display'] = format_expiration_display(exp_date, actual_dte)
    setup['expiration_type'] = exp_type
    setup['dte'] = actual_dte
    setup['time_until_exp'] = get_time_until_expiration(exp_date)
    setup['exp_color'] = get_expiration_color(actual_dte)

    return setup


def display_expiration_info(setup: Dict):
    """
    Display expiration information in Streamlit UI

    Args:
        setup: Strategy setup with expiration info
    """
    if not STREAMLIT_AVAILABLE:
        print(f"Expiration: {setup.get('expiration_display', 'N/A')} ({setup.get('dte', 'N/A')} DTE)")
        return

    if 'expiration_display' not in setup:
        setup = add_expiration_to_setup(setup)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Expiration",
            setup['expiration_display'],
            help=f"Expires {setup['time_until_exp']} from now"
        )

    with col2:
        st.metric(
            "Type",
            setup['expiration_type']
        )

    with col3:
        st.markdown(f"{setup['exp_color']} **{setup['dte']} DTE**")


def get_all_fridays_in_month(year: int, month: int) -> list:
    """
    Get all Fridays in a given month

    Args:
        year: Year
        month: Month (1-12)

    Returns:
        List of datetime objects for all Fridays
    """
    fridays = []

    # Get first day of month
    first_day = datetime(year, month, 1)

    # Find first Friday
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)

    # Add all Fridays in the month
    current = first_friday
    while current.month == month:
        fridays.append(current)
        current += timedelta(days=7)

    return fridays


def is_weekly_expiration(date: datetime) -> bool:
    """
    Check if a date is a weekly expiration (Friday, but not monthly)

    Args:
        date: Date to check

    Returns:
        True if weekly expiration
    """
    if date.weekday() != 4:  # Not Friday
        return False

    # Check if it's the third Friday (monthly)
    third_friday = get_third_friday_of_month(date.year, date.month)

    return date != third_friday


def get_next_monthly_expiration(from_date: datetime = None) -> datetime:
    """
    Get the next monthly expiration (third Friday of the month)

    Args:
        from_date: Starting date (defaults to today)

    Returns:
        datetime object of next monthly expiration
    """
    if from_date is None:
        from_date = datetime.now()

    # Get this month's third Friday
    this_month_third = get_third_friday_of_month(from_date.year, from_date.month)

    # If we've passed it, get next month's
    if from_date >= this_month_third:
        if from_date.month == 12:
            next_year = from_date.year + 1
            next_month = 1
        else:
            next_year = from_date.year
            next_month = from_date.month + 1

        return get_third_friday_of_month(next_year, next_month)
    else:
        return this_month_third
