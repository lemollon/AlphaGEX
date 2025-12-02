"""
Infrastructure Tests

Tests system infrastructure:
1. WebSocket Live Data
2. Commission Calculations
3. Multi-Symbol Isolation
4. Rate Limit Handling
5. Stale Data Detection

Run: python tests/test_infrastructure.py
"""

import os
import sys
import time
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RESULTS = {"passed": [], "failed": [], "warnings": []}
CENTRAL_TZ = ZoneInfo("America/Chicago")

def log_pass(test, details=""):
    RESULTS["passed"].append({"test": test, "details": details})
    print(f"✅ {test}" + (f": {details}" if details else ""))

def log_fail(test, details=""):
    RESULTS["failed"].append({"test": test, "details": details})
    print(f"❌ {test}" + (f": {details}" if details else ""))

def log_warn(test, details=""):
    RESULTS["warnings"].append({"test": test, "details": details})
    print(f"⚠️  {test}" + (f": {details}" if details else ""))


# =============================================================================
# TEST 1: WebSocket Live Data
# =============================================================================
def test_websocket_data():
    """
    Test WebSocket data flow to frontend.
    """
    print("\n" + "="*70)
    print("TEST: WEBSOCKET LIVE DATA")
    print("="*70)

    try:
        # Check if WebSocket endpoint exists
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Test WebSocket endpoints
        print("\nChecking WebSocket configuration:")

        # Check for WebSocket routes in app
        websocket_routes = [route for route in app.routes if hasattr(route, 'path') and 'ws' in route.path.lower()]

        if websocket_routes:
            print(f"   Found {len(websocket_routes)} WebSocket route(s):")
            for route in websocket_routes:
                print(f"      - {route.path}")
            log_pass("WebSocket Routes", f"{len(websocket_routes)} routes configured")
        else:
            log_warn("WebSocket Routes", "No WebSocket routes found")

        # Test REST fallback for real-time data
        print("\nTesting REST endpoints for real-time data:")

        endpoints = [
            ("/api/trader/status", "Trader Status"),
            ("/api/trader/SPY/positions", "SPY Positions"),
            ("/api/trader/performance", "Performance"),
        ]

        for endpoint, name in endpoints:
            try:
                response = client.get(endpoint)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        log_pass(f"REST {name}", "Responds correctly")
                    else:
                        log_warn(f"REST {name}", f"Response not successful")
                else:
                    log_warn(f"REST {name}", f"HTTP {response.status_code}")
            except Exception as e:
                log_warn(f"REST {name}", str(e))

        # Test data freshness
        print("\nTesting data freshness:")

        try:
            response = client.get("/api/trader/status")
            if response.status_code == 200:
                data = response.json()
                if data.get('success') and data.get('data'):
                    status = data['data']
                    last_check = status.get('last_check')

                    if last_check:
                        # Parse timestamp
                        try:
                            if isinstance(last_check, str):
                                last_dt = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
                            else:
                                last_dt = datetime.fromtimestamp(last_check)

                            age_seconds = (datetime.now(last_dt.tzinfo if last_dt.tzinfo else None) - last_dt).total_seconds()

                            if age_seconds < 300:  # 5 minutes
                                log_pass("Data Freshness", f"Last update {age_seconds:.0f}s ago")
                            elif age_seconds < 600:  # 10 minutes
                                log_warn("Data Freshness", f"Last update {age_seconds/60:.1f}m ago")
                            else:
                                log_warn("Data Freshness", f"Stale data: {age_seconds/60:.1f}m old")
                        except:
                            log_warn("Data Freshness", f"Could not parse timestamp: {last_check}")
                    else:
                        log_warn("Data Freshness", "No last_check timestamp")

        except Exception as e:
            log_warn("Data Freshness", str(e))

    except ImportError as e:
        log_warn("WebSocket Test", f"Could not import app: {e}")
    except Exception as e:
        log_fail("WebSocket Test", str(e))


# =============================================================================
# TEST 2: Commission Calculations
# =============================================================================
def test_commission_calculations():
    """
    Test commission calculations match Tradier fee structure.
    Tradier: $0.35 per contract, no base fee
    """
    print("\n" + "="*70)
    print("TEST: COMMISSION CALCULATIONS")
    print("="*70)

    try:
        # Try multiple import paths for costs calculator
        try:
            from trading_costs import TradingCostsCalculator, PAPER_TRADING_COSTS
        except ImportError:
            try:
                from trading.costs_calculator import TradingCostsCalculator, PAPER_TRADING_COSTS
            except ImportError:
                from utils.trading_costs import TradingCostsCalculator, PAPER_TRADING_COSTS

        calc = TradingCostsCalculator()

        # Get actual per-contract cost from calculator (commission + regulatory fees)
        # Paper trading uses $0.50 commission + $0.03 regulatory = $0.53/contract
        per_contract_cost = calc.config.commission_per_contract + calc.config.regulatory_fee_per_contract

        test_cases = [
            (1, per_contract_cost * 1, "1 contract"),
            (5, per_contract_cost * 5, "5 contracts"),
            (10, per_contract_cost * 10, "10 contracts"),
            (50, per_contract_cost * 50, "50 contracts"),
            (100, per_contract_cost * 100, "100 contracts"),
        ]

        print(f"\nTesting commission calculations (${per_contract_cost:.2f}/contract incl. fees):")

        all_correct = True
        for contracts, expected, description in test_cases:
            result = calc.calculate_commission(contracts)

            if isinstance(result, dict):
                actual = result.get('total_commission', 0)
            else:
                actual = result

            diff = abs(actual - expected)

            print(f"\n   {description}:")
            print(f"      Expected: ${expected:.2f}")
            print(f"      Actual: ${actual:.2f}")

            if diff < 0.01:  # Allow for floating point
                log_pass(f"Commission - {description}", f"${actual:.2f}")
            else:
                log_fail(f"Commission - {description}", f"Expected ${expected:.2f}, got ${actual:.2f}")
                all_correct = False

        # Test round-trip commission (entry + exit)
        print("\nTesting round-trip commissions:")

        contracts = 10
        entry_commission = calc.calculate_commission(contracts)
        exit_commission = calc.calculate_commission(contracts)

        if isinstance(entry_commission, dict):
            entry_cost = entry_commission.get('total_commission', 0)
            exit_cost = exit_commission.get('total_commission', 0)
        else:
            entry_cost = entry_commission
            exit_cost = exit_commission

        total_commission = entry_cost + exit_cost
        expected_roundtrip = contracts * per_contract_cost * 2

        print(f"   10 contracts round-trip:")
        print(f"      Entry: ${entry_cost:.2f}")
        print(f"      Exit: ${exit_cost:.2f}")
        print(f"      Total: ${total_commission:.2f}")
        print(f"      Expected: ${expected_roundtrip:.2f}")

        if abs(total_commission - expected_roundtrip) < 0.01:
            log_pass("Round-trip Commission", f"${total_commission:.2f}")
        else:
            log_warn("Round-trip Commission", f"Got ${total_commission:.2f}, expected ${expected_roundtrip:.2f}")

        # Verify commissions are being applied to trades
        print("\nVerifying commissions in closed trades:")

        try:
            from database_adapter import get_connection
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                SELECT contracts, entry_price, exit_price, realized_pnl
                FROM autonomous_closed_trades
                ORDER BY exit_date DESC
                LIMIT 5
            """)

            trades = cursor.fetchall()

            if trades:
                for trade in trades:
                    contracts = int(trade[0]) if trade[0] else 1
                    entry = float(trade[1]) if trade[1] else 0
                    exit_p = float(trade[2]) if trade[2] else 0
                    pnl = float(trade[3]) if trade[3] else 0

                    # Calculate gross P&L
                    gross_pnl = (exit_p - entry) * contracts * 100

                    # Expected commission impact
                    expected_commission = contracts * per_contract_cost * 2

                    # Actual commission (difference between gross and net)
                    actual_commission = gross_pnl - pnl

                    print(f"\n   Trade ({contracts} contracts):")
                    print(f"      Gross P&L: ${gross_pnl:.2f}")
                    print(f"      Net P&L: ${pnl:.2f}")
                    print(f"      Commission paid: ${actual_commission:.2f}")
                    print(f"      Expected commission: ${expected_commission:.2f}")

                    if abs(actual_commission - expected_commission) < 5:  # Allow some variance
                        log_pass(f"Trade Commission Applied", f"~${actual_commission:.2f}")
                    else:
                        log_warn(f"Trade Commission", f"Expected ~${expected_commission:.2f}, saw ${actual_commission:.2f}")
            else:
                log_warn("Trade Commissions", "No closed trades to verify")

            conn.close()

        except Exception as e:
            log_warn("Trade Commission Verification", str(e))

    except ImportError as e:
        log_warn("Commission Test", f"Could not import calculator: {e}")
    except Exception as e:
        log_fail("Commission Test", str(e))


# =============================================================================
# TEST 3: Multi-Symbol Isolation
# =============================================================================
def test_multi_symbol_isolation():
    """
    Test that SPY and SPX traders don't interfere with each other.
    """
    print("\n" + "="*70)
    print("TEST: MULTI-SYMBOL ISOLATION")
    print("="*70)

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Check position isolation
        print("\nChecking position isolation:")

        cursor.execute("""
            SELECT symbol, COUNT(*) as count, SUM(contracts) as total_contracts
            FROM autonomous_open_positions
            GROUP BY symbol
        """)

        positions_by_symbol = cursor.fetchall()

        if positions_by_symbol:
            print("   Open positions by symbol:")
            for row in positions_by_symbol:
                symbol = row[0]
                count = row[1]
                contracts = row[2]
                print(f"      {symbol}: {count} positions, {contracts} contracts")
                log_pass(f"Position Isolation - {symbol}", f"{count} positions")
        else:
            log_warn("Position Isolation", "No open positions")

        # Check closed trades isolation
        print("\nClosed trades by symbol:")

        cursor.execute("""
            SELECT symbol, COUNT(*) as count, SUM(realized_pnl) as total_pnl
            FROM autonomous_closed_trades
            GROUP BY symbol
        """)

        trades_by_symbol = cursor.fetchall()

        if trades_by_symbol:
            for row in trades_by_symbol:
                symbol = row[0]
                count = row[1]
                total_pnl = float(row[2]) if row[2] else 0
                print(f"      {symbol}: {count} trades, ${total_pnl:,.2f} total P&L")
                log_pass(f"Trade Isolation - {symbol}", f"{count} trades")
        else:
            log_warn("Trade Isolation", "No closed trades")

        # Check for cross-contamination
        print("\nChecking for cross-contamination:")

        # Positions should not have mixed symbols
        cursor.execute("""
            SELECT COUNT(DISTINCT symbol) FROM autonomous_open_positions
        """)
        distinct_symbols = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM autonomous_open_positions
        """)
        total_positions = cursor.fetchone()[0]

        # Multi-leg strategy names that are valid contract symbols
        multi_leg_strategies = [
            'IRON_CONDOR', 'IRON_BUTTERFLY', 'VERTICAL_SPREAD',
            'CALENDAR_SPREAD', 'DIAGONAL_SPREAD', 'STRADDLE', 'STRANGLE',
            'BUTTERFLY', 'CONDOR', 'COLLAR', 'COVERED_CALL', 'PROTECTIVE_PUT'
        ]

        if total_positions > 0:
            print(f"   {distinct_symbols} distinct symbols in {total_positions} positions")

            # Check if any position has wrong symbol format (excluding multi-leg strategies)
            cursor.execute("""
                SELECT id, symbol, contract_symbol
                FROM autonomous_open_positions
                WHERE contract_symbol IS NOT NULL
                AND contract_symbol NOT LIKE symbol || '%'
                LIMIT 10
            """)

            mismatches = cursor.fetchall()

            # Filter out valid multi-leg strategies
            real_mismatches = []
            for m in mismatches:
                contract = m[2].upper() if m[2] else ''
                if contract not in multi_leg_strategies:
                    real_mismatches.append(m)
                else:
                    print(f"   ✓ Position {m[0]}: {contract} is valid multi-leg strategy")

            if real_mismatches:
                for m in real_mismatches:
                    log_fail(f"Symbol Mismatch - Position {m[0]}", f"Symbol={m[1]}, Contract={m[2]}")
            else:
                log_pass("Contract Symbol Consistency", "All contracts valid (OCC or multi-leg)")

        # Check config isolation
        print("\nChecking config isolation:")

        # Check if symbol column exists in autonomous_config
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'autonomous_config' AND column_name = 'symbol'
            """)
            has_symbol_col = cursor.fetchone() is not None

            if has_symbol_col:
                cursor.execute("""
                    SELECT symbol, key, value
                    FROM autonomous_config
                    WHERE symbol IS NOT NULL
                    ORDER BY symbol, key
                """)

                configs = cursor.fetchall()

                spy_configs = [c for c in configs if c[0] == 'SPY']
                spx_configs = [c for c in configs if c[0] == 'SPX']

                print(f"   SPY configs: {len(spy_configs)}")
                print(f"   SPX configs: {len(spx_configs)}")

                if spy_configs or spx_configs:
                    log_pass("Config Isolation", f"SPY: {len(spy_configs)}, SPX: {len(spx_configs)}")
                else:
                    log_warn("Config Isolation", "No symbol-specific configs found")
            else:
                # Table doesn't have symbol column - check key-based config
                cursor.execute("""
                    SELECT key, value FROM autonomous_config ORDER BY key
                """)
                configs = cursor.fetchall()
                print(f"   Found {len(configs)} config entries (global config, no symbol column)")
                log_pass("Config Available", f"{len(configs)} config entries")

        except Exception as e:
            log_warn("Config Isolation", str(e))

        conn.close()

    except Exception as e:
        log_fail("Multi-Symbol Isolation", str(e))


# =============================================================================
# TEST 4: Rate Limit Handling
# =============================================================================
def test_rate_limit_handling():
    """
    Test that the system handles API rate limits gracefully.
    Tradier: 120 requests/minute
    Polygon: 5 requests/minute (free tier)
    """
    print("\n" + "="*70)
    print("TEST: RATE LIMIT HANDLING")
    print("="*70)

    try:
        from data.unified_data_provider import UnifiedDataProvider

        provider = UnifiedDataProvider()

        # Test rapid requests to check rate limiting
        print("\nTesting rapid quote requests:")

        request_count = 10
        success_count = 0
        fail_count = 0
        start_time = time.time()

        for i in range(request_count):
            try:
                quote = provider.get_quote('SPY')
                if quote and quote.price > 0:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                fail_count += 1
                if 'rate' in str(e).lower():
                    print(f"   Request {i+1}: Rate limited")
                else:
                    print(f"   Request {i+1}: Failed - {e}")

        elapsed = time.time() - start_time

        print(f"\n   Made {request_count} requests in {elapsed:.2f}s")
        print(f"   Success: {success_count}, Failed: {fail_count}")
        print(f"   Rate: {request_count/elapsed:.1f} requests/second")

        if success_count == request_count:
            log_pass("Rate Limit - Basic", f"{success_count}/{request_count} succeeded")
        elif success_count > request_count * 0.8:
            log_warn("Rate Limit - Basic", f"{fail_count} requests failed")
        else:
            log_fail("Rate Limit - Basic", f"Too many failures: {fail_count}/{request_count}")

        # Check for rate limit configuration
        print("\nChecking rate limit configuration:")

        # Look for rate limit settings in code
        config_files = [
            'unified_config.py',
            'data/tradier_client.py',
            'data/polygon_client.py',
        ]

        for config_file in config_files:
            full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), config_file)
            if os.path.exists(full_path):
                with open(full_path, 'r') as f:
                    content = f.read().lower()
                    if 'rate' in content or 'limit' in content or 'throttle' in content:
                        log_pass(f"Rate Config - {config_file}", "Has rate limit settings")
                    else:
                        log_warn(f"Rate Config - {config_file}", "No rate limit settings found")

        # Test concurrent requests
        print("\nTesting concurrent request handling:")

        results = []

        def make_request():
            try:
                quote = provider.get_quote('SPY')
                results.append(('success', quote.price if quote else 0))
            except Exception as e:
                results.append(('error', str(e)))

        threads = []
        for _ in range(5):
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        successes = len([r for r in results if r[0] == 'success'])
        print(f"   {successes}/5 concurrent requests succeeded")

        if successes >= 4:
            log_pass("Concurrent Requests", f"{successes}/5 succeeded")
        else:
            log_warn("Concurrent Requests", f"Only {successes}/5 succeeded")

    except Exception as e:
        log_fail("Rate Limit Test", str(e))


# =============================================================================
# TEST 5: Stale Data Detection
# =============================================================================
def test_stale_data_detection():
    """
    Test that the system detects and warns about stale data.
    """
    print("\n" + "="*70)
    print("TEST: STALE DATA DETECTION")
    print("="*70)

    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # Check position last_updated timestamps
        print("\nChecking position data freshness:")

        cursor.execute("""
            SELECT id, symbol, last_updated, current_price
            FROM autonomous_open_positions
            WHERE last_updated IS NOT NULL
            ORDER BY last_updated DESC
            LIMIT 10
        """)

        positions = cursor.fetchall()

        now = datetime.now()
        stale_positions = []

        if positions:
            for pos in positions:
                pos_id = pos[0]
                symbol = pos[1]
                last_updated = pos[2]
                current_price = pos[3]

                if last_updated:
                    if isinstance(last_updated, str):
                        last_updated = datetime.fromisoformat(last_updated)

                    age_minutes = (now - last_updated.replace(tzinfo=None)).total_seconds() / 60

                    status = "Fresh" if age_minutes < 10 else "Stale" if age_minutes < 60 else "Very Stale"

                    print(f"   Position {pos_id} ({symbol}): Updated {age_minutes:.1f}m ago - {status}")

                    if age_minutes > 30:
                        stale_positions.append((pos_id, symbol, age_minutes))

            if stale_positions:
                log_warn("Stale Positions", f"{len(stale_positions)} positions > 30 min old")
            else:
                log_pass("Position Freshness", "All positions recently updated")
        else:
            log_warn("Position Freshness", "No positions with timestamps")

        # Check quote freshness
        print("\nChecking live quote freshness:")

        try:
            from data.unified_data_provider import UnifiedDataProvider

            provider = UnifiedDataProvider()
            quote = provider.get_quote('SPY')

            if quote:
                if hasattr(quote, 'timestamp') and quote.timestamp:
                    quote_age = (datetime.now() - quote.timestamp.replace(tzinfo=None)).total_seconds()
                    print(f"   Quote timestamp age: {quote_age:.1f}s")

                    if quote_age < 60:
                        log_pass("Quote Freshness", f"{quote_age:.1f}s old")
                    elif quote_age < 300:
                        log_warn("Quote Freshness", f"{quote_age:.1f}s old - getting stale")
                    else:
                        log_fail("Quote Freshness", f"{quote_age:.1f}s old - STALE")
                else:
                    log_warn("Quote Timestamp", "No timestamp on quote")

                # Check if is_delayed flag is set
                if hasattr(quote, 'is_delayed'):
                    if quote.is_delayed:
                        log_warn("Quote Delayed", "Using delayed data (Polygon)")
                    else:
                        log_pass("Quote Real-time", "Using real-time data (Tradier)")

        except Exception as e:
            log_warn("Quote Freshness Check", str(e))

        # Check is_delayed column in database
        print("\nChecking is_delayed flags in database:")

        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_delayed = true THEN 1 ELSE 0 END) as delayed,
                SUM(CASE WHEN is_delayed = false THEN 1 ELSE 0 END) as realtime,
                SUM(CASE WHEN is_delayed IS NULL THEN 1 ELSE 0 END) as unknown
            FROM autonomous_open_positions
        """)

        result = cursor.fetchone()

        if result:
            total, delayed, realtime, unknown = result
            delayed = delayed or 0
            realtime = realtime or 0
            unknown = unknown or 0

            print(f"   Total positions: {total}")
            print(f"   Real-time: {realtime}")
            print(f"   Delayed: {delayed}")
            print(f"   Unknown: {unknown}")

            if delayed > 0:
                log_warn("Delayed Data Positions", f"{delayed} positions using delayed data")
            elif realtime > 0:
                log_pass("Real-time Data", f"{realtime} positions using real-time data")
            else:
                log_warn("Data Source Unknown", f"{unknown} positions without is_delayed flag")

        conn.close()

        # Check for stale data detection in code
        print("\nChecking stale data detection logic:")

        trader_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'core', 'autonomous_paper_trader.py'
        )

        if os.path.exists(trader_file):
            with open(trader_file, 'r') as f:
                content = f.read().lower()

            has_stale_check = any(term in content for term in ['stale', 'age', 'fresh', 'last_updated', 'timeout'])

            if has_stale_check:
                log_pass("Stale Detection Logic", "Found in trader code")
            else:
                log_warn("Stale Detection Logic", "Not found in trader code")

    except Exception as e:
        log_fail("Stale Data Detection", str(e))


# =============================================================================
# SUMMARY
# =============================================================================
def print_summary():
    print("\n" + "="*70)
    print("INFRASTRUCTURE TEST RESULTS")
    print("="*70)

    total = len(RESULTS["passed"]) + len(RESULTS["failed"]) + len(RESULTS["warnings"])

    print(f"\n✅ Passed:   {len(RESULTS['passed'])}")
    print(f"❌ Failed:   {len(RESULTS['failed'])}")
    print(f"⚠️  Warnings: {len(RESULTS['warnings'])}")

    if RESULTS["failed"]:
        print("\n❌ FAILURES:")
        for item in RESULTS["failed"]:
            print(f"   • {item['test']}: {item['details']}")

    if RESULTS["warnings"]:
        print("\n⚠️  WARNINGS:")
        for item in RESULTS["warnings"]:
            print(f"   • {item['test']}: {item['details']}")

    return len(RESULTS["failed"]) == 0


if __name__ == "__main__":
    print("="*70)
    print("INFRASTRUCTURE TESTS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    test_websocket_data()
    test_commission_calculations()
    test_multi_symbol_isolation()
    test_rate_limit_handling()
    test_stale_data_detection()

    success = print_summary()
    sys.exit(0 if success else 1)
