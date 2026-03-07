#!/usr/bin/env python3
"""
Test script: Verify Tradier API can provide historical option OHLC data
for Iron Condor backtesting.

Tests two endpoints:
1. /markets/history - Daily OHLC for option contracts
2. /markets/timesales - Intraday minute bars for option contracts

Uses PRODUCTION API (required for SPX/SPY options data even with sandbox account).
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try to load env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_api_key():
    """Get Tradier production API key (needed for market data)."""
    key = os.getenv('TRADIER_API_KEY')
    if not key:
        # Try sandbox key as fallback
        key = os.getenv('TRADIER_SANDBOX_API_KEY')
        if key:
            print("WARNING: Using SANDBOX key - historical option data may be limited")
    if not key:
        print("ERROR: No TRADIER_API_KEY or TRADIER_SANDBOX_API_KEY found in environment")
        sys.exit(1)
    return key


def build_occ_symbol(underlying: str, expiration: str, strike: float, option_type: str) -> str:
    """Build OCC option symbol. option_type: 'C' or 'P'"""
    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    exp_str = exp_date.strftime('%y%m%d')
    strike_str = f"{int(float(strike) * 1000):08d}"
    root = underlying.upper()
    if root == 'SPX':
        root = 'SPXW'  # Weekly SPX options use SPXW
    return f"{root}{exp_str}{option_type}{strike_str}"


def test_daily_history(api_key: str, base_url: str, occ_symbol: str, start_date: str, end_date: str):
    """Test /markets/history endpoint for daily OHLC on an option contract."""
    print(f"\n{'='*70}")
    print(f"TEST 1: Daily OHLC History")
    print(f"  Endpoint: /markets/history")
    print(f"  Symbol:   {occ_symbol}")
    print(f"  Range:    {start_date} to {end_date}")
    print(f"{'='*70}")

    url = f"{base_url}/markets/history"
    params = {
        'symbol': occ_symbol,
        'interval': 'daily',
        'start': start_date,
        'end': end_date,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"  HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()

            if 'history' in data and data['history']:
                history = data['history']
                days = history.get('day', [])
                if isinstance(days, dict):
                    days = [days]  # Single day comes as dict, not list

                print(f"  Days returned: {len(days)}")
                print(f"\n  {'Date':<12} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>10}")
                print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

                for day in days:
                    print(f"  {day.get('date',''):<12} "
                          f"{day.get('open',0):>8.2f} "
                          f"{day.get('high',0):>8.2f} "
                          f"{day.get('low',0):>8.2f} "
                          f"{day.get('close',0):>8.2f} "
                          f"{day.get('volume',0):>10}")

                print(f"\n  RESULT: Daily OHLC data available for options contracts")
                print(f"  Fields: date, open, high, low, close, volume")
                return True
            else:
                print(f"  No history data returned.")
                print(f"  Response: {json.dumps(data, indent=2)[:500]}")
                return False
        else:
            print(f"  Error response: {resp.text[:500]}")
            return False

    except Exception as e:
        print(f"  Exception: {e}")
        return False


def test_timesales(api_key: str, base_url: str, occ_symbol: str, date: str, interval: str = '5min'):
    """Test /markets/timesales endpoint for intraday bars on an option contract."""
    print(f"\n{'='*70}")
    print(f"TEST 2: Intraday Time & Sales")
    print(f"  Endpoint: /markets/timesales")
    print(f"  Symbol:   {occ_symbol}")
    print(f"  Date:     {date}")
    print(f"  Interval: {interval}")
    print(f"{'='*70}")

    url = f"{base_url}/markets/timesales"
    params = {
        'symbol': occ_symbol,
        'interval': interval,
        'start': f"{date} 09:30",
        'end': f"{date} 16:00",
        'session_filter': 'open',
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"  HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            data = resp.json()

            if 'series' in data and data['series']:
                series = data['series']
                bars = series.get('data', [])
                if isinstance(bars, dict):
                    bars = [bars]

                print(f"  Bars returned: {len(bars)}")

                if bars:
                    # Show first 5 and last 5 bars
                    show_bars = bars[:5] + (['...'] if len(bars) > 10 else []) + bars[-5:] if len(bars) > 10 else bars

                    print(f"\n  {'Time':<22} {'Open':>8} {'High':>8} {'Low':>8} {'Close':>8} {'Volume':>8}")
                    print(f"  {'-'*22} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")

                    for bar in show_bars:
                        if bar == '...':
                            print(f"  {'...':<22}")
                            continue
                        print(f"  {bar.get('time',''):<22} "
                              f"{bar.get('open',0):>8.2f} "
                              f"{bar.get('high',0):>8.2f} "
                              f"{bar.get('low',0):>8.2f} "
                              f"{bar.get('close',0):>8.2f} "
                              f"{bar.get('volume',0):>8}")

                    # Highlight the key data points for backtesting
                    first_bar = bars[0]
                    last_bar = bars[-1]
                    print(f"\n  KEY BACKTEST DATA POINTS:")
                    print(f"    Market Open price:  ${first_bar.get('open', 0):.2f} at {first_bar.get('time', '')}")
                    print(f"    Market Close price: ${last_bar.get('close', 0):.2f} at {last_bar.get('time', '')}")

                print(f"\n  RESULT: Intraday {interval} bars available for options contracts")
                return True
            else:
                print(f"  No timesales data returned.")
                print(f"  Response: {json.dumps(data, indent=2)[:500]}")
                return False
        else:
            print(f"  Error response: {resp.text[:500]}")
            return False

    except Exception as e:
        print(f"  Exception: {e}")
        return False


def test_expired_option_history(api_key: str, base_url: str):
    """Test if we can get data for EXPIRED options (critical for backtesting)."""
    print(f"\n{'='*70}")
    print(f"TEST 3: Expired Option Historical Data (Backtesting Critical)")
    print(f"{'='*70}")

    # Try an expired SPY option from ~1 month ago
    exp_date = (datetime.now() - timedelta(days=30))
    # Find a recent Friday
    while exp_date.weekday() != 4:  # Friday
        exp_date -= timedelta(days=1)

    exp_str = exp_date.strftime('%Y-%m-%d')
    # Use a round strike near recent SPY price
    strike = 580.0
    occ = build_occ_symbol('SPY', exp_str, strike, 'C')

    start = (exp_date - timedelta(days=5)).strftime('%Y-%m-%d')

    print(f"  Testing expired contract: {occ}")
    print(f"  Expiration: {exp_str}")
    print(f"  Query range: {start} to {exp_str}")

    result = test_daily_history(api_key, base_url, occ, start, exp_str)

    if not result:
        # Try a different strike
        strike = 570.0
        occ = build_occ_symbol('SPY', exp_str, strike, 'C')
        print(f"\n  Retrying with strike ${strike}: {occ}")
        result = test_daily_history(api_key, base_url, occ, start, exp_str)

    return result


def test_spx_option(api_key: str, base_url: str):
    """Test SPX index options (uses SPXW root)."""
    print(f"\n{'='*70}")
    print(f"TEST 4: SPX Index Options (SPXW)")
    print(f"{'='*70}")

    # Find a recent Friday for SPX expiration
    exp_date = (datetime.now() - timedelta(days=14))
    while exp_date.weekday() != 4:
        exp_date -= timedelta(days=1)

    exp_str = exp_date.strftime('%Y-%m-%d')
    strike = 5800.0  # Round SPX strike
    occ = build_occ_symbol('SPX', exp_str, strike, 'C')

    start = (exp_date - timedelta(days=3)).strftime('%Y-%m-%d')

    print(f"  Testing SPX contract: {occ}")
    print(f"  Expiration: {exp_str}")

    return test_daily_history(api_key, base_url, occ, start, exp_str)


def test_rate_limits(api_key: str, base_url: str):
    """Quick test of rate limits - how fast can we query?"""
    print(f"\n{'='*70}")
    print(f"TEST 5: Rate Limit Check (10 rapid requests)")
    print(f"{'='*70}")

    # Use a recent SPY option
    exp_date = (datetime.now() - timedelta(days=7))
    while exp_date.weekday() != 4:
        exp_date -= timedelta(days=1)
    exp_str = exp_date.strftime('%Y-%m-%d')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'application/json'
    }

    strikes = [570, 575, 580, 585, 590, 560, 565, 555, 595, 600]
    start = (exp_date - timedelta(days=2)).strftime('%Y-%m-%d')

    success = 0
    errors = 0
    start_time = time.time()

    for strike in strikes:
        occ = build_occ_symbol('SPY', exp_str, strike, 'C')
        url = f"{base_url}/markets/history"
        params = {'symbol': occ, 'interval': 'daily', 'start': start, 'end': exp_str}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            if resp.status_code == 200:
                success += 1
            elif resp.status_code == 429:
                errors += 1
                print(f"  RATE LIMITED at request #{success + errors}")
                break
            else:
                errors += 1
        except Exception:
            errors += 1

    elapsed = time.time() - start_time
    print(f"  Sent {success + errors} requests in {elapsed:.2f}s")
    print(f"  Success: {success}, Errors/Rate-limited: {errors}")
    print(f"  Rate: {(success + errors) / elapsed:.1f} requests/sec")

    if errors == 0:
        print(f"  RESULT: No rate limiting at {(success + errors) / elapsed:.1f} req/s")

    return errors == 0


def main():
    print("=" * 70)
    print("TRADIER HISTORICAL OPTION DATA TEST")
    print("Testing endpoints for Iron Condor backtesting feasibility")
    print("=" * 70)

    api_key = get_api_key()

    # Determine which base URL to use
    # For market data, production API is preferred
    sandbox_key = os.getenv('TRADIER_SANDBOX_API_KEY')
    prod_key = os.getenv('TRADIER_API_KEY')

    if prod_key:
        base_url = "https://api.tradier.com/v1"
        print(f"Using PRODUCTION API")
    else:
        base_url = "https://sandbox.tradier.com/v1"
        print(f"Using SANDBOX API (data may be limited)")

    print(f"API Key: {api_key[:8]}...{api_key[-4:]}")

    # ---- Find a recent active SPY option to test with ----
    # Use a recent expiration (last week's Friday)
    today = datetime.now()
    last_friday = today - timedelta(days=(today.weekday() - 4) % 7)
    if last_friday >= today:
        last_friday -= timedelta(days=7)

    # Go back one more week to ensure it's fully expired
    test_exp = (last_friday - timedelta(days=7)).strftime('%Y-%m-%d')
    test_strike = 580.0
    test_start = (datetime.strptime(test_exp, '%Y-%m-%d') - timedelta(days=5)).strftime('%Y-%m-%d')

    occ_call = build_occ_symbol('SPY', test_exp, test_strike, 'C')
    occ_put = build_occ_symbol('SPY', test_exp, test_strike, 'P')

    print(f"\nTest contracts:")
    print(f"  Call: {occ_call}")
    print(f"  Put:  {occ_put}")
    print(f"  Exp:  {test_exp}")

    results = {}

    # Test 1: Daily OHLC for a call
    results['daily_call'] = test_daily_history(api_key, base_url, occ_call, test_start, test_exp)
    time.sleep(0.2)

    # Test 1b: Daily OHLC for a put
    results['daily_put'] = test_daily_history(api_key, base_url, occ_put, test_start, test_exp)
    time.sleep(0.2)

    # Test 2: Intraday timesales (use the day before expiration)
    intraday_date = (datetime.strptime(test_exp, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    # Skip weekends
    intraday_dt = datetime.strptime(intraday_date, '%Y-%m-%d')
    while intraday_dt.weekday() >= 5:
        intraday_dt -= timedelta(days=1)
    intraday_date = intraday_dt.strftime('%Y-%m-%d')

    results['intraday'] = test_timesales(api_key, base_url, occ_call, intraday_date, '5min')
    time.sleep(0.2)

    # Test 3: Expired options (older)
    results['expired'] = test_expired_option_history(api_key, base_url)
    time.sleep(0.2)

    # Test 4: SPX index options
    results['spx'] = test_spx_option(api_key, base_url)
    time.sleep(0.2)

    # Test 5: Rate limits
    results['rate_limits'] = test_rate_limits(api_key, base_url)

    # ---- Summary ----
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    for test_name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {test_name}")

    print(f"\n{'='*70}")
    print(f"BACKTEST FEASIBILITY ASSESSMENT")
    print(f"{'='*70}")

    if results.get('daily_call') and results.get('daily_put'):
        print("  Daily OHLC for SPY options:     AVAILABLE")
        print("    -> Can get real open/close prices per contract per day")
        print("    -> Entry credit = sum of open prices for 4 IC legs")
        print("    -> Exit debit = sum of close prices for 4 IC legs")
    else:
        print("  Daily OHLC for SPY options:     NOT AVAILABLE")

    if results.get('intraday'):
        print("  Intraday bars for SPY options:   AVAILABLE")
        print("    -> Can get specific entry/exit time prices (e.g., 9:35 AM, 3:00 PM)")
    else:
        print("  Intraday bars for SPY options:   NOT AVAILABLE or LIMITED")

    if results.get('expired'):
        print("  Expired option data:            AVAILABLE")
        print("    -> Can backtest historical dates")
    else:
        print("  Expired option data:            NOT AVAILABLE")

    if results.get('spx'):
        print("  SPX index options:              AVAILABLE")
        print("    -> Can backtest SAMSON/ANCHOR SPX Iron Condors")
    else:
        print("  SPX index options:              NOT AVAILABLE (may need CBOE data)")

    if results.get('rate_limits'):
        print("  Rate limits:                    NO ISSUES at test rate")
    else:
        print("  Rate limits:                    RATE LIMITED - need throttling")

    # Estimate data collection time
    trading_days = 660  # ~2.5 years
    legs_per_ic = 4
    calls_per_day = legs_per_ic  # one /history call per leg per day
    total_calls = trading_days * calls_per_day
    est_time_mins = total_calls / 10 / 60  # ~10 req/s conservative

    print(f"\n  ESTIMATED DATA COLLECTION:")
    print(f"    Trading days to backtest: ~{trading_days}")
    print(f"    API calls needed: ~{total_calls} (4 legs x {trading_days} days)")
    print(f"    Est. time at 10 req/s: ~{est_time_mins:.0f} minutes")
    print(f"    Recommendation: Pre-download and cache in PostgreSQL")


if __name__ == '__main__':
    main()
