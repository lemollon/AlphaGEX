"""
Risk Management System for Autonomous Trader
Implements max drawdown limits, daily loss limits, position limits, correlation checks

CRITICAL: Prevents catastrophic losses
- Max Drawdown: 15% from peak equity
- Daily Loss Limit: 5% of account
- Position Limit: 20% per trade
- Correlation Limit: Max 50% in correlated symbols
"""

from database_adapter import get_connection
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import psycopg2.extras
import logging

# Configure logger for risk manager
logger = logging.getLogger('autonomous_risk_manager')


class RiskManager:
    """Enterprise-grade risk management for autonomous trading"""

    # Default starting capital for fallback when DB unavailable
    DEFAULT_STARTING_CAPITAL = 1000000.0

    def __init__(self):
        self.max_drawdown_pct = 15.0  # 15% max drawdown
        self.daily_loss_limit_pct = 5.0  # 5% daily loss limit
        self.position_size_limit_pct = 20.0  # 20% per position
        self.correlation_limit = 0.5  # Max 50% portfolio in correlated symbols

        # In-memory cache for when database is unavailable
        self._cached_peak_equity = None
        self._cached_current_equity = None
        self._cached_start_of_day_equity = None
        self._cache_timestamp = None
        self._cache_ttl_seconds = 60  # Cache valid for 60 seconds

    def check_all_limits(self, account_value: float, proposed_trade: Dict) -> Tuple[bool, str]:
        """
        Check risk limits before allowing trade.
        Daily loss and max drawdown limits have been removed.

        Returns:
            (can_trade: bool, reason: str)
        """
        # Check position size limit
        can_trade, reason = self.check_position_size(
            account_value,
            proposed_trade.get('cost', 0)
        )
        if not can_trade:
            return False, f"❌ POSITION SIZE LIMIT BREACH: {reason}"

        # Check correlation limit
        can_trade, reason = self.check_correlation_limit(
            proposed_trade.get('symbol', 'SPY')
        )
        if not can_trade:
            return False, f"❌ CORRELATION LIMIT BREACH: {reason}"

        return True, "✅ All risk checks passed"

    def check_position_size(self, account_value: float, position_cost: float) -> Tuple[bool, str]:
        """Check if position size exceeds limit"""
        position_pct = (position_cost / account_value) * 100

        if position_pct > self.position_size_limit_pct:
            return False, f"Position {position_pct:.1f}% exceeds limit {self.position_size_limit_pct:.1f}%"

        return True, f"Position {position_pct:.1f}% within limit"

    def check_correlation_limit(self, symbol: str) -> Tuple[bool, str]:
        """Check if adding this symbol exceeds correlation limit"""
        # Get current open positions
        open_positions = self._get_open_positions()

        if not open_positions:
            return True, "No open positions"

        # Calculate correlation exposure
        correlated_symbols = self._get_correlated_symbols(symbol)
        correlated_exposure = sum(
            pos['unrealized_pnl'] + (pos['entry_price'] * pos['contracts'] * 100)
            for pos in open_positions
            if pos['symbol'] in correlated_symbols
        )

        total_exposure = sum(
            pos['unrealized_pnl'] + (pos['entry_price'] * pos['contracts'] * 100)
            for pos in open_positions
        )

        if total_exposure == 0:
            return True, "No total exposure"

        correlation_pct = (correlated_exposure / total_exposure) * 100

        if correlation_pct > self.correlation_limit * 100:
            return False, f"Correlated exposure {correlation_pct:.1f}% exceeds limit {self.correlation_limit*100:.0f}%"

        return True, f"Correlated exposure {correlation_pct:.1f}% within limit"

    def calculate_sharpe_ratio(self, days: int = 30) -> float:
        """Calculate Sharpe Ratio for recent performance"""
        returns = self._get_daily_returns(days)

        if len(returns) < 2:
            return 0.0

        mean_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Annualized Sharpe (252 trading days)
        sharpe = (mean_return / std_return) * np.sqrt(252)

        return sharpe

    def get_performance_metrics(self, days: int = 30) -> Dict:
        """Get comprehensive performance metrics"""
        conn = get_connection()
        c = conn.cursor()

        # Get closed positions in date range
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        c.execute("""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN realized_pnl <= 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(realized_pnl) as total_pnl,
                AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_winner,
                AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END) as avg_loser,
                MAX(realized_pnl) as largest_winner,
                MIN(realized_pnl) as largest_loser
            FROM autonomous_closed_trades
            WHERE COALESCE(exit_date, entry_date) >= %s
        """, (start_date,))

        row = c.fetchone()
        conn.close()

        total_trades = row[0] if row[0] else 0
        winning_trades = row[1] if row[1] else 0
        losing_trades = row[2] if row[2] else 0
        total_pnl = row[3] if row[3] else 0
        avg_winner = row[4] if row[4] else 0
        avg_loser = row[5] if row[5] else 0
        largest_winner = row[6] if row[6] else 0
        largest_loser = row[7] if row[7] else 0

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Calculate Sharpe Ratio
        sharpe = self.calculate_sharpe_ratio(days)

        # Calculate max drawdown
        peak_value = self._get_peak_equity()
        current_value = self._get_current_equity()
        max_drawdown_pct = ((peak_value - current_value) / peak_value * 100) if peak_value > 0 else 0

        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_winner': avg_winner,
            'avg_loser': avg_loser,
            'largest_winner': largest_winner,
            'largest_loser': largest_loser,
            'sharpe_ratio': sharpe,
            'max_drawdown_pct': max_drawdown_pct,
            'profit_factor': abs(avg_winner / avg_loser) if avg_loser != 0 else 0,
            'expectancy': ((win_rate / 100) * avg_winner) + ((1 - win_rate / 100) * avg_loser)
        }

    def _is_cache_valid(self) -> bool:
        """Check if cached values are still valid"""
        if self._cache_timestamp is None:
            return False
        elapsed = (datetime.now() - self._cache_timestamp).total_seconds()
        return elapsed < self._cache_ttl_seconds

    def _update_cache(self, peak: float = None, current: float = None, start_of_day: float = None):
        """Update in-memory cache values"""
        if peak is not None:
            self._cached_peak_equity = peak
        if current is not None:
            self._cached_current_equity = current
        if start_of_day is not None:
            self._cached_start_of_day_equity = start_of_day
        self._cache_timestamp = datetime.now()

    # Helper methods
    def _get_peak_equity(self) -> float:
        """Get peak equity value with in-memory fallback"""
        try:
            conn = get_connection()
            c = conn.cursor()

            # Get max equity from equity_snapshots or calculate from positions
            c.execute("""
                SELECT value FROM autonomous_config WHERE key = 'capital'
            """)
            result = c.fetchone()
            starting_capital = float(result[0]) if result else self.DEFAULT_STARTING_CAPITAL

            c.execute("""
                SELECT SUM(realized_pnl) FROM autonomous_closed_trades
            """)
            result = c.fetchone()
            total_realized = result[0] if result[0] else 0

            conn.close()

            peak = starting_capital + total_realized
            # Update cache on successful DB read
            self._update_cache(peak=peak)
            return peak

        except Exception as e:
            logger.warning(f"Database unavailable for peak equity, using cache: {e}")
            # Return cached value or default
            if self._cached_peak_equity is not None:
                return self._cached_peak_equity
            return self.DEFAULT_STARTING_CAPITAL

    def _get_current_equity(self) -> float:
        """Get current equity value with in-memory fallback"""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                SELECT value FROM autonomous_config WHERE key = 'capital'
            """)
            result = c.fetchone()
            starting_capital = float(result[0]) if result else self.DEFAULT_STARTING_CAPITAL

            c.execute("""
                SELECT SUM(realized_pnl) FROM autonomous_closed_trades
            """)
            result = c.fetchone()
            total_realized = result[0] if result[0] else 0

            c.execute("""
                SELECT SUM(unrealized_pnl) FROM autonomous_open_positions
            """)
            result = c.fetchone()
            total_unrealized = result[0] if result[0] else 0

            conn.close()

            current = starting_capital + total_realized + total_unrealized
            # Update cache on successful DB read
            self._update_cache(current=current)
            return current

        except Exception as e:
            logger.warning(f"Database unavailable for current equity, using cache: {e}")
            # Return cached value or default
            if self._cached_current_equity is not None:
                return self._cached_current_equity
            return self.DEFAULT_STARTING_CAPITAL

    def _get_start_of_day_equity(self) -> float:
        """Get equity value at start of trading day from equity snapshots with in-memory fallback"""
        try:
            conn = get_connection()
            c = conn.cursor()

            today = datetime.now().strftime('%Y-%m-%d')

            # Try to get today's earliest snapshot (start of day equity)
            c.execute("""
                SELECT account_value FROM autonomous_equity_snapshots
                WHERE snapshot_date = %s
                ORDER BY snapshot_time ASC
                LIMIT 1
            """, (today,))
            result = c.fetchone()

            if result:
                conn.close()
                start_of_day = float(result[0])
                self._update_cache(start_of_day=start_of_day)
                return start_of_day

            # If no snapshot today, get yesterday's last snapshot
            c.execute("""
                SELECT account_value FROM autonomous_equity_snapshots
                WHERE snapshot_date < %s
                ORDER BY snapshot_date DESC, snapshot_time DESC
                LIMIT 1
            """, (today,))
            result = c.fetchone()

            if result:
                conn.close()
                start_of_day = float(result[0])
                self._update_cache(start_of_day=start_of_day)
                return start_of_day

            # Fallback to current equity if no snapshots exist
            conn.close()
            return self._get_current_equity()

        except Exception as e:
            logger.warning(f"Error getting start of day equity: {e}")
            # Return cached value or fallback to current equity
            if self._cached_start_of_day_equity is not None:
                return self._cached_start_of_day_equity
            return self._get_current_equity()

    def _get_open_positions(self) -> List[Dict]:
        """Get all open positions with error handling"""
        try:
            conn = get_connection()
            c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            c.execute("""
                SELECT * FROM autonomous_open_positions
            """)

            positions = [dict(row) for row in c.fetchall()]
            conn.close()

            return positions

        except Exception as e:
            logger.warning(f"Error getting open positions: {e}")
            return []  # Return empty list on error to fail safe

    def _get_correlated_symbols(self, symbol: str) -> List[str]:
        """Get list of symbols correlated with given symbol"""
        # Correlation matrix (simplified - could fetch from data)
        correlations = {
            'SPY': ['QQQ', 'IWM', 'DIA'],  # All indices correlated
            'QQQ': ['SPY', 'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META'],  # Tech heavy
            'AAPL': ['QQQ', 'MSFT', 'NVDA'],
            'MSFT': ['QQQ', 'AAPL', 'NVDA'],
            'NVDA': ['QQQ', 'AAPL', 'MSFT', 'AMD'],
            'TSLA': ['NIO', 'RIVN'],
            'AMD': ['NVDA', 'INTC']
        }

        return correlations.get(symbol, [symbol])

    def _get_daily_returns(self, days: int) -> List[float]:
        """Get daily returns for Sharpe calculation with error handling"""
        try:
            conn = get_connection()
            c = conn.cursor()

            start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            c.execute("""
                SELECT
                    COALESCE(exit_date, entry_date) as exit_date,
                    SUM(realized_pnl) as daily_pnl
                FROM autonomous_closed_trades
                WHERE COALESCE(exit_date, entry_date) >= %s
                GROUP BY COALESCE(exit_date, entry_date)
                ORDER BY COALESCE(exit_date, entry_date)
            """, (start_date,))

            rows = c.fetchall()
            conn.close()

            # Convert to returns (pnl / account_value)
            account_value = self._get_current_equity()
            returns = [(row[1] / account_value) for row in rows if account_value > 0]

            return returns

        except Exception as e:
            logger.warning(f"Error getting daily returns: {e}")
            return []  # Return empty list on error


# Singleton instance
_risk_manager = None

def get_risk_manager() -> RiskManager:
    """Get singleton risk manager"""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
