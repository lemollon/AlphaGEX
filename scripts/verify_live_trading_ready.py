#!/usr/bin/env python3
"""
Verify ETH-USD and BTC-USD are fully wired for LIVE Coinbase trading.

Run in Render shell:
    python scripts/verify_live_trading_ready.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class R:
    passed = 0
    failed = 0
    errors = []

    @classmethod
    def ok(cls, msg):
        cls.passed += 1
        print(f"  \033[92m[PASS]\033[0m {msg}")

    @classmethod
    def fail(cls, msg, reason=""):
        cls.failed += 1
        full = f"  \033[91m[FAIL]\033[0m {msg}: {reason}" if reason else f"  \033[91m[FAIL]\033[0m {msg}"
        print(full)
        cls.errors.append(full)

    @classmethod
    def warn(cls, msg, reason=""):
        print(f"  \033[93m[WARN]\033[0m {msg}: {reason}")

    @classmethod
    def info(cls, msg):
        print(f"  \033[94m[INFO]\033[0m {msg}")


LIVE_TICKERS = ["ETH-USD", "BTC-USD"]

print("=" * 70)
print("AGAPE-SPOT: ETH + BTC LIVE TRADING READINESS CHECK")
print("=" * 70)


# =========================================================================
# 1. CONFIG: Both tickers in code defaults
# =========================================================================
print("\n--- 1. CONFIG ---")

try:
    from trading.agape_spot.models import AgapeSpotConfig, SPOT_TICKERS

    config = AgapeSpotConfig()

    for tk in LIVE_TICKERS:
        if tk in config.tickers:
            R.ok(f"{tk} in config.tickers")
        else:
            R.fail(f"{tk} in config.tickers", f"Missing! tickers={config.tickers}")

        if tk in config.live_tickers:
            R.ok(f"{tk} in config.live_tickers (LIVE mode)")
        else:
            R.fail(f"{tk} in config.live_tickers", f"Not live! live={config.live_tickers}")

        if config.is_live(tk):
            R.ok(f"config.is_live('{tk}') = True")
        else:
            R.fail(f"config.is_live('{tk}')", "Returns False — would trade PAPER only")

        if tk in SPOT_TICKERS:
            sp = SPOT_TICKERS[tk]
            R.ok(f"{tk} SPOT_TICKERS: capital=${sp['starting_capital']}, qty={sp['default_quantity']}")
        else:
            R.fail(f"{tk} in SPOT_TICKERS", "Missing from ticker registry")

except Exception as e:
    R.fail("Config check", str(e))


# =========================================================================
# 2. DB CONFIG: tickers/live_tickers are code-controlled
# =========================================================================
print("\n--- 2. DB CONFIG OVERRIDE PROTECTION ---")

try:
    config2 = AgapeSpotConfig()
    from unittest.mock import MagicMock
    mock_db = MagicMock()
    # Simulate stale DB with old 4-ticker config
    mock_db.load_config.return_value = {
        "tickers": "ETH-USD,XRP-USD,SHIB-USD,DOGE-USD",
        "live_tickers": "ETH-USD,XRP-USD,SHIB-USD,DOGE-USD",
    }
    loaded = AgapeSpotConfig.load_from_db(mock_db)

    if "BTC-USD" in loaded.tickers:
        R.ok("DB cannot remove BTC-USD from tickers (code-controlled)")
    else:
        R.fail("DB override protection", f"DB stripped BTC! tickers={loaded.tickers}")

    if "BTC-USD" in loaded.live_tickers:
        R.ok("DB cannot remove BTC-USD from live_tickers (code-controlled)")
    else:
        R.fail("DB override protection", f"DB stripped BTC! live={loaded.live_tickers}")

except Exception as e:
    R.fail("DB override check", str(e))


# =========================================================================
# 3. VALID TICKERS: routes accept BTC-USD
# =========================================================================
print("\n--- 3. API ROUTE VALIDATION ---")

try:
    from backend.api.routes.agape_spot_routes import _VALID_TICKERS

    for tk in LIVE_TICKERS:
        if tk in _VALID_TICKERS:
            R.ok(f"{tk} in _VALID_TICKERS (API won't reject with 400)")
        else:
            R.fail(f"{tk} in _VALID_TICKERS", f"API will return 400! valid={_VALID_TICKERS}")

except ImportError:
    # Direct import may fail in worker process; check via code
    R.warn("Route import", "Could not import routes directly, checking SPOT_TICKERS instead")
    for tk in LIVE_TICKERS:
        if tk in SPOT_TICKERS:
            R.ok(f"{tk} in SPOT_TICKERS (routes derive _VALID_TICKERS from this)")
        else:
            R.fail(f"{tk} validation", "Not in SPOT_TICKERS")


# =========================================================================
# 4. TRADER: singleton has both tickers + win trackers
# =========================================================================
print("\n--- 4. TRADER SINGLETON ---")

try:
    from trading.agape_spot.trader import get_agape_spot_trader, create_agape_spot_trader

    trader = get_agape_spot_trader()
    if not trader:
        R.info("No running trader singleton — creating one for verification...")
        trader = create_agape_spot_trader()

    if trader:
        # Config check
        for tk in LIVE_TICKERS:
            if tk in trader.config.tickers:
                R.ok(f"Trader config has {tk}")
            else:
                R.fail(f"Trader config {tk}", f"tickers={trader.config.tickers}")

            if tk in trader.config.live_tickers:
                R.ok(f"Trader config: {tk} is LIVE")
            else:
                R.fail(f"Trader config {tk} live", "Not in live_tickers!")

        # Win trackers
        if hasattr(trader, '_win_trackers'):
            for tk in LIVE_TICKERS:
                wt = trader._win_trackers.get(tk)
                if wt:
                    R.ok(f"{tk} win tracker: trades={wt.total_trades}, P(win)={wt.win_probability:.3f}")
                else:
                    R.fail(f"{tk} win tracker", "MISSING — Bayesian tracker not loaded")
        else:
            R.fail("Win trackers", "_win_trackers attribute missing from trader")
    else:
        R.fail("Trader", "Could not create trader singleton")

except Exception as e:
    R.fail("Trader check", str(e))


# =========================================================================
# 5. EXECUTOR: Coinbase clients for both tickers
# =========================================================================
print("\n--- 5. COINBASE CLIENTS ---")

try:
    if trader and hasattr(trader, 'executor'):
        ex = trader.executor

        # Global client status
        R.info(f"has_any_client = {ex.has_any_client}")
        R.info(f"Default client (_client): {'Connected' if ex._client else 'NONE'}")
        R.info(f"Ticker clients: {list(ex._ticker_clients.keys())}")

        for tk in LIVE_TICKERS:
            client = ex._get_client(tk)
            if client is not None:
                source = "dedicated" if tk in ex._ticker_clients else "default"
                R.ok(f"{tk} has Coinbase client (source: {source})")
            else:
                R.fail(f"{tk} Coinbase client", "NO CLIENT — cannot place live orders!")

            # Check accounts
            accounts = ex.get_all_accounts(tk)
            live_accounts = [a for a in accounts if a[1] is True]
            paper_accounts = [a for a in accounts if a[1] is False]

            if live_accounts:
                labels = [a[0] for a in live_accounts]
                R.ok(f"{tk} live accounts: {labels}")
            else:
                R.fail(f"{tk} live accounts", "NO LIVE ACCOUNTS — orders will only go to paper!")

            R.info(f"{tk} all accounts: {accounts}")

        # Product limits
        R.info(f"Product limits loaded for: {list(ex._product_limits.keys())}")
        for tk in LIVE_TICKERS:
            limits = ex._product_limits.get(tk)
            if limits:
                R.ok(f"{tk} product limits: min_base={limits.get('base_min_size')}, "
                     f"min_quote=${limits.get('quote_min_size')}, "
                     f"increment={limits.get('base_increment')}")
            else:
                R.warn(f"{tk} product limits", "Not cached — will use config defaults")
    else:
        R.fail("Executor", "Trader has no executor")

except Exception as e:
    R.fail("Coinbase client check", str(e))


# =========================================================================
# 6. PRICE DATA: Can fetch live prices
# =========================================================================
print("\n--- 6. LIVE PRICE DATA ---")

try:
    if trader and hasattr(trader, 'executor'):
        for tk in LIVE_TICKERS:
            price = trader.executor.get_current_price(tk)
            if price and price > 0:
                R.ok(f"{tk} live price: ${price:,.2f}")
            else:
                R.fail(f"{tk} price", "Cannot fetch price — orders will fail!")
    else:
        R.fail("Price check", "No trader/executor available")

except Exception as e:
    R.fail("Price check", str(e))


# =========================================================================
# 7. ACCOUNT BALANCES: Can see balances
# =========================================================================
print("\n--- 7. ACCOUNT BALANCES ---")

try:
    if trader and hasattr(trader, 'executor'):
        # Per-ticker balances
        for tk in LIVE_TICKERS:
            bal = trader.executor.get_account_balance(tk)
            if bal:
                symbol = SPOT_TICKERS[tk]["symbol"].lower()
                usd = bal.get("usd_balance", bal.get("usdc_balance", "?"))
                crypto = bal.get(f"{symbol}_balance", "?")
                acct_type = bal.get("account_type", "?")
                R.ok(f"{tk} balance ({acct_type}): USD=${usd}, {symbol.upper()}={crypto}")
            else:
                R.warn(f"{tk} balance", "Could not fetch (client may not exist)")

        # All accounts summary
        all_bal = trader.executor.get_all_account_balances()
        if all_bal:
            R.ok(f"All account balances: {len(all_bal)} accounts")
            for label, data in all_bal.items():
                tickers_on_acct = data.get("tickers", [])
                usd = data.get("usd_balance", data.get("usdc_balance", "?"))
                R.info(f"  Account '{label}': USD=${usd}, tickers={tickers_on_acct}")
        else:
            R.warn("All balances", "Could not fetch")
    else:
        R.fail("Balance check", "No trader/executor")

except Exception as e:
    R.fail("Balance check", str(e))


# =========================================================================
# 8. SIGNAL GATE: Bayesian won't block on cold start
# =========================================================================
print("\n--- 8. SIGNAL GATE ---")

try:
    from trading.agape_spot.signals import AgapeSpotSignalGenerator

    assert AgapeSpotSignalGenerator.MIN_WIN_PROBABILITY == 0.50
    R.ok(f"MIN_WIN_PROBABILITY = {AgapeSpotSignalGenerator.MIN_WIN_PROBABILITY}")

    if trader:
        gen = trader.signals
        for tk in LIVE_TICKERS:
            prob = gen._calculate_win_probability(tk, "POSITIVE")
            status = "ALLOWED" if prob >= 0.50 else "BLOCKED"
            color = "\033[92m" if prob >= 0.50 else "\033[91m"
            if prob >= 0.50:
                R.ok(f"{tk} win probability = {prob:.3f} → {color}{status}\033[0m")
            else:
                R.fail(f"{tk} signal gate", f"P(win)={prob:.3f} < 0.50 → BLOCKED from trading!")

            # Check all regimes
            for regime in ["POSITIVE", "NEGATIVE", "NEUTRAL"]:
                rp = gen._calculate_win_probability(tk, regime)
                gate = "PASS" if rp >= 0.50 else "BLOCK"
                R.info(f"  {tk} {regime}: P(win)={rp:.3f} → {gate}")

except Exception as e:
    R.fail("Signal gate", str(e))


# =========================================================================
# 9. ORDER MINIMUMS: Can we place minimum orders?
# =========================================================================
print("\n--- 9. ORDER MINIMUMS ---")

try:
    if trader and hasattr(trader, 'executor'):
        for tk in LIVE_TICKERS:
            sp = SPOT_TICKERS[tk]
            min_notional = trader.executor.get_min_notional(tk)
            min_base = trader.executor.get_min_base_size(tk)
            default_qty = sp["default_quantity"]
            price = trader.executor.get_current_price(tk) or 0

            notional = default_qty * price
            R.info(f"{tk}: default_qty={default_qty}, price=${price:,.2f}, notional=${notional:,.2f}")
            R.info(f"{tk}: min_notional=${min_notional}, min_base={min_base}")

            if notional >= min_notional:
                R.ok(f"{tk} default order ${notional:,.2f} >= min ${min_notional} notional")
            else:
                R.fail(f"{tk} order size", f"${notional:.2f} < min ${min_notional} — order will be rejected!")

            if default_qty >= min_base:
                R.ok(f"{tk} default qty {default_qty} >= min base {min_base}")
            else:
                R.fail(f"{tk} qty size", f"{default_qty} < min {min_base} — order will be rejected!")

except Exception as e:
    R.fail("Order minimums", str(e))


# =========================================================================
# 10. END-TO-END: API endpoint returns both tickers
# =========================================================================
print("\n--- 10. API ENDPOINTS ---")

api_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")

try:
    import urllib.request
    import json

    def api_get(path):
        url = f"{api_url}{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "LiveCheck/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())

    # Summary
    try:
        data = api_get("/api/agape-spot/summary")
        if data.get("success"):
            tickers = data.get("data", {}).get("tickers", {})
            for tk in LIVE_TICKERS:
                if tk in tickers:
                    td = tickers[tk]
                    mode = td.get("mode", "?")
                    price = td.get("current_price", 0)
                    if mode == "live":
                        R.ok(f"Summary API: {tk} mode=LIVE, price=${price:,.2f}")
                    else:
                        R.fail(f"Summary API {tk}", f"mode={mode} (should be 'live')")
                else:
                    R.fail(f"Summary API {tk}", f"MISSING from response! Keys: {list(tickers.keys())}")
        else:
            R.warn("Summary API", f"success=false: {data.get('reason')}")
    except Exception as e:
        R.warn("Summary API", str(e))

    # Per-ticker status
    for tk in LIVE_TICKERS:
        try:
            data = api_get(f"/api/agape-spot/status?ticker={tk}")
            if data.get("success"):
                status = data.get("data", {})
                mode = status.get("mode", "?")
                live_ready = status.get("live_ready", False)
                cb = status.get("coinbase_connected", False)
                cb_acct = status.get("coinbase_account", "?")

                if live_ready:
                    R.ok(f"{tk} status: live_ready=True, coinbase={cb_acct}")
                elif mode == "live" and cb:
                    R.ok(f"{tk} status: mode=live, coinbase=connected ({cb_acct})")
                else:
                    R.fail(f"{tk} status", f"mode={mode}, live_ready={live_ready}, coinbase={cb}, acct={cb_acct}")
            else:
                R.fail(f"{tk} status API", f"success=false: {data.get('reason', data.get('detail', '?'))}")
        except Exception as e:
            R.warn(f"{tk} status API", str(e))

    # Tickers endpoint
    try:
        data = api_get("/api/agape-spot/tickers")
        if data.get("success"):
            live_list = data.get("live_tickers", [])
            for tk in LIVE_TICKERS:
                if tk in live_list:
                    R.ok(f"Tickers API: {tk} in live_tickers")
                else:
                    R.fail(f"Tickers API {tk}", f"Not in live_tickers: {live_list}")
    except Exception as e:
        R.warn("Tickers API", str(e))

except Exception as e:
    R.warn("API checks", str(e))


# =========================================================================
# 11. ENV VARS: Coinbase credentials exist
# =========================================================================
print("\n--- 11. ENVIRONMENT ---")

env_checks = [
    ("COINBASE_API_KEY", "Default Coinbase client"),
    ("COINBASE_API_SECRET", "Default Coinbase secret"),
    ("COINBASE_DEDICATED_API_KEY", "Shared dedicated client"),
    ("COINBASE_DEDICATED_API_SECRET", "Shared dedicated secret"),
]

for var, desc in env_checks:
    val = os.getenv(var)
    if val:
        masked = val[:20] + "..." if len(val) > 20 else val[:5] + "..."
        R.ok(f"{var} set ({desc}): {masked}")
    else:
        R.warn(f"{var}", f"NOT SET — {desc} won't initialize")

# Per-ticker keys (optional)
for tk in LIVE_TICKERS:
    symbol = SPOT_TICKERS.get(tk, {}).get("symbol", tk.split("-")[0])
    key_var = f"COINBASE_{symbol.upper()}_API_KEY"
    val = os.getenv(key_var)
    if val:
        R.info(f"{key_var} set (per-ticker dedicated)")
    else:
        R.info(f"{key_var} not set (will use shared dedicated or default)")


# =========================================================================
# SUMMARY
# =========================================================================
print("\n" + "=" * 70)
total = R.passed + R.failed
print(f"TOTAL: {R.passed}/{total} PASSED — {R.failed} FAILED")
print("=" * 70)

if R.errors:
    print("\n\033[91mFAILURES:\033[0m")
    for err in R.errors:
        print(err)

status = "LIVE TRADING READY" if R.failed == 0 else f"{R.failed} ISSUES FOUND"
color = "\033[92m" if R.failed == 0 else "\033[91m"
print(f"\n{color}STATUS: {status}\033[0m")

if R.failed == 0:
    print("\nETH-USD and BTC-USD are fully configured for live Coinbase trading.")
else:
    print("\nFix the failures above before going live.")

print("=" * 70)
sys.exit(0 if R.failed == 0 else 1)
