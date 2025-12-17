#!/usr/bin/env python3
"""
Backtest GEX Probability Models
===============================

Historical simulation of the GEX signal generator to validate edge.

Simulates:
- Daily signals based on GEX structure at open
- Bull Call Spread for LONG signals
- Bear Call Spread for SHORT signals
- P&L based on actual price movement

Usage:
    python scripts/backtest_gex_signals.py
    python scripts/backtest_gex_signals.py --start 2023-01-01 --end 2024-12-31

Author: AlphaGEX Quant
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import statistics

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')


@dataclass
class Trade:
    """Represents a single trade"""
    date: str
    symbol: str
    direction: str  # LONG or SHORT
    entry_price: float
    exit_price: float
    spread_type: str
    spread_width: float = 2.0

    # Outcomes
    price_change_pct: float = 0
    won: bool = False
    pnl_pct: float = 0  # Return on risk

    # Context
    direction_confidence: float = 0
    overall_conviction: float = 0
    expected_volatility: float = 0
    gamma_regime: str = ""


@dataclass
class BacktestResults:
    """Backtest performance summary"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0

    total_return_pct: float = 0
    avg_win_pct: float = 0
    avg_loss_pct: float = 0
    profit_factor: float = 0

    long_trades: int = 0
    long_win_rate: float = 0
    short_trades: int = 0
    short_win_rate: float = 0

    max_drawdown_pct: float = 0
    sharpe_ratio: float = 0

    by_regime: Dict = field(default_factory=dict)
    by_month: Dict = field(default_factory=dict)


def get_connection():
    """Get PostgreSQL connection"""
    import psycopg2
    from urllib.parse import urlparse

    database_url = os.getenv('ORAT_DATABASE_URL') or os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL or ORAT_DATABASE_URL not set")

    result = urlparse(database_url)
    return psycopg2.connect(
        host=result.hostname,
        port=result.port or 5432,
        user=result.username,
        password=result.password,
        database=result.path[1:],
        connect_timeout=30
    )


def load_backtest_data(
    symbols: List[str] = ['SPX', 'SPY'],
    start_date: str = '2022-01-01',
    end_date: str = None
) -> pd.DataFrame:
    """Load GEX structure data for backtesting"""
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    conn = get_connection()

    query = """
        SELECT
            trade_date,
            symbol,
            spot_open,
            spot_close,
            spot_high,
            spot_low,
            net_gamma,
            total_call_gamma,
            total_put_gamma,
            flip_point,
            magnet_1_strike,
            magnet_1_gamma,
            magnet_2_strike,
            magnet_2_gamma,
            call_wall,
            put_wall,
            gamma_above_spot,
            gamma_below_spot,
            gamma_imbalance_pct,
            num_magnets_above,
            num_magnets_below,
            nearest_magnet_strike,
            nearest_magnet_distance_pct,
            open_to_flip_distance_pct,
            open_in_pin_zone,
            price_change_pct,
            price_range_pct
        FROM gex_structure_daily
        WHERE symbol = ANY(%s)
          AND trade_date >= %s
          AND trade_date <= %s
          AND price_range_pct > 0
        ORDER BY trade_date, symbol
    """

    df = pd.read_sql(query, conn, params=(symbols, start_date, end_date))
    conn.close()

    # Convert decimals
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = df[col].astype(float)
            except:
                pass

    return df


def build_features_from_row(row: pd.Series, prev_row: Optional[pd.Series] = None) -> Dict:
    """Build ML features from a data row"""
    spot = float(row['spot_open'])
    net_gamma = float(row['net_gamma']) if row['net_gamma'] else 0
    call_wall = float(row['call_wall']) if row['call_wall'] else spot
    put_wall = float(row['put_wall']) if row['put_wall'] else spot
    flip_point = float(row['flip_point']) if row['flip_point'] else spot

    regime = 'POSITIVE' if net_gamma > 0 else 'NEGATIVE'

    features = {
        'gamma_regime_positive': 1 if regime == 'POSITIVE' else 0,
        'gamma_regime_negative': 1 if regime == 'NEGATIVE' else 0,
        'net_gamma_normalized': net_gamma / 1e9 if net_gamma else 0,
        'gamma_imbalance_pct': float(row['gamma_imbalance_pct']) if row['gamma_imbalance_pct'] else 0,
        'top_magnet_concentration': 0.4,
        'flip_distance_normalized': abs(spot - flip_point) / spot * 100 if spot > 0 else 0,
        'near_flip': 1 if abs(spot - flip_point) / spot * 100 < 0.5 else 0,
        'wall_spread_pct': abs(call_wall - put_wall) / spot * 100 if spot > 0 else 0,
        'near_magnet': 0,
        'magnet_distance_normalized': float(row['nearest_magnet_distance_pct']) if row['nearest_magnet_distance_pct'] else 0,
        'num_magnets_above': int(row['num_magnets_above']) if row['num_magnets_above'] else 2,
        'num_magnets_below': int(row['num_magnets_below']) if row['num_magnets_below'] else 2,
        'vix_level': 20,  # Default VIX
        'vix_percentile': 0.5,
        'vix_regime_low': 0,
        'vix_regime_mid': 1,
        'vix_regime_high': 0,
        'gamma_change_1d': 0,
        'gamma_regime_changed': 0,
        'prev_price_change_pct': 0,
        'prev_price_range_pct': 1.0,
        'day_of_week': pd.to_datetime(row['trade_date']).weekday(),
        'is_monday': 1 if pd.to_datetime(row['trade_date']).weekday() == 0 else 0,
        'is_friday': 1 if pd.to_datetime(row['trade_date']).weekday() == 4 else 0,
        'is_opex_week': 1 if 15 <= pd.to_datetime(row['trade_date']).day <= 21 else 0,
        'is_month_end': 1 if pd.to_datetime(row['trade_date']).day >= 25 else 0,
        'open_in_pin_zone': 1 if row['open_in_pin_zone'] else 0,
        'pin_zone_width_pct': abs(call_wall - put_wall) / spot * 100 if spot > 0 else 0,
    }

    # Add momentum if prev row available
    if prev_row is not None:
        prev_net = float(prev_row['net_gamma']) if prev_row['net_gamma'] else 0
        features['gamma_change_1d'] = (net_gamma - prev_net) / 1e9
        prev_regime = 'POSITIVE' if prev_net > 0 else 'NEGATIVE'
        features['gamma_regime_changed'] = 1 if regime != prev_regime else 0
        features['prev_price_change_pct'] = float(prev_row['price_change_pct']) if prev_row['price_change_pct'] else 0
        features['prev_price_range_pct'] = float(prev_row['price_range_pct']) if prev_row['price_range_pct'] else 1.0

    # Calculate gamma ratio
    call_gamma = abs(float(row['total_call_gamma'])) if row['total_call_gamma'] else 0
    put_gamma = abs(float(row['total_put_gamma'])) if row['total_put_gamma'] else 0
    if put_gamma > 0:
        gamma_ratio = call_gamma / put_gamma
    else:
        gamma_ratio = 10.0 if call_gamma > 0 else 1.0
    features['gamma_ratio_log'] = np.log(max(0.1, min(10.0, gamma_ratio)))

    return features


def simulate_spread_trade(
    direction: str,
    entry_price: float,
    close_price: float,
    spread_width: float = 2.0
) -> Tuple[bool, float]:
    """
    Simulate spread P&L based on price movement.

    For Bull Call Spread (LONG):
    - Max profit when price goes UP by spread_width or more
    - Max loss when price goes DOWN

    For Bear Call Spread (SHORT):
    - Max profit when price goes DOWN by spread_width or more
    - Max loss when price goes UP

    Returns: (won, pnl_pct) where pnl_pct is return on risk
    """
    price_move = close_price - entry_price
    move_pct = price_move / entry_price * 100

    if direction == 'LONG':
        # Bull call spread profits when price goes up
        if price_move >= spread_width:
            return True, 100.0  # Max profit = 100% of risk
        elif price_move > 0:
            # Partial profit
            profit_pct = (price_move / spread_width) * 100
            return True, profit_pct
        else:
            # Loss
            loss_pct = min(abs(price_move) / spread_width * 100, 100)
            return False, -loss_pct

    else:  # SHORT
        # Bear call spread profits when price goes down
        if price_move <= -spread_width:
            return True, 100.0  # Max profit
        elif price_move < 0:
            profit_pct = (abs(price_move) / spread_width) * 100
            return True, profit_pct
        else:
            loss_pct = min(price_move / spread_width * 100, 100)
            return False, -loss_pct


def run_backtest(
    symbols: List[str] = ['SPY'],
    start_date: str = '2022-01-01',
    end_date: str = None,
    spread_width: float = 2.0
) -> Tuple[BacktestResults, List[Trade]]:
    """
    Run backtest of GEX signal generator.
    """
    print("=" * 70)
    print("GEX SIGNAL BACKTEST")
    print("=" * 70)
    print(f"Symbols: {symbols}")
    print(f"Date range: {start_date} to {end_date or 'present'}")
    print(f"Spread width: ${spread_width}")

    # Load models
    from quant.gex_probability_models import GEXSignalGenerator

    print("\nLoading models...")
    generator = GEXSignalGenerator()
    try:
        generator.load('models/gex_signal_generator.joblib')
        print("  Models loaded successfully")
    except FileNotFoundError:
        print("  ERROR: Models not found. Run train_gex_probability_models.py first")
        return BacktestResults(), []

    # Load data
    print("\nLoading backtest data...")
    df = load_backtest_data(symbols, start_date, end_date)
    print(f"  Loaded {len(df)} trading days")

    # Run simulation
    print("\nRunning simulation...")
    trades: List[Trade] = []

    for symbol in symbols:
        symbol_df = df[df['symbol'] == symbol].sort_values('trade_date').reset_index(drop=True)

        for i, row in symbol_df.iterrows():
            # Build features
            prev_row = symbol_df.iloc[i-1] if i > 0 else None
            features = build_features_from_row(row, prev_row)

            # Get signal
            try:
                signal = generator.predict(features)
            except Exception as e:
                continue

            # Only trade on LONG or SHORT signals
            if signal.trade_recommendation not in ['LONG', 'SHORT']:
                continue

            # Simulate trade
            entry_price = float(row['spot_open'])
            close_price = float(row['spot_close'])

            won, pnl_pct = simulate_spread_trade(
                signal.trade_recommendation,
                entry_price,
                close_price,
                spread_width
            )

            trade = Trade(
                date=str(row['trade_date']),
                symbol=symbol,
                direction=signal.trade_recommendation,
                entry_price=entry_price,
                exit_price=close_price,
                spread_type='BULL_CALL_SPREAD' if signal.trade_recommendation == 'LONG' else 'BEAR_CALL_SPREAD',
                spread_width=spread_width,
                price_change_pct=float(row['price_change_pct']),
                won=won,
                pnl_pct=pnl_pct,
                direction_confidence=signal.direction_confidence,
                overall_conviction=signal.overall_conviction,
                expected_volatility=signal.expected_volatility_pct,
                gamma_regime='POSITIVE' if features['gamma_regime_positive'] else 'NEGATIVE'
            )
            trades.append(trade)

    print(f"  Generated {len(trades)} trades")

    # Calculate results
    results = calculate_results(trades)

    return results, trades


def calculate_results(trades: List[Trade]) -> BacktestResults:
    """Calculate backtest performance metrics"""
    if not trades:
        return BacktestResults()

    results = BacktestResults()
    results.total_trades = len(trades)
    results.winning_trades = sum(1 for t in trades if t.won)
    results.losing_trades = results.total_trades - results.winning_trades
    results.win_rate = results.winning_trades / results.total_trades if results.total_trades > 0 else 0

    # P&L metrics
    pnls = [t.pnl_pct for t in trades]
    results.total_return_pct = sum(pnls)

    wins = [t.pnl_pct for t in trades if t.won]
    losses = [t.pnl_pct for t in trades if not t.won]

    results.avg_win_pct = statistics.mean(wins) if wins else 0
    results.avg_loss_pct = statistics.mean(losses) if losses else 0

    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    results.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # By direction
    long_trades = [t for t in trades if t.direction == 'LONG']
    short_trades = [t for t in trades if t.direction == 'SHORT']

    results.long_trades = len(long_trades)
    results.long_win_rate = sum(1 for t in long_trades if t.won) / len(long_trades) if long_trades else 0

    results.short_trades = len(short_trades)
    results.short_win_rate = sum(1 for t in short_trades if t.won) / len(short_trades) if short_trades else 0

    # Drawdown
    cumulative = np.cumsum(pnls)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    results.max_drawdown_pct = max(drawdown) if len(drawdown) > 0 else 0

    # Sharpe (simplified - daily returns)
    if len(pnls) > 1:
        daily_std = statistics.stdev(pnls)
        daily_mean = statistics.mean(pnls)
        results.sharpe_ratio = (daily_mean / daily_std * np.sqrt(252)) if daily_std > 0 else 0

    # By regime
    pos_gamma_trades = [t for t in trades if t.gamma_regime == 'POSITIVE']
    neg_gamma_trades = [t for t in trades if t.gamma_regime == 'NEGATIVE']

    results.by_regime = {
        'POSITIVE': {
            'trades': len(pos_gamma_trades),
            'win_rate': sum(1 for t in pos_gamma_trades if t.won) / len(pos_gamma_trades) if pos_gamma_trades else 0,
            'avg_pnl': statistics.mean([t.pnl_pct for t in pos_gamma_trades]) if pos_gamma_trades else 0
        },
        'NEGATIVE': {
            'trades': len(neg_gamma_trades),
            'win_rate': sum(1 for t in neg_gamma_trades if t.won) / len(neg_gamma_trades) if neg_gamma_trades else 0,
            'avg_pnl': statistics.mean([t.pnl_pct for t in neg_gamma_trades]) if neg_gamma_trades else 0
        }
    }

    return results


def print_results(results: BacktestResults, trades: List[Trade]):
    """Print backtest results"""
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)

    print(f"\n  Total Trades:     {results.total_trades}")
    print(f"  Winning Trades:   {results.winning_trades}")
    print(f"  Losing Trades:    {results.losing_trades}")
    print(f"  Win Rate:         {results.win_rate:.1%}")

    print(f"\n  Total Return:     {results.total_return_pct:.1f}%")
    print(f"  Avg Win:          {results.avg_win_pct:.1f}%")
    print(f"  Avg Loss:         {results.avg_loss_pct:.1f}%")
    print(f"  Profit Factor:    {results.profit_factor:.2f}")

    print(f"\n  LONG Trades:      {results.long_trades} ({results.long_win_rate:.1%} win rate)")
    print(f"  SHORT Trades:     {results.short_trades} ({results.short_win_rate:.1%} win rate)")

    print(f"\n  Max Drawdown:     {results.max_drawdown_pct:.1f}%")
    print(f"  Sharpe Ratio:     {results.sharpe_ratio:.2f}")

    print("\n  By Gamma Regime:")
    for regime, stats in results.by_regime.items():
        print(f"    {regime}: {stats['trades']} trades, {stats['win_rate']:.1%} win, {stats['avg_pnl']:.1f}% avg P&L")

    # Recent trades
    if trades:
        print("\n  Recent Trades:")
        for trade in trades[-10:]:
            status = "WIN" if trade.won else "LOSS"
            print(f"    {trade.date} {trade.symbol} {trade.direction}: {trade.pnl_pct:+.1f}% ({status})")


def main():
    parser = argparse.ArgumentParser(description='Backtest GEX Signal Generator')
    parser.add_argument('--symbols', type=str, nargs='+', default=['SPY'],
                        help='Symbols to backtest')
    parser.add_argument('--start', type=str, default='2022-01-01',
                        help='Start date')
    parser.add_argument('--end', type=str, default=None,
                        help='End date')
    parser.add_argument('--spread-width', type=float, default=2.0,
                        help='Spread width in dollars')
    parser.add_argument('--output', type=str, default=None,
                        help='CSV output file for trades')
    args = parser.parse_args()

    results, trades = run_backtest(
        symbols=args.symbols,
        start_date=args.start,
        end_date=args.end,
        spread_width=args.spread_width
    )

    print_results(results, trades)

    # Save trades to CSV if requested
    if args.output and trades:
        df = pd.DataFrame([vars(t) for t in trades])
        df.to_csv(args.output, index=False)
        print(f"\nTrades saved to {args.output}")

    print("\n" + "=" * 70)
    print("BACKTEST COMPLETE")
    print("=" * 70)

    return results, trades


if __name__ == '__main__':
    main()
