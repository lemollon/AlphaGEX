"""
Historical Open Interest (OI) Snapshot Job - POLYGON.IO VERSION

This script captures daily snapshots of open interest for all actively traded options.
Uses Polygon.io for REAL open interest data (no more synthetic/fake data!)

Usage:
    python historical_oi_snapshot_job.py                    # Snapshot all configured symbols
    python historical_oi_snapshot_job.py SPY TSLA           # Snapshot specific symbols
    python historical_oi_snapshot_job.py --test             # Test mode (no database write)

Schedule with cron:
    # Run daily at 4:30 PM ET (after market close)
    30 16 * * 1-5 cd /home/user/AlphaGEX && python historical_oi_snapshot_job.py >> logs/oi_snapshot.log 2>&1

Author: AlphaGEX Team
Date: 2025-11-24 (Updated to use Polygon.io)
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
from database_adapter import get_connection
from polygon_data_fetcher import polygon_fetcher

# Default symbols to track
DEFAULT_SYMBOLS = [
    'SPY',   # S&P 500 ETF (primary)
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
    """Captures daily Open Interest snapshots using Polygon.io"""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.snapshot_date = datetime.now().date()
        self.results = []

    def snapshot_symbol(self, symbol: str) -> Dict:
        """
        Capture OI snapshot for a single symbol using Polygon.io

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
        print(f"📸 Snapshotting {symbol} - {self.snapshot_date} (Polygon.io)")
        print(f"{'='*60}")

        result = {
            'symbol': symbol,
            'expirations_processed': 0,
            'strikes_processed': 0,
            'success': False,
            'error': None
        }

        try:
            # Get ALL options contracts from Polygon.io
            print(f"   🔍 Fetching options chain from Polygon.io...")

            options_df = polygon_fetcher.get_options_chain(
                symbol=symbol,
                expiration=None,  # Get all expirations
                strike=None,      # Get all strikes
                option_type=None  # Get both calls and puts
            )

            if options_df is None or len(options_df) == 0:
                result['error'] = "No options data available from Polygon.io"
                print(f"   ⚠️  No options data available for {symbol}")
                return result

            print(f"   ✅ Fetched {len(options_df)} option contracts")

            # Filter to next 60 days (near-term magnets matter most)
            cutoff_date = (datetime.now() + timedelta(days=60)).date()

            # Parse expiration dates
            if 'expiration_date' in options_df.columns:
                options_df['exp_date_parsed'] = options_df['expiration_date'].apply(
                    lambda x: datetime.strptime(x, '%Y-%m-%d').date()
                )
                options_df = options_df[options_df['exp_date_parsed'] <= cutoff_date]

                print(f"   📅 Processing {len(options_df)} contracts expiring in next 60 days")

            # Group by expiration date
            if 'expiration_date' not in options_df.columns:
                result['error'] = "Invalid options data format from Polygon.io"
                print(f"   ❌ Missing expiration_date column")
                return result

            expirations = options_df['expiration_date'].unique()
            print(f"   Found {len(expirations)} unique expiration dates")

            # Process each expiration
            for expiration in sorted(expirations):
                exp_contracts = options_df[options_df['expiration_date'] == expiration]
                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                dte = (exp_date - self.snapshot_date).days

                print(f"   • {expiration} ({dte} DTE)...", end='')

                try:
                    # Get unique strikes for this expiration
                    strikes = exp_contracts['strike_price'].unique() if 'strike_price' in exp_contracts.columns else []

                    strikes_processed = 0

                    for strike in strikes:
                        strike_contracts = exp_contracts[exp_contracts['strike_price'] == strike]

                        # Separate calls and puts
                        calls = strike_contracts[strike_contracts['contract_type'] == 'call']
                        puts = strike_contracts[strike_contracts['contract_type'] == 'put']

                        call_oi = 0
                        put_oi = 0
                        call_volume = 0
                        put_volume = 0

                        # Get open interest from Polygon.io data
                        # Note: Basic options endpoint may not include OI, need to get snapshot
                        if len(calls) > 0:
                            # Try to get OI from contract details or snapshot
                            call_ticker = calls.iloc[0].get('ticker', None)
                            if call_ticker:
                                call_quote = self._get_option_snapshot(call_ticker)
                                if call_quote:
                                    call_oi = call_quote.get('open_interest', 0)
                                    call_volume = call_quote.get('volume', 0)

                        if len(puts) > 0:
                            put_ticker = puts.iloc[0].get('ticker', None)
                            if put_ticker:
                                put_quote = self._get_option_snapshot(put_ticker)
                                if put_quote:
                                    put_oi = put_quote.get('open_interest', 0)
                                    put_volume = put_quote.get('volume', 0)

                        # Only save if we have open interest data
                        if call_oi > 0 or put_oi > 0:
                            self._save_snapshot(
                                symbol=symbol,
                                strike=float(strike),
                                expiration_date=expiration,
                                call_oi=call_oi,
                                put_oi=put_oi,
                                call_volume=call_volume,
                                put_volume=put_volume
                            )
                            strikes_processed += 1

                    print(f" ✅ {strikes_processed} strikes")
                    result['expirations_processed'] += 1
                    result['strikes_processed'] += strikes_processed

                    # Minimal delay for paid tier (100+ req/min)
                    time.sleep(0.01)

                except Exception as e:
                    print(f" ❌ Error: {e}")

            result['success'] = True
            print(f"\n   ✅ {symbol} complete: {result['expirations_processed']} expirations, {result['strikes_processed']} strikes")

        except Exception as e:
            result['error'] = str(e)
            print(f"\n   ❌ Error snapshotting {symbol}: {e}")
            import traceback
            traceback.print_exc()

        return result

    def _get_option_snapshot(self, option_ticker: str) -> Optional[Dict]:
        """
        Get snapshot data for a specific option ticker using Polygon.io Options Developer API
        Returns: {'open_interest': int, 'volume': int, 'last_price': float, ...}
        """
        try:
            # Extract details from ticker (e.g., O:SPY241220C00570000)
            # Format: O:{underlying}{YYMMDD}{C/P}{price*1000:08d}
            if not option_ticker.startswith('O:'):
                return None

            parts = option_ticker[2:]  # Remove "O:"

            # Parse the option ticker
            # Example: SPY241220C00570000
            # Extract: underlying (SPY), date (241220), type (C), strike (00570000)

            # Find where the date starts (first digit)
            i = 0
            while i < len(parts) and not parts[i].isdigit():
                i += 1

            underlying = parts[:i]
            remaining = parts[i:]

            # Date is next 6 digits (YYMMDD)
            date_str = remaining[:6]
            remaining = remaining[6:]

            # Type is next char (C or P)
            option_type = 'call' if remaining[0] == 'C' else 'put'
            remaining = remaining[1:]

            # Strike is remaining 8 digits
            strike_int = int(remaining)
            strike = strike_int / 1000.0

            # Convert date YYMMDD to YYYY-MM-DD
            expiration = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:6]}"

            # Use polygon_fetcher to get the quote
            quote = polygon_fetcher.get_option_quote(underlying, strike, expiration, option_type)

            return quote

        except Exception as e:
            # Silent fail - not all contracts have snapshots available
            return None

    def _save_snapshot(self, symbol: str, strike: float, expiration_date: str,
                       call_oi: int, put_oi: int, call_volume: int = 0, put_volume: int = 0,
                       call_gamma: float = 0.0, put_gamma: float = 0.0):
        """Save OI snapshot to PostgreSQL database"""
        if self.test_mode:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            # Check if record exists
            c.execute('''
                SELECT id FROM historical_open_interest
                WHERE date = %s AND symbol = %s AND strike = %s AND expiration_date = %s
            ''', (
                self.snapshot_date.isoformat(),
                symbol,
                strike,
                expiration_date
            ))

            existing = c.fetchone()

            if existing:
                # Update existing record
                c.execute('''
                    UPDATE historical_open_interest
                    SET call_oi = %s, put_oi = %s, call_volume = %s, put_volume = %s,
                        call_gamma = %s, put_gamma = %s
                    WHERE id = %s
                ''', (
                    call_oi, put_oi, call_volume, put_volume, call_gamma, put_gamma, existing[0]
                ))
            else:
                # Insert new record
                c.execute('''
                    INSERT INTO historical_open_interest
                    (date, symbol, strike, expiration_date, call_oi, put_oi, call_volume, put_volume, call_gamma, put_gamma)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    self.snapshot_date.isoformat(),
                    symbol,
                    strike,
                    expiration_date,
                    call_oi,
                    put_oi,
                    call_volume,
                    put_volume,
                    call_gamma,
                    put_gamma
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"      ⚠️  Database error: {e}")

    def run_all(self, symbols: List[str] = None):
        """Run snapshots for all symbols"""
        if symbols is None:
            symbols = DEFAULT_SYMBOLS

        print("\n" + "="*80)
        print("📸 HISTORICAL OPEN INTEREST SNAPSHOT - POLYGON.IO")
        print("="*80)
        print(f"Date: {self.snapshot_date}")
        print(f"Symbols: {', '.join(symbols)}")
        print(f"Mode: {'TEST (no database writes)' if self.test_mode else 'PRODUCTION'}")
        print("="*80)

        for i, symbol in enumerate(symbols, 1):
            print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")
            result = self.snapshot_symbol(symbol)
            self.results.append(result)

            # Minimal delay between symbols for paid tier
            if i < len(symbols):
                print(f"   ⏸️  Waiting 0.5s before next symbol...")
                time.sleep(0.5)

        self.print_summary()

    def print_summary(self):
        """Print summary of all snapshots"""
        print("\n" + "="*80)
        print("📊 SNAPSHOT SUMMARY")
        print("="*80)

        successful = [r for r in self.results if r['success']]
        failed = [r for r in self.results if not r['success']]

        print(f"\n✅ Successful: {len(successful)}")
        for r in successful:
            print(f"   • {r['symbol']:6} - {r['expirations_processed']} expirations, {r['strikes_processed']} strikes")

        if failed:
            print(f"\n❌ Failed: {len(failed)}")
            for r in failed:
                print(f"   • {r['symbol']:6} - {r['error']}")

        total_strikes = sum(r['strikes_processed'] for r in self.results)
        print(f"\n📊 Total: {len(self.results)} symbols, {total_strikes} strikes saved")
        print("="*80)


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Capture daily OI snapshots using Polygon.io')
    parser.add_argument('symbols', nargs='*', help='Symbols to snapshot (default: SPY, QQQ, etc.)')
    parser.add_argument('--test', action='store_true', help='Test mode (no database writes)')
    args = parser.parse_args()

    # Determine which symbols to process
    symbols = args.symbols if args.symbols else DEFAULT_SYMBOLS

    # Run snapshot job
    job = OISnapshotJob(test_mode=args.test)
    job.run_all(symbols=symbols)


if __name__ == '__main__':
    main()
