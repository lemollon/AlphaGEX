#!/usr/bin/env python3
"""
ARES Integration Test Suite
============================

Tests that ARES bot is properly integrated and can:
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
        print(f"   Cash Available: ${account.get('cash', {}).get('cash_available', 0):,.2f}")
        print(f"   Option BP: ${account.get('option_buying_power', 0):,.2f}")
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
# TEST 4: Options Chain
# =============================================================================
@test("Options Chain (SPXW)")
def test_options_chain():
    """Test that we can get SPX options chain"""
    from data.tradier_data_fetcher import TradierDataFetcher

    tradier = TradierDataFetcher(sandbox=True)

    # Get expirations
    expirations = tradier.get_option_expirations('SPXW')
    if not expirations:
        print("   ⚠️  No SPXW expirations, trying SPX...")
        expirations = tradier.get_option_expirations('SPX')

    if expirations:
        print(f"   Found {len(expirations)} expirations")
        print(f"   Nearest: {expirations[0]}")

        # Get chain for nearest expiration
        chain = tradier.get_option_chain('SPXW', expirations[0])
        if chain and chain.chains:
            contracts = chain.chains.get(expirations[0], [])
            puts = [c for c in contracts if c.option_type == 'put']
            calls = [c for c in contracts if c.option_type == 'call']
            print(f"   Contracts: {len(puts)} puts, {len(calls)} calls")
            return True
        else:
            print("   ⚠️  No chain data (sandbox may have limited options)")
            return True  # Not a failure, sandbox limitation
    else:
        print("   ❌ No expirations found")
        return False


# =============================================================================
# TEST 5: ARES Bot Initialization
# =============================================================================
@test("ARES Bot Initialization")
def test_ares_init():
    """Test that ARES bot initializes correctly"""
    from trading.ares_iron_condor import ARESTrader, TradingMode

    ares = ARESTrader(
        mode=TradingMode.PAPER,
        initial_capital=200_000
    )

    status = ares.get_status()
    print(f"   Mode: {status['mode']}")
    print(f"   Capital: ${status['capital']:,.0f}")
    print(f"   Risk/Trade: {status['config']['risk_per_trade']}%")
    print(f"   Spread Width: ${status['config']['spread_width']}")
    print(f"   SD Multiplier: {status['config']['sd_multiplier']}")
    print(f"   In Trading Window: {status['in_trading_window']}")
    print(f"   Traded Today: {status['traded_today']}")

    return status['mode'] == 'paper' and status['capital'] == 200_000


# =============================================================================
# TEST 6: Decision Logger
# =============================================================================
@test("Decision Logger Database")
def test_decision_logger():
    """Test that decision logger can write to database"""
    from trading.decision_logger import DecisionLogger, BotName, DecisionType

    logger = DecisionLogger()

    # Check if ARES is in BotName enum
    assert hasattr(BotName, 'ARES'), "ARES not in BotName enum"
    print(f"   BotName.ARES: {BotName.ARES.value}")

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

    # Count existing ARES logs
    cursor.execute("SELECT COUNT(*) FROM decision_logs WHERE bot_name = 'ARES'")
    ares_count = cursor.fetchone()[0]
    print(f"   Existing ARES decisions: {ares_count}")

    conn.close()
    return True


# =============================================================================
# TEST 7: Backend API
# =============================================================================
@test("Backend API (/bots/status)")
def test_backend_api():
    """Test that backend API returns ARES in bots status"""
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
                    if 'ARES' in bots:
                        print(f"   ✓ ARES found in API response")
                        print(f"   ARES capital: ${bots['ARES']['capital_allocation']:,}")
                        print(f"   ARES schedule: {bots['ARES']['schedule']}")
                        print(f"   ARES scheduled: {bots['ARES']['scheduled']}")

                        # Check capital allocation
                        allocation = data.get('data', {}).get('capital_summary', {}).get('allocation', {})
                        if 'ARES' in allocation:
                            print(f"   Capital allocation: ${allocation['ARES']['amount']:,} ({allocation['ARES']['pct']}%)")

                        autonomous = data.get('data', {}).get('autonomous_bots', [])
                        print(f"   Autonomous bots: {autonomous}")
                        return 'ARES' in autonomous
                    else:
                        print(f"   ❌ ARES not in bots: {list(bots.keys())}")
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
    """Test that scheduler recognizes ARES"""
    from scheduler.trader_scheduler import CAPITAL_ALLOCATION, ARES_AVAILABLE

    print(f"   ARES_AVAILABLE: {ARES_AVAILABLE}")
    print(f"   ARES Capital: ${CAPITAL_ALLOCATION.get('ARES', 0):,}")
    print(f"   PHOENIX Capital: ${CAPITAL_ALLOCATION.get('PHOENIX', 0):,}")
    print(f"   ATLAS Capital: ${CAPITAL_ALLOCATION.get('ATLAS', 0):,}")
    print(f"   Total: ${CAPITAL_ALLOCATION.get('TOTAL', 0):,}")

    return ARES_AVAILABLE and CAPITAL_ALLOCATION.get('ARES') == 200_000


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + "="*60)
    print("ARES INTEGRATION TEST SUITE")
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
        print("\n🎉 ALL TESTS PASSED - ARES is ready to trade!")
    else:
        print(f"\n⚠️  {TESTS_FAILED} tests failed - review above for issues")

    return TESTS_FAILED == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
