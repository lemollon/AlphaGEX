#!/usr/bin/env python3
"""
Manual FORTRESS Iron Condor Trade Execution Script
===============================================

Run this in Render shell to manually execute an Iron Condor trade.

Usage:
    python scripts/manual_ares_trade.py
    python scripts/manual_ares_trade.py --dry-run  # Preview without executing
    python scripts/manual_ares_trade.py --contracts 2  # Override contract count
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_tradier_client():
    """Initialize Tradier client"""
    from data.tradier_data_fetcher import TradierDataFetcher

    api_key = os.getenv('TRADIER_API_KEY')
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    sandbox = os.getenv('TRADIER_SANDBOX', 'false').lower() == 'true'

    if not api_key or not account_id:
        logger.error("TRADIER_API_KEY or TRADIER_ACCOUNT_ID not set!")
        sys.exit(1)

    logger.info(f"Mode: {'SANDBOX' if sandbox else 'PRODUCTION'}")
    logger.info(f"Account: {account_id}")

    return TradierDataFetcher(sandbox=sandbox)


def get_account_info(tradier):
    """Get account balances and positions"""
    import requests

    url = f"{tradier.base_url}/accounts/{tradier.account_id}/balances"
    response = requests.get(url, headers=tradier.headers)
    balances = response.json()

    logger.info("=" * 60)
    logger.info("ACCOUNT BALANCES")
    logger.info("=" * 60)

    bal = balances.get('balances', {})
    total_equity = bal.get('total_equity', 0)
    option_bp = bal.get('option_buying_power', 0)
    stock_bp = bal.get('stock_buying_power', 0)

    logger.info(f"Total Equity:        ${total_equity:,.2f}")
    logger.info(f"Option Buying Power: ${option_bp:,.2f}")
    logger.info(f"Stock Buying Power:  ${stock_bp:,.2f}")

    return bal


def get_market_data(tradier, ticker):
    """Get current price and VIX"""
    logger.info("=" * 60)
    logger.info("MARKET DATA")
    logger.info("=" * 60)

    # Get underlying price
    quote = tradier.get_quote(ticker)
    underlying_price = quote.get('last', 0) or quote.get('close', 0)
    logger.info(f"{ticker} Price: ${underlying_price:.2f}")

    # Get VIX - use $VIX.X for Tradier (correct symbol format)
    vix_quote = tradier.get_quote('$VIX.X')
    vix = vix_quote.get('last', 0) if vix_quote else 0
    if not vix:
        vix = 20.0  # Fallback
    logger.info(f"VIX: {vix:.2f}")

    # Calculate expected move (1 SD)
    # Daily SD = Price * VIX / sqrt(252) / 100
    import math
    expected_move = underlying_price * vix / math.sqrt(252) / 100
    logger.info(f"Expected Move (1 SD): ${expected_move:.2f}")

    return {
        'underlying_price': underlying_price,
        'vix': vix,
        'expected_move': expected_move
    }


def get_expiration(tradier, ticker):
    """Get next valid expiration (0-1 DTE)"""
    tz = ZoneInfo('America/Chicago')
    today = datetime.now(tz).date()

    # Get available expirations
    expirations = tradier.get_option_expirations(ticker)
    logger.info(f"Available expirations: {expirations[:5]}...")  # Show first 5

    # Find today's or next day's expiration
    for exp in expirations:
        exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
        days_to_exp = (exp_date - today).days
        if 0 <= days_to_exp <= 1:
            logger.info(f"Selected expiration: {exp} ({days_to_exp} DTE)")
            return exp

    # Fallback to first available
    if expirations:
        logger.warning(f"No 0-1 DTE found, using: {expirations[0]}")
        return expirations[0]

    return None


def find_iron_condor_strikes(tradier, ticker, price, expected_move, expiration, spread_width):
    """Find Iron Condor strikes at ~1 standard deviation"""
    logger.info("=" * 60)
    logger.info("FINDING IRON CONDOR STRIKES")
    logger.info("=" * 60)

    # Target strikes at 1 SD
    put_short_target = price - expected_move
    call_short_target = price + expected_move

    logger.info(f"Target put short strike: ${put_short_target:.2f}")
    logger.info(f"Target call short strike: ${call_short_target:.2f}")

    # Get options chain
    chain = tradier.get_option_chain(ticker, expiration, greeks=True)
    if not chain:
        logger.error("No options chain data!")
        return None

    puts = [c for c in chain if c.get('option_type') == 'put']
    calls = [c for c in chain if c.get('option_type') == 'call']

    logger.info(f"Found {len(puts)} puts and {len(calls)} calls")

    # Find put short strike (closest to target, below price)
    put_strikes = sorted(set(c.get('strike') for c in puts if c.get('strike') < price))
    put_short = min(put_strikes, key=lambda s: abs(s - put_short_target), default=None)

    if not put_short:
        logger.error("No suitable put strikes found!")
        return None

    put_long = put_short - spread_width

    # Find call short strike (closest to target, above price)
    call_strikes = sorted(set(c.get('strike') for c in calls if c.get('strike') > price))
    call_short = min(call_strikes, key=lambda s: abs(s - call_short_target), default=None)

    if not call_short:
        logger.error("No suitable call strikes found!")
        return None

    call_long = call_short + spread_width

    logger.info(f"Put Spread:  ${put_long} / ${put_short}")
    logger.info(f"Call Spread: ${call_short} / ${call_long}")

    # Get credits
    def get_mid_price(option_type, strike):
        for c in chain:
            if c.get('option_type') == option_type and c.get('strike') == strike:
                bid = c.get('bid', 0) or 0
                ask = c.get('ask', 0) or 0
                return (bid + ask) / 2
        return 0

    put_long_price = get_mid_price('put', put_long)
    put_short_price = get_mid_price('put', put_short)
    call_short_price = get_mid_price('call', call_short)
    call_long_price = get_mid_price('call', call_long)

    put_credit = put_short_price - put_long_price
    call_credit = call_short_price - call_long_price
    total_credit = put_credit + call_credit

    logger.info(f"Put Credit:   ${put_credit:.2f}")
    logger.info(f"Call Credit:  ${call_credit:.2f}")
    logger.info(f"Total Credit: ${total_credit:.2f}")

    max_loss = spread_width - total_credit
    logger.info(f"Max Loss:     ${max_loss:.2f} per contract")

    return {
        'put_long_strike': put_long,
        'put_short_strike': put_short,
        'call_short_strike': call_short,
        'call_long_strike': call_long,
        'put_credit': put_credit,
        'call_credit': call_credit,
        'total_credit': total_credit,
        'max_loss': max_loss
    }


def execute_trade(tradier, ticker, expiration, strikes, contracts, dry_run=False):
    """Execute the Iron Condor trade"""
    logger.info("=" * 60)
    logger.info("EXECUTING TRADE")
    logger.info("=" * 60)

    logger.info(f"Ticker: {ticker}")
    logger.info(f"Expiration: {expiration}")
    logger.info(f"Contracts: {contracts}")
    logger.info(f"Total Premium: ${strikes['total_credit'] * 100 * contracts:,.2f}")
    logger.info(f"Max Risk: ${strikes['max_loss'] * 100 * contracts:,.2f}")

    if dry_run:
        logger.info("DRY RUN - Not executing trade")
        return {'status': 'dry_run'}

    logger.info("Submitting order to Tradier...")

    result = tradier.place_iron_condor(
        symbol=ticker,
        expiration=expiration,
        put_long=strikes['put_long_strike'],
        put_short=strikes['put_short_strike'],
        call_short=strikes['call_short_strike'],
        call_long=strikes['call_long_strike'],
        quantity=contracts,
        limit_price=strikes['total_credit']
    )

    logger.info(f"Tradier Response: {result}")

    # Check for errors
    if 'errors' in result:
        error_msg = result.get('errors', {}).get('error', 'Unknown error')
        logger.error(f"ORDER FAILED: {error_msg}")
        return result

    order_info = result.get('order', {})
    if order_info:
        order_id = order_info.get('id')
        status = order_info.get('status')
        logger.info(f"ORDER PLACED SUCCESSFULLY!")
        logger.info(f"  Order ID: {order_id}")
        logger.info(f"  Status: {status}")
    else:
        logger.warning(f"No order info in response: {result}")

    return result


def main():
    parser = argparse.ArgumentParser(description='Manual FORTRESS Iron Condor Trade')
    parser.add_argument('--dry-run', action='store_true', help='Preview without executing')
    parser.add_argument('--contracts', type=int, default=None, help='Override contract count')
    parser.add_argument('--ticker', type=str, default=None, help='Override ticker (default: SPY for sandbox, SPX for prod)')
    parser.add_argument('--spread-width', type=float, default=None, help='Override spread width')
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("MANUAL FORTRESS IRON CONDOR TRADE")
    logger.info("=" * 60)

    # Initialize Tradier
    tradier = get_tradier_client()

    # Determine ticker and spread width based on mode
    is_sandbox = tradier.sandbox
    ticker = args.ticker or ('SPY' if is_sandbox else 'SPX')
    spread_width = args.spread_width or (2.0 if ticker == 'SPY' else 10.0)

    logger.info(f"Trading: {ticker} with ${spread_width} spread width")

    # Get account info
    balances = get_account_info(tradier)
    option_bp = balances.get('option_buying_power', 0)

    if option_bp <= 0:
        logger.error("NO BUYING POWER! Cannot trade.")
        logger.error("Reset sandbox at: https://dash.tradier.com/")
        sys.exit(1)

    # Get market data
    market_data = get_market_data(tradier, ticker)

    if market_data['underlying_price'] <= 0:
        logger.error("Could not get market price!")
        sys.exit(1)

    # Get expiration
    expiration = get_expiration(tradier, ticker)
    if not expiration:
        logger.error("No valid expiration found!")
        sys.exit(1)

    # Find strikes
    strikes = find_iron_condor_strikes(
        tradier, ticker,
        market_data['underlying_price'],
        market_data['expected_move'],
        expiration,
        spread_width
    )

    if not strikes:
        logger.error("Could not find suitable strikes!")
        sys.exit(1)

    # Calculate contracts
    if args.contracts:
        contracts = args.contracts
    else:
        # 10% of buying power
        risk_pct = 0.10
        risk_budget = option_bp * risk_pct
        max_loss_per_contract = strikes['max_loss'] * 100  # Per contract in dollars
        contracts = max(1, int(risk_budget / max_loss_per_contract))

    logger.info(f"Calculated contracts: {contracts}")

    # Execute
    result = execute_trade(tradier, ticker, expiration, strikes, contracts, args.dry_run)

    logger.info("=" * 60)
    logger.info("DONE")
    logger.info("=" * 60)

    return result


if __name__ == '__main__':
    main()
