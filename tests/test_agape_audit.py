"""
AGAPE Implementation Verification Tests

Tests the AGAPE ETH Micro Futures bot end-to-end:
- API endpoint responses and contract shapes
- Backend → Data layer wiring
- Frontend ↔ Backend contract matching
- Database schema integrity

Usage:
    python tests/test_agape_audit.py --api-url https://your-backend.com
    python tests/test_agape_audit.py  # defaults to localhost:8000
"""

import argparse
import sys
import json

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Run: pip install requests")
    sys.exit(1)


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name, reason=""):
        self.failed += 1
        msg = f"  [FAIL] {name}: {reason}" if reason else f"  [FAIL] {name}"
        print(msg)
        self.errors.append(msg)

    def total(self):
        return self.passed + self.failed


# ===========================================================================
# PHASE 1: API Endpoint Tests
# ===========================================================================

def test_api_endpoints(api_url: str, results: TestResult):
    """Test all 13 AGAPE API endpoints exist and return correct shapes."""
    print("\n=== PHASE 1A: API ENDPOINT TESTS ===\n")

    endpoints = [
        # (method, path, expected_status, required_fields)
        ("GET", "/api/agape/status", 200, ["success"]),
        ("GET", "/api/agape/positions", 200, ["success"]),
        ("GET", "/api/agape/closed-trades?limit=10", 200, ["success"]),
        ("GET", "/api/agape/equity-curve?days=30", 200, ["success"]),
        ("GET", "/api/agape/equity-curve/intraday", 200, ["success"]),
        ("GET", "/api/agape/performance", 200, ["success"]),
        ("GET", "/api/agape/logs?limit=5", 200, ["success"]),
        ("GET", "/api/agape/scan-activity?limit=5", 200, ["success"]),
        ("GET", "/api/agape/snapshot", 200, ["success"]),
        ("GET", "/api/agape/signal", 200, ["success"]),
        ("GET", "/api/agape/gex-mapping", 200, ["success", "data"]),
    ]

    for method, path, expected_status, required_fields in endpoints:
        try:
            url = f"{api_url}{path}"
            if method == "GET":
                resp = requests.get(url, timeout=10)
            else:
                resp = requests.post(url, timeout=10)

            if resp.status_code != expected_status:
                results.fail(
                    f"{method} {path}",
                    f"Expected {expected_status}, got {resp.status_code}"
                )
                continue

            data = resp.json()
            missing = [f for f in required_fields if f not in data]
            if missing:
                results.fail(
                    f"{method} {path} response shape",
                    f"Missing fields: {missing}"
                )
            else:
                results.ok(f"{method} {path} → {resp.status_code}")

        except requests.exceptions.ConnectionError:
            results.fail(f"{method} {path}", "Connection refused (server not running?)")
        except requests.exceptions.Timeout:
            results.fail(f"{method} {path}", "Timeout (>10s)")
        except Exception as e:
            results.fail(f"{method} {path}", str(e))


# ===========================================================================
# PHASE 2: Contract Tests (Frontend ↔ Backend)
# ===========================================================================

def test_equity_curve_contract(api_url: str, results: TestResult):
    """Test equity curve matches the format MultiBotEquityCurve expects."""
    print("\n=== PHASE 2A: EQUITY CURVE CONTRACT ===\n")

    try:
        resp = requests.get(f"{api_url}/api/agape/equity-curve?days=30", timeout=10)
        data = resp.json()

        # MultiBotEquityCurve checks: data?.success && data.data?.equity_curve
        if data.get("success"):
            results.ok("equity-curve has 'success' field")
        else:
            results.fail("equity-curve 'success' field", f"Got: {data.get('success')}")

        inner = data.get("data", {})
        if isinstance(inner, dict) and "equity_curve" in inner:
            results.ok("equity-curve has 'data.equity_curve' wrapper")
        else:
            results.fail("equity-curve 'data.equity_curve'", "Missing wrapper - MultiBotEquityCurve won't render")

        # Check equity curve point shape
        curve = inner.get("equity_curve", []) if isinstance(inner, dict) else []
        if curve:
            point = curve[0]
            required = ["date", "equity", "daily_pnl", "cumulative_pnl"]
            missing = [f for f in required if f not in point]
            if missing:
                results.fail("equity curve point shape", f"Missing: {missing}")
            else:
                results.ok("equity curve point has all required fields")
        else:
            results.ok("equity curve is empty (no trades yet - OK)")

        # Check summary fields
        summary_fields = ["starting_capital", "current_equity", "total_pnl", "total_return_pct"]
        missing = [f for f in summary_fields if f not in inner]
        if missing:
            results.fail("equity curve summary fields", f"Missing: {missing}")
        else:
            results.ok("equity curve has all summary fields")

    except Exception as e:
        results.fail("equity-curve contract", str(e))


def test_status_contract(api_url: str, results: TestResult):
    """Test /status returns all fields the frontend page expects."""
    print("\n=== PHASE 2B: STATUS CONTRACT ===\n")

    try:
        resp = requests.get(f"{api_url}/api/agape/status", timeout=10)
        data = resp.json()
        status = data.get("data", {})

        if not status and data.get("data_unavailable"):
            results.ok("status returns unavailable (trader not initialized - OK for cold start)")
            return

        required = [
            "status", "current_eth_price", "open_positions", "max_positions",
            "starting_capital", "instrument", "risk_per_trade_pct",
            "max_contracts", "cooldown_minutes", "require_oracle", "cycle_count", "mode"
        ]

        if not isinstance(status, dict):
            results.fail("status response", f"Expected dict, got {type(status).__name__}")
            return

        missing = [f for f in required if f not in status]
        if missing:
            results.fail("status missing fields", f"Frontend expects: {missing}")
        else:
            results.ok(f"status has all {len(required)} required fields")

    except Exception as e:
        results.fail("status contract", str(e))


def test_performance_contract(api_url: str, results: TestResult):
    """Test /performance returns all fields the frontend expects."""
    print("\n=== PHASE 2C: PERFORMANCE CONTRACT ===\n")

    try:
        resp = requests.get(f"{api_url}/api/agape/performance", timeout=10)
        data = resp.json()
        perf = data.get("data", {})

        if not isinstance(perf, dict):
            results.ok("performance returns unavailable (trader not initialized - OK)")
            return

        required = ["total_pnl", "win_rate", "total_trades", "profit_factor", "avg_win", "avg_loss", "return_pct"]
        missing = [f for f in required if f not in perf]
        if missing:
            results.fail("performance missing fields", f"Frontend expects: {missing}")
        else:
            results.ok(f"performance has all {len(required)} required fields")

    except Exception as e:
        results.fail("performance contract", str(e))


def test_gex_mapping_contract(api_url: str, results: TestResult):
    """Test /gex-mapping returns static reference data correctly."""
    print("\n=== PHASE 2D: GEX MAPPING CONTRACT ===\n")

    try:
        resp = requests.get(f"{api_url}/api/agape/gex-mapping", timeout=10)
        data = resp.json()
        mapping = data.get("data", {})

        required = ["title", "description", "mappings", "trade_instrument"]
        missing = [f for f in required if f not in mapping]
        if missing:
            results.fail("gex-mapping missing fields", f"Missing: {missing}")
        else:
            results.ok("gex-mapping has all required fields")

        mappings = mapping.get("mappings", [])
        if len(mappings) == 6:
            results.ok(f"gex-mapping has {len(mappings)} signal mappings")
        else:
            results.fail("gex-mapping count", f"Expected 6, got {len(mappings)}")

    except Exception as e:
        results.fail("gex-mapping contract", str(e))


# ===========================================================================
# PHASE 3: Backend Wiring Tests
# ===========================================================================

def test_backend_wiring(api_url: str, results: TestResult):
    """Test that backend routes call real methods (not stubs)."""
    print("\n=== PHASE 3: BACKEND WIRING ===\n")

    # Test that snapshot returns structured crypto data (not empty)
    try:
        resp = requests.get(f"{api_url}/api/agape/snapshot?symbol=ETH", timeout=15)
        data = resp.json()

        if data.get("data_unavailable"):
            results.ok("snapshot: provider unavailable (expected without COINGLASS_API_KEY)")
        elif data.get("data"):
            snap = data["data"]
            signal_fields = ["funding", "liquidations", "long_short", "crypto_gex", "signals"]
            missing = [f for f in signal_fields if f not in snap]
            if missing:
                results.fail("snapshot crypto data", f"Missing signal groups: {missing}")
            else:
                results.ok("snapshot returns full crypto microstructure data")
        else:
            results.fail("snapshot", "No data and no unavailable flag")
    except Exception as e:
        results.fail("snapshot wiring", str(e))

    # Test enable/disable (POST) endpoints
    for action in ["disable", "enable"]:
        try:
            resp = requests.post(f"{api_url}/api/agape/{action}", timeout=10)
            if resp.status_code in (200, 503):
                results.ok(f"POST /{action} → {resp.status_code}")
            else:
                results.fail(f"POST /{action}", f"Unexpected status: {resp.status_code}")
        except Exception as e:
            results.fail(f"POST /{action}", str(e))

    # Test 404 for nonexistent endpoint
    try:
        resp = requests.get(f"{api_url}/api/agape/nonexistent", timeout=5)
        if resp.status_code in (404, 405):
            results.ok("nonexistent endpoint returns 404/405")
        else:
            results.fail("404 handling", f"Expected 404, got {resp.status_code}")
    except Exception as e:
        results.fail("404 handling", str(e))


# ===========================================================================
# PHASE 4: Code Structure Tests (no server needed)
# ===========================================================================

def test_code_structure(results: TestResult):
    """Test code structure and imports without running the server."""
    print("\n=== PHASE 4: CODE STRUCTURE ===\n")
    import ast
    import os

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Test all AGAPE files parse correctly
    files = [
        "trading/agape/__init__.py",
        "trading/agape/models.py",
        "trading/agape/db.py",
        "trading/agape/signals.py",
        "trading/agape/executor.py",
        "trading/agape/trader.py",
        "data/crypto_data_provider.py",
        "backend/api/routes/agape_routes.py",
    ]

    for f in files:
        path = os.path.join(base, f)
        if not os.path.exists(path):
            results.fail(f"File exists: {f}", "NOT FOUND")
            continue
        try:
            with open(path) as fh:
                ast.parse(fh.read())
            results.ok(f"Syntax OK: {f}")
        except SyntaxError as e:
            results.fail(f"Syntax: {f}", str(e))

    # Test frontend files exist
    frontend_files = [
        "frontend/src/app/agape/page.tsx",
        "frontend/src/components/charts/MultiBotEquityCurve.tsx",
    ]
    for f in frontend_files:
        path = os.path.join(base, f)
        if os.path.exists(path):
            results.ok(f"File exists: {f}")
        else:
            results.fail(f"File exists: {f}", "NOT FOUND")

    # Test AGAPE is in navigation
    nav_path = os.path.join(base, "frontend/src/components/Navigation.tsx")
    if os.path.exists(nav_path):
        with open(nav_path) as fh:
            content = fh.read()
        if "/agape" in content:
            results.ok("AGAPE in Navigation.tsx")
        else:
            results.fail("AGAPE in Navigation.tsx", "href='/agape' not found")

    # Test AGAPE in BotBranding
    branding_path = os.path.join(base, "frontend/src/components/trader/BotBranding.tsx")
    if os.path.exists(branding_path):
        with open(branding_path) as fh:
            content = fh.read()
        if "AGAPE" in content:
            results.ok("AGAPE in BotBranding.tsx")
        else:
            results.fail("AGAPE in BotBranding.tsx", "AGAPE not in BotName type")

    # Test AGAPE in MultiBotEquityCurve LIVE_BOTS
    mbc_path = os.path.join(base, "frontend/src/components/charts/MultiBotEquityCurve.tsx")
    if os.path.exists(mbc_path):
        with open(mbc_path) as fh:
            content = fh.read()
        if "AGAPE" in content and "/api/agape/equity-curve" in content:
            results.ok("AGAPE in MultiBotEquityCurve LIVE_BOTS")
        else:
            results.fail("AGAPE in MultiBotEquityCurve", "Not in LIVE_BOTS array")

    # Test Oracle integration uses correct method
    signals_path = os.path.join(base, "trading/agape/signals.py")
    if os.path.exists(signals_path):
        with open(signals_path) as fh:
            content = fh.read()
        if "get_strategy_recommendation" in content:
            results.ok("Oracle uses get_strategy_recommendation (correct)")
        elif "get_recommendation" in content:
            results.fail("Oracle method", "Uses get_recommendation (WRONG - should be get_strategy_recommendation)")
        else:
            results.fail("Oracle method", "No Oracle call found")

        if "MarketContext" in content:
            results.ok("Oracle uses MarketContext dataclass (correct)")
        else:
            results.fail("Oracle type", "Missing MarketContext import")

    # Test intraday snapshots are saved
    trader_path = os.path.join(base, "trading/agape/trader.py")
    if os.path.exists(trader_path):
        with open(trader_path) as fh:
            content = fh.read()
        if "save_equity_snapshot" in content:
            results.ok("Intraday equity snapshots are saved in run_cycle()")
        else:
            results.fail("Intraday snapshots", "save_equity_snapshot never called in trader.py")

        if "expire_position" in content:
            results.ok("expire_position() used for MAX_HOLD_TIME")
        else:
            results.fail("expire_position", "Not used for MAX_HOLD_TIME exits")

    # Test spot price guard
    cdp_path = os.path.join(base, "data/crypto_data_provider.py")
    if os.path.exists(cdp_path):
        with open(cdp_path) as fh:
            content = fh.read()
        if "spot <= 0" in content or "spot_price <= 0" in content:
            results.ok("Spot price 0 guard in crypto_data_provider")
        else:
            results.fail("Spot price guard", "No check for spot_price=0 in get_snapshot()")


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="AGAPE Implementation Verification Tests")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--skip-api", action="store_true", help="Skip API tests (code structure only)")
    args = parser.parse_args()

    results = TestResult()

    print("=" * 60)
    print("AGAPE IMPLEMENTATION VERIFICATION TEST SUITE")
    print("=" * 60)
    print(f"API URL: {args.api_url}")

    # Always run code structure tests
    test_code_structure(results)

    if not args.skip_api:
        # API tests
        test_api_endpoints(args.api_url, results)
        test_equity_curve_contract(args.api_url, results)
        test_status_contract(args.api_url, results)
        test_performance_contract(args.api_url, results)
        test_gex_mapping_contract(args.api_url, results)
        test_backend_wiring(args.api_url, results)

    # Summary
    print("\n" + "=" * 60)
    print(f"TOTAL: {results.passed}/{results.total()} PASSED — {results.failed} FAILED")
    print("=" * 60)

    if results.errors:
        print("\nFAILURES:")
        for err in results.errors:
            print(f"  {err}")

    status = "ALL PASSED" if results.failed == 0 else f"{results.failed} FAILURES"
    print(f"\nSTATUS: {'[PASS]' if results.failed == 0 else '[FAIL]'} {status}")
    print("=" * 60)

    sys.exit(0 if results.failed == 0 else 1)


if __name__ == "__main__":
    main()
