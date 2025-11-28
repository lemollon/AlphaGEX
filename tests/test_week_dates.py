#!/usr/bin/env python3
"""
Test the current week date calculation logic
"""
from datetime import datetime, timedelta
import pytz

print("=" * 80)
print("TESTING WEEK DATE CALCULATION")
print("=" * 80)

# Simulate what the function does
current_time = datetime.now(pytz.timezone('America/New_York'))
current_weekday = current_time.weekday()  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
current_date_str = current_time.strftime('%Y-%m-%d')

print(f"\nCurrent time (ET): {current_time}")
print(f"Current weekday: {current_weekday} (0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri)")
print(f"Current date string: {current_date_str}")
print(f"Day name: {current_time.strftime('%A')}")

# Calculate week start (Monday)
is_weekend = current_weekday >= 5
is_friday_after_close = current_weekday == 4 and current_time.hour >= 16

if is_weekend:
    days_to_monday = (7 - current_weekday)
    week_start = current_time + timedelta(days=days_to_monday)
    edge_case = 'WEEKEND'
elif is_friday_after_close:
    days_since_monday = current_weekday
    week_start = current_time - timedelta(days=days_since_monday)
    edge_case = 'FRIDAY_AFTER_CLOSE'
else:
    days_since_monday = current_weekday
    week_start = current_time - timedelta(days=days_since_monday)
    edge_case = None

week_end = week_start + timedelta(days=4)

print(f"\nEdge case: {edge_case}")
print(f"Days since Monday: {current_weekday if not is_weekend else 'N/A'}")
print(f"Week start (Monday): {week_start.strftime('%Y-%m-%d %A')}")
print(f"Week end (Friday): {week_end.strftime('%Y-%m-%d %A')}")

# Build trading days
print("\nTrading days for this week:")
for i in range(5):
    day = week_start + timedelta(days=i)
    is_today = day.strftime('%Y-%m-%d') == current_date_str
    marker = " <-- TODAY" if is_today else ""
    print(f"  {day.strftime('%A %Y-%m-%d')}{marker}")

print("\n" + "=" * 80)
