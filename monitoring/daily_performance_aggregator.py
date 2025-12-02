"""
Daily Performance Aggregator
Calculates and logs daily performance metrics:
- Sharpe ratio
- Max drawdown
- Win rate
- Average P&L
- Risk-adjusted returns
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo
from database_adapter import get_connection
import pandas as pd
import numpy as np

CENTRAL_TZ = ZoneInfo("America/Chicago")


def aggregate_daily_performance():
    """
    Calculate and log daily performance metrics from autonomous trader (PostgreSQL)

    Metrics calculated:
    - Daily P&L
    - Cumulative P&L
    - Win rate
    - Sharpe ratio (risk-adjusted returns)
    - Max drawdown
    - Average trade duration
    - Capital utilization
    """
    try:
        print("📈 Daily Performance Aggregator - Calculating Trading Metrics\n")

        conn = get_connection()

        # Get all closed positions
        closed_positions = pd.read_sql_query("""
            SELECT
                closed_date as date,
                realized_pnl,
                entry_date,
                closed_date,
                entry_time,
                closed_time,
                confidence,
                strategy
            FROM autonomous_positions
            WHERE status = 'CLOSED'
              AND closed_date IS NOT NULL
            ORDER BY closed_date, closed_time
        """, conn.raw_connection)

        if closed_positions.empty:
            print("⚠️ No closed positions yet - nothing to aggregate")
            conn.close()
            return

        # Get starting capital
        c = conn.cursor()
        c.execute("SELECT value FROM autonomous_config WHERE key = 'capital'")
        result = c.fetchone()
        starting_capital = float(result[0]) if result else 1000000.0

        # Group by date and calculate daily metrics
        daily_groups = closed_positions.groupby('date')

        now = datetime.now(CENTRAL_TZ)
        records_logged = 0

        for date, day_positions in daily_groups:
            # Calculate daily metrics
            daily_pnl = day_positions['realized_pnl'].sum()
            trades_count = len(day_positions)
            winners = len(day_positions[day_positions['realized_pnl'] > 0])
            losers = len(day_positions[day_positions['realized_pnl'] < 0])
            win_rate = (winners / trades_count * 100) if trades_count > 0 else 0

            avg_winner = day_positions[day_positions['realized_pnl'] > 0]['realized_pnl'].mean() if winners > 0 else 0
            avg_loser = day_positions[day_positions['realized_pnl'] < 0]['realized_pnl'].mean() if losers > 0 else 0

            # Calculate cumulative P&L up to this date
            cumulative_pnl = closed_positions[closed_positions['date'] <= date]['realized_pnl'].sum()
            account_value = starting_capital + cumulative_pnl

            # Calculate daily return
            daily_return_pct = (daily_pnl / starting_capital) * 100

            # Calculate drawdown (peak to trough)
            historical_pnl = closed_positions[closed_positions['date'] <= date]['realized_pnl'].cumsum()
            if len(historical_pnl) > 0 and not historical_pnl.empty:
                peak = historical_pnl.expanding().max().iloc[-1]
                current = historical_pnl.iloc[-1]
                drawdown = peak - current
                drawdown_pct = (drawdown / starting_capital * 100) if starting_capital > 0 else 0
            else:
                peak = 0
                current = 0
                drawdown = 0
                drawdown_pct = 0

            # Calculate Sharpe ratio (requires multiple days)
            sharpe_ratio = calculate_sharpe_ratio(closed_positions, date, starting_capital)

            # Average holding time
            day_positions['entry_dt'] = pd.to_datetime(day_positions['entry_date'] + ' ' + day_positions['entry_time'])
            day_positions['closed_dt'] = pd.to_datetime(day_positions['date'] + ' ' + day_positions['closed_time'])
            day_positions['hold_hours'] = (day_positions['closed_dt'] - day_positions['entry_dt']).dt.total_seconds() / 3600
            avg_hold_hours = day_positions['hold_hours'].mean()

            # Expectancy (average $ per trade)
            expectancy = daily_pnl / trades_count if trades_count > 0 else 0

            # Profit factor (gross profit / gross loss)
            gross_profit = day_positions[day_positions['realized_pnl'] > 0]['realized_pnl'].sum()
            gross_loss = abs(day_positions[day_positions['realized_pnl'] < 0]['realized_pnl'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

            # Log to database with PostgreSQL ON CONFLICT
            c.execute("""
                INSERT INTO performance (
                    date, daily_pnl, cumulative_pnl, account_value,
                    trades_count, winners, losers, win_rate_pct,
                    avg_winner, avg_loser, expectancy,
                    sharpe_ratio, max_drawdown, max_drawdown_pct,
                    daily_return_pct, profit_factor, avg_hold_hours,
                    starting_capital
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date) DO UPDATE SET
                    daily_pnl = EXCLUDED.daily_pnl,
                    cumulative_pnl = EXCLUDED.cumulative_pnl,
                    account_value = EXCLUDED.account_value,
                    trades_count = EXCLUDED.trades_count,
                    winners = EXCLUDED.winners,
                    losers = EXCLUDED.losers,
                    win_rate_pct = EXCLUDED.win_rate_pct,
                    avg_winner = EXCLUDED.avg_winner,
                    avg_loser = EXCLUDED.avg_loser,
                    expectancy = EXCLUDED.expectancy,
                    sharpe_ratio = EXCLUDED.sharpe_ratio,
                    max_drawdown = EXCLUDED.max_drawdown,
                    max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                    daily_return_pct = EXCLUDED.daily_return_pct,
                    profit_factor = EXCLUDED.profit_factor,
                    avg_hold_hours = EXCLUDED.avg_hold_hours,
                    starting_capital = EXCLUDED.starting_capital
            """, (
                date,
                daily_pnl,
                cumulative_pnl,
                account_value,
                trades_count,
                winners,
                losers,
                win_rate,
                avg_winner,
                avg_loser,
                expectancy,
                sharpe_ratio,
                drawdown,
                drawdown_pct,
                daily_return_pct,
                profit_factor,
                avg_hold_hours,
                starting_capital
            ))

            records_logged += 1

            # Print daily summary
            pnl_emoji = "✅" if daily_pnl >= 0 else "❌"
            print(f"{pnl_emoji} {date}: ${daily_pnl:+.2f} | "
                  f"Trades: {trades_count} | Win Rate: {win_rate:.1f}% | "
                  f"Sharpe: {sharpe_ratio:.2f} | "
                  f"Account: ${account_value:,.2f}")

        conn.commit()

        # Print overall summary
        print_performance_summary(c)

        conn.close()

        print(f"\n✅ Logged {records_logged} daily performance records")

    except Exception as e:
        print(f"❌ Error aggregating daily performance: {e}")
        import traceback
        traceback.print_exc()


def calculate_sharpe_ratio(positions_df: pd.DataFrame, current_date: str,
                           starting_capital: float) -> float:
    """
    Calculate Sharpe ratio (risk-adjusted return)

    Sharpe = (Average Return - Risk Free Rate) / Std Dev of Returns
    Assuming 0% risk-free rate for simplicity
    """
    try:
        # Get all positions up to current date
        historical = positions_df[positions_df['date'] <= current_date].copy()

        if len(historical) < 2:
            return 0.0

        # Calculate daily returns
        historical['date'] = pd.to_datetime(historical['date'])
        daily_returns = historical.groupby('date')['realized_pnl'].sum()
        daily_returns_pct = (daily_returns / starting_capital) * 100

        if len(daily_returns_pct) < 2:
            return 0.0

        # Sharpe ratio (annualized)
        avg_daily_return = daily_returns_pct.mean()
        std_daily_return = daily_returns_pct.std()

        if std_daily_return == 0:
            return 0.0

        sharpe_daily = avg_daily_return / std_daily_return

        # Annualize (assuming 252 trading days)
        sharpe_annual = sharpe_daily * np.sqrt(252)

        return round(sharpe_annual, 2)

    except Exception as e:
        print(f"⚠️ Error calculating Sharpe ratio: {e}")
        return 0.0


def print_performance_summary(cursor):
    """Print overall performance summary"""

    # Get latest performance metrics
    cursor.execute("""
        SELECT
            date,
            account_value,
            cumulative_pnl,
            win_rate_pct,
            sharpe_ratio,
            max_drawdown_pct,
            profit_factor
        FROM performance
        ORDER BY date DESC
        LIMIT 1
    """)

    latest = cursor.fetchone()

    if latest:
        date, account_value, cum_pnl, win_rate, sharpe, drawdown, pf = latest

        print("\n" + "="*60)
        print("📊 OVERALL TRADING PERFORMANCE")
        print("="*60)
        print(f"Latest Date:        {date}")
        print(f"Account Value:      ${account_value:,.2f}")
        print(f"Cumulative P&L:     ${cum_pnl:+,.2f}")
        print(f"Win Rate:           {win_rate:.1f}%")
        print(f"Sharpe Ratio:       {sharpe:.2f}")
        print(f"Max Drawdown:       {drawdown:.2f}%")
        print(f"Profit Factor:      {pf:.2f}")
        print("="*60)

    # Get best and worst days
    cursor.execute("""
        SELECT date, daily_pnl
        FROM performance
        ORDER BY daily_pnl DESC
        LIMIT 1
    """)
    best_day = cursor.fetchone()

    cursor.execute("""
        SELECT date, daily_pnl
        FROM performance
        ORDER BY daily_pnl ASC
        LIMIT 1
    """)
    worst_day = cursor.fetchone()

    if best_day and worst_day:
        print(f"\n🏆 Best Day:  {best_day[0]} (${best_day[1]:+.2f})")
        print(f"💔 Worst Day: {worst_day[0]} (${worst_day[1]:+.2f})")


if __name__ == '__main__':
    aggregate_daily_performance()
