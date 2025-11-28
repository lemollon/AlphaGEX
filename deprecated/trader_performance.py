"""
Performance Tracking Module for Autonomous Trading
===================================================

Extracted from autonomous_paper_trader.py to reduce class complexity.

This module handles:
- Equity snapshot creation
- Strategy stats updates
- Performance metrics calculation
- Trade activity logging

Author: AlphaGEX
Date: 2025-11-27
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List
from dataclasses import dataclass

from database_adapter import get_connection

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Trading performance metrics"""
    total_pnl: float
    realized_pnl: float
    unrealized_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    expectancy: float
    sharpe_ratio: float
    max_drawdown_pct: float
    starting_capital: float
    current_value: float
    return_pct: float


class TraderPerformance:
    """
    Handles performance tracking, equity snapshots, and strategy stats.
    """

    def __init__(self, trader_symbol: str = "SPY", starting_capital: float = 1000000):
        """
        Initialize performance tracker.

        Args:
            trader_symbol: Symbol being traded
            starting_capital: Initial capital
        """
        self.symbol = trader_symbol
        self.starting_capital = starting_capital

    def get_performance(self) -> PerformanceMetrics:
        """Calculate comprehensive performance metrics from database."""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Get realized P&L from closed trades
            cursor.execute("""
                SELECT
                    COALESCE(SUM(realized_pnl), 0) as total_realized,
                    COUNT(*) as total_trades,
                    COUNT(CASE WHEN realized_pnl > 0 THEN 1 END) as winners,
                    COUNT(CASE WHEN realized_pnl <= 0 THEN 1 END) as losers,
                    COALESCE(AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END), 0) as avg_win,
                    COALESCE(AVG(CASE WHEN realized_pnl < 0 THEN ABS(realized_pnl) END), 0) as avg_loss
                FROM autonomous_closed_trades
            """)
            row = cursor.fetchone()
            realized_pnl = float(row[0] or 0)
            total_trades = int(row[1] or 0)
            winning_trades = int(row[2] or 0)
            losing_trades = int(row[3] or 0)
            avg_win = float(row[4] or 0)
            avg_loss = float(row[5] or 0)

            # Get unrealized P&L from open positions
            cursor.execute("""
                SELECT COALESCE(SUM(unrealized_pnl), 0)
                FROM autonomous_open_positions
            """)
            unrealized_pnl = float(cursor.fetchone()[0] or 0)

            # Get latest equity snapshot for Sharpe and drawdown
            cursor.execute("""
                SELECT sharpe_ratio, max_drawdown_pct
                FROM autonomous_equity_snapshots
                ORDER BY snapshot_date DESC, snapshot_time DESC
                LIMIT 1
            """)
            snapshot = cursor.fetchone()
            sharpe_ratio = float(snapshot[0] or 0) if snapshot else 0
            max_drawdown_pct = float(snapshot[1] or 0) if snapshot else 0

            conn.close()

            # Calculate metrics
            total_pnl = realized_pnl + unrealized_pnl
            current_value = self.starting_capital + total_pnl
            return_pct = (total_pnl / self.starting_capital * 100) if self.starting_capital > 0 else 0
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

            # Calculate expectancy
            if total_trades > 0:
                win_prob = winning_trades / total_trades
                loss_prob = losing_trades / total_trades
                expectancy = (win_prob * avg_win) - (loss_prob * avg_loss)
            else:
                expectancy = 0

            return PerformanceMetrics(
                total_pnl=total_pnl,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                avg_win=avg_win,
                avg_loss=avg_loss,
                expectancy=expectancy,
                sharpe_ratio=sharpe_ratio,
                max_drawdown_pct=max_drawdown_pct,
                starting_capital=self.starting_capital,
                current_value=current_value,
                return_pct=return_pct
            )
        except Exception as e:
            logger.error(f"Error getting performance: {e}")
            return PerformanceMetrics(
                total_pnl=0, realized_pnl=0, unrealized_pnl=0,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0, avg_win=0, avg_loss=0, expectancy=0,
                sharpe_ratio=0, max_drawdown_pct=0,
                starting_capital=self.starting_capital,
                current_value=self.starting_capital, return_pct=0
            )

    def create_equity_snapshot(self) -> bool:
        """Create end-of-day equity snapshot in database."""
        try:
            metrics = self.get_performance()

            conn = get_connection()
            cursor = conn.cursor()

            today = datetime.now().strftime('%Y-%m-%d')
            now_time = datetime.now().strftime('%H:%M:%S')

            cursor.execute("""
                INSERT INTO autonomous_equity_snapshots (
                    snapshot_date, snapshot_time, starting_capital,
                    total_realized_pnl, total_unrealized_pnl, account_value,
                    daily_pnl, daily_return_pct, total_return_pct,
                    max_drawdown_pct, sharpe_ratio, win_rate, total_trades
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                today, now_time, metrics.starting_capital,
                metrics.realized_pnl, metrics.unrealized_pnl, metrics.current_value,
                metrics.total_pnl, metrics.return_pct, metrics.return_pct,
                metrics.max_drawdown_pct, metrics.sharpe_ratio,
                metrics.win_rate, metrics.total_trades
            ))

            conn.commit()
            conn.close()

            logger.info(f"Equity snapshot created: ${metrics.current_value:,.2f} "
                       f"({metrics.return_pct:+.2f}%)")
            return True
        except Exception as e:
            logger.error(f"Error creating equity snapshot: {e}")
            return False

    def update_strategy_stats(
        self,
        strategy_name: str,
        pnl: float,
        pnl_pct: float,
        is_win: bool
    ) -> bool:
        """
        Update strategy statistics after a trade closes.

        Args:
            strategy_name: Name of the strategy
            pnl: Absolute P&L
            pnl_pct: Percentage P&L
            is_win: Whether trade was profitable

        Returns:
            True if update successful
        """
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Check if strategy exists
            cursor.execute("""
                SELECT total_trades, winning_trades, total_pnl,
                       sum_win_pct, sum_loss_pct
                FROM strategy_stats
                WHERE strategy_name = %s
            """, (strategy_name,))
            row = cursor.fetchone()

            if row:
                total_trades = row[0] + 1
                winning_trades = row[1] + (1 if is_win else 0)
                total_pnl = row[2] + pnl
                sum_win_pct = row[3] + (pnl_pct if is_win else 0)
                sum_loss_pct = row[4] + (abs(pnl_pct) if not is_win else 0)

                cursor.execute("""
                    UPDATE strategy_stats SET
                        total_trades = %s,
                        winning_trades = %s,
                        total_pnl = %s,
                        sum_win_pct = %s,
                        sum_loss_pct = %s,
                        last_update = NOW()
                    WHERE strategy_name = %s
                """, (total_trades, winning_trades, total_pnl,
                     sum_win_pct, sum_loss_pct, strategy_name))
            else:
                cursor.execute("""
                    INSERT INTO strategy_stats (
                        strategy_name, total_trades, winning_trades,
                        total_pnl, sum_win_pct, sum_loss_pct, last_update
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (
                    strategy_name, 1, 1 if is_win else 0,
                    pnl, pnl_pct if is_win else 0, abs(pnl_pct) if not is_win else 0
                ))

            conn.commit()
            conn.close()

            logger.info(f"Strategy stats updated for {strategy_name}")
            return True
        except Exception as e:
            logger.error(f"Error updating strategy stats: {e}")
            return False

    def log_trade_activity(
        self,
        action_type: str,
        symbol: str,
        details: str,
        pnl: float = 0,
        contracts: int = 0,
        strategy: str = None
    ) -> bool:
        """Log trade activity to database."""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO trader_activity_log (
                    timestamp, action_type, symbol, details,
                    pnl, contracts, strategy
                ) VALUES (NOW(), %s, %s, %s, %s, %s, %s)
            """, (action_type, symbol, details, pnl, contracts, strategy))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error logging trade activity: {e}")
            return False

    def get_strategy_performance(self, strategy_name: str = None) -> List[Dict]:
        """Get performance breakdown by strategy."""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            if strategy_name:
                cursor.execute("""
                    SELECT
                        strategy,
                        COUNT(*) as trades,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(realized_pnl) as total_pnl,
                        AVG(realized_pnl) as avg_pnl
                    FROM autonomous_closed_trades
                    WHERE strategy = %s
                    GROUP BY strategy
                """, (strategy_name,))
            else:
                cursor.execute("""
                    SELECT
                        strategy,
                        COUNT(*) as trades,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(realized_pnl) as total_pnl,
                        AVG(realized_pnl) as avg_pnl
                    FROM autonomous_closed_trades
                    GROUP BY strategy
                    ORDER BY total_pnl DESC
                """)

            results = []
            for row in cursor.fetchall():
                trades = row[1] or 0
                wins = row[2] or 0
                results.append({
                    'strategy': row[0],
                    'trades': trades,
                    'wins': wins,
                    'win_rate': (wins / trades * 100) if trades > 0 else 0,
                    'total_pnl': float(row[3] or 0),
                    'avg_pnl': float(row[4] or 0)
                })

            conn.close()
            return results
        except Exception as e:
            logger.error(f"Error getting strategy performance: {e}")
            return []
