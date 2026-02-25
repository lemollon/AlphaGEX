#!/usr/bin/env python3
"""
Force Trade Script
==================

Forces FLAME or SPARK to execute a paper trade, bypassing trading-window
and has-traded-today checks.  Use this to verify end-to-end execution.

Usage (from Render shell):
    cd /opt/render/project/src/ironforge
    DATABASE_URL="..." /tmp/venv/bin/python scripts/force_trade.py flame
    DATABASE_URL="..." /tmp/venv/bin/python scripts/force_trade.py spark
"""

import sys
import os
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("force_trade")


def main():
    bot = "flame"
    if len(sys.argv) > 1:
        bot = sys.argv[1].lower()
    if bot not in ("flame", "spark"):
        print(f"Usage: {sys.argv[0]} [flame|spark]")
        sys.exit(1)

    print(f"=" * 60)
    print(f"  FORCE TRADE: {bot.upper()}")
    print(f"=" * 60)

    from config import Config

    valid, msg = Config.validate()
    if not valid:
        print(f"  Config invalid: {msg}")
        sys.exit(1)
    print(f"  [+] Config: OK")

    from setup_tables import setup_all_tables
    setup_all_tables()

    from trading.models import flame_config, spark_config
    from trading.signals import SignalGenerator
    from trading.executor import PaperExecutor
    from trading.db import TradingDatabase

    config = flame_config() if bot == "flame" else spark_config()
    db = TradingDatabase(bot_name=config.bot_name, dte_mode=config.dte_mode)
    db.initialize_paper_account(config.starting_capital)

    signal_gen = SignalGenerator(config)
    executor = PaperExecutor(config, db)

    # Step 1: Check for open positions
    open_positions = db.get_open_positions()
    if open_positions:
        print(f"  [!] {len(open_positions)} open position(s) found:")
        for pos in open_positions:
            print(f"      {pos.position_id} - {pos.put_long}/{pos.put_short_strike}P-{pos.call_short_strike}/{pos.call_long_strike}C")
        print(f"  Skipping trade (close existing positions first)")
        sys.exit(1)

    # Step 2: Generate signal
    print(f"\n  Generating signal...")
    signal = signal_gen.generate_signal()
    if not signal:
        print(f"  [FAIL] No signal generated (None)")
        sys.exit(1)
    if not signal.is_valid:
        print(f"  [FAIL] Signal not valid: {signal.reasoning}")
        sys.exit(1)

    print(f"  [+] Signal: {signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C")
    print(f"      Expiration: {signal.expiration}")
    print(f"      Credit: ${signal.total_credit:.4f} ({signal.source})")
    print(f"      Spot: ${signal.spot_price:.2f}, VIX: {signal.vix:.1f}")

    # Step 3: Size the trade
    account = db.get_paper_account()
    spread_width = signal.put_short - signal.put_long
    collateral_per = executor.calculate_collateral(spread_width, signal.total_credit)
    max_contracts = executor.calculate_max_contracts(account.buying_power, collateral_per)

    print(f"\n  Sizing:")
    print(f"      Buying Power: ${account.buying_power:.2f}")
    print(f"      Collateral/contract: ${collateral_per:.2f}")
    print(f"      Max Contracts: {max_contracts}")

    if max_contracts < 1:
        print(f"  [FAIL] Cannot afford any contracts")
        sys.exit(1)

    # Step 4: Execute
    print(f"\n  Executing paper trade...")
    position = executor.open_paper_position(signal, max_contracts)
    if not position:
        print(f"  [FAIL] Execution failed")
        sys.exit(1)

    # Step 5: Log signal
    db.log_signal(
        spot_price=signal.spot_price,
        vix=signal.vix,
        expected_move=signal.expected_move,
        call_wall=signal.call_wall,
        put_wall=signal.put_wall,
        gex_regime=signal.gex_regime,
        put_short=signal.put_short,
        put_long=signal.put_long,
        call_short=signal.call_short,
        call_long=signal.call_long,
        total_credit=signal.total_credit,
        confidence=signal.confidence,
        was_executed=True,
        reasoning=f"FORCE TRADE: {signal.reasoning}",
        wings_adjusted=signal.wings_adjusted,
    )

    db.update_heartbeat("active", "force_trade")

    print(f"\n  {'=' * 56}")
    print(f"  SUCCESS!")
    print(f"  Position ID: {position.position_id}")
    print(f"  Strikes: {signal.put_long}/{signal.put_short}P-{signal.call_short}/{signal.call_long}C")
    print(f"  Contracts: {max_contracts}")
    print(f"  Credit: ${signal.total_credit:.4f}")
    print(f"  Collateral: ${collateral_per * max_contracts:.2f}")
    print(f"  Expiration: {signal.expiration}")
    print(f"  {'=' * 56}")


if __name__ == "__main__":
    main()
