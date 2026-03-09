"""
Full 2026 US economic calendar — major events only.
All times are US Central (America/Chicago). DST handled via zoneinfo (stdlib).
Dates are best estimates based on typical BLS/Fed scheduling patterns.
Update annually when official schedules are published.
"""

from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

CT = ZoneInfo('America/Chicago')


def _ct(year, month, day, hour, minute):
    """Helper to create CT-aware datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=CT)


ECONOMIC_EVENTS_2026 = [
    # ========== FOMC RATE DECISIONS (8 meetings) ==========
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 1, 28, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + press conference"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 3, 18, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + SEP/dot plot"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 5, 6, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + press conference"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 6, 17, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + SEP/dot plot"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 7, 29, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + press conference"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 9, 16, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + SEP/dot plot"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 10, 28, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + press conference"},
    {"name": "FOMC Rate Decision", "datetime": _ct(2026, 12, 9, 13, 0), "impact": "HIGH", "description": "Federal Reserve interest rate announcement + SEP/dot plot"},

    # ========== CPI REPORTS (12 monthly) ==========
    {"name": "CPI Report (Dec data)", "datetime": _ct(2026, 1, 14, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Jan data)", "datetime": _ct(2026, 2, 11, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Feb data)", "datetime": _ct(2026, 3, 11, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Mar data)", "datetime": _ct(2026, 4, 14, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Apr data)", "datetime": _ct(2026, 5, 13, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (May data)", "datetime": _ct(2026, 6, 10, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Jun data)", "datetime": _ct(2026, 7, 14, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Jul data)", "datetime": _ct(2026, 8, 12, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Aug data)", "datetime": _ct(2026, 9, 11, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Sep data)", "datetime": _ct(2026, 10, 14, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Oct data)", "datetime": _ct(2026, 11, 12, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},
    {"name": "CPI Report (Nov data)", "datetime": _ct(2026, 12, 10, 7, 30), "impact": "HIGH", "description": "Consumer Price Index — core and headline inflation"},

    # ========== PPI REPORTS (12 monthly) ==========
    {"name": "PPI Report (Dec data)", "datetime": _ct(2026, 1, 15, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Jan data)", "datetime": _ct(2026, 2, 12, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Feb data)", "datetime": _ct(2026, 3, 12, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Mar data)", "datetime": _ct(2026, 4, 15, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Apr data)", "datetime": _ct(2026, 5, 14, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (May data)", "datetime": _ct(2026, 6, 11, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Jun data)", "datetime": _ct(2026, 7, 15, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Jul data)", "datetime": _ct(2026, 8, 13, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Aug data)", "datetime": _ct(2026, 9, 10, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Sep data)", "datetime": _ct(2026, 10, 15, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Oct data)", "datetime": _ct(2026, 11, 13, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},
    {"name": "PPI Report (Nov data)", "datetime": _ct(2026, 12, 11, 7, 30), "impact": "HIGH", "description": "Producer Price Index — wholesale inflation gauge"},

    # ========== NFP / NON-FARM PAYROLLS (12 monthly, first Friday) ==========
    {"name": "Non-Farm Payrolls (Dec data)", "datetime": _ct(2026, 1, 9, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Jan data)", "datetime": _ct(2026, 2, 6, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Feb data)", "datetime": _ct(2026, 3, 6, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Mar data)", "datetime": _ct(2026, 4, 3, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Apr data)", "datetime": _ct(2026, 5, 8, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (May data)", "datetime": _ct(2026, 6, 5, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Jun data)", "datetime": _ct(2026, 7, 2, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Jul data)", "datetime": _ct(2026, 8, 7, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Aug data)", "datetime": _ct(2026, 9, 4, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Sep data)", "datetime": _ct(2026, 10, 2, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Oct data)", "datetime": _ct(2026, 11, 6, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},
    {"name": "Non-Farm Payrolls (Nov data)", "datetime": _ct(2026, 12, 4, 7, 30), "impact": "HIGH", "description": "Employment situation — jobs added, unemployment rate, wages"},

    # ========== GDP RELEASES (12 — advance, preliminary, final each quarter) ==========
    {"name": "GDP Q4 Advance", "datetime": _ct(2026, 1, 29, 7, 30), "impact": "HIGH", "description": "First estimate of Q4 2025 GDP growth"},
    {"name": "GDP Q4 Preliminary", "datetime": _ct(2026, 2, 26, 7, 30), "impact": "MEDIUM", "description": "Second estimate of Q4 2025 GDP growth"},
    {"name": "GDP Q4 Final", "datetime": _ct(2026, 3, 26, 7, 30), "impact": "MEDIUM", "description": "Final estimate of Q4 2025 GDP growth"},
    {"name": "GDP Q1 Advance", "datetime": _ct(2026, 4, 29, 7, 30), "impact": "HIGH", "description": "First estimate of Q1 2026 GDP growth"},
    {"name": "GDP Q1 Preliminary", "datetime": _ct(2026, 5, 28, 7, 30), "impact": "MEDIUM", "description": "Second estimate of Q1 2026 GDP growth"},
    {"name": "GDP Q1 Final", "datetime": _ct(2026, 6, 25, 7, 30), "impact": "MEDIUM", "description": "Final estimate of Q1 2026 GDP growth"},
    {"name": "GDP Q2 Advance", "datetime": _ct(2026, 7, 30, 7, 30), "impact": "HIGH", "description": "First estimate of Q2 2026 GDP growth"},
    {"name": "GDP Q2 Preliminary", "datetime": _ct(2026, 8, 27, 7, 30), "impact": "MEDIUM", "description": "Second estimate of Q2 2026 GDP growth"},
    {"name": "GDP Q2 Final", "datetime": _ct(2026, 9, 24, 7, 30), "impact": "MEDIUM", "description": "Final estimate of Q2 2026 GDP growth"},
    {"name": "GDP Q3 Advance", "datetime": _ct(2026, 10, 29, 7, 30), "impact": "HIGH", "description": "First estimate of Q3 2026 GDP growth"},
    {"name": "GDP Q3 Preliminary", "datetime": _ct(2026, 11, 25, 7, 30), "impact": "MEDIUM", "description": "Second estimate of Q3 2026 GDP growth"},
    {"name": "GDP Q3 Final", "datetime": _ct(2026, 12, 23, 7, 30), "impact": "MEDIUM", "description": "Final estimate of Q3 2026 GDP growth"},

    # ========== PCE (Personal Consumption Expenditures — Fed's preferred inflation) ==========
    {"name": "PCE Price Index (Dec data)", "datetime": _ct(2026, 1, 30, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Jan data)", "datetime": _ct(2026, 2, 27, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Feb data)", "datetime": _ct(2026, 3, 27, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Mar data)", "datetime": _ct(2026, 4, 30, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Apr data)", "datetime": _ct(2026, 5, 29, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (May data)", "datetime": _ct(2026, 6, 26, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Jun data)", "datetime": _ct(2026, 7, 31, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Jul data)", "datetime": _ct(2026, 8, 28, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Aug data)", "datetime": _ct(2026, 9, 25, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Sep data)", "datetime": _ct(2026, 10, 30, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Oct data)", "datetime": _ct(2026, 11, 25, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},
    {"name": "PCE Price Index (Nov data)", "datetime": _ct(2026, 12, 24, 7, 30), "impact": "HIGH", "description": "Personal Consumption Expenditures — Fed's preferred inflation measure"},

    # ========== JOLTS JOB OPENINGS (12 monthly) ==========
    {"name": "JOLTS Job Openings (Nov data)", "datetime": _ct(2026, 1, 6, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Dec data)", "datetime": _ct(2026, 2, 3, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Jan data)", "datetime": _ct(2026, 3, 10, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Feb data)", "datetime": _ct(2026, 4, 7, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Mar data)", "datetime": _ct(2026, 5, 5, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Apr data)", "datetime": _ct(2026, 6, 2, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (May data)", "datetime": _ct(2026, 7, 7, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Jun data)", "datetime": _ct(2026, 8, 4, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Jul data)", "datetime": _ct(2026, 9, 1, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Aug data)", "datetime": _ct(2026, 10, 6, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Sep data)", "datetime": _ct(2026, 11, 3, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},
    {"name": "JOLTS Job Openings (Oct data)", "datetime": _ct(2026, 12, 1, 9, 0), "impact": "MEDIUM", "description": "Job Openings and Labor Turnover Survey"},

    # ========== RETAIL SALES (12 monthly) ==========
    {"name": "Retail Sales (Dec data)", "datetime": _ct(2026, 1, 16, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Jan data)", "datetime": _ct(2026, 2, 13, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Feb data)", "datetime": _ct(2026, 3, 17, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Mar data)", "datetime": _ct(2026, 4, 16, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Apr data)", "datetime": _ct(2026, 5, 15, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (May data)", "datetime": _ct(2026, 6, 16, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Jun data)", "datetime": _ct(2026, 7, 16, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Jul data)", "datetime": _ct(2026, 8, 14, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Aug data)", "datetime": _ct(2026, 9, 16, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Sep data)", "datetime": _ct(2026, 10, 16, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Oct data)", "datetime": _ct(2026, 11, 13, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},
    {"name": "Retail Sales (Nov data)", "datetime": _ct(2026, 12, 15, 7, 30), "impact": "MEDIUM", "description": "Advance monthly retail trade — consumer spending gauge"},

    # ========== ISM MANUFACTURING PMI (12 monthly, 1st business day) ==========
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 1, 2, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 2, 2, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 3, 2, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 4, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 5, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 6, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 7, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 8, 3, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 9, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 10, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 11, 2, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},
    {"name": "ISM Manufacturing PMI", "datetime": _ct(2026, 12, 1, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management manufacturing index — above 50 = expansion"},

    # ========== ISM SERVICES PMI (12 monthly, 3rd business day) ==========
    {"name": "ISM Services PMI", "datetime": _ct(2026, 1, 6, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 2, 4, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 3, 4, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 4, 3, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 5, 5, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 6, 3, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 7, 6, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 8, 5, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 9, 3, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 10, 5, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 11, 4, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},
    {"name": "ISM Services PMI", "datetime": _ct(2026, 12, 3, 9, 0), "impact": "MEDIUM", "description": "Institute for Supply Management services index — above 50 = expansion"},

    # ========== QUARTERLY EARNINGS SEASONS (approximate start dates) ==========
    {"name": "Q4 Earnings Season Begins", "datetime": _ct(2026, 1, 12, 5, 0), "impact": "MEDIUM", "description": "Major banks (JPM, GS, MS) kick off Q4 earnings. Expect elevated IV all week."},
    {"name": "Q1 Earnings Season Begins", "datetime": _ct(2026, 4, 13, 5, 0), "impact": "MEDIUM", "description": "Major banks kick off Q1 earnings. Expect elevated IV all week."},
    {"name": "Q2 Earnings Season Begins", "datetime": _ct(2026, 7, 13, 5, 0), "impact": "MEDIUM", "description": "Major banks kick off Q2 earnings. Expect elevated IV all week."},
    {"name": "Q3 Earnings Season Begins", "datetime": _ct(2026, 10, 12, 5, 0), "impact": "MEDIUM", "description": "Major banks kick off Q3 earnings. Expect elevated IV all week."},
]

# Sort all events by datetime
ECONOMIC_EVENTS_2026.sort(key=lambda e: e["datetime"])


# ========== MARKET HOLIDAYS 2026 ==========
MARKET_HOLIDAYS_2026 = [
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Jr. Day
    date(2026, 2, 16),  # Presidents' Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
]


def is_market_holiday(d: date) -> bool:
    """Check if a date is a US stock market holiday."""
    return d in MARKET_HOLIDAYS_2026


def get_central_now():
    """Get current time in US Central (DST-aware)."""
    return datetime.now(CT)


def get_todays_events(today_date=None):
    """Return list of economic events happening TODAY."""
    if today_date is None:
        today_date = get_central_now().date()

    return [
        e for e in ECONOMIC_EVENTS_2026
        if e["datetime"].date() == today_date
    ]


def get_next_event(from_date=None):
    """Return the next upcoming economic event after the given date/datetime."""
    if from_date is None:
        from_date = get_central_now()
    elif isinstance(from_date, date) and not isinstance(from_date, datetime):
        from_date = datetime.combine(from_date, datetime.min.time(), tzinfo=CT)

    for event in ECONOMIC_EVENTS_2026:
        if event["datetime"] > from_date:
            return event
    return None


def get_upcoming_events(from_date=None, days=7, count=5):
    """Return upcoming events within the next N days, limited to count."""
    if from_date is None:
        now = get_central_now()
    elif isinstance(from_date, date) and not isinstance(from_date, datetime):
        now = datetime.combine(from_date, datetime.min.time(), tzinfo=CT)
    else:
        now = from_date

    cutoff = now + timedelta(days=days)
    upcoming = []

    for event in ECONOMIC_EVENTS_2026:
        if event["datetime"] > now and event["datetime"] <= cutoff:
            upcoming.append(event)
            if len(upcoming) >= count:
                break

    return upcoming


def format_countdown(event_dt):
    """Format a human-readable countdown to an event datetime."""
    now = get_central_now()
    delta = event_dt - now

    if delta.total_seconds() < 0:
        return "Already passed"

    total_seconds = int(delta.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days == 0 and hours == 0:
        return f"{minutes} minutes away"
    elif days == 0:
        return f"{hours}h {minutes}m away"
    elif days == 1:
        return f"Tomorrow at {event_dt.strftime('%-I:%M %p')} CT"
    else:
        return f"{days} days, {hours}h away ({event_dt.strftime('%A, %b %-d')})"


def format_event_time(event_dt):
    """Format event time as readable string."""
    return event_dt.strftime("%-I:%M %p CT")
