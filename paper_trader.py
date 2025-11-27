"""
Paper Trading Engine with Auto-Execution
Automatically trades SPY based on AlphaGEX strategies for performance testing
"""

import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import streamlit as st
from config_and_database import DB_PATH
from database_adapter import get_connection
from core_classes_and_engines import BlackScholesPricer
import numpy as np


def get_next_expiration(dte_target: int) -> datetime:
    """
    Calculate the actual expiration date based on DTE target

    Args:
        dte_target: Target days to expiration (e.g., 7 for weekly, 30 for monthly)

    Returns:
        datetime object of the expiration date (next Friday for weeklies)
    """
    today = datetime.now()

    # For 0-7 DTE: Next Friday (weekly)
    if dte_target <= 7:
        days_until_friday = (4 - today.weekday()) % 7
        if days_until_friday == 0 and today.hour >= 16:  # After market close Friday
            days_until_friday = 7
        expiration = today + timedelta(days=days_until_friday)

    # For 8-14 DTE: Friday next week
    elif dte_target <= 14:
        days_until_friday = (4 - today.weekday()) % 7
        expiration = today + timedelta(days=days_until_friday + 7)

    # For 15-30 DTE: Third Friday of next month (monthly)
    else:
        # Move to next month
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)

        # Find third Friday
        first_day = next_month
        first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
        third_friday = first_friday + timedelta(days=14)
        expiration = third_friday

    return expiration


def parse_dte_from_strategy(strategy_name: str, best_time: str = None) -> int:
    """
    Parse DTE from strategy name or best_time field

    Args:
        strategy_name: Strategy name
        best_time: Best time to enter (e.g., "7-14 DTE")

    Returns:
        DTE as integer (defaults to 7)
    """
    # Check best_time first
    if best_time:
        if 'DTE' in best_time:
            parts = best_time.split()
            for part in parts:
                if '-' in part:
                    # Get midpoint of range (e.g., "7-14" -> 10)
                    try:
                        low, high = part.split('-')
                        return int((int(low) + int(high)) / 2)
                    except:
                        pass
                elif part.isdigit():
                    return int(part)

    # Default based on strategy type
    if 'SQUEEZE' in strategy_name.upper():
        return 5  # Short-term for squeezes
    elif 'IRON CONDOR' in strategy_name.upper():
        return 10  # Medium-term for theta plays
    elif 'SPREAD' in strategy_name.upper():
        return 10
    else:
        return 7  # Default weekly


class PaperTradingEngine:
    """Auto-executes paper trades based on AlphaGEX strategies"""

    def __init__(self, db_path: str = DB_PATH, initial_capital: float = 100000):
        self.db_path = db_path
        self.initial_capital = initial_capital
        self.pricer = BlackScholesPricer()
        self._ensure_paper_trading_tables()

    def _ensure_paper_trading_tables(self):
        """Create or update paper trading tables"""
        conn = get_connection()
        c = conn.cursor()

        # Paper positions table with expiration dates
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_positions (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                strategy TEXT NOT NULL,
                action TEXT NOT NULL,
                entry_price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                strike REAL,
                option_type TEXT,
                expiration_date TEXT,
                dte INTEGER,
                entry_spot_price REAL,
                entry_premium REAL,
                current_value REAL,
                unrealized_pnl REAL,
                status TEXT DEFAULT 'OPEN',
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                exit_price REAL,
                realized_pnl REAL,
                exit_reason TEXT,
                confidence_score INTEGER,
                entry_net_gex REAL,
                entry_flip_point REAL,
                notes TEXT
            )
        """)

        # Paper trading performance table
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_performance (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                total_capital REAL NOT NULL,
                open_positions INTEGER,
                closed_positions INTEGER,
                win_rate REAL,
                total_pnl REAL,
                day_pnl REAL,
                best_trade REAL,
                worst_trade REAL,
                avg_win REAL,
                avg_loss REAL,
                notes TEXT
            )
        """)

        # Paper trading config
        c.execute("""
            CREATE TABLE IF NOT EXISTS paper_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Initialize config if not exists
        c.execute("INSERT INTO paper_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('enabled', 'false'))
        c.execute("INSERT INTO paper_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('capital', str(self.initial_capital)))
        c.execute("INSERT INTO paper_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('min_confidence', '70'))
        c.execute("INSERT INTO paper_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('max_position_size', '0.10'))  # 10% max per position
        c.execute("INSERT INTO paper_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING",
                 ('auto_execute', 'false'))

        conn.commit()
        conn.close()

    def get_config(self, key: str) -> str:
        """Get configuration value"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT value FROM paper_config WHERE key = %s", (key,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    def set_config(self, key: str, value: str):
        """Set configuration value"""
        conn = get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO paper_config (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
        conn.commit()
        conn.close()

    def is_enabled(self) -> bool:
        """Check if paper trading is enabled"""
        return self.get_config('enabled') == 'true'

    def is_auto_execute_enabled(self) -> bool:
        """Check if auto-execution is enabled"""
        return self.get_config('auto_execute') == 'true'

    def get_available_capital(self) -> float:
        """Calculate available capital for new positions"""
        total_capital = float(self.get_config('capital'))

        # Get current open positions value
        conn = get_connection()
        query = """
            SELECT SUM(ABS(entry_premium * quantity))
            FROM paper_positions
            WHERE status = 'OPEN'
        """
        result = pd.read_sql_query(query, conn.raw_connection)
        conn.close()

        used_capital = result.iloc[0, 0] if not result.iloc[0, 0] is None else 0
        return total_capital - used_capital

    def calculate_position_size(self, setup: Dict, spot_price: float) -> Tuple[int, float]:
        """
        Calculate appropriate position size based on strategy and risk

        Args:
            setup: Strategy setup dictionary
            spot_price: Current spot price

        Returns:
            (quantity, premium) tuple
        """
        available_capital = self.get_available_capital()
        max_position_pct = float(self.get_config('max_position_size'))
        max_position_value = available_capital * max_position_pct

        # Estimate option premium based on strategy
        strategy = setup.get('strategy', '')
        confidence = setup.get('confidence', 70)

        # Get strike from action if available
        action = setup.get('action', '')
        strike = None
        option_type = None

        if 'CALL' in action.upper():
            option_type = 'call'
            # Try to extract strike from action
            try:
                strike = float([word for word in action.split() if word.replace('.', '').isdigit()][0])
            except:
                strike = spot_price  # ATM fallback
        elif 'PUT' in action.upper():
            option_type = 'put'
            try:
                strike = float([word for word in action.split() if word.replace('.', '').isdigit()][0])
            except:
                strike = spot_price  # ATM fallback
        else:
            # For spreads/condors, use lower capital requirement
            strike = spot_price
            option_type = 'spread'

        # Calculate estimated premium
        if 'IRON CONDOR' in strategy.upper() or 'SPREAD' in strategy.upper():
            # Spreads collect credit, estimate $1-3 per contract
            estimated_premium = 2.0 * 100  # $200 credit per IC
        else:
            # Single options - estimate using BS or simple heuristic
            dte = parse_dte_from_strategy(strategy, setup.get('best_time'))

            if option_type in ['call', 'put']:
                option_calc = self.pricer.calculate_option_price(
                    spot_price, strike, dte/365, 0.25, option_type
                )
                estimated_premium = option_calc.get('price', 3.0) * 100  # Per contract
            else:
                estimated_premium = 300  # Default $3 per contract

        # Calculate quantity based on max position size
        quantity = int(max_position_value / max(estimated_premium, 100))
        quantity = max(1, min(quantity, 10))  # Min 1, max 10 contracts

        # Adjust based on confidence
        if confidence >= 80:
            quantity = quantity  # Full size for high confidence
        elif confidence >= 70:
            quantity = max(1, int(quantity * 0.75))  # 75% size
        else:
            quantity = max(1, int(quantity * 0.5))  # 50% size for lower confidence

        return quantity, estimated_premium / 100  # Return premium per contract

    def open_position(self, setup: Dict, gex_data: Dict) -> Optional[int]:
        """
        Open a new paper trading position

        Args:
            setup: Strategy setup dictionary
            gex_data: Current GEX data

        Returns:
            Position ID if successful, None otherwise
        """
        if not self.is_enabled():
            return None

        symbol = setup.get('symbol', 'SPY')
        spot_price = gex_data.get('spot_price', 0)

        # Calculate position size
        quantity, premium = self.calculate_position_size(setup, spot_price)

        # Parse expiration
        dte = parse_dte_from_strategy(setup.get('strategy', ''), setup.get('best_time'))
        expiration_date = get_next_expiration(dte)

        # Extract strike and option type from action
        action = setup.get('action', '')
        strike = spot_price  # Default
        option_type = 'call'  # Default

        if 'CALL' in action.upper():
            option_type = 'call'
            try:
                strike = float([word for word in action.split() if word.replace('.', '').isdigit()][0])
            except:
                strike = setup.get('target_1', spot_price)
        elif 'PUT' in action.upper():
            option_type = 'put'
            try:
                strike = float([word for word in action.split() if word.replace('.', '').isdigit()][0])
            except:
                strike = setup.get('target_1', spot_price)
        elif 'SPREAD' in action.upper() or 'CONDOR' in action.upper():
            option_type = 'spread'

        conn = get_connection()
        c = conn.cursor()

        c.execute("""
            INSERT INTO paper_positions (
                symbol, strategy, action, entry_price, quantity, strike, option_type,
                expiration_date, dte, entry_spot_price, entry_premium, current_value,
                unrealized_pnl, status, opened_at, confidence_score, entry_net_gex,
                entry_flip_point, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            symbol,
            setup.get('strategy', 'Unknown'),
            action,
            premium,  # Entry price = premium
            quantity,
            strike,
            option_type,
            expiration_date.strftime('%Y-%m-%d'),
            dte,
            spot_price,
            premium,
            premium * quantity * 100,  # Current value (contracts * 100 shares)
            0.0,  # Unrealized P&L starts at 0
            'OPEN',
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            setup.get('confidence', 70),
            gex_data.get('net_gex', 0),
            gex_data.get('flip_point', 0),
            setup.get('reasoning', '')
        ))

        result = c.fetchone()
        position_id = result[0] if result else None
        conn.commit()
        conn.close()

        return position_id

    def update_position_value(self, position_id: int, current_spot_price: float):
        """Update the current value and P&L of a position"""
        conn = get_connection()
        c = conn.cursor()

        # Get position details
        c.execute("""
            SELECT strike, option_type, expiration_date, entry_premium, quantity, entry_spot_price
            FROM paper_positions WHERE id = %s AND status = 'OPEN'
        """, (position_id,))

        result = c.fetchone()
        if not result:
            conn.close()
            return

        strike, option_type, exp_date_str, entry_premium, quantity, entry_spot = result

        # Calculate DTE
        exp_date = datetime.strptime(exp_date_str, '%Y-%m-%d')
        dte = max(0, (exp_date - datetime.now()).days)

        # Calculate current option value
        if option_type in ['call', 'put'] and dte > 0:
            option_calc = self.pricer.calculate_option_price(
                current_spot_price, strike, dte/365, 0.25, option_type
            )
            current_premium = option_calc.get('price', entry_premium)
        elif option_type == 'spread':
            # Estimate spread value based on price movement
            price_move_pct = (current_spot_price - entry_spot) / entry_spot
            # Spreads lose value as underlying moves favorably
            if abs(price_move_pct) < 0.02:  # Within 2% range
                current_premium = entry_premium * 0.7  # Decay some value
            else:
                current_premium = entry_premium * 0.5  # More decay
        else:
            # Expired or unknown, use intrinsic value
            if option_type == 'call':
                current_premium = max(0, current_spot_price - strike)
            elif option_type == 'put':
                current_premium = max(0, strike - current_spot_price)
            else:
                current_premium = 0

        # Calculate P&L
        current_value = current_premium * quantity * 100
        entry_value = entry_premium * quantity * 100
        unrealized_pnl = current_value - entry_value

        # Update database
        c.execute("""
            UPDATE paper_positions
            SET current_value = %s, unrealized_pnl = %s
            WHERE id = %s
        """, (current_value, unrealized_pnl, position_id))

        conn.commit()
        conn.close()

    def check_exit_conditions(self, position: Dict, current_gex: Dict) -> Tuple[bool, str]:
        """
        Check if position should be closed based on exit conditions

        Args:
            position: Position dictionary
            current_gex: Current GEX data

        Returns:
            (should_exit, reason) tuple
        """
        current_spot = current_gex.get('spot_price', 0)
        entry_spot = position.get('entry_spot_price', current_spot)
        unrealized_pnl = position.get('unrealized_pnl', 0)
        entry_value = position.get('entry_premium', 1) * position.get('quantity', 1) * 100

        # Calculate P&L percentage
        pnl_pct = (unrealized_pnl / entry_value * 100) if entry_value > 0 else 0

        # Exit condition 1: Profit target hit (>50% gain)
        if pnl_pct >= 50:
            return True, f"Profit target hit: +{pnl_pct:.1f}%"

        # Exit condition 2: Stop loss hit (<-30% loss)
        if pnl_pct <= -30:
            return True, f"Stop loss hit: {pnl_pct:.1f}%"

        # Exit condition 3: Expiration approaching (1 DTE or less)
        exp_date = datetime.strptime(position.get('expiration_date', ''), '%Y-%m-%d')
        dte = (exp_date - datetime.now()).days
        if dte <= 1:
            return True, f"Expiration approaching: {dte} DTE remaining"

        # Exit condition 4: GEX regime flip (invalidates thesis)
        entry_gex = position.get('entry_net_gex', 0)
        current_gex_value = current_gex.get('net_gex', 0)

        # Check if GEX sign flipped
        if (entry_gex > 0 and current_gex_value < 0) or (entry_gex < 0 and current_gex_value > 0):
            return True, "GEX regime flip - thesis invalidated"

        # Exit condition 5: Small profit at 7+ DTE (>20% gain, take it)
        if dte >= 7 and pnl_pct >= 20:
            return True, f"Taking profit early: +{pnl_pct:.1f}% with {dte} DTE left"

        return False, ""

    def close_position(self, position_id: int, exit_reason: str = "Manual close"):
        """Close a paper trading position"""
        conn = get_connection()
        c = conn.cursor()

        # Get current position value
        c.execute("""
            SELECT current_value, entry_premium, quantity, unrealized_pnl
            FROM paper_positions WHERE id = %s AND status = 'OPEN'
        """, (position_id,))

        result = c.fetchone()
        if not result:
            conn.close()
            return

        current_value, entry_premium, quantity, unrealized_pnl = result

        # Calculate exit price
        exit_price = current_value / (quantity * 100) if quantity > 0 else entry_premium

        # Update position
        c.execute("""
            UPDATE paper_positions
            SET status = 'CLOSED',
                closed_at = %s,
                exit_price = %s,
                realized_pnl = %s,
                exit_reason = %s
            WHERE id = %s
        """, (
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            exit_price,
            unrealized_pnl,  # Unrealized becomes realized
            exit_reason,
            position_id
        ))

        conn.commit()
        conn.close()

    def auto_manage_positions(self, api_client):
        """Automatically manage all open positions"""
        if not self.is_auto_execute_enabled():
            return []

        conn = get_connection()
        positions = pd.read_sql_query("""
            SELECT * FROM paper_positions WHERE status = 'OPEN'
        """, conn.raw_connection)
        conn.close()

        actions_taken = []

        for _, position in positions.iterrows():
            symbol = position['symbol']

            try:
                # Get current market data
                current_gex = api_client.get_net_gamma(symbol)
                if current_gex and not current_gex.get('error'):
                    current_spot = current_gex.get('spot_price', 0)

                    # Update position value
                    self.update_position_value(position['id'], current_spot)

                    # Re-fetch position with updated values
                    conn = get_connection()
                    updated_position = pd.read_sql_query(
                        "SELECT * FROM paper_positions WHERE id = %s",
                        conn.raw_connection, params=(position['id'],)
                    ).iloc[0]
                    conn.close()

                    # Check exit conditions
                    should_exit, reason = self.check_exit_conditions(
                        updated_position.to_dict(), current_gex
                    )

                    if should_exit:
                        self.close_position(position['id'], reason)
                        actions_taken.append({
                            'action': 'CLOSE',
                            'position_id': position['id'],
                            'symbol': symbol,
                            'strategy': position['strategy'],
                            'reason': reason,
                            'pnl': updated_position['unrealized_pnl']
                        })
            except Exception as e:
                print(f"Error managing position {position['id']}: {e}")
                continue

        return actions_taken

    def evaluate_new_setup(self, setup: Dict, gex_data: Dict) -> bool:
        """
        Evaluate if a new setup should be auto-executed

        Args:
            setup: Strategy setup to evaluate
            gex_data: Current GEX data

        Returns:
            True if setup should be executed
        """
        if not self.is_auto_execute_enabled():
            return False

        # Check minimum confidence
        min_confidence = int(self.get_config('min_confidence'))
        if setup.get('confidence', 0) < min_confidence:
            return False

        # Check available capital
        available = self.get_available_capital()
        total_capital = float(self.get_config('capital'))

        if available < total_capital * 0.1:  # Need at least 10% capital available
            return False

        # Check if we already have a similar open position
        conn = get_connection()
        similar_positions = pd.read_sql_query("""
            SELECT COUNT(*) as count FROM paper_positions
            WHERE status = 'OPEN' AND symbol = %s AND strategy = %s
        """, conn.raw_connection, params=(setup.get('symbol', 'SPY'), setup.get('strategy', '')))
        conn.close()

        if similar_positions.iloc[0]['count'] > 0:
            return False  # Don't double up on same strategy

        return True

    def get_performance_summary(self) -> Dict:
        """Get overall paper trading performance"""
        conn = get_connection()

        # Get all closed positions
        closed_positions = pd.read_sql_query("""
            SELECT * FROM paper_positions WHERE status = 'CLOSED'
        """, conn.raw_connection)

        # Get open positions
        open_positions = pd.read_sql_query("""
            SELECT * FROM paper_positions WHERE status = 'OPEN'
        """, conn.raw_connection)

        conn.close()

        total_capital = float(self.get_config('capital'))

        summary = {
            'total_capital': total_capital,
            'open_positions': len(open_positions),
            'closed_positions': len(closed_positions),
            'total_trades': len(closed_positions),
            'win_rate': 0,
            'total_realized_pnl': 0,
            'total_unrealized_pnl': 0,
            'best_trade': 0,
            'worst_trade': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'current_value': total_capital
        }

        if not closed_positions.empty:
            summary['total_realized_pnl'] = closed_positions['realized_pnl'].sum()
            winners = closed_positions[closed_positions['realized_pnl'] > 0]
            losers = closed_positions[closed_positions['realized_pnl'] < 0]

            summary['win_rate'] = (len(winners) / len(closed_positions) * 100)
            summary['best_trade'] = closed_positions['realized_pnl'].max()
            summary['worst_trade'] = closed_positions['realized_pnl'].min()
            summary['avg_win'] = winners['realized_pnl'].mean() if not winners.empty else 0
            summary['avg_loss'] = losers['realized_pnl'].mean() if not losers.empty else 0

        if not open_positions.empty:
            summary['total_unrealized_pnl'] = open_positions['unrealized_pnl'].sum()

        summary['current_value'] = total_capital + summary['total_realized_pnl'] + summary['total_unrealized_pnl']

        return summary
