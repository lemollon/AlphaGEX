"""
GEX Strategy Backtester

Backtests GEX-based trading signals:
- Flip point breakouts/breakdowns
- Call/Put wall rejections
- Positive GEX -> Negative GEX regime changes
- Dealer positioning shifts

Uses REAL GEX data from Trading Volatility API
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtest_framework import BacktestBase, BacktestResults, Trade
from typing import Dict, List


class GEXBacktester(BacktestBase):
    """Backtest GEX-based strategies using REAL GEX data"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gex_data = None
        self.api_client = None

    def simulate_gex_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Simulate approximate GEX levels when real data unavailable

        Uses simplified heuristics based on price action and volatility:
        - Flip point typically 2-3% below current price
        - Call wall ~2% above price
        - Put wall ~2-3% below price
        - Net GEX correlates inversely with recent volatility
        """
        df = price_data.copy()

        # Calculate volatility for GEX estimation
        df['returns'] = df['Close'].pct_change()
        df['volatility'] = df['returns'].rolling(10).std() * 100

        # Simulate flip point (typically below current price, moves with volatility)
        df['flip_point'] = df['Close'] * 0.975  # 2.5% below current

        # Call wall (resistance above)
        df['call_wall'] = df['Close'] * 1.020  # 2% above

        # Put wall (support below)
        df['put_wall'] = df['Close'] * 0.975  # 2.5% below

        # Net GEX (negative when volatile, positive when calm)
        # Scale based on median volatility to create realistic variation
        median_vol = df['volatility'].median()
        df['net_gex'] = df['volatility'].apply(
            lambda v: -5e9 if v > median_vol * 1.5 else 2e9 if v < median_vol * 0.7 else 0
        )

        # Derived metrics
        df['dist_to_flip'] = abs(df['Close'] - df['flip_point']) / df['flip_point'] * 100
        df['dist_to_call_wall'] = abs(df['Close'] - df['call_wall']) / df['Close'] * 100
        df['dist_to_put_wall'] = abs(df['Close'] - df['put_wall']) / df['Close'] * 100

        # Calculate ATR
        df['HL'] = df['High'] - df['Low']
        df['HC'] = abs(df['High'] - df['Close'].shift(1))
        df['LC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['HL', 'HC', 'LC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(14).mean()

        print(f"✓ Simulated GEX data generated")
        print(f"   Net GEX range: ${df['net_gex'].min()/1e9:.2f}B to ${df['net_gex'].max()/1e9:.2f}B")
        print(f"   Flip point range: ${df['flip_point'].min():.2f} to ${df['flip_point'].max():.2f}")

        return df

    def fetch_real_gex_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Fetch REAL historical GEX data from Trading Volatility API

        Returns price data merged with actual GEX levels (net GEX, flip point, walls)
        """
        try:
            from core_classes_and_engines import TradingVolatilityAPI
        except ImportError as e:
            print(f"⚠️ Trading Volatility API not available: {e}")
            print("   Falling back to SIMULATED GEX data for backtesting...")
            return self.simulate_gex_data(price_data)

        df = price_data.copy()

        # Initialize API client
        if self.api_client is None:
            try:
                self.api_client = TradingVolatilityAPI()
            except Exception as e:
                print(f"⚠️ Failed to initialize Trading Volatility API: {e}")
                print("   Falling back to SIMULATED GEX data for backtesting...")
                return self.simulate_gex_data(price_data)

        print(f"📡 Fetching REAL historical GEX data from Trading Volatility API...")

        # Calculate days back from date range
        start_dt = pd.to_datetime(self.start_date)
        end_dt = pd.to_datetime(self.end_date)
        days_back = (end_dt - start_dt).days + 10  # Add buffer

        # Fetch real historical GEX data
        try:
            historical_gex = self.api_client.get_historical_gamma(self.symbol, days_back=days_back)
        except Exception as e:
            print(f"⚠️ Failed to fetch historical GEX data: {e}")
            print("   Falling back to SIMULATED GEX data for backtesting...")
            return self.simulate_gex_data(price_data)

        if not historical_gex or len(historical_gex) == 0:
            print("⚠️ WARNING: No historical GEX data available from Trading Volatility API")
            print("   Falling back to SIMULATED GEX data for backtesting...")
            print("   NOTE: Results will be approximate - use real data for production validation")
            return self.simulate_gex_data(price_data)

        print(f"✅ Received {len(historical_gex)} days of REAL GEX data")

        # Convert to DataFrame and parse dates
        gex_df = pd.DataFrame(historical_gex)

        # Parse date field (handle different possible formats)
        date_field = None
        for field in ['date', 'Date', 'timestamp', 'trading_date', 'collection_date']:
            if field in gex_df.columns:
                date_field = field
                break

        if date_field is None:
            print("⚠️  Warning: No date field found in GEX data")
            print(f"   Available fields: {list(gex_df.columns)}")
            raise ValueError("Cannot parse dates from GEX historical data")

        # Parse dates with flexible format handling
        # Trading Volatility API returns inconsistent formats:
        # - "2022-01-20_20:47:25" (underscore separator)
        # - "2022-01-10 14:36:25.864668" (space separator with microseconds)
        gex_df['date'] = pd.to_datetime(gex_df[date_field].str.replace('_', ' '), format='mixed', errors='coerce')
        gex_df.set_index('date', inplace=True)

        # Merge GEX data with price data by date
        print("Merging GEX data with price data...")

        # Rename columns to standard names if needed
        column_mapping = {
            'net_gex': 'net_gex',
            'netGex': 'net_gex',
            'net_gamma': 'net_gex',
            'gex_per_1pct_chg': 'net_gex',
            'nearest_gex_value': 'net_gex',
            'flip_point': 'flip_point',
            'flipPoint': 'flip_point',
            'zero_gamma': 'flip_point',
            'gex_flip_price': 'flip_point',
            'call_wall': 'call_wall',
            'callWall': 'call_wall',
            'put_wall': 'put_wall',
            'putWall': 'put_wall'
        }

        for old_name, new_name in column_mapping.items():
            if old_name in gex_df.columns and new_name not in gex_df.columns:
                gex_df.rename(columns={old_name: new_name}, inplace=True)

        # Merge on date index - only include columns that exist
        available_gex_cols = [col for col in ['net_gex', 'flip_point', 'call_wall', 'put_wall']
                              if col in gex_df.columns]

        if available_gex_cols:
            df = df.join(gex_df[available_gex_cols], how='left')
        else:
            print("⚠️  No recognized GEX columns found, falling back to simulated data")
            return self.simulate_gex_data(price_data)

        # Forward fill missing GEX values (weekends/holidays)
        if 'net_gex' in df.columns:
            df['net_gex'].fillna(method='ffill', inplace=True)
        if 'flip_point' in df.columns:
            df['flip_point'].fillna(method='ffill', inplace=True)
        if 'call_wall' in df.columns:
            df['call_wall'].fillna(method='ffill', inplace=True)
        if 'put_wall' in df.columns:
            df['put_wall'].fillna(method='ffill', inplace=True)

        # Calculate derived metrics
        if 'flip_point' in df.columns:
            df['dist_to_flip'] = abs(df['Close'] - df['flip_point']) / df['flip_point'] * 100
        if 'call_wall' in df.columns:
            df['dist_to_call_wall'] = abs(df['Close'] - df['call_wall']) / df['Close'] * 100
        else:
            df['call_wall'] = df['Close'] * 1.05  # Estimate 5% above price
            df['dist_to_call_wall'] = 5.0
        if 'put_wall' in df.columns:
            df['dist_to_put_wall'] = abs(df['Close'] - df['put_wall']) / df['Close'] * 100
        else:
            df['put_wall'] = df['Close'] * 0.95  # Estimate 5% below price
            df['dist_to_put_wall'] = 5.0

        # Calculate ATR for additional analysis
        df['HL'] = df['High'] - df['Low']
        df['HC'] = abs(df['High'] - df['Close'].shift(1))
        df['LC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['HL', 'HC', 'LC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(14).mean()

        # Calculate volume moving average for entry conditions
        df['volume_sma'] = df['Volume'].rolling(20).mean()

        print(f"✅ GEX data merged successfully - ready for backtesting")
        if 'net_gex' in df.columns and not df['net_gex'].isna().all():
            net_gex_min = float(df['net_gex'].min())
            net_gex_max = float(df['net_gex'].max())
            print(f"   Net GEX range: ${net_gex_min/1e9:.2f}B to ${net_gex_max/1e9:.2f}B")
        if 'flip_point' in df.columns and not df['flip_point'].isna().all():
            flip_min = float(df['flip_point'].min())
            flip_max = float(df['flip_point'].max())
            print(f"   Flip point range: ${flip_min:.2f} to ${flip_max:.2f}")

        return df

    def detect_flip_point_breakout(self, row: pd.Series, prev_row: pd.Series) -> Dict:
        """Detect flip point breakout (bullish signal)"""
        # Price breaks above flip point with volume
        if (prev_row['Close'] <= prev_row['flip_point'] and
            row['Close'] > row['flip_point'] and
            row['Volume'] > row['volume_sma'] * 1.2):

            return {
                'signal': True,
                'direction': 'LONG',
                'entry_price': row['Close'],
                'stop_loss': row['flip_point'] * 0.99,
                'target': row['call_wall'],
                'confidence': 75,
                'notes': 'Flip point breakout with volume'
            }
        return {'signal': False}

    def detect_flip_point_breakdown(self, row: pd.Series, prev_row: pd.Series) -> Dict:
        """Detect flip point breakdown (bearish signal)"""
        # Price breaks below flip point with volume
        if (prev_row['Close'] >= prev_row['flip_point'] and
            row['Close'] < row['flip_point'] and
            row['Volume'] > row['volume_sma'] * 1.2):

            return {
                'signal': True,
                'direction': 'SHORT',
                'entry_price': row['Close'],
                'stop_loss': row['flip_point'] * 1.01,
                'target': row['put_wall'],
                'confidence': 72,
                'notes': 'Flip point breakdown with volume'
            }
        return {'signal': False}

    def detect_call_wall_rejection(self, row: pd.Series, prev_row: pd.Series) -> Dict:
        """Detect call wall rejection (bearish signal)"""
        # Price hits call wall and rejects
        if (row['High'] >= row['call_wall'] * 0.998 and
            row['Close'] < row['call_wall'] * 0.995 and
            row['dist_to_call_wall'] < 0.5):

            return {
                'signal': True,
                'direction': 'SHORT',
                'entry_price': row['Close'],
                'stop_loss': row['call_wall'] * 1.005,
                'target': row['flip_point'],
                'confidence': 68,
                'notes': 'Call wall rejection'
            }
        return {'signal': False}

    def detect_put_wall_bounce(self, row: pd.Series, prev_row: pd.Series) -> Dict:
        """Detect put wall bounce (bullish signal)"""
        # Price hits put wall and bounces
        if (row['Low'] <= row['put_wall'] * 1.002 and
            row['Close'] > row['put_wall'] * 1.005 and
            row['dist_to_put_wall'] < 0.5):

            return {
                'signal': True,
                'direction': 'LONG',
                'entry_price': row['Close'],
                'stop_loss': row['put_wall'] * 0.995,
                'target': row['flip_point'],
                'confidence': 70,
                'notes': 'Put wall bounce'
            }
        return {'signal': False}

    def detect_negative_gex_squeeze(self, row: pd.Series, prev_row: pd.Series) -> Dict:
        """Detect negative GEX squeeze (explosive move)"""
        # Negative GEX + price near flip = squeeze potential
        # Volume must be 2x average to confirm real dealer activity
        if (row['net_gex'] < -0.5e9 and
            row['dist_to_flip'] < 2.0 and
            row['Volume'] > row['volume_sma'] * 2.0):

            # Direction based on which side of flip point
            direction = 'LONG' if row['Close'] > row['flip_point'] else 'SHORT'

            return {
                'signal': True,
                'direction': direction,
                'entry_price': row['Close'],
                'stop_loss': row['flip_point'],
                'target': row['call_wall'] if direction == 'LONG' else row['put_wall'],
                'confidence': 80,
                'notes': 'Negative GEX squeeze - dealer amplification active'
            }
        return {'signal': False}

    def run_backtest(self) -> BacktestResults:
        """Run GEX strategy backtest using REAL historical GEX data"""
        print(f"\n🎯 Running GEX Strategy Backtest...")

        # Fetch price data
        self.fetch_historical_data()

        # Fetch REAL GEX data from Trading Volatility API
        print("Fetching REAL historical GEX data from Trading Volatility API...")
        self.gex_data = self.fetch_real_gex_data(self.price_data)

        # Strategy configurations
        strategies = {
            'Flip Point Breakout': self.detect_flip_point_breakout,
            'Flip Point Breakdown': self.detect_flip_point_breakdown,
            'Call Wall Rejection': self.detect_call_wall_rejection,
            'Put Wall Bounce': self.detect_put_wall_bounce,
            'Negative GEX Squeeze': self.detect_negative_gex_squeeze
        }

        all_trades = []

        # Run each strategy
        for strategy_name, detector_func in strategies.items():
            print(f"\nTesting {strategy_name}...")
            strategy_trades = self.test_strategy(detector_func, strategy_name)
            all_trades.extend(strategy_trades)

            # Print individual strategy results
            if strategy_trades:
                results = self.calculate_metrics(strategy_trades, strategy_name)
                print(f"  Trades: {results.total_trades}, Win Rate: {results.win_rate:.1f}%, Expectancy: {results.expectancy_pct:+.2f}%")

        # Calculate combined results
        results = self.calculate_metrics(all_trades, "GEX Strategies (Combined)")
        self.print_summary(results)
        self.save_results_to_db(results)

        return results

    def test_strategy(self, detector_func, strategy_name: str) -> List[Trade]:
        """Test a single strategy and return trades"""
        trades = []
        in_position = False
        entry_signal = None

        for i in range(20, len(self.gex_data)):  # Start after warmup period
            row = self.gex_data.iloc[i]
            prev_row = self.gex_data.iloc[i-1]

            # Skip if not enough data for rolling calculations
            if pd.isna(row['ATR']) or pd.isna(row['flip_point']):
                continue

            # Entry logic
            if not in_position:
                signal = detector_func(row, prev_row)

                if signal['signal']:
                    entry_signal = signal
                    entry_signal['entry_date'] = row.name.strftime('%Y-%m-%d')
                    in_position = True

            # Exit logic (if in position)
            elif in_position:
                exit_triggered = False
                exit_price = row['Close']
                exit_date = row.name.strftime('%Y-%m-%d')

                # Stop loss hit
                if entry_signal['direction'] == 'LONG' and row['Low'] <= entry_signal['stop_loss']:
                    exit_price = entry_signal['stop_loss']
                    exit_triggered = True
                elif entry_signal['direction'] == 'SHORT' and row['High'] >= entry_signal['stop_loss']:
                    exit_price = entry_signal['stop_loss']
                    exit_triggered = True

                # Target hit
                if entry_signal['direction'] == 'LONG' and row['High'] >= entry_signal['target']:
                    exit_price = entry_signal['target']
                    exit_triggered = True
                elif entry_signal['direction'] == 'SHORT' and row['Low'] <= entry_signal['target']:
                    exit_price = entry_signal['target']
                    exit_triggered = True

                # Max holding period (5 days)
                entry_date = pd.to_datetime(entry_signal['entry_date'])
                current_date = row.name
                if (current_date - entry_date).days >= 5:
                    exit_triggered = True

                if exit_triggered:
                    trade = self.create_trade(
                        entry_date=entry_signal['entry_date'],
                        exit_date=exit_date,
                        entry_price=entry_signal['entry_price'],
                        exit_price=exit_price,
                        direction=entry_signal['direction'],
                        strategy=strategy_name,
                        confidence=entry_signal['confidence'],
                        notes=entry_signal['notes']
                    )
                    trades.append(trade)
                    in_position = False
                    entry_signal = None

        return trades


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Backtest GEX strategies')
    parser.add_argument('--symbol', default='SPY', help='Symbol to backtest')
    parser.add_argument('--start', default='2022-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', default='2024-12-31', help='End date YYYY-MM-DD')
    args = parser.parse_args()

    backtester = GEXBacktester(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        position_size_pct=10.0,
        commission_pct=0.05,
        slippage_pct=0.10
    )

    results = backtester.run_backtest()

    print("\n🎯 GEX Backtest Complete!")
    print(f"Check database for full results")
