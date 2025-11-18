"""
AlphaGEX Unified Backtesting Framework

Provides base classes and utilities for backtesting ALL AlphaGEX strategies:
- Options strategies (11 strategies from config)
- Psychology trap patterns (13 patterns)
- GEX signals (flip points, walls, regimes)
- Autonomous trader performance

Critical Features:
- Realistic transaction costs (commissions + slippage)
- Position sizing and risk management
- Win rate, expectancy, Sharpe ratio calculations
- Drawdown tracking
- Trade-by-trade audit trail
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from config_and_database import DB_PATH
try:
    from polygon_data_fetcher import polygon_fetcher
    POLYGON_AVAILABLE = True
except:
    POLYGON_AVAILABLE = False

try:
    from flexible_price_data import price_data_fetcher
    FLEXIBLE_DATA_AVAILABLE = True
except:
    FLEXIBLE_DATA_AVAILABLE = False


@dataclass
class Trade:
    """Represents a single trade with full details"""
    entry_date: str
    exit_date: str
    symbol: str
    strategy: str
    direction: str  # 'LONG', 'SHORT', 'NEUTRAL'
    entry_price: float
    exit_price: float
    position_size: float
    commission: float
    slippage: float
    pnl_percent: float
    pnl_dollars: float
    duration_days: int
    win: bool
    confidence: float = 0.0
    notes: str = ""


@dataclass
class BacktestResults:
    """Complete backtest results with all metrics"""
    strategy_name: str
    start_date: str
    end_date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    largest_win_pct: float
    largest_loss_pct: float
    expectancy_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    avg_trade_duration_days: float
    trades: List[Trade]

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'strategy_name': self.strategy_name,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 2),
            'avg_win_pct': round(self.avg_win_pct, 2),
            'avg_loss_pct': round(self.avg_loss_pct, 2),
            'largest_win_pct': round(self.largest_win_pct, 2),
            'largest_loss_pct': round(self.largest_loss_pct, 2),
            'expectancy_pct': round(self.expectancy_pct, 2),
            'total_return_pct': round(self.total_return_pct, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'avg_trade_duration_days': round(self.avg_trade_duration_days, 1),
            'total_trades_count': len(self.trades)
        }


class BacktestBase:
    """Base class for all backtests - provides common functionality"""

    def __init__(self,
                 symbol: str = "SPY",
                 start_date: str = "2022-01-01",
                 end_date: str = "2024-12-31",
                 initial_capital: float = 10000,
                 position_size_pct: float = 10.0,
                 commission_pct: float = 0.05,
                 slippage_pct: float = 0.10):
        """
        Initialize backtest

        Args:
            symbol: Ticker to backtest (default SPY)
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD
            initial_capital: Starting capital ($)
            position_size_pct: % of capital per trade (default 10%)
            commission_pct: Commission per trade side (default 0.05%)
            slippage_pct: Slippage per trade (default 0.10%)
        """
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

        # Will be populated by fetch_data()
        self.price_data = None
        self.trades = []

    def fetch_historical_data(self) -> pd.DataFrame:
        """Fetch historical price data using flexible data sources with fallback"""
        print(f"Fetching {self.symbol} data from {self.start_date} to {self.end_date}...")

        # Calculate number of days between start and end
        start = datetime.strptime(self.start_date, '%Y-%m-%d')
        end = datetime.strptime(self.end_date, '%Y-%m-%d')
        days = (end - start).days

        df = None

        # Try Polygon first if available
        if POLYGON_AVAILABLE:
            try:
                df = polygon_fetcher.get_price_history(
                    symbol=self.symbol,
                    days=days,
                    timeframe='day',
                    multiplier=1
                )
                if df is not None and not df.empty:
                    print(f"✓ Fetched {len(df)} days of data from Polygon.io")
            except Exception as e:
                print(f"⚠️ Polygon fetch failed: {e}")
                df = None

        # Fallback to flexible data fetcher (yfinance, etc.)
        if (df is None or df.empty) and FLEXIBLE_DATA_AVAILABLE:
            try:
                print("Falling back to yfinance...")
                import yfinance as yf
                ticker = yf.Ticker(self.symbol)
                df = ticker.history(start=self.start_date, end=self.end_date)

                if df is not None and not df.empty:
                    # Standardize column names to match Polygon format
                    df = df.rename(columns={
                        'Open': 'Open',
                        'High': 'High',
                        'Low': 'Low',
                        'Close': 'Close',
                        'Volume': 'Volume'
                    })
                    print(f"✓ Fetched {len(df)} days of data from yfinance")
            except Exception as e:
                print(f"⚠️ yfinance fetch failed: {e}")
                df = None

        # Final fallback: simple price fetcher (with synthetic data generation)
        if df is None or df.empty:
            try:
                from simple_price_fetcher import get_price_history
                df = get_price_history(self.symbol, self.start_date, self.end_date)
            except Exception as e:
                print(f"⚠️ Simple fetcher failed: {e}")
                df = None

        if df is None or df.empty:
            raise ValueError(f"No data fetched for {self.symbol} - all data sources failed")

        # Filter to exact date range
        df = df[(df.index >= start) & (df.index <= end)]

        self.price_data = df
        return df

    def calculate_transaction_costs(self, entry_price: float, exit_price: float,
                                    position_size: float) -> Tuple[float, float]:
        """
        Calculate realistic transaction costs

        Returns:
            (commission, slippage) in dollars
        """
        trade_value = position_size
        commission = trade_value * (self.commission_pct / 100) * 2  # Entry + Exit
        slippage = trade_value * (self.slippage_pct / 100)

        return commission, slippage

    def calculate_pnl(self, entry_price: float, exit_price: float,
                     direction: str, position_size: float) -> Tuple[float, float]:
        """
        Calculate PnL with transaction costs

        Returns:
            (pnl_percent, pnl_dollars)
        """
        # Calculate gross PnL
        if direction == 'LONG':
            gross_pnl_pct = ((exit_price - entry_price) / entry_price) * 100
        elif direction == 'SHORT':
            gross_pnl_pct = ((entry_price - exit_price) / entry_price) * 100
        else:  # NEUTRAL strategies
            gross_pnl_pct = 0.0  # Implement specific logic in subclass

        # Subtract transaction costs
        commission, slippage = self.calculate_transaction_costs(
            entry_price, exit_price, position_size
        )
        total_costs = commission + slippage
        cost_pct = (total_costs / position_size) * 100

        net_pnl_pct = gross_pnl_pct - cost_pct
        net_pnl_dollars = position_size * (net_pnl_pct / 100)

        return net_pnl_pct, net_pnl_dollars

    def create_trade(self, entry_date: str, exit_date: str, entry_price: float,
                    exit_price: float, direction: str, strategy: str,
                    confidence: float = 0.0, notes: str = "") -> Trade:
        """Create a Trade object with calculated PnL"""
        position_size = self.initial_capital * (self.position_size_pct / 100)
        commission, slippage = self.calculate_transaction_costs(
            entry_price, exit_price, position_size
        )
        pnl_pct, pnl_dollars = self.calculate_pnl(
            entry_price, exit_price, direction, position_size
        )

        # Calculate duration
        entry_dt = pd.to_datetime(entry_date)
        exit_dt = pd.to_datetime(exit_date)
        duration_days = (exit_dt - entry_dt).days

        return Trade(
            entry_date=entry_date,
            exit_date=exit_date,
            symbol=self.symbol,
            strategy=strategy,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            position_size=position_size,
            commission=commission,
            slippage=slippage,
            pnl_percent=pnl_pct,
            pnl_dollars=pnl_dollars,
            duration_days=duration_days,
            win=(pnl_pct > 0),
            confidence=confidence,
            notes=notes
        )

    def calculate_metrics(self, trades: List[Trade], strategy_name: str) -> BacktestResults:
        """Calculate comprehensive performance metrics"""
        if not trades:
            return BacktestResults(
                strategy_name=strategy_name,
                start_date=self.start_date,
                end_date=self.end_date,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                avg_win_pct=0.0,
                avg_loss_pct=0.0,
                largest_win_pct=0.0,
                largest_loss_pct=0.0,
                expectancy_pct=0.0,
                total_return_pct=0.0,
                max_drawdown_pct=0.0,
                sharpe_ratio=0.0,
                avg_trade_duration_days=0.0,
                trades=[]
            )

        wins = [t for t in trades if t.win]
        losses = [t for t in trades if not t.win]

        total_trades = len(trades)
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        avg_win_pct = sum(t.pnl_percent for t in wins) / len(wins) if wins else 0
        avg_loss_pct = sum(t.pnl_percent for t in losses) / len(losses) if losses else 0

        largest_win_pct = max((t.pnl_percent for t in wins), default=0)
        largest_loss_pct = min((t.pnl_percent for t in losses), default=0)

        # Expectancy = (Win% * Avg Win) + (Loss% * Avg Loss)
        expectancy_pct = (win_rate / 100 * avg_win_pct) + ((100 - win_rate) / 100 * avg_loss_pct)

        # Total return (compounded)
        total_return_pct = sum(t.pnl_percent for t in trades)

        # Max drawdown
        cumulative_returns = []
        cumulative = 0
        for trade in trades:
            cumulative += trade.pnl_percent
            cumulative_returns.append(cumulative)

        max_drawdown_pct = 0
        peak = cumulative_returns[0]
        for cum_return in cumulative_returns:
            if cum_return > peak:
                peak = cum_return
            drawdown = peak - cum_return
            if drawdown > max_drawdown_pct:
                max_drawdown_pct = drawdown

        # Sharpe ratio (simplified - assumes risk-free rate = 0)
        returns = [t.pnl_percent for t in trades]
        avg_return = sum(returns) / len(returns)
        std_dev = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5
        sharpe_ratio = (avg_return / std_dev * (252 ** 0.5)) if std_dev > 0 else 0

        # Average trade duration
        avg_duration = sum(t.duration_days for t in trades) / len(trades)

        results = BacktestResults(
            strategy_name=strategy_name,
            start_date=self.start_date,
            end_date=self.end_date,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            largest_win_pct=largest_win_pct,
            largest_loss_pct=largest_loss_pct,
            expectancy_pct=expectancy_pct,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            avg_trade_duration_days=avg_duration,
            trades=trades
        )

        # AUTO-UPDATE: Save strategy stats for dynamic system
        try:
            from strategy_stats import update_strategy_stats
            update_strategy_stats(strategy_name, results.to_dict())
        except Exception as e:
            print(f"⚠️  Could not auto-update strategy stats: {e}")

        return results

    def save_results_to_db(self, results: BacktestResults):
        """Save backtest results to database"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        # Create backtest_results table if not exists
        c.execute('''
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                strategy_name TEXT,
                symbol TEXT,
                start_date TEXT,
                end_date TEXT,
                total_trades INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                win_rate REAL,
                avg_win_pct REAL,
                avg_loss_pct REAL,
                largest_win_pct REAL,
                largest_loss_pct REAL,
                expectancy_pct REAL,
                total_return_pct REAL,
                max_drawdown_pct REAL,
                sharpe_ratio REAL,
                avg_trade_duration_days REAL
            )
        ''')

        # Insert results
        c.execute('''
            INSERT INTO backtest_results (
                strategy_name, symbol, start_date, end_date,
                total_trades, winning_trades, losing_trades, win_rate,
                avg_win_pct, avg_loss_pct, largest_win_pct, largest_loss_pct,
                expectancy_pct, total_return_pct, max_drawdown_pct, sharpe_ratio,
                avg_trade_duration_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            results.strategy_name, self.symbol, results.start_date, results.end_date,
            results.total_trades, results.winning_trades, results.losing_trades,
            results.win_rate, results.avg_win_pct, results.avg_loss_pct,
            results.largest_win_pct, results.largest_loss_pct,
            results.expectancy_pct, results.total_return_pct, results.max_drawdown_pct,
            results.sharpe_ratio, results.avg_trade_duration_days
        ))

        conn.commit()
        conn.close()

        print(f"✓ Saved {results.strategy_name} results to database")

    def print_summary(self, results: BacktestResults):
        """Print formatted backtest summary"""
        print("\n" + "=" * 80)
        print(f"BACKTEST RESULTS: {results.strategy_name}")
        print("=" * 80)
        print(f"Period: {results.start_date} to {results.end_date}")
        print(f"Total Trades: {results.total_trades}")
        print(f"Win Rate: {results.win_rate:.1f}% ({results.winning_trades}W / {results.losing_trades}L)")
        print(f"Avg Win: +{results.avg_win_pct:.2f}%")
        print(f"Avg Loss: {results.avg_loss_pct:.2f}%")
        print(f"Expectancy: {results.expectancy_pct:+.2f}% per trade")
        print(f"Total Return: {results.total_return_pct:+.2f}%")
        print(f"Max Drawdown: -{results.max_drawdown_pct:.2f}%")
        print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"Avg Duration: {results.avg_trade_duration_days:.1f} days")
        print("=" * 80)

        # CRITICAL: Profitability assessment
        if results.expectancy_pct > 0.5 and results.win_rate > 55:
            print("✅ PROFITABLE STRATEGY - Has positive edge")
        elif results.expectancy_pct > 0:
            print("⚠️  MARGINAL - Small edge, needs improvement")
        else:
            print("❌ LOSING STRATEGY - Do not trade this")
        print("=" * 80 + "\n")

    def run_backtest(self) -> BacktestResults:
        """Override this in subclasses to implement strategy logic"""
        raise NotImplementedError("Subclasses must implement run_backtest()")
