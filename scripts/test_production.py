#!/usr/bin/env python3
"""
Production System Test Script
==============================
Run this on Render to verify all components work end-to-end.

Usage:
    python scripts/test_production.py [--base-url https://your-app.onrender.com]

If no --base-url provided, tests local components only.
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Results tracking
results = {"passed": 0, "failed": 0, "warnings": 0, "details": []}

def test(name, condition, details=""):
    """Record test result"""
    if condition == True:
        results["passed"] += 1
        status = "PASS"
        symbol = "✓"
    elif condition == "warn":
        results["warnings"] += 1
        status = "WARN"
        symbol = "⚠"
    else:
        results["failed"] += 1
        status = "FAIL"
        symbol = "✗"

    results["details"].append({"name": name, "status": status, "details": details})
    print(f"  {symbol} {name}" + (f" - {details}" if details and status != "PASS" else ""))

def section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)


# =============================================================================
# 1. DATABASE CONNECTION
# =============================================================================
def test_database():
    section("1. DATABASE CONNECTION")
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        conn.close()
        test("Database connection", result[0] == 1)
    except Exception as e:
        test("Database connection", False, str(e)[:80])


# =============================================================================
# 2. DATA PROVIDERS
# =============================================================================
def test_data_providers():
    section("2. DATA PROVIDERS")

    # Polygon
    try:
        from data.polygon_data_fetcher import polygon_fetcher
        price = polygon_fetcher.get_current_price('SPY')
        test("Polygon - SPY price", price is not None and price > 0, f"${price}" if price else "No data")
    except Exception as e:
        test("Polygon - SPY price", False, str(e)[:80])

    # Tradier
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        fetcher = TradierDataFetcher()
        quote = fetcher.get_quote('SPY')
        test("Tradier - SPY quote", quote is not None, "Connected" if quote else "No data")
    except Exception as e:
        test("Tradier - SPY quote", "warn", str(e)[:80])

    # Unified provider
    try:
        from data.unified_data_provider import get_price, get_vix
        price = get_price('SPY')
        test("Unified provider - price", price is not None and price > 0, f"${price}" if price else "No data")

        vix = get_vix()
        test("Unified provider - VIX", vix is not None and vix > 0, f"{vix}" if vix else "No data")
    except Exception as e:
        test("Unified provider", False, str(e)[:80])

    # GEX data
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()
        gex = api.get_net_gamma('SPY')
        has_gex = gex and 'net_gex' in gex and not gex.get('error')
        test("Trading Volatility API - GEX", has_gex, f"Net GEX: {gex.get('net_gex', 'N/A')}" if has_gex else str(gex.get('error', 'No data'))[:50])
    except Exception as e:
        test("Trading Volatility API - GEX", "warn", str(e)[:80])


# =============================================================================
# 3. CORE TRADING COMPONENTS
# =============================================================================
def test_core_components():
    section("3. CORE TRADING COMPONENTS")

    # Market Regime Classifier
    try:
        from core.market_regime_classifier import get_classifier, MarketAction
        classifier = get_classifier('SPY')
        test("Market Regime Classifier", classifier is not None)
    except Exception as e:
        test("Market Regime Classifier", False, str(e)[:80])

    # Strategy Stats
    try:
        from core.strategy_stats import get_strategy_stats
        stats = get_strategy_stats()
        has_stats = stats and len(stats) > 0
        sources = set(s.get('source', 'unknown') for s in stats.values()) if has_stats else set()
        test("Strategy Stats loaded", has_stats, f"{len(stats)} strategies, sources: {sources}")

        # Check if any are from backtest (not initial_estimate)
        backtest_count = sum(1 for s in stats.values() if s.get('source') == 'backtest')
        test("Strategy Stats from backtests", backtest_count > 0 or "warn", f"{backtest_count} from backtest" if backtest_count else "All initial estimates - run backtests!")
    except Exception as e:
        test("Strategy Stats", False, str(e)[:80])

    # Psychology Trap Detector
    try:
        from core.psychology_trap_detector import analyze_current_market_complete
        test("Psychology Trap Detector", True, "Module loaded")
    except Exception as e:
        test("Psychology Trap Detector", "warn", str(e)[:80])

    # Unified Trader (SPY)
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader
        trader = AutonomousPaperTrader(symbol='SPY', capital=1_000_000)
        test("SPY Trader init", trader.symbol == 'SPY', f"Capital: ${trader.starting_capital:,}")
    except Exception as e:
        test("SPY Trader init", False, str(e)[:80])

    # Unified Trader (SPX)
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader
        trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
        test("SPX Trader init", trader.symbol == 'SPX', f"Capital: ${trader.starting_capital:,}")

        # Test RiskManagerMixin methods
        has_risk = hasattr(trader, 'check_risk_limits') and hasattr(trader, 'get_portfolio_greeks')
        test("SPX RiskManagerMixin", has_risk)
    except Exception as e:
        test("SPX Trader init", False, str(e)[:80])


# =============================================================================
# 4. BACKTEST SYSTEM
# =============================================================================
def test_backtest():
    section("4. BACKTEST SYSTEM")

    try:
        from backtest.backtest_framework import BacktestResults, Trade
        test("Backtest framework", True)
    except Exception as e:
        test("Backtest framework", False, str(e)[:80])

    try:
        from backtest.autonomous_backtest_engine import PatternBacktester, get_backtester
        backtester = get_backtester()
        test("Backtest engine", backtester is not None)
    except Exception as e:
        test("Backtest engine", False, str(e)[:80])


# =============================================================================
# 5. DATABASE TABLES & DATA
# =============================================================================
def test_database_tables():
    section("5. DATABASE TABLES & DATA")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check key tables exist and have data
        tables = [
            ('autonomous_open_positions', 'Open positions'),
            ('autonomous_trade_history', 'Trade history'),
            ('autonomous_equity_snapshots', 'Equity snapshots'),
            ('backtest_results', 'Backtest results'),
            ('gex_history', 'GEX history'),
            ('regime_signals', 'Regime signals'),
        ]

        for table, desc in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                test(f"Table: {table}", True, f"{count} rows")
            except Exception as e:
                test(f"Table: {table}", "warn", f"Not found or empty")

        conn.close()
    except Exception as e:
        test("Database tables", False, str(e)[:80])


# =============================================================================
# 6. API ENDPOINTS (if base_url provided)
# =============================================================================
def test_api_endpoints(base_url):
    section("6. API ENDPOINTS")

    if not base_url:
        print("  (Skipped - no --base-url provided)")
        return

    try:
        import requests
    except ImportError:
        print("  (Skipped - requests not installed)")
        return

    endpoints = [
        ("/api/health", "Health check"),
        ("/api/trader/status", "Trader status"),
        ("/api/trader/positions", "Open positions"),
        ("/api/trader/history", "Trade history"),
        ("/api/trader/equity-curve", "Equity curve"),
        ("/api/spx/status", "SPX status"),
        ("/api/spx/performance", "SPX performance"),
        ("/api/regime/current", "Current regime"),
        ("/api/gex/current", "Current GEX"),
        ("/api/vix/current", "Current VIX"),
        ("/api/backtests/results", "Backtest results"),
        ("/api/strategies/stats", "Strategy stats"),
        ("/api/psychology/analysis", "Psychology analysis"),
    ]

    for endpoint, desc in endpoints:
        try:
            url = f"{base_url.rstrip('/')}{endpoint}"
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                success = data.get('success', True)
                test(f"GET {endpoint}", success, desc)
            else:
                test(f"GET {endpoint}", False, f"HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            test(f"GET {endpoint}", "warn", "Timeout")
        except Exception as e:
            test(f"GET {endpoint}", False, str(e)[:50])


# =============================================================================
# 7. FEEDBACK LOOP VERIFICATION
# =============================================================================
def test_feedback_loop():
    section("7. FEEDBACK LOOP (Backtest → Strategy Stats → Kelly)")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check if backtests have run recently
        cursor.execute("""
            SELECT COUNT(*), MAX(completed_at)
            FROM backtest_results
            WHERE completed_at > NOW() - INTERVAL '7 days'
        """)
        result = cursor.fetchone()
        recent_backtests = result[0] if result else 0
        last_backtest = result[1] if result else None

        test("Recent backtests (7 days)", recent_backtests > 0,
             f"{recent_backtests} backtests, last: {last_backtest}" if recent_backtests else "No recent backtests!")

        conn.close()
    except Exception as e:
        test("Backtest history", "warn", str(e)[:80])

    # Check strategy stats are being updated
    try:
        from core.strategy_stats import get_strategy_stats
        stats = get_strategy_stats()

        backtest_sources = [k for k, v in stats.items() if v.get('source') == 'backtest']
        estimate_sources = [k for k, v in stats.items() if v.get('source') == 'initial_estimate']

        if backtest_sources:
            test("Strategy stats updated from backtests", True, f"{len(backtest_sources)} strategies")
        else:
            test("Strategy stats updated from backtests", "warn",
                 f"All {len(estimate_sources)} strategies using initial estimates")
    except Exception as e:
        test("Strategy stats feedback", False, str(e)[:80])


# =============================================================================
# 8. SCHEDULER STATUS
# =============================================================================
def test_scheduler():
    section("8. SCHEDULER")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check for recent scheduler activity
        cursor.execute("""
            SELECT COUNT(*) FROM autonomous_trade_log
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        result = cursor.fetchone()
        recent_logs = result[0] if result else 0
        test("Scheduler activity (24h)", recent_logs > 0 or "warn",
             f"{recent_logs} log entries" if recent_logs else "No activity - is scheduler running?")

        conn.close()
    except Exception as e:
        test("Scheduler activity", "warn", str(e)[:80])


# =============================================================================
# 9. UI PAGES CHECK (if base_url provided)
# =============================================================================
def test_ui_pages(base_url):
    section("9. UI PAGES")

    if not base_url:
        print("  (Skipped - no --base-url provided)")
        return

    try:
        import requests
    except ImportError:
        print("  (Skipped - requests not installed)")
        return

    pages = [
        ("/", "Dashboard"),
        ("/trader", "Trader page"),
        ("/spx", "SPX page"),
        ("/backtest", "Backtest page"),
        ("/psychology", "Psychology page"),
        ("/regime", "Regime page"),
    ]

    for path, desc in pages:
        try:
            url = f"{base_url.rstrip('/')}{path}"
            resp = requests.get(url, timeout=15)
            test(f"Page: {path}", resp.status_code == 200, desc)
        except Exception as e:
            test(f"Page: {path}", "warn", str(e)[:50])


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="Test AlphaGEX production system")
    parser.add_argument("--base-url", help="Base URL for API tests (e.g., https://your-app.onrender.com)")
    args = parser.parse_args()

    print("\n" + "="*60)
    print(" ALPHAGEX PRODUCTION SYSTEM TEST")
    print(" " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)

    # Run all tests
    test_database()
    test_data_providers()
    test_core_components()
    test_backtest()
    test_database_tables()
    test_api_endpoints(args.base_url)
    test_feedback_loop()
    test_scheduler()
    test_ui_pages(args.base_url)

    # Summary
    section("SUMMARY")
    print(f"\n  ✓ Passed:   {results['passed']}")
    print(f"  ✗ Failed:   {results['failed']}")
    print(f"  ⚠ Warnings: {results['warnings']}")

    if results['failed'] == 0:
        print("\n  🎉 ALL CRITICAL TESTS PASSED!")
    else:
        print(f"\n  ⚠️  {results['failed']} test(s) failed - review above")

    # List failures
    failures = [d for d in results['details'] if d['status'] == 'FAIL']
    if failures:
        print("\n  Failed tests:")
        for f in failures:
            print(f"    - {f['name']}: {f['details']}")

    print("\n" + "="*60 + "\n")

    return 0 if results['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
