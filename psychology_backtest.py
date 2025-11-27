#!/usr/bin/env python3
"""
Psychology Trap Detection - Backtest Framework

This module backtests the psychology trap detection system against historical data
to validate pattern predictions and calculate actual win rates.

Features:
- Load historical price and gamma data
- Run psychology detector on past data
- Track outcomes (did prediction match reality?)
- Calculate win rates per pattern
- Generate performance reports

Usage:
    python psychology_backtest.py --symbol SPY --start 2024-01-01 --end 2024-12-31
"""

import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from polygon_data_fetcher import polygon_fetcher

from psychology_trap_detector import (
    analyze_current_market_complete,
    calculate_mtf_rsi_score
)
from config_and_database import DB_PATH
from database_adapter import get_connection


class PsychologyBacktester:
    """Backtest psychology trap detection patterns"""

    def __init__(self, symbol: str = 'SPY'):
        self.symbol = symbol
        self.results = []
        self.pattern_stats = {}

    def fetch_historical_data(self, start_date: str, end_date: str) -> Dict:
        """
        Fetch historical price data for all timeframes using Polygon.io

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Dict with price data for all timeframes
        """
        print(f"Fetching historical data for {self.symbol} from {start_date} to {end_date} via Polygon.io...")

        # Calculate days needed (add buffer for RSI calculation)
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=30)
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        total_days = (end_dt - start_dt).days

        price_data = {}

        # 5-minute data
        try:
            df_5m = polygon_fetcher.get_price_history(self.symbol, days=3, timeframe='minute', multiplier=5)
            price_data['5m'] = self._format_ohlcv(df_5m) if df_5m is not None else []
        except Exception as e:
            print(f"Warning: Could not fetch 5m data: {e}")
            price_data['5m'] = []

        # 15-minute data
        try:
            df_15m = polygon_fetcher.get_price_history(self.symbol, days=7, timeframe='minute', multiplier=15)
            price_data['15m'] = self._format_ohlcv(df_15m) if df_15m is not None else []
        except Exception as e:
            print(f"Warning: Could not fetch 15m data: {e}")
            price_data['15m'] = []

        # 1-hour data
        try:
            df_1h = polygon_fetcher.get_price_history(self.symbol, days=14, timeframe='hour', multiplier=1)
            price_data['1h'] = self._format_ohlcv(df_1h) if df_1h is not None else []
        except Exception as e:
            print(f"Warning: Could not fetch 1h data: {e}")
            price_data['1h'] = []

        # 4-hour data
        try:
            df_4h = polygon_fetcher.get_price_history(self.symbol, days=30, timeframe='hour', multiplier=4)
            price_data['4h'] = self._format_ohlcv(df_4h) if df_4h is not None else []
        except Exception as e:
            print(f"Warning: Could not fetch 4h data: {e}")
            price_data['4h'] = []

        # Daily data
        try:
            df_1d = polygon_fetcher.get_price_history(self.symbol, days=total_days, timeframe='day', multiplier=1)
            price_data['1d'] = self._format_ohlcv(df_1d) if df_1d is not None else []
        except Exception as e:
            print(f"Warning: Could not fetch 1d data: {e}")
            price_data['1d'] = []

        print(f"✓ Fetched {len(price_data['1d'])} days of data from Polygon.io")

        return price_data

    def _format_ohlcv(self, df: pd.DataFrame) -> List[Dict]:
        """Convert pandas DataFrame to list of OHLCV dicts"""
        if df.empty:
            return []

        df = df.reset_index()
        result = []

        for _, row in df.iterrows():
            result.append({
                'timestamp': row.get('Date', row.get('Datetime', datetime.now())).isoformat(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })

        return result

    def simulate_gamma_data(self, current_price: float, date: datetime) -> Dict:
        """
        Simulate gamma data for historical dates

        NOTE: This is a simplified simulation. For real backtesting, you need historical gamma data.
        This creates synthetic gamma levels based on price for demonstration purposes.

        Args:
            current_price: Current stock price
            date: Date to simulate for

        Returns:
            Simulated gamma data structure
        """
        # Simulate gamma walls around current price
        call_wall_strike = round(current_price * 1.02, 0)  # 2% above
        put_wall_strike = round(current_price * 0.98, 0)   # 2% below
        flip_point = round(current_price, 0)

        # Simulate net gamma (varies by day of week - simplified)
        day_of_week = date.weekday()
        if day_of_week in [0, 1]:  # Monday, Tuesday - more negative
            net_gamma = -5e9
        elif day_of_week in [4]:  # Friday - more positive (OPEX effect)
            net_gamma = 2e9
        else:
            net_gamma = -1e9

        return {
            'net_gamma': net_gamma,
            'flip_point': flip_point,
            'call_wall': call_wall_strike,
            'put_wall': put_wall_strike,
            'expirations': [
                {
                    'expiration_date': date + timedelta(days=1),
                    'dte': 1,
                    'expiration_type': '0dte',
                    'call_strikes': [
                        {'strike': call_wall_strike, 'gamma_exposure': -2e9, 'open_interest': 50000, 'delta': 0.3}
                    ],
                    'put_strikes': [
                        {'strike': put_wall_strike, 'gamma_exposure': -1.5e9, 'open_interest': 40000, 'delta': -0.3}
                    ]
                },
                {
                    'expiration_date': date + timedelta(days=7),
                    'dte': 7,
                    'expiration_type': 'weekly',
                    'call_strikes': [
                        {'strike': call_wall_strike, 'gamma_exposure': -1e9, 'open_interest': 30000, 'delta': 0.25}
                    ],
                    'put_strikes': [
                        {'strike': put_wall_strike, 'gamma_exposure': -0.8e9, 'open_interest': 25000, 'delta': -0.25}
                    ]
                }
            ]
        }

    def backtest_date(self, date: datetime, price_data: Dict) -> Dict:
        """
        Run psychology detector for a specific date

        Args:
            date: Date to backtest
            price_data: Historical price data (all timeframes)

        Returns:
            Analysis result for that date
        """
        # Get price data up to this date
        date_str = date.strftime('%Y-%m-%d')

        # Filter price data to only include data up to this date
        filtered_price_data = {}
        for tf, data in price_data.items():
            filtered_data = [
                bar for bar in data
                if datetime.fromisoformat(bar['timestamp']).date() <= date.date()
            ]
            filtered_price_data[tf] = filtered_data[-100:]  # Keep last 100 bars

        if not filtered_price_data.get('1d'):
            return None

        current_price = filtered_price_data['1d'][-1]['close']

        # Simulate gamma data (replace with real historical gamma if available)
        gamma_data = self.simulate_gamma_data(current_price, date)

        # Calculate volume ratio (simplified)
        if len(filtered_price_data['1d']) >= 20:
            recent_vol = filtered_price_data['1d'][-1]['volume']
            avg_vol = np.mean([bar['volume'] for bar in filtered_price_data['1d'][-20:]])
            volume_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
        else:
            volume_ratio = 1.0

        try:
            # Run psychology analysis
            analysis = analyze_current_market_complete(
                current_price,
                filtered_price_data,
                gamma_data,
                volume_ratio
            )

            return {
                'date': date_str,
                'price': current_price,
                'analysis': analysis,
                'volume_ratio': volume_ratio
            }
        except Exception as e:
            print(f"Error analyzing {date_str}: {e}")
            return None

    def calculate_outcome(self, signal_date: datetime, regime_type: str,
                         trade_direction: str, price_data: Dict) -> Dict:
        """
        Calculate if the regime prediction was correct

        Args:
            signal_date: Date signal was generated
            regime_type: Type of regime detected
            trade_direction: Predicted direction
            price_data: Historical price data

        Returns:
            Outcome metrics (win/loss, price change, etc.)
        """
        # Get price at signal
        signal_price = None
        for bar in price_data['1d']:
            bar_date = datetime.fromisoformat(bar['timestamp']).date()
            if bar_date == signal_date.date():
                signal_price = bar['close']
                break

        if not signal_price:
            return {'outcome': 'unknown', 'price_change': 0}

        # Define lookforward periods based on regime type
        if regime_type in ['GAMMA_SQUEEZE_CASCADE', 'FLIP_POINT_CRITICAL', 'ZERO_DTE_PIN']:
            lookforward_days = 1  # Same day or next day
        elif regime_type in ['LIBERATION_TRADE', 'FALSE_FLOOR', 'PIN_AT_CALL_WALL', 'PIN_AT_PUT_WALL']:
            lookforward_days = 3
        else:
            lookforward_days = 5

        # Get price after lookforward period
        target_date = signal_date + timedelta(days=lookforward_days)
        target_price = None

        for bar in price_data['1d']:
            bar_date = datetime.fromisoformat(bar['timestamp']).date()
            if bar_date >= target_date.date():
                target_price = bar['close']
                break

        if not target_price:
            return {'outcome': 'unknown', 'price_change': 0}

        # Calculate price change
        price_change_pct = ((target_price - signal_price) / signal_price) * 100

        # Determine if prediction was correct
        correct = False

        if trade_direction == 'bullish':
            correct = price_change_pct > 0.5  # >0.5% move up
        elif trade_direction == 'bearish':
            correct = price_change_pct < -0.5  # >0.5% move down
        elif trade_direction in ['bullish_post_expiration', 'fade']:
            correct = abs(price_change_pct) > 0.5  # Any meaningful move
        else:
            # Neutral or unclear - count as correct if abs move < 1%
            correct = abs(price_change_pct) < 1.0

        return {
            'outcome': 'win' if correct else 'loss',
            'signal_price': signal_price,
            'target_price': target_price,
            'price_change_pct': price_change_pct,
            'lookforward_days': lookforward_days
        }

    def run_backtest(self, start_date: str, end_date: str) -> Dict:
        """
        Run complete backtest over date range

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)

        Returns:
            Backtest results with win rates per pattern
        """
        print(f"\n{'='*60}")
        print(f"Psychology Trap Detection - Backtest")
        print(f"{'='*60}\n")

        # Fetch historical data
        price_data = self.fetch_historical_data(start_date, end_date)

        if not price_data.get('1d'):
            print("Error: No daily price data available")
            return {}

        # Run analysis for each day
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        current_date = start_dt
        signals = []

        while current_date <= end_dt:
            result = self.backtest_date(current_date, price_data)

            if result and result['analysis']:
                regime = result['analysis']['regime']

                # Only track actionable signals (not NEUTRAL)
                if regime['primary_type'] != 'NEUTRAL':
                    # Calculate outcome
                    outcome = self.calculate_outcome(
                        current_date,
                        regime['primary_type'],
                        regime['trade_direction'],
                        price_data
                    )

                    signals.append({
                        'date': result['date'],
                        'price': result['price'],
                        'regime_type': regime['primary_type'],
                        'trade_direction': regime['trade_direction'],
                        'confidence': regime['confidence'],
                        'risk_level': regime['risk_level'],
                        **outcome
                    })

                    print(f"{result['date']}: {regime['primary_type']} - {outcome['outcome'].upper()}")

            current_date += timedelta(days=1)

        # Calculate statistics
        stats = self._calculate_statistics(signals)

        print(f"\n{'='*60}")
        print(f"Backtest Results Summary")
        print(f"{'='*60}\n")

        self._print_statistics(stats)

        # Save to database
        self._save_backtest_results(signals, stats)

        return {
            'signals': signals,
            'statistics': stats,
            'total_signals': len(signals),
            'date_range': f"{start_date} to {end_date}"
        }

    def _calculate_statistics(self, signals: List[Dict]) -> Dict:
        """Calculate win rates and statistics per pattern"""
        stats = {}

        # Group by regime type
        by_regime = {}
        for signal in signals:
            regime = signal['regime_type']
            if regime not in by_regime:
                by_regime[regime] = []
            by_regime[regime].append(signal)

        # Calculate stats for each regime
        for regime, regime_signals in by_regime.items():
            wins = [s for s in regime_signals if s.get('outcome') == 'win']
            losses = [s for s in regime_signals if s.get('outcome') == 'loss']

            total = len(regime_signals)
            win_count = len(wins)
            loss_count = len(losses)

            win_rate = (win_count / total * 100) if total > 0 else 0

            avg_gain = np.mean([s['price_change_pct'] for s in wins]) if wins else 0
            avg_loss = np.mean([s['price_change_pct'] for s in losses]) if losses else 0

            stats[regime] = {
                'total_signals': total,
                'wins': win_count,
                'losses': loss_count,
                'win_rate': win_rate,
                'avg_gain_pct': avg_gain,
                'avg_loss_pct': avg_loss,
                'avg_confidence': np.mean([s['confidence'] for s in regime_signals])
            }

        return stats

    def _print_statistics(self, stats: Dict):
        """Print formatted statistics"""
        for regime, data in sorted(stats.items(), key=lambda x: x[1]['win_rate'], reverse=True):
            print(f"\n{regime}:")
            print(f"  Total Signals: {data['total_signals']}")
            print(f"  Win Rate: {data['win_rate']:.1f}%")
            print(f"  Wins/Losses: {data['wins']}/{data['losses']}")
            print(f"  Avg Gain: {data['avg_gain_pct']:+.2f}%")
            print(f"  Avg Loss: {data['avg_loss_pct']:+.2f}%")
            print(f"  Avg Confidence: {data['avg_confidence']:.0f}")

    def _save_backtest_results(self, signals: List[Dict], stats: Dict):
        """Save backtest results to database"""
        conn = get_connection()
        c = conn.cursor()

        # Create backtest results table if it doesn't exist
        c.execute('''
            CREATE TABLE IF NOT EXISTS backtest_results (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                backtest_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                signal_date DATE,
                regime_type TEXT,
                trade_direction TEXT,
                confidence REAL,
                risk_level TEXT,
                signal_price REAL,
                target_price REAL,
                price_change_pct REAL,
                outcome TEXT,
                lookforward_days INTEGER
            )
        ''')

        # Insert signals
        for signal in signals:
            c.execute('''
                INSERT INTO backtest_results (
                    symbol, signal_date, regime_type, trade_direction,
                    confidence, risk_level, signal_price, target_price,
                    price_change_pct, outcome, lookforward_days
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                self.symbol, signal['date'], signal['regime_type'],
                signal['trade_direction'], signal['confidence'],
                signal['risk_level'], signal.get('signal_price'),
                signal.get('target_price'), signal.get('price_change_pct'),
                signal.get('outcome'), signal.get('lookforward_days')
            ))

        # Update sucker_statistics table with actual backtest data
        for regime, data in stats.items():
            c.execute('''
                INSERT INTO sucker_statistics (
                    scenario_type, total_occurrences, newbie_fade_failed,
                    newbie_fade_succeeded, failure_rate, last_updated
                ) VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (scenario_type) DO UPDATE SET
                    total_occurrences = EXCLUDED.total_occurrences,
                    newbie_fade_failed = EXCLUDED.newbie_fade_failed,
                    newbie_fade_succeeded = EXCLUDED.newbie_fade_succeeded,
                    failure_rate = EXCLUDED.failure_rate,
                    last_updated = NOW()
            ''', (
                regime, data['total_signals'], data['wins'],
                data['losses'], 100 - data['win_rate']
            ))

        conn.commit()
        conn.close()

        print(f"\n✓ Saved {len(signals)} signals to database")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Backtest Psychology Trap Detection')
    parser.add_argument('--symbol', default='SPY', help='Stock symbol')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')

    args = parser.parse_args()

    backtester = PsychologyBacktester(args.symbol)
    results = backtester.run_backtest(args.start, args.end)

    print(f"\nBacktest complete! Tested {results['total_signals']} signals.")


if __name__ == '__main__':
    main()
