"""
Historical Open Interest (OI) Snapshot Job

This script captures daily snapshots of open interest for all actively traded options.
Used to track OI accumulation rates for forward gamma magnet detection.

Usage:
    python historical_oi_snapshot_job.py                    # Snapshot all configured symbols
    python historical_oi_snapshot_job.py SPY TSLA           # Snapshot specific symbols
    python historical_oi_snapshot_job.py --test             # Test mode (no database write)

Schedule with cron:
    # Run daily at 4:30 PM ET (after market close)
    30 16 * * 1-5 cd /home/user/AlphaGEX && python historical_oi_snapshot_job.py >> logs/oi_snapshot.log 2>&1

Author: AlphaGEX Team
Date: 2025-11-14
"""

import os
import sys
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yfinance as yf
from config_and_database import DB_PATH

# Default symbols to track
DEFAULT_SYMBOLS = [
    'SPY',   # S&P 500 ETF
    'QQQ',   # Nasdaq 100 ETF
    'IWM',   # Russell 2000 ETF
    'AAPL',  # Apple
    'MSFT',  # Microsoft
    'NVDA',  # NVIDIA
    'TSLA',  # Tesla
    'AMZN',  # Amazon
    'GOOGL', # Google
    'META',  # Meta
]


class OISnapshotJob:
    """Captures daily Open Interest snapshots"""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.snapshot_date = datetime.now().date()
        self.results = []

    def snapshot_symbol(self, symbol: str) -> Dict:
        """
        Capture OI snapshot for a single symbol

        Returns:
            {
                'symbol': str,
                'expirations_processed': int,
                'strikes_processed': int,
                'success': bool,
                'error': str or None
            }
        """
        print(f"\n{'='*60}")
        print(f"📸 Snapshotting {symbol} - {self.snapshot_date}")
        print(f"{'='*60}")

        result = {
            'symbol': symbol,
            'expirations_processed': 0,
            'strikes_processed': 0,
            'success': False,
            'error': None
        }

        try:
            ticker = yf.Ticker(symbol)

            # Get all available expiration dates
            expirations = ticker.options
            if not expirations:
                result['error'] = "No expirations available"
                print(f"   ⚠️  No options data available for {symbol}")
                return result

            print(f"   Found {len(expirations)} expirations")

            # Focus on next 60 days (near-term magnets matter most)
            cutoff_date = (datetime.now() + timedelta(days=60)).date()
            relevant_expirations = [
                exp for exp in expirations
                if datetime.strptime(exp, '%Y-%m-%d').date() <= cutoff_date
            ]

            print(f"   Processing {len(relevant_expirations)} near-term expirations (next 60 days)")

            for expiration in relevant_expirations:
                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                dte = (exp_date - self.snapshot_date).days

                print(f"   • {expiration} ({dte} DTE)...", end='')

                try:
                    # Get options chain
                    chain = ticker.option_chain(expiration)

                    calls_processed = 0
                    puts_processed = 0

                    # Process calls
                    for _, row in chain.calls.iterrows():
                        strike = float(row['strike'])
                        oi = int(row.get('openInterest', 0))
                        volume = int(row.get('volume', 0))

                        if oi > 0:  # Only save strikes with OI
                            self._save_snapshot(
                                symbol=symbol,
                                strike=strike,
                                expiration_date=expiration,
                                call_oi=oi,
                                put_oi=0,
                                call_volume=volume,
                                put_volume=0
                            )
                            calls_processed += 1

                    # Process puts
                    for _, row in chain.puts.iterrows():
                        strike = float(row['strike'])
                        oi = int(row.get('openInterest', 0))
                        volume = int(row.get('volume', 0))

                        if oi > 0:
                            # Update existing record or create new one
                            self._update_snapshot(
                                symbol=symbol,
                                strike=strike,
                                expiration_date=expiration,
                                put_oi=oi,
                                put_volume=volume
                            )
                            puts_processed += 1

                    print(f" ✅ {calls_processed} calls, {puts_processed} puts")

                    result['expirations_processed'] += 1
                    result['strikes_processed'] += calls_processed + puts_processed

                except Exception as e:
                    print(f" ❌ Error: {e}")

            result['success'] = True
            print(f"\n   ✅ {symbol} complete: {result['expirations_processed']} expirations, {result['strikes_processed']} strikes")

        except Exception as e:
            result['error'] = str(e)
            print(f"\n   ❌ Error snapshotting {symbol}: {e}")

        return result

    def _save_snapshot(self, symbol: str, strike: float, expiration_date: str,
                       call_oi: int, put_oi: int, call_volume: int = 0, put_volume: int = 0):
        """Save OI snapshot to database"""
        if self.test_mode:
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            c.execute('''
                INSERT INTO historical_open_interest
                (date, symbol, strike, expiration_date, call_oi, put_oi, call_volume, put_volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.snapshot_date.isoformat(),
                symbol,
                strike,
                expiration_date,
                call_oi,
                put_oi,
                call_volume,
                put_volume
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"      ⚠️  Database error: {e}")

    def _update_snapshot(self, symbol: str, strike: float, expiration_date: str,
                         put_oi: int, put_volume: int):
        """Update existing snapshot with put data"""
        if self.test_mode:
            return

        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()

            # Check if record exists
            c.execute('''
                SELECT id FROM historical_open_interest
                WHERE date = ? AND symbol = ? AND strike = ? AND expiration_date = ?
            ''', (self.snapshot_date.isoformat(), symbol, strike, expiration_date))

            if c.fetchone():
                # Update existing
                c.execute('''
                    UPDATE historical_open_interest
                    SET put_oi = ?, put_volume = ?
                    WHERE date = ? AND symbol = ? AND strike = ? AND expiration_date = ?
                ''', (put_oi, put_volume, self.snapshot_date.isoformat(), symbol, strike, expiration_date))
            else:
                # Insert new
                c.execute('''
                    INSERT INTO historical_open_interest
                    (date, symbol, strike, expiration_date, call_oi, put_oi, call_volume, put_volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (self.snapshot_date.isoformat(), symbol, strike, expiration_date, 0, put_oi, 0, put_volume))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"      ⚠️  Database update error: {e}")

    def run(self, symbols: List[str]) -> Dict:
        """
        Run snapshot job for all symbols

        Returns:
            {
                'snapshot_date': str,
                'symbols_processed': int,
                'total_strikes': int,
                'success': bool,
                'results': List[Dict]
            }
        """
        print(f"\n{'#'*80}")
        print(f"# HISTORICAL OPEN INTEREST SNAPSHOT JOB")
        print(f"# Date: {self.snapshot_date}")
        print(f"# Symbols: {len(symbols)}")
        print(f"# Test Mode: {'YES' if self.test_mode else 'NO'}")
        print(f"{'#'*80}\n")

        for symbol in symbols:
            result = self.snapshot_symbol(symbol)
            self.results.append(result)

        # Summary
        total_strikes = sum(r['strikes_processed'] for r in self.results)
        success_count = sum(1 for r in self.results if r['success'])

        print(f"\n{'='*80}")
        print(f"📊 SUMMARY")
        print(f"{'='*80}")
        print(f"   Date: {self.snapshot_date}")
        print(f"   Symbols processed: {success_count}/{len(symbols)}")
        print(f"   Total strikes captured: {total_strikes:,}")
        print(f"   Test mode: {'YES' if self.test_mode else 'NO'}")

        if not self.test_mode:
            print(f"   Database: {DB_PATH}")

        # Failed symbols
        failed = [r for r in self.results if not r['success']]
        if failed:
            print(f"\n   ⚠️  Failed symbols:")
            for r in failed:
                print(f"      - {r['symbol']}: {r['error']}")

        print(f"{'='*80}\n")

        return {
            'snapshot_date': self.snapshot_date.isoformat(),
            'symbols_processed': success_count,
            'total_strikes': total_strikes,
            'success': success_count == len(symbols),
            'results': self.results
        }


def calculate_oi_accumulation(symbol: str, strike: float, expiration: str, days_back: int = 5) -> Optional[Dict]:
    """
    Calculate OI accumulation rate for a specific option

    Args:
        symbol: Stock symbol
        strike: Strike price
        expiration: Expiration date (YYYY-MM-DD)
        days_back: Number of days to look back

    Returns:
        {
            'strike': float,
            'expiration': str,
            'oi_current': int,
            'oi_start': int,
            'oi_change': int,
            'oi_change_pct': float,
            'accumulation_rate': str,  # 'RAPID', 'MODERATE', 'SLOW', 'DECLINING'
            'days_tracked': int
        }
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Get OI history
        c.execute('''
            SELECT date, call_oi, put_oi
            FROM historical_open_interest
            WHERE symbol = ? AND strike = ? AND expiration_date = ?
            ORDER BY date DESC
            LIMIT ?
        ''', (symbol, strike, expiration, days_back + 1))

        rows = c.fetchall()
        conn.close()

        if len(rows) < 2:
            return None

        # Current OI
        current_date, current_call, current_put = rows[0]
        current_oi = current_call + current_put

        # Starting OI
        start_date, start_call, start_put = rows[-1]
        start_oi = start_call + start_put

        # Calculate change
        oi_change = current_oi - start_oi
        oi_change_pct = (oi_change / start_oi * 100) if start_oi > 0 else 0

        # Classify accumulation rate
        if oi_change_pct > 50:
            rate = 'RAPID'
        elif oi_change_pct > 20:
            rate = 'MODERATE'
        elif oi_change_pct > 0:
            rate = 'SLOW'
        else:
            rate = 'DECLINING'

        return {
            'strike': strike,
            'expiration': expiration,
            'oi_current': current_oi,
            'oi_start': start_oi,
            'oi_change': oi_change,
            'oi_change_pct': oi_change_pct,
            'accumulation_rate': rate,
            'days_tracked': len(rows)
        }

    except Exception as e:
        print(f"Error calculating OI accumulation: {e}")
        return None


def main():
    """Main entry point"""
    # Parse arguments
    test_mode = '--test' in sys.argv
    symbols = [arg for arg in sys.argv[1:] if not arg.startswith('--')]

    if not symbols:
        symbols = DEFAULT_SYMBOLS

    # Run job
    job = OISnapshotJob(test_mode=test_mode)
    summary = job.run(symbols)

    # Exit with status code
    sys.exit(0 if summary['success'] else 1)


if __name__ == "__main__":
    main()
