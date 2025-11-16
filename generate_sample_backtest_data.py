"""
Generate Sample Backtest Data for Strategy Backtesting Page

Creates realistic backtest results so users can immediately see and use:
- Smart Strategy Picker
- Freshness indicators
- Confidence scores
- All new features

Run this once to populate the database with sample data.
Replace with real backtests when Polygon API is available.
"""

import sqlite3
from datetime import datetime, timedelta
from config_and_database import DB_PATH

# Sample backtest data - realistic performance metrics
sample_strategies = [
    # Psychology Trap Strategies (13 patterns)
    {
        'strategy_name': 'LIBERATION_TRAP_SHORT_CALLS',
        'total_trades': 142,
        'win_rate': 73.2,
        'expectancy_pct': 1.23,
        'avg_win_pct': 2.8,
        'avg_loss_pct': -1.1,
        'max_drawdown_pct': -8.5,
        'sharpe_ratio': 1.85,
        'total_return_pct': 174.66
    },
    {
        'strategy_name': 'BEAR_TRAP_BOUNCE_LONG_CALLS',
        'total_trades': 98,
        'win_rate': 68.4,
        'expectancy_pct': 0.95,
        'avg_win_pct': 3.2,
        'avg_loss_pct': -1.5,
        'max_drawdown_pct': -12.3,
        'sharpe_ratio': 1.42,
        'total_return_pct': 93.10
    },
    {
        'strategy_name': 'FALSE_FLOOR_REJECTION_SHORT_PUTS',
        'total_trades': 76,
        'win_rate': 71.1,
        'expectancy_pct': 1.05,
        'avg_win_pct': 2.5,
        'avg_loss_pct': -1.3,
        'max_drawdown_pct': -9.8,
        'sharpe_ratio': 1.58,
        'total_return_pct': 79.80
    },
    {
        'strategy_name': 'GAMMA_SQUEEZE_CASCADE_FADE',
        'total_trades': 54,
        'win_rate': 62.9,
        'expectancy_pct': 0.72,
        'avg_win_pct': 2.9,
        'avg_loss_pct': -1.8,
        'max_drawdown_pct': -15.2,
        'sharpe_ratio': 1.12,
        'total_return_pct': 38.88
    },
    {
        'strategy_name': 'FLIP_POINT_STRADDLE',
        'total_trades': 45,
        'win_rate': 58.8,
        'expectancy_pct': 0.45,
        'avg_win_pct': 3.5,
        'avg_loss_pct': -2.1,
        'max_drawdown_pct': -18.5,
        'sharpe_ratio': 0.88,
        'total_return_pct': 20.25
    },

    # GEX Strategies (5 strategies)
    {
        'strategy_name': 'GEX_WALL_BOUNCE_REVERSAL',
        'total_trades': 118,
        'win_rate': 69.5,
        'expectancy_pct': 0.89,
        'avg_win_pct': 2.6,
        'avg_loss_pct': -1.4,
        'max_drawdown_pct': -10.2,
        'sharpe_ratio': 1.52,
        'total_return_pct': 105.02
    },
    {
        'strategy_name': 'NEGATIVE_GEX_AMPLIFICATION',
        'total_trades': 87,
        'win_rate': 64.4,
        'expectancy_pct': 0.78,
        'avg_win_pct': 2.9,
        'avg_loss_pct': -1.6,
        'max_drawdown_pct': -13.8,
        'sharpe_ratio': 1.28,
        'total_return_pct': 67.86
    },
    {
        'strategy_name': 'ZERO_GEX_BREAKOUT',
        'total_trades': 62,
        'win_rate': 61.3,
        'expectancy_pct': 0.68,
        'avg_win_pct': 3.1,
        'avg_loss_pct': -1.9,
        'max_drawdown_pct': -16.5,
        'sharpe_ratio': 1.05,
        'total_return_pct': 42.16
    },
    {
        'strategy_name': 'POSITIVE_GEX_MEAN_REVERSION',
        'total_trades': 95,
        'win_rate': 66.3,
        'expectancy_pct': 0.82,
        'avg_win_pct': 2.4,
        'avg_loss_pct': -1.2,
        'max_drawdown_pct': -11.5,
        'sharpe_ratio': 1.38,
        'total_return_pct': 77.90
    },
    {
        'strategy_name': 'GEX_VOLATILITY_CRUSH',
        'total_trades': 71,
        'win_rate': 59.2,
        'expectancy_pct': 0.52,
        'avg_win_pct': 2.7,
        'avg_loss_pct': -1.7,
        'max_drawdown_pct': -14.2,
        'sharpe_ratio': 0.95,
        'total_return_pct': 36.92
    },

    # Options Strategies (11 strategies)
    {
        'strategy_name': 'IRON_CONDOR_HIGH_IV',
        'total_trades': 156,
        'win_rate': 75.6,
        'expectancy_pct': 0.65,
        'avg_win_pct': 1.8,
        'avg_loss_pct': -2.5,
        'max_drawdown_pct': -9.2,
        'sharpe_ratio': 1.68,
        'total_return_pct': 101.40
    },
    {
        'strategy_name': 'CREDIT_SPREAD_AT_WALLS',
        'total_trades': 134,
        'win_rate': 72.4,
        'expectancy_pct': 0.78,
        'avg_win_pct': 2.1,
        'avg_loss_pct': -1.8,
        'max_drawdown_pct': -10.5,
        'sharpe_ratio': 1.55,
        'total_return_pct': 104.52
    },
    {
        'strategy_name': 'STRANGLE_VIX_SPIKE',
        'total_trades': 48,
        'win_rate': 56.2,
        'expectancy_pct': 0.38,
        'avg_win_pct': 4.2,
        'avg_loss_pct': -2.8,
        'max_drawdown_pct': -19.8,
        'sharpe_ratio': 0.72,
        'total_return_pct': 18.24
    },
    {
        'strategy_name': 'BUTTERFLY_EARNINGS',
        'total_trades': 39,
        'win_rate': 53.8,
        'expectancy_pct': 0.25,
        'avg_win_pct': 3.8,
        'avg_loss_pct': -3.2,
        'max_drawdown_pct': -21.5,
        'sharpe_ratio': 0.58,
        'total_return_pct': 9.75
    },
    {
        'strategy_name': 'CALENDAR_SPREAD_THETA',
        'total_trades': 89,
        'win_rate': 67.4,
        'expectancy_pct': 0.58,
        'avg_win_pct': 2.2,
        'avg_loss_pct': -1.6,
        'max_drawdown_pct': -12.8,
        'sharpe_ratio': 1.18,
        'total_return_pct': 51.62
    },
    {
        'strategy_name': 'POOR_MANS_COVERED_CALL',
        'total_trades': 112,
        'win_rate': 70.5,
        'expectancy_pct': 0.72,
        'avg_win_pct': 2.3,
        'avg_loss_pct': -1.5,
        'max_drawdown_pct': -11.2,
        'sharpe_ratio': 1.45,
        'total_return_pct': 80.64
    },
    {
        'strategy_name': 'RATIO_SPREAD_SKEW',
        'total_trades': 65,
        'win_rate': 60.0,
        'expectancy_pct': 0.48,
        'avg_win_pct': 2.8,
        'avg_loss_pct': -2.0,
        'max_drawdown_pct': -15.8,
        'sharpe_ratio': 0.92,
        'total_return_pct': 31.20
    },
    {
        'strategy_name': 'JADE_LIZARD_NEUTRAL',
        'total_trades': 78,
        'win_rate': 64.1,
        'expectancy_pct': 0.62,
        'avg_win_pct': 2.5,
        'avg_loss_pct': -1.8,
        'max_drawdown_pct': -13.5,
        'sharpe_ratio': 1.08,
        'total_return_pct': 48.36
    },
    {
        'strategy_name': 'DIAGONAL_SPREAD_DELTA',
        'total_trades': 92,
        'win_rate': 65.2,
        'expectancy_pct': 0.68,
        'avg_win_pct': 2.4,
        'avg_loss_pct': -1.7,
        'max_drawdown_pct': -12.5,
        'sharpe_ratio': 1.22,
        'total_return_pct': 62.56
    },
    {
        'strategy_name': 'WHEEL_STRATEGY_ASSIGNMENT',
        'total_trades': 105,
        'win_rate': 68.6,
        'expectancy_pct': 0.55,
        'avg_win_pct': 1.9,
        'avg_loss_pct': -1.4,
        'max_drawdown_pct': -10.8,
        'sharpe_ratio': 1.32,
        'total_return_pct': 57.75
    },
    {
        'strategy_name': 'COVERED_STRANGLE_PREMIUM',
        'total_trades': 86,
        'win_rate': 62.8,
        'expectancy_pct': 0.48,
        'avg_win_pct': 2.1,
        'avg_loss_pct': -1.8,
        'max_drawdown_pct': -14.2,
        'sharpe_ratio': 0.98,
        'total_return_pct': 41.28
    },
]

def generate_sample_data():
    """Generate and insert sample backtest data"""

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Clear existing data
    c.execute('DELETE FROM backtest_results')

    # Insert sample data
    now = datetime.now()

    for i, strategy in enumerate(sample_strategies):
        # Vary timestamps (most recent in last 7 days, some older)
        if i < 10:
            days_ago = i % 7  # Fresh data
        elif i < 20:
            days_ago = 7 + (i % 20)  # Recent data
        else:
            days_ago = 30 + (i % 10)  # Stale data

        timestamp = (now - timedelta(days=days_ago)).strftime('%Y-%m-%d %H:%M:%S')

        # Test period: 1 year of backtesting
        end_date = (now - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        start_date = (now - timedelta(days=days_ago + 365)).strftime('%Y-%m-%d')

        # Calculate derived metrics
        winning_trades = int(strategy['total_trades'] * strategy['win_rate'] / 100)
        losing_trades = strategy['total_trades'] - winning_trades

        # Largest wins/losses (typically 2-3x average)
        largest_win_pct = strategy['avg_win_pct'] * 2.5
        largest_loss_pct = strategy['avg_loss_pct'] * 2.3

        # Average trade duration (options: 3-21 days)
        avg_trade_duration = 7.0 + (i % 14)

        c.execute('''
            INSERT INTO backtest_results (
                timestamp, strategy_name, symbol,
                start_date, end_date,
                total_trades, winning_trades, losing_trades,
                win_rate, avg_win_pct, avg_loss_pct,
                largest_win_pct, largest_loss_pct,
                expectancy_pct, total_return_pct,
                max_drawdown_pct, sharpe_ratio,
                avg_trade_duration_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            timestamp,
            strategy['strategy_name'],
            'SPY',
            start_date,
            end_date,
            strategy['total_trades'],
            winning_trades,
            losing_trades,
            strategy['win_rate'],
            strategy['avg_win_pct'],
            strategy['avg_loss_pct'],
            largest_win_pct,
            largest_loss_pct,
            strategy['expectancy_pct'],
            strategy['total_return_pct'],
            strategy['max_drawdown_pct'],
            strategy['sharpe_ratio'],
            avg_trade_duration
        ))

    conn.commit()

    # Verify
    c.execute('SELECT COUNT(*) FROM backtest_results')
    count = c.fetchone()[0]

    print(f"✅ Successfully inserted {count} sample backtest results")
    print(f"\nBreakdown:")
    print(f"  - Psychology Strategies: 5")
    print(f"  - GEX Strategies: 5")
    print(f"  - Options Strategies: 11")
    print(f"  - TOTAL: {count}")

    # Show top 3 performers
    c.execute('''
        SELECT strategy_name, win_rate, expectancy_pct, total_return_pct
        FROM backtest_results
        ORDER BY expectancy_pct DESC
        LIMIT 3
    ''')

    print(f"\n🏆 Top 3 Strategies by Expectancy:")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1]:.1f}% WR, {row[2]:.2f}% Exp, {row[3]:.2f}% Return")

    conn.close()

    print(f"\n✅ Sample data ready!")
    print(f"Visit /backtesting to see Smart Strategy Picker in action")

if __name__ == '__main__':
    generate_sample_data()
