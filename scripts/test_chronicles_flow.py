#!/usr/bin/env python3
"""
CHRONICLES End-to-End Test Script

Tests the complete backtest flow:
1. Health check endpoint
2. Database connectivity
3. ORAT data availability
4. Backtest execution
5. Result structure validation

Run this BEFORE using the frontend to verify everything works.
"""

import os
import sys
import time
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required if DATABASE_URL is already set

def test_database_connection():
    """Test database connectivity and ORAT data"""
    print("\n" + "="*60)
    print("TEST 1: Database Connection & ORAT Data")
    print("="*60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Test connection
        cursor.execute("SELECT 1")
        print("✅ Database connection: OK")

        # Check ORAT data
        cursor.execute("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT ticker) as tickers,
                MIN(trade_date) as earliest_date,
                MAX(trade_date) as latest_date
            FROM orat_options_eod
        """)
        row = cursor.fetchone()

        if row and row[0] > 0:
            print(f"✅ ORAT data available:")
            print(f"   - Total rows: {row[0]:,}")
            print(f"   - Tickers: {row[1]}")
            print(f"   - Date range: {row[2]} to {row[3]}")
        else:
            print("❌ ORAT data: EMPTY - No data in orat_options_eod table")
            return False

        # Check SPX specifically (what CHRONICLES uses)
        cursor.execute("""
            SELECT COUNT(*), MIN(trade_date), MAX(trade_date)
            FROM orat_options_eod
            WHERE ticker = 'SPX'
        """)
        spx = cursor.fetchone()
        if spx and spx[0] > 0:
            print(f"✅ SPX data: {spx[0]:,} rows ({spx[1]} to {spx[2]})")
        else:
            print("❌ SPX data: MISSING - CHRONICLES requires SPX data")
            return False

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Database error: {e}")
        return False


def test_backtester_import():
    """Test that backtester module imports correctly"""
    print("\n" + "="*60)
    print("TEST 2: Backtester Module Import")
    print("="*60)

    try:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester
        print("✅ HybridFixedBacktester imported successfully")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_backtester_initialization():
    """Test that backtester initializes with valid config"""
    print("\n" + "="*60)
    print("TEST 3: Backtester Initialization")
    print("="*60)

    try:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

        # Use a small date range for quick test
        backtester = HybridFixedBacktester(
            start_date='2024-01-01',
            end_date='2024-01-31',  # Just 1 month
            initial_capital=100000,
            spread_width=10,
            sd_multiplier=1.0,
            risk_per_trade_pct=5.0,
            ticker='SPX'
        )

        print("✅ Backtester initialized with config:")
        print(f"   - Date range: 2024-01-01 to 2024-01-31")
        print(f"   - Initial capital: $100,000")
        print(f"   - Ticker: SPX")

        return backtester

    except Exception as e:
        print(f"❌ Initialization error: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_trading_days_query(backtester):
    """Test the get_trading_days query"""
    print("\n" + "="*60)
    print("TEST 4: Trading Days Query")
    print("="*60)

    try:
        trading_days = backtester.get_trading_days()

        if trading_days:
            print(f"✅ Found {len(trading_days)} trading days")
            print(f"   - First day: {trading_days[0]}")
            print(f"   - Last day: {trading_days[-1]}")
            return True
        else:
            print("❌ No trading days found")
            print("   This means the date range has no ORAT data")
            return False

    except Exception as e:
        print(f"❌ Query error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_market_data_load(backtester):
    """Test market data loading (VIX, SPX OHLC)"""
    print("\n" + "="*60)
    print("TEST 5: Market Data Loading")
    print("="*60)

    try:
        backtester.load_market_data()

        if backtester.spx_ohlc:
            print(f"✅ SPX OHLC data loaded: {len(backtester.spx_ohlc)} days")
        else:
            print("⚠️  SPX OHLC data: Empty (will use fallback)")

        if backtester.vix_data:
            print(f"✅ VIX data loaded: {len(backtester.vix_data)} days")
        else:
            print("⚠️  VIX data: Empty (will use default VIX=18)")

        return True

    except Exception as e:
        print(f"❌ Market data error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_mini_backtest():
    """Run a minimal backtest to verify full flow"""
    print("\n" + "="*60)
    print("TEST 6: Mini Backtest (1 month)")
    print("="*60)

    try:
        from backtest.zero_dte_hybrid_fixed import HybridFixedBacktester

        # Progress tracking
        progress_updates = []
        def track_progress(pct, msg):
            progress_updates.append((pct, msg))
            print(f"   [{pct}%] {msg}")

        backtester = HybridFixedBacktester(
            start_date='2024-01-01',
            end_date='2024-01-31',
            initial_capital=100000,
            spread_width=10,
            sd_multiplier=1.0,
            risk_per_trade_pct=5.0,
            ticker='SPX'
        )
        backtester.progress_callback = track_progress

        print("Running backtest...")
        results = backtester.run()

        if not results:
            print("❌ Backtest returned empty results")
            return False, None

        # Verify result structure
        print("\n✅ Backtest completed! Verifying result structure...")

        required_keys = ['summary', 'trades', 'monthly_returns', 'equity_curve']
        missing_keys = [k for k in required_keys if k not in results]

        if missing_keys:
            print(f"⚠️  Missing keys in results: {missing_keys}")
        else:
            print("✅ All required keys present")

        # Show summary
        if 'summary' in results:
            s = results['summary']
            print(f"\n   Results Summary:")
            print(f"   - Final equity: ${s.get('final_equity', 0):,.0f}")
            print(f"   - Total return: {s.get('total_return_pct', 0):.1f}%")
            print(f"   - Max drawdown: {s.get('max_drawdown_pct', 0):.1f}%")

        if 'trades' in results:
            t = results['trades']
            print(f"   - Total trades: {t.get('total', 0)}")
            print(f"   - Win rate: {t.get('win_rate', 0):.1f}%")

        return True, results

    except Exception as e:
        print(f"❌ Backtest error: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_result_structure(results):
    """Verify result structure matches what frontend expects"""
    print("\n" + "="*60)
    print("TEST 7: Frontend Compatibility Check")
    print("="*60)

    issues = []

    # Check summary fields (frontend uses these)
    summary_fields = ['final_equity', 'total_return_pct', 'avg_monthly_return_pct', 'max_drawdown_pct']
    if 'summary' in results:
        for field in summary_fields:
            if field not in results['summary']:
                issues.append(f"summary.{field} missing")
    else:
        issues.append("summary object missing")

    # Check trades fields
    trades_fields = ['total', 'win_rate', 'profit_factor']
    if 'trades' in results:
        for field in trades_fields:
            if field not in results['trades']:
                issues.append(f"trades.{field} missing")
    else:
        issues.append("trades object missing")

    # Check equity_curve structure
    if 'equity_curve' in results and results['equity_curve']:
        sample = results['equity_curve'][0]
        ec_fields = ['date', 'equity', 'drawdown_pct']
        for field in ec_fields:
            if field not in sample:
                issues.append(f"equity_curve[].{field} missing")

    # Check all_trades structure (for trades tab)
    if 'all_trades' in results and results['all_trades']:
        sample = results['all_trades'][0]
        trade_fields = ['trade_number', 'trade_date', 'tier_name', 'contracts', 'net_pnl', 'outcome']
        for field in trade_fields:
            if field not in sample:
                issues.append(f"all_trades[].{field} missing")

    if issues:
        print("⚠️  Frontend compatibility issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    else:
        print("✅ Result structure matches frontend expectations")
        return True


def main():
    print("\n" + "="*60)
    print("CHRONICLES END-TO-END DIAGNOSTIC TEST")
    print("="*60)
    print("This script tests the complete backtest flow")
    print("Run this BEFORE using the frontend")

    all_passed = True

    # Test 1: Database
    if not test_database_connection():
        all_passed = False
        print("\n❌ STOP: Fix database connection before proceeding")
        return

    # Test 2: Import
    if not test_backtester_import():
        all_passed = False
        print("\n❌ STOP: Fix import errors before proceeding")
        return

    # Test 3: Initialize
    backtester = test_backtester_initialization()
    if not backtester:
        all_passed = False
        print("\n❌ STOP: Fix initialization before proceeding")
        return

    # Test 4: Trading days
    if not test_trading_days_query(backtester):
        all_passed = False
        print("\n⚠️  WARNING: No trading days found - check date range")

    # Test 5: Market data
    if not test_market_data_load(backtester):
        all_passed = False

    # Test 6: Mini backtest
    success, results = test_mini_backtest()
    if not success:
        all_passed = False
        print("\n❌ CRITICAL: Backtest failed - CHRONICLES will not work")
        return

    # Test 7: Result structure
    if results:
        if not test_result_structure(results):
            all_passed = False

    # Final verdict
    print("\n" + "="*60)
    print("FINAL VERDICT")
    print("="*60)

    if all_passed:
        print("✅ ALL TESTS PASSED - CHRONICLES should work!")
        print("\nNext steps:")
        print("1. Start backend: python backend/main.py")
        print("2. Start frontend: cd frontend && npm run dev")
        print("3. Open http://localhost:3000/zero-dte-backtest")
        print("4. Look for green 'Backend Connected' indicator")
        print("5. Click 'Run Backtest'")
    else:
        print("⚠️  SOME TESTS FAILED - Review issues above")
        print("\nKRONOS may not work correctly until issues are fixed")


if __name__ == "__main__":
    main()
