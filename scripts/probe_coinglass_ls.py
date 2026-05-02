#!/usr/bin/env python3
"""Probe CoinGlass v4 L/S ratio endpoint with explicit exchange param.

Run on Render:
    curl -s https://raw.githubusercontent.com/lemollon/AlphaGEX/main/scripts/probe_coinglass_ls.py -o /tmp/ls.py && python /tmp/ls.py
"""
import os, time, requests

API_KEY = os.environ.get("COINGLASS_API_KEY", "")
if not API_KEY:
    print("COINGLASS_API_KEY not set"); raise SystemExit(1)

H = {"CG-API-KEY": API_KEY}
U = "https://open-api-v4.coinglass.com/api/futures/global-long-short-account-ratio/history"

combos = [
    {"exchange": "Binance", "symbol": "BTCUSDT", "interval": "h4", "limit": 1},
    {"exchange": "Binance", "symbol": "BTC-USDT", "interval": "h4", "limit": 1},
    {"exchange": "OKX", "symbol": "BTC-USDT-SWAP", "interval": "h4", "limit": 1},
    {"exchange": "Bybit", "symbol": "BTCUSDT", "interval": "h4", "limit": 1},
    {"exchange": "Binance", "symbol": "BTCUSDT", "interval": "h1", "limit": 1},
    {"exchange": "Binance", "symbol": "BTCUSDT", "interval": "d1", "limit": 1},
]

print(f"L/S RATIO EXCHANGE+SYMBOL PROBE  key={API_KEY[:6]}...{API_KEY[-4:]}")
print("-" * 80)
working = None
for c in combos:
    time.sleep(2.5)
    try:
        r = requests.get(U, headers=H, params=c, timeout=15).json()
        code = r.get("code")
        msg = (r.get("msg") or "")[:60]
        has_data = bool(r.get("data"))
        flag = "OK  " if code in ("0", 0) and has_data else "FAIL"
        print(f"  {flag} ex={c['exchange']:8s} sym={c['symbol']:18s} iv={c['interval']:3s}  code={code} data={has_data}  {msg}")
        if flag == "OK  " and not working:
            working = c
            print(f"    sample: {r.get('data')[-1] if isinstance(r.get('data'), list) else r.get('data')}")
    except Exception as e:
        print(f"  EXC  {c} -> {e}")

if working:
    print()
    print(f"WORKING combo: exchange={working['exchange']} symbol={working['symbol']} interval={working['interval']}")
    print()
    print("Now testing all 5 perp tickers with that combo pattern:")
    base_sym = working["symbol"]
    for ticker in ["BTC", "ETH", "XRP", "DOGE", "SHIB"]:
        sym = base_sym.replace("BTC", ticker)
        time.sleep(2.5)
        try:
            r = requests.get(U, headers=H, params={
                "exchange": working["exchange"], "symbol": sym,
                "interval": working["interval"], "limit": 1
            }, timeout=15).json()
            code = r.get("code")
            msg = (r.get("msg") or "")[:60]
            has = bool(r.get("data"))
            flag = "OK  " if code in ("0", 0) and has else "FAIL"
            print(f"  {flag} {ticker:5s} sym={sym:18s} code={code} data={has}  {msg}")
        except Exception as e:
            print(f"  EXC  {ticker} -> {e}")
else:
    print()
    print("NO COMBO WORKED. L/S ratio likely fully gated on this plan.")
