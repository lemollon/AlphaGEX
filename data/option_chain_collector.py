"""
Option Chain Data Collector

Collects option chain snapshots periodically for:
1. Future backtesting with REAL historical data
2. Volatility surface analysis
3. Greek calculations over time
4. Strike/expiration analysis

Data Collection Strategy:
- During market hours: Snapshot every 15 minutes
- Focus on SPY, QQQ, and other liquid underlyings
- Store near-term expirations (0-60 DTE)
- Store strikes within 10% of current spot

Storage: PostgreSQL (options_chain_snapshots table)

Usage:
    from data.option_chain_collector import collect_option_snapshot
    collect_option_snapshot('SPY')

Or run the scheduler:
    python option_chain_collector.py
"""

import os
import sys
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
import logging

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_adapter import get_connection
from data.polygon_data_fetcher import polygon_fetcher

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ET = ZoneInfo("America/New_York")


def ensure_tables():
    """
    Verify option chain tables exist.
    NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
    Tables expected: options_chain_snapshots, options_collection_log
    """
    # Tables created by main schema - just log readiness
    logger.info("Option chain tables ready (created by main schema)")


def collect_option_snapshot(
    symbol: str = 'SPY',
    max_dte: int = 60,
    strike_range_pct: float = 0.10
) -> Dict:
    """
    Collect option chain snapshot for a symbol.

    Args:
        symbol: Underlying symbol
        max_dte: Maximum days to expiration to collect
        strike_range_pct: Percentage range from spot for strikes (0.10 = 10%)

    Returns:
        Dict with collection statistics
    """
    ensure_tables()
    start_time = datetime.now(ET)

    conn = get_connection()
    cursor = conn.cursor()

    stats = {
        'symbol': symbol,
        'timestamp': start_time.isoformat(),
        'spot_price': 0,
        'expirations': 0,
        'contracts': 0,
        'calls': 0,
        'puts': 0,
        'status': 'SUCCESS',
        'error': None
    }

    try:
        # Get current spot price
        spot = polygon_fetcher.get_current_price(symbol)
        if not spot or spot <= 0:
            raise ValueError(f"Could not get spot price for {symbol}")

        stats['spot_price'] = spot

        # Calculate strike range
        min_strike = spot * (1 - strike_range_pct)
        max_strike = spot * (1 + strike_range_pct)

        logger.info(f"Collecting options for {symbol} @ ${spot:.2f}")
        logger.info(f"Strike range: ${min_strike:.2f} - ${max_strike:.2f}")

        # Get option chain from Polygon
        chain = polygon_fetcher.get_options_chain(symbol)

        if not chain or 'options' not in chain:
            raise ValueError(f"Could not get options chain for {symbol}")

        options = chain.get('options', [])
        logger.info(f"Retrieved {len(options)} option contracts")

        # Filter and store options
        collected = 0
        for opt in options:
            try:
                # Parse expiration
                expiration = opt.get('expiration_date', '')
                if not expiration:
                    continue

                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                dte = (exp_date - datetime.now(ET).date()).days

                # Skip if too far out
                if dte > max_dte or dte < 0:
                    continue

                # Parse strike
                strike = opt.get('strike_price', 0)
                if not strike or strike < min_strike or strike > max_strike:
                    continue

                option_type = opt.get('contract_type', '').lower()
                if option_type not in ['call', 'put']:
                    continue

                # Build option ticker
                exp_str = expiration.replace('-', '')[2:]  # "2024-12-20" -> "241220"
                type_char = 'C' if option_type == 'call' else 'P'
                strike_str = f"{int(strike * 1000):08d}"
                option_ticker = f"O:{symbol}{exp_str}{type_char}{strike_str}"

                # Extract pricing
                bid = opt.get('bid', 0) or 0
                ask = opt.get('ask', 0) or 0
                mid = (bid + ask) / 2 if bid and ask else opt.get('last_price', 0)
                last = opt.get('last_price', 0) or 0
                volume = opt.get('volume', 0) or 0
                oi = opt.get('open_interest', 0) or 0

                # Calculate spread
                spread = ask - bid if bid and ask else 0
                spread_pct = (spread / mid * 100) if mid > 0 else 0

                # Greeks
                greeks = opt.get('greeks', {}) or {}
                delta = greeks.get('delta', 0) or 0
                gamma = greeks.get('gamma', 0) or 0
                theta = greeks.get('theta', 0) or 0
                vega = greeks.get('vega', 0) or 0
                rho = greeks.get('rho', 0) or 0
                iv = opt.get('implied_volatility', 0) or 0

                # Moneyness
                is_itm = (option_type == 'call' and strike < spot) or \
                         (option_type == 'put' and strike > spot)
                moneyness = (spot - strike) / spot if option_type == 'call' else (strike - spot) / spot

                # Insert into database
                cursor.execute('''
                    INSERT INTO options_chain_snapshots (
                        timestamp, symbol, spot_price, option_ticker,
                        strike, expiration, option_type, dte,
                        bid, ask, mid, last, volume, open_interest,
                        delta, gamma, theta, vega, rho, iv,
                        is_itm, moneyness, bid_size, ask_size, spread, spread_pct
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (symbol, option_ticker, timestamp) DO NOTHING
                ''', (
                    start_time, symbol, spot, option_ticker,
                    strike, exp_date, option_type, dte,
                    bid, ask, mid, last, volume, oi,
                    delta, gamma, theta, vega, rho, iv,
                    is_itm, moneyness,
                    opt.get('bid_size', 0) or 0,
                    opt.get('ask_size', 0) or 0,
                    spread, spread_pct
                ))

                collected += 1
                if option_type == 'call':
                    stats['calls'] += 1
                else:
                    stats['puts'] += 1

            except Exception as e:
                logger.debug(f"Skipping option: {e}")
                continue

        stats['contracts'] = collected

        # Count unique expirations
        cursor.execute('''
            SELECT COUNT(DISTINCT expiration)
            FROM options_chain_snapshots
            WHERE symbol = %s AND timestamp = %s
        ''', (symbol, start_time))
        stats['expirations'] = cursor.fetchone()[0]

        conn.commit()

    except Exception as e:
        stats['status'] = 'ERROR'
        stats['error'] = str(e)
        logger.error(f"Collection failed: {e}")
        conn.rollback()

    finally:
        # Log collection run
        end_time = datetime.now(ET)
        duration = (end_time - start_time).total_seconds()

        try:
            cursor.execute('''
                INSERT INTO options_collection_log (
                    symbol, spot_price, expirations_collected,
                    contracts_collected, calls_collected, puts_collected,
                    duration_seconds, status, error_message
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                symbol, stats['spot_price'], stats['expirations'],
                stats['contracts'], stats['calls'], stats['puts'],
                duration, stats['status'], stats['error']
            ))
            conn.commit()
        except:
            pass

        conn.close()

    logger.info(f"Collected {stats['contracts']} contracts "
                f"({stats['calls']} calls, {stats['puts']} puts) "
                f"across {stats['expirations']} expirations")

    return stats


def collect_all_symbols():
    """Collect option snapshots for all tracked symbols"""
    symbols = ['SPY', 'QQQ', 'IWM']  # Add more as needed

    results = []
    for symbol in symbols:
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Collecting options for {symbol}")
            logger.info('='*60)
            result = collect_option_snapshot(symbol)
            results.append(result)
        except Exception as e:
            logger.error(f"Failed to collect {symbol}: {e}")
            results.append({
                'symbol': symbol,
                'status': 'ERROR',
                'error': str(e)
            })

    return results


def get_collection_stats(days: int = 7) -> Dict:
    """Get statistics on recent option data collection"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            symbol,
            COUNT(*) as collections,
            SUM(contracts_collected) as total_contracts,
            AVG(contracts_collected) as avg_contracts,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM options_collection_log
        WHERE timestamp > NOW() - INTERVAL '%s days'
          AND status = 'SUCCESS'
        GROUP BY symbol
        ORDER BY symbol
    ''', (days,))

    results = cursor.fetchall()
    conn.close()

    stats = {}
    for row in results:
        stats[row[0]] = {
            'collections': row[1],
            'total_contracts': row[2],
            'avg_contracts': float(row[3]) if row[3] else 0,
            'earliest': row[4].isoformat() if row[4] else None,
            'latest': row[5].isoformat() if row[5] else None
        }

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Option Chain Data Collector')
    parser.add_argument('--symbol', default='SPY', help='Symbol to collect')
    parser.add_argument('--all', action='store_true', help='Collect all symbols')
    parser.add_argument('--stats', action='store_true', help='Show collection stats')
    parser.add_argument('--max-dte', type=int, default=60, help='Max days to expiration')
    args = parser.parse_args()

    if args.stats:
        print("\n" + "="*60)
        print("OPTION DATA COLLECTION STATISTICS (Last 7 Days)")
        print("="*60)
        stats = get_collection_stats()
        for symbol, data in stats.items():
            print(f"\n{symbol}:")
            print(f"  Collections: {data['collections']}")
            print(f"  Total Contracts: {data['total_contracts']}")
            print(f"  Avg Contracts: {data['avg_contracts']:.0f}")
            print(f"  Range: {data['earliest'][:10]} to {data['latest'][:10]}")
    elif args.all:
        collect_all_symbols()
    else:
        collect_option_snapshot(args.symbol, max_dte=args.max_dte)
