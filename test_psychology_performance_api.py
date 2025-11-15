"""
Test Psychology Performance API Endpoints

Verifies that all 5 endpoints the performance page calls are working
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_endpoint(endpoint: str, params: dict = None):
    """Test a single endpoint"""
    url = f"{BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=5)

        if response.status_code == 200:
            data = response.json()
            print(f"✅ {endpoint}")
            print(f"   Status: {response.status_code}")
            print(f"   Keys: {list(data.keys())}")
            return True
        else:
            print(f"❌ {endpoint}")
            print(f"   Status: {response.status_code}")
            print(f"   Error: {response.text[:200]}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"⚠️  {endpoint}")
        print(f"   Backend not running (expected if testing without server)")
        return None
    except Exception as e:
        print(f"❌ {endpoint}")
        print(f"   Error: {e}")
        return False


def test_all_endpoints():
    """Test all 5 performance page endpoints"""

    print("="*80)
    print("TESTING PSYCHOLOGY PERFORMANCE API ENDPOINTS")
    print("="*80)
    print()

    endpoints = [
        ("/api/psychology/performance/overview", {"days": 30}),
        ("/api/psychology/performance/by-pattern", {"days": 90}),
        ("/api/psychology/performance/signals", {"limit": 50}),
        ("/api/psychology/performance/chart-data", {"days": 30}),
        ("/api/psychology/performance/vix-correlation", {"days": 90})
    ]

    results = []
    for endpoint, params in endpoints:
        result = test_endpoint(endpoint, params)
        results.append(result)
        print()

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    if all(r is None for r in results):
        print("⚠️  Backend server not running")
        print("   To test: Start backend with 'python backend/main.py'")
    elif all(r for r in results if r is not None):
        print("✅ All endpoints working!")
        print("   Performance page will load successfully")
    else:
        print("❌ Some endpoints failed")
        print(f"   Passed: {sum(1 for r in results if r)}/{len(results)}")

    print()


if __name__ == "__main__":
    test_all_endpoints()
