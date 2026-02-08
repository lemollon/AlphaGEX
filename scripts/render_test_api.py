#!/usr/bin/env python3
"""
Render Shell Script: Test API Endpoints

Run in Render shell:
    python scripts/render_test_api.py              # Test internally (import routes)
    python scripts/render_test_api.py --live URL   # Test live API

This tests all new AI endpoints work correctly.
"""

import os
import sys
import argparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

def ok(msg): print(f"[OK] {msg}")
def fail(msg): print(f"[FAIL] {msg}")
def warn(msg): print(f"[WARN] {msg}")
def info(msg): print(f"[INFO] {msg}")

parser = argparse.ArgumentParser()
parser.add_argument("--live", type=str, help="Test live API at URL")
args = parser.parse_args()

print("=" * 60)
print("TESTING API ENDPOINTS")
print("=" * 60)

if args.live:
    # Live API testing
    import requests
    base_url = args.live.rstrip('/')

    endpoints = [
        ("/health", "GET", "Health check"),
        ("/api/ai/counselor/health", "GET", "COUNSELOR health"),
        ("/api/ai/counselor/capabilities", "GET", "COUNSELOR capabilities"),
        ("/api/ai/counselor/learning-memory/stats", "GET", "Learning Memory stats"),
        ("/api/fortress/status", "GET", "FORTRESS status"),
        ("/api/solomon/status", "GET", "SOLOMON status"),
    ]

    print(f"\nTesting: {base_url}")
    errors = []

    for endpoint, method, desc in endpoints:
        try:
            url = f"{base_url}{endpoint}"
            if method == "GET":
                r = requests.get(url, timeout=10)
            else:
                r = requests.post(url, json={}, timeout=10)

            if r.status_code == 200:
                ok(f"{endpoint} ({r.status_code})")
            else:
                warn(f"{endpoint} returned {r.status_code}")
                errors.append(endpoint)
        except Exception as e:
            fail(f"{endpoint}: {e}")
            errors.append(endpoint)

    print("\n" + "=" * 60)
    if errors:
        print(f"FAILED: {len(errors)} endpoints had issues")
    else:
        print("SUCCESS: All endpoints responding")
    sys.exit(len(errors))

else:
    # Internal testing (import routes directly)
    print("\nInternal route testing (no HTTP)...")

    errors = []

    # Test AI routes import and structure
    print("\n-- AI Routes --")
    try:
        from backend.api.routes.ai_routes import router as ai_router

        routes = [r.path for r in ai_router.routes]
        ok(f"AI router loaded: {len(routes)} routes")

        # Check for new endpoints
        new_endpoints = [
            "/counselor/learning-memory/stats",
            "/counselor/extended-thinking",
            "/counselor/analyze-strike",
            "/counselor/evaluate-trade",
            "/counselor/capabilities",
            "/counselor/health",
        ]

        for ep in new_endpoints:
            found = any(ep in r for r in routes)
            if found:
                ok(f"  {ep}")
            else:
                fail(f"  {ep} NOT FOUND")
                errors.append(ep)

    except Exception as e:
        fail(f"AI routes error: {e}")
        errors.append("ai_routes")

    # Test FORTRESS routes
    print("\n-- FORTRESS Routes --")
    try:
        from backend.api.routes.fortress_routes import router as ares_router
        routes = [r.path for r in ares_router.routes]
        ok(f"FORTRESS router loaded: {len(routes)} routes")

        # Check Tradier endpoint exists
        if any("tradier" in r for r in routes):
            ok("  Tradier connection endpoint exists")
        else:
            warn("  No Tradier endpoint found")

    except Exception as e:
        fail(f"FORTRESS routes error: {e}")
        errors.append("fortress_routes")

    # Test SOLOMON routes
    print("\n-- SOLOMON Routes --")
    try:
        from backend.api.routes.solomon_routes import router as solomon_router
        routes = [r.path for r in solomon_router.routes]
        ok(f"SOLOMON router loaded: {len(routes)} routes")
    except Exception as e:
        fail(f"SOLOMON routes error: {e}")
        errors.append("solomon_routes")

    # Test main app loads
    print("\n-- Main App --")
    try:
        from backend.main import app
        ok("FastAPI app loads successfully")

        # Count all routes
        route_count = len(app.routes)
        info(f"Total routes in app: {route_count}")
    except Exception as e:
        fail(f"Main app error: {e}")
        errors.append("main_app")

    print("\n" + "=" * 60)
    if errors:
        print(f"FAILED: {len(errors)} issues found")
        sys.exit(1)
    else:
        print("SUCCESS: All API routes valid")
        sys.exit(0)
