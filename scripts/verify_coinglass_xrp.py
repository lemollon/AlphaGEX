#!/usr/bin/env python3
"""
Verify CoinGlass API returns real data for XRP, DOGE, and SHIB.

Run on Render (where COINGLASS_API_KEY is set):
    python scripts/verify_coinglass_xrp.py 2>&1 | tee /tmp/coinglass_verify.txt
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
SYMBOLS = ["XRP", "DOGE", "SHIB", "ETH", "BTC"]

print("=" * 70)
print(f"COINGLASS API VERIFICATION — {datetime.now().isoformat()}")
print(f"API Key: {API_KEY[:6]}...{API_KEY[-4:]}")
print("=" * 70)

# ── TEST 1: Funding Rates (v2 — the only working CoinGlass endpoint) ──
# The v2 /funding endpoint returns ALL symbols in a single response.
# We make ONE call and parse out each symbol.

print("\n[TEST 1] Funding Rate — GET /public/v2/funding")
print("-" * 70)

try:
    resp = requests.get(
        f"{V2_BASE}/funding",
        headers=HEADERS,
        params={"time_type": "all"},
        timeout=15,
    )
    print(f"HTTP Status: {resp.status_code}")

    if resp.status_code != 200:
        print(f"ERROR: {resp.text[:300]}")
        sys.exit(1)

    payload = resp.json()
    print(f"API success: {payload.get('success')}")

    data = payload.get("data", [])
    if not isinstance(data, list):
        print(f"ERROR: Expected list, got {type(data).__name__}")
        sys.exit(1)

    print(f"Total symbols in response: {len(data)}")

    # Build lookup by symbol
    by_symbol = {}
    for entry in data:
        sym = entry.get("symbol", "").upper()
        if sym:
            by_symbol[sym] = entry

    # Show available symbols (first 30)
    all_syms = sorted(by_symbol.keys())
    print(f"Available symbols ({len(all_syms)}): {', '.join(all_syms[:30])}{'...' if len(all_syms) > 30 else ''}")

    # Check each target symbol
    for symbol in SYMBOLS:
        print(f"\n  ── {symbol} ──")
        entry = by_symbol.get(symbol)
        if not entry:
            print(f"  ❌ {symbol} NOT FOUND in CoinGlass response")
            continue

        exchanges = entry.get("uMarginList", [])
        rates = []
        for ex in exchanges:
            rate = ex.get("rate")
            name = ex.get("exchangeName", "unknown")
            if rate is not None:
                rates.append((name, float(rate)))

        if not rates:
            print(f"  ❌ {symbol} found but no exchange rates returned")
            continue

        print(f"  ✅ {symbol} CONFIRMED — {len(rates)} exchanges reporting")
        for name, rate in sorted(rates, key=lambda x: x[0]):
            annualized = rate * 3 * 365
            print(f"     {name:20s}  rate={rate:+.6f}  (annualized: {annualized:+.1f}%)")
        avg = sum(r for _, r in rates) / len(rates)
        print(f"     {'AVERAGE':20s}  rate={avg:+.6f}  (annualized: {avg * 3 * 365:+.1f}%)")

except Exception as e:
    print(f"FATAL: {e}")
    import traceback
    traceback.print_exc()

# ── TEST 2: v3 endpoint status check ──
print(f"\n{'=' * 70}")
print("[TEST 2] v3 Endpoints Status (known broken since Feb 2026)")
print("-" * 70)

v3_endpoints = [
    ("L/S Ratio", "https://open-api-v3.coinglass.com/api/futures/global-long-short-account-ratio", {"symbol": "BTC"}),
    ("Liquidation", "https://open-api-v3.coinglass.com/api/futures/liquidation-heatmap", {"symbol": "BTC"}),
]

for name, url, params in v3_endpoints:
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        print(f"  {name:20s}  HTTP {resp.status_code}  {'✅ WORKING' if resp.status_code == 200 else '❌ BROKEN'}")
    except Exception as e:
        print(f"  {name:20s}  ❌ ERROR: {e}")

print(f"\n{'=' * 70}")
print("SUMMARY")
print("=" * 70)
found = [s for s in SYMBOLS if s in by_symbol and any(ex.get("rate") is not None for ex in by_symbol[s].get("uMarginList", []))]
missing = [s for s in SYMBOLS if s not in found]
print(f"Funding rates available: {', '.join(found) if found else 'NONE'}")
if missing:
    print(f"Funding rates missing:   {', '.join(missing)}")
print(f"\nThis data flows into CryptoDataProvider → _derive_signals() →")
print(f"snapshot.funding_regime → perp bot signal scoring")
