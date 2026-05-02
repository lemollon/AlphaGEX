#!/usr/bin/env python3
"""
Slow, focused probe of CoinGlass v4 with the user's API key.

Previous probe burned through the rate limit (most calls returned 429).
This version sleeps 2s between every call and probes the two real
unknowns: (a) symbol format for L/S ratio history at h4+, and (b)
which non-rate-limited endpoints actually work.

Run on Render:
    python scripts/probe_coinglass_plan.py 2>&1 | tee /tmp/coinglass_probe.txt
"""

import os
import sys
import time
import requests
from datetime import datetime

API_KEY = os.getenv("COINGLASS_API_KEY", "")
if not API_KEY:
    print("ERROR: COINGLASS_API_KEY not set")
    sys.exit(1)

H = {"CG-API-KEY": API_KEY}
V4 = "https://open-api-v4.coinglass.com/api"
DELAY_SECONDS = 2.5  # well under any conceivable rate limit

print("=" * 72)
print(f"COINGLASS v4 PLAN PROBE (slow) — {datetime.now().isoformat()}")
print(f"Key: {API_KEY[:6]}...{API_KEY[-4:]}  delay={DELAY_SECONDS}s/call")
print("=" * 72)


def call(path, params, label=""):
    """Single GET with delay; returns (status, code, msg, size, data)."""
    time.sleep(DELAY_SECONDS)
    try:
        r = requests.get(f"{V4}/{path}", headers=H, params=params, timeout=15)
        if r.status_code != 200:
            return ("HTTP", r.status_code, r.text[:90], 0, None)
        j = r.json()
        code = j.get("code")
        msg = j.get("msg", "")
        data = j.get("data")
        size = len(data) if isinstance(data, list) else (1 if data else 0)
        if code in ("0", 0) and size:
            return ("OK", code, msg, size, data)
        return ("FAIL", code, msg[:90], size, data)
    except Exception as e:
        return ("EXC", "-", str(e)[:90], 0, None)


# ─────────────────────────────────────────────────────────────────────
# 1. L/S RATIO: discover the correct symbol format
# ─────────────────────────────────────────────────────────────────────
print("\n[1] L/S Ratio — symbol-format probe at interval=h4")
print("-" * 72)
ls_path = "futures/global-long-short-account-ratio/history"
formats = ["BTC", "BTCUSDT", "BTC-USDT", "BTC-USDT-SWAP", "BTC_USDT", "BTCUSD"]
working_format = None
for fmt in formats:
    s, c, m, n, _ = call(ls_path, {"symbol": fmt, "interval": "h4", "limit": 1}, fmt)
    flag = "✅" if s == "OK" else "❌"
    print(f"  {fmt:18s}  {flag}  status={s} code={c} size={n}  {m}")
    if s == "OK" and working_format is None:
        working_format = fmt

if working_format:
    print(f"\n  → Symbol format that works: '{working_format}'")
    # Show an actual data sample
    s, c, m, n, data = call(ls_path, {"symbol": working_format, "interval": "h4", "limit": 1}, "sample")
    if s == "OK" and data:
        print(f"  Sample record: {data[-1] if isinstance(data, list) else data}")


# ─────────────────────────────────────────────────────────────────────
# 2. L/S RATIO: try each perp symbol with the working format pattern
# ─────────────────────────────────────────────────────────────────────
if working_format:
    print(f"\n[2] L/S Ratio across all 5 perps using format pattern of '{working_format}'")
    print("-" * 72)
    # Build per-symbol names by replacing BTC with each ticker
    symbols = ["BTC", "ETH", "XRP", "DOGE", "SHIB"]
    for sym in symbols:
        candidate = working_format.replace("BTC", sym)
        s, c, m, n, _ = call(ls_path, {"symbol": candidate, "interval": "h4", "limit": 1}, candidate)
        flag = "✅" if s == "OK" else "❌"
        print(f"  {candidate:18s}  {flag}  size={n}  {m}")

    # SHIB-specific: many exchanges use 1000SHIB
    print(f"\n  SHIB variants (some exchanges quote as 1000SHIB):")
    for variant in ["1000SHIB", "1000SHIBUSDT", "1000SHIB-USDT-SWAP"]:
        s, c, m, n, _ = call(ls_path, {"symbol": variant, "interval": "h4", "limit": 1}, variant)
        flag = "✅" if s == "OK" else "❌"
        print(f"  {variant:18s}  {flag}  size={n}  {m}")


# ─────────────────────────────────────────────────────────────────────
# 3. Open Interest (point-in-time, no interval needed)
# ─────────────────────────────────────────────────────────────────────
print("\n[3] Open Interest — exchange-list (one symbol at a time, with delay)")
print("-" * 72)
for sym in ["BTC", "ETH", "XRP", "DOGE", "SHIB"]:
    s, c, m, n, data = call("futures/open-interest/exchange-list", {"symbol": sym}, sym)
    flag = "✅" if s == "OK" else "❌"
    extra = ""
    if s == "OK" and isinstance(data, list) and data:
        sample = data[0]
        extra = f"  sample_keys={list(sample.keys())[:6]}"
    print(f"  {sym:5s}  {flag}  size={n}  {m}{extra}")


# ─────────────────────────────────────────────────────────────────────
# 4. Taker Buy/Sell Volume — one symbol only (rate-limit aware)
# ─────────────────────────────────────────────────────────────────────
print("\n[4] Taker Buy/Sell Volume — BTC only")
print("-" * 72)
s, c, m, n, data = call("futures/taker-buy-sell-volume/exchange-list", {"symbol": "BTC"}, "BTC")
flag = "✅" if s == "OK" else "❌"
print(f"  BTC    {flag}  size={n}  {m}")
if s == "OK" and isinstance(data, list) and data:
    print(f"  sample: {data[0]}")


# ─────────────────────────────────────────────────────────────────────
# 5. Liquidation history (cheaper than heatmap, hopefully unlocked)
# ─────────────────────────────────────────────────────────────────────
print("\n[5] Liquidation aggregated-history — BTC at h4")
print("-" * 72)
s, c, m, n, data = call(
    "futures/liquidation/aggregated-history",
    {"symbol": "BTC", "interval": "h4", "limit": 1},
    "BTC",
)
flag = "✅" if s == "OK" else "❌"
print(f"  BTC    {flag}  size={n}  {m}")
if s == "OK" and isinstance(data, list) and data:
    print(f"  sample: {data[0]}")


# ─────────────────────────────────────────────────────────────────────
# 6. Liquidation coin-list (free metadata endpoint)
# ─────────────────────────────────────────────────────────────────────
print("\n[6] Liquidation coin-list (free metadata)")
print("-" * 72)
s, c, m, n, data = call("futures/liquidation/coin-list", {}, "")
flag = "✅" if s == "OK" else "❌"
print(f"         {flag}  size={n}  {m}")
if s == "OK" and isinstance(data, list) and data:
    print(f"  first 5: {[d.get('symbol') for d in data[:5]]}")


print("\n" + "=" * 72)
print("PASTE THIS BACK TO CLAUDE")
print("=" * 72)
