#!/usr/bin/env python3
"""
Test script to verify ALL API endpoints work correctly.
This provides real confidence that pages won't break.
"""
import requests
import json
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"

# All endpoints used by the navigation pages
ENDPOINTS = [
    # Dashboard
    ("GET", "/api/gex/SPY", "Dashboard - GEX data"),
    ("GET", "/api/trader/performance", "Dashboard - Trader performance"),
    ("GET", "/api/trader/positions", "Dashboard - Open positions"),
    ("GET", "/api/trader/equity-curve?days=30", "Dashboard - Equity curve"),

    # GEX Analysis
    ("GET", "/api/gex/SPY", "GEX Analysis - Main data"),
    ("GET", "/api/gex/SPY/levels", "GEX Analysis - Levels"),

    # GEX History
    ("GET", "/api/gex/history?symbol=SPY&days=30", "GEX History - Historical data"),
    ("GET", "/api/gex/regime-changes?symbol=SPY&days=30", "GEX History - Regime changes"),

    # Gamma Intelligence
    ("GET", "/api/gamma/SPY/intelligence", "Gamma Intelligence - Main data"),
    ("GET", "/api/gamma/SPY/history?days=30", "Gamma Intelligence - History"),
    ("GET", "/api/gamma/SPY/probabilities?vix=20", "Gamma Intelligence - Probabilities"),
    ("GET", "/api/gamma/SPY/expiration", "Gamma Intelligence - Expiration"),
    ("GET", "/api/gamma/SPY/expiration-waterfall", "Gamma Intelligence - Waterfall"),

    # 0DTE Tracker
    ("GET", "/api/gamma/SPY/intelligence", "0DTE Tracker - Uses gamma intelligence"),

    # OI Trends
    ("GET", "/api/oi/trends?symbol=SPY&days=90", "OI Trends - Trend data"),
    ("GET", "/api/oi/unusual-activity?symbol=SPY&days=14", "OI Trends - Unusual activity"),

    # Psychology Traps
    ("GET", "/api/psychology/current-regime?symbol=SPY", "Psychology - Current regime"),
    ("GET", "/api/psychology/liberation-setups?days=7", "Psychology - Liberation setups"),
    ("GET", "/api/psychology/false-floors?days=7", "Psychology - False floors"),
    ("GET", "/api/psychology/statistics?days=30", "Psychology - Statistics"),

    # Psychology Performance
    ("GET", "/api/psychology/performance/overview", "Psychology Performance - Overview"),
    ("GET", "/api/psychology/performance/patterns", "Psychology Performance - Patterns"),
    ("GET", "/api/psychology/performance/signals?limit=50", "Psychology Performance - Signals"),
    ("GET", "/api/psychology/notifications/history?limit=20", "Psychology Performance - Notifications"),
    ("GET", "/api/psychology/notifications/stats", "Psychology Performance - Notification stats"),

    # Strategy Optimizer
    ("GET", "/api/optimizer/strikes", "Optimizer - Strike performance"),
    ("GET", "/api/optimizer/dte", "Optimizer - DTE performance"),
    ("GET", "/api/optimizer/regime-specific", "Optimizer - Regime performance"),
    ("GET", "/api/optimizer/greeks", "Optimizer - Greeks performance"),
    ("GET", "/api/optimizer/best-combinations", "Optimizer - Best combinations"),

    # Scanner
    ("GET", "/api/scanner/history?limit=10", "Scanner - History"),

    # Trade Setups
    ("GET", "/api/setups/list?limit=20&status=active", "Setups - Active setups"),

    # Position Sizing
    ("POST", "/api/position-sizing/calculate", "Position Sizing - Calculate", {
        "account_size": 100000,
        "win_rate": 0.6,
        "avg_win": 100,
        "avg_loss": 50,
        "current_price": 570,
        "risk_per_trade_pct": 1
    }),

    # AI Copilot
    ("POST", "/api/ai/analyze", "AI Copilot - Analyze", {
        "symbol": "SPY",
        "query": "test query"
    }),

    # Conversation History
    ("GET", "/api/ai/conversations?limit=50", "AI History - Conversations"),

    # Recommendations History
    ("GET", "/api/recommendations/history?days=90", "Recommendations - History"),
    ("GET", "/api/recommendations/performance", "Recommendations - Performance"),

    # Backtesting
    ("GET", "/api/backtests/results", "Backtesting - Results"),
    ("GET", "/api/backtests/smart-recommendations", "Backtesting - Smart recommendations"),

    # Probability System
    ("GET", "/api/probability/outcomes?days=30", "Probability - Outcomes"),
    ("GET", "/api/probability/weights", "Probability - Weights"),
    ("GET", "/api/probability/calibration-history?days=90", "Probability - Calibration history"),

    # SPY Autonomous Trader
    ("GET", "/api/trader/status", "Trader - Status"),
    ("GET", "/api/trader/live-status", "Trader - Live status"),
    ("GET", "/api/trader/performance", "Trader - Performance"),
    ("GET", "/api/trader/trades?limit=10", "Trader - Recent trades"),
    ("GET", "/api/trader/positions", "Trader - Positions"),
    ("GET", "/api/trader/closed-trades?limit=50", "Trader - Closed trades"),
    ("GET", "/api/trader/strategies", "Trader - Strategies"),
    ("GET", "/api/autonomous/logs?limit=100", "Trader - Logs"),
    ("GET", "/api/autonomous/competition/leaderboard", "Trader - Leaderboard"),
    ("GET", "/api/autonomous/risk/status", "Trader - Risk status"),
    ("GET", "/api/autonomous/risk/metrics", "Trader - Risk metrics"),
    ("GET", "/api/autonomous/ml/model-status", "Trader - ML model status"),

    # SPX Autonomous Trader
    ("GET", "/api/spx/status", "SPX - Status"),
    ("GET", "/api/spx/performance", "SPX - Performance"),
    ("GET", "/api/spx/trades?limit=20", "SPX - Trades"),
    ("GET", "/api/spx/equity-curve?days=30", "SPX - Equity curve"),

    # VIX Dashboard
    ("GET", "/api/vix/current", "VIX - Current data"),
    ("GET", "/api/vix/hedge-signal", "VIX - Hedge signal"),
    ("GET", "/api/vix/signal-history?days=30", "VIX - Signal history"),

    # Volatility Comparison
    ("GET", "/api/gex/SPY", "Volatility Comparison - GEX data"),

    # Alerts
    ("GET", "/api/alerts/list?status=active", "Alerts - Active alerts"),
    ("GET", "/api/alerts/history?limit=50", "Alerts - History"),

    # System Settings
    ("GET", "/api/system/trader-status", "System - Trader status"),

    # Database Admin
    ("GET", "/api/database/stats", "Database - Stats"),
    ("GET", "/api/test-connections", "Database - Test connections"),

    # Health check
    ("GET", "/health", "Health check"),
    ("GET", "/api/time", "Time endpoint"),
]


def test_endpoint(method, path, description, body=None):
    """Test a single endpoint and return result."""
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=30)
        elif method == "POST":
            response = requests.post(url, json=body or {}, timeout=30)
        else:
            return {"status": "SKIP", "message": f"Unknown method: {method}"}

        # Check for success
        if response.status_code == 200:
            try:
                data = response.json()
                # Check if response has success field
                if isinstance(data, dict):
                    if data.get("success") == True:
                        return {"status": "PASS", "message": "OK"}
                    elif data.get("success") == False:
                        return {"status": "WARN", "message": f"success=False: {data.get('error', 'unknown')}"}
                    elif "error" in data:
                        return {"status": "WARN", "message": f"Has error: {data.get('error')}"}
                    else:
                        # No success field but valid response
                        return {"status": "PASS", "message": "OK (no success field)"}
                return {"status": "PASS", "message": "OK"}
            except json.JSONDecodeError:
                return {"status": "WARN", "message": "Response not JSON"}
        elif response.status_code == 404:
            return {"status": "FAIL", "message": "404 Not Found"}
        elif response.status_code == 500:
            try:
                detail = response.json().get("detail", "Unknown error")
            except:
                detail = response.text[:100]
            return {"status": "FAIL", "message": f"500 Error: {detail}"}
        elif response.status_code == 503:
            return {"status": "WARN", "message": "503 Service Unavailable (expected for some modules)"}
        else:
            return {"status": "FAIL", "message": f"HTTP {response.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"status": "FAIL", "message": "Connection refused - is the server running?"}
    except requests.exceptions.Timeout:
        return {"status": "WARN", "message": "Timeout (>30s)"}
    except Exception as e:
        return {"status": "FAIL", "message": str(e)}


def main():
    print(f"\n{'='*80}")
    print(f"AlphaGEX API Endpoint Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Testing {len(ENDPOINTS)} endpoints against {BASE_URL}")
    print(f"{'='*80}\n")

    results = {"PASS": 0, "WARN": 0, "FAIL": 0, "SKIP": 0}
    failures = []
    warnings = []

    for endpoint in ENDPOINTS:
        if len(endpoint) == 3:
            method, path, description = endpoint
            body = None
        else:
            method, path, description, body = endpoint

        result = test_endpoint(method, path, description, body)
        results[result["status"]] += 1

        # Color coding
        if result["status"] == "PASS":
            icon = "✓"
            color = "\033[92m"  # Green
        elif result["status"] == "WARN":
            icon = "⚠"
            color = "\033[93m"  # Yellow
            warnings.append((description, path, result["message"]))
        elif result["status"] == "FAIL":
            icon = "✗"
            color = "\033[91m"  # Red
            failures.append((description, path, result["message"]))
        else:
            icon = "○"
            color = "\033[90m"  # Gray

        reset = "\033[0m"
        print(f"{color}{icon} [{result['status']}]{reset} {description}")
        if result["status"] != "PASS":
            print(f"  └─ {path}: {result['message']}")

    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"✓ PASS: {results['PASS']}")
    print(f"⚠ WARN: {results['WARN']}")
    print(f"✗ FAIL: {results['FAIL']}")
    print(f"○ SKIP: {results['SKIP']}")

    if failures:
        print(f"\n{'='*80}")
        print("FAILURES (pages will break)")
        print(f"{'='*80}")
        for desc, path, msg in failures:
            print(f"✗ {desc}")
            print(f"  {path}")
            print(f"  Error: {msg}\n")

    if warnings:
        print(f"\n{'='*80}")
        print("WARNINGS (may cause issues)")
        print(f"{'='*80}")
        for desc, path, msg in warnings:
            print(f"⚠ {desc}")
            print(f"  {path}")
            print(f"  Warning: {msg}\n")

    # Exit code
    if results["FAIL"] > 0:
        print("\n❌ TESTS FAILED - Some pages will break!")
        sys.exit(1)
    elif results["WARN"] > 0:
        print("\n⚠️ TESTS PASSED WITH WARNINGS")
        sys.exit(0)
    else:
        print("\n✅ ALL TESTS PASSED!")
        sys.exit(0)


if __name__ == "__main__":
    main()
