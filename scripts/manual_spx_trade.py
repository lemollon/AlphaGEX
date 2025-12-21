#!/usr/bin/env python3
"""
Manual SPX Iron Condor Trade Execution
=======================================

Execute an ARES-style SPX Iron Condor trade manually.
Uses LIVE Tradier connection to trade SPXW options.

Usage:
    python scripts/manual_spx_trade.py --dry-run    # Preview only
    python scripts/manual_spx_trade.py              # Execute trade
    python scripts/manual_spx_trade.py --contracts 2  # Custom size
"""

import os
import sys
import math
import argparse
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description='Manual SPX Iron Condor Trade')
    parser.add_argument('--dry-run', action='store_true', help='Preview without executing')
    parser.add_argument('--contracts', type=int, default=None, help='Number of contracts')
    parser.add_argument('--capital', type=float, default=200_000, help='Capital for sizing')
    args = parser.parse_args()

    from data.tradier_data_fetcher import TradierDataFetcher

    # MUST use production for SPX/SPXW
    logger.info("=" * 60)
    logger.info("MANUAL SPX IRON CONDOR TRADE")
    logger.info("=" * 60)

    # Check environment - need PRODUCTION for SPX
    sandbox = os.getenv('TRADIER_SANDBOX', 'false').lower() == 'true'
    if sandbox:
        logger.error("TRADIER_SANDBOX=true - Cannot trade SPX in sandbox mode!")
        logger.error("Set TRADIER_SANDBOX=false for production SPX trading")
        sys.exit(1)

    tradier = TradierDataFetcher(sandbox=False)
    logger.info("Connected to Tradier PRODUCTION")

    # ARES parameters for SPX
    SPREAD_WIDTH = 10.0  # $10 wide spreads
    RISK_PCT = 0.10  # 10% risk per trade
    MIN_CREDIT = 3.00  # Minimum $3 credit per spread

    # Get SPX price
    spx_quote = tradier.get_quote('SPX')
    spx_price = spx_quote.get('last') or spx_quote.get('close')
    logger.info(f"SPX Price: ${spx_price:.2f}")

    # Get VIX - use $VIX.X for Tradier (correct symbol format)
    vix_quote = tradier.get_quote('$VIX.X')
    vix = vix_quote.get('last') if vix_quote else 0
    if not vix:
        vix = 20.0  # Fallback
    logger.info(f"VIX: {vix:.2f}")

    # Calculate expected move (1 SD)
    expected_move = spx_price * vix / math.sqrt(252) / 100
    logger.info(f"Expected Move (1 SD): ${expected_move:.2f}")

    # Get 0DTE expiration (Central Time)
    tz = ZoneInfo('America/Chicago')
    today = datetime.now(tz).strftime('%Y-%m-%d')

    expirations = tradier.get_option_expirations('SPXW')
    if today not in expirations:
        logger.error(f"No 0DTE expiration available for {today}")
        logger.info(f"Available: {expirations[:5]}")
        # Use next available
        exp = expirations[0] if expirations else None
        if not exp:
            sys.exit(1)
    else:
        exp = today

    logger.info(f"Expiration: {exp}")

    # Get options chain
    chain_obj = tradier.get_option_chain('SPXW', exp, greeks=True)
    chain = chain_obj.chains.get(exp, [])
    logger.info(f"Found {len(chain)} SPXW contracts")

    if not chain:
        logger.error("No options chain data!")
        sys.exit(1)

    # Find strikes at 1 SD
    put_strikes = sorted([c.strike for c in chain if c.option_type == 'put' and c.strike < spx_price])
    call_strikes = sorted([c.strike for c in chain if c.option_type == 'call' and c.strike > spx_price])

    # Target 1 SD away
    put_short_target = spx_price - expected_move
    call_short_target = spx_price + expected_move

    put_short = min(put_strikes, key=lambda s: abs(s - put_short_target))
    call_short = min(call_strikes, key=lambda s: abs(s - call_short_target))
    put_long = put_short - SPREAD_WIDTH
    call_long = call_short + SPREAD_WIDTH

    logger.info(f"\n=== IRON CONDOR STRIKES ===")
    logger.info(f"Put Spread:  {put_long}/{put_short}P")
    logger.info(f"Call Spread: {call_short}/{call_long}C")

    # Get credits
    def get_mid(opt_type, strike):
        for c in chain:
            if c.option_type == opt_type and c.strike == strike:
                return c.mid or ((c.bid or 0) + (c.ask or 0)) / 2
        return 0

    put_long_price = get_mid('put', put_long)
    put_short_price = get_mid('put', put_short)
    call_short_price = get_mid('call', call_short)
    call_long_price = get_mid('call', call_long)

    put_credit = put_short_price - put_long_price
    call_credit = call_short_price - call_long_price
    total_credit = put_credit + call_credit

    logger.info(f"\n=== PRICING ===")
    logger.info(f"Put Credit:   ${put_credit:.2f}")
    logger.info(f"Call Credit:  ${call_credit:.2f}")
    logger.info(f"Total Credit: ${total_credit:.2f}")

    max_loss = SPREAD_WIDTH - total_credit
    logger.info(f"Max Loss:     ${max_loss:.2f}")

    if total_credit < MIN_CREDIT:
        logger.warning(f"Credit ${total_credit:.2f} below minimum ${MIN_CREDIT}")

    # Calculate position size
    if args.contracts:
        contracts = args.contracts
    else:
        risk_budget = args.capital * RISK_PCT
        max_loss_per_contract = max_loss * 100
        contracts = max(1, int(risk_budget / max_loss_per_contract))

    logger.info(f"\n=== POSITION SIZE ===")
    logger.info(f"Capital: ${args.capital:,.2f}")
    logger.info(f"Risk %: {RISK_PCT * 100}%")
    logger.info(f"Contracts: {contracts}")
    logger.info(f"Total Premium: ${total_credit * 100 * contracts:,.2f}")
    logger.info(f"Max Risk: ${max_loss * 100 * contracts:,.2f}")

    if args.dry_run:
        logger.info("\n*** DRY RUN - Not executing ***")
        return

    # Execute trade
    logger.info(f"\n=== EXECUTING TRADE ===")

    result = tradier.place_iron_condor(
        symbol='SPXW',
        expiration=exp,
        put_long=put_long,
        put_short=put_short,
        call_short=call_short,
        call_long=call_long,
        quantity=contracts,
        limit_price=total_credit
    )

    logger.info(f"Result: {result}")

    # Check result
    if 'errors' in result:
        logger.error(f"ORDER FAILED: {result['errors']}")
        return

    order_info = result.get('order', {})
    if order_info:
        logger.info(f"\n✅ ORDER PLACED!")
        logger.info(f"   Order ID: {order_info.get('id')}")
        logger.info(f"   Status: {order_info.get('status')}")
    else:
        logger.warning(f"No order info returned: {result}")


if __name__ == '__main__':
    main()
