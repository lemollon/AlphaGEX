"""
Wheel Strategy Implementation for AlphaGEX Autonomous Trader

The Wheel is a 3-phase income strategy:
1. PHASE 1 (CSP): Sell cash-secured puts on stocks you want to own
2. PHASE 2 (ASSIGNED): If assigned, you own 100 shares per contract
3. PHASE 3 (CC): Sell covered calls on your shares until called away
4. REPEAT: Back to Phase 1

This module handles:
- State machine for wheel cycle management
- Assignment detection and processing
- Premium tracking across the full cycle
- Roll logic for both puts and calls
- Integration with autonomous trader
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from database_adapter import get_connection

logger = logging.getLogger(__name__)


class WheelPhase(Enum):
    """Current phase of a wheel cycle"""
    CSP = "CSP"                    # Cash-secured put active
    ASSIGNED = "ASSIGNED"          # Shares assigned, waiting to sell CC
    COVERED_CALL = "COVERED_CALL"  # Covered call active
    CALLED_AWAY = "CALLED_AWAY"    # Shares called away, cycle complete
    CLOSED = "CLOSED"              # Manually closed


class WheelAction(Enum):
    """Actions that can be taken on a wheel position"""
    OPEN_CSP = "OPEN_CSP"
    CSP_EXPIRED_OTM = "CSP_EXPIRED_OTM"
    CSP_ASSIGNED = "CSP_ASSIGNED"
    ROLL_CSP = "ROLL_CSP"
    OPEN_COVERED_CALL = "OPEN_COVERED_CALL"
    CC_EXPIRED_OTM = "CC_EXPIRED_OTM"
    CC_CALLED_AWAY = "CC_CALLED_AWAY"
    ROLL_COVERED_CALL = "ROLL_COVERED_CALL"
    CLOSE_POSITION = "CLOSE_POSITION"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"


@dataclass
class WheelLeg:
    """Represents a single leg (option trade) in the wheel cycle"""
    leg_id: int
    cycle_id: int
    leg_type: str  # 'CSP' or 'CC'
    action: str    # 'SELL_TO_OPEN', 'BUY_TO_CLOSE', 'EXPIRED', 'ASSIGNED', 'CALLED_AWAY'
    strike: float
    expiration_date: date
    contracts: int
    premium_received: float  # Per contract
    premium_paid: float      # If bought to close
    open_date: datetime
    close_date: Optional[datetime] = None
    close_reason: Optional[str] = None
    underlying_price_at_open: float = 0.0
    underlying_price_at_close: float = 0.0
    iv_at_open: float = 0.0
    delta_at_open: float = 0.0
    dte_at_open: int = 0
    contract_symbol: Optional[str] = None

    @property
    def net_premium(self) -> float:
        """Net premium for this leg (received - paid)"""
        return (self.premium_received - self.premium_paid) * self.contracts * 100

    @property
    def is_open(self) -> bool:
        return self.close_date is None


@dataclass
class WheelCycle:
    """Represents a complete wheel cycle from CSP to called away"""
    cycle_id: int
    symbol: str
    status: WheelPhase
    start_date: datetime
    end_date: Optional[datetime] = None

    # Share position tracking
    shares_owned: int = 0
    share_cost_basis: float = 0.0  # Per share cost basis including premiums

    # Premium tracking
    total_csp_premium: float = 0.0
    total_cc_premium: float = 0.0
    total_premium_collected: float = 0.0

    # Assignment/call tracking
    assignment_date: Optional[datetime] = None
    assignment_price: float = 0.0
    called_away_date: Optional[datetime] = None
    called_away_price: float = 0.0

    # P&L
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    # Legs
    legs: List[WheelLeg] = field(default_factory=list)

    # Config
    target_delta_csp: float = 0.30    # Target delta for CSPs (30 delta)
    target_delta_cc: float = 0.30     # Target delta for covered calls
    min_premium_pct: float = 1.0      # Min premium as % of strike
    max_dte: int = 45                 # Maximum DTE for options
    min_dte: int = 21                 # Minimum DTE for options

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def is_active(self) -> bool:
        return self.status not in [WheelPhase.CALLED_AWAY, WheelPhase.CLOSED]

    @property
    def current_leg(self) -> Optional[WheelLeg]:
        """Get the currently open leg"""
        for leg in reversed(self.legs):
            if leg.is_open:
                return leg
        return None


class WheelStrategyManager:
    """
    Manages wheel strategy cycles for the autonomous trader.

    Features:
    - Start new wheel cycles (sell CSP)
    - Detect and process assignments
    - Transition to covered calls after assignment
    - Roll options when advantageous
    - Track full cycle P&L and premiums
    - Support multiple concurrent wheels on different symbols
    """

    def __init__(self):
        # Texas Central Time - standard timezone for all AlphaGEX operations
        self.tz = ZoneInfo("America/Chicago")
        self._db_initialized = False

    def _ensure_db_initialized(self):
        """Lazy database initialization - only when first needed"""
        if not self._db_initialized:
            self._init_database()
            self._db_initialized = True

    def _init_database(self):
        """
        Verify wheel-specific database tables exist.
        NOTE: Tables are now defined in db/config_and_database.py (single source of truth).
        This method just verifies they exist.
        """
        # Tables wheel_cycles, wheel_legs, wheel_activity_log are created by
        # db/config_and_database.py init_database() on app startup.
        # No need to create them here - just log that we're ready.
        logger.info("Wheel strategy tables expected from main schema (db/config_and_database.py)")

    def start_wheel_cycle(
        self,
        symbol: str,
        strike: float,
        expiration_date: date,
        contracts: int,
        premium: float,
        underlying_price: float,
        delta: float = 0.30,
        iv: float = 0.0,
        contract_symbol: str = None
    ) -> int:
        """
        Start a new wheel cycle by selling a cash-secured put.

        Args:
            symbol: Underlying symbol (e.g., 'SPY')
            strike: Put strike price
            expiration_date: Option expiration date
            contracts: Number of contracts to sell
            premium: Premium received per contract
            underlying_price: Current price of underlying
            delta: Delta of the put sold
            iv: Implied volatility at entry
            contract_symbol: Full option contract symbol

        Returns:
            cycle_id: ID of the new wheel cycle
        """
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now(self.tz)
        dte = (expiration_date - now.date()).days
        total_premium = premium * contracts * 100

        # Create the cycle
        cursor.execute('''
            INSERT INTO wheel_cycles (
                symbol, status, start_date,
                total_csp_premium, total_premium_collected,
                target_delta_csp
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (symbol, WheelPhase.CSP.value, now, total_premium, total_premium, delta))

        cycle_id = cursor.fetchone()[0]

        # Create the CSP leg
        cursor.execute('''
            INSERT INTO wheel_legs (
                cycle_id, leg_type, action, strike, expiration_date,
                contracts, premium_received, open_date,
                underlying_price_at_open, iv_at_open, delta_at_open,
                dte_at_open, contract_symbol
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            cycle_id, 'CSP', 'SELL_TO_OPEN', strike, expiration_date,
            contracts, premium, now, underlying_price, iv, delta, dte, contract_symbol
        ))

        leg_id = cursor.fetchone()[0]

        # Log the activity
        self._log_activity(
            cursor, cycle_id, leg_id,
            WheelAction.OPEN_CSP.value,
            f"Opened CSP: {contracts}x {symbol} ${strike}P exp {expiration_date} for ${premium:.2f}/contract",
            premium_impact=total_premium,
            underlying_price=underlying_price,
            option_price=premium
        )

        conn.commit()
        conn.close()

        logger.info(f"Started wheel cycle #{cycle_id}: {symbol} CSP ${strike} exp {expiration_date}")
        return cycle_id

    def process_csp_expiration(self, cycle_id: int, final_underlying_price: float) -> Dict[str, Any]:
        """
        Process CSP expiration - either expired OTM or assigned.

        Args:
            cycle_id: Wheel cycle ID
            final_underlying_price: Price of underlying at expiration

        Returns:
            Dict with action taken and new status
        """
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        # Get cycle and current leg
        cursor.execute('SELECT * FROM wheel_cycles WHERE id = %s', (cycle_id,))
        cycle_row = cursor.fetchone()
        if not cycle_row:
            conn.close()
            raise ValueError(f"Wheel cycle {cycle_id} not found")

        cursor.execute('''
            SELECT * FROM wheel_legs
            WHERE cycle_id = %s AND leg_type = 'CSP' AND close_date IS NULL
            ORDER BY id DESC LIMIT 1
        ''', (cycle_id,))
        leg_row = cursor.fetchone()
        if not leg_row:
            conn.close()
            raise ValueError(f"No open CSP leg found for cycle {cycle_id}")

        # Get column indices (psycopg2 returns tuples)
        leg_id = leg_row[0]
        strike = leg_row[4]
        contracts = leg_row[6]
        premium_received = leg_row[7]

        now = datetime.now(self.tz)
        result = {}

        if final_underlying_price > strike:
            # Expired OTM - keep premium, ready for new CSP
            cursor.execute('''
                UPDATE wheel_legs SET
                    close_date = %s,
                    close_reason = 'EXPIRED_OTM',
                    underlying_price_at_close = %s
                WHERE id = %s
            ''', (now, final_underlying_price, leg_id))

            # Realize the premium as profit
            realized = premium_received * contracts * 100
            cursor.execute('''
                UPDATE wheel_cycles SET
                    realized_pnl = realized_pnl + %s,
                    updated_at = %s
                WHERE id = %s
            ''', (realized, now, cycle_id))

            self._log_activity(
                cursor, cycle_id, leg_id,
                WheelAction.CSP_EXPIRED_OTM.value,
                f"CSP expired OTM. Underlying ${final_underlying_price:.2f} > Strike ${strike}. Premium kept: ${realized:.2f}",
                pnl_impact=realized,
                underlying_price=final_underlying_price
            )

            result = {
                'action': 'EXPIRED_OTM',
                'premium_kept': realized,
                'ready_for': 'NEW_CSP'
            }

        else:
            # Assigned - now own shares
            shares = contracts * 100
            # Cost basis = strike price - premium received per share
            cost_basis = strike - premium_received

            cursor.execute('''
                UPDATE wheel_legs SET
                    close_date = %s,
                    close_reason = 'ASSIGNED',
                    underlying_price_at_close = %s
                WHERE id = %s
            ''', (now, final_underlying_price, leg_id))

            cursor.execute('''
                UPDATE wheel_cycles SET
                    status = %s,
                    shares_owned = %s,
                    share_cost_basis = %s,
                    assignment_date = %s,
                    assignment_price = %s,
                    updated_at = %s
                WHERE id = %s
            ''', (
                WheelPhase.ASSIGNED.value, shares, cost_basis,
                now, strike, now, cycle_id
            ))

            self._log_activity(
                cursor, cycle_id, leg_id,
                WheelAction.CSP_ASSIGNED.value,
                f"Assigned on CSP. Bought {shares} shares at ${strike}. Cost basis: ${cost_basis:.2f}/share",
                underlying_price=final_underlying_price
            )

            result = {
                'action': 'ASSIGNED',
                'shares_owned': shares,
                'cost_basis': cost_basis,
                'assignment_price': strike,
                'ready_for': 'COVERED_CALL'
            }

        conn.commit()
        conn.close()

        logger.info(f"Processed CSP expiration for cycle #{cycle_id}: {result['action']}")
        return result

    def sell_covered_call(
        self,
        cycle_id: int,
        strike: float,
        expiration_date: date,
        premium: float,
        underlying_price: float,
        delta: float = 0.30,
        iv: float = 0.0,
        contract_symbol: str = None
    ) -> int:
        """
        Sell a covered call after being assigned shares.

        Args:
            cycle_id: Wheel cycle ID
            strike: Call strike price (should be above cost basis)
            expiration_date: Option expiration date
            premium: Premium received per contract
            underlying_price: Current price of underlying
            delta: Delta of the call sold
            iv: Implied volatility
            contract_symbol: Full option contract symbol

        Returns:
            leg_id: ID of the new covered call leg
        """
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        # Verify cycle is in ASSIGNED status
        cursor.execute('SELECT status, shares_owned FROM wheel_cycles WHERE id = %s', (cycle_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Wheel cycle {cycle_id} not found")

        status, shares = row
        if status != WheelPhase.ASSIGNED.value:
            conn.close()
            raise ValueError(f"Cycle {cycle_id} is in {status} status, expected ASSIGNED")

        contracts = shares // 100
        now = datetime.now(self.tz)
        dte = (expiration_date - now.date()).days
        total_premium = premium * contracts * 100

        # Create the CC leg
        cursor.execute('''
            INSERT INTO wheel_legs (
                cycle_id, leg_type, action, strike, expiration_date,
                contracts, premium_received, open_date,
                underlying_price_at_open, iv_at_open, delta_at_open,
                dte_at_open, contract_symbol
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            cycle_id, 'CC', 'SELL_TO_OPEN', strike, expiration_date,
            contracts, premium, now, underlying_price, iv, delta, dte, contract_symbol
        ))

        leg_id = cursor.fetchone()[0]

        # Update cycle
        cursor.execute('''
            UPDATE wheel_cycles SET
                status = %s,
                total_cc_premium = total_cc_premium + %s,
                total_premium_collected = total_premium_collected + %s,
                updated_at = %s
            WHERE id = %s
        ''', (WheelPhase.COVERED_CALL.value, total_premium, total_premium, now, cycle_id))

        self._log_activity(
            cursor, cycle_id, leg_id,
            WheelAction.OPEN_COVERED_CALL.value,
            f"Sold CC: {contracts}x ${strike}C exp {expiration_date} for ${premium:.2f}/contract",
            premium_impact=total_premium,
            underlying_price=underlying_price,
            option_price=premium
        )

        conn.commit()
        conn.close()

        logger.info(f"Sold covered call for cycle #{cycle_id}: ${strike}C exp {expiration_date}")
        return leg_id

    def process_cc_expiration(self, cycle_id: int, final_underlying_price: float) -> Dict[str, Any]:
        """
        Process covered call expiration - either expired OTM or called away.

        Args:
            cycle_id: Wheel cycle ID
            final_underlying_price: Price of underlying at expiration

        Returns:
            Dict with action taken and new status
        """
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        # Get cycle and current leg
        cursor.execute('SELECT * FROM wheel_cycles WHERE id = %s', (cycle_id,))
        cycle_row = cursor.fetchone()
        if not cycle_row:
            conn.close()
            raise ValueError(f"Wheel cycle {cycle_id} not found")

        cursor.execute('''
            SELECT * FROM wheel_legs
            WHERE cycle_id = %s AND leg_type = 'CC' AND close_date IS NULL
            ORDER BY id DESC LIMIT 1
        ''', (cycle_id,))
        leg_row = cursor.fetchone()
        if not leg_row:
            conn.close()
            raise ValueError(f"No open CC leg found for cycle {cycle_id}")

        leg_id = leg_row[0]
        strike = leg_row[4]
        contracts = leg_row[6]
        premium_received = leg_row[7]

        # Get cost basis from cycle
        share_cost_basis = cycle_row[6]  # share_cost_basis column

        now = datetime.now(self.tz)
        result = {}

        if final_underlying_price < strike:
            # Expired OTM - keep premium and shares, ready for new CC
            cursor.execute('''
                UPDATE wheel_legs SET
                    close_date = %s,
                    close_reason = 'EXPIRED_OTM',
                    underlying_price_at_close = %s
                WHERE id = %s
            ''', (now, final_underlying_price, leg_id))

            # Realize the premium as profit
            realized = premium_received * contracts * 100
            cursor.execute('''
                UPDATE wheel_cycles SET
                    status = %s,
                    realized_pnl = realized_pnl + %s,
                    updated_at = %s
                WHERE id = %s
            ''', (WheelPhase.ASSIGNED.value, realized, now, cycle_id))

            self._log_activity(
                cursor, cycle_id, leg_id,
                WheelAction.CC_EXPIRED_OTM.value,
                f"CC expired OTM. Underlying ${final_underlying_price:.2f} < Strike ${strike}. Premium kept: ${realized:.2f}",
                pnl_impact=realized,
                underlying_price=final_underlying_price
            )

            result = {
                'action': 'EXPIRED_OTM',
                'premium_kept': realized,
                'shares_retained': contracts * 100,
                'ready_for': 'NEW_COVERED_CALL'
            }

        else:
            # Called away - shares sold at strike
            shares = contracts * 100
            sale_proceeds = strike * shares
            # P&L from share appreciation (strike - cost basis)
            share_pnl = (strike - share_cost_basis) * shares
            cc_premium = premium_received * contracts * 100
            total_pnl = share_pnl + cc_premium

            cursor.execute('''
                UPDATE wheel_legs SET
                    close_date = %s,
                    close_reason = 'CALLED_AWAY',
                    underlying_price_at_close = %s
                WHERE id = %s
            ''', (now, final_underlying_price, leg_id))

            cursor.execute('''
                UPDATE wheel_cycles SET
                    status = %s,
                    shares_owned = 0,
                    called_away_date = %s,
                    called_away_price = %s,
                    realized_pnl = realized_pnl + %s,
                    end_date = %s,
                    updated_at = %s
                WHERE id = %s
            ''', (
                WheelPhase.CALLED_AWAY.value, now, strike,
                total_pnl, now, now, cycle_id
            ))

            self._log_activity(
                cursor, cycle_id, leg_id,
                WheelAction.CC_CALLED_AWAY.value,
                f"Called away at ${strike}. Shares sold for ${sale_proceeds:.2f}. Total cycle P&L: ${total_pnl:.2f}",
                pnl_impact=total_pnl,
                underlying_price=final_underlying_price
            )

            result = {
                'action': 'CALLED_AWAY',
                'sale_price': strike,
                'share_pnl': share_pnl,
                'cc_premium': cc_premium,
                'total_pnl': total_pnl,
                'cycle_complete': True
            }

        conn.commit()
        conn.close()

        logger.info(f"Processed CC expiration for cycle #{cycle_id}: {result['action']}")
        return result

    def roll_position(
        self,
        cycle_id: int,
        new_strike: float,
        new_expiration: date,
        close_price: float,
        open_premium: float,
        underlying_price: float,
        delta: float = 0.30,
        iv: float = 0.0
    ) -> Dict[str, Any]:
        """
        Roll an existing position (CSP or CC) to a new strike/expiration.

        This closes the current leg and opens a new one.

        Args:
            cycle_id: Wheel cycle ID
            new_strike: New strike price
            new_expiration: New expiration date
            close_price: Price to buy back current option
            open_premium: Premium for new option
            underlying_price: Current underlying price
            delta: Target delta for new position
            iv: Implied volatility

        Returns:
            Dict with roll details
        """
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        # Get current open leg
        cursor.execute('''
            SELECT * FROM wheel_legs
            WHERE cycle_id = %s AND close_date IS NULL
            ORDER BY id DESC LIMIT 1
        ''', (cycle_id,))
        leg_row = cursor.fetchone()

        if not leg_row:
            conn.close()
            raise ValueError(f"No open leg found for cycle {cycle_id}")

        old_leg_id = leg_row[0]
        leg_type = leg_row[2]
        old_strike = leg_row[4]
        contracts = leg_row[6]

        now = datetime.now(self.tz)
        dte = (new_expiration - now.date()).days

        # Close old leg
        cursor.execute('''
            UPDATE wheel_legs SET
                close_date = %s,
                premium_paid = %s,
                close_reason = 'ROLLED',
                underlying_price_at_close = %s
            WHERE id = %s
        ''', (now, close_price, underlying_price, old_leg_id))

        # Open new leg
        cursor.execute('''
            INSERT INTO wheel_legs (
                cycle_id, leg_type, action, strike, expiration_date,
                contracts, premium_received, open_date,
                underlying_price_at_open, iv_at_open, delta_at_open, dte_at_open
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            cycle_id, leg_type, 'SELL_TO_OPEN', new_strike, new_expiration,
            contracts, open_premium, now, underlying_price, iv, delta, dte
        ))

        new_leg_id = cursor.fetchone()[0]

        # Calculate net credit/debit
        roll_cost = close_price * contracts * 100
        roll_credit = open_premium * contracts * 100
        net_credit = roll_credit - roll_cost

        # Update cycle premiums
        premium_col = 'total_csp_premium' if leg_type == 'CSP' else 'total_cc_premium'
        cursor.execute(f'''
            UPDATE wheel_cycles SET
                {premium_col} = {premium_col} + %s,
                total_premium_collected = total_premium_collected + %s,
                updated_at = %s
            WHERE id = %s
        ''', (net_credit, net_credit, now, cycle_id))

        action = WheelAction.ROLL_CSP if leg_type == 'CSP' else WheelAction.ROLL_COVERED_CALL
        self._log_activity(
            cursor, cycle_id, new_leg_id,
            action.value,
            f"Rolled {leg_type}: ${old_strike} -> ${new_strike} exp {new_expiration}. Net: ${net_credit:.2f}",
            premium_impact=net_credit,
            underlying_price=underlying_price,
            option_price=open_premium,
            details={'old_strike': old_strike, 'close_price': close_price}
        )

        conn.commit()
        conn.close()

        logger.info(f"Rolled {leg_type} for cycle #{cycle_id}: ${old_strike} -> ${new_strike}")

        return {
            'action': 'ROLLED',
            'leg_type': leg_type,
            'old_strike': old_strike,
            'new_strike': new_strike,
            'new_expiration': str(new_expiration),
            'roll_cost': roll_cost,
            'roll_credit': roll_credit,
            'net_credit': net_credit,
            'new_leg_id': new_leg_id
        }

    def close_cycle(self, cycle_id: int, reason: str, close_price: float = 0.0, underlying_price: float = 0.0) -> Dict[str, Any]:
        """
        Manually close a wheel cycle.

        Args:
            cycle_id: Wheel cycle ID
            reason: Reason for closing
            close_price: Price to close any open option
            underlying_price: Current underlying price

        Returns:
            Dict with close details
        """
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        now = datetime.now(self.tz)

        # Close any open legs
        cursor.execute('''
            UPDATE wheel_legs SET
                close_date = %s,
                premium_paid = %s,
                close_reason = %s,
                underlying_price_at_close = %s
            WHERE cycle_id = %s AND close_date IS NULL
        ''', (now, close_price, f'MANUAL_CLOSE: {reason}', underlying_price, cycle_id))

        # Close the cycle
        cursor.execute('''
            UPDATE wheel_cycles SET
                status = %s,
                end_date = %s,
                updated_at = %s
            WHERE id = %s
            RETURNING realized_pnl, total_premium_collected
        ''', (WheelPhase.CLOSED.value, now, now, cycle_id))

        row = cursor.fetchone()

        self._log_activity(
            cursor, cycle_id, None,
            WheelAction.CLOSE_POSITION.value,
            f"Manually closed cycle: {reason}",
            underlying_price=underlying_price
        )

        conn.commit()
        conn.close()

        return {
            'action': 'CLOSED',
            'reason': reason,
            'final_pnl': row[0] if row else 0,
            'total_premium': row[1] if row else 0
        }

    def get_active_cycles(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get all active wheel cycles, optionally filtered by symbol"""
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        query = '''
            SELECT c.*,
                   l.strike as current_strike,
                   l.expiration_date as current_expiration,
                   l.leg_type as current_leg_type
            FROM wheel_cycles c
            LEFT JOIN wheel_legs l ON l.cycle_id = c.id AND l.close_date IS NULL
            WHERE c.status NOT IN ('CALLED_AWAY', 'CLOSED')
        '''
        params = []

        if symbol:
            query += ' AND c.symbol = %s'
            params.append(symbol)

        query += ' ORDER BY c.start_date DESC'

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        conn.close()

        return [dict(zip(columns, row)) for row in rows]

    def get_cycle_details(self, cycle_id: int) -> Dict[str, Any]:
        """Get full details of a wheel cycle including all legs"""
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        # Get cycle
        cursor.execute('SELECT * FROM wheel_cycles WHERE id = %s', (cycle_id,))
        columns = [desc[0] for desc in cursor.description]
        cycle_row = cursor.fetchone()

        if not cycle_row:
            conn.close()
            return None

        cycle = dict(zip(columns, cycle_row))

        # Get legs
        cursor.execute('''
            SELECT * FROM wheel_legs WHERE cycle_id = %s ORDER BY open_date
        ''', (cycle_id,))
        leg_columns = [desc[0] for desc in cursor.description]
        leg_rows = cursor.fetchall()
        cycle['legs'] = [dict(zip(leg_columns, row)) for row in leg_rows]

        # Get activity log
        cursor.execute('''
            SELECT * FROM wheel_activity_log WHERE cycle_id = %s ORDER BY timestamp
        ''', (cycle_id,))
        log_columns = [desc[0] for desc in cursor.description]
        log_rows = cursor.fetchall()
        cycle['activity_log'] = [dict(zip(log_columns, row)) for row in log_rows]

        conn.close()
        return cycle

    def get_wheel_summary(self, symbol: str = None) -> Dict[str, Any]:
        """Get summary statistics for wheel strategy"""
        self._ensure_db_initialized()
        conn = get_connection()
        cursor = conn.cursor()

        base_query = 'FROM wheel_cycles'
        where = ' WHERE 1=1'
        params = []

        if symbol:
            where += ' AND symbol = %s'
            params.append(symbol)

        # Get counts by status
        cursor.execute(f'''
            SELECT status, COUNT(*), SUM(realized_pnl), SUM(total_premium_collected)
            {base_query} {where}
            GROUP BY status
        ''', params)

        status_stats = {}
        for row in cursor.fetchall():
            status_stats[row[0]] = {
                'count': row[1],
                'realized_pnl': float(row[2] or 0),
                'total_premium': float(row[3] or 0)
            }

        # Get totals
        cursor.execute(f'''
            SELECT
                COUNT(*),
                SUM(realized_pnl),
                SUM(total_premium_collected),
                SUM(total_csp_premium),
                SUM(total_cc_premium),
                AVG(realized_pnl) FILTER (WHERE status = 'CALLED_AWAY')
            {base_query} {where}
        ''', params)

        totals = cursor.fetchone()

        conn.close()

        return {
            'total_cycles': totals[0] or 0,
            'total_realized_pnl': float(totals[1] or 0),
            'total_premium_collected': float(totals[2] or 0),
            'total_csp_premium': float(totals[3] or 0),
            'total_cc_premium': float(totals[4] or 0),
            'avg_pnl_per_complete_cycle': float(totals[5] or 0),
            'by_status': status_stats
        }

    def _log_activity(
        self,
        cursor,
        cycle_id: int,
        leg_id: int,
        action: str,
        description: str,
        premium_impact: float = 0.0,
        pnl_impact: float = 0.0,
        underlying_price: float = None,
        option_price: float = None,
        details: Dict = None
    ):
        """Log activity to wheel_activity_log"""
        import json
        cursor.execute('''
            INSERT INTO wheel_activity_log (
                cycle_id, leg_id, action, description,
                premium_impact, pnl_impact, underlying_price, option_price, details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            cycle_id, leg_id, action, description,
            premium_impact, pnl_impact, underlying_price, option_price,
            json.dumps(details) if details else None
        ))


# Singleton instance for use by autonomous trader
wheel_manager = WheelStrategyManager()
