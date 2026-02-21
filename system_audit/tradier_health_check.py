#!/usr/bin/env python3
"""
TRADIER API HEALTH CHECK — Pre/Post Deploy Verification
========================================================
Run BEFORE and AFTER every deployment to verify Tradier connectivity is intact.

Usage on Render shell:
    python3 system_audit/tradier_health_check.py              # Full check
    python3 system_audit/tradier_health_check.py --save-baseline  # Save baseline snapshot
    python3 system_audit/tradier_health_check.py --compare     # Compare against saved baseline

Exit codes:
    0 = All checks passed
    1 = One or more checks FAILED (do NOT deploy / ROLLBACK immediately)
"""
import os
import sys
import json
import urllib.request
from datetime import datetime

RESULTS = []
PASS_COUNT = 0
FAIL_COUNT = 0
WARN_COUNT = 0


def check(name, passed, detail=""):
    """Record a check result."""
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT
    if passed is None:
        status = "WARN"
        WARN_COUNT += 1
    elif passed:
        status = "PASS"
        PASS_COUNT += 1
    else:
        status = "FAIL"
        FAIL_COUNT += 1
    RESULTS.append({"name": name, "status": status, "detail": detail})
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARN": "[WARN]"}[status]
    print(f"  {icon} {name}")
    if detail:
        print(f"         {detail}")


def tradier_get(base_url, api_token, endpoint, timeout=10):
    """Make a GET request to Tradier API."""
    url = f"{base_url}{endpoint}"
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {api_token}',
        'Accept': 'application/json'
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        return {'error': f"HTTP {e.code}: {e.read().decode()[:200]}"}, e.code
    except Exception as e:
        return {'error': str(e)}, 0


def main():
    global PASS_COUNT, FAIL_COUNT, WARN_COUNT

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_baseline = '--save-baseline' in sys.argv
    compare_baseline = '--compare' in sys.argv

    print("=" * 60)
    print("  TRADIER API HEALTH CHECK")
    print(f"  {timestamp}")
    if save_baseline:
        print("  MODE: Saving baseline snapshot")
    elif compare_baseline:
        print("  MODE: Comparing against baseline")
    else:
        print("  MODE: Standard health check")
    print("=" * 60)

    # ── CHECK 1: Environment variables exist ──
    print("\n--- 1. ENVIRONMENT VARIABLES ---")

    api_key = os.environ.get('TRADIER_API_KEY')
    prod_key = os.environ.get('TRADIER_PROD_API_KEY')
    account_id = os.environ.get('TRADIER_ACCOUNT_ID')
    sandbox_key = os.environ.get('TRADIER_SANDBOX_API_KEY')
    sandbox_account = os.environ.get('TRADIER_SANDBOX_ACCOUNT_ID')

    # Determine which token to use (same logic as TradierDataFetcher)
    api_token = prod_key or api_key
    check("TRADIER_API_KEY or TRADIER_PROD_API_KEY exists",
          api_token is not None,
          f"Token prefix: {api_token[:8]}..." if api_token else "MISSING")
    check("TRADIER_ACCOUNT_ID exists",
          account_id is not None,
          f"Account: {account_id}" if account_id else "MISSING")
    check("TRADIER_SANDBOX_API_KEY exists (optional)",
          None if sandbox_key is None else True,
          "Present" if sandbox_key else "Not set (OK if not using sandbox)")
    check("TRADIER_SANDBOX_ACCOUNT_ID exists (optional)",
          None if sandbox_account is None else True,
          "Present" if sandbox_account else "Not set (OK if not using sandbox)")

    if not api_token or not account_id:
        print("\n  CANNOT CONTINUE: Missing required credentials")
        print("=" * 60)
        print(f"  RESULT: {FAIL_COUNT} FAILED — DO NOT DEPLOY")
        print("=" * 60)
        return 1

    # ── CHECK 2: Production API connectivity ──
    print("\n--- 2. PRODUCTION API CONNECTIVITY ---")
    BASE_URL = 'https://api.tradier.com/v1'

    # 2a. Can we reach the API at all? (market clock is unauthenticated-ish)
    data, status = tradier_get(BASE_URL, api_token, '/markets/clock')
    check("Production API reachable (markets/clock)",
          status == 200,
          f"HTTP {status}" if status != 200 else "OK")

    # 2b. Can we authenticate? (account balances require auth)
    data, status = tradier_get(BASE_URL, api_token, f'/accounts/{account_id}/balances')
    check("Authentication works (account balances)",
          status == 200,
          f"HTTP {status}" if status != 200 else "OK")

    balance_snapshot = {}
    if status == 200:
        bal = data.get('balances', data)
        equity = bal.get('total_equity')
        buying_power = bal.get('option_buying_power')
        if equity is not None:
            check("Account has equity",
                  float(equity) > 0,
                  f"Total equity: ${float(equity):,.2f}")
            balance_snapshot['total_equity'] = float(equity)
        if buying_power is not None:
            balance_snapshot['option_buying_power'] = float(buying_power)

    # 2c. Can we get positions?
    data, status = tradier_get(BASE_URL, api_token, f'/accounts/{account_id}/positions')
    check("Positions endpoint accessible",
          status == 200,
          f"HTTP {status}" if status != 200 else "OK")

    position_count = 0
    position_symbols = []
    if status == 200:
        positions = data.get('positions', {})
        if positions and positions != 'null':
            pos_list = positions.get('position', [])
            if isinstance(pos_list, dict):
                pos_list = [pos_list]
            position_count = len(pos_list)
            position_symbols = [p.get('symbol', '?') for p in pos_list]
        check("Position count retrieved",
              True,
              f"{position_count} positions" + (f": {', '.join(position_symbols[:5])}" if position_symbols else ""))

    # 2d. Can we get orders?
    data, status = tradier_get(BASE_URL, api_token, f'/accounts/{account_id}/orders')
    check("Orders endpoint accessible",
          status == 200,
          f"HTTP {status}" if status != 200 else "OK")

    order_count = 0
    if status == 200:
        orders = data.get('orders', {})
        if orders and orders != 'null':
            order_list = orders.get('order', [])
            if isinstance(order_list, dict):
                order_list = [order_list]
            order_count = len(order_list)
        check("Order history retrieved",
              True,
              f"{order_count} recent orders")

    # ── CHECK 3: SPX quote (critical for JUBILEE IC) ──
    print("\n--- 3. SPX QUOTE (Critical for JUBILEE IC) ---")
    data, status = tradier_get(BASE_URL, api_token, '/markets/quotes?symbols=$SPX.X')
    spx_price = None
    if status == 200:
        quotes = data.get('quotes', {})
        quote = quotes.get('quote', {})
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        spx_price = quote.get('last', quote.get('close'))
        check("SPX quote available ($SPX.X)",
              spx_price is not None and float(spx_price) > 1000,
              f"SPX = ${float(spx_price):,.2f}" if spx_price else "No price returned")
    else:
        check("SPX quote available ($SPX.X)",
              False,
              f"HTTP {status}")

    # ── CHECK 4: SPX option chain (critical for IC trading) ──
    print("\n--- 4. SPX OPTION CHAIN ---")
    data, status = tradier_get(BASE_URL, api_token, '/markets/options/expirations?symbol=$SPX.X')
    if status == 200:
        expirations = data.get('expirations', {})
        exp_list = expirations.get('date', []) if expirations else []
        check("SPX option expirations available",
              len(exp_list) > 0 if isinstance(exp_list, list) else False,
              f"{len(exp_list)} expirations" if isinstance(exp_list, list) else "Unexpected format")
    else:
        check("SPX option expirations available",
              False,
              f"HTTP {status}")

    # ── CHECK 5: SPY quote (for ARES/ATHENA/ICARUS) ──
    print("\n--- 5. SPY QUOTE (For ARES/ATHENA/ICARUS) ---")
    data, status = tradier_get(BASE_URL, api_token, '/markets/quotes?symbols=SPY')
    if status == 200:
        quotes = data.get('quotes', {})
        quote = quotes.get('quote', {})
        if isinstance(quote, list):
            quote = quote[0] if quote else {}
        spy_price = quote.get('last', quote.get('close'))
        check("SPY quote available",
              spy_price is not None and float(spy_price) > 100,
              f"SPY = ${float(spy_price):,.2f}" if spy_price else "No price returned")
    else:
        check("SPY quote available",
              False,
              f"HTTP {status}")

    # ── CHECK 6: Sandbox connectivity (if configured) ──
    if sandbox_key and sandbox_account:
        print("\n--- 6. SANDBOX API (Optional) ---")
        SANDBOX_URL = 'https://sandbox.tradier.com/v1'
        data, status = tradier_get(SANDBOX_URL, sandbox_key,
                                   f'/accounts/{sandbox_account}/balances')
        check("Sandbox API reachable",
              status == 200,
              f"HTTP {status}" if status != 200 else "OK")
    else:
        print("\n--- 6. SANDBOX API (Skipped - not configured) ---")

    # ── CHECK 7: TradierDataFetcher import ──
    print("\n--- 7. TRADIER CLIENT IMPORT ---")
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from data.tradier_data_fetcher import TradierDataFetcher
        check("TradierDataFetcher importable",
              True,
              "data.tradier_data_fetcher.TradierDataFetcher")
    except Exception as e:
        check("TradierDataFetcher importable",
              False,
              str(e)[:100])

    # ── CHECK 8: Verify URL constants haven't changed ──
    print("\n--- 8. URL CONSTANT VERIFICATION ---")
    try:
        import inspect
        from data.tradier_data_fetcher import TradierDataFetcher
        source = inspect.getsource(TradierDataFetcher)
        check("Production URL in client",
              'api.tradier.com' in source,
              "Found api.tradier.com")
        check("Sandbox URL in client",
              'sandbox.tradier.com' in source,
              "Found sandbox.tradier.com")
    except Exception as e:
        check("URL constant verification",
              None,
              f"Could not inspect source: {str(e)[:80]}")

    # ── SNAPSHOT for baseline comparison ──
    snapshot = {
        'timestamp': timestamp,
        'pass_count': PASS_COUNT,
        'fail_count': FAIL_COUNT,
        'warn_count': WARN_COUNT,
        'balance': balance_snapshot,
        'position_count': position_count,
        'position_symbols': position_symbols,
        'order_count': order_count,
        'spx_price': float(spx_price) if spx_price else None,
        'results': RESULTS,
    }

    baseline_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'tradier_baseline.json')

    if save_baseline:
        with open(baseline_path, 'w') as f:
            json.dump(snapshot, f, indent=2)
        print(f"\n  Baseline saved to: {baseline_path}")

    if compare_baseline:
        print("\n--- BASELINE COMPARISON ---")
        if os.path.exists(baseline_path):
            with open(baseline_path) as f:
                baseline = json.load(f)
            print(f"  Baseline from: {baseline.get('timestamp', '?')}")
            print(f"  Current time:  {timestamp}")

            # Compare key metrics
            b_equity = baseline.get('balance', {}).get('total_equity')
            c_equity = balance_snapshot.get('total_equity')
            if b_equity and c_equity:
                diff = c_equity - b_equity
                pct = diff / b_equity * 100
                status = "OK" if abs(pct) < 5 else "SIGNIFICANT CHANGE"
                print(f"  Equity: ${b_equity:,.2f} -> ${c_equity:,.2f} ({diff:+,.2f}, {pct:+.1f}%) [{status}]")

            b_pos = baseline.get('position_count', 0)
            print(f"  Positions: {b_pos} -> {position_count} (delta: {position_count - b_pos:+d})")

            b_orders = baseline.get('order_count', 0)
            print(f"  Orders: {b_orders} -> {order_count} (delta: {order_count - b_orders:+d})")

            b_fails = baseline.get('fail_count', 0)
            if FAIL_COUNT > b_fails:
                print(f"  NEW FAILURES: {b_fails} -> {FAIL_COUNT} — INVESTIGATE!")
            elif FAIL_COUNT == 0:
                print(f"  No failures (same as baseline)")
        else:
            print(f"  No baseline found at {baseline_path}")
            print(f"  Run with --save-baseline first")

    # ── FINAL VERDICT ──
    print(f"\n{'='*60}")
    print(f"  TRADIER HEALTH CHECK RESULTS")
    print(f"  {PASS_COUNT} passed, {FAIL_COUNT} failed, {WARN_COUNT} warnings")
    if FAIL_COUNT == 0:
        print(f"  VERDICT: ALL CHECKS PASSED")
        if not save_baseline:
            print(f"  Safe to proceed with deployment")
    else:
        print(f"  VERDICT: {FAIL_COUNT} CHECKS FAILED")
        print(f"  DO NOT DEPLOY / ROLLBACK IMMEDIATELY")
        for r in RESULTS:
            if r['status'] == 'FAIL':
                print(f"    - {r['name']}: {r['detail']}")
    print(f"{'='*60}")

    return 1 if FAIL_COUNT > 0 else 0


if __name__ == '__main__':
    sys.exit(main())
