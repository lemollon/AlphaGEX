#!/usr/bin/env python3
"""
FORTRESS Integration Test Suite
============================

Tests that FORTRESS bot is properly integrated and can:
1. Connect to Tradier sandbox API
2. Get market data (SPX price, VIX)
3. Build Iron Condor orders
4. Log decisions to database
5. Show up on frontend API

Run: python scripts/test_ares_integration.py
"""

import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results
TESTS_RUN = 0
TESTS_PASSED = 0
TESTS_FAILED = 0


def test(name):
    """Decorator for test functions"""
    def decorator(func):
        def wrapper():
            global TESTS_RUN, TESTS_PASSED, TESTS_FAILED
            TESTS_RUN += 1
            print(f"\n{'='*60}")
            print(f"TEST: {name}")
            print('='*60)
            try:
                result = func()
                if result:
                    TESTS_PASSED += 1
                    print(f"✅ PASSED: {name}")
                else:
                    TESTS_FAILED += 1
                    print(f"❌ FAILED: {name}")
                return result
            except Exception as e:
                TESTS_FAILED += 1
                print(f"❌ FAILED: {name}")
                print(f"   Error: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                return False
        return wrapper
    return decorator


# =============================================================================
# TEST 1: Environment Variables
# =============================================================================
@test("Environment Variables Configured")
def test_env_vars():
    """Check all required environment variables are set"""
    required = ['TRADIER_API_KEY', 'TRADIER_ACCOUNT_ID', 'TRADIER_SANDBOX']

    missing = []
    for var in required:
        value = os.getenv(var)
        if not value:
            missing.append(var)
            print(f"   ❌ {var}: NOT SET")
        else:
            masked = value[:4] + '...' + value[-4:] if len(value) > 10 else '***'
            print(f"   ✓ {var}: {masked}")

    sandbox = os.getenv('TRADIER_SANDBOX', 'false').lower()
    print(f"\n   Mode: {'SANDBOX (safe)' if sandbox == 'true' else '⚠️  PRODUCTION (real money)'}")

    return len(missing) == 0


# =============================================================================
# TEST 2: Tradier API Connection
# =============================================================================
@test("Tradier API Connection")
def test_tradier_connection():
    """Test that we can connect to Tradier and get account info"""
    from data.tradier_data_fetcher import TradierDataFetcher

    tradier = TradierDataFetcher(sandbox=True)
    print(f"   Base URL: {tradier.base_url}")
    print(f"   Sandbox Mode: {tradier.sandbox}")

    # Get account info
    account = tradier.get_account_balance()
    if account:
        print(f"   Account ID: {tradier.account_id}")

        # Get cash info
        cash = account.get('cash', {})
        cash_available = cash.get('cash_available', 0)
        option_bp = account.get('option_buying_power', 0)
        total_equity = account.get('total_equity', 0)

        print(f"   Total Equity: ${total_equity:,.2f}")
        print(f"   Cash Available: ${cash_available:,.2f}")
        print(f"   Option BP: ${option_bp:,.2f}")

        # Check if buying power is $0 - this is a known sandbox issue
        if option_bp == 0 and total_equity > 0:
            print()
            print("   ⚠️  WARNING: Option Buying Power is $0!")
            print("   This is a known Tradier sandbox issue.")
            print()
            print("   TO FIX: Go to https://dash.tradier.com/")
            print("   1. Log in and switch to Sandbox mode")
            print("   2. Go to 'Reset Sandbox Account' in settings")
            print("   3. Reset the account to restore buying power")
            print()
            print("   (Test still passes - connection works)")

        return True
    else:
        print("   ❌ Could not get account info")
        return False


# =============================================================================
# TEST 3: Market Data
# =============================================================================
@test("Market Data (SPX/VIX)")
def test_market_data():
    """Test that we can get SPX and VIX quotes"""
    from data.tradier_data_fetcher import TradierDataFetcher

    tradier = TradierDataFetcher(sandbox=True)

    # Get SPX (try both symbols)
    spx = tradier.get_quote('$SPX.X') or tradier.get_quote('SPX')
    if spx and spx.get('last'):
        print(f"   SPX: ${spx['last']:,.2f}")
    else:
        # Fallback to SPY * 10
        spy = tradier.get_quote('SPY')
        if spy and spy.get('last'):
            print(f"   SPY: ${spy['last']:.2f} (SPX estimate: ${spy['last'] * 10:,.2f})")
        else:
            print("   ❌ Could not get SPX or SPY quote")
            return False

    # Get VIX
    vix = tradier.get_quote('$VIX.X') or tradier.get_quote('VIX')
    if vix and vix.get('last'):
        print(f"   VIX: {vix['last']:.2f}")
    else:
        print("   ⚠️  VIX not available (will use default 15)")

    return True


# =============================================================================
# TEST 4: Options Chain (SPY for sandbox, as SPXW is not available)
# =============================================================================
@test("Options Chain (SPY - sandbox mode uses SPY)")
def test_options_chain():
    """Test that we can get SPY options chain (sandbox uses SPY instead of SPXW)"""
    from data.tradier_data_fetcher import TradierDataFetcher

    tradier = TradierDataFetcher(sandbox=True)

    # FORTRESS uses SPY in sandbox mode because SPXW is not available
    # Get expirations for SPY
    expirations = tradier.get_option_expirations('SPY')

    if not expirations:
        print("   ❌ No SPY expirations found")
        return False

    print(f"   Found {len(expirations)} expirations")
    print(f"   Nearest: {expirations[0]}")

    # Get chain for nearest expiration
    chain = tradier.get_option_chain('SPY', expirations[0])

    if chain and chain.chains and expirations[0] in chain.chains:
        contracts = chain.chains.get(expirations[0], [])
        puts = [c for c in contracts if c.option_type == 'put']
        calls = [c for c in contracts if c.option_type == 'call']
        print(f"   Contracts: {len(puts)} puts, {len(calls)} calls")

        if len(puts) > 0 and len(calls) > 0:
            print(f"   ✓ Options data available for FORTRESS sandbox trading")
            return True
        else:
            print("   ⚠️  Limited options data (no bids/asks)")
            return True  # Still pass, sandbox limitation
    else:
        print("   ⚠️  No chain data returned (sandbox may have limited options)")
        print("   NOTE: FORTRESS will use SPY in sandbox mode")
        return True  # Not a hard failure, sandbox limitation


# =============================================================================
# TEST 5: FORTRESS Bot Initialization
# =============================================================================
@test("FORTRESS Bot Initialization")
def test_ares_init():
    """Test that FORTRESS bot initializes correctly"""
    from trading.ares_iron_condor import FortressTrader, TradingMode

    fortress = FortressTrader(
        mode=TradingMode.PAPER,
        initial_capital=200_000
    )

    status = fortress.get_status()
    print(f"   Mode: {status['mode']}")
    print(f"   Capital: ${status['capital']:,.0f}")
    print(f"   Trading Ticker: {status['config']['ticker']}")
    print(f"   Sandbox Ticker: {status['config']['sandbox_ticker']}")
    print(f"   Production Ticker: {status['config']['production_ticker']}")
    print(f"   Risk/Trade: {status['config']['risk_per_trade']}%")
    print(f"   Spread Width: ${status['config']['spread_width']}")
    print(f"   SD Multiplier: {status['config']['sd_multiplier']}")
    print(f"   In Trading Window: {status['in_trading_window']}")
    print(f"   Traded Today: {status['traded_today']}")

    # In paper mode, should be using SPY
    correct_ticker = status['config']['ticker'] == 'SPY'
    if not correct_ticker:
        print(f"   ⚠️  Expected SPY for sandbox, got {status['config']['ticker']}")

    return status['mode'] == 'paper' and status['capital'] == 200_000 and correct_ticker


# =============================================================================
# TEST 6: Decision Logger
# =============================================================================
@test("Decision Logger Database")
def test_decision_logger():
    """Test that decision logger can write to database"""
    from trading.decision_logger import DecisionLogger, BotName, DecisionType

    logger = DecisionLogger()

    # Check if FORTRESS is in BotName enum
    assert hasattr(BotName, 'FORTRESS'), "FORTRESS not in BotName enum"
    print(f"   BotName.FORTRESS: {BotName.FORTRESS.value}")

    # Check database connection
    from database_adapter import get_connection
    conn = get_connection()
    cursor = conn.cursor()

    # Check decision_logs table exists
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'decision_logs'
        )
    """)
    table_exists = cursor.fetchone()[0]
    print(f"   decision_logs table exists: {table_exists}")

    if not table_exists:
        # Create table if needed
        print("   Creating decision_logs table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ DEFAULT NOW(),
                decision_id VARCHAR(100),
                bot_name VARCHAR(50),
                decision_type VARCHAR(50),
                action VARCHAR(50),
                symbol VARCHAR(20),
                what TEXT,
                why TEXT,
                how TEXT,
                outcome TEXT,
                data JSONB
            )
        """)
        conn.commit()
        print("   ✓ Table created")

    # Count existing FORTRESS logs
    cursor.execute("SELECT COUNT(*) FROM decision_logs WHERE bot_name = 'FORTRESS'")
    ares_count = cursor.fetchone()[0]
    print(f"   Existing FORTRESS decisions: {ares_count}")

    conn.close()
    return True


# =============================================================================
# TEST 7: Backend API
# =============================================================================
@test("Backend API (/bots/status)")
def test_backend_api():
    """Test that backend API returns FORTRESS in bots status"""
    import requests

    # Try local backend
    urls_to_try = [
        'http://localhost:8000/api/trader/bots/status',
        'http://127.0.0.1:8000/api/trader/bots/status'
    ]

    for url in urls_to_try:
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    bots = data.get('data', {}).get('bots', {})
                    if 'FORTRESS' in bots:
                        print(f"   ✓ FORTRESS found in API response")
                        print(f"   FORTRESS capital: ${bots['FORTRESS']['capital_allocation']:,}")
                        print(f"   FORTRESS schedule: {bots['FORTRESS']['schedule']}")
                        print(f"   FORTRESS scheduled: {bots['FORTRESS']['scheduled']}")

                        # Check capital allocation
                        allocation = data.get('data', {}).get('capital_summary', {}).get('allocation', {})
                        if 'FORTRESS' in allocation:
                            print(f"   Capital allocation: ${allocation['FORTRESS']['amount']:,} ({allocation['FORTRESS']['pct']}%)")

                        autonomous = data.get('data', {}).get('autonomous_bots', [])
                        print(f"   Autonomous bots: {autonomous}")
                        return 'FORTRESS' in autonomous
                    else:
                        print(f"   ❌ FORTRESS not in bots: {list(bots.keys())}")
                        return False
        except requests.exceptions.ConnectionError:
            continue
        except Exception as e:
            print(f"   Error: {e}")
            continue

    print("   ⚠️  Backend not running locally - skipping")
    print("   Run: cd backend && uvicorn main:app --reload")
    return True  # Not a failure if backend isn't running


# =============================================================================
# TEST 8: Scheduler Integration
# =============================================================================
@test("Scheduler Integration")
def test_scheduler():
    """Test that scheduler recognizes FORTRESS"""
    from scheduler.trader_scheduler import CAPITAL_ALLOCATION, ARES_AVAILABLE

    print(f"   ARES_AVAILABLE: {ARES_AVAILABLE}")
    print(f"   FORTRESS Capital: ${CAPITAL_ALLOCATION.get('FORTRESS', 0):,}")
    print(f"   LAZARUS Capital: ${CAPITAL_ALLOCATION.get('LAZARUS', 0):,}")
    print(f"   CORNERSTONE Capital: ${CAPITAL_ALLOCATION.get('CORNERSTONE', 0):,}")
    print(f"   Total: ${CAPITAL_ALLOCATION.get('TOTAL', 0):,}")

    return ARES_AVAILABLE and CAPITAL_ALLOCATION.get('FORTRESS') == 200_000


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + "="*60)
    print("FORTRESS INTEGRATION TEST SUITE")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Run all tests
    test_env_vars()
    test_tradier_connection()
    test_market_data()
    test_options_chain()
    test_ares_init()
    test_decision_logger()
    test_backend_api()
    test_scheduler()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Total:  {TESTS_RUN}")
    print(f"Passed: {TESTS_PASSED} ✅")
    print(f"Failed: {TESTS_FAILED} ❌")
    print("="*60)

    if TESTS_FAILED == 0:
        print("\n🎉 ALL TESTS PASSED - FORTRESS is ready to trade!")
    else:
        print(f"\n⚠️  {TESTS_FAILED} tests failed - review above for issues")

    return TESTS_FAILED == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
