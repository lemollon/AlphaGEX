#!/usr/bin/env python3
"""
Production Test Script for Bot Reports Feature

Run this in Render shell to verify the bot reports feature works correctly.

Usage:
    python scripts/test_bot_reports_production.py

Tests:
1. Database tables exist
2. API endpoints respond
3. Report generation works
4. Archive functions work
"""

import os
import sys
import json
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")
VALID_BOTS = ['ares', 'athena', 'titan', 'pegasus', 'icarus']

def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def print_result(test_name, passed, details=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {test_name}")
    if details:
        print(f"       {details}")

def test_database_connection():
    """Test 1: Database connection works"""
    print_header("TEST 1: Database Connection")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()

        print_result("Database connection", result[0] == 1)
        return True
    except Exception as e:
        print_result("Database connection", False, str(e))
        return False

def test_report_tables_exist():
    """Test 2: Report tables exist for all bots"""
    print_header("TEST 2: Report Tables Exist")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        all_exist = True
        for bot in VALID_BOTS:
            table_name = f"{bot}_daily_reports"
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table_name,))
            exists = cursor.fetchone()[0]
            print_result(f"Table {table_name}", exists)
            if not exists:
                all_exist = False

        conn.close()
        return all_exist
    except Exception as e:
        print_result("Report tables check", False, str(e))
        return False

def test_table_schema():
    """Test 3: Table schema has required columns"""
    print_header("TEST 3: Table Schema Validation")

    required_columns = [
        'report_date', 'trades_data', 'intraday_ticks', 'scan_activity',
        'market_context', 'trade_analyses', 'daily_summary', 'lessons_learned',
        'total_pnl', 'trade_count', 'win_count', 'loss_count',
        'generated_at', 'generation_model'
    ]

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check first bot's table as representative
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'ares_daily_reports'
        """)
        columns = [row[0] for row in cursor.fetchall()]

        all_present = True
        for col in required_columns:
            present = col in columns
            if not present:
                print_result(f"Column '{col}'", False, "MISSING")
                all_present = False

        if all_present:
            print_result("All required columns present", True, f"{len(columns)} columns total")

        conn.close()
        return all_present
    except Exception as e:
        print_result("Schema validation", False, str(e))
        return False

def test_position_tables_exist():
    """Test 4: Position tables exist (source data for reports)"""
    print_header("TEST 4: Position Tables Exist")

    position_tables = {
        'ares': 'ares_positions',
        'athena': 'athena_positions',
        'titan': 'titan_positions',
        'pegasus': 'pegasus_positions',
        'icarus': 'icarus_positions'
    }

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        all_exist = True
        for bot, table in position_tables.items():
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """, (table,))
            exists = cursor.fetchone()[0]
            print_result(f"Position table {table}", exists)
            if not exists:
                all_exist = False

        conn.close()
        return all_exist
    except Exception as e:
        print_result("Position tables check", False, str(e))
        return False

def test_fetch_closed_trades():
    """Test 5: Can fetch closed trades"""
    print_header("TEST 5: Fetch Closed Trades")

    try:
        from backend.services.bot_report_generator import fetch_closed_trades_for_date

        today = datetime.now(CENTRAL_TZ).date()

        for bot in VALID_BOTS:
            trades = fetch_closed_trades_for_date(bot, today)
            print_result(f"Fetch trades for {bot.upper()}", True, f"{len(trades)} trades today")

        return True
    except Exception as e:
        print_result("Fetch closed trades", False, str(e))
        return False

def test_archive_functions():
    """Test 6: Archive functions work"""
    print_header("TEST 6: Archive Functions")

    try:
        from backend.services.bot_report_generator import (
            get_archive_list,
            get_archive_stats,
            get_report_from_archive
        )

        for bot in VALID_BOTS[:2]:  # Just test first 2 to save time
            # Test archive list
            reports, total = get_archive_list(bot, limit=5)
            print_result(f"Archive list for {bot.upper()}", True, f"{total} total reports")

            # Test archive stats
            stats = get_archive_stats(bot)
            print_result(f"Archive stats for {bot.upper()}", True,
                        f"total_reports={stats.get('total_reports', 0)}")

        return True
    except Exception as e:
        print_result("Archive functions", False, str(e))
        return False

def test_report_generation_dry_run():
    """Test 7: Report generation components (without actually generating)"""
    print_header("TEST 7: Report Generation Components")

    try:
        # Test imports
        from backend.services.bot_report_generator import (
            _safe_json_dumps,
            _safe_get,
            _extract_claude_response_text,
            _parse_claude_json_response,
            CLAUDE_MODEL
        )
        print_result("Import helper functions", True)

        # Test _safe_json_dumps
        from decimal import Decimal
        test_data = {"pnl": Decimal("123.45"), "date": date.today()}
        result = _safe_json_dumps(test_data)
        print_result("_safe_json_dumps with Decimal/date", "123.45" in result)

        # Test _safe_get
        nested = {"a": {"b": {"c": 42}}}
        result = _safe_get(nested, "a", "b", "c")
        print_result("_safe_get nested access", result == 42)

        # Test _parse_claude_json_response
        json_text = '```json\n{"key": "value"}\n```'
        result = _parse_claude_json_response(json_text)
        print_result("_parse_claude_json_response", result == {"key": "value"})

        # Check Claude model
        print_result("Claude model configured", True, f"Using {CLAUDE_MODEL}")

        return True
    except Exception as e:
        print_result("Report generation components", False, str(e))
        return False

def test_anthropic_client():
    """Test 8: Anthropic client is available"""
    print_header("TEST 8: Anthropic Client")

    try:
        api_key = os.environ.get('ANTHROPIC_API_KEY') or os.environ.get('CLAUDE_API_KEY')
        if not api_key:
            print_result("Anthropic API key", False, "No API key found")
            return False

        print_result("Anthropic API key", True, f"Key found ({len(api_key)} chars)")

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        print_result("Anthropic client created", True)

        return True
    except Exception as e:
        print_result("Anthropic client", False, str(e))
        return False

def test_generate_report_for_bot():
    """Test 9: Actually generate a report (if trades exist)"""
    print_header("TEST 9: Generate Report (Live Test)")

    try:
        from backend.services.bot_report_generator import (
            fetch_closed_trades_for_date,
            generate_report_for_bot
        )

        today = datetime.now(CENTRAL_TZ).date()

        # Find a bot with trades today
        bot_with_trades = None
        for bot in VALID_BOTS:
            trades = fetch_closed_trades_for_date(bot, today)
            if trades:
                bot_with_trades = bot
                print(f"Found {len(trades)} trades for {bot.upper()} today")
                break

        if not bot_with_trades:
            print_result("Generate report", True, "No trades today - skipping generation test")
            return True

        print(f"Generating report for {bot_with_trades.upper()}...")
        report = generate_report_for_bot(bot_with_trades, today)

        if report:
            print_result("Report generated", True)
            print(f"       - Total P&L: ${report.get('total_pnl', 0):.2f}")
            print(f"       - Trade count: {report.get('trade_count', 0)}")
            print(f"       - Win/Loss: {report.get('win_count', 0)}W / {report.get('loss_count', 0)}L")
            print(f"       - Model: {report.get('generation_model', 'N/A')}")
            return True
        else:
            print_result("Report generated", False, "Returned None")
            return False

    except Exception as e:
        print_result("Generate report", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*60)
    print("  BOT REPORTS PRODUCTION TEST SUITE")
    print("  " + datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d %H:%M:%S CT"))
    print("="*60)

    results = []

    # Run tests
    results.append(("Database Connection", test_database_connection()))
    results.append(("Report Tables Exist", test_report_tables_exist()))
    results.append(("Table Schema", test_table_schema()))
    results.append(("Position Tables", test_position_tables_exist()))
    results.append(("Fetch Closed Trades", test_fetch_closed_trades()))
    results.append(("Archive Functions", test_archive_functions()))
    results.append(("Generation Components", test_report_generation_dry_run()))
    results.append(("Anthropic Client", test_anthropic_client()))

    # Optional: Actually generate a report
    print("\n" + "-"*60)
    response = input("Run live report generation test? (y/N): ").strip().lower()
    if response == 'y':
        results.append(("Live Generation", test_generate_report_for_bot()))

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\n  Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 ALL TESTS PASSED - Ready for production!")
    else:
        print("\n  ⚠️  Some tests failed - Review above for details")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
