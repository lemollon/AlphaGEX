#!/usr/bin/env python3
"""
Quant Validation with REAL Historical Data
==========================================

This script connects to your actual PostgreSQL database and validates:
1. Gamma wall prediction accuracy (call_wall as resistance, put_wall as support)
2. Sharpe ratio on real trading returns
3. GEX regime prediction accuracy
4. Strategy performance analysis

Run from AlphaGEX directory:
    python3 scripts/validate_with_real_data.py
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
from database_adapter import get_connection


def print_header(title: str):
    print(f"\n{'='*70}")
    print(f" {title}")
    print(f"{'='*70}")


def print_section(title: str):
    print(f"\n  {title}")
    print(f"  {'-'*50}")


# =============================================================================
# 1. GAMMA WALL PREDICTION VALIDATION
# =============================================================================

def validate_gamma_walls():
    """Validate call_wall as resistance and put_wall as support using real data"""
    print_header("GAMMA WALL PREDICTION ACCURACY (Real Data)")

    conn = get_connection()

    # Get GEX history with next-day price movement
    query = """
        SELECT
            g1.timestamp,
            g1.symbol,
            g1.spot_price,
            g1.call_wall,
            g1.put_wall,
            g1.flip_point,
            g1.net_gex,
            g2.spot_price as next_spot_price,
            (g2.spot_price - g1.spot_price) / g1.spot_price * 100 as price_change_pct
        FROM gex_history g1
        JOIN gex_history g2 ON g1.symbol = g2.symbol
            AND DATE(g2.timestamp) = DATE(g1.timestamp) + INTERVAL '1 day'
        WHERE g1.call_wall IS NOT NULL
            AND g1.put_wall IS NOT NULL
            AND g1.spot_price > 0
        ORDER BY g1.timestamp DESC
        LIMIT 500
    """

    try:
        df = pd.read_sql_query(query, conn.raw_connection)
        conn.close()
    except Exception as e:
        print(f"  Error querying database: {e}")
        conn.close()
        return None

    if df.empty:
        print("  No GEX history data found in database")
        return None

    print(f"  Analyzing {len(df)} days of GEX data...")

    # Validate Call Wall as Resistance
    print_section("CALL WALL AS RESISTANCE")

    # Days where price approached call wall (within 1%)
    df['near_call_wall'] = (df['call_wall'] - df['spot_price']) / df['spot_price'] < 0.01
    near_call = df[df['near_call_wall']]

    if len(near_call) > 0:
        # Did price reject (stay below or reverse)?
        rejected = near_call[near_call['next_spot_price'] < near_call['call_wall']]
        call_wall_accuracy = len(rejected) / len(near_call) * 100

        print(f"    Days near call wall: {len(near_call)}")
        print(f"    Days price rejected: {len(rejected)}")
        print(f"    Accuracy: {call_wall_accuracy:.1f}%")
        print(f"    Statistically significant: {'Yes' if len(near_call) >= 30 else 'No (need 30+ samples)'}")
    else:
        print("    No instances of price near call wall")
        call_wall_accuracy = None

    # Validate Put Wall as Support
    print_section("PUT WALL AS SUPPORT")

    # Days where price approached put wall (within 1%)
    df['near_put_wall'] = (df['spot_price'] - df['put_wall']) / df['spot_price'] < 0.01
    near_put = df[df['near_put_wall']]

    if len(near_put) > 0:
        # Did price bounce (stay above or reverse up)?
        bounced = near_put[near_put['next_spot_price'] > near_put['put_wall']]
        put_wall_accuracy = len(bounced) / len(near_put) * 100

        print(f"    Days near put wall: {len(near_put)}")
        print(f"    Days price bounced: {len(bounced)}")
        print(f"    Accuracy: {put_wall_accuracy:.1f}%")
        print(f"    Statistically significant: {'Yes' if len(near_put) >= 30 else 'No (need 30+ samples)'}")
    else:
        print("    No instances of price near put wall")
        put_wall_accuracy = None

    # Validate Flip Point Behavior
    print_section("FLIP POINT VOLATILITY ANALYSIS")

    # Above flip should have lower volatility (positive gamma environment)
    above_flip = df[df['spot_price'] > df['flip_point']]
    below_flip = df[df['spot_price'] < df['flip_point']]

    if len(above_flip) > 10 and len(below_flip) > 10:
        vol_above = above_flip['price_change_pct'].abs().mean()
        vol_below = below_flip['price_change_pct'].abs().mean()

        print(f"    Days above flip: {len(above_flip)}")
        print(f"    Days below flip: {len(below_flip)}")
        print(f"    Avg volatility above flip: {vol_above:.2f}%")
        print(f"    Avg volatility below flip: {vol_below:.2f}%")
        print(f"    Theory holds (lower vol above): {'Yes' if vol_above < vol_below else 'No'}")

        # T-test for significance
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(
            above_flip['price_change_pct'].abs(),
            below_flip['price_change_pct'].abs()
        )
        print(f"    P-value: {p_value:.4f}")
        print(f"    Statistically significant: {'Yes' if p_value < 0.05 else 'No'}")
    else:
        print("    Insufficient data for flip point analysis")

    return {
        'call_wall_accuracy': call_wall_accuracy,
        'put_wall_accuracy': put_wall_accuracy,
        'total_samples': len(df)
    }


# =============================================================================
# 2. SHARPE RATIO ON REAL TRADING RETURNS
# =============================================================================

def analyze_real_trading_returns():
    """Calculate Sharpe ratio on actual trading P&L from database"""
    print_header("SHARPE RATIO ANALYSIS (Real Trading Data)")

    conn = get_connection()

    # Get closed positions with P&L
    query = """
        SELECT
            closed_at::date as trade_date,
            symbol,
            strategy,
            pnl,
            entry_price,
            exit_price
        FROM positions
        WHERE status = 'CLOSED'
            AND pnl IS NOT NULL
            AND closed_at IS NOT NULL
        ORDER BY closed_at
    """

    try:
        positions_df = pd.read_sql_query(query, conn.raw_connection)
    except Exception as e:
        print(f"  Error querying positions: {e}")
        positions_df = pd.DataFrame()

    # Also get autonomous positions
    query2 = """
        SELECT
            closed_date::date as trade_date,
            symbol,
            strategy,
            realized_pnl as pnl,
            entry_price,
            exit_price
        FROM autonomous_positions
        WHERE status = 'CLOSED'
            AND realized_pnl IS NOT NULL
            AND closed_date IS NOT NULL
        ORDER BY closed_date
    """

    try:
        auto_df = pd.read_sql_query(query2, conn.raw_connection)
    except Exception as e:
        print(f"  Error querying autonomous_positions: {e}")
        auto_df = pd.DataFrame()

    conn.close()

    # Combine both sources
    df = pd.concat([positions_df, auto_df], ignore_index=True)

    if df.empty:
        print("  No closed positions found in database")
        return None

    print(f"  Analyzing {len(df)} closed trades...")

    # Calculate daily returns
    daily_pnl = df.groupby('trade_date')['pnl'].sum()

    if len(daily_pnl) < 10:
        print(f"  Only {len(daily_pnl)} trading days - need more data for reliable Sharpe")
        return None

    # Calculate Sharpe ratio (annualized)
    returns = daily_pnl.values
    avg_return = np.mean(returns)
    std_return = np.std(returns, ddof=1)

    if std_return == 0:
        print("  Zero standard deviation - cannot calculate Sharpe")
        return None

    # Daily Sharpe * sqrt(252) for annualized
    daily_sharpe = avg_return / std_return
    annualized_sharpe = daily_sharpe * np.sqrt(252)

    # Bootstrap confidence interval
    n_bootstrap = 1000
    bootstrap_sharpes = []
    for _ in range(n_bootstrap):
        sample = np.random.choice(returns, size=len(returns), replace=True)
        if np.std(sample) > 0:
            bootstrap_sharpes.append(np.mean(sample) / np.std(sample) * np.sqrt(252))

    ci_lower = np.percentile(bootstrap_sharpes, 2.5)
    ci_upper = np.percentile(bootstrap_sharpes, 97.5)

    print_section("SHARPE RATIO RESULTS")
    print(f"    Trading days: {len(daily_pnl)}")
    print(f"    Total trades: {len(df)}")
    print(f"    Total P&L: ${df['pnl'].sum():,.2f}")
    print(f"    Avg daily P&L: ${avg_return:,.2f}")
    print(f"    Daily Std Dev: ${std_return:,.2f}")
    print(f"    Annualized Sharpe: {annualized_sharpe:.2f}")
    print(f"    95% CI: [{ci_lower:.2f}, {ci_upper:.2f}]")
    print(f"    Statistically significant: {'Yes' if ci_lower > 0 else 'No'}")

    # Win rate analysis
    print_section("WIN RATE ANALYSIS")
    winning = df[df['pnl'] > 0]
    losing = df[df['pnl'] <= 0]

    win_rate = len(winning) / len(df) * 100
    avg_win = winning['pnl'].mean() if len(winning) > 0 else 0
    avg_loss = losing['pnl'].mean() if len(losing) > 0 else 0

    print(f"    Winning trades: {len(winning)} ({win_rate:.1f}%)")
    print(f"    Losing trades: {len(losing)} ({100-win_rate:.1f}%)")
    print(f"    Average win: ${avg_win:,.2f}")
    print(f"    Average loss: ${avg_loss:,.2f}")

    if avg_loss != 0:
        profit_factor = abs(winning['pnl'].sum() / losing['pnl'].sum()) if losing['pnl'].sum() != 0 else float('inf')
        print(f"    Profit factor: {profit_factor:.2f}")

    # Max drawdown
    cumulative = daily_pnl.cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    max_dd = drawdown.min()

    print(f"    Max drawdown: ${max_dd:,.2f}")

    # Strategy breakdown
    print_section("PERFORMANCE BY STRATEGY")
    strategy_perf = df.groupby('strategy').agg({
        'pnl': ['count', 'sum', 'mean'],
    })
    strategy_perf.columns = ['trades', 'total_pnl', 'avg_pnl']
    strategy_perf['win_rate'] = df.groupby('strategy').apply(
        lambda x: (x['pnl'] > 0).sum() / len(x) * 100
    )
    strategy_perf = strategy_perf.sort_values('total_pnl', ascending=False)

    for strategy, row in strategy_perf.iterrows():
        print(f"    {strategy or 'Unknown'}:")
        print(f"      Trades: {int(row['trades'])}, Win Rate: {row['win_rate']:.1f}%, Total P&L: ${row['total_pnl']:,.2f}")

    return {
        'sharpe': annualized_sharpe,
        'ci_lower': ci_lower,
        'ci_upper': ci_upper,
        'total_pnl': df['pnl'].sum(),
        'win_rate': win_rate
    }


# =============================================================================
# 3. GEX REGIME PREDICTION ACCURACY
# =============================================================================

def analyze_gex_regime_predictions():
    """Analyze if GEX regime correctly predicts market behavior"""
    print_header("GEX REGIME PREDICTION ACCURACY")

    conn = get_connection()

    query = """
        SELECT
            g1.timestamp,
            g1.symbol,
            g1.spot_price,
            g1.net_gex,
            g1.regime,
            g2.spot_price as next_spot_price,
            (g2.spot_price - g1.spot_price) / g1.spot_price * 100 as price_change_pct
        FROM gex_history g1
        JOIN gex_history g2 ON g1.symbol = g2.symbol
            AND DATE(g2.timestamp) = DATE(g1.timestamp) + INTERVAL '1 day'
        WHERE g1.net_gex IS NOT NULL
        ORDER BY g1.timestamp DESC
        LIMIT 500
    """

    try:
        df = pd.read_sql_query(query, conn.raw_connection)
        conn.close()
    except Exception as e:
        print(f"  Error querying database: {e}")
        conn.close()
        return None

    if df.empty:
        print("  No GEX regime data found")
        return None

    print(f"  Analyzing {len(df)} days of regime data...")

    # Classify regimes
    df['is_positive_gex'] = df['net_gex'] > 0
    df['is_large_move'] = df['price_change_pct'].abs() > 1.0  # >1% move

    print_section("POSITIVE GEX = LOWER VOLATILITY")

    pos_gex = df[df['is_positive_gex']]
    neg_gex = df[~df['is_positive_gex']]

    if len(pos_gex) > 10 and len(neg_gex) > 10:
        vol_pos = pos_gex['price_change_pct'].abs().mean()
        vol_neg = neg_gex['price_change_pct'].abs().mean()
        large_moves_pos = pos_gex['is_large_move'].sum() / len(pos_gex) * 100
        large_moves_neg = neg_gex['is_large_move'].sum() / len(neg_gex) * 100

        print(f"    Positive GEX days: {len(pos_gex)}")
        print(f"    Negative GEX days: {len(neg_gex)}")
        print(f"    Avg volatility (positive GEX): {vol_pos:.2f}%")
        print(f"    Avg volatility (negative GEX): {vol_neg:.2f}%")
        print(f"    Large moves (positive GEX): {large_moves_pos:.1f}%")
        print(f"    Large moves (negative GEX): {large_moves_neg:.1f}%")
        print(f"    Theory holds (lower vol when positive): {'Yes' if vol_pos < vol_neg else 'No'}")

        # Statistical test
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(
            pos_gex['price_change_pct'].abs(),
            neg_gex['price_change_pct'].abs()
        )
        print(f"    P-value: {p_value:.4f}")
        print(f"    Statistically significant: {'Yes' if p_value < 0.05 else 'No'}")
    else:
        print("    Insufficient data for regime analysis")

    return {'positive_gex_days': len(pos_gex), 'negative_gex_days': len(neg_gex)}


# =============================================================================
# 4. BACKTEST RESULTS ANALYSIS
# =============================================================================

def analyze_backtest_results():
    """Analyze stored backtest results"""
    print_header("HISTORICAL BACKTEST RESULTS")

    conn = get_connection()

    query = """
        SELECT
            strategy_name,
            symbol,
            total_trades,
            win_rate,
            expectancy_pct,
            total_return_pct,
            max_drawdown_pct,
            sharpe_ratio,
            timestamp
        FROM backtest_results
        ORDER BY timestamp DESC
        LIMIT 50
    """

    try:
        df = pd.read_sql_query(query, conn.raw_connection)
        conn.close()
    except Exception as e:
        print(f"  Error querying backtest_results: {e}")
        conn.close()
        return None

    if df.empty:
        print("  No backtest results found in database")
        return None

    print(f"  Found {len(df)} backtest runs\n")

    for _, row in df.head(10).iterrows():
        print(f"  {row['strategy_name']} ({row['symbol']}):")
        print(f"    Trades: {row['total_trades']}, Win Rate: {row['win_rate']:.1f}%")
        print(f"    Sharpe: {row['sharpe_ratio']:.2f}, Max DD: {row['max_drawdown_pct']:.1f}%")
        print(f"    Total Return: {row['total_return_pct']:.1f}%")
        print()

    return df


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("\n" + "="*70)
    print("     ALPHAGEX REAL DATA VALIDATION")
    print("     Using PostgreSQL Database")
    print("="*70)

    results = {}

    # Run all validations
    try:
        results['gamma_walls'] = validate_gamma_walls()
    except Exception as e:
        print(f"\n  Gamma wall validation error: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['sharpe'] = analyze_real_trading_returns()
    except Exception as e:
        print(f"\n  Sharpe analysis error: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['regime'] = analyze_gex_regime_predictions()
    except Exception as e:
        print(f"\n  Regime analysis error: {e}")
        import traceback
        traceback.print_exc()

    try:
        results['backtest'] = analyze_backtest_results()
    except Exception as e:
        print(f"\n  Backtest analysis error: {e}")
        import traceback
        traceback.print_exc()

    # Summary
    print_header("VALIDATION SUMMARY")

    if results.get('gamma_walls'):
        gw = results['gamma_walls']
        print(f"  Gamma Wall Prediction:")
        if gw.get('call_wall_accuracy'):
            print(f"    Call Wall Resistance: {gw['call_wall_accuracy']:.1f}% accurate")
        if gw.get('put_wall_accuracy'):
            print(f"    Put Wall Support: {gw['put_wall_accuracy']:.1f}% accurate")

    if results.get('sharpe'):
        s = results['sharpe']
        sig = "SIGNIFICANT" if s['ci_lower'] > 0 else "NOT significant"
        print(f"  Trading Performance:")
        print(f"    Sharpe Ratio: {s['sharpe']:.2f} ({sig})")
        print(f"    Win Rate: {s['win_rate']:.1f}%")
        print(f"    Total P&L: ${s['total_pnl']:,.2f}")

    print("\n" + "="*70)
    print("  Validation complete. Review results above.")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
