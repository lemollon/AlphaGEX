#!/usr/bin/env python3
"""
FORTRESS Full Cycle Debug Script
==============================

Runs a complete FORTRESS cycle and traces every step.

Run on Render shell:
    python scripts/debug_ares_full_cycle.py
"""

import os
import sys
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo('America/Chicago')

def main():
    print("=" * 70)
    print("FORTRESS FULL CYCLE DEBUG")
    print("=" * 70)
    print(f"Time: {datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d %H:%M:%S CT')}")
    print()

    try:
        from trading.fortress_v2.trader import FortressTrader
        from trading.fortress_v2.models import TradingMode

        print("[1] Initializing FORTRESS trader...")
        trader = FortressTrader(mode=TradingMode.PAPER)
        print(f"    Mode: {trader.mode}")
        print(f"    Ticker: {trader.config.ticker}")
        print()

        print("[2] Checking status...")
        status = trader.get_status()
        print(f"    Mode: {status.get('mode')}")
        print(f"    Capital: ${status.get('capital', 0):,.2f}")
        print(f"    In Trading Window: {status.get('in_trading_window')}")
        print(f"    Open Positions: {status.get('open_positions', 0)}")
        print()

        print("[3] Running cycle (with detailed logging)...")
        print("-" * 70)

        # Enable debug logging
        import logging
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger('trading.fortress_v2')
        logger.setLevel(logging.DEBUG)

        # Run the cycle
        result = trader.run_cycle()

        print("-" * 70)
        print()

        print("[4] Cycle Result:")
        print(f"    Action: {result.get('action')}")
        print(f"    Trade Opened: {result.get('trade_opened', False)}")
        print(f"    Positions Closed: {result.get('positions_closed', 0)}")
        print(f"    Realized P&L: ${result.get('realized_pnl', 0):.2f}")
        print()

        details = result.get('details', {})
        if details:
            print("[5] Details:")
            if details.get('skip_reason'):
                print(f"    Skip Reason: {details['skip_reason']}")
            if details.get('strategy_suggestion'):
                print(f"    Strategy Suggestion: {details['strategy_suggestion']}")
            if details.get('oracle_suggests_solomon'):
                print(f"    Oracle Suggests SOLOMON: {details['oracle_suggests_solomon']}")
            if details.get('position'):
                print(f"    Position: {json.dumps(details['position'], indent=6)}")
        print()

        errors = result.get('errors', [])
        if errors:
            print("[6] Errors:")
            for err in errors:
                print(f"    - {err}")
            print()

        print("=" * 70)
        if result.get('trade_opened'):
            print("SUCCESS: Trade was opened!")
        else:
            print(f"NO TRADE: {result.get('action')} - {details.get('skip_reason', 'See details above')}")
        print("=" * 70)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
