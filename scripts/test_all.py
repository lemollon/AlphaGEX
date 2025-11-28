#!/usr/bin/env python3
"""
AlphaGEX Complete System Test
==============================
One script to test EVERYTHING - run this on Render after deploy.

Tests:
1. Database connection & tables
2. Data providers (Polygon, Tradier, GEX, VIX)
3. Core trading components (Trader, Regime, Strategy Stats)
4. Backtest system & feedback loop
5. API endpoints
6. UI pages
7. Scheduler activity

Usage:
    python scripts/test_all.py https://your-app.onrender.com

    # Or test locally without API/UI tests:
    python scripts/test_all.py
"""

import sys
import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ============================================================================
# CONFIGURATION
# ============================================================================
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else None

# Try to import requests for API tests
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# ============================================================================
# TEST TRACKING
# ============================================================================
class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.skipped = 0
        self.details = []
        self.current_section = ""

    def section(self, name: str):
        self.current_section = name
        print(f"\n{'='*70}")
        print(f" {name}")
        print('='*70)

    def test(self, name: str, result, details: str = ""):
        if result == True:
            self.passed += 1
            symbol, status = "✓", "PASS"
        elif result == "warn":
            self.warnings += 1
            symbol, status = "⚠", "WARN"
        elif result == "skip":
            self.skipped += 1
            symbol, status = "○", "SKIP"
        else:
            self.failed += 1
            symbol, status = "✗", "FAIL"

        self.details.append({
            "section": self.current_section,
            "name": name,
            "status": status,
            "details": details
        })

        detail_str = f" - {details}" if details and status != "PASS" else ""
        print(f"  {symbol} {name}{detail_str}")

    def summary(self):
        print(f"\n{'='*70}")
        print(" SUMMARY")
        print('='*70)
        print(f"\n  ✓ Passed:   {self.passed}")
        print(f"  ✗ Failed:   {self.failed}")
        print(f"  ⚠ Warnings: {self.warnings}")
        print(f"  ○ Skipped:  {self.skipped}")

        if self.failed == 0:
            print("\n  🎉 ALL CRITICAL TESTS PASSED!")
        else:
            print(f"\n  ⚠️  {self.failed} CRITICAL TEST(S) FAILED")
            print("\n  Failed tests:")
            for d in self.details:
                if d["status"] == "FAIL":
                    print(f"    - [{d['section']}] {d['name']}: {d['details']}")

        if self.warnings > 0:
            print(f"\n  Warnings ({self.warnings}):")
            for d in self.details:
                if d["status"] == "WARN":
                    print(f"    - [{d['section']}] {d['name']}: {d['details']}")

        print("\n" + "="*70)
        return self.failed == 0

R = TestResults()

# ============================================================================
# 1. DATABASE
# ============================================================================
def test_database():
    R.section("1. DATABASE CONNECTION")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        R.test("PostgreSQL connection", cursor.fetchone()[0] == 1)

        # Check tables exist and have data
        tables = {
            'autonomous_open_positions': 'Open positions',
            'autonomous_trade_history': 'Trade history',
            'autonomous_equity_snapshots': 'Equity snapshots',
            'autonomous_trade_log': 'Trade logs',
            'backtest_results': 'Backtest results',
            'gex_history': 'GEX history',
            'regime_signals': 'Regime signals',
            'spx_institutional_positions': 'SPX positions',
        }

        for table, desc in tables.items():
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                R.test(f"Table: {table}", True, f"{count} rows")
            except Exception as e:
                R.test(f"Table: {table}", "warn", "Missing or empty")

        conn.close()
    except Exception as e:
        R.test("Database connection", False, str(e)[:100])

# ============================================================================
# 2. DATA PROVIDERS
# ============================================================================
def test_data_providers():
    R.section("2. DATA PROVIDERS")

    # Polygon
    try:
        from data.polygon_data_fetcher import polygon_fetcher
        price = polygon_fetcher.get_current_price('SPY')
        R.test("Polygon - SPY price", price and price > 0, f"${price:.2f}" if price else "No data")
    except Exception as e:
        R.test("Polygon - SPY price", False, str(e)[:80])

    # Tradier
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        fetcher = TradierDataFetcher()
        if fetcher.api_key:
            quote = fetcher.get_quote('SPY')
            R.test("Tradier - SPY quote", quote is not None, "OK" if quote else "No data")
        else:
            R.test("Tradier - SPY quote", "warn", "No API key configured")
    except Exception as e:
        R.test("Tradier - SPY quote", "warn", str(e)[:80])

    # Unified Data Provider
    try:
        from data.unified_data_provider import get_price, get_vix
        price = get_price('SPY')
        R.test("Unified - get_price('SPY')", price and price > 0, f"${price:.2f}" if price else "No data")

        vix = get_vix()
        R.test("Unified - get_vix()", vix and vix > 0, f"VIX: {vix:.2f}" if vix else "No data")
    except Exception as e:
        R.test("Unified Data Provider", False, str(e)[:80])

    # GEX Data (Trading Volatility API)
    try:
        from core_classes_and_engines import TradingVolatilityAPI
        api = TradingVolatilityAPI()
        gex = api.get_net_gamma('SPY')
        if gex and 'net_gex' in gex and not gex.get('error'):
            R.test("Trading Volatility - GEX", True, f"Net GEX: {gex['net_gex']:,.0f}")
        else:
            R.test("Trading Volatility - GEX", "warn", gex.get('error', 'No data')[:50] if gex else "No data")
    except Exception as e:
        R.test("Trading Volatility - GEX", "warn", str(e)[:80])

# ============================================================================
# 3. CORE TRADING COMPONENTS
# ============================================================================
def test_core_components():
    R.section("3. CORE TRADING COMPONENTS")

    # Market Regime Classifier
    try:
        from core.market_regime_classifier import get_classifier, MarketAction
        classifier = get_classifier('SPY')
        R.test("Market Regime Classifier", classifier is not None)
    except Exception as e:
        R.test("Market Regime Classifier", False, str(e)[:80])

    # Strategy Stats
    try:
        from core.strategy_stats import get_strategy_stats
        stats = get_strategy_stats()
        if stats:
            sources = {}
            for k, v in stats.items():
                src = v.get('source', 'unknown')
                sources[src] = sources.get(src, 0) + 1

            backtest_count = sources.get('backtest', 0)
            estimate_count = sources.get('initial_estimate', 0)

            R.test("Strategy Stats loaded", True, f"{len(stats)} strategies")

            if backtest_count > 0:
                R.test("Stats from backtests", True, f"{backtest_count} from backtest")
            else:
                R.test("Stats from backtests", "warn", f"All {estimate_count} using initial estimates - run backtests!")
        else:
            R.test("Strategy Stats loaded", False, "Empty")
    except Exception as e:
        R.test("Strategy Stats", False, str(e)[:80])

    # Psychology Trap Detector
    try:
        from core.psychology_trap_detector import analyze_current_market_complete
        R.test("Psychology Trap Detector", True)
    except Exception as e:
        R.test("Psychology Trap Detector", "warn", str(e)[:80])

    # SPY Trader
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader
        trader = AutonomousPaperTrader(symbol='SPY', capital=1_000_000)
        R.test("SPY Trader init", trader.symbol == 'SPY', f"${trader.starting_capital:,}")

        # Check mixins
        has_mixins = all(hasattr(trader, m) for m in [
            'calculate_kelly_position_size',
            'check_risk_limits',
            'get_portfolio_greeks',
            'get_performance_summary'
        ])
        R.test("SPY Trader mixins", has_mixins)
    except Exception as e:
        R.test("SPY Trader", False, str(e)[:80])

    # SPX Trader
    try:
        from core.autonomous_paper_trader import AutonomousPaperTrader
        trader = AutonomousPaperTrader(symbol='SPX', capital=100_000_000)
        R.test("SPX Trader init", trader.symbol == 'SPX', f"${trader.starting_capital:,}")
    except Exception as e:
        R.test("SPX Trader", False, str(e)[:80])

# ============================================================================
# 4. BACKTEST SYSTEM
# ============================================================================
def test_backtest():
    R.section("4. BACKTEST SYSTEM")

    try:
        from backtest.backtest_framework import BacktestResults, Trade
        R.test("Backtest framework imports", True)
    except Exception as e:
        R.test("Backtest framework imports", False, str(e)[:80])

    try:
        from backtest.autonomous_backtest_engine import PatternBacktester, get_backtester
        backtester = get_backtester()
        R.test("Backtest engine", backtester is not None)
    except Exception as e:
        R.test("Backtest engine", False, str(e)[:80])

    # Check recent backtest activity
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), MAX(completed_at)
            FROM backtest_results
            WHERE completed_at > NOW() - INTERVAL '7 days'
        """)
        result = cursor.fetchone()
        count, last = result[0], result[1]
        conn.close()

        if count > 0:
            R.test("Recent backtests (7 days)", True, f"{count} runs, last: {last}")
        else:
            R.test("Recent backtests (7 days)", "warn", "None - trigger /api/backtests/run")
    except Exception as e:
        R.test("Recent backtests", "warn", str(e)[:80])

# ============================================================================
# 5. SCHEDULER & ACTIVITY
# ============================================================================
def test_scheduler():
    R.section("5. SCHEDULER & TRADING ACTIVITY")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Recent trade log activity
        cursor.execute("""
            SELECT COUNT(*) FROM autonomous_trade_log
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        log_count = cursor.fetchone()[0]

        if log_count > 0:
            R.test("Trade log activity (24h)", True, f"{log_count} entries")
        else:
            R.test("Trade log activity (24h)", "warn", "No activity - is scheduler running?")

        # Recent regime signals
        cursor.execute("""
            SELECT COUNT(*) FROM regime_signals
            WHERE timestamp > NOW() - INTERVAL '24 hours'
        """)
        regime_count = cursor.fetchone()[0]
        R.test("Regime signals (24h)", regime_count > 0 or "warn",
               f"{regime_count} signals" if regime_count else "No signals")

        # Open positions
        cursor.execute("SELECT COUNT(*) FROM autonomous_open_positions WHERE status = 'OPEN'")
        open_count = cursor.fetchone()[0]
        R.test("Open positions", True, f"{open_count} positions")

        # Trade history
        cursor.execute("SELECT COUNT(*) FROM autonomous_trade_history")
        history_count = cursor.fetchone()[0]
        R.test("Trade history total", True, f"{history_count} trades")

        conn.close()
    except Exception as e:
        R.test("Scheduler activity", False, str(e)[:80])

# ============================================================================
# 6. API ENDPOINTS
# ============================================================================
def test_api_endpoints():
    R.section("6. API ENDPOINTS")

    if not BASE_URL:
        R.test("API tests", "skip", "No --base-url provided")
        return

    if not REQUESTS_AVAILABLE:
        R.test("API tests", "skip", "requests module not installed")
        return

    endpoints = [
        # Core health
        ("GET", "/api/health", "Health check"),
        ("GET", "/api/time", "Server time"),

        # Trader
        ("GET", "/api/trader/status", "Trader status"),
        ("GET", "/api/trader/positions", "Open positions"),
        ("GET", "/api/trader/history", "Trade history"),
        ("GET", "/api/trader/equity-curve", "Equity curve"),
        ("GET", "/api/trader/live-status", "Live status"),

        # SPX
        ("GET", "/api/spx/status", "SPX status"),
        ("GET", "/api/spx/performance", "SPX performance"),
        ("GET", "/api/spx/trades", "SPX trades"),
        ("GET", "/api/spx/equity-curve", "SPX equity curve"),

        # Market data
        ("GET", "/api/regime/current", "Current regime"),
        ("GET", "/api/gex/SPY", "SPY GEX"),
        ("GET", "/api/vix/current", "Current VIX"),

        # Backtest
        ("GET", "/api/backtests/results", "Backtest results"),

        # Strategies
        ("GET", "/api/strategies/stats", "Strategy stats"),

        # Psychology
        ("GET", "/api/psychology/analyze", "Psychology analysis"),
    ]

    for method, endpoint, desc in endpoints:
        try:
            url = f"{BASE_URL.rstrip('/')}{endpoint}"
            if method == "GET":
                resp = requests.get(url, timeout=30)
            else:
                resp = requests.post(url, timeout=30)

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    success = data.get('success', True)
                    R.test(f"{method} {endpoint}", success, desc)
                except:
                    R.test(f"{method} {endpoint}", True, desc)
            elif resp.status_code == 404:
                R.test(f"{method} {endpoint}", "warn", "Not found")
            else:
                R.test(f"{method} {endpoint}", False, f"HTTP {resp.status_code}")
        except requests.exceptions.Timeout:
            R.test(f"{method} {endpoint}", "warn", "Timeout")
        except requests.exceptions.ConnectionError:
            R.test(f"{method} {endpoint}", False, "Connection refused")
        except Exception as e:
            R.test(f"{method} {endpoint}", False, str(e)[:50])

# ============================================================================
# 7. UI PAGES
# ============================================================================
def test_ui_pages():
    R.section("7. UI PAGES")

    if not BASE_URL:
        R.test("UI tests", "skip", "No --base-url provided")
        return

    if not REQUESTS_AVAILABLE:
        R.test("UI tests", "skip", "requests module not installed")
        return

    pages = [
        ("/", "Dashboard"),
        ("/trader", "Trader"),
        ("/spx", "SPX Trader"),
        ("/backtest", "Backtest"),
        ("/psychology", "Psychology"),
        ("/regime", "Market Regime"),
        ("/gex", "GEX Analysis"),
    ]

    for path, desc in pages:
        try:
            url = f"{BASE_URL.rstrip('/')}{path}"
            resp = requests.get(url, timeout=15)
            R.test(f"Page: {path}", resp.status_code == 200, desc)
        except requests.exceptions.Timeout:
            R.test(f"Page: {path}", "warn", "Timeout")
        except Exception as e:
            R.test(f"Page: {path}", "warn", str(e)[:50])

# ============================================================================
# 8. TRIGGER BACKTEST (Optional)
# ============================================================================
def test_trigger_backtest():
    R.section("8. TRIGGER BACKTEST")

    if not BASE_URL:
        R.test("Trigger backtest", "skip", "No --base-url provided")
        return

    if not REQUESTS_AVAILABLE:
        R.test("Trigger backtest", "skip", "requests module not installed")
        return

    print("  Triggering backtest run...")
    try:
        url = f"{BASE_URL.rstrip('/')}/api/backtests/run"
        resp = requests.post(url, timeout=120)  # Backtests can take time

        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                summary = data.get('data', {}).get('summary', {})
                patterns = summary.get('patterns_tested', 0)
                R.test("POST /api/backtests/run", True, f"{patterns} patterns tested")
            else:
                R.test("POST /api/backtests/run", "warn", data.get('error', 'Unknown error')[:50])
        else:
            R.test("POST /api/backtests/run", False, f"HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        R.test("POST /api/backtests/run", "warn", "Timeout (backtest may still be running)")
    except Exception as e:
        R.test("POST /api/backtests/run", False, str(e)[:50])

# ============================================================================
# 9. FEEDBACK LOOP VERIFICATION
# ============================================================================
def test_feedback_loop():
    R.section("9. FEEDBACK LOOP VERIFICATION")

    print("  Checking if backtests update strategy stats...")

    try:
        from core.strategy_stats import get_strategy_stats
        stats = get_strategy_stats()

        backtest_sources = [k for k, v in stats.items() if v.get('source') == 'backtest']

        if backtest_sources:
            R.test("Feedback loop working", True, f"{len(backtest_sources)} strategies updated from backtests")

            # Show sample
            sample = backtest_sources[0]
            sample_data = stats[sample]
            R.test(f"Sample: {sample}", True,
                   f"win_rate={sample_data.get('win_rate', 0):.1%}, trades={sample_data.get('total_trades', 0)}")
        else:
            R.test("Feedback loop working", "warn",
                   "No strategies updated from backtests yet - run /api/backtests/run")
    except Exception as e:
        R.test("Feedback loop", False, str(e)[:80])

# ============================================================================
# 10. MODULE IMPORTS
# ============================================================================
def test_imports():
    R.section("10. MODULE STRUCTURE")

    modules = [
        ("core.autonomous_paper_trader", "AutonomousPaperTrader"),
        ("core.market_regime_classifier", "get_classifier"),
        ("core.strategy_stats", "get_strategy_stats"),
        ("core.psychology_trap_detector", "analyze_current_market_complete"),
        ("data.polygon_data_fetcher", "polygon_fetcher"),
        ("data.unified_data_provider", "get_data_provider"),
        ("backtest.backtest_framework", "BacktestResults"),
        ("backtest.autonomous_backtest_engine", "PatternBacktester"),
        ("trading.mixins", "RiskManagerMixin"),
        ("gamma.gamma_expiration_builder", "build_gamma_with_expirations"),
        ("db.autonomous_database_logger", "get_database_logger"),
    ]

    for module, attr in modules:
        try:
            mod = __import__(module, fromlist=[attr])
            getattr(mod, attr)
            R.test(f"Import {module}", True)
        except Exception as e:
            R.test(f"Import {module}", False, str(e)[:60])

# ============================================================================
# MAIN
# ============================================================================
def main():
    print("\n" + "="*70)
    print(" ALPHAGEX COMPLETE SYSTEM TEST")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if BASE_URL:
        print(f" Target: {BASE_URL}")
    else:
        print(" Mode: Local only (no API/UI tests)")
    print("="*70)

    # Run all tests
    test_imports()
    test_database()
    test_data_providers()
    test_core_components()
    test_backtest()
    test_scheduler()
    test_api_endpoints()
    test_ui_pages()
    test_feedback_loop()

    # Optional: trigger backtest if URL provided
    if BASE_URL and REQUESTS_AVAILABLE:
        print("\n  💡 To trigger a backtest, run:")
        print(f"     curl -X POST {BASE_URL}/api/backtests/run")

    # Summary
    success = R.summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
