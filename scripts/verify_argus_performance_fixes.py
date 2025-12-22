#!/usr/bin/env python3
"""
ARGUS Performance Fixes Verification Script
============================================

Run this after deploying the performance improvements to verify everything works.

Usage:
    python scripts/verify_argus_performance_fixes.py

Checks:
1. Database migration applied (performance indexes exist)
2. ARGUS engine initialization with ML models
3. ARES expected move validation
4. ATHENA expected move in skip decisions
5. VIX fetcher working
6. API endpoints responding correctly
"""

import os
import sys
import time
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"
WARN = "\033[93m⚠️  WARN\033[0m"
INFO = "\033[94mℹ️  INFO\033[0m"

results = {
    'passed': 0,
    'failed': 0,
    'warnings': 0
}


def check(name: str, condition: bool, message: str = "", warn_only: bool = False):
    """Log a check result"""
    if condition:
        logger.info(f"{PASS} {name}")
        results['passed'] += 1
    elif warn_only:
        logger.info(f"{WARN} {name}: {message}")
        results['warnings'] += 1
    else:
        logger.info(f"{FAIL} {name}: {message}")
        results['failed'] += 1
    return condition


def test_database_indexes():
    """Test 1: Check if performance indexes exist"""
    logger.info("\n" + "="*60)
    logger.info("TEST 1: Database Performance Indexes")
    logger.info("="*60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check for our performance indexes
        cursor.execute("""
            SELECT indexname FROM pg_indexes
            WHERE tablename = 'argus_snapshots'
            AND indexname LIKE 'idx_argus_%'
        """)
        indexes = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected_indexes = [
            'idx_argus_snapshots_snapshot_time_desc',
            'idx_argus_snapshots_snapshot_time_asc',
            'idx_argus_snapshots_date_time'
        ]

        found = sum(1 for idx in expected_indexes if idx in indexes)

        if found == len(expected_indexes):
            check("Performance indexes", True)
        elif found > 0:
            check("Performance indexes", False,
                  f"Found {found}/{len(expected_indexes)} indexes. Run: psql $DATABASE_URL -f db/migrations/006_argus_performance_indexes.sql",
                  warn_only=True)
        else:
            check("Performance indexes", False,
                  "No performance indexes found. Run: psql $DATABASE_URL -f db/migrations/006_argus_performance_indexes.sql")

    except Exception as e:
        check("Database connection", False, str(e))


def test_argus_engine():
    """Test 2: ARGUS engine initialization"""
    logger.info("\n" + "="*60)
    logger.info("TEST 2: ARGUS Engine Initialization")
    logger.info("="*60)

    try:
        from core.argus_engine import get_argus_engine, initialize_argus_engine

        # Test get_argus_engine
        engine = get_argus_engine()
        check("ARGUS engine singleton", engine is not None)

        # Test initialize function exists
        import inspect
        source = inspect.getsource(initialize_argus_engine)
        check("initialize_argus_engine has ML loading", "_get_ml_models" in source)

    except ImportError as e:
        check("ARGUS engine import", False, str(e))
    except Exception as e:
        check("ARGUS engine", False, str(e))


def test_ares_validation():
    """Test 3: ARES expected move validation"""
    logger.info("\n" + "="*60)
    logger.info("TEST 3: ARES Expected Move Validation")
    logger.info("="*60)

    try:
        import inspect
        from trading.ares_iron_condor import ARESTrader

        source = inspect.getsource(ARESTrader.get_current_market_data)

        checks = [
            ("Underlying price validation", "Invalid underlying price" in source),
            ("VIX range validation", "outside normal range" in source),
            ("Expected move validation", "expected_move_pct" in source),
            ("Fallback calculation", "Fallback" in source or "fallback" in source),
            ("Market data logging", "ARES Market Data" in source),
        ]

        for name, condition in checks:
            check(name, condition)

    except ImportError as e:
        check("ARES import", False, str(e))
    except Exception as e:
        check("ARES validation code", False, str(e))


def test_athena_expected_move():
    """Test 4: ATHENA expected move in skip decisions"""
    logger.info("\n" + "="*60)
    logger.info("TEST 4: ATHENA Expected Move in Skip Decisions")
    logger.info("="*60)

    try:
        import inspect
        from trading.athena_directional_spreads import ATHENATrader

        # Check _log_skip_decision
        source = inspect.getsource(ATHENATrader._log_skip_decision)

        checks = [
            ("expected_move_pct calculation", "expected_move_pct = (vix / 16)" in source),
            ("VIX validation", "outside normal range" in source),
            ("expected_move_pct in MarketContext", "expected_move_pct=expected_move_pct" in source),
            ("Skip decision logging", "ATHENA Skip Decision" in source),
        ]

        for name, condition in checks:
            check(name, condition)

        # Also check _log_decision
        source2 = inspect.getsource(ATHENATrader._log_decision)
        check("_log_decision has validation", "outside normal range" in source2)

    except ImportError as e:
        check("ATHENA import", False, str(e))
    except Exception as e:
        check("ATHENA expected move code", False, str(e))


def test_vix_fetcher():
    """Test 5: VIX fetcher"""
    logger.info("\n" + "="*60)
    logger.info("TEST 5: VIX Fetcher")
    logger.info("="*60)

    try:
        from data.vix_fetcher import get_vix_price

        start = time.time()
        vix = get_vix_price()
        elapsed = time.time() - start

        check("VIX fetcher returns value", vix is not None and vix > 0,
              f"VIX={vix}")
        check("VIX in reasonable range", 8 <= vix <= 100 if vix else False,
              f"VIX={vix}")
        check("VIX fetch time < 5s", elapsed < 5, f"Took {elapsed:.2f}s")

        logger.info(f"{INFO} Current VIX: {vix:.2f}")

    except Exception as e:
        check("VIX fetcher", False, str(e), warn_only=True)


def test_tradier_connection():
    """Test 6: Tradier API connectivity"""
    logger.info("\n" + "="*60)
    logger.info("TEST 6: Tradier API Connectivity")
    logger.info("="*60)

    try:
        from data.tradier_data_fetcher import TradierDataFetcher

        tradier = TradierDataFetcher()
        check("Tradier client initialized", True)

        # Test SPY quote
        quote = tradier.get_quote('SPY')
        spy_price = quote.get('last') or quote.get('close')
        check("SPY quote retrieved", spy_price is not None and spy_price > 0,
              f"SPY=${spy_price}" if spy_price else "No price")

        # Test option expirations
        expirations = tradier.get_option_expirations('SPY')
        check("Option expirations retrieved", len(expirations) > 0,
              f"Found {len(expirations)} expirations")

        if expirations:
            # Test option chain
            exp = expirations[0]
            chain = tradier.get_option_chain('SPY', exp)
            contracts = chain.chains.get(exp, [])
            check("Option chain retrieved", len(contracts) > 0,
                  f"Found {len(contracts)} contracts for {exp}")

            if contracts:
                # Check that we have both calls and puts
                calls = [c for c in contracts if c.option_type == 'call']
                puts = [c for c in contracts if c.option_type == 'put']
                check("Has both calls and puts", len(calls) > 0 and len(puts) > 0,
                      f"{len(calls)} calls, {len(puts)} puts")

                # Check for gamma data
                contracts_with_gamma = [c for c in contracts if c.gamma != 0]
                check("Greeks (gamma) available", len(contracts_with_gamma) > 0,
                      f"{len(contracts_with_gamma)} contracts with gamma")

        logger.info(f"{INFO} Tradier mode: {'SANDBOX' if tradier.sandbox else 'PRODUCTION'}")

    except Exception as e:
        check("Tradier connection", False, str(e))


def test_api_endpoints():
    """Test 7: API endpoints (requires server running)"""
    logger.info("\n" + "="*60)
    logger.info("TEST 7: API Endpoints (requires server at localhost:8000)")
    logger.info("="*60)

    try:
        import requests

        base_url = os.environ.get('API_URL', 'http://localhost:8000')

        endpoints = [
            ("/api/argus/gamma", "ARGUS gamma"),
            ("/api/ares/market-data", "ARES market data"),
            ("/api/athena/diagnostics", "ATHENA diagnostics"),
        ]

        for endpoint, name in endpoints:
            try:
                resp = requests.get(f"{base_url}{endpoint}", timeout=10)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('success'):
                        check(f"{name} endpoint", True)

                        # Additional checks for specific endpoints
                        if 'ares' in endpoint:
                            em = data.get('data', {}).get('expected_move') or \
                                 data.get('data', {}).get('spx', {}).get('expected_move')
                            if em:
                                check(f"  - Expected move > 0", em > 0, f"EM={em}")
                            else:
                                check(f"  - Expected move present", False, "No expected_move in response")
                    else:
                        check(f"{name} endpoint", False, data.get('message', 'Unknown error'))
                else:
                    check(f"{name} endpoint", False, f"Status {resp.status_code}")

            except requests.exceptions.ConnectionError:
                check(f"{name} endpoint", False, "Server not running", warn_only=True)
            except Exception as e:
                check(f"{name} endpoint", False, str(e), warn_only=True)

    except ImportError:
        logger.info(f"{WARN} requests module not available, skipping API tests")


def test_argus_routes_optimization():
    """Test 8: ARGUS routes optimization code"""
    logger.info("\n" + "="*60)
    logger.info("TEST 8: ARGUS Routes Optimization")
    logger.info("="*60)

    try:
        with open('backend/api/routes/argus_routes.py', 'r') as f:
            source = f.read()

        checks = [
            ("Cache TTL = 60s", "CACHE_TTL_SECONDS = 60" in source),
            ("O(1) dictionary lookup", "options_by_key" in source),
            ("Expected move caching", "EM_CACHE_TTL = 300" in source),
            ("Cache result storage", "_em_result_cache[cache_key]" in source),
            ("Correct method name (get_option_chain)", "tradier.get_option_chain" in source),
            ("OptionChain dataclass handling", "option_chain.chains.get" in source),
        ]

        for name, condition in checks:
            check(name, condition)

    except Exception as e:
        check("ARGUS routes file", False, str(e))


def test_frontend_parallel_fetch():
    """Test 9: Frontend parallel API calls"""
    logger.info("\n" + "="*60)
    logger.info("TEST 9: Frontend Parallel API Calls")
    logger.info("="*60)

    try:
        with open('frontend/src/app/argus/page.tsx', 'r') as f:
            source = f.read()

        checks = [
            ("Promise.all for parallel fetch", "Promise.all([" in source),
            ("Last updated timestamp", "lastUpdated.toLocaleTimeString()" in source),
            ("Commentary debug logging", "[ARGUS] Fetching commentary" in source),
            ("Generate Commentary button", "Generate Commentary Now" in source),
        ]

        for name, condition in checks:
            check(name, condition)

    except Exception as e:
        check("Frontend file", False, str(e))


def print_summary():
    """Print test summary"""
    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)

    total = results['passed'] + results['failed'] + results['warnings']

    logger.info(f"  Passed:   {results['passed']}/{total}")
    logger.info(f"  Failed:   {results['failed']}/{total}")
    logger.info(f"  Warnings: {results['warnings']}/{total}")

    if results['failed'] == 0:
        logger.info(f"\n{PASS} All critical checks passed!")
        if results['warnings'] > 0:
            logger.info(f"{WARN} Some warnings to review above")
    else:
        logger.info(f"\n{FAIL} {results['failed']} checks failed - review above")

    logger.info("\n" + "="*60)
    logger.info("NEXT STEPS")
    logger.info("="*60)

    if results['failed'] > 0 or results['warnings'] > 0:
        logger.info("""
1. Run database migration if indexes missing:
   psql $DATABASE_URL -f db/migrations/006_argus_performance_indexes.sql

2. Restart backend to pick up changes:
   - ARGUS engine eager loading
   - New caching logic
   - Expected move validation

3. Check logs after restart for:
   - "ARGUS engine initialized with ML models pre-loaded"
   - "ARES Market Data: SPX=$XXXX, VIX=XX.XX, EM=$XX.XX"
   - "ATHENA Skip Decision: VIX=XX.XX, Expected Move=X.XX%"

4. Test in browser:
   - Open ARGUS page, check Strike Analysis has timestamp
   - Check browser console for [ARGUS] logs
   - Open ARES/ATHENA pages, verify expected move shows

5. Run existing test suites:
   pytest backend/tests/test_argus.py -v
   python scripts/test_athena_e2e.py
""")
    else:
        logger.info("All checks passed! The deployment is verified.")


def main():
    logger.info("="*60)
    logger.info("ARGUS Performance Fixes Verification")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*60)

    test_database_indexes()
    test_argus_engine()
    test_ares_validation()
    test_athena_expected_move()
    test_vix_fetcher()
    test_tradier_connection()
    test_api_endpoints()
    test_argus_routes_optimization()
    test_frontend_parallel_fetch()

    print_summary()

    return 0 if results['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
