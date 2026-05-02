#!/usr/bin/env python3
"""
Verify CoinGlass v2 + v4 endpoints return real data for XRP, DOGE, SHIB,
ETH, and BTC. Run on Render where COINGLASS_API_KEY is set:

    python scripts/verify_coinglass_xrp.py 2>&1 | tee /tmp/coinglass_verify.txt

Tests:
  v2 /funding                                       (public, all symbols)
  v4 /futures/global-long-short-account-ratio/history (paid, CG-API-KEY)
  v4 /futures/liquidation/aggregated-heatmap/model1   (paid, CG-API-KEY)
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

V2_HEADERS = {"coinglassSecret": API_KEY}
V4_HEADERS = {"CG-API-KEY": API_KEY}
V2_BASE = "https://open-api.coinglass.com/public/v2"
V4_BASE = "https://open-api-v4.coinglass.com/api"
SYMBOLS = ["XRP", "DOGE", "SHIB", "ETH", "BTC"]

print("=" * 70)
print(f"COINGLASS API VERIFICATION — {datetime.now().isoformat()}")
print(f"API Key: {API_KEY[:6]}...{API_KEY[-4:]}")
print("=" * 70)


# ─────────────────────────────────────────────────────────────────────
# TEST 1: v2 funding (public, no paid plan required)
# ─────────────────────────────────────────────────────────────────────
print("\n[TEST 1] v2 Funding Rate — GET /public/v2/funding")
print("-" * 70)

funding_found = []
try:
    resp = requests.get(
        f"{V2_BASE}/funding",
        headers=V2_HEADERS,
        params={"time_type": "all"},
        timeout=15,
    )
    print(f"HTTP {resp.status_code}")
    if resp.status_code != 200:
        print(f"ERROR: {resp.text[:300]}")
    else:
        payload = resp.json()
        data = payload.get("data", [])
        by_symbol = {e.get("symbol", "").upper(): e for e in data if e.get("symbol")}
        for symbol in SYMBOLS:
            entry = by_symbol.get(symbol)
            if not entry:
                print(f"  {symbol:5s}  ❌ not in response")
                continue
            rates = [
                float(ex["rate"])
                for ex in entry.get("uMarginList", [])
                if ex.get("rate") is not None
            ]
            if not rates:
                print(f"  {symbol:5s}  ❌ found but no exchange rates")
                continue
            avg = sum(rates) / len(rates)
            funding_found.append(symbol)
            print(f"  {symbol:5s}  ✅ avg rate {avg:+.6f}  ({len(rates)} exchanges)")
except Exception as e:
    print(f"FATAL: {e}")


# ─────────────────────────────────────────────────────────────────────
# TEST 2: v4 Long/Short Account Ratio (paid plan)
# ─────────────────────────────────────────────────────────────────────
print(f"\n[TEST 2] v4 Long/Short Ratio — GET /api/futures/global-long-short-account-ratio/history")
print("-" * 70)

ls_found = []
for symbol in SYMBOLS:
    try:
        resp = requests.get(
            f"{V4_BASE}/futures/global-long-short-account-ratio/history",
            headers=V4_HEADERS,
            params={"symbol": symbol, "interval": "h1", "limit": 1},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  {symbol:5s}  ❌ HTTP {resp.status_code}: {resp.text[:120]}")
            continue
        payload = resp.json()
        if payload.get("code") not in ("0", 0, None):
            print(f"  {symbol:5s}  ❌ API error: {payload.get('msg', 'unknown')}")
            continue
        data = payload.get("data")
        if not data:
            print(f"  {symbol:5s}  ⚠️  no data returned")
            continue
        latest = data[-1] if isinstance(data, list) else data
        long_pct = latest.get("longAccount") or latest.get("longRate")
        short_pct = latest.get("shortAccount") or latest.get("shortRate")
        ratio = latest.get("longShortRatio") or latest.get("ratio")
        print(f"  {symbol:5s}  ✅ long={long_pct} short={short_pct} ratio={ratio}")
        ls_found.append(symbol)
        if symbol == "BTC":
            print(f"         raw shape: {json.dumps(latest)[:200]}")
    except Exception as e:
        print(f"  {symbol:5s}  ❌ exception: {e}")


# ─────────────────────────────────────────────────────────────────────
# TEST 3: v4 Liquidation Aggregated Heatmap (paid plan)
# ─────────────────────────────────────────────────────────────────────
print(f"\n[TEST 3] v4 Liquidation Heatmap — GET /api/futures/liquidation/aggregated-heatmap/model1")
print("-" * 70)

liq_found = []
for symbol in SYMBOLS:
    try:
        resp = requests.get(
            f"{V4_BASE}/futures/liquidation/aggregated-heatmap/model1",
            headers=V4_HEADERS,
            params={"symbol": symbol, "range": "1d"},
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  {symbol:5s}  ❌ HTTP {resp.status_code}: {resp.text[:120]}")
            continue
        payload = resp.json()
        if payload.get("code") not in ("0", 0, None):
            print(f"  {symbol:5s}  ❌ API error: {payload.get('msg', 'unknown')}")
            continue
        data = payload.get("data")
        if not data:
            print(f"  {symbol:5s}  ⚠️  no data returned")
            continue
        # v4 heatmap shape: {"y": [prices], "data": [[x,y,usd], ...]}
        if isinstance(data, dict):
            cells = data.get("data", [])
            prices = data.get("y", [])
            total_usd = sum(float(c[2]) for c in cells if len(c) >= 3)
            print(f"  {symbol:5s}  ✅ {len(cells)} cells across {len(prices)} price levels, total ${total_usd:,.0f}")
            liq_found.append(symbol)
            if symbol == "BTC":
                print(f"         sample cell: {cells[0] if cells else 'none'}")
        elif isinstance(data, list):
            print(f"  {symbol:5s}  ✅ {len(data)} levels (legacy flat shape)")
            liq_found.append(symbol)
    except Exception as e:
        print(f"  {symbol:5s}  ❌ exception: {e}")


# ─────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"  Funding rate (v2):      {', '.join(funding_found) if funding_found else 'NONE'}")
print(f"  Long/Short ratio (v4):  {', '.join(ls_found) if ls_found else 'NONE'}")
print(f"  Liquidation heatmap (v4): {', '.join(liq_found) if liq_found else 'NONE'}")
missing_v4 = [s for s in SYMBOLS if s not in ls_found or s not in liq_found]
if missing_v4:
    print(f"\n  ⚠️  Symbols missing v4 data: {', '.join(missing_v4)}")
    print("     Either the paid plan doesn't cover these tickers, or the symbol")
    print("     name needs adjustment (e.g., 1000SHIB instead of SHIB).")
else:
    print("\n  ✅ All 5 perp tickers fully covered by v4. Bots can go live.")
