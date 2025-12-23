#!/usr/bin/env python3
"""
Test script for new ARGUS features:
- Strike Trends (30-minute trend tracking)
- Gamma Flips (30-minute flip history)
- API endpoint verification

Run: python scripts/test_argus_new_features.py
"""

import requests
import sys
from datetime import datetime

BASE_URL = "http://localhost:8000"

def test_strike_trends():
    """Test /api/argus/strike-trends endpoint"""
    print("\n" + "="*60)
    print("TEST: Strike Trends Endpoint")
    print("="*60)

    try:
        response = requests.get(f"{BASE_URL}/api/argus/strike-trends", timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"FAIL: Expected 200, got {response.status_code}")
            return False

        data = response.json()

        # Check response structure
        if not data.get("success"):
            print(f"FAIL: success=False, message: {data.get('data', {}).get('message')}")
            return False

        trends = data.get("data", {}).get("trends", {})
        window = data.get("data", {}).get("window_minutes")
        generated_at = data.get("data", {}).get("generated_at")

        print(f"Window: {window} minutes")
        print(f"Generated at: {generated_at}")
        print(f"Strikes with trends: {len(trends)}")

        if trends:
            # Show sample trend
            sample_strike = list(trends.keys())[0]
            sample = trends[sample_strike]
            print(f"\nSample trend for strike ${sample_strike}:")
            print(f"  Dominant status: {sample.get('dominant_status')}")
            print(f"  Dominant duration: {sample.get('dominant_duration_mins')} mins")
            print(f"  Current status: {sample.get('current_status')}")
            print(f"  Status counts: {sample.get('status_counts')}")
        else:
            print("(No active trends in last 30 mins - this is OK if market is quiet)")

        print("PASS: Strike Trends endpoint works correctly")
        return True

    except requests.exceptions.ConnectionError:
        print("FAIL: Cannot connect to backend. Is it running?")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_gamma_flips():
    """Test /api/argus/gamma-flips endpoint"""
    print("\n" + "="*60)
    print("TEST: Gamma Flips Endpoint")
    print("="*60)

    try:
        response = requests.get(f"{BASE_URL}/api/argus/gamma-flips", timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"FAIL: Expected 200, got {response.status_code}")
            return False

        data = response.json()

        if not data.get("success"):
            print(f"FAIL: success=False, message: {data.get('data', {}).get('message')}")
            return False

        flips = data.get("data", {}).get("flips", [])
        count = data.get("data", {}).get("count", 0)
        window = data.get("data", {}).get("window_minutes")

        print(f"Window: {window} minutes")
        print(f"Flips found: {count}")

        if flips:
            print("\nRecent flips:")
            for flip in flips[:5]:  # Show first 5
                print(f"  ${flip['strike']}: {flip['direction']} ({flip['mins_ago']} mins ago)")
                print(f"    Gamma: {flip['gamma_before']} -> {flip['gamma_after']}")
        else:
            print("(No gamma flips in last 30 mins - this is OK)")

        print("PASS: Gamma Flips endpoint works correctly")
        return True

    except requests.exceptions.ConnectionError:
        print("FAIL: Cannot connect to backend. Is it running?")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_main_gamma_endpoint():
    """Test main /api/argus/gamma endpoint still works"""
    print("\n" + "="*60)
    print("TEST: Main Gamma Endpoint")
    print("="*60)

    try:
        response = requests.get(f"{BASE_URL}/api/argus/gamma", timeout=30)
        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"FAIL: Expected 200, got {response.status_code}")
            return False

        data = response.json()

        if not data.get("success"):
            print(f"FAIL: success=False")
            return False

        gamma_data = data.get("data", {})

        print(f"Symbol: {gamma_data.get('symbol')}")
        print(f"Spot: ${gamma_data.get('spot_price')}")
        print(f"VIX: {gamma_data.get('vix')}")
        print(f"Regime: {gamma_data.get('gamma_regime')}")
        print(f"Is Mock: {gamma_data.get('is_mock')}")
        print(f"Strikes: {len(gamma_data.get('strikes', []))}")
        print(f"Danger Zones: {len(gamma_data.get('danger_zones', []))}")

        # Verify strike structure has required fields
        if gamma_data.get('strikes'):
            strike = gamma_data['strikes'][0]
            required_fields = ['strike', 'net_gamma', 'probability', 'roc_1min', 'roc_5min']
            missing = [f for f in required_fields if f not in strike]
            if missing:
                print(f"FAIL: Strike missing fields: {missing}")
                return False
            print(f"Strike fields OK: {list(strike.keys())}")

        print("PASS: Main Gamma endpoint works correctly")
        return True

    except requests.exceptions.ConnectionError:
        print("FAIL: Cannot connect to backend. Is it running?")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_danger_zone_logs():
    """Test /api/argus/danger-zones/log endpoint"""
    print("\n" + "="*60)
    print("TEST: Danger Zone Logs Endpoint")
    print("="*60)

    try:
        response = requests.get(f"{BASE_URL}/api/argus/danger-zones/log", timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"FAIL: Expected 200, got {response.status_code}")
            return False

        data = response.json()

        if not data.get("success"):
            print(f"FAIL: success=False")
            return False

        logs = data.get("data", {}).get("logs", [])
        print(f"Logs found: {len(logs)}")

        if logs:
            print("\nRecent danger zones:")
            for log in logs[:5]:
                status = "ACTIVE" if log['is_active'] else "resolved"
                print(f"  ${log['strike']} {log['danger_type']} - {status}")
                print(f"    Detected: {log['detected_at']}")
                print(f"    ROC: 1m={log['roc_1min']:.1f}%, 5m={log['roc_5min']:.1f}%")
        else:
            print("(No danger zone logs - this is OK if market hasn't had spikes)")

        print("PASS: Danger Zone Logs endpoint works correctly")
        return True

    except requests.exceptions.ConnectionError:
        print("FAIL: Cannot connect to backend. Is it running?")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def test_expirations():
    """Test /api/argus/expirations endpoint"""
    print("\n" + "="*60)
    print("TEST: Expirations Endpoint")
    print("="*60)

    try:
        response = requests.get(f"{BASE_URL}/api/argus/expirations", timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"FAIL: Expected 200, got {response.status_code}")
            return False

        data = response.json()

        if not data.get("success"):
            print(f"FAIL: success=False")
            return False

        expirations = data.get("data", {}).get("expirations", [])
        today = data.get("data", {}).get("today")

        print(f"Today: {today}")
        print(f"Expirations:")
        for exp in expirations:
            status = "TODAY" if exp['is_today'] else ("past" if exp['is_past'] else "future")
            print(f"  {exp['day']}: {exp['date']} ({status})")

        print("PASS: Expirations endpoint works correctly")
        return True

    except requests.exceptions.ConnectionError:
        print("FAIL: Cannot connect to backend. Is it running?")
        return False
    except Exception as e:
        print(f"FAIL: {e}")
        return False


def main():
    print("="*60)
    print("ARGUS New Features Test Suite")
    print(f"Testing against: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)

    results = {
        "Main Gamma": test_main_gamma_endpoint(),
        "Strike Trends": test_strike_trends(),
        "Gamma Flips": test_gamma_flips(),
        "Danger Zone Logs": test_danger_zone_logs(),
        "Expirations": test_expirations(),
    }

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n*** ALL TESTS PASSED ***")
        return 0
    else:
        print("\n*** SOME TESTS FAILED ***")
        return 1


if __name__ == "__main__":
    sys.exit(main())
