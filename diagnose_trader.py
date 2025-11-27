#!/usr/bin/env python3
"""
Autonomous Trader Diagnostic Tool
Run this to check why the trader isn't trading

Usage:
    python diagnose_trader.py

Or on Render shell:
    python diagnose_trader.py
"""

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Ensure we can import from the project
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_environment():
    """Check environment variables"""
    print_section("ENVIRONMENT CHECK")

    database_url = os.getenv('DATABASE_URL')
    polygon_key = os.getenv('POLYGON_API_KEY')
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')

    print(f"DATABASE_URL: {'✅ Set' if database_url else '❌ MISSING'}")
    print(f"POLYGON_API_KEY: {'✅ Set' if polygon_key else '❌ MISSING'}")
    print(f"ANTHROPIC_API_KEY: {'✅ Set (for AI reasoning)' if anthropic_key else '⚠️ Not set (AI reasoning disabled)'}")

    if not database_url:
        print("\n❌ CRITICAL: DATABASE_URL is required!")
        return False
    if not polygon_key:
        print("\n❌ CRITICAL: POLYGON_API_KEY is required for option data!")
        return False
    return True

def check_market_hours():
    """Check if market is currently open"""
    print_section("MARKET HOURS CHECK")

    try:
        ct_now = datetime.now(ZoneInfo("America/Chicago"))
    except:
        from datetime import timezone
        ct_now = datetime.now(timezone(timedelta(hours=-6)))

    print(f"Current Time (CT): {ct_now.strftime('%I:%M:%S %p, %A %B %d, %Y')}")
    print(f"Day of Week: {ct_now.strftime('%A')} (0=Mon, 6=Sun): {ct_now.weekday()}")

    # Check weekend
    if ct_now.weekday() >= 5:
        print(f"\n🔴 MARKET CLOSED: It's the weekend")
        return False

    # Check time (8:30 AM - 3:00 PM CT)
    from datetime import time as dt_time
    market_open = dt_time(8, 30)
    market_close = dt_time(15, 0)
    current_time = ct_now.time()

    print(f"Market Hours: {market_open.strftime('%I:%M %p')} - {market_close.strftime('%I:%M %p')} CT")

    if current_time < market_open:
        print(f"\n🔴 MARKET CLOSED: Before market open ({current_time.strftime('%I:%M %p')} < {market_open.strftime('%I:%M %p')})")
        return False
    elif current_time > market_close:
        print(f"\n🔴 MARKET CLOSED: After market close ({current_time.strftime('%I:%M %p')} > {market_close.strftime('%I:%M %p')})")
        return False
    else:
        print(f"\n🟢 MARKET OPEN: Trading should be active")
        return True

def check_database():
    """Check database connection and tables"""
    print_section("DATABASE CHECK")

    try:
        from database_adapter import get_connection
        import psycopg2.extras

        conn = get_connection()
        c = conn.cursor()

        print("✅ Database connection successful")

        # Check key tables
        tables_to_check = [
            'autonomous_live_status',
            'autonomous_trade_log',
            'autonomous_open_positions',
            'autonomous_closed_trades',
            'autonomous_config',
            'autonomous_trader_logs'
        ]

        print("\nTable Status:")
        for table in tables_to_check:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                count = c.fetchone()[0]
                print(f"  {table}: ✅ {count} rows")
            except Exception as e:
                print(f"  {table}: ❌ Error - {e}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Database error: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_trader_status():
    """Check autonomous trader live status"""
    print_section("TRADER STATUS")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        c.execute("SELECT * FROM autonomous_live_status WHERE id = 1")
        row = c.fetchone()

        if row:
            print(f"Timestamp: {row[1]}")
            print(f"Status: {row[2]}")
            print(f"Current Action: {row[3]}")
            print(f"Market Analysis: {row[4]}")
            print(f"Next Check Time: {row[5]}")
            print(f"Last Decision: {row[6]}")
            print(f"Is Working: {'✅ Yes' if row[7] else '❌ No'}")

            # Check if status is stale (older than 10 minutes)
            if row[1]:
                try:
                    last_update = datetime.fromisoformat(row[1].replace('Z', '+00:00'))
                    now = datetime.now(last_update.tzinfo) if last_update.tzinfo else datetime.now()
                    age_minutes = (now - last_update).total_seconds() / 60

                    if age_minutes > 10:
                        print(f"\n⚠️ WARNING: Status is {age_minutes:.0f} minutes old - scheduler may not be running!")
                    else:
                        print(f"\n✅ Status is fresh ({age_minutes:.1f} minutes old)")
                except:
                    pass
        else:
            print("❌ No live status found - trader may not have started")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error checking status: {e}")
        return False

def check_trader_config():
    """Check trader configuration"""
    print_section("TRADER CONFIG")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        c.execute("SELECT key, value FROM autonomous_config")
        configs = c.fetchall()

        config_dict = {row[0]: row[1] for row in configs}

        print(f"Capital: ${float(config_dict.get('capital', 1000000)):,.2f}")
        print(f"Mode: {config_dict.get('mode', 'paper')}")
        print(f"Signal Only: {config_dict.get('signal_only', 'false')}")
        print(f"Last Trade Date: {config_dict.get('last_trade_date', 'Never')}")
        print(f"Auto Execute: {config_dict.get('auto_execute', 'true')}")
        print(f"Use Theoretical Pricing: {config_dict.get('use_theoretical_pricing', 'true')}")

        # Check signal_only mode
        if config_dict.get('signal_only', 'false').lower() == 'true':
            print("\n⚠️ WARNING: signal_only mode is ENABLED - trades will NOT auto-execute!")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error checking config: {e}")
        return False

def check_recent_activity():
    """Check recent trade activity"""
    print_section("RECENT ACTIVITY (Last 24 Hours)")

    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        # Check trade log
        c.execute("""
            SELECT timestamp, action, details, success
            FROM autonomous_trade_log
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        logs = c.fetchall()

        if logs:
            print("\nRecent Trade Log:")
            for log in logs:
                status = "✅" if log[3] else "❌"
                print(f"  {status} {log[0]} | {log[1]}: {str(log[2])[:60]}...")
        else:
            print("\n⚠️ No trade log entries in last 24 hours")

        # Check open positions
        c.execute("SELECT COUNT(*) FROM autonomous_open_positions")
        open_count = c.fetchone()[0]
        print(f"\nOpen Positions: {open_count}")

        # Check today's closed trades
        c.execute("""
            SELECT COUNT(*), COALESCE(SUM(realized_pnl), 0)
            FROM autonomous_closed_trades
            WHERE exit_date = CURRENT_DATE
        """)
        result = c.fetchone()
        print(f"Today's Closed Trades: {result[0]} (P&L: ${result[1]:+,.2f})")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error checking activity: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_polygon_api():
    """Check Polygon.io API connectivity"""
    print_section("POLYGON.IO API CHECK")

    try:
        from polygon_data_fetcher import polygon_fetcher

        # Try to get SPY quote
        print("Testing SPY quote fetch...")
        quote = polygon_fetcher.get_current_price('SPY')

        if quote and quote > 0:
            print(f"✅ SPY Price: ${quote:.2f}")
        else:
            print(f"⚠️ Could not get SPY price: {quote}")

        # Test VIX
        print("\nTesting VIX fetch...")
        vix = polygon_fetcher.get_current_price('^VIX')
        if vix:
            print(f"✅ VIX: {vix:.2f}")
        else:
            print("⚠️ Could not get VIX")

        # Test option quote
        print("\nTesting option quote fetch...")
        from datetime import datetime, timedelta
        exp_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        option = polygon_fetcher.get_option_quote(
            symbol='SPY',
            strike=round(quote) if quote else 590,
            expiration=exp_date,
            option_type='call'
        )

        if option and not option.get('error'):
            print(f"✅ Option quote: bid=${option.get('bid', 0):.2f}, ask=${option.get('ask', 0):.2f}")
            if option.get('is_delayed'):
                print("   ⚠️ Data is 15-minute delayed (Options Developer tier)")
        else:
            print(f"⚠️ Option quote error: {option}")

        return True

    except Exception as e:
        print(f"❌ Polygon API error: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_diagnostics():
    """Run all diagnostic checks"""
    print("\n" + "="*60)
    print("  AUTONOMOUS TRADER DIAGNOSTIC REPORT")
    print("  " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*60)

    results = {}

    results['environment'] = check_environment()
    results['market_hours'] = check_market_hours()
    results['database'] = check_database()
    results['trader_status'] = check_trader_status()
    results['trader_config'] = check_trader_config()
    results['recent_activity'] = check_recent_activity()
    results['polygon_api'] = check_polygon_api()

    print_section("SUMMARY")

    all_ok = all(results.values())

    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {check}: {status}")

    if all_ok:
        print("\n✅ All checks passed - trader should be operational")
    else:
        print("\n❌ Some checks failed - see details above")

    # Recommendations
    print_section("RECOMMENDATIONS")

    if not results['market_hours']:
        print("• Market is closed - trader will resume during market hours (8:30 AM - 3:00 PM CT, Mon-Fri)")

    if not results['environment']:
        print("• Check environment variables in Render dashboard")

    if not results['database']:
        print("• Check DATABASE_URL and run: python -c 'from config_and_database import init_database; init_database()'")

    if not results['polygon_api']:
        print("• Check POLYGON_API_KEY is valid and has sufficient quota")

    print("\nTo manually trigger a trade cycle:")
    print("  curl -X POST https://alphagex-api.onrender.com/api/trader/execute")

    return all_ok

if __name__ == "__main__":
    run_diagnostics()
