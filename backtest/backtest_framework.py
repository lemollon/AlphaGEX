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

import pandas as pd
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from database_adapter import get_connection

# Data collection for ML storage
try:
    from services.data_collector import DataCollector
    DATA_COLLECTOR_AVAILABLE = True
except:
    DATA_COLLECTOR_AVAILABLE = False

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from data.unified_data_provider import get_data_provider, UnifiedDataProvider
    UNIFIED_DATA_AVAILABLE = True
    print("✅ Backtester: Unified Data Provider (Tradier) integrated")
except ImportError:
    UNIFIED_DATA_AVAILABLE = False

# Legacy Polygon fallback
try:
    from data.polygon_data_fetcher import polygon_fetcher
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False

try:
    from flexible_price_data import price_data_fetcher
    FLEXIBLE_DATA_AVAILABLE = True
except ImportError:
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
class DataQuality:
    """Tracks data quality for backtest results - CRITICAL for quant integrity"""
    price_data_source: str = "unknown"  # 'polygon', 'tradier', 'yfinance', 'simulated'
    gex_data_source: str = "unknown"    # 'tradingvolatility', 'database', 'simulated'
    uses_simulated_data: bool = False   # TRUE = Results are unreliable!
    data_coverage_pct: float = 100.0    # % of days with complete data
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

    def is_production_ready(self) -> bool:
        """
        Returns True only if data quality is sufficient for production decisions.

        QUANT RULE: Never trade based on simulated backtest data.
        """
        if self.uses_simulated_data:
            return False
        if self.data_coverage_pct < 90.0:
            return False
        if self.gex_data_source == "simulated":
            return False
        return True

    def to_dict(self) -> Dict:
        return {
            'price_data_source': self.price_data_source,
            'gex_data_source': self.gex_data_source,
            'uses_simulated_data': self.uses_simulated_data,
            'data_coverage_pct': self.data_coverage_pct,
            'production_ready': self.is_production_ready(),
            'warnings': self.warnings
        }


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
    data_quality: DataQuality = None  # NEW: Track data quality

    def __post_init__(self):
        if self.data_quality is None:
            self.data_quality = DataQuality()

    def is_reliable(self) -> bool:
        """Returns True only if results are based on real data"""
        return self.data_quality.is_production_ready()

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        result = {
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
            'total_trades_count': len(self.trades),
            # NEW: Data quality metadata
            'data_quality': self.data_quality.to_dict() if self.data_quality else None,
            'reliable': self.is_reliable()
        }
        return result


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

        # NO FAKE DATA - fail if real data unavailable
        if df is None or df.empty:
            raise ValueError(f"No data fetched for {self.symbol} - all data sources failed. Check API keys.")

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
            from core.strategy_stats import update_strategy_stats
            update_strategy_stats(strategy_name, results.to_dict())
        except Exception as e:
            print(f"⚠️  Could not auto-update strategy stats: {e}")

        # Store individual trades for ML/audit
        try:
            self.save_trades_to_db(trades, strategy_name)
        except Exception as e:
            print(f"⚠️  Could not save individual trades: {e}")

        return results

    def save_results_to_db(self, results: BacktestResults):
        """Save backtest results to database (PostgreSQL compatible)"""
        conn = get_connection()
        c = conn.cursor()

        # NOTE: Table 'backtest_results' defined in db/config_and_database.py (single source of truth)

        # Insert results (PostgreSQL %s placeholders)
        c.execute('''
            INSERT INTO backtest_results (
                strategy_name, symbol, start_date, end_date,
                total_trades, winning_trades, losing_trades, win_rate,
                avg_win_pct, avg_loss_pct, largest_win_pct, largest_loss_pct,
                expectancy_pct, total_return_pct, max_drawdown_pct, sharpe_ratio,
                avg_trade_duration_days
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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

    def save_trades_to_db(self, trades: List, strategy_name: str):
        """Save individual backtest trades for audit and ML training"""
        if not DATA_COLLECTOR_AVAILABLE or not trades:
            return

        run_id = str(uuid.uuid4())
        for i, trade in enumerate(trades, 1):
            try:
                trade_data = {
                    'strategy': strategy_name,
                    'symbol': getattr(trade, 'symbol', 'SPY'),
                    'entry_date': getattr(trade, 'entry_date', None),
                    'exit_date': getattr(trade, 'exit_date', None),
                    'entry_price': getattr(trade, 'entry_price', 0),
                    'exit_price': getattr(trade, 'exit_price', 0),
                    'pnl_dollars': getattr(trade, 'pnl_dollars', 0),
                    'pnl_percent': getattr(trade, 'pnl_percent', 0),
                    'win': getattr(trade, 'win', False),
                    'confidence': getattr(trade, 'confidence', 0),
                }
                DataCollector.store_backtest_trade(run_id, trade_data, i)
            except Exception as e:
                pass  # Don't fail backtest if storage fails

        print(f"✓ Saved {len(trades)} individual trades to backtest_trades table")

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
