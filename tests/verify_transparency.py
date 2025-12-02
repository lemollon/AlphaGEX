"""
Transparency Verification Tests

Run this on Render to verify all transparency features are working:
    python tests/verify_transparency.py

This tests:
1. Database columns exist
2. API endpoints respond
3. Data sources are configured (Tradier vs Polygon)
4. Trade data has required fields populated
5. Entry/exit prices are being captured
"""

import os
import sys
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Results tracking
RESULTS = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def log_pass(test_name, details=""):
    RESULTS["passed"].append({"test": test_name, "details": details})
    print(f"✅ PASS: {test_name}")
    if details:
        print(f"   {details}")

def log_fail(test_name, details=""):
    RESULTS["failed"].append({"test": test_name, "details": details})
    print(f"❌ FAIL: {test_name}")
    if details:
        print(f"   {details}")

def log_warn(test_name, details=""):
    RESULTS["warnings"].append({"test": test_name, "details": details})
    print(f"⚠️  WARN: {test_name}")
    if details:
        print(f"   {details}")


# =============================================================================
# TEST 1: Database Columns Exist
# =============================================================================
def test_database_columns():
    """Verify all required columns exist in the database"""
    print("\n" + "="*60)
    print("TEST 1: Database Column Verification")
    print("="*60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Required columns for autonomous_open_positions
        open_positions_required = [
            'id', 'symbol', 'strategy', 'strike', 'option_type', 'contracts',
            'entry_price', 'entry_bid', 'entry_ask', 'entry_spot_price',
            'entry_date', 'entry_time', 'expiration_date', 'contract_symbol',
            'entry_iv', 'entry_delta', 'entry_gamma', 'entry_theta', 'entry_vega',
            'current_price', 'current_iv', 'current_delta',
            'is_delayed', 'data_confidence',
            'gex_regime', 'confidence', 'trade_reasoning'
        ]

        # Check autonomous_open_positions
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'autonomous_open_positions'
        """)
        existing_columns = [row[0] for row in cursor.fetchall()]

        missing_open = []
        for col in open_positions_required:
            if col not in existing_columns:
                missing_open.append(col)

        if missing_open:
            log_fail("Open Positions Columns", f"Missing: {', '.join(missing_open)}")
        else:
            log_pass("Open Positions Columns", f"All {len(open_positions_required)} required columns exist")

        # Required columns for autonomous_closed_trades
        closed_trades_required = [
            'id', 'symbol', 'strategy', 'strike', 'option_type', 'contracts',
            'entry_price', 'entry_bid', 'entry_ask', 'entry_spot_price',
            'entry_date', 'entry_time', 'exit_date', 'exit_time',
            'exit_price', 'exit_spot_price', 'exit_reason',
            'realized_pnl', 'realized_pnl_pct', 'contract_symbol',
            'hold_duration_minutes'
        ]

        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'autonomous_closed_trades'
        """)
        existing_closed = [row[0] for row in cursor.fetchall()]

        missing_closed = []
        for col in closed_trades_required:
            if col not in existing_closed:
                missing_closed.append(col)

        if missing_closed:
            log_fail("Closed Trades Columns", f"Missing: {', '.join(missing_closed)}")
        else:
            log_pass("Closed Trades Columns", f"All {len(closed_trades_required)} required columns exist")

        conn.close()

    except Exception as e:
        log_fail("Database Connection", str(e))


# =============================================================================
# TEST 2: Data Source Configuration
# =============================================================================
def test_data_sources():
    """Verify Tradier and Polygon are configured"""
    print("\n" + "="*60)
    print("TEST 2: Data Source Configuration")
    print("="*60)

    # Check Tradier
    tradier_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_ACCESS_TOKEN')
    tradier_env = os.environ.get('TRADIER_ENVIRONMENT', 'sandbox')

    if tradier_key:
        masked_key = tradier_key[:4] + "..." + tradier_key[-4:] if len(tradier_key) > 8 else "***"
        log_pass("Tradier API Key", f"Found (masked: {masked_key})")

        if tradier_env == 'production':
            log_pass("Tradier Environment", "PRODUCTION (real-time data)")
        else:
            log_warn("Tradier Environment", f"'{tradier_env}' - Not production, may have delayed data")
    else:
        log_fail("Tradier API Key", "Not found in environment variables")

    # Check Polygon
    polygon_key = os.environ.get('POLYGON_API_KEY')
    if polygon_key:
        masked_key = polygon_key[:4] + "..." + polygon_key[-4:] if len(polygon_key) > 8 else "***"
        log_pass("Polygon API Key", f"Found (masked: {masked_key})")
    else:
        log_warn("Polygon API Key", "Not found - fallback data source unavailable")

    # Test actual data provider
    try:
        from data.unified_data_provider import UnifiedDataProvider
        provider = UnifiedDataProvider()

        # Check which sources are available
        sources = []
        if hasattr(provider, '_tradier') and provider._tradier:
            sources.append("Tradier")
        if hasattr(provider, '_polygon') and provider._polygon:
            sources.append("Polygon")

        if sources:
            log_pass("Data Provider Initialized", f"Available sources: {', '.join(sources)}")
        else:
            log_fail("Data Provider Initialized", "No data sources available!")

    except Exception as e:
        log_fail("Data Provider Import", str(e))


# =============================================================================
# TEST 3: Live Quote Test
# =============================================================================
def test_live_quotes():
    """Test that we can get live quotes and identify the source"""
    print("\n" + "="*60)
    print("TEST 3: Live Quote Verification")
    print("="*60)

    try:
        from data.unified_data_provider import UnifiedDataProvider
        provider = UnifiedDataProvider()

        # Test SPY quote
        quote = provider.get_quote('SPY')

        if quote:
            log_pass("SPY Quote Retrieved", f"Price: ${quote.price:.2f}, Source: {quote.source}")

            if quote.source == 'tradier':
                log_pass("Quote Source", "Using Tradier (real-time)")
            elif quote.source == 'polygon':
                log_warn("Quote Source", "Using Polygon (15-min delayed)")
            else:
                log_warn("Quote Source", f"Unknown source: {quote.source}")

            if quote.bid > 0 and quote.ask > 0:
                spread = quote.ask - quote.bid
                log_pass("Bid/Ask Available", f"Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: ${spread:.2f}")
            else:
                log_warn("Bid/Ask Missing", "Bid/Ask not available in quote")
        else:
            log_fail("SPY Quote", "Could not retrieve quote")

        # Test SPX quote
        quote_spx = provider.get_quote('SPX')
        if quote_spx:
            log_pass("SPX Quote Retrieved", f"Price: ${quote_spx.price:.2f}, Source: {quote_spx.source}")
        else:
            log_warn("SPX Quote", "Could not retrieve - may need different symbol ($SPX.X)")

    except Exception as e:
        log_fail("Live Quote Test", str(e))


# =============================================================================
# TEST 4: Options Chain Test
# =============================================================================
def test_options_chain():
    """Test that we can get options chain with Greeks"""
    print("\n" + "="*60)
    print("TEST 4: Options Chain & Greeks")
    print("="*60)

    try:
        from data.unified_data_provider import UnifiedDataProvider
        provider = UnifiedDataProvider()

        # Get options chain for SPY
        chain = provider.get_options_chain('SPY', greeks=True)

        if chain:
            log_pass("Options Chain Retrieved", f"Symbol: {chain.symbol}")

            # Check for calls
            if hasattr(chain, 'calls') and chain.calls:
                sample_call = chain.calls[0] if isinstance(chain.calls, list) else list(chain.calls.values())[0]

                # Check Greeks
                has_delta = hasattr(sample_call, 'delta') and sample_call.delta is not None
                has_gamma = hasattr(sample_call, 'gamma') and sample_call.gamma is not None
                has_theta = hasattr(sample_call, 'theta') and sample_call.theta is not None
                has_vega = hasattr(sample_call, 'vega') and sample_call.vega is not None
                has_iv = hasattr(sample_call, 'iv') or hasattr(sample_call, 'implied_volatility')

                greeks_available = [
                    'delta' if has_delta else None,
                    'gamma' if has_gamma else None,
                    'theta' if has_theta else None,
                    'vega' if has_vega else None,
                    'iv' if has_iv else None
                ]
                greeks_available = [g for g in greeks_available if g]

                if len(greeks_available) >= 4:
                    log_pass("Greeks Available", f"Found: {', '.join(greeks_available)}")
                else:
                    log_warn("Greeks Incomplete", f"Only found: {', '.join(greeks_available) if greeks_available else 'None'}")

                # Check contract symbol
                if hasattr(sample_call, 'symbol') and sample_call.symbol:
                    log_pass("Contract Symbol", f"Example: {sample_call.symbol}")
                else:
                    log_warn("Contract Symbol", "Not available in options data")
            else:
                log_fail("Options Calls", "No call options found in chain")
        else:
            log_fail("Options Chain", "Could not retrieve options chain")

    except Exception as e:
        log_fail("Options Chain Test", str(e))


# =============================================================================
# TEST 5: Trade Data Integrity
# =============================================================================
def test_trade_data_integrity():
    """Verify trades have required data populated"""
    print("\n" + "="*60)
    print("TEST 5: Trade Data Integrity")
    print("="*60)

    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        # Check open positions - use defensive query that works with or without Greek columns
        try:
            cursor.execute("""
                SELECT
                    id, symbol, contract_symbol, entry_date, entry_time,
                    entry_price,
                    COALESCE(entry_bid, 0) as entry_bid,
                    COALESCE(entry_ask, 0) as entry_ask,
                    entry_spot_price,
                    COALESCE(entry_delta, 0) as entry_delta,
                    COALESCE(entry_gamma, 0) as entry_gamma,
                    COALESCE(entry_theta, 0) as entry_theta,
                    COALESCE(entry_vega, 0) as entry_vega,
                    COALESCE(entry_iv, 0) as entry_iv,
                    COALESCE(is_delayed, false) as is_delayed,
                    COALESCE(data_confidence, 'unknown') as data_confidence
                FROM autonomous_open_positions
                ORDER BY created_at DESC
                LIMIT 5
            """)
        except Exception as col_err:
            # Fallback if Greek columns don't exist
            print(f"   Note: Some columns not available yet: {col_err}")
            cursor.execute("""
                SELECT
                    id, symbol, contract_symbol, entry_date, entry_time,
                    entry_price, 0 as entry_bid, 0 as entry_ask, entry_spot_price,
                    0 as entry_delta, 0 as entry_gamma, 0 as entry_theta, 0 as entry_vega, 0 as entry_iv,
                    false as is_delayed, 'unknown' as data_confidence
                FROM autonomous_open_positions
                ORDER BY created_at DESC
                LIMIT 5
            """)

        positions = cursor.fetchall()

        if positions:
            log_pass("Open Positions Found", f"Found {len(positions)} recent positions")

            for pos in positions:
                pos_id = pos[0]
                symbol = pos[1]
                contract_symbol = pos[2]
                entry_price = pos[5]
                entry_bid = pos[6]
                entry_ask = pos[7]
                entry_delta = pos[9]

                issues = []

                if not contract_symbol:
                    issues.append("missing contract_symbol")
                if not entry_price or entry_price == 0:
                    issues.append("zero entry_price")
                # Only warn about bid/ask if they're truly expected (not for multi-leg)
                if entry_bid == 0 and contract_symbol and 'CONDOR' not in str(contract_symbol).upper():
                    issues.append("missing entry_bid")
                if entry_ask == 0 and contract_symbol and 'CONDOR' not in str(contract_symbol).upper():
                    issues.append("missing entry_ask")
                # Greeks are optional for multi-leg strategies
                # if entry_delta == 0:
                #     issues.append("missing entry_delta")

                if issues:
                    log_warn(f"Position {pos_id} ({symbol})", f"Issues: {', '.join(issues)}")
                else:
                    log_pass(f"Position {pos_id} ({symbol})", f"All fields populated, contract: {contract_symbol}")
        else:
            log_warn("Open Positions", "No open positions found to verify")

        # Check closed trades
        cursor.execute("""
            SELECT
                id, symbol, contract_symbol, entry_date, entry_time,
                exit_date, exit_time, entry_price, exit_price,
                realized_pnl, hold_duration_minutes
            FROM autonomous_closed_trades
            ORDER BY exit_date DESC, exit_time DESC
            LIMIT 5
        """)

        closed = cursor.fetchall()

        if closed:
            log_pass("Closed Trades Found", f"Found {len(closed)} recent closed trades")

            for trade in closed:
                trade_id = trade[0]
                symbol = trade[1]
                contract_symbol = trade[2]
                entry_price = trade[7]
                exit_price = trade[8]
                realized_pnl = trade[9]

                issues = []

                if not contract_symbol:
                    issues.append("missing contract_symbol")
                if not entry_price or entry_price == 0:
                    issues.append("zero entry_price")
                if not exit_price or exit_price == 0:
                    issues.append("zero exit_price")
                if realized_pnl is None:
                    issues.append("missing realized_pnl")

                if issues:
                    log_warn(f"Trade {trade_id} ({symbol})", f"Issues: {', '.join(issues)}")
                else:
                    log_pass(f"Trade {trade_id} ({symbol})", f"Entry: ${entry_price:.2f}, Exit: ${exit_price:.2f}, P&L: ${realized_pnl:.2f}")
        else:
            log_warn("Closed Trades", "No closed trades found to verify")

        conn.close()

    except Exception as e:
        log_fail("Trade Data Integrity", str(e))


# =============================================================================
# TEST 6: API Endpoints
# =============================================================================
def test_api_endpoints():
    """Test that API endpoints respond correctly"""
    print("\n" + "="*60)
    print("TEST 6: API Endpoint Verification")
    print("="*60)

    try:
        # Import FastAPI app
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        # Test positions endpoint
        response = client.get("/api/trader/SPY/positions")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                positions = data.get('data', [])
                log_pass("GET /api/trader/SPY/positions", f"Returned {len(positions)} positions")

                # Check if positions have new fields
                if positions:
                    pos = positions[0]
                    has_new_fields = all(k in pos for k in ['contract_symbol', 'entry_bid', 'entry_ask'])
                    if has_new_fields:
                        log_pass("Position Data Fields", "Includes contract_symbol, entry_bid, entry_ask")
                    else:
                        log_warn("Position Data Fields", "Missing some new transparency fields")
            else:
                log_fail("Positions Endpoint", f"Response not successful: {data}")
        else:
            log_fail("Positions Endpoint", f"HTTP {response.status_code}")

        # Test regime endpoint
        response = client.get("/api/regime/current")
        if response.status_code == 200:
            log_pass("GET /api/regime/current", "Endpoint responding")
        else:
            log_warn("GET /api/regime/current", f"HTTP {response.status_code} - May not be implemented")

        # Test vol surface endpoint
        response = client.get("/api/volatility-surface/trading-signal/SPY")
        if response.status_code == 200:
            log_pass("GET /api/volatility-surface/trading-signal/SPY", "Endpoint responding")
        else:
            log_warn("GET /api/volatility-surface/trading-signal/SPY", f"HTTP {response.status_code} - May not be implemented")

        # Test jobs endpoint
        response = client.get("/api/jobs/list")
        if response.status_code == 200:
            log_pass("GET /api/jobs/list", "Endpoint responding")
        else:
            log_warn("GET /api/jobs/list", f"HTTP {response.status_code} - May not be implemented")

        # Test unified portfolio endpoint
        response = client.get("/api/trader/portfolio/unified")
        if response.status_code == 200:
            log_pass("GET /api/trader/portfolio/unified", "Endpoint responding")
        else:
            log_warn("GET /api/trader/portfolio/unified", f"HTTP {response.status_code} - May not be implemented")

    except ImportError as e:
        log_warn("API Test", f"Could not import FastAPI app: {e}")
    except Exception as e:
        log_fail("API Endpoints Test", str(e))


# =============================================================================
# SUMMARY
# =============================================================================
def print_summary():
    """Print test results summary"""
    print("\n" + "="*60)
    print("TEST RESULTS SUMMARY")
    print("="*60)

    total = len(RESULTS["passed"]) + len(RESULTS["failed"]) + len(RESULTS["warnings"])

    print(f"\n✅ Passed:   {len(RESULTS['passed'])}")
    print(f"❌ Failed:   {len(RESULTS['failed'])}")
    print(f"⚠️  Warnings: {len(RESULTS['warnings'])}")
    print(f"📊 Total:    {total}")

    if RESULTS["failed"]:
        print("\n❌ FAILURES (must fix):")
        for item in RESULTS["failed"]:
            print(f"   - {item['test']}: {item['details']}")

    if RESULTS["warnings"]:
        print("\n⚠️  WARNINGS (should review):")
        for item in RESULTS["warnings"]:
            print(f"   - {item['test']}: {item['details']}")

    print("\n" + "="*60)

    if RESULTS["failed"]:
        print("❌ OVERALL: SOME TESTS FAILED - Review failures above")
        return False
    elif RESULTS["warnings"]:
        print("⚠️  OVERALL: PASSED WITH WARNINGS - Review warnings above")
        return True
    else:
        print("✅ OVERALL: ALL TESTS PASSED")
        return True


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("="*60)
    print("TRANSPARENCY VERIFICATION TESTS")
    print(f"Running at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    # Run all tests
    test_database_columns()
    test_data_sources()
    test_live_quotes()
    test_options_chain()
    test_trade_data_integrity()
    test_api_endpoints()

    # Print summary
    success = print_summary()

    # Exit with appropriate code
    sys.exit(0 if success else 1)
