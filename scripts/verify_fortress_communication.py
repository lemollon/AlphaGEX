#!/usr/bin/env python3
"""
FORTRESS Communication Verification Script

This script verifies the entire FORTRESS data flow:
1. Backend routes are registered and accessible
2. FORTRESS trader is importable and functional
3. Tradier API connectivity
4. Database logging works
5. Scheduler integration

Run this on Render to verify everything works.
"""

import os
import sys
import json
import requests
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header(title):
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{title}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

def print_pass(msg):
    print(f"{GREEN}✓ PASS:{RESET} {msg}")

def print_fail(msg):
    print(f"{RED}✗ FAIL:{RESET} {msg}")

def print_warn(msg):
    print(f"{YELLOW}⚠ WARN:{RESET} {msg}")

def print_info(msg):
    print(f"  {msg}")

results = {
    'passed': 0,
    'failed': 0,
    'warnings': 0,
    'checks': []
}

def check(name, condition, details=""):
    if condition:
        print_pass(name)
        results['passed'] += 1
        results['checks'].append({'name': name, 'status': 'pass', 'details': details})
    else:
        print_fail(name)
        results['failed'] += 1
        results['checks'].append({'name': name, 'status': 'fail', 'details': details})

def warn(name, details=""):
    print_warn(name)
    results['warnings'] += 1
    results['checks'].append({'name': name, 'status': 'warn', 'details': details})


def main():
    print_header("FORTRESS COMMUNICATION VERIFICATION")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python: {sys.version.split()[0]}")

    # =========================================================================
    # CHECK 1: Environment Variables
    # =========================================================================
    print_header("1. ENVIRONMENT CONFIGURATION")

    tradier_key = os.getenv('TRADIER_API_KEY')
    tradier_account = os.getenv('TRADIER_ACCOUNT_ID')
    tradier_sandbox = os.getenv('TRADIER_SANDBOX', 'true')
    database_url = os.getenv('DATABASE_URL')

    check("TRADIER_API_KEY set", bool(tradier_key))
    check("TRADIER_ACCOUNT_ID set", bool(tradier_account))
    check("DATABASE_URL set", bool(database_url))
    print_info(f"TRADIER_SANDBOX: {tradier_sandbox}")

    # =========================================================================
    # CHECK 2: FORTRESS Module Import
    # =========================================================================
    print_header("2. FORTRESS MODULE IMPORT")

    try:
        from trading.fortress_v2 import FortressTrader, TradingMode, FortressConfig
        check("FortressTrader class imported", True)
        check("TradingMode enum imported", True)
        check("FortressConfig dataclass imported", True)
    except ImportError as e:
        check("FORTRESS module import", False, str(e))

    # =========================================================================
    # CHECK 3: FORTRESS Initialization
    # =========================================================================
    print_header("3. FORTRESS INITIALIZATION")

    try:
        fortress = FortressTrader(mode=TradingMode.PAPER, initial_capital=200_000)
        check("FortressTrader instantiated", True)

        # Check configuration
        ticker = fortress.get_trading_ticker()
        spread_width = fortress.get_spread_width()
        min_credit = fortress.get_min_credit()

        check(f"Trading ticker = SPY (sandbox)", ticker == "SPY", f"Got: {ticker}")
        check(f"Spread width = $2 (SPY)", spread_width == 2.0, f"Got: ${spread_width}")
        check(f"Min credit = $0.15 (SPY)", min_credit == 0.15, f"Got: ${min_credit}")

        # Check status method
        status = fortress.get_status()
        check("get_status() works", 'mode' in status and 'capital' in status)
        print_info(f"  Mode: {status.get('mode')}")
        print_info(f"  Capital: ${status.get('capital', 0):,.0f}")
        print_info(f"  In Window: {status.get('in_trading_window')}")

    except Exception as e:
        check("FORTRESS initialization", False, str(e))

    # =========================================================================
    # CHECK 4: Tradier Connection
    # =========================================================================
    print_header("4. TRADIER API CONNECTION")

    try:
        if fortress.tradier:
            check("Tradier client initialized", True)

            # Get account balance
            balance = fortress.tradier.get_account_balance()
            if balance:
                check("Account balance API works", True)
                total_equity = balance.get('total_equity', 0)
                option_bp = balance.get('option_buying_power', 0)
                print_info(f"  Total Equity: ${total_equity:,.2f}")
                print_info(f"  Option BP: ${option_bp:,.2f}")

                if option_bp == 0 and total_equity > 0:
                    warn("Option Buying Power is $0 - need to reset sandbox account")
            else:
                check("Account balance API works", False, "No data returned")

            # Get SPY quote
            quote = fortress.tradier.get_quote("SPY")
            if quote and quote.get('last'):
                check("SPY quote API works", True)
                print_info(f"  SPY: ${quote.get('last')}")
            else:
                check("SPY quote API works", False, "No quote data")

        else:
            check("Tradier client initialized", False, "tradier is None")

    except Exception as e:
        check("Tradier API", False, str(e))

    # =========================================================================
    # CHECK 5: Options Chain Access
    # =========================================================================
    print_header("5. OPTIONS CHAIN ACCESS")

    try:
        expirations = fortress.tradier.get_option_expirations('SPY')
        if expirations:
            check("SPY expirations available", True)
            print_info(f"  Found {len(expirations)} expirations")
            print_info(f"  Nearest: {expirations[0]}")

            # Get chain
            chain = fortress.tradier.get_option_chain('SPY', expirations[0])
            if chain and chain.chains:
                contracts = chain.chains.get(expirations[0], [])
                puts = len([c for c in contracts if c.option_type == 'put'])
                calls = len([c for c in contracts if c.option_type == 'call'])
                check("SPY options chain available", puts > 0 and calls > 0)
                print_info(f"  Contracts: {puts} puts, {calls} calls")
            else:
                check("SPY options chain available", False, "No chain data")
        else:
            check("SPY expirations available", False)

    except Exception as e:
        check("Options chain access", False, str(e))

    # =========================================================================
    # CHECK 6: Market Data
    # =========================================================================
    print_header("6. MARKET DATA")

    try:
        market_data = fortress.get_current_market_data()
        if market_data:
            check("get_current_market_data() works", True)
            print_info(f"  Ticker: {market_data.get('ticker')}")
            print_info(f"  Price: ${market_data.get('underlying_price', 0):,.2f}")
            print_info(f"  VIX: {market_data.get('vix', 0):.1f}")
            print_info(f"  Expected Move: ${market_data.get('expected_move', 0):.2f}")
        else:
            check("get_current_market_data() works", False, "Returned None")

    except Exception as e:
        check("Market data", False, str(e))

    # =========================================================================
    # CHECK 7: Decision Logger
    # =========================================================================
    print_header("7. DECISION LOGGER")

    try:
        from trading.decision_logger import DecisionLogger, BotName
        check("DecisionLogger imported", True)
        check("BotName.FORTRESS exists", hasattr(BotName, 'FORTRESS'))
        print_info(f"  BotName.FORTRESS = {BotName.FORTRESS.value}")

        # Check database connection
        logger = DecisionLogger()
        check("DecisionLogger instantiated", True)

    except Exception as e:
        check("Decision logger", False, str(e))

    # =========================================================================
    # CHECK 8: Backend Route Registration
    # =========================================================================
    print_header("8. BACKEND ROUTE REGISTRATION")

    try:
        from backend.api.routes.trader_routes import router

        # Get all routes
        routes = [r.path for r in router.routes]

        fortress_status_route = '/bots/fortress/status' in routes
        ares_run_route = '/bots/fortress/run' in routes

        check("/bots/fortress/status route exists", fortress_status_route)
        check("/bots/fortress/run route exists", ares_run_route)

        if not fortress_status_route or not ares_run_route:
            print_info("  Available routes:")
            for r in routes:
                if 'fortress' in r.lower() or 'bots' in r.lower():
                    print_info(f"    {r}")

    except Exception as e:
        check("Backend routes", False, str(e))

    # =========================================================================
    # CHECK 9: Scheduler Integration
    # =========================================================================
    print_header("9. SCHEDULER INTEGRATION")

    try:
        from scheduler.trader_scheduler import CAPITAL_ALLOCATION
        check("CAPITAL_ALLOCATION imported", True)

        ares_capital = CAPITAL_ALLOCATION.get('FORTRESS', 0)
        check("FORTRESS capital allocated", ares_capital > 0, f"${ares_capital:,}")
        print_info(f"  FORTRESS: ${ares_capital:,}")
        print_info(f"  LAZARUS: ${CAPITAL_ALLOCATION.get('LAZARUS', 0):,}")
        print_info(f"  CORNERSTONE: ${CAPITAL_ALLOCATION.get('CORNERSTONE', 0):,}")
        print_info(f"  Total: ${CAPITAL_ALLOCATION.get('TOTAL', 0):,}")

    except Exception as e:
        check("Scheduler integration", False, str(e))

    # =========================================================================
    # CHECK 10: Trading Window
    # =========================================================================
    print_header("10. TRADING WINDOW")

    try:
        in_window = fortress.is_trading_window()
        should_trade = fortress.should_trade_today()

        print_info(f"  Current Time: {datetime.now().strftime('%H:%M:%S')}")
        print_info(f"  In Trading Window: {in_window}")
        print_info(f"  Should Trade Today: {should_trade}")
        print_info(f"  Config Window: {fortress.config.entry_time_start} - {fortress.config.entry_time_end}")

        check("Trading window logic works", True)

    except Exception as e:
        check("Trading window", False, str(e))

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print_header("VERIFICATION SUMMARY")

    total = results['passed'] + results['failed']
    print(f"  Passed: {GREEN}{results['passed']}{RESET}/{total}")
    print(f"  Failed: {RED}{results['failed']}{RESET}/{total}")
    print(f"  Warnings: {YELLOW}{results['warnings']}{RESET}")

    if results['failed'] == 0:
        print(f"\n{GREEN}{'='*60}{RESET}")
        print(f"{GREEN}ALL CHECKS PASSED - FORTRESS Communication is working!{RESET}")
        print(f"{GREEN}{'='*60}{RESET}")
    else:
        print(f"\n{RED}{'='*60}{RESET}")
        print(f"{RED}SOME CHECKS FAILED - Review issues above{RESET}")
        print(f"{RED}{'='*60}{RESET}")

        print("\nFailed checks:")
        for c in results['checks']:
            if c['status'] == 'fail':
                print(f"  {RED}✗{RESET} {c['name']}: {c['details']}")

    return results['failed'] == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
