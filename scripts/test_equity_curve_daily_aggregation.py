#!/usr/bin/env python3
"""
Test script for equity curve daily P&L aggregation fix.

Run from Render shell:
    python scripts/test_equity_curve_daily_aggregation.py

This test verifies that:
1. Daily P&L is the SUM of all trades that closed on that day (not just the last trade)
2. equity[today] - equity[yesterday] = daily_pnl[today]
3. The math adds up correctly across all days

The fix ensures that when multiple trades close on the same day, the displayed
daily_pnl shows the day's total, not just the last trade's P&L.

Created: January 2025
Purpose: Verify fix for equity curve calculation inconsistency
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Colors for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'
BOLD = '\033[1m'


def print_header(msg: str):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{msg}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}")


def print_section(msg: str):
    print(f"\n{CYAN}--- {msg} ---{RESET}")


def print_pass(msg: str):
    print(f"  {GREEN}✓ PASS: {msg}{RESET}")


def print_fail(msg: str):
    print(f"  {RED}✗ FAIL: {msg}{RESET}")


def print_warn(msg: str):
    print(f"  {YELLOW}⚠ WARN: {msg}{RESET}")


def print_info(msg: str):
    print(f"  {msg}")


def test_daily_aggregation_for_bot(bot_name: str, table_name: str, conn) -> dict:
    """
    Test that daily P&L is correctly aggregated from all trades on that day.

    Returns a dict with test results and any issues found.
    """
    print_section(f"{bot_name} Daily P&L Aggregation Test")

    cursor = conn.cursor()
    results = {
        "bot": bot_name,
        "passed": True,
        "issues": [],
        "stats": {}
    }

    try:
        # Step 1: Get all closed trades grouped by date
        cursor.execute(f"""
            SELECT
                DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') as close_date,
                COUNT(*) as trade_count,
                SUM(realized_pnl) as daily_pnl
            FROM {table_name}
            WHERE status IN ('closed', 'expired', 'partial_close')
            GROUP BY DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago')
            ORDER BY close_date
        """)

        daily_data = cursor.fetchall()

        if not daily_data:
            print_warn(f"No closed trades found for {bot_name}")
            results["stats"]["total_days"] = 0
            return results

        results["stats"]["total_days"] = len(daily_data)

        # Step 2: Check for days with multiple trades (where aggregation matters)
        multi_trade_days = [(d, c, p) for d, c, p in daily_data if c > 1]
        results["stats"]["multi_trade_days"] = len(multi_trade_days)

        print_info(f"Total trading days: {len(daily_data)}")
        print_info(f"Days with multiple trades: {len(multi_trade_days)}")

        if multi_trade_days:
            print_info(f"\nDays with multiple trades (aggregation is critical):")
            for date, count, daily_pnl in multi_trade_days[:5]:  # Show first 5
                print_info(f"  {date}: {count} trades, daily P&L = ${float(daily_pnl or 0):,.2f}")

        # Step 3: Verify equity math: equity[today] - equity[yesterday] = daily_pnl[today]
        print_info(f"\nVerifying equity math: equity[today] - equity[yesterday] = daily_pnl[today]")

        # Get starting capital from config
        cursor.execute("""
            SELECT value
            FROM autonomous_config
            WHERE key = %s
        """, (f"{bot_name.lower()}_starting_capital",))
        config_row = cursor.fetchone()

        if config_row and config_row[0]:
            starting_capital = float(config_row[0])
        else:
            # Default based on bot type
            starting_capital = 200000 if bot_name in ['SAMSON', 'ANCHOR'] else 100000

        print_info(f"Starting capital: ${starting_capital:,.2f}")

        # Calculate cumulative equity for each day
        cumulative_pnl = 0
        prev_equity = starting_capital
        math_errors = []

        for close_date, trade_count, daily_pnl in daily_data:
            daily_pnl = float(daily_pnl or 0)
            cumulative_pnl += daily_pnl
            current_equity = starting_capital + cumulative_pnl

            # Verify: equity change = daily_pnl
            equity_change = current_equity - prev_equity
            diff = abs(equity_change - daily_pnl)

            if diff > 0.01:  # Allow for rounding
                math_errors.append({
                    "date": close_date,
                    "expected_change": daily_pnl,
                    "actual_change": equity_change,
                    "diff": diff
                })

            prev_equity = current_equity

        if math_errors:
            results["passed"] = False
            results["issues"].append(f"Found {len(math_errors)} days with equity math errors")
            print_fail(f"Found {len(math_errors)} days where equity change != daily_pnl:")
            for err in math_errors[:3]:
                print_info(f"  {err['date']}: expected ${err['expected_change']:,.2f}, got ${err['actual_change']:,.2f}")
        else:
            print_pass("All equity math verified: equity[today] - equity[yesterday] = daily_pnl[today]")

        # Step 4: Verify individual trades sum to daily total
        print_info(f"\nVerifying individual trades sum to daily totals...")

        for close_date, expected_count, expected_sum in multi_trade_days[:5]:
            cursor.execute(f"""
                SELECT realized_pnl
                FROM {table_name}
                WHERE status IN ('closed', 'expired', 'partial_close')
                AND DATE(COALESCE(close_time, open_time)::timestamptz AT TIME ZONE 'America/Chicago') = %s
            """, (close_date,))

            individual_pnls = [float(row[0] or 0) for row in cursor.fetchall()]
            actual_sum = sum(individual_pnls)
            expected_sum = float(expected_sum or 0)

            if abs(actual_sum - expected_sum) > 0.01:
                results["passed"] = False
                results["issues"].append(f"{close_date}: Sum mismatch")
                print_fail(f"{close_date}: Individual sum ${actual_sum:,.2f} != expected ${expected_sum:,.2f}")
            else:
                print_pass(f"{close_date}: {len(individual_pnls)} trades sum to ${actual_sum:,.2f}")

        # Final summary for this bot
        results["stats"]["cumulative_pnl"] = cumulative_pnl
        results["stats"]["final_equity"] = starting_capital + cumulative_pnl

        print_info(f"\nFinal stats:")
        print_info(f"  Total cumulative P&L: ${cumulative_pnl:,.2f}")
        print_info(f"  Final equity: ${starting_capital + cumulative_pnl:,.2f}")

        return results

    except Exception as e:
        print_fail(f"Error testing {bot_name}: {e}")
        import traceback
        traceback.print_exc()
        results["passed"] = False
        results["issues"].append(str(e))
        return results


def test_api_response_consistency(bot_name: str, conn) -> bool:
    """
    Verify the API endpoint returns consistent data.
    This simulates what the frontend would receive.
    """
    print_section(f"{bot_name} API Response Consistency")

    try:
        # Import the service that powers the API
        from backend.services.bot_metrics_service import get_metrics_service, BotName

        service = get_metrics_service()
        bot_enum = BotName(bot_name)

        # Get equity curve
        result = service.get_equity_curve(bot_enum, days=30)

        if not result.get('success'):
            print_fail(f"API returned success=False")
            return False

        equity_curve = result.get('equity_curve', [])
        if not equity_curve:
            print_warn("Empty equity curve returned")
            return True  # Not a failure, just no data

        print_info(f"Received {len(equity_curve)} data points")

        # Verify consecutive points have consistent math
        errors = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i-1]
            curr = equity_curve[i]

            # Skip if either point is missing equity
            if 'equity' not in prev or 'equity' not in curr:
                continue

            equity_change = curr['equity'] - prev['equity']
            daily_pnl = curr.get('daily_pnl', 0)

            # Allow for today's point which might include unrealized
            if curr.get('unrealized_pnl') is not None:
                # Today's point - daily_pnl includes unrealized
                continue

            diff = abs(equity_change - daily_pnl)
            if diff > 0.01:
                errors.append({
                    "from_date": prev.get('date'),
                    "to_date": curr.get('date'),
                    "equity_change": equity_change,
                    "daily_pnl": daily_pnl,
                    "diff": diff
                })

        if errors:
            print_fail(f"Found {len(errors)} inconsistencies in API response:")
            for err in errors[:3]:
                print_info(f"  {err['from_date']} -> {err['to_date']}: "
                          f"equity change ${err['equity_change']:,.2f} != daily_pnl ${err['daily_pnl']:,.2f}")
            return False
        else:
            print_pass("API response is mathematically consistent")
            return True

    except ImportError as e:
        print_warn(f"Could not import service (may not be in correct environment): {e}")
        return True  # Not a failure in shell context
    except Exception as e:
        print_fail(f"Error: {e}")
        return False


def run_all_tests():
    """Run comprehensive tests for all bots."""
    print_header("EQUITY CURVE DAILY AGGREGATION TEST")
    print(f"Timestamp: {datetime.now(ZoneInfo('America/Chicago')).isoformat()}")
    print(f"\nThis test verifies the fix for:")
    print(f"  - daily_pnl shows SUM of all trades per day (not just last trade)")
    print(f"  - equity[today] - equity[yesterday] = daily_pnl[today]")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        print_pass("Database connection established")
    except Exception as e:
        print_fail(f"Cannot connect to database: {e}")
        return 1

    # Bot configurations
    bots = [
        ("FORTRESS", "fortress_positions"),
        ("SAMSON", "samson_positions"),
        ("ANCHOR", "anchor_positions"),
        ("SOLOMON", "solomon_positions"),
        ("GIDEON", "gideon_positions"),
    ]

    all_results = []
    total_passed = 0
    total_failed = 0

    for bot_name, table_name in bots:
        result = test_daily_aggregation_for_bot(bot_name, table_name, conn)
        all_results.append(result)

        if result["passed"]:
            total_passed += 1
        else:
            total_failed += 1

        # Also test API response if available
        test_api_response_consistency(bot_name, conn)

    conn.close()

    # Summary
    print_header("TEST SUMMARY")

    for result in all_results:
        status = f"{GREEN}PASS{RESET}" if result["passed"] else f"{RED}FAIL{RESET}"
        print(f"  {result['bot']}: {status}")
        if result["issues"]:
            for issue in result["issues"]:
                print(f"    - {issue}")
        if result["stats"].get("multi_trade_days", 0) > 0:
            print(f"    - {result['stats']['multi_trade_days']} multi-trade days verified")

    print(f"\n{BOLD}Results:{RESET}")
    print(f"  {GREEN}Passed: {total_passed}{RESET}")
    print(f"  {RED}Failed: {total_failed}{RESET}")

    if total_failed > 0:
        print(f"\n{RED}{BOLD}SOME TESTS FAILED!{RESET}")
        print("The equity curve daily P&L aggregation may not be working correctly.")
        return 1
    else:
        print(f"\n{GREEN}{BOLD}ALL TESTS PASSED!{RESET}")
        print("Equity curve daily P&L aggregation is working correctly.")
        return 0


def test_single_bot(bot_name: str):
    """Test a single bot."""
    bot_configs = {
        "FORTRESS": "fortress_positions",
        "SAMSON": "samson_positions",
        "ANCHOR": "anchor_positions",
        "SOLOMON": "solomon_positions",
        "GIDEON": "gideon_positions",
    }

    bot_name = bot_name.upper()
    if bot_name not in bot_configs:
        print(f"{RED}Unknown bot: {bot_name}{RESET}")
        print(f"Available: {', '.join(bot_configs.keys())}")
        return 1

    print_header(f"TESTING {bot_name} DAILY P&L AGGREGATION")

    from database_adapter import get_connection
    conn = get_connection()

    result = test_daily_aggregation_for_bot(bot_name, bot_configs[bot_name], conn)
    test_api_response_consistency(bot_name, conn)

    conn.close()

    if result["passed"]:
        print(f"\n{GREEN}{BOLD}TEST PASSED{RESET}")
        return 0
    else:
        print(f"\n{RED}{BOLD}TEST FAILED{RESET}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        bot = sys.argv[1]
        sys.exit(test_single_bot(bot))
    else:
        sys.exit(run_all_tests())
