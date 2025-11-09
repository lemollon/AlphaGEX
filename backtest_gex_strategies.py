"""
GEX Strategy Backtester

Backtests GEX-based trading signals:
- Flip point breakouts/breakdowns
- Call/Put wall rejections
- Positive GEX -> Negative GEX regime changes
- Dealer positioning shifts

Uses simulated gamma data (can be replaced with real GEX data if available)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtest_framework import BacktestBase, BacktestResults, Trade
from typing import Dict, List


class GEXBacktester(BacktestBase):
    """Backtest GEX-based strategies"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.gex_data = None

    def simulate_gex_data(self, price_data: pd.DataFrame) -> pd.DataFrame:
        """
        Simulate GEX data based on price action

        In production, replace this with actual GEX calculations
        Simulation logic:
        - Flip point ~= ATR-based dynamic level
        - Walls appear near round numbers
        - Negative GEX when price volatile
        - Positive GEX when price stable
        """
        df = price_data.copy()

        # Calculate ATR for flip point estimation
        df['HL'] = df['High'] - df['Low']
        df['HC'] = abs(df['High'] - df['Close'].shift(1))
        df['LC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['HL', 'HC', 'LC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(14).mean()

        # Flip point = Moving average with ATR offset
        df['flip_point'] = df['Close'].rolling(20).mean()

        # Call/Put walls at psychological levels (round numbers)
        df['call_wall'] = (np.ceil(df['Close'] / 10) * 10).astype(float)
        df['put_wall'] = (np.floor(df['Close'] / 10) * 10).astype(float)

        # Net GEX estimation (negative when volatile, positive when calm)
        df['volatility'] = df['Close'].pct_change().rolling(10).std() * 100
        df['net_gex'] = np.where(
            df['volatility'] > df['volatility'].rolling(50).mean(),
            -1e9,  # Negative GEX (volatile)
            +2e9   # Positive GEX (calm)
        )

        # Distance to flip point
        df['dist_to_flip'] = abs(df['Close'] - df['flip_point']) / df['flip_point'] * 100

        # Distance to walls
        df['dist_to_call_wall'] = abs(df['Close'] - df['call_wall']) / df['Close'] * 100
        df['dist_to_put_wall'] = abs(df['Close'] - df['put_wall']) / df['Close'] * 100

        return df

    def detect_flip_point_breakout(self, row: pd.Series, prev_row: pd.Series) -> Dict:
        """Detect flip point breakout (bullish signal)"""
        # Price breaks above flip point with volume
        if (prev_row['Close'] <= prev_row['flip_point'] and
            row['Close'] > row['flip_point'] and
            row['Volume'] > row['Volume'].rolling(20).mean() * 1.2):

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
            row['Volume'] > row['Volume'].rolling(20).mean() * 1.2):

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
        if (row['net_gex'] < -0.5e9 and
            row['dist_to_flip'] < 2.0 and
            row['Volume'] > row['Volume'].rolling(20).mean() * 1.3):

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
        """Run GEX strategy backtest"""
        print(f"\n🎯 Running GEX Strategy Backtest...")

        # Fetch price data
        self.fetch_historical_data()

        # Simulate GEX data
        print("Simulating GEX data (replace with real data in production)...")
        self.gex_data = self.simulate_gex_data(self.price_data)

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
