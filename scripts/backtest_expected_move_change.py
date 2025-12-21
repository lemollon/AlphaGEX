#!/usr/bin/env python3
"""
Expected Move Change Signal Backtest
=====================================

Backtests the hypothesis that changes in expected move from prior day
can predict intraday market direction:

    - EM DOWN from prior day → Bearish (market likely to fall)
    - EM UP from prior day → Bullish (market likely to rise)
    - EM FLAT → Range-bound day
    - EM WIDEN → Big move coming (either direction)

Expected Move formula: EM = Spot × (VIX/100) × √(1/252)

Key insight: We compare EM as % of spot (not absolute $) to account for overnight gaps.

Usage:
    python scripts/backtest_expected_move_change.py
    python scripts/backtest_expected_move_change.py --start 2020-01-01 --end 2024-12-31 --verbose

Author: AlphaGEX
"""

import os
import sys
import argparse
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


# =============================================================================
# CONFIGURATION
# =============================================================================

# Signal thresholds (as % change in EM%)
FLAT_THRESHOLD = 3.0      # Less than 3% change = FLAT
WIDEN_THRESHOLD = 15.0    # More than 15% increase = WIDEN

# Outcome thresholds
BULLISH_MOVE_THRESHOLD = 0.0   # Positive close = bullish outcome
BEARISH_MOVE_THRESHOLD = 0.0   # Negative close = bearish outcome
BIG_MOVE_THRESHOLD = 0.5       # |change| > 0.5% = big move


@dataclass
class DayResult:
    """Results for a single trading day"""
    date: str

    # Expected Move data
    spot_open: float
    spot_close: float
    vix_open: float
    prior_vix: float
    prior_spot: float

    # Calculated EM
    em_today: float        # Today's expected move in $
    em_today_pct: float    # Today's EM as % of spot
    em_prior: float        # Prior day's EM in $
    em_prior_pct: float    # Prior day's EM as % of spot
    em_change_pct: float   # % change in EM%

    # Signal
    signal: str            # DOWN, UP, FLAT, WIDEN
    predicted_sentiment: str  # BEARISH, BULLISH, NEUTRAL, VOLATILE

    # Actual outcome
    price_change_pct: float    # (close - open) / open * 100
    actual_sentiment: str      # BEARISH, BULLISH, NEUTRAL
    is_big_move: bool          # |change| > threshold

    # Accuracy (calculated in __post_init__)
    signal_correct: bool = False

    def __post_init__(self):
        """Calculate signal correctness"""
        if self.predicted_sentiment == "VOLATILE":
            # WIDEN predicts big move (either direction)
            self.signal_correct = self.is_big_move
        elif self.predicted_sentiment == "NEUTRAL":
            # FLAT predicts small move
            self.signal_correct = not self.is_big_move
        else:
            # BULLISH/BEARISH predicts direction
            if self.predicted_sentiment == "BULLISH":
                self.signal_correct = self.actual_sentiment == "BULLISH"
            elif self.predicted_sentiment == "BEARISH":
                self.signal_correct = self.actual_sentiment == "BEARISH"
            else:
                self.signal_correct = False


@dataclass
class BacktestResults:
    """Complete backtest results"""
    start_date: str
    end_date: str
    total_days: int = 0

    # Overall accuracy
    correct_signals: int = 0
    accuracy_pct: float = 0.0

    # By signal type
    down_signals: int = 0
    down_correct: int = 0
    down_accuracy: float = 0.0
    down_avg_move: float = 0.0

    up_signals: int = 0
    up_correct: int = 0
    up_accuracy: float = 0.0
    up_avg_move: float = 0.0

    flat_signals: int = 0
    flat_correct: int = 0
    flat_accuracy: float = 0.0
    flat_avg_move: float = 0.0

    widen_signals: int = 0
    widen_correct: int = 0
    widen_accuracy: float = 0.0
    widen_avg_move: float = 0.0

    # Edge analysis
    avg_move_when_down: float = 0.0  # Avg price change when DOWN signal
    avg_move_when_up: float = 0.0    # Avg price change when UP signal

    # By year/month
    by_year: Dict = field(default_factory=dict)
    by_month: Dict = field(default_factory=dict)

    # Detailed results
    day_results: List[DayResult] = field(default_factory=list)


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL or ORAT_DATABASE_URL not set")

    return psycopg2.connect(database_url, connect_timeout=30)


def calculate_expected_move(spot: float, vix: float) -> float:
    """
    Calculate 1-day expected move from VIX.
    Formula: EM = Spot × (VIX/100) × √(1/252)
    """
    if spot <= 0 or vix <= 0:
        return 0
    return spot * (vix / 100) * math.sqrt(1 / 252)


def classify_signal(em_change_pct: float) -> Tuple[str, str]:
    """
    Classify the EM change into signal and sentiment.

    Returns: (signal, sentiment)
    """
    if abs(em_change_pct) < FLAT_THRESHOLD:
        return "FLAT", "NEUTRAL"
    elif em_change_pct > WIDEN_THRESHOLD:
        return "WIDEN", "VOLATILE"
    elif em_change_pct > 0:
        return "UP", "BULLISH"
    else:
        return "DOWN", "BEARISH"


def load_historical_data(start_date: str, end_date: str) -> pd.DataFrame:
    """
    Load historical SPY and VIX data.
    Falls back to Yahoo Finance if database doesn't have data.
    """
    print("Loading historical data...")

    spy_data = None
    vix_data = None

    # Try database first (if configured)
    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if database_url:
        try:
            conn = get_connection()
            cur = conn.cursor()

            # Check what tables are available
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name IN ('underlying_prices', 'vix_history', 'gex_structure_daily')
            """)
            available_tables = [row[0] for row in cur.fetchall()]
            print(f"  Available tables: {available_tables}")

            if 'underlying_prices' in available_tables:
                cur.execute("""
                    SELECT trade_date, open, high, low, close
                    FROM underlying_prices
                    WHERE symbol = 'SPY' AND trade_date >= %s AND trade_date <= %s
                    ORDER BY trade_date
                """, (start_date, end_date))
                rows = cur.fetchall()
                if rows:
                    spy_data = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close'])
                    spy_data['date'] = pd.to_datetime(spy_data['date'])
                    spy_data.set_index('date', inplace=True)
                    print(f"  Found {len(spy_data)} SPY records in database")

            if 'vix_history' in available_tables:
                cur.execute("""
                    SELECT trade_date, open, high, low, close
                    FROM vix_history
                    WHERE trade_date >= %s AND trade_date <= %s
                    ORDER BY trade_date
                """, (start_date, end_date))
                rows = cur.fetchall()
                if rows:
                    vix_data = pd.DataFrame(rows, columns=['date', 'vix_open', 'vix_high', 'vix_low', 'vix_close'])
                    vix_data['date'] = pd.to_datetime(vix_data['date'])
                    vix_data.set_index('date', inplace=True)
                    print(f"  Found {len(vix_data)} VIX records in database")

            conn.close()
        except Exception as db_error:
            print(f"  Database error: {db_error}")
    else:
        print("  No database configured, using Yahoo Finance...")

    # Fall back to Yahoo Finance if needed
    if spy_data is None or len(spy_data) == 0 or vix_data is None or len(vix_data) == 0:
        print("  Fetching from Yahoo Finance...")
        try:
            import yfinance as yf

            if spy_data is None or len(spy_data) == 0:
                spy = yf.download('SPY', start=start_date, end=end_date, progress=False)
                if not spy.empty:
                    # Handle multi-index columns
                    if isinstance(spy.columns, pd.MultiIndex):
                        spy.columns = spy.columns.get_level_values(0)
                    spy_data = spy[['Open', 'High', 'Low', 'Close']].copy()
                    spy_data.columns = ['open', 'high', 'low', 'close']
                    print(f"  Downloaded {len(spy_data)} SPY records from Yahoo")

            if vix_data is None or len(vix_data) == 0:
                vix = yf.download('^VIX', start=start_date, end=end_date, progress=False)
                if not vix.empty:
                    if isinstance(vix.columns, pd.MultiIndex):
                        vix.columns = vix.columns.get_level_values(0)
                    vix_data = vix[['Open', 'High', 'Low', 'Close']].copy()
                    vix_data.columns = ['vix_open', 'vix_high', 'vix_low', 'vix_close']
                    print(f"  Downloaded {len(vix_data)} VIX records from Yahoo")

        except Exception as yf_error:
            print(f"  yfinance error: {type(yf_error).__name__}")
            print("  Attempting alternative data sources...")

            # Try Alpha Vantage or Federal Reserve data
            try:
                import requests

                # Use FRED for VIX (free, no API key needed for basic access)
                # Try using an alternative: generate from sample data
                print("  Generating synthetic test data based on historical patterns...")

                # Generate realistic synthetic data for testing
                # Based on actual SPY/VIX historical statistics
                np.random.seed(42)
                start = pd.to_datetime(start_date)
                end = pd.to_datetime(end_date)
                dates = pd.bdate_range(start=start, end=end)  # Business days only

                # SPY: Start around 400, daily returns ~0.04% mean, 1.2% std
                spy_returns = np.random.normal(0.0004, 0.012, len(dates))
                spy_prices = [400]
                for ret in spy_returns[1:]:
                    spy_prices.append(spy_prices[-1] * (1 + ret))

                # Generate OHLC
                spy_opens = []
                spy_highs = []
                spy_lows = []
                spy_closes = []

                for i, price in enumerate(spy_prices):
                    if i == 0:
                        # First day
                        gap = np.random.normal(0, 0.003)  # Small gap
                    else:
                        gap = np.random.normal(0, 0.005)  # Overnight gap

                    open_price = spy_prices[i-1] * (1 + gap) if i > 0 else price
                    close_price = price
                    intraday_vol = abs(np.random.normal(0, 0.008))
                    high_price = max(open_price, close_price) * (1 + intraday_vol)
                    low_price = min(open_price, close_price) * (1 - intraday_vol)

                    spy_opens.append(open_price)
                    spy_highs.append(high_price)
                    spy_lows.append(low_price)
                    spy_closes.append(close_price)

                spy_data = pd.DataFrame({
                    'open': spy_opens,
                    'high': spy_highs,
                    'low': spy_lows,
                    'close': spy_closes
                }, index=dates)

                # VIX: Mean revert around 18, range 12-35
                vix_values = [18]
                for i in range(1, len(dates)):
                    # Mean reversion + noise
                    mean_rev = 0.02 * (18 - vix_values[-1])
                    # Higher VIX when SPY drops
                    spy_shock = -spy_returns[i] * 80  # Inverse correlation
                    noise = np.random.normal(0, 0.5)
                    new_vix = max(10, min(50, vix_values[-1] + mean_rev + spy_shock + noise))
                    vix_values.append(new_vix)

                vix_data = pd.DataFrame({
                    'vix_open': [v * (1 + np.random.normal(0, 0.02)) for v in vix_values],
                    'vix_high': [v * (1 + abs(np.random.normal(0, 0.03))) for v in vix_values],
                    'vix_low': [v * (1 - abs(np.random.normal(0, 0.03))) for v in vix_values],
                    'vix_close': vix_values
                }, index=dates)

                print(f"  Generated {len(spy_data)} synthetic trading days for testing")
                print("  NOTE: Using synthetic data - results are for methodology validation only!")

            except Exception as gen_error:
                print(f"  Data generation failed: {gen_error}")
                print("\n  To run this backtest, you need historical data.")
                print("  Options:")
                print("    1. Install yfinance: pip install yfinance")
                print("    2. Populate database tables: underlying_prices, vix_history")
                print("    3. Place CSV files in data/spy_daily.csv and data/vix_daily.csv")
                raise ValueError("Cannot load historical data for backtest")

    if spy_data is None or vix_data is None:
        raise ValueError("Could not load SPY or VIX data")

    # Merge SPY and VIX data
    merged = spy_data.join(vix_data, how='inner')
    merged = merged.dropna()
    merged = merged.reset_index()
    merged.rename(columns={'index': 'date'}, inplace=True)

    # Ensure date is datetime
    merged['date'] = pd.to_datetime(merged['date'])

    print(f"  Merged data: {len(merged)} trading days")

    return merged


def run_backtest(
    start_date: str = '2020-01-01',
    end_date: str = None,
    verbose: bool = False
) -> BacktestResults:
    """
    Run the Expected Move Change backtest.
    """
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    print(f"\n{'='*60}")
    print("EXPECTED MOVE CHANGE SIGNAL BACKTEST")
    print(f"{'='*60}")
    print(f"Period: {start_date} to {end_date}")
    print(f"Hypothesis: EM DOWN → Bearish, EM UP → Bullish")
    print(f"{'='*60}\n")

    # Load data
    data = load_historical_data(start_date, end_date)

    # Initialize results
    results = BacktestResults(start_date=start_date, end_date=end_date)

    # Track moves by signal type
    down_moves = []
    up_moves = []
    flat_moves = []
    widen_moves = []

    # Process each day
    for i in range(1, len(data)):
        current = data.iloc[i]
        prior = data.iloc[i-1]

        # Get prices
        spot_open = float(current['open'])
        spot_close = float(current['close'])
        vix_open = float(current['vix_open'])
        prior_vix = float(prior['vix_close'])  # Use prior close for prior VIX
        prior_spot = float(prior['close'])

        # Skip invalid data
        if spot_open <= 0 or spot_close <= 0 or vix_open <= 0 or prior_vix <= 0:
            continue

        # Calculate expected moves
        em_today = calculate_expected_move(spot_open, vix_open)
        em_today_pct = (em_today / spot_open * 100) if spot_open > 0 else 0
        em_prior = calculate_expected_move(prior_spot, prior_vix)
        em_prior_pct = (em_prior / prior_spot * 100) if prior_spot > 0 else 0

        # Calculate EM% change (normalized for overnight gaps)
        if em_prior_pct > 0:
            em_change_pct = ((em_today_pct - em_prior_pct) / em_prior_pct) * 100
        else:
            em_change_pct = 0

        # Classify signal
        signal, predicted_sentiment = classify_signal(em_change_pct)

        # Calculate actual outcome
        price_change_pct = ((spot_close - spot_open) / spot_open) * 100
        is_big_move = abs(price_change_pct) > BIG_MOVE_THRESHOLD

        if price_change_pct > BULLISH_MOVE_THRESHOLD:
            actual_sentiment = "BULLISH"
        elif price_change_pct < BEARISH_MOVE_THRESHOLD:
            actual_sentiment = "BEARISH"
        else:
            actual_sentiment = "NEUTRAL"

        # Create day result
        day_result = DayResult(
            date=current['date'].strftime('%Y-%m-%d'),
            spot_open=spot_open,
            spot_close=spot_close,
            vix_open=vix_open,
            prior_vix=prior_vix,
            prior_spot=prior_spot,
            em_today=em_today,
            em_today_pct=em_today_pct,
            em_prior=em_prior,
            em_prior_pct=em_prior_pct,
            em_change_pct=em_change_pct,
            signal=signal,
            predicted_sentiment=predicted_sentiment,
            price_change_pct=price_change_pct,
            actual_sentiment=actual_sentiment,
            is_big_move=is_big_move
        )

        results.day_results.append(day_result)
        results.total_days += 1

        if day_result.signal_correct:
            results.correct_signals += 1

        # Track by signal type
        if signal == "DOWN":
            results.down_signals += 1
            if day_result.signal_correct:
                results.down_correct += 1
            down_moves.append(price_change_pct)
        elif signal == "UP":
            results.up_signals += 1
            if day_result.signal_correct:
                results.up_correct += 1
            up_moves.append(price_change_pct)
        elif signal == "FLAT":
            results.flat_signals += 1
            if day_result.signal_correct:
                results.flat_correct += 1
            flat_moves.append(price_change_pct)
        elif signal == "WIDEN":
            results.widen_signals += 1
            if day_result.signal_correct:
                results.widen_correct += 1
            widen_moves.append(price_change_pct)

        # Track by year
        year = current['date'].year
        if year not in results.by_year:
            results.by_year[year] = {'total': 0, 'correct': 0, 'down': 0, 'up': 0, 'flat': 0, 'widen': 0}
        results.by_year[year]['total'] += 1
        if day_result.signal_correct:
            results.by_year[year]['correct'] += 1
        results.by_year[year][signal.lower()] += 1

        # Verbose output
        if verbose:
            correctness = "✓" if day_result.signal_correct else "✗"
            print(f"{day_result.date}: EM Change {em_change_pct:+.1f}% → {signal} ({predicted_sentiment}) | "
                  f"Price {price_change_pct:+.2f}% ({actual_sentiment}) [{correctness}]")

    # Calculate final statistics
    if results.total_days > 0:
        results.accuracy_pct = (results.correct_signals / results.total_days) * 100

    if results.down_signals > 0:
        results.down_accuracy = (results.down_correct / results.down_signals) * 100
        results.down_avg_move = sum(down_moves) / len(down_moves)
        results.avg_move_when_down = results.down_avg_move

    if results.up_signals > 0:
        results.up_accuracy = (results.up_correct / results.up_signals) * 100
        results.up_avg_move = sum(up_moves) / len(up_moves)
        results.avg_move_when_up = results.up_avg_move

    if results.flat_signals > 0:
        results.flat_accuracy = (results.flat_correct / results.flat_signals) * 100
        results.flat_avg_move = sum(flat_moves) / len(flat_moves) if flat_moves else 0

    if results.widen_signals > 0:
        results.widen_accuracy = (results.widen_correct / results.widen_signals) * 100
        results.widen_avg_move = abs(sum([abs(m) for m in widen_moves]) / len(widen_moves)) if widen_moves else 0

    # Calculate year accuracies
    for year in results.by_year:
        yr = results.by_year[year]
        yr['accuracy'] = (yr['correct'] / yr['total'] * 100) if yr['total'] > 0 else 0

    return results


def print_results(results: BacktestResults):
    """Print formatted backtest results"""

    print(f"\n{'='*60}")
    print("BACKTEST RESULTS")
    print(f"{'='*60}")
    print(f"Period: {results.start_date} to {results.end_date}")
    print(f"Total Trading Days: {results.total_days}")
    print(f"{'='*60}\n")

    # Overall accuracy
    print("OVERALL ACCURACY")
    print("-" * 40)
    print(f"  Correct Signals: {results.correct_signals} / {results.total_days}")
    print(f"  Accuracy: {results.accuracy_pct:.1f}%")
    print()

    # By signal type
    print("ACCURACY BY SIGNAL TYPE")
    print("-" * 40)
    print(f"  DOWN (Bearish):")
    print(f"    Signals: {results.down_signals} ({results.down_signals/results.total_days*100:.1f}%)")
    print(f"    Accuracy: {results.down_accuracy:.1f}%")
    print(f"    Avg Move When DOWN: {results.down_avg_move:+.3f}%")
    print()
    print(f"  UP (Bullish):")
    print(f"    Signals: {results.up_signals} ({results.up_signals/results.total_days*100:.1f}%)")
    print(f"    Accuracy: {results.up_accuracy:.1f}%")
    print(f"    Avg Move When UP: {results.up_avg_move:+.3f}%")
    print()
    print(f"  FLAT (Neutral):")
    print(f"    Signals: {results.flat_signals} ({results.flat_signals/results.total_days*100:.1f}%)")
    print(f"    Accuracy: {results.flat_accuracy:.1f}%")
    print(f"    Avg Move When FLAT: {results.flat_avg_move:+.3f}%")
    print()
    print(f"  WIDEN (Volatile):")
    print(f"    Signals: {results.widen_signals} ({results.widen_signals/results.total_days*100:.1f}%)")
    print(f"    Accuracy: {results.widen_accuracy:.1f}%")
    print(f"    Avg Abs Move When WIDEN: {results.widen_avg_move:.3f}%")
    print()

    # Key finding
    print("KEY EDGE ANALYSIS")
    print("-" * 40)
    edge = results.avg_move_when_up - results.avg_move_when_down
    print(f"  Avg Move When UP Signal: {results.avg_move_when_up:+.3f}%")
    print(f"  Avg Move When DOWN Signal: {results.avg_move_when_down:+.3f}%")
    print(f"  Directional Edge: {edge:+.3f}%")

    if edge > 0:
        print(f"\n  → UP signals have {edge:.3f}% more bullish bias than DOWN signals")
        print(f"  → This {'SUPPORTS' if edge > 0.05 else 'weakly supports'} the hypothesis")
    elif edge < 0:
        print(f"\n  → DOWN signals have {abs(edge):.3f}% more bearish bias than UP signals")
        print(f"  → This {'SUPPORTS' if abs(edge) > 0.05 else 'weakly supports'} the hypothesis")
    else:
        print(f"\n  → No significant directional edge found")

    print()

    # By year
    print("ACCURACY BY YEAR")
    print("-" * 40)
    for year in sorted(results.by_year.keys()):
        yr = results.by_year[year]
        print(f"  {year}: {yr['accuracy']:.1f}% ({yr['correct']}/{yr['total']}) | "
              f"DOWN: {yr['down']}, UP: {yr['up']}, FLAT: {yr['flat']}, WIDEN: {yr['widen']}")
    print()

    # Interpretation
    print("INTERPRETATION")
    print("-" * 40)

    if results.down_accuracy > 55 and results.up_accuracy > 55:
        print("  ✓ STRONG SIGNAL: Both DOWN and UP signals show predictive value")
    elif results.down_accuracy > 55 or results.up_accuracy > 55:
        print("  ~ PARTIAL SIGNAL: One direction shows predictive value")
    else:
        print("  ✗ WEAK SIGNAL: Neither direction shows strong predictive value")

    if abs(edge) > 0.10:
        print(f"  ✓ STRONG EDGE: {abs(edge):.2f}% directional difference is significant")
    elif abs(edge) > 0.05:
        print(f"  ~ MODERATE EDGE: {abs(edge):.2f}% directional difference may be exploitable")
    else:
        print(f"  ✗ WEAK EDGE: {abs(edge):.2f}% directional difference is too small")

    print()


def export_results_to_csv(results: BacktestResults, filename: str = None):
    """Export detailed results to CSV"""
    if filename is None:
        filename = f"em_change_backtest_{results.start_date}_{results.end_date}.csv"

    df = pd.DataFrame([
        {
            'date': r.date,
            'spot_open': r.spot_open,
            'spot_close': r.spot_close,
            'vix_open': r.vix_open,
            'em_today': r.em_today,
            'em_today_pct': r.em_today_pct,
            'em_prior': r.em_prior,
            'em_prior_pct': r.em_prior_pct,
            'em_change_pct': r.em_change_pct,
            'signal': r.signal,
            'predicted_sentiment': r.predicted_sentiment,
            'price_change_pct': r.price_change_pct,
            'actual_sentiment': r.actual_sentiment,
            'is_big_move': r.is_big_move,
            'signal_correct': r.signal_correct
        }
        for r in results.day_results
    ])

    df.to_csv(filename, index=False)
    print(f"Results exported to: {filename}")
    return filename


def main():
    parser = argparse.ArgumentParser(description='Backtest Expected Move Change Signal')
    parser.add_argument('--start', type=str, default='2020-01-01', help='Start date YYYY-MM-DD')
    parser.add_argument('--end', type=str, default=None, help='End date YYYY-MM-DD')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show daily results')
    parser.add_argument('--export', '-e', action='store_true', help='Export results to CSV')
    parser.add_argument('--flat-threshold', type=float, default=FLAT_THRESHOLD,
                        help=f'Threshold for FLAT signal (default: {FLAT_THRESHOLD}%%)')
    parser.add_argument('--widen-threshold', type=float, default=WIDEN_THRESHOLD,
                        help=f'Threshold for WIDEN signal (default: {WIDEN_THRESHOLD}%%)')

    args = parser.parse_args()

    try:
        results = run_backtest(
            start_date=args.start,
            end_date=args.end,
            verbose=args.verbose
        )

        print_results(results)

        if args.export:
            export_results_to_csv(results)

    except Exception as e:
        print(f"Error running backtest: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
