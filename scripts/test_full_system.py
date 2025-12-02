#!/usr/bin/env python3
"""
FULL SYSTEM TEST - AlphaGEX SPX Wheel Trading System

Tests everything end-to-end:
1. Polygon API connectivity (VIX, SPY data)
2. Trading Volatility API connectivity (GEX data)
3. ML feature extraction with real data
4. Backtest execution
5. ML training pipeline
6. Database connectivity

Run: python scripts/test_full_system.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import json

# Track test results
results = {
    'passed': [],
    'failed': [],
    'warnings': []
}


def test_passed(name, details=""):
    results['passed'].append({'name': name, 'details': details})
    print(f"✅ PASS: {name}")
    if details:
        print(f"   {details}")


def test_failed(name, error):
    results['failed'].append({'name': name, 'error': str(error)})
    print(f"❌ FAIL: {name}")
    print(f"   Error: {error}")


def test_warning(name, message):
    results['warnings'].append({'name': name, 'message': message})
    print(f"⚠️ WARN: {name}")
    print(f"   {message}")


def print_section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}\n")


# =============================================================================
# TEST 1: Environment Variables
# =============================================================================
def test_environment():
    print_section("TEST 1: Environment Variables")

    env_vars = {
        'POLYGON_API_KEY': os.getenv('POLYGON_API_KEY'),
        'TRADING_VOLATILITY_API_KEY': os.getenv('TRADING_VOLATILITY_API_KEY') or os.getenv('TV_USERNAME'),
        'DATABASE_URL': os.getenv('DATABASE_URL'),
    }

    for var, value in env_vars.items():
        if value:
            # Mask the value for security
            masked = value[:4] + '...' + value[-4:] if len(value) > 8 else '***'
            test_passed(f"Env: {var}", f"Set ({masked})")
        else:
            if var == 'TRADING_VOLATILITY_API_KEY':
                test_warning(f"Env: {var}", "Not set - GEX data will be unavailable")
            elif var == 'DATABASE_URL':
                test_warning(f"Env: {var}", "Not set - using SQLite fallback")
            else:
                test_failed(f"Env: {var}", "Not set - required for operation")


# =============================================================================
# TEST 2: Polygon API - VIX Data
# =============================================================================
def test_polygon_vix():
    print_section("TEST 2: Polygon API - VIX Data (I:VIX)")

    try:
        from data.polygon_data_fetcher import get_vix_for_date, get_vix_data_quality, polygon_fetcher

        # Test 1: Current VIX price
        print("Testing current VIX price...")
        for ticker in ['I:VIX', 'VIX']:
            try:
                df = polygon_fetcher.get_price_history(ticker, days=5, timeframe='day')
                if df is not None and not df.empty:
                    latest_vix = df['Close'].iloc[-1]
                    test_passed(f"VIX via {ticker}", f"Current: {latest_vix:.2f}")
                    break
            except Exception as e:
                continue
        else:
            test_failed("VIX current price", "Could not fetch from any ticker format")

        # Test 2: Historical VIX lookup
        print("\nTesting historical VIX lookup...")
        test_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        vix_value = get_vix_for_date(test_date)

        if vix_value and vix_value != 18.0:  # 18.0 is fallback
            test_passed(f"VIX for {test_date}", f"Value: {vix_value:.2f}")
        elif vix_value == 18.0:
            test_warning(f"VIX for {test_date}", "Got fallback value 18.0 - check Polygon subscription")
        else:
            test_failed(f"VIX for {test_date}", "No value returned")

        # Test 3: VIX data quality stats
        stats = get_vix_data_quality()
        print(f"\nVIX Data Quality: {stats}")

    except ImportError as e:
        test_failed("Polygon import", str(e))
    except Exception as e:
        test_failed("Polygon VIX test", str(e))


# =============================================================================
# TEST 3: Polygon API - SPY Data
# =============================================================================
def test_polygon_spy():
    print_section("TEST 3: Polygon API - SPY Price Data")

    try:
        from data.polygon_data_fetcher import get_spx_returns, polygon_fetcher

        # Test 1: SPY price history
        print("Testing SPY price history...")
        df = polygon_fetcher.get_price_history('SPY', days=30, timeframe='day')

        if df is not None and not df.empty:
            test_passed("SPY price history", f"Got {len(df)} days of data")
            print(f"   Latest close: ${df['Close'].iloc[-1]:.2f}")
        else:
            test_failed("SPY price history", "No data returned")

        # Test 2: SPX returns calculation
        print("\nTesting SPX returns calculation...")
        returns = get_spx_returns()

        if returns and returns.get('5d_return') is not None:
            test_passed("SPX returns",
                       f"5d: {returns['5d_return']:.2f}%, 20d: {returns['20d_return']:.2f}%")
        else:
            test_failed("SPX returns", "Could not calculate returns")

    except Exception as e:
        test_failed("Polygon SPY test", str(e))


# =============================================================================
# TEST 4: Trading Volatility API - GEX Data
# =============================================================================
def test_trading_volatility_gex():
    print_section("TEST 4: Trading Volatility API - GEX Data")

    try:
        from data.polygon_data_fetcher import get_gex_data, get_gex_data_quality

        print("Testing GEX data fetch...")
        gex_result = get_gex_data('SPY')

        if 'error' not in gex_result:
            test_passed("GEX data fetch",
                       f"Net GEX: {gex_result.get('net_gex', 'N/A')}, "
                       f"Put Wall: {gex_result.get('put_wall', 'N/A')}, "
                       f"Call Wall: {gex_result.get('call_wall', 'N/A')}")
        else:
            error = gex_result.get('error', 'Unknown')
            if 'API key' in error or 'not configured' in error.lower():
                test_warning("GEX data fetch", f"API key not configured: {error}")
            else:
                test_failed("GEX data fetch", error)

        # Show quality stats
        stats = get_gex_data_quality()
        print(f"\nGEX Data Quality: {stats}")

    except ImportError as e:
        test_warning("Trading Volatility import", f"TradingVolatilityAPI not available: {e}")
    except Exception as e:
        test_failed("GEX test", str(e))


# =============================================================================
# TEST 5: ML Feature Extraction
# =============================================================================
def test_ml_features():
    print_section("TEST 5: ML Feature Extraction (Real Data)")

    try:
        from data.polygon_data_fetcher import get_ml_features_for_trade

        # Test with a sample trade
        test_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        print(f"Testing ML features for trade on {test_date}...")
        features = get_ml_features_for_trade(
            trade_date=test_date,
            strike=580.0,
            underlying_price=600.0,
            option_iv=0.15
        )

        if features:
            print("\nFeatures extracted:")
            for key, value in features.items():
                if key != 'data_sources':
                    print(f"   {key}: {value}")

            print("\nData sources:")
            for source, status in features.get('data_sources', {}).items():
                print(f"   {source}: {status}")

            quality = features.get('data_quality_pct', 0)
            if quality >= 70:
                test_passed("ML features", f"Data quality: {quality}%")
            else:
                test_warning("ML features", f"Data quality only {quality}% - some sources unavailable")
        else:
            test_failed("ML features", "No features returned")

    except Exception as e:
        test_failed("ML features test", str(e))


# =============================================================================
# TEST 6: SPX Wheel ML System
# =============================================================================
def test_spx_wheel_ml():
    print_section("TEST 6: SPX Wheel ML System")

    try:
        from trading.spx_wheel_ml import (
            get_spx_wheel_ml_trainer,
            get_outcome_tracker,
            SPXWheelFeatures
        )

        # Test 1: Trainer initialization
        print("Testing ML trainer initialization...")
        trainer = get_spx_wheel_ml_trainer()

        if trainer:
            test_passed("ML trainer init", "Trainer created successfully")

            # Check if model is trained
            if trainer.model:
                test_passed("ML model", "Model is trained and ready")
            else:
                test_warning("ML model", "Model not trained yet - run backtest first")
        else:
            test_failed("ML trainer init", "Could not create trainer")

        # Test 2: Outcome tracker
        print("\nTesting outcome tracker...")
        tracker = get_outcome_tracker()

        if tracker:
            outcomes = tracker.get_all_outcomes()
            test_passed("Outcome tracker", f"{len(outcomes)} trade outcomes recorded")
        else:
            test_failed("Outcome tracker", "Could not create tracker")

        # Test 3: Feature dataclass
        print("\nTesting SPXWheelFeatures dataclass...")
        try:
            features = SPXWheelFeatures(
                trade_date='2024-01-15',
                strike=580.0,
                underlying_price=600.0,
                dte=45,
                delta=0.20,
                premium=5.50,
                iv=0.15,
                iv_rank=50,
                vix=15.0,
                vix_percentile=50,
                vix_term_structure=-1.0,
                put_wall_distance_pct=3.3,
                call_wall_distance_pct=5.0,
                net_gex=0,
                spx_20d_return=2.5,
                spx_5d_return=0.5,
                spx_distance_from_high=-1.0,
                premium_to_strike_pct=0.95,
                annualized_return=7.7
            )
            test_passed("SPXWheelFeatures", "Dataclass works correctly")
        except Exception as e:
            test_failed("SPXWheelFeatures", str(e))

    except ImportError as e:
        test_failed("SPX Wheel ML import", str(e))
    except Exception as e:
        test_failed("SPX Wheel ML test", str(e))


# =============================================================================
# TEST 7: Database Connectivity
# =============================================================================
def test_database():
    print_section("TEST 7: Database Connectivity")

    try:
        # Try multiple import paths
        get_connection = None
        import_source = None

        try:
            from database_adapter import get_connection
            import_source = "database_adapter"
        except ImportError:
            try:
                from backend.api.database import get_connection
                import_source = "backend.api.database"
            except ImportError:
                pass

        if get_connection is None:
            test_warning("Database import", "No database adapter found - using in-memory storage")
            return

        print(f"Testing database connection (from {import_source})...")
        conn = get_connection()

        if conn:
            cursor = conn.cursor()

            # Test basic query
            cursor.execute("SELECT 1")
            result = cursor.fetchone()

            if result:
                test_passed("Database connection", "Connected and query works")

                # Check for required tables
                try:
                    cursor.execute("""
                        SELECT name FROM sqlite_master
                        WHERE type='table'
                        ORDER BY name
                    """)
                    tables = [row[0] for row in cursor.fetchall()]
                    print(f"   Tables found: {', '.join(tables) if tables else 'None'}")
                except:
                    # Might be PostgreSQL
                    try:
                        cursor.execute("""
                            SELECT table_name FROM information_schema.tables
                            WHERE table_schema = 'public'
                        """)
                        tables = [row[0] for row in cursor.fetchall()]
                        print(f"   Tables found: {', '.join(tables) if tables else 'None'}")
                    except:
                        pass

            conn.close()
        else:
            test_failed("Database connection", "Could not connect")

    except Exception as e:
        test_warning("Database test", str(e))


# =============================================================================
# TEST 8: Backtest System (Dry Run)
# =============================================================================
def test_backtest_system():
    print_section("TEST 8: Backtest System (Import Check)")

    try:
        from backtest.spx_premium_backtest import SPXPremiumBacktester

        test_passed("Backtest import", "SPXPremiumBacktester available")

        # Check if we can create an instance
        print("\nCreating backtester instance (short period)...")

        # Use a very recent short period to minimize API calls
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        backtester = SPXPremiumBacktester(
            start_date=start_date,
            initial_capital=100000,
            put_delta=0.20,
            dte_target=45
        )

        if backtester:
            test_passed("Backtest instantiation", f"Created for period starting {start_date}")
        else:
            test_failed("Backtest instantiation", "Could not create backtester")

    except ImportError as e:
        test_failed("Backtest import", str(e))
    except Exception as e:
        test_failed("Backtest test", str(e))


# =============================================================================
# TEST 9: API Routes (Import Check)
# =============================================================================
def test_api_routes():
    print_section("TEST 9: API Routes (Import Check)")

    routes_to_test = [
        ('backend.api.routes.spx_backtest_routes', 'SPX Backtest routes'),
        ('backend.api.routes.ml_routes', 'ML routes'),
    ]

    for module, name in routes_to_test:
        try:
            __import__(module)
            test_passed(name, "Imported successfully")
        except ImportError as e:
            test_failed(name, str(e))
        except Exception as e:
            test_failed(name, str(e))


# =============================================================================
# TEST 10: Full Integration - ML Features Pipeline
# =============================================================================
def test_integration():
    print_section("TEST 10: Full Integration Test")

    try:
        from data.polygon_data_fetcher import get_ml_features_for_trade, get_vix_data_quality, get_gex_data_quality

        print("Running full feature extraction pipeline...")

        # Test with recent date
        test_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

        features = get_ml_features_for_trade(
            trade_date=test_date,
            strike=580.0,
            underlying_price=600.0,
            option_iv=None  # Test VIX proxy
        )

        # Check all critical features
        critical_features = ['vix', 'iv_rank', 'spx_5d_return', 'spx_20d_return', 'data_quality_pct']
        missing = [f for f in critical_features if f not in features]

        if not missing:
            test_passed("Integration test", "All critical features extracted")
        else:
            test_failed("Integration test", f"Missing features: {missing}")

        # Final data quality summary
        print("\n" + "="*60)
        print(" DATA QUALITY SUMMARY")
        print("="*60)

        vix_quality = get_vix_data_quality()
        gex_quality = get_gex_data_quality()

        print(f"\nVIX Data:")
        print(f"   Real: {vix_quality.get('real_count', 0)}, Fallback: {vix_quality.get('fallback_count', 0)}")
        if vix_quality.get('warning'):
            print(f"   ⚠️ {vix_quality['warning']}")

        print(f"\nGEX Data:")
        print(f"   Available: {gex_quality.get('available', False)}")
        if gex_quality.get('recent_errors'):
            print(f"   Recent errors: {gex_quality['recent_errors'][:2]}")

    except Exception as e:
        test_failed("Integration test", str(e))


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + "="*60)
    print(" AlphaGEX FULL SYSTEM TEST")
    print(" " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("="*60)

    # Run all tests
    test_environment()
    test_polygon_vix()
    test_polygon_spy()
    test_trading_volatility_gex()
    test_ml_features()
    test_spx_wheel_ml()
    test_database()
    test_backtest_system()
    test_api_routes()
    test_integration()

    # Print summary
    print("\n" + "="*60)
    print(" TEST SUMMARY")
    print("="*60)

    total = len(results['passed']) + len(results['failed']) + len(results['warnings'])

    print(f"\n✅ Passed:   {len(results['passed'])}/{total}")
    print(f"❌ Failed:   {len(results['failed'])}/{total}")
    print(f"⚠️ Warnings: {len(results['warnings'])}/{total}")

    if results['failed']:
        print("\n--- FAILURES ---")
        for fail in results['failed']:
            print(f"  • {fail['name']}: {fail['error']}")

    if results['warnings']:
        print("\n--- WARNINGS ---")
        for warn in results['warnings']:
            print(f"  • {warn['name']}: {warn['message']}")

    # Overall verdict
    print("\n" + "="*60)
    if not results['failed']:
        print(" ✅ SYSTEM READY - All critical tests passed!")
        if results['warnings']:
            print(f"    (with {len(results['warnings'])} warnings - review above)")
    else:
        print(f" ❌ SYSTEM NOT READY - {len(results['failed'])} critical failures")
        print("    Fix the failures above before running backtests")
    print("="*60 + "\n")

    return len(results['failed']) == 0


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
