#!/usr/bin/env python3
"""
Probe which CoinGlass v4 endpoints + intervals the current API key unlocks.

Funding (v2) is already known to work for all 5 perp tickers; this script
focuses on the v4 paid surface so we can choose endpoints + intervals that
fit the user's plan tier.

Run on Render:
    python scripts/probe_coinglass_plan.py 2>&1 | tee /tmp/coinglass_probe.txt
"""

import os
import sys
import requests
from datetime import datetime

API_KEY = os.getenv("COINGLASS_API_KEY", "")
if not API_KEY:
    print("ERROR: COINGLASS_API_KEY not set")
    sys.exit(1)

H = {"CG-API-KEY": API_KEY}
V4 = "https://open-api-v4.coinglass.com/api"
SYMBOLS = ["BTC", "ETH", "XRP", "DOGE", "SHIB"]
INTERVALS = ["h1", "h4", "h8", "h12", "d1"]

print("=" * 72)
print(f"COINGLASS v4 PLAN PROBE — {datetime.now().isoformat()}")
print(f"Key: {API_KEY[:6]}...{API_KEY[-4:]}")
print("=" * 72)


def call(path, params, label):
    """Single GET; return (status, code, msg, payload_size)."""
    try:
        r = requests.get(f"{V4}/{path}", headers=H, params=params, timeout=15)
        if r.status_code != 200:
            return ("HTTP", r.status_code, r.text[:80], 0)
        j = r.json()
        code = j.get("code")
        msg = j.get("msg", "")
        data = j.get("data")
        size = len(data) if isinstance(data, list) else (1 if data else 0)
        if code in ("0", 0) and size:
            return ("OK", code, msg, size)
        return ("FAIL", code, msg[:80], size)
    except Exception as e:
        return ("EXC", "-", str(e)[:80], 0)


# ─────────────────────────────────────────────────────────────────────
# 1. L/S ratio: try every interval to find finest the plan allows
# ─────────────────────────────────────────────────────────────────────
print("\n[1] Long/Short Account Ratio — try intervals h1→d1 (BTC only)")
print("-" * 72)
ls_path = "futures/global-long-short-account-ratio/history"
allowed_interval = None
for iv in INTERVALS:
    s, c, m, n = call(ls_path, {"symbol": "BTC", "interval": iv, "limit": 1}, iv)
    flag = "✅" if s == "OK" else "❌"
    print(f"  interval={iv:4s}  {flag} status={s} code={c} size={n}  {m}")
    if s == "OK" and allowed_interval is None:
        allowed_interval = iv

if allowed_interval:
    print(f"\n  → Finest allowed interval: {allowed_interval}")
    print(f"  Now testing all symbols at {allowed_interval}:")
    for sym in SYMBOLS:
        s, c, m, n = call(ls_path, {"symbol": sym, "interval": allowed_interval, "limit": 1}, sym)
        flag = "✅" if s == "OK" else "❌"
        print(f"    {sym:5s}  {flag}  size={n}  {m}")
else:
    print("\n  → No interval allowed at all.")


# ─────────────────────────────────────────────────────────────────────
# 2. Open Interest (gamma walls proxy)
# ─────────────────────────────────────────────────────────────────────
print("\n[2] Open Interest — exchange-list (point-in-time)")
print("-" * 72)
for sym in SYMBOLS:
    s, c, m, n = call("futures/open-interest/exchange-list", {"symbol": sym}, sym)
    flag = "✅" if s == "OK" else "❌"
    print(f"  {sym:5s}  {flag}  size={n}  {m}")


# ─────────────────────────────────────────────────────────────────────
# 3. Taker buy/sell volume (alternate directional bias)
# ─────────────────────────────────────────────────────────────────────
print("\n[3] Taker Buy/Sell Volume — exchange-list")
print("-" * 72)
for sym in SYMBOLS:
    s, c, m, n = call("futures/taker-buy-sell-volume/exchange-list", {"symbol": sym}, sym)
    flag = "✅" if s == "OK" else "❌"
    print(f"  {sym:5s}  {flag}  size={n}  {m}")


# ─────────────────────────────────────────────────────────────────────
# 4. Liquidation alternatives (heatmap is paywalled — try others)
# ─────────────────────────────────────────────────────────────────────
print("\n[4] Liquidation alternatives")
print("-" * 72)
liq_paths = [
    ("futures/liquidation/aggregated-heatmap/model1", {"symbol": "BTC", "range": "1d"}),
    ("futures/liquidation/heatmap/model1", {"symbol": "BTC", "range": "1d"}),
    ("futures/liquidation/aggregated-history", {"symbol": "BTC", "interval": "h1", "limit": 1}),
    ("futures/liquidation/aggregated-history", {"symbol": "BTC", "interval": "d1", "limit": 1}),
    ("futures/liquidation/order", {"symbol": "BTC", "exchange_name": "Binance"}),
    ("futures/liquidation/coin-list", {}),
]
for path, params in liq_paths:
    label = f"{path}?{','.join(f'{k}={v}' for k,v in params.items())}"
    s, c, m, n = call(path, params, label)
    flag = "✅" if s == "OK" else "❌"
    print(f"  {flag} {label[:60]}  status={s} code={c} size={n}  {m}")


# ─────────────────────────────────────────────────────────────────────
# 5. Funding alternatives (we already have v2; check v4 alternatives)
# ─────────────────────────────────────────────────────────────────────
print("\n[5] Funding rate v4 alternatives (we have v2 working)")
print("-" * 72)
for sym in ["BTC", "XRP"]:
    for path in [
        "futures/funding-rate/exchange-list",
        "futures/funding-rate/oi-weight-history",
    ]:
        params = {"symbol": sym}
        if "history" in path:
            params["interval"] = allowed_interval or "d1"
            params["limit"] = 1
        s, c, m, n = call(path, params, f"{sym} {path}")
        flag = "✅" if s == "OK" else "❌"
        print(f"  {sym:5s}  {flag} {path}  size={n}  {m}")


print("\n" + "=" * 72)
print("DECISION GUIDE")
print("=" * 72)
print(f"  L/S ratio allowed interval: {allowed_interval or 'NONE'}")
print( "  → Update CoinGlassClient.get_long_short_ratio() to use this interval.")
print( "  → If liquidation heatmap is paywalled, drop liquidation_clusters")
print( "    and lean on funding + L/S ratio (squeeze_risk stays LOW by default).")
