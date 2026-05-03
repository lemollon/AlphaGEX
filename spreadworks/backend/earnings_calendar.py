"""Marquee earnings dates for market-moving names.

Big-tech earnings + bank season kickoffs move SPY ±1-3% on the day.
We treat these like economic events so the evening brief flags them
alongside CPI / FOMC / NFP. Times are best-known patterns:
- Big tech: usually after-hours (16:00-16:30 ET = 15:00-15:30 CT)
- Banks: usually pre-market (07:00-08:00 ET = 06:00-07:00 CT)

These are estimates — real earnings dates shift weekly. Update at
the start of each quarter from the company's IR calendar.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")


def _ct(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=CT)


# Q2 2026 earnings season (reporting Q1 results) - approximate
# Patterns based on prior-year cadence; real dates land mid-week of these slots
EARNINGS_2026 = [
    # ===== APRIL/MAY: Q1 EARNINGS =====
    {"name": "📊 JPM Earnings (Q1)", "datetime": _ct(2026, 4, 14, 6, 30), "impact": "MEDIUM",
     "description": "JPMorgan Chase — kicks off bank earnings, sets sector tone"},
    {"name": "📊 GS Earnings (Q1)", "datetime": _ct(2026, 4, 14, 6, 30), "impact": "MEDIUM",
     "description": "Goldman Sachs — bank season"},
    {"name": "📊 NFLX Earnings (Q1)", "datetime": _ct(2026, 4, 16, 15, 0), "impact": "MEDIUM",
     "description": "Netflix — first FAANG to report, streaming sector read"},
    {"name": "📊 TSLA Earnings (Q1)", "datetime": _ct(2026, 4, 22, 15, 0), "impact": "HIGH",
     "description": "Tesla — high-vol single-name, often moves SPY 0.5%+"},
    {"name": "📊 META Earnings (Q1)", "datetime": _ct(2026, 4, 29, 15, 0), "impact": "HIGH",
     "description": "Meta Platforms — ad-spend bellwether, AI capex watch"},
    {"name": "📊 MSFT Earnings (Q1)", "datetime": _ct(2026, 4, 29, 15, 0), "impact": "HIGH",
     "description": "Microsoft — Azure/AI growth, enterprise software read"},
    {"name": "📊 GOOGL Earnings (Q1)", "datetime": _ct(2026, 4, 30, 15, 0), "impact": "HIGH",
     "description": "Alphabet — search ad revenue, cloud, AI capex"},
    {"name": "📊 AMZN Earnings (Q1)", "datetime": _ct(2026, 4, 30, 15, 0), "impact": "HIGH",
     "description": "Amazon — AWS growth, e-commerce margins"},
    {"name": "📊 AAPL Earnings (Q1)", "datetime": _ct(2026, 5, 1, 15, 0), "impact": "HIGH",
     "description": "Apple — iPhone units, services growth, China"},
    {"name": "📊 NVDA Earnings (Q1)", "datetime": _ct(2026, 5, 21, 15, 0), "impact": "HIGH",
     "description": "Nvidia — AI capex king, single biggest single-name SPY mover"},
    {"name": "📊 WMT Earnings (Q1)", "datetime": _ct(2026, 5, 19, 6, 0), "impact": "MEDIUM",
     "description": "Walmart — consumer health, low-end shopper read"},

    # ===== JULY/AUGUST: Q2 EARNINGS =====
    {"name": "📊 JPM Earnings (Q2)", "datetime": _ct(2026, 7, 14, 6, 30), "impact": "MEDIUM",
     "description": "JPMorgan Chase — kicks off bank earnings, sets sector tone"},
    {"name": "📊 NFLX Earnings (Q2)", "datetime": _ct(2026, 7, 16, 15, 0), "impact": "MEDIUM",
     "description": "Netflix — streaming season"},
    {"name": "📊 TSLA Earnings (Q2)", "datetime": _ct(2026, 7, 22, 15, 0), "impact": "HIGH",
     "description": "Tesla — Q2 deliveries usually pre-announced; focus on margins"},
    {"name": "📊 GOOGL Earnings (Q2)", "datetime": _ct(2026, 7, 28, 15, 0), "impact": "HIGH",
     "description": "Alphabet — search ad revenue, cloud growth"},
    {"name": "📊 META Earnings (Q2)", "datetime": _ct(2026, 7, 29, 15, 0), "impact": "HIGH",
     "description": "Meta — ad-spend, capex guidance"},
    {"name": "📊 MSFT Earnings (Q2)", "datetime": _ct(2026, 7, 29, 15, 0), "impact": "HIGH",
     "description": "Microsoft — Azure/AI Copilot adoption"},
    {"name": "📊 AAPL Earnings (Q2)", "datetime": _ct(2026, 7, 30, 15, 0), "impact": "HIGH",
     "description": "Apple — fiscal Q3, iPhone refresh setup"},
    {"name": "📊 AMZN Earnings (Q2)", "datetime": _ct(2026, 7, 30, 15, 0), "impact": "HIGH",
     "description": "Amazon — AWS, retail, Prime Day pull-forward"},
    {"name": "📊 NVDA Earnings (Q2)", "datetime": _ct(2026, 8, 26, 15, 0), "impact": "HIGH",
     "description": "Nvidia — AI capex king, single biggest single-name SPY mover"},

    # ===== OCTOBER/NOVEMBER: Q3 EARNINGS =====
    {"name": "📊 JPM Earnings (Q3)", "datetime": _ct(2026, 10, 13, 6, 30), "impact": "MEDIUM",
     "description": "JPMorgan Chase — kicks off bank earnings"},
    {"name": "📊 NFLX Earnings (Q3)", "datetime": _ct(2026, 10, 15, 15, 0), "impact": "MEDIUM",
     "description": "Netflix — Q4 subscriber guide"},
    {"name": "📊 TSLA Earnings (Q3)", "datetime": _ct(2026, 10, 21, 15, 0), "impact": "HIGH",
     "description": "Tesla — Cybertruck/4680 progress, FSD"},
    {"name": "📊 GOOGL Earnings (Q3)", "datetime": _ct(2026, 10, 27, 15, 0), "impact": "HIGH",
     "description": "Alphabet — Gemini monetization, cloud"},
    {"name": "📊 MSFT Earnings (Q3)", "datetime": _ct(2026, 10, 27, 15, 0), "impact": "HIGH",
     "description": "Microsoft — Azure, Copilot run-rate"},
    {"name": "📊 META Earnings (Q3)", "datetime": _ct(2026, 10, 28, 15, 0), "impact": "HIGH",
     "description": "Meta — Reels monetization, Reality Labs losses"},
    {"name": "📊 AAPL Earnings (Q3)", "datetime": _ct(2026, 10, 29, 15, 0), "impact": "HIGH",
     "description": "Apple — iPhone 18 cycle, holiday guide"},
    {"name": "📊 AMZN Earnings (Q3)", "datetime": _ct(2026, 10, 29, 15, 0), "impact": "HIGH",
     "description": "Amazon — AWS, retail margins, Q4 guide"},
    {"name": "📊 NVDA Earnings (Q3)", "datetime": _ct(2026, 11, 18, 15, 0), "impact": "HIGH",
     "description": "Nvidia — Blackwell ramp, data-center demand"},
]

EARNINGS_2026.sort(key=lambda e: e["datetime"])


def get_upcoming_earnings(from_date=None, days=30):
    """Return upcoming earnings dates within the next N days."""
    from datetime import timedelta, date as _date
    if from_date is None:
        now = datetime.now(CT)
    elif isinstance(from_date, _date) and not isinstance(from_date, datetime):
        now = datetime.combine(from_date, datetime.min.time(), tzinfo=CT)
    else:
        now = from_date

    cutoff = now + timedelta(days=days)
    return [e for e in EARNINGS_2026 if now < e["datetime"] <= cutoff]
