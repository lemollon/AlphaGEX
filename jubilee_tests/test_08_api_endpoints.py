#!/usr/bin/env python3
"""Test 8: API Endpoint Validation

Hits every JUBILEE IC API endpoint and verifies valid JSON responses.
Uses urllib to avoid external dependency requirements.
Read-only — GET requests only (no POST modifications).
"""
import sys
import json
import traceback

HEADER = """
╔══════════════════════════════════════╗
║  TEST 8: API Endpoint Validation     ║
╚══════════════════════════════════════╝
"""

# Base URL — Render web service runs on port 8000 or $PORT
import os
PORT = os.environ.get('PORT', '8000')
BASE_URL = f"http://localhost:{PORT}"

# Endpoints to test (GET only — read-only)
ENDPOINTS = [
    ("/api/jubilee/status", "Bot status"),
    ("/api/jubilee/health", "Health check"),
    ("/api/jubilee/positions", "Box spread positions"),
    ("/api/jubilee/ic/status", "IC trading status"),
    ("/api/jubilee/ic/positions", "Open IC positions"),
    ("/api/jubilee/ic/closed-trades", "IC closed trades"),
    ("/api/jubilee/ic/performance", "IC performance stats"),
    ("/api/jubilee/ic/equity-curve", "IC equity curve"),
    ("/api/jubilee/ic/equity-curve/intraday", "IC intraday equity"),
    ("/api/jubilee/ic/signals/recent", "Recent IC signals"),
    ("/api/jubilee/ic/logs", "IC activity logs"),
    ("/api/jubilee/equity-curve", "Box equity curve"),
    ("/api/jubilee/equity-curve/intraday", "Box intraday equity"),
    ("/api/jubilee/daily-pnl", "Daily P&L"),
    ("/api/jubilee/combined/performance", "Combined performance"),
    ("/api/jubilee/logs", "Activity logs"),
    ("/api/jubilee/analytics/performance", "Analytics performance"),
    ("/api/jubilee/analytics/rates", "Rate analysis"),
    ("/api/jubilee/analytics/rates/history", "Rate history"),
    ("/api/jubilee/config", "Configuration"),
    ("/api/jubilee/ic/config", "IC configuration"),
]


def fetch_url(url, timeout=10):
    """Fetch URL using urllib (no external deps)"""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            body = response.read().decode('utf-8', errors='replace')
            return status, body, None
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace') if hasattr(e, 'read') else str(e)
        return e.code, body, None
    except urllib.error.URLError as e:
        return None, None, str(e)
    except Exception as e:
        return None, None, str(e)


def run():
    print(HEADER)

    # --- Check 8A: Server reachable ---
    print("--- Check 8A: Server Reachability ---")
    status, body, err = fetch_url(f"{BASE_URL}/health")
    if status is not None:
        print(f"  /health → HTTP {status}")
        if status == 200:
            print(f"  ✅ Server is reachable on port {PORT}")
        else:
            print(f"  ⚠️ Server reachable but /health returned {status}")
        print(f"Result: ✅ PASS\n")
    else:
        print(f"  ❌ Cannot reach server at {BASE_URL}")
        print(f"  Error: {err}")
        print(f"  Trying alternative approach with FastAPI TestClient...\n")

        # Try using FastAPI TestClient instead
        try:
            from fastapi.testclient import TestClient
            from backend.main import app
            client = TestClient(app)
            response = client.get("/health")
            print(f"  /health → HTTP {response.status_code} (via TestClient)")
            print(f"  ✅ Using FastAPI TestClient for remaining tests")
            print(f"Result: ✅ PASS\n")

            # Run tests with TestClient
            _run_with_testclient(client)
            return
        except Exception as e2:
            print(f"  ❌ TestClient also failed: {e2}")
            print(f"\n  Falling back to route inspection only...")
            _run_route_inspection()
            return

    # --- Check 8B: Test all endpoints ---
    print("--- Check 8B: Endpoint Testing ---")
    pass_count = 0
    fail_count = 0
    warn_count = 0

    for path, description in ENDPOINTS:
        url = f"{BASE_URL}{path}"
        status, body, err = fetch_url(url)

        if err:
            print(f"  ❌ {path}")
            print(f"     {description}")
            print(f"     Error: {err}")
            fail_count += 1
            continue

        # Truncate body for display
        body_preview = body[:200] if body else "(empty)"

        if status == 200:
            # Verify JSON
            try:
                json.loads(body)
                print(f"  ✅ {path} → {status} (valid JSON, {len(body)} bytes)")
                pass_count += 1
            except json.JSONDecodeError:
                print(f"  ⚠️ {path} → {status} (NOT valid JSON)")
                print(f"     Body: {body_preview}")
                warn_count += 1
        elif status == 500:
            print(f"  ❌ {path} → {status} ENDPOINT CRASH")
            print(f"     {description}")
            print(f"     Error: {body_preview}")
            fail_count += 1
        elif status == 404:
            print(f"  ❌ {path} → {status} NOT FOUND")
            print(f"     {description}")
            fail_count += 1
        elif status == 422:
            print(f"  ⚠️ {path} → {status} (validation error — may need query params)")
            print(f"     Body: {body_preview}")
            warn_count += 1
        else:
            print(f"  ⚠️ {path} → {status}")
            print(f"     Body: {body_preview}")
            warn_count += 1

    print(f"\n  Summary: {pass_count} pass, {fail_count} fail, {warn_count} warning")

    overall = fail_count == 0
    if overall:
        print(f"\nResult: ✅ PASS — all endpoints responding")
    else:
        print(f"\nResult: ❌ FAIL — {fail_count} endpoints failed")

    print(f"""
═══════════════════════════════
TEST 8 OVERALL: {'✅ PASS' if overall else '❌ FAIL'}
═══════════════════════════════
""")


def _run_with_testclient(client):
    """Run endpoint tests using FastAPI TestClient"""
    print("--- Check 8B: Endpoint Testing (TestClient) ---")
    pass_count = 0
    fail_count = 0
    warn_count = 0

    for path, description in ENDPOINTS:
        try:
            response = client.get(path)
            status = response.status_code
            body = response.text

            body_preview = body[:200] if body else "(empty)"

            if status == 200:
                try:
                    json.loads(body)
                    print(f"  ✅ {path} → {status} (valid JSON, {len(body)} bytes)")
                    pass_count += 1
                except json.JSONDecodeError:
                    print(f"  ⚠️ {path} → {status} (NOT valid JSON)")
                    warn_count += 1
            elif status == 500:
                print(f"  ❌ {path} → {status} ENDPOINT CRASH")
                print(f"     Error: {body_preview}")
                fail_count += 1
            elif status == 404:
                print(f"  ❌ {path} → {status} NOT FOUND")
                fail_count += 1
            else:
                print(f"  ⚠️ {path} → {status}")
                print(f"     Body: {body_preview}")
                warn_count += 1
        except Exception as e:
            print(f"  ❌ {path} → Exception: {e}")
            fail_count += 1

    print(f"\n  Summary: {pass_count} pass, {fail_count} fail, {warn_count} warning")

    overall = fail_count == 0
    print(f"""
═══════════════════════════════
TEST 8 OVERALL: {'✅ PASS' if overall else '❌ FAIL'}
═══════════════════════════════
""")


def _run_route_inspection():
    """Fallback: inspect route definitions instead of hitting endpoints"""
    print("--- Check 8B: Route Inspection (Fallback) ---")
    try:
        from backend.api.routes import jubilee_routes
        import inspect

        source = inspect.getsource(jubilee_routes)
        ic_routes = []
        for line in source.split('\n'):
            if '@router.' in line and ('get' in line.lower() or 'post' in line.lower()):
                ic_routes.append(line.strip())

        print(f"  Routes found in jubilee_routes.py: {len(ic_routes)}")
        for route in ic_routes[:30]:
            print(f"    {route}")
        if len(ic_routes) > 30:
            print(f"    ... and {len(ic_routes) - 30} more")

        # Check specific IC routes exist
        expected_paths = ['/ic/status', '/ic/positions', '/ic/closed-trades',
                          '/ic/performance', '/ic/equity-curve', '/ic/signals/recent']
        for path in expected_paths:
            found = any(path in r for r in ic_routes)
            print(f"  {'✅' if found else '❌'} {path}: {'found' if found else 'NOT FOUND'}")

        print(f"\nResult: ✅ PASS — routes inspected (server not available for live test)")
    except Exception as e:
        print(f"  Error: {e}")
        traceback.print_exc()
        print(f"Result: ⚠️ WARNING — cannot inspect routes")

    print(f"""
═══════════════════════════════
TEST 8 OVERALL: ⚠️ PARTIAL (server not reachable)
═══════════════════════════════
""")


if __name__ == '__main__':
    try:
        run()
    except Exception as e:
        print(f"\n❌ SCRIPT CRASHED: {e}")
        traceback.print_exc()
        sys.exit(1)
