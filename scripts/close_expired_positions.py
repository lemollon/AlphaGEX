#!/usr/bin/env python3
"""
Close Expired ATHENA Positions

This script finds all ATHENA positions that have expired (expiration <= today)
but are still marked as 'open', calculates their P&L, and updates:
1. Position status to 'expired'
2. Realized P&L based on closing price
3. Daily performance table (equity curve)

Usage:
    python scripts/close_expired_positions.py [--dry-run] [--closing-price PRICE]

Options:
    --dry-run         Show what would be done without making changes
    --closing-price   Override the closing price (for testing)
"""

import argparse
import sys
import os
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection


class SpreadType(Enum):
    BULL_CALL_SPREAD = "BULL_CALL_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"


@dataclass
class ExpiredPosition:
    """Represents an expired position that needs to be closed."""
    position_id: str
    spread_type: str
    ticker: str
    long_strike: float
    short_strike: float
    expiration: str
    entry_price: float
    contracts: int
    max_profit: float
    max_loss: float
    spot_at_entry: float
    created_at: datetime


def get_expired_positions() -> List[ExpiredPosition]:
    """Find all positions with status='open' and expiration <= today."""
    today = date.today().strftime('%Y-%m-%d')
    conn = get_connection()
    c = conn.cursor()

    c.execute('''
        SELECT
            position_id, spread_type, ticker, long_strike, short_strike,
            expiration, entry_price, contracts, max_profit, max_loss,
            spot_at_entry, created_at
        FROM apache_positions
        WHERE status = 'open' AND expiration <= %s
        ORDER BY expiration ASC
    ''', (today,))

    rows = c.fetchall()
    conn.close()

    positions = []
    for row in rows:
        positions.append(ExpiredPosition(
            position_id=row[0],
            spread_type=row[1],
            ticker=row[2],
            long_strike=float(row[3]) if row[3] else 0,
            short_strike=float(row[4]) if row[4] else 0,
            expiration=str(row[5]) if row[5] else '',
            entry_price=float(row[6]) if row[6] else 0,
            contracts=int(row[7]) if row[7] else 1,
            max_profit=float(row[8]) if row[8] else 0,
            max_loss=float(row[9]) if row[9] else 0,
            spot_at_entry=float(row[10]) if row[10] else 0,
            created_at=row[11]
        ))

    return positions


def get_closing_price(ticker: str, for_date: str = None) -> Optional[float]:
    """
    Get the closing price for a ticker on a specific date.

    For today, tries to get current price.
    For past dates, looks up historical data.
    """
    today = date.today().strftime('%Y-%m-%d')

    # Try Tradier API for current/recent price
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        tradier = TradierDataFetcher()

        if for_date is None or for_date >= today:
            # Get current price
            quote = tradier.get_quote(ticker)
            if quote:
                price = quote.get('close') or quote.get('last')
                if price and price > 0:
                    return float(price)
        else:
            # Get historical price
            history = tradier.get_history(ticker, start=for_date, end=for_date)
            if history and len(history) > 0:
                price = history[0].get('close')
                if price and price > 0:
                    return float(price)
    except Exception as e:
        print(f"  Warning: Tradier API error: {e}")

    # Try unified data provider
    try:
        from data.unified_data_provider import get_price
        price = get_price(ticker)
        if price and price > 0:
            return float(price)
    except Exception:
        pass

    # Try database historical prices
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''
            SELECT close_price FROM daily_prices
            WHERE symbol = %s AND trade_date = %s
            LIMIT 1
        ''', (ticker, for_date or today))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return float(row[0])
    except Exception:
        pass

    return None


def determine_outcome(position: ExpiredPosition, closing_price: float) -> str:
    """
    Determine the outcome of an expired spread.

    For Bull Call Spread (buy low call, sell high call):
    - MAX_PROFIT: Price >= short strike (both ITM)
    - PARTIAL: Price between strikes
    - MAX_LOSS: Price <= long strike (both OTM)

    For Bear Call Spread (sell low call, buy high call):
    - MAX_PROFIT: Price <= short strike (both OTM)
    - PARTIAL: Price between strikes
    - MAX_LOSS: Price >= long strike (both ITM)
    """
    if position.spread_type == SpreadType.BULL_CALL_SPREAD.value:
        if closing_price >= position.short_strike:
            return "MAX_PROFIT"
        elif closing_price <= position.long_strike:
            return "MAX_LOSS"
        else:
            return "PARTIAL_PROFIT"
    else:  # BEAR_CALL_SPREAD
        if closing_price <= position.short_strike:
            return "MAX_PROFIT"
        elif closing_price >= position.long_strike:
            return "MAX_LOSS"
        else:
            return "PARTIAL_LOSS"


def calculate_pnl(position: ExpiredPosition, outcome: str, closing_price: float) -> float:
    """
    Calculate realized P&L at expiration for a spread.

    For Bull Call Spread (debit spread):
    - Entry: Pay debit (entry_price > 0)
    - MAX_PROFIT: Spread worth spread_width, P&L = (spread_width - entry_price) * 100 * contracts
    - MAX_LOSS: Spread worth 0, P&L = -entry_price * 100 * contracts
    - PARTIAL: Spread worth (closing_price - long_strike)

    For Bear Call Spread (credit spread):
    - Entry: Receive credit (entry_price < 0)
    - MAX_PROFIT: Both OTM, keep full credit
    - MAX_LOSS: Both ITM, lose spread_width - credit
    """
    contracts = position.contracts
    spread_width = abs(position.short_strike - position.long_strike)

    if position.spread_type == SpreadType.BULL_CALL_SPREAD.value:
        # Debit spread
        debit_paid = position.entry_price * 100 * contracts

        if outcome == "MAX_PROFIT":
            spread_value = spread_width * 100 * contracts
            return spread_value - debit_paid
        elif outcome == "MAX_LOSS":
            return -debit_paid
        else:  # PARTIAL_PROFIT
            intrinsic = closing_price - position.long_strike
            spread_value = intrinsic * 100 * contracts
            return spread_value - debit_paid

    else:  # BEAR_CALL_SPREAD (credit spread)
        credit_received = abs(position.entry_price) * 100 * contracts

        if outcome == "MAX_PROFIT":
            return credit_received
        elif outcome == "MAX_LOSS":
            max_loss = spread_width * 100 * contracts
            return credit_received - max_loss
        else:  # PARTIAL_LOSS
            intrinsic = closing_price - position.short_strike
            settlement_cost = intrinsic * 100 * contracts
            return credit_received - settlement_cost


def update_position_status(position: ExpiredPosition, outcome: str,
                          closing_price: float, realized_pnl: float,
                          dry_run: bool = False) -> bool:
    """Update position status to 'expired' with realized P&L."""
    if dry_run:
        return True

    try:
        conn = get_connection()
        c = conn.cursor()

        c.execute('''
            UPDATE apache_positions
            SET status = 'expired',
                exit_price = %s,
                exit_time = NOW(),
                exit_reason = %s,
                realized_pnl = %s
            WHERE position_id = %s
        ''', (
            closing_price,
            f"EXPIRED_{outcome}",
            realized_pnl,
            position.position_id
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  Error updating position {position.position_id}: {e}")
        return False


def update_daily_performance(position: ExpiredPosition, realized_pnl: float,
                            ending_capital: float, dry_run: bool = False) -> bool:
    """Update daily performance table with the closed position."""
    if dry_run:
        return True

    try:
        conn = get_connection()
        c = conn.cursor()

        today = date.today().strftime('%Y-%m-%d')
        is_win = realized_pnl > 0
        is_bullish = position.spread_type == SpreadType.BULL_CALL_SPREAD.value

        c.execute('''
            INSERT INTO apache_performance (
                trade_date, trades_executed, trades_won, trades_lost,
                gross_pnl, net_pnl, starting_capital, ending_capital,
                bullish_trades, bearish_trades
            ) VALUES (
                %s, 1, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (trade_date) DO UPDATE SET
                trades_executed = apache_performance.trades_executed + 1,
                trades_won = apache_performance.trades_won + EXCLUDED.trades_won,
                trades_lost = apache_performance.trades_lost + EXCLUDED.trades_lost,
                gross_pnl = apache_performance.gross_pnl + EXCLUDED.gross_pnl,
                net_pnl = apache_performance.net_pnl + EXCLUDED.net_pnl,
                ending_capital = EXCLUDED.ending_capital,
                bullish_trades = apache_performance.bullish_trades + EXCLUDED.bullish_trades,
                bearish_trades = apache_performance.bearish_trades + EXCLUDED.bearish_trades,
                win_rate = CASE
                    WHEN (apache_performance.trades_executed + 1) > 0
                    THEN (apache_performance.trades_won + EXCLUDED.trades_won)::float / (apache_performance.trades_executed + 1)
                    ELSE 0
                END
        ''', (
            today,
            1 if is_win else 0,
            0 if is_win else 1,
            realized_pnl,
            realized_pnl,
            ending_capital - realized_pnl,  # starting capital
            ending_capital,
            1 if is_bullish else 0,
            0 if is_bullish else 1
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  Error updating daily performance: {e}")
        return False


def get_current_capital() -> float:
    """Get current capital from the latest performance record or config."""
    try:
        conn = get_connection()
        c = conn.cursor()

        # Try to get from latest performance record
        c.execute('''
            SELECT ending_capital FROM apache_performance
            ORDER BY trade_date DESC LIMIT 1
        ''')
        row = c.fetchone()
        if row and row[0]:
            conn.close()
            return float(row[0])

        # Default starting capital
        conn.close()
        return 25000.0
    except Exception:
        return 25000.0


def main():
    parser = argparse.ArgumentParser(description='Close expired ATHENA positions')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be done without making changes')
    parser.add_argument('--closing-price', type=float,
                       help='Override closing price (for testing)')
    args = parser.parse_args()

    print("=" * 80)
    print("CLOSE EXPIRED ATHENA POSITIONS")
    print("=" * 80)

    if args.dry_run:
        print("** DRY RUN MODE - No changes will be made **\n")

    # Find expired positions
    print("Searching for expired positions with status='open'...")
    positions = get_expired_positions()

    if not positions:
        print("No expired open positions found.")
        print("=" * 80)
        return

    print(f"Found {len(positions)} expired position(s) to process:\n")

    # Get current capital for equity tracking
    current_capital = get_current_capital()
    print(f"Starting capital: ${current_capital:,.2f}\n")

    total_pnl = 0.0
    winners = 0
    losers = 0
    processed = 0
    errors = 0

    for position in positions:
        print(f"Processing: {position.position_id}")
        print(f"  Type: {position.spread_type}")
        print(f"  Ticker: {position.ticker}")
        print(f"  Strikes: {position.long_strike}/{position.short_strike}")
        print(f"  Expiration: {position.expiration}")
        print(f"  Entry Price: ${position.entry_price:.2f}")
        print(f"  Contracts: {position.contracts}")

        # Get closing price
        if args.closing_price:
            closing_price = args.closing_price
            print(f"  Closing Price: ${closing_price:.2f} (override)")
        else:
            closing_price = get_closing_price(position.ticker, position.expiration)
            if closing_price is None:
                print(f"  ERROR: Could not get closing price for {position.ticker} on {position.expiration}")
                errors += 1
                continue
            print(f"  Closing Price: ${closing_price:.2f}")

        # Determine outcome
        outcome = determine_outcome(position, closing_price)
        print(f"  Outcome: {outcome}")

        # Calculate P&L
        realized_pnl = calculate_pnl(position, outcome, closing_price)
        print(f"  Realized P&L: ${realized_pnl:+,.2f}")

        # Update capital
        current_capital += realized_pnl
        print(f"  New Capital: ${current_capital:,.2f}")

        # Update database
        if update_position_status(position, outcome, closing_price, realized_pnl, args.dry_run):
            if update_daily_performance(position, realized_pnl, current_capital, args.dry_run):
                processed += 1
                total_pnl += realized_pnl
                if realized_pnl > 0:
                    winners += 1
                else:
                    losers += 1
                print(f"  Status: {'Would update' if args.dry_run else 'UPDATED'}")
            else:
                errors += 1
        else:
            errors += 1

        print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Processed: {processed} position(s)")
    print(f"Winners: {winners}")
    print(f"Losers: {losers}")
    print(f"Errors: {errors}")
    print(f"Total P&L: ${total_pnl:+,.2f}")
    print(f"Final Capital: ${current_capital:,.2f}")

    if args.dry_run:
        print("\n** DRY RUN - No changes were made **")
        print("Run without --dry-run to apply changes.")
    else:
        print("\nPositions closed and equity curve updated.")

    print("=" * 80)


if __name__ == '__main__':
    main()
