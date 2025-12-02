#!/usr/bin/env python3
"""
TEST 04: API Endpoints
Tests FastAPI routes and data flow.

Run: python scripts/test_04_api_endpoints.py

Note: This test can run in two modes:
1. Direct import mode (tests route handlers directly)
2. HTTP mode (requires running server)
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
import json

print("\n" + "="*60)
print(" TEST 04: API ENDPOINTS")
print("="*60)

# =============================================================================
# 1. Import API Components
# =============================================================================
print("\n--- Importing API Components ---")

api_available = False

try:
    from backend.api.routes import spx_backtest_routes
    print("  spx_backtest_routes imported")
    api_available = True
except ImportError:
    try:
        from api.routes import spx_backtest_routes
        print("  spx_backtest_routes imported (alternate path)")
        api_available = True
    except ImportError as e:
        print(f"  Could not import spx_backtest_routes: {e}")

try:
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    print("  TestClient initialized")
    test_client_available = True
except ImportError:
    try:
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        print("  TestClient initialized (alternate path)")
        test_client_available = True
    except ImportError as e:
        print(f"  TestClient not available: {e}")
        test_client_available = False

# =============================================================================
# 2. Test Health Endpoint
# =============================================================================
print("\n--- Health Endpoint ---")

if test_client_available:
    try:
        response = client.get("/health")
        print(f"  GET /health: {response.status_code}")
        if response.status_code == 200:
            print(f"    Response: {response.json()}")
    except Exception as e:
        print(f"  Error: {e}")
else:
    print("  Skipped (TestClient not available)")

# =============================================================================
# 3. Test Backtest Endpoint
# =============================================================================
print("\n--- Backtest Endpoint ---")

if test_client_available:
    try:
        # Prepare backtest request
        end_date = datetime.now() - timedelta(days=7)
        start_date = end_date - timedelta(days=30)

        payload = {
            "start_date": start_date.strftime('%Y-%m-%d'),
            "end_date": end_date.strftime('%Y-%m-%d'),
            "initial_capital": 100000000,  # $100M for SPX margin
            "put_delta": 0.16,
            "dte_target": 45,
            "use_ml_scoring": True
        }

        print(f"  POST /api/spx-backtest/run")
        print(f"    Payload: {json.dumps(payload)}")

        response = client.post("/api/spx-backtest/run", json=payload)
        print(f"    Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"    Response keys: {list(data.keys())}")

            # Check trades
            trades = data.get('trades', [])
            print(f"    Trades returned: {len(trades)}")

            # Check summary
            summary = data.get('summary', {})
            print(f"    Summary fields: {list(summary.keys())[:5]}...")

            # Check equity curve
            equity = data.get('equity_curve', [])
            print(f"    Equity curve points: {len(equity)}")

            # Verify critical fields
            print("\n  Critical Field Checks:")
            print(f"    [{'OK' if trades else 'XX'}] trades: {'present' if trades else 'MISSING'}")
            print(f"    [{'OK' if 'total_return_pct' in summary else 'XX'}] total_return_pct: {'present' if 'total_return_pct' in summary else 'MISSING'}")
            print(f"    [{'OK' if 'win_rate' in summary else 'XX'}] win_rate: {'present' if 'win_rate' in summary else 'MISSING'}")
            print(f"    [{'OK' if equity else 'XX'}] equity_curve: {'present' if equity else 'MISSING'}")

        elif response.status_code == 422:
            print(f"    Validation error: {response.json()}")
        else:
            print(f"    Error response: {response.text[:200]}")

    except Exception as e:
        print(f"  Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("  Skipped (TestClient not available)")

# =============================================================================
# 4. Test Direct Route Handler
# =============================================================================
print("\n--- Direct Route Handler Test ---")

if api_available:
    try:
        # Test the run_backtest function directly
        import asyncio

        async def test_backtest_handler():
            from pydantic import BaseModel
            from typing import Optional

            class BacktestRequest(BaseModel):
                start_date: str
                end_date: str
                initial_capital: float = 100000
                delta_target: float = 0.16

            end_date = datetime.now() - timedelta(days=7)
            start_date = end_date - timedelta(days=14)

            request = BacktestRequest(
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d'),
                initial_capital=100000
            )

            # Find the route handler
            if hasattr(spx_backtest_routes, 'run_backtest'):
                result = await spx_backtest_routes.run_backtest(request)
                return result
            else:
                return {"error": "run_backtest not found"}

        result = asyncio.run(test_backtest_handler())

        if 'error' not in result:
            print("  Direct handler call successful")
            print(f"    Keys: {list(result.keys())}")
        else:
            print(f"  Handler error: {result.get('error')}")

    except Exception as e:
        print(f"  Error: {e}")
else:
    print("  Skipped (API module not available)")

# =============================================================================
# 5. Test Market Data Endpoint
# =============================================================================
print("\n--- Market Data Endpoint ---")

if test_client_available:
    try:
        response = client.get("/api/market-data/spy")
        print(f"  GET /api/market-data/spy: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"    Price: ${data.get('price', 'N/A')}")
            print(f"    Change: {data.get('change_pct', 'N/A')}%")
        elif response.status_code == 404:
            print("    Endpoint not found (may not be implemented)")
        else:
            print(f"    Response: {response.text[:100]}")

    except Exception as e:
        print(f"  Error: {e}")
else:
    print("  Skipped (TestClient not available)")

# =============================================================================
# 6. Test GEX Data Endpoint
# =============================================================================
print("\n--- GEX Data Endpoint ---")

if test_client_available:
    try:
        response = client.get("/api/gex/spy")
        print(f"  GET /api/gex/spy: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"    Net GEX: {data.get('net_gex', 'N/A')}")
            print(f"    Put Wall: {data.get('put_wall', 'N/A')}")
            print(f"    Call Wall: {data.get('call_wall', 'N/A')}")
        elif response.status_code == 404:
            print("    Endpoint not found (may not be implemented)")
        else:
            print(f"    Response: {response.text[:100]}")

    except Exception as e:
        print(f"  Error: {e}")
else:
    print("  Skipped (TestClient not available)")

# =============================================================================
# 7. Test ML Features Endpoint
# =============================================================================
print("\n--- ML Features Endpoint ---")

if test_client_available:
    try:
        test_date = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

        payload = {
            "trade_date": test_date,
            "strike": 580.0,
            "underlying_price": 600.0,
            "option_iv": 0.16
        }

        response = client.post("/api/ml/features", json=payload)
        print(f"  POST /api/ml/features: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"    VIX: {data.get('vix', 'N/A')}")
            print(f"    IV Rank: {data.get('iv_rank', 'N/A')}")
            print(f"    Net GEX: {data.get('net_gex', 'N/A')}")
        elif response.status_code == 404:
            print("    Endpoint not found (may not be implemented)")
        else:
            print(f"    Response: {response.text[:100]}")

    except Exception as e:
        print(f"  Error: {e}")
else:
    print("  Skipped (TestClient not available)")

# =============================================================================
# 8. Response Structure Validation
# =============================================================================
print("\n--- Response Structure Validation ---")

try:
    # Define expected structure
    expected_backtest_response = {
        'trades': list,
        'summary': dict,
        'equity_curve': list
    }

    expected_summary_fields = [
        'total_return_pct',
        'max_drawdown_pct',
        'win_rate',
        'total_trades',
        'winning_trades',
        'losing_trades'
    ]

    expected_trade_fields = [
        'entry_date',
        'exit_date',
        'strike',
        'premium',
        'outcome',
        'pnl'
    ]

    print("  Expected backtest response structure:")
    for key, type_ in expected_backtest_response.items():
        print(f"    - {key}: {type_.__name__}")

    print("\n  Expected summary fields:")
    for field in expected_summary_fields:
        print(f"    - {field}")

    print("\n  Expected trade fields:")
    for field in expected_trade_fields:
        print(f"    - {field}")

except Exception as e:
    print(f"  Error: {e}")

# =============================================================================
# 9. Test Error Handling
# =============================================================================
print("\n--- Error Handling ---")

if test_client_available:
    try:
        # Test with invalid date range
        payload = {
            "start_date": "2025-01-01",  # Future date
            "end_date": "2025-12-31",
            "initial_capital": 100000000
        }

        response = client.post("/api/spx-backtest/run", json=payload)
        print(f"  Future dates: {response.status_code}")

        # Test with invalid capital
        payload = {
            "start_date": "2024-01-01",
            "end_date": "2024-06-30",
            "initial_capital": -1000  # Invalid
        }

        response = client.post("/api/spx-backtest/run", json=payload)
        print(f"  Negative capital: {response.status_code}")

        # Test with missing fields
        response = client.post("/api/spx-backtest/run", json={})
        print(f"  Missing fields: {response.status_code}")

    except Exception as e:
        print(f"  Error: {e}")
else:
    print("  Skipped (TestClient not available)")

# =============================================================================
# Summary
# =============================================================================
print("\n" + "="*60)
print(" API ENDPOINTS TEST COMPLETE")
print("="*60 + "\n")
