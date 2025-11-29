"""
Autonomous Trader Dashboard - Data Access Module

This module provides data access functions for the autonomous trader.
UI rendering has been removed - use the backend API for dashboard views.
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

from core.autonomous_paper_trader import AutonomousPaperTrader
from database_adapter import get_connection

logger = logging.getLogger(__name__)


def get_performance_data(trader: AutonomousPaperTrader) -> Dict:
    """Get performance metrics for the autonomous trader"""
    return trader.get_performance()


def get_open_positions() -> pd.DataFrame:
    """Get all open positions"""
    conn = get_connection()
    positions = pd.read_sql_query("""
        SELECT * FROM autonomous_positions
        WHERE status = 'OPEN'
        ORDER BY entry_date DESC, entry_time DESC
    """, conn)
    conn.close()
    return positions


def get_closed_positions(limit: int = 50) -> pd.DataFrame:
    """Get closed positions (trade history)"""
    conn = get_connection()
    positions = pd.read_sql_query("""
        SELECT * FROM autonomous_positions
        WHERE status = 'CLOSED'
        ORDER BY closed_date DESC, closed_time DESC
        LIMIT %s
    """, conn, params=(limit,))
    conn.close()
    return positions


def get_activity_log(limit: int = 200) -> pd.DataFrame:
    """Get system activity log"""
    conn = get_connection()
    log = pd.read_sql_query("""
        SELECT * FROM autonomous_trade_log
        ORDER BY date DESC, time DESC
        LIMIT %s
    """, conn, params=(limit,))
    conn.close()
    return log


def get_performance_timeline(starting_capital: float) -> List[Dict]:
    """Get performance timeline for charting"""
    conn = get_connection()
    trades = pd.read_sql_query("""
        SELECT
            entry_date,
            entry_time,
            closed_date,
            closed_time,
            realized_pnl,
            status
        FROM autonomous_positions
        ORDER BY entry_date, entry_time
    """, conn)
    conn.close()

    if trades.empty:
        return []

    timeline = []
    running_capital = starting_capital

    # Add starting point
    if len(trades) > 0:
        first_date = trades.iloc[0]['entry_date']
        timeline.append({
            'date': first_date,
            'account_value': running_capital,
            'event': 'Start'
        })

    # Add each completed trade
    for _, trade in trades.iterrows():
        if trade['status'] == 'CLOSED' and trade['closed_date']:
            running_capital += trade['realized_pnl']
            timeline.append({
                'date': trade['closed_date'],
                'account_value': running_capital,
                'event': f"${trade['realized_pnl']:+,.0f}"
            })

    return timeline


def get_profitability_analytics() -> Optional[Dict]:
    """Get profitability analytics for closed trades"""
    conn = get_connection()
    all_trades = pd.read_sql_query("""
        SELECT
            strategy,
            action,
            realized_pnl,
            entry_date,
            closed_date,
            confidence,
            CASE
                WHEN realized_pnl > 0 THEN 'Win'
                ELSE 'Loss'
            END as outcome
        FROM autonomous_positions
        WHERE status = 'CLOSED'
        ORDER BY closed_date, closed_time
    """, conn)
    conn.close()

    if len(all_trades) < 5:
        return None

    wins = all_trades[all_trades['realized_pnl'] > 0]
    losses = all_trades[all_trades['realized_pnl'] <= 0]

    avg_win = wins['realized_pnl'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['realized_pnl'].mean()) if len(losses) > 0 else 0

    # Profit Factor
    total_wins = wins['realized_pnl'].sum()
    total_losses = abs(losses['realized_pnl'].sum())
    profit_factor = total_wins / total_losses if total_losses > 0 else 0

    # Expectancy
    expectancy = all_trades['realized_pnl'].mean()

    # Win/Loss Ratio
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 0

    # Strategy performance
    strategy_perf = all_trades.groupby('strategy').agg({
        'realized_pnl': ['sum', 'mean', 'count'],
        'outcome': lambda x: (x == 'Win').sum() / len(x) * 100
    }).round(2)
    strategy_perf.columns = ['total_pnl', 'avg_pnl', 'trades', 'win_rate']
    strategy_perf = strategy_perf.sort_values('total_pnl', ascending=False)

    return {
        'profit_factor': profit_factor,
        'expectancy': expectancy,
        'win_loss_ratio': win_loss_ratio,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'total_trades': len(all_trades),
        'win_count': len(wins),
        'loss_count': len(losses),
        'strategy_performance': strategy_perf.to_dict('index')
    }


def get_live_status() -> Optional[Dict]:
    """Get bot's live status"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, status, current_action, market_analysis, last_decision
        FROM autonomous_live_status
        WHERE id = 1
    """)
    result = c.fetchone()
    conn.close()

    if result:
        return {
            'timestamp': result[0],
            'status': result[1],
            'current_action': result[2],
            'market_analysis': result[3],
            'last_decision': result[4]
        }
    return None


def get_automation_status(trader: AutonomousPaperTrader) -> Dict:
    """Get automation status overview"""
    last_trade_date = trader.get_config('last_trade_date')
    today = datetime.now().strftime('%Y-%m-%d')
    traded_today = (last_trade_date == today)

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM autonomous_positions WHERE status = 'OPEN'")
    open_positions = c.fetchone()[0]
    conn.close()

    # Check scheduler status
    try:
        from scheduler.trader_scheduler import get_scheduler
        scheduler = get_scheduler()
        scheduler_running = scheduler.is_running
    except (ImportError, AttributeError, Exception):
        scheduler_running = False

    return {
        'traded_today': traded_today,
        'last_trade_date': last_trade_date,
        'open_positions': open_positions,
        'scheduler_running': scheduler_running
    }


# Module-level trader instance
_trader_instance: Optional[AutonomousPaperTrader] = None


def get_trader() -> AutonomousPaperTrader:
    """Get or create the autonomous trader instance"""
    global _trader_instance
    if _trader_instance is None:
        _trader_instance = AutonomousPaperTrader()
    return _trader_instance
