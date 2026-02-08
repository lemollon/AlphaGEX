#!/usr/bin/env python3
"""
AlphaGEX Deployment Verification Script
========================================
Post-deployment health check for LIVE production systems.

Run: python tests/verify_deployment.py \
       --frontend-url https://alphagex.vercel.app \
       --backend-url https://your-app.onrender.com
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Tuple

try:
    import requests
except ImportError:
    print("ERROR: requests library required. Install with: pip install requests")
    sys.exit(1)

RESULTS = {"passed": 0, "failed": 0, "warnings": 0, "issues": []}

def log_result(test_name: str, passed: bool, warning: bool = False, message: str = ""):
    """Log test result."""
    if passed:
        RESULTS["passed"] += 1
        status = "PASS"
    elif warning:
        RESULTS["warnings"] += 1
        status = "WARN"
    else:
        RESULTS["failed"] += 1
        status = "FAIL"
        RESULTS["issues"].append({"test": test_name, "message": message})

    print(f"  [{status}] {test_name}" + (f" - {message}" if message and not passed else ""))


def check_frontend(frontend_url: str):
    """Check frontend pages are accessible."""
    print("\n=== FRONTEND (Vercel) ===")

    pages = [
        "/",
        "/dashboard",
        "/valor",
        "/jubilee",
        "/fortress",
        "/solomon",
        "/samson",
        "/anchor",
        "/gideon",
    ]

    for page in pages:
        try:
            resp = requests.get(f"{frontend_url}{page}", timeout=30, allow_redirects=True)
            passed = resp.status_code == 200
            log_result(f"GET {page}", passed, message=f"Status: {resp.status_code}")
        except requests.exceptions.RequestException as e:
            log_result(f"GET {page}", False, message=str(e))


def check_backend_health(backend_url: str):
    """Check backend health endpoints."""
    print("\n=== BACKEND (Render) ===")

    endpoints = [
        ("/health", "status"),
        ("/api/time", "time"),
        ("/api/system-health", "status"),
    ]

    for endpoint, expected_field in endpoints:
        try:
            resp = requests.get(f"{backend_url}{endpoint}", timeout=30)
            passed = resp.status_code == 200

            # Check response has expected field
            if passed:
                try:
                    data = resp.json()
                    has_field = expected_field in data or expected_field in str(data)
                    if not has_field:
                        passed = False

                except:
                    passed = False

            log_result(f"GET {endpoint}", passed, message=f"Status: {resp.status_code}")

        except requests.exceptions.RequestException as e:
            log_result(f"GET {endpoint}", False, message=str(e))


def check_bot_status(backend_url: str):
    """Check all trading bots are responding."""
    print("\n=== BOT STATUS ===")

    bots = [
        ("valor", "/api/valor/status"),
        ("jubilee", "/api/jubilee/status"),
        ("fortress", "/api/fortress/status"),
        ("solomon", "/api/solomon/status"),
        ("samson", "/api/samson/status"),
        ("anchor", "/api/anchor/status"),
        ("gideon", "/api/gideon/status"),
    ]

    for bot_name, endpoint in bots:
        try:
            resp = requests.get(f"{backend_url}{endpoint}", timeout=30)
            passed = resp.status_code == 200

            if passed:
                try:
                    data = resp.json()
                    status = data.get("status", "unknown")
                    log_result(f"{bot_name.upper()} status", passed, message=f"Status: {status}")
                except:
                    log_result(f"{bot_name.upper()} status", passed)
            else:
                log_result(f"{bot_name.upper()} status", False, message=f"HTTP {resp.status_code}")

        except requests.exceptions.RequestException as e:
            log_result(f"{bot_name.upper()} status", False, message=str(e))


def check_cors(frontend_url: str, backend_url: str):
    """Check CORS is configured correctly."""
    print("\n=== CROSS-ORIGIN (CORS) ===")

    # Simulate preflight request
    headers = {
        "Origin": frontend_url,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type",
    }

    try:
        resp = requests.options(f"{backend_url}/api/valor/status", headers=headers, timeout=30)

        # Check for CORS headers
        cors_origin = resp.headers.get("Access-Control-Allow-Origin", "")
        cors_methods = resp.headers.get("Access-Control-Allow-Methods", "")

        cors_ok = frontend_url in cors_origin or cors_origin == "*"
        log_result("CORS allows frontend origin", cors_ok,
                  message=f"Allow-Origin: {cors_origin}")

        method_ok = "GET" in cors_methods.upper()
        log_result("CORS allows GET method", method_ok,
                  message=f"Allow-Methods: {cors_methods}")

    except requests.exceptions.RequestException as e:
        log_result("CORS preflight request", False, message=str(e))


def check_data_freshness(backend_url: str):
    """Check that data is fresh (bots are running)."""
    print("\n=== DATA FRESHNESS ===")

    # Check VALOR scan activity
    try:
        resp = requests.get(f"{backend_url}/api/valor/scan-activity?limit=1", timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            scans = data.get("scans", [])
            if scans:
                last_scan = scans[0].get("scan_time", "")
                try:
                    scan_time = datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
                    age_minutes = (datetime.now(scan_time.tzinfo) - scan_time).total_seconds() / 60
                    is_fresh = age_minutes < 30
                    log_result("VALOR last scan < 30 min ago", is_fresh, warning=not is_fresh,
                              message=f"Last scan: {int(age_minutes)} min ago")
                except:
                    log_result("VALOR scan timestamp parsing", False, warning=True,
                              message="Could not parse timestamp")
            else:
                log_result("VALOR has scan data", False, warning=True,
                          message="No scans found")
        else:
            log_result("VALOR scan activity endpoint", False, message=f"HTTP {resp.status_code}")

    except requests.exceptions.RequestException as e:
        log_result("VALOR scan activity check", False, message=str(e))


def check_ml_status(backend_url: str):
    """Check ML models are loaded."""
    print("\n=== ML MODEL STATUS ===")

    ml_endpoints = [
        ("/api/valor/ml/status", "VALOR ML"),
        ("/api/ml/wisdom/status", "WISDOM ML"),
        ("/api/ml/gex-models/status", "STARS GEX ML"),
    ]

    for endpoint, name in ml_endpoints:
        try:
            resp = requests.get(f"{backend_url}{endpoint}", timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                trained = data.get("model_trained", data.get("is_trained", False))
                log_result(f"{name} model loaded", trained, warning=not trained,
                          message="Trained" if trained else "Not trained")
            else:
                log_result(f"{name} endpoint", False, message=f"HTTP {resp.status_code}")

        except requests.exceptions.RequestException as e:
            log_result(f"{name} check", False, message=str(e))


def print_summary():
    """Print verification summary."""
    print("\n" + "=" * 60)
    print("DEPLOYMENT VERIFICATION RESULTS")
    print("=" * 60)
    print(f"PASSED:   {RESULTS['passed']}")
    print(f"WARNINGS: {RESULTS['warnings']}")
    print(f"FAILED:   {RESULTS['failed']}")
    print("=" * 60)

    if RESULTS["issues"]:
        print("\nISSUES FOUND:")
        for issue in RESULTS["issues"]:
            print(f"  - {issue['test']}: {issue['message']}")

    if RESULTS["failed"] == 0:
        status = "✅ HEALTHY" if RESULTS["warnings"] == 0 else "⚠️ HEALTHY (with warnings)"
        print(f"\nLIVE SYSTEM STATUS: {status}")
        return 0
    else:
        print(f"\n❌ LIVE SYSTEM STATUS: ISSUES FOUND ({RESULTS['failed']} failures)")
        return 1


def main():
    parser = argparse.ArgumentParser(description="AlphaGEX Deployment Verification")
    parser.add_argument("--frontend-url", default=os.environ.get("FRONTEND_URL", "https://alphagex.vercel.app"),
                        help="Vercel frontend URL")
    parser.add_argument("--backend-url", default=os.environ.get("API_URL", "http://localhost:8000"),
                        help="Render backend URL")
    parser.add_argument("--skip-frontend", action="store_true",
                        help="Skip frontend checks")
    args = parser.parse_args()

    print("AlphaGEX Deployment Verification")
    print(f"Frontend: {args.frontend_url}")
    print(f"Backend: {args.backend_url}")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Run verification checks
    if not args.skip_frontend:
        check_frontend(args.frontend_url)

    check_backend_health(args.backend_url)
    check_bot_status(args.backend_url)
    check_cors(args.frontend_url, args.backend_url)
    check_data_freshness(args.backend_url)
    check_ml_status(args.backend_url)

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
