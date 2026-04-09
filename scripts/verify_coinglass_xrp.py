#!/usr/bin/env python3
"""
Verify CoinGlass API returns real data for XRP, DOGE, and SHIB.

Run on Render (where COINGLASS_API_KEY is set):
    python scripts/verify_coinglass_xrp.py 2>&1 | tee /tmp/coinglass_verify.txt

This script makes direct API calls to all CoinGlass endpoints used by
CryptoDataProvider and reports exactly what data comes back for each coin.
"""

import os
import sys
import json
import requests
from datetime import datetime

API_KEY = os.getenv("COINGLASS_API_KEY", "")
if not API_KEY:
    print("ERROR: COINGLASS_API_KEY not set in environment")
    sys.exit(1)

HEADERS = {"coinglassSecret": API_KEY}
V2_BASE = "https://open-api.coinglass.com/public/v2"
V3_BASE = "https://open-api-v3.coinglass.com/api"
SYMBOLS = ["XRP", "DOGE", "SHIB", "ETH", "BTC"]  # ETH/BTC as control group

results = {}


def test_endpoint(name, url, params, use_v2=True):
    """Test a single API endpoint and return structured result."""
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        status = resp.status_code
        if status == 200:
            data = resp.json()
            success = data.get("success") or data.get("code") == "0"
            return {
                "status": status,
                "success": success,
                "has_data": data.get("data") is not None,
                "data_type": type(data.get("data")).__name__,
                "data_preview": str(data.get("data", ""))[:500],
                "msg": data.get("msg", ""),
            }
        return {"status": status, "success": False, "error": resp.text[:200]}
    except Exception as e:
        return {"status": 0, "success": False, "error": str(e)}


print("=" * 70)
print(f"COINGLASS API VERIFICATION — {datetime.now().isoformat()}")
print(f"API Key: {API_KEY[:6]}...{API_KEY[-4:]}")
print("=" * 70)

for symbol in SYMBOLS:
    print(f"\n{'─' * 70}")
    print(f"  SYMBOL: {symbol}")
    print(f"{'─' * 70}")

    # 1. Funding Rate (v2) — this is the one confirmed working
    r = test_endpoint(
        "Funding Rate (v2)",
        f"{V2_BASE}/funding",
        {"symbol": symbol, "time_type": "all"},
    )
    print(f"\n  [1] Funding Rate (v2): HTTP {r['status']}, success={r.get('success')}")
    if r.get("success") and r.get("has_data"):
        # Parse out exchange-level rates
        try:
            data = json.loads(r["data_preview"]) if isinstance(r["data_preview"], str) else r["data_preview"]
        except json.JSONDecodeError:
            data = None
        if data and isinstance(data, list):
            for entry in data:
                if entry.get("symbol", "").upper() == symbol:
                    exchanges = entry.get("uMarginList", [])
                    rates = [(ex.get("exchangeName"), ex.get("rate")) for ex in exchanges if ex.get("rate") is not None]
                    print(f"    Exchanges with data: {len(rates)}")
                    for name, rate in rates[:8]:
                        print(f"      {name}: {float(rate):.6f}")
                    if len(rates) > 8:
                        print(f"      ... and {len(rates) - 8} more")
                    avg = sum(float(r) for _, r in rates) / len(rates) if rates else 0
                    print(f"    Average rate: {avg:.6f}")
                    print(f"    ✅ FUNDING DATA CONFIRMED FOR {symbol}")
                    break
            else:
                print(f"    ⚠️ Symbol {symbol} not found in response")
        else:
            print(f"    Raw preview: {r['data_preview'][:200]}")
    else:
        print(f"    ❌ No data. Error: {r.get('error', r.get('msg', 'unknown'))}")

    # 2. Long/Short Ratio (v3)
    r = test_endpoint(
        "L/S Ratio (v3)",
        f"{V3_BASE}/futures/global-long-short-account-ratio",
        {"symbol": symbol},
    )
    print(f"\n  [2] L/S Ratio (v3): HTTP {r['status']}, success={r.get('success')}")
    if r.get("success") and r.get("has_data"):
        print(f"    Data: {r['data_preview'][:300]}")
        print(f"    ✅ L/S RATIO DATA CONFIRMED FOR {symbol}")
    else:
        print(f"    ❌ No data. Error: {r.get('error', r.get('msg', 'unknown'))}")

    # 3. Liquidation Heatmap (v3)
    r = test_endpoint(
        "Liquidation Heatmap (v3)",
        f"{V3_BASE}/futures/liquidation-heatmap",
        {"symbol": symbol},
    )
    print(f"\n  [3] Liquidation Heatmap (v3): HTTP {r['status']}, success={r.get('success')}")
    if r.get("success") and r.get("has_data"):
        print(f"    Data type: {r['data_type']}")
        print(f"    ✅ LIQUIDATION DATA CONFIRMED FOR {symbol}")
    else:
        print(f"    ❌ No data. Error: {r.get('error', r.get('msg', 'unknown'))}")

    # 4. Open Interest (v2)
    r = test_endpoint(
        "Open Interest (v2)",
        f"{V2_BASE}/futures/open-interest",
        {"symbol": symbol},
    )
    print(f"\n  [4] Open Interest (v2): HTTP {r['status']}, success={r.get('success')}")
    if r.get("success") and r.get("has_data"):
        print(f"    ✅ OPEN INTEREST DATA CONFIRMED FOR {symbol}")
    else:
        print(f"    ❌ No data. Error: {r.get('error', r.get('msg', 'unknown'))}")

print(f"\n{'=' * 70}")
print("VERIFICATION COMPLETE")
print("=" * 70)
print("\nRun this on Render to get real results:")
print("  python scripts/verify_coinglass_xrp.py 2>&1 | tee /tmp/coinglass_verify.txt")
