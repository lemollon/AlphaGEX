"""
MetaTrader-Style Backtest Report Generator

Creates comprehensive backtest reports with:
- Profit factor, expected payoff
- Maximal drawdown (absolute, relative)
- Win rates by direction (long/short)
- Consecutive wins/losses tracking
- Equity curve data for visualization

Usage:
    from core.backtest_report import BacktestReportGenerator

    generator = BacktestReportGenerator(trades_df, starting_capital=10000)
    report = generator.generate()
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class BacktestReport:
    """Complete backtest report in MetaTrader format"""

    # Header info
    symbol: str
    period: str  # e.g., "1 Hour (H1) 2024.01.01 - 2024.12.01"
    model: str = "Every tick"

    # Bars and data quality
    bars_in_test: int = 0
    ticks_modeled: int = 0
    modeling_quality: float = 0.0  # Percentage

    # Capital
    initial_deposit: float = 10000.0
    current_balance: float = 10000.0

    # P&L Summary
    total_net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0

    # Risk Metrics
    profit_factor: float = 0.0  # Gross Profit / Gross Loss
    expected_payoff: float = 0.0  # Avg profit per trade
    absolute_drawdown: float = 0.0  # Max drop from initial capital
    maximal_drawdown: float = 0.0  # Max drop in $ from peak
    maximal_drawdown_pct: float = 0.0  # Max drop in % from peak
    relative_drawdown: float = 0.0  # Relative drawdown %

    # Trade Statistics
    total_trades: int = 0
    short_positions: int = 0
    short_positions_won_pct: float = 0.0
    long_positions: int = 0
    long_positions_won_pct: float = 0.0
    profit_trades: int = 0
    profit_trades_pct: float = 0.0
    loss_trades: int = 0
    loss_trades_pct: float = 0.0

    # Best/Worst
    largest_profit_trade: float = 0.0
    largest_loss_trade: float = 0.0
    average_profit_trade: float = 0.0
    average_loss_trade: float = 0.0

    # Consecutive Stats
    max_consecutive_wins: int = 0
    max_consecutive_wins_money: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_losses_money: float = 0.0
    max_consecutive_profit: float = 0.0
    max_consecutive_profit_count: int = 0
    max_consecutive_loss: float = 0.0
    max_consecutive_loss_count: int = 0
    average_consecutive_wins: int = 0
    average_consecutive_losses: int = 0

    # Time analysis
    avg_hold_time_minutes: float = 0.0
    avg_winning_hold_time: float = 0.0
    avg_losing_hold_time: float = 0.0

    # Sharpe and advanced metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0  # Net profit / Max drawdown

    # Equity curve data (for charting)
    equity_curve: List[Dict] = None

    def to_dict(self) -> Dict:
        d = asdict(self)
        # Ensure equity_curve is serializable
        if d['equity_curve'] is None:
            d['equity_curve'] = []
        return d


class BacktestReportGenerator:
    """
    Generates MetaTrader-style backtest reports from trade data.
    """

    def __init__(self, trades: pd.DataFrame, starting_capital: float = 10000.0,
                 symbol: str = "SPY", period: str = None):
        """
        Initialize report generator.

        Args:
            trades: DataFrame with columns: entry_date, exit_date, realized_pnl,
                   action (BUY/SELL), hold_duration_minutes (optional)
            starting_capital: Initial account balance
            symbol: Trading symbol
            period: Time period string (auto-generated if None)
        """
        self.trades = trades.copy() if trades is not None else pd.DataFrame()
        self.starting_capital = starting_capital
        self.symbol = symbol
        self.period = period

        # Ensure required columns
        if not self.trades.empty:
            self._prepare_data()

    def _prepare_data(self):
        """Prepare and validate trade data"""
        # Ensure realized_pnl column
        if 'realized_pnl' not in self.trades.columns:
            if 'pnl' in self.trades.columns:
                self.trades['realized_pnl'] = self.trades['pnl']
            else:
                self.trades['realized_pnl'] = 0

        # Ensure action column (BUY/SELL or LONG/SHORT)
        if 'action' not in self.trades.columns:
            if 'option_type' in self.trades.columns:
                # For options: CALL = bullish = LONG, PUT = bearish = SHORT
                self.trades['action'] = self.trades['option_type'].apply(
                    lambda x: 'LONG' if str(x).upper() == 'CALL' else 'SHORT'
                )
            else:
                self.trades['action'] = 'LONG'

        # Sort by exit date
        if 'exit_date' in self.trades.columns:
            self.trades = self.trades.sort_values('exit_date')
        elif 'entry_date' in self.trades.columns:
            self.trades = self.trades.sort_values('entry_date')

        # Calculate cumulative P&L
        self.trades['cumulative_pnl'] = self.trades['realized_pnl'].cumsum()
        self.trades['equity'] = self.starting_capital + self.trades['cumulative_pnl']

    def generate(self) -> BacktestReport:
        """Generate complete backtest report"""
        if self.trades.empty:
            return BacktestReport(
                symbol=self.symbol,
                period=self.period or "No data",
                initial_deposit=self.starting_capital,
                current_balance=self.starting_capital
            )

        report = BacktestReport(
            symbol=self.symbol,
            period=self._calculate_period(),
            initial_deposit=self.starting_capital
        )

        # Calculate all metrics
        self._calculate_pnl_metrics(report)
        self._calculate_trade_stats(report)
        self._calculate_drawdown(report)
        self._calculate_consecutive_stats(report)
        self._calculate_time_stats(report)
        self._calculate_advanced_metrics(report)
        self._generate_equity_curve(report)

        return report

    def _calculate_period(self) -> str:
        """Generate period string from trade dates"""
        if self.period:
            return self.period

        if self.trades.empty:
            return "No data"

        # Try to get date range
        date_col = 'exit_date' if 'exit_date' in self.trades.columns else 'entry_date'
        if date_col not in self.trades.columns:
            return "Unknown period"

        dates = pd.to_datetime(self.trades[date_col])
        start = dates.min()
        end = dates.max()

        return f"{start.strftime('%Y.%m.%d')} - {end.strftime('%Y.%m.%d')}"

    def _calculate_pnl_metrics(self, report: BacktestReport):
        """Calculate P&L metrics"""
        pnl = self.trades['realized_pnl']

        report.total_net_profit = float(pnl.sum())
        report.gross_profit = float(pnl[pnl > 0].sum())
        report.gross_loss = float(abs(pnl[pnl < 0].sum()))
        report.current_balance = self.starting_capital + report.total_net_profit

        # Profit factor
        if report.gross_loss > 0:
            report.profit_factor = round(report.gross_profit / report.gross_loss, 2)
        else:
            report.profit_factor = float('inf') if report.gross_profit > 0 else 0

        # Expected payoff (avg profit per trade)
        report.total_trades = len(self.trades)
        if report.total_trades > 0:
            report.expected_payoff = round(report.total_net_profit / report.total_trades, 2)

    def _calculate_trade_stats(self, report: BacktestReport):
        """Calculate trade statistics by direction"""
        # Winning vs losing trades
        winners = self.trades[self.trades['realized_pnl'] > 0]
        losers = self.trades[self.trades['realized_pnl'] < 0]

        report.profit_trades = len(winners)
        report.loss_trades = len(losers)

        if report.total_trades > 0:
            report.profit_trades_pct = round(100 * report.profit_trades / report.total_trades, 2)
            report.loss_trades_pct = round(100 * report.loss_trades / report.total_trades, 2)

        # Best/worst trades
        if len(winners) > 0:
            report.largest_profit_trade = float(winners['realized_pnl'].max())
            report.average_profit_trade = float(winners['realized_pnl'].mean())

        if len(losers) > 0:
            report.largest_loss_trade = float(losers['realized_pnl'].min())
            report.average_loss_trade = float(losers['realized_pnl'].mean())

        # Long vs Short positions
        self.trades['is_long'] = self.trades['action'].str.upper().isin(['BUY', 'LONG', 'CALL'])

        longs = self.trades[self.trades['is_long'] == True]
        shorts = self.trades[self.trades['is_long'] == False]

        report.long_positions = len(longs)
        report.short_positions = len(shorts)

        if len(longs) > 0:
            long_winners = longs[longs['realized_pnl'] > 0]
            report.long_positions_won_pct = round(100 * len(long_winners) / len(longs), 2)

        if len(shorts) > 0:
            short_winners = shorts[shorts['realized_pnl'] > 0]
            report.short_positions_won_pct = round(100 * len(short_winners) / len(shorts), 2)

    def _calculate_drawdown(self, report: BacktestReport):
        """Calculate drawdown metrics"""
        equity = self.trades['equity'].values

        # Running maximum (peak)
        peak = np.maximum.accumulate(equity)

        # Drawdown at each point
        drawdown = peak - equity
        drawdown_pct = (drawdown / peak) * 100

        # Absolute drawdown (from initial capital)
        report.absolute_drawdown = round(max(0, self.starting_capital - equity.min()), 2)

        # Maximal drawdown (from peak)
        report.maximal_drawdown = round(float(drawdown.max()), 2)
        report.maximal_drawdown_pct = round(float(drawdown_pct.max()), 2)

        # Relative drawdown (percentage)
        report.relative_drawdown = report.maximal_drawdown_pct

    def _calculate_consecutive_stats(self, report: BacktestReport):
        """Calculate consecutive wins/losses statistics"""
        pnl = self.trades['realized_pnl'].values

        # Track consecutive sequences
        consecutive_wins = []
        consecutive_losses = []
        consecutive_win_money = []
        consecutive_loss_money = []

        current_streak = 0
        current_money = 0
        is_winning_streak = None

        for p in pnl:
            if p > 0:
                if is_winning_streak == True:
                    current_streak += 1
                    current_money += p
                else:
                    # End losing streak, start winning
                    if is_winning_streak == False and current_streak > 0:
                        consecutive_losses.append(current_streak)
                        consecutive_loss_money.append(abs(current_money))
                    current_streak = 1
                    current_money = p
                    is_winning_streak = True
            elif p < 0:
                if is_winning_streak == False:
                    current_streak += 1
                    current_money += p
                else:
                    # End winning streak, start losing
                    if is_winning_streak == True and current_streak > 0:
                        consecutive_wins.append(current_streak)
                        consecutive_win_money.append(current_money)
                    current_streak = 1
                    current_money = p
                    is_winning_streak = False

        # Don't forget the last streak
        if current_streak > 0:
            if is_winning_streak:
                consecutive_wins.append(current_streak)
                consecutive_win_money.append(current_money)
            else:
                consecutive_losses.append(current_streak)
                consecutive_loss_money.append(abs(current_money))

        # Max consecutive wins
        if consecutive_wins:
            report.max_consecutive_wins = max(consecutive_wins)
            max_idx = consecutive_wins.index(report.max_consecutive_wins)
            report.max_consecutive_wins_money = round(consecutive_win_money[max_idx], 2)
            report.average_consecutive_wins = int(np.mean(consecutive_wins))

        # Max consecutive losses
        if consecutive_losses:
            report.max_consecutive_losses = max(consecutive_losses)
            max_idx = consecutive_losses.index(report.max_consecutive_losses)
            report.max_consecutive_losses_money = round(consecutive_loss_money[max_idx], 2)
            report.average_consecutive_losses = int(np.mean(consecutive_losses))

        # Max consecutive profit/loss (by money)
        if consecutive_win_money:
            report.max_consecutive_profit = round(max(consecutive_win_money), 2)
            max_idx = consecutive_win_money.index(report.max_consecutive_profit)
            report.max_consecutive_profit_count = consecutive_wins[max_idx]

        if consecutive_loss_money:
            report.max_consecutive_loss = round(max(consecutive_loss_money), 2)
            max_idx = consecutive_loss_money.index(report.max_consecutive_loss)
            report.max_consecutive_loss_count = consecutive_losses[max_idx]

    def _calculate_time_stats(self, report: BacktestReport):
        """Calculate time-based statistics"""
        if 'hold_duration_minutes' in self.trades.columns:
            durations = self.trades['hold_duration_minutes'].dropna()
            if len(durations) > 0:
                report.avg_hold_time_minutes = float(durations.mean())

                winners = self.trades[self.trades['realized_pnl'] > 0]
                losers = self.trades[self.trades['realized_pnl'] < 0]

                if 'hold_duration_minutes' in winners.columns and len(winners) > 0:
                    report.avg_winning_hold_time = float(winners['hold_duration_minutes'].mean())

                if 'hold_duration_minutes' in losers.columns and len(losers) > 0:
                    report.avg_losing_hold_time = float(losers['hold_duration_minutes'].mean())

    def _calculate_advanced_metrics(self, report: BacktestReport):
        """Calculate Sharpe, Sortino, Calmar ratios"""
        if len(self.trades) < 2:
            return

        returns = self.trades['realized_pnl'] / self.starting_capital

        # Sharpe Ratio (assuming risk-free rate = 0 for simplicity)
        if returns.std() > 0:
            # Annualize assuming daily trades
            report.sharpe_ratio = round(float(returns.mean() / returns.std() * np.sqrt(252)), 2)

        # Sortino Ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            report.sortino_ratio = round(float(returns.mean() / downside_returns.std() * np.sqrt(252)), 2)

        # Calmar Ratio (return / max drawdown)
        if report.maximal_drawdown_pct > 0:
            annual_return = (report.total_net_profit / self.starting_capital) * 100
            report.calmar_ratio = round(annual_return / report.maximal_drawdown_pct, 2)

        # Recovery Factor (net profit / max drawdown)
        if report.maximal_drawdown > 0:
            report.recovery_factor = round(report.total_net_profit / report.maximal_drawdown, 2)

    def _generate_equity_curve(self, report: BacktestReport):
        """Generate equity curve data for charting"""
        equity_data = []

        # Start point
        equity_data.append({
            'trade_num': 0,
            'balance': self.starting_capital,
            'equity': self.starting_capital,
            'drawdown_pct': 0
        })

        peak = self.starting_capital

        for i, (_, row) in enumerate(self.trades.iterrows()):
            equity = row['equity']
            peak = max(peak, equity)
            drawdown_pct = ((peak - equity) / peak) * 100 if peak > 0 else 0

            equity_data.append({
                'trade_num': i + 1,
                'balance': float(equity),
                'equity': float(equity),
                'drawdown_pct': round(drawdown_pct, 2),
                'date': str(row.get('exit_date', ''))
            })

        report.equity_curve = equity_data


def generate_backtest_report(trades_df: pd.DataFrame,
                             starting_capital: float = 10000.0,
                             symbol: str = "SPY",
                             period: str = None) -> Dict:
    """
    Convenience function to generate backtest report.

    Args:
        trades_df: DataFrame with trade data
        starting_capital: Initial balance
        symbol: Trading symbol
        period: Time period string

    Returns:
        Dict with all report metrics
    """
    generator = BacktestReportGenerator(trades_df, starting_capital, symbol, period)
    report = generator.generate()
    return report.to_dict()
