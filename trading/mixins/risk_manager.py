"""
Risk Management Mixin

Provides portfolio-level risk management, Greeks tracking, and performance metrics.
Used by AutonomousPaperTrader for both SPY and SPX trading.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from zoneinfo import ZoneInfo
import logging

from database_adapter import get_connection

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class RiskManagerMixin:
    """
    Mixin providing risk management functionality.

    Requires from main class:
    - self.symbol: str
    - self.starting_capital: float
    """

    # Default risk limits (can be overridden per symbol)
    DEFAULT_RISK_LIMITS = {
        'SPY': {
            'max_position_pct': 0.05,  # 5% max per position
            'max_delta_exposure': 50000,  # $50K delta exposure
            'max_contracts_per_trade': 100,
            'max_daily_loss_pct': 0.05,  # 5% daily loss limit
            'max_open_positions': 10,
        },
        'SPX': {
            'max_position_pct': 0.05,  # 5% max per position
            'max_delta_exposure': 500000,  # $500K delta exposure (institutional)
            'max_contracts_per_trade': 50,  # SPX contracts are larger
            'max_daily_loss_pct': 0.05,
            'max_open_positions': 10,
        },
        'QQQ': {
            'max_position_pct': 0.05,
            'max_delta_exposure': 50000,
            'max_contracts_per_trade': 100,
            'max_daily_loss_pct': 0.05,
            'max_open_positions': 10,
        },
    }

    @property
    def max_position_pct(self) -> float:
        """Maximum position size as percentage of capital."""
        limits = self.DEFAULT_RISK_LIMITS.get(self.symbol, self.DEFAULT_RISK_LIMITS['SPY'])
        return limits['max_position_pct']

    @property
    def max_delta_exposure(self) -> float:
        """Maximum delta exposure in dollars."""
        limits = self.DEFAULT_RISK_LIMITS.get(self.symbol, self.DEFAULT_RISK_LIMITS['SPY'])
        return limits['max_delta_exposure']

    @property
    def max_contracts_per_trade(self) -> int:
        """Maximum contracts per single trade."""
        limits = self.DEFAULT_RISK_LIMITS.get(self.symbol, self.DEFAULT_RISK_LIMITS['SPY'])
        return limits['max_contracts_per_trade']

    def get_portfolio_greeks(self) -> Dict:
        """
        Calculate aggregate Greeks across all open positions.

        Returns:
            Dict with total delta, gamma, theta, vega
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Query open positions for this symbol from unified table
            c.execute("""
                SELECT action as option_type, contracts, strike
                FROM autonomous_open_positions
                WHERE symbol = %s
            """, (self.symbol,))

            positions = c.fetchall()
            conn.close()

            # For now, return position count without Greeks calculation
            # Greeks would need to be calculated from live option prices
            position_count = len(positions)

            return {
                'total_delta': 0,
                'total_gamma': 0,
                'total_theta': 0,
                'total_vega': 0,
                'position_count': position_count,
                'delta_exposure_pct': 0
            }

        except Exception as e:
            logger.warning(f"Error calculating portfolio Greeks: {e}")
            return {
                'total_delta': 0, 'total_gamma': 0, 'total_theta': 0, 'total_vega': 0,
                'position_count': 0, 'delta_exposure_pct': 0, 'error': str(e)
            }

    def check_risk_limits(self, proposed_trade: Dict) -> Tuple[bool, str]:
        """
        Check if a proposed trade passes all risk limits.

        Args:
            proposed_trade: Dict with 'contracts', 'entry_price', 'delta'

        Returns:
            Tuple of (can_trade: bool, reason: str)
        """
        try:
            contracts = proposed_trade.get('contracts', 0)
            entry_price = proposed_trade.get('entry_price', 0)
            delta = proposed_trade.get('delta', 0.5)

            # Get current state
            greeks = self.get_portfolio_greeks()
            available = self.get_available_capital()
            daily_pnl = self._get_daily_pnl()

            # Check max contracts
            if contracts > self.max_contracts_per_trade:
                return False, f"Exceeds max contracts ({contracts} > {self.max_contracts_per_trade})"

            # Check position size
            position_value = contracts * entry_price * 100
            position_pct = position_value / self.starting_capital
            if position_pct > self.max_position_pct:
                return False, f"Position too large ({position_pct:.1%} > {self.max_position_pct:.1%})"

            # Check available capital
            if position_value > available:
                return False, f"Insufficient capital (${position_value:,.0f} > ${available:,.0f})"

            # Check delta exposure
            new_delta = abs(greeks['total_delta']) + abs(delta * contracts * 100)
            if new_delta > self.max_delta_exposure:
                return False, f"Would exceed delta exposure (${new_delta:,.0f} > ${self.max_delta_exposure:,.0f})"

            # Check daily loss limit
            if daily_pnl < -(self.starting_capital * self.DEFAULT_RISK_LIMITS.get(self.symbol, {}).get('max_daily_loss_pct', 0.05)):
                return False, f"Daily loss limit reached (${daily_pnl:,.0f})"

            # Check max positions
            max_positions = self.DEFAULT_RISK_LIMITS.get(self.symbol, {}).get('max_open_positions', 10)
            if greeks['position_count'] >= max_positions:
                return False, f"Max positions reached ({greeks['position_count']} >= {max_positions})"

            return True, "Trade passes all risk checks"

        except Exception as e:
            logger.warning(f"Error checking risk limits: {e}")
            return False, f"Risk check failed: {e}"

    def get_performance_summary(self) -> Dict:
        """
        Get comprehensive performance metrics.

        Returns:
            Dict with P&L, win rate, Sharpe, drawdown, etc.
        """
        try:
            conn = get_connection()
            c = conn.cursor()

            # Get closed trades stats from unified table filtered by symbol
            c.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(realized_pnl) as total_pnl,
                    AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) as avg_win,
                    AVG(CASE WHEN realized_pnl <= 0 THEN realized_pnl END) as avg_loss,
                    MAX(realized_pnl) as largest_win,
                    MIN(realized_pnl) as largest_loss
                FROM autonomous_closed_trades
                WHERE symbol = %s
            """, (self.symbol,))

            row = c.fetchone()

            total_trades = row[0] or 0
            winning_trades = row[1] or 0
            total_pnl = float(row[2] or 0)
            avg_win = float(row[3] or 0)
            avg_loss = float(row[4] or 0)
            largest_win = float(row[5] or 0)
            largest_loss = float(row[6] or 0)

            # Calculate metrics
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            losing_trades = total_trades - winning_trades
            total_return_pct = (total_pnl / self.starting_capital * 100) if self.starting_capital > 0 else 0

            # Calculate expectancy
            if total_trades > 0:
                expectancy = (win_rate/100 * avg_win) + ((1 - win_rate/100) * avg_loss)
            else:
                expectancy = 0

            # Get max drawdown
            max_drawdown = self._get_max_drawdown()

            # Get today's P&L
            today_pnl = self._get_daily_pnl()

            # Get open positions value
            greeks = self.get_portfolio_greeks()

            conn.close()

            return {
                'symbol': self.symbol,
                'starting_capital': self.starting_capital,
                'current_equity': self.starting_capital + total_pnl,
                'total_pnl': round(total_pnl, 2),
                'total_return_pct': round(total_return_pct, 2),
                'today_pnl': round(today_pnl, 2),
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 1),
                'avg_win': round(avg_win, 2),
                'avg_loss': round(avg_loss, 2),
                'largest_win': round(largest_win, 2),
                'largest_loss': round(largest_loss, 2),
                'expectancy': round(expectancy, 2),
                'max_drawdown_pct': round(max_drawdown, 2),
                'open_positions': greeks['position_count'],
                'delta_exposure': greeks['total_delta'],
                'timestamp': datetime.now(CENTRAL_TZ).isoformat()
            }

        except Exception as e:
            logger.warning(f"Error getting performance summary: {e}")
            return {
                'symbol': self.symbol,
                'starting_capital': self.starting_capital,
                'error': str(e)
            }

    def _get_daily_pnl(self) -> float:
        """Get today's realized P&L."""
        try:
            conn = get_connection()
            c = conn.cursor()

            today = datetime.now(CENTRAL_TZ).strftime('%Y-%m-%d')

            c.execute("""
                SELECT COALESCE(SUM(realized_pnl), 0)
                FROM autonomous_closed_trades
                WHERE exit_date = %s AND symbol = %s
            """, (today, self.symbol))

            result = c.fetchone()
            conn.close()

            return float(result[0]) if result else 0.0

        except Exception as e:
            logger.warning(f"Error getting daily PnL: {e}")
            return 0.0

    def _get_max_drawdown(self) -> float:
        """Calculate maximum drawdown percentage."""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                SELECT exit_date, realized_pnl
                FROM autonomous_closed_trades
                WHERE symbol = %s
                ORDER BY exit_date ASC
            """, (self.symbol,))

            trades = c.fetchall()
            conn.close()

            if not trades:
                return 0.0

            # Calculate running equity and drawdown
            cumulative_pnl = 0
            peak_equity = self.starting_capital
            max_drawdown = 0

            for _, pnl in trades:
                cumulative_pnl += float(pnl or 0)
                current_equity = self.starting_capital + cumulative_pnl

                if current_equity > peak_equity:
                    peak_equity = current_equity

                drawdown = (peak_equity - current_equity) / peak_equity * 100 if peak_equity > 0 else 0
                max_drawdown = max(max_drawdown, drawdown)

            return max_drawdown

        except Exception as e:
            logger.warning(f"Error calculating max drawdown: {e}")
            return 0.0

    def get_open_positions_summary(self) -> Dict:
        """Get summary of all open positions."""
        try:
            conn = get_connection()
            c = conn.cursor()

            c.execute("""
                SELECT
                    id, action as option_type, strike, expiration_date, contracts,
                    entry_price, current_price, unrealized_pnl, strategy
                FROM autonomous_open_positions
                WHERE symbol = %s
                ORDER BY entry_date DESC
            """, (self.symbol,))

            positions = []
            total_unrealized = 0

            for row in c.fetchall():
                unrealized = float(row[7] or 0)
                total_unrealized += unrealized
                positions.append({
                    'id': row[0],
                    'option_type': row[1],
                    'strike': row[2],
                    'expiration': str(row[3]) if row[3] else None,
                    'contracts': row[4],
                    'entry_price': float(row[5] or 0),
                    'current_price': float(row[6] or 0),
                    'unrealized_pnl': round(unrealized, 2),
                    'strategy': row[8]
                })

            conn.close()

            return {
                'positions': positions,
                'count': len(positions),
                'total_unrealized_pnl': round(total_unrealized, 2)
            }

        except Exception as e:
            logger.warning(f"Error getting open positions: {e}")
            return {'positions': [], 'count': 0, 'total_unrealized_pnl': 0, 'error': str(e)}
