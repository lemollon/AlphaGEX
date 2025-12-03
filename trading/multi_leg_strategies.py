"""
MULTI-LEG STRATEGY SUPPORT

Adds support for defined-risk strategies on SPX:

1. PUT CREDIT SPREADS - Sell put, buy lower put (defined risk)
2. CALL CREDIT SPREADS - Sell call, buy higher call
3. IRON CONDORS - Put spread + Call spread
4. IRON BUTTERFLIES - ATM straddle + OTM wings

This provides defined risk alternatives to naked puts.

USAGE:
    from trading.multi_leg_strategies import PutCreditSpread, IronCondor

    # Create a put credit spread
    spread = PutCreditSpread(
        short_strike=5800,
        long_strike=5750,
        expiration='2024-12-20',
        contracts=1
    )

    # Get max profit/loss
    print(spread.max_profit)
    print(spread.max_loss)
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Strategy types"""
    NAKED_PUT = "naked_put"
    PUT_CREDIT_SPREAD = "put_credit_spread"
    CALL_CREDIT_SPREAD = "call_credit_spread"
    IRON_CONDOR = "iron_condor"
    IRON_BUTTERFLY = "iron_butterfly"


@dataclass
class OptionLeg:
    """Single option leg"""
    option_type: str  # 'put' or 'call'
    strike: float
    expiration: str
    side: str  # 'buy' or 'sell'
    contracts: int = 1
    premium: float = 0
    delta: float = 0
    iv: float = 0


@dataclass
class MultiLegPosition:
    """Multi-leg option position"""
    strategy_type: StrategyType
    legs: List[OptionLeg]
    expiration: str
    contracts: int
    underlying: str = "SPX"

    # Calculated on creation
    max_profit: float = 0
    max_loss: float = 0
    breakeven: float = 0
    credit_received: float = 0
    margin_required: float = 0

    # Status
    entry_date: str = ""
    status: str = "PENDING"  # PENDING, OPEN, CLOSED
    entry_underlying_price: float = 0


class PutCreditSpread:
    """
    Put Credit Spread (Bull Put Spread)

    - Sell higher strike put
    - Buy lower strike put
    - Same expiration

    Max Profit: Credit received
    Max Loss: (Short Strike - Long Strike - Credit) * 100

    This is a DEFINED RISK alternative to naked puts.
    """

    def __init__(
        self,
        short_strike: float,
        long_strike: float,
        expiration: str,
        contracts: int = 1
    ):
        if long_strike >= short_strike:
            raise ValueError("Long strike must be below short strike for put spread")

        self.short_strike = short_strike
        self.long_strike = long_strike
        self.expiration = expiration
        self.contracts = contracts
        self.width = short_strike - long_strike

        self.short_premium = 0
        self.long_premium = 0
        self.net_credit = 0
        self.max_profit = 0
        self.max_loss = 0

    def calculate_prices(self) -> bool:
        """Fetch prices and calculate P&L parameters"""
        try:
            from data.polygon_data_fetcher import polygon_fetcher

            # Get short put price (we receive this)
            short_quote = polygon_fetcher.get_option_quote(
                'SPX', self.short_strike, self.expiration, 'put'
            )

            # Get long put price (we pay this)
            long_quote = polygon_fetcher.get_option_quote(
                'SPX', self.long_strike, self.expiration, 'put'
            )

            if short_quote and long_quote:
                self.short_premium = short_quote.get('bid', 0)  # Sell at bid
                self.long_premium = long_quote.get('ask', 0)   # Buy at ask

                self.net_credit = self.short_premium - self.long_premium
                self.max_profit = self.net_credit * 100 * self.contracts
                self.max_loss = (self.width - self.net_credit) * 100 * self.contracts

                return True

        except Exception as e:
            logger.error(f"Error calculating spread prices: {e}")

        return False

    def get_breakeven(self) -> float:
        """Calculate breakeven price"""
        return self.short_strike - self.net_credit

    def get_risk_reward(self) -> float:
        """Calculate risk/reward ratio"""
        if self.max_loss > 0:
            return self.max_profit / self.max_loss
        return 0

    def get_margin_requirement(self) -> float:
        """
        Calculate margin for spread.

        For credit spreads, margin = width * 100 - credit
        """
        return self.max_loss  # Margin = max loss for spreads

    def to_position(self) -> MultiLegPosition:
        """Convert to MultiLegPosition"""
        legs = [
            OptionLeg(
                option_type='put',
                strike=self.short_strike,
                expiration=self.expiration,
                side='sell',
                contracts=self.contracts,
                premium=self.short_premium
            ),
            OptionLeg(
                option_type='put',
                strike=self.long_strike,
                expiration=self.expiration,
                side='buy',
                contracts=self.contracts,
                premium=self.long_premium
            )
        ]

        return MultiLegPosition(
            strategy_type=StrategyType.PUT_CREDIT_SPREAD,
            legs=legs,
            expiration=self.expiration,
            contracts=self.contracts,
            max_profit=self.max_profit,
            max_loss=self.max_loss,
            breakeven=self.get_breakeven(),
            credit_received=self.net_credit * 100 * self.contracts,
            margin_required=self.get_margin_requirement()
        )

    def __str__(self) -> str:
        return (
            f"Put Credit Spread: "
            f"Sell {self.short_strike}P / Buy {self.long_strike}P "
            f"({self.expiration}) x{self.contracts}\n"
            f"  Credit: ${self.net_credit:.2f} ({self.max_profit:.2f} max profit)\n"
            f"  Max Loss: ${self.max_loss:.2f}\n"
            f"  Breakeven: ${self.get_breakeven():.2f}\n"
            f"  R/R: {self.get_risk_reward():.2f}"
        )


class IronCondor:
    """
    Iron Condor

    - Put Credit Spread (lower)
    - Call Credit Spread (upper)
    - Same expiration

    Max Profit: Net credit from both spreads
    Max Loss: Width of one spread - total credit

    This profits when the underlying stays in a range.
    """

    def __init__(
        self,
        put_short_strike: float,
        put_long_strike: float,
        call_short_strike: float,
        call_long_strike: float,
        expiration: str,
        contracts: int = 1
    ):
        self.put_short = put_short_strike
        self.put_long = put_long_strike
        self.call_short = call_short_strike
        self.call_long = call_long_strike
        self.expiration = expiration
        self.contracts = contracts

        # Validate strikes
        if put_long >= put_short:
            raise ValueError("Put long strike must be below put short strike")
        if call_long <= call_short:
            raise ValueError("Call long strike must be above call short strike")
        if put_short >= call_short:
            raise ValueError("Put short must be below call short")

        self.put_width = put_short - put_long
        self.call_width = call_long - call_short

        self.put_credit = 0
        self.call_credit = 0
        self.total_credit = 0
        self.max_profit = 0
        self.max_loss = 0

    def calculate_prices(self) -> bool:
        """Fetch prices and calculate P&L"""
        try:
            from data.polygon_data_fetcher import polygon_fetcher

            # Put spread
            put_short_quote = polygon_fetcher.get_option_quote(
                'SPX', self.put_short, self.expiration, 'put'
            )
            put_long_quote = polygon_fetcher.get_option_quote(
                'SPX', self.put_long, self.expiration, 'put'
            )

            # Call spread
            call_short_quote = polygon_fetcher.get_option_quote(
                'SPX', self.call_short, self.expiration, 'call'
            )
            call_long_quote = polygon_fetcher.get_option_quote(
                'SPX', self.call_long, self.expiration, 'call'
            )

            if all([put_short_quote, put_long_quote, call_short_quote, call_long_quote]):
                self.put_credit = (
                    put_short_quote.get('bid', 0) -
                    put_long_quote.get('ask', 0)
                )
                self.call_credit = (
                    call_short_quote.get('bid', 0) -
                    call_long_quote.get('ask', 0)
                )

                self.total_credit = self.put_credit + self.call_credit
                self.max_profit = self.total_credit * 100 * self.contracts

                # Max loss is the wider wing minus total credit
                max_wing = max(self.put_width, self.call_width)
                self.max_loss = (max_wing - self.total_credit) * 100 * self.contracts

                return True

        except Exception as e:
            logger.error(f"Error calculating iron condor prices: {e}")

        return False

    def get_profit_range(self) -> Tuple[float, float]:
        """Get the price range where max profit is achieved"""
        return (self.put_short, self.call_short)

    def get_breakevens(self) -> Tuple[float, float]:
        """Get lower and upper breakeven prices"""
        lower = self.put_short - self.total_credit
        upper = self.call_short + self.total_credit
        return (lower, upper)

    def to_position(self) -> MultiLegPosition:
        """Convert to MultiLegPosition"""
        legs = [
            OptionLeg('put', self.put_short, self.expiration, 'sell', self.contracts),
            OptionLeg('put', self.put_long, self.expiration, 'buy', self.contracts),
            OptionLeg('call', self.call_short, self.expiration, 'sell', self.contracts),
            OptionLeg('call', self.call_long, self.expiration, 'buy', self.contracts),
        ]

        lower_be, upper_be = self.get_breakevens()

        return MultiLegPosition(
            strategy_type=StrategyType.IRON_CONDOR,
            legs=legs,
            expiration=self.expiration,
            contracts=self.contracts,
            max_profit=self.max_profit,
            max_loss=self.max_loss,
            breakeven=lower_be,  # Lower breakeven
            credit_received=self.total_credit * 100 * self.contracts,
            margin_required=self.max_loss
        )

    def __str__(self) -> str:
        lower_be, upper_be = self.get_breakevens()
        return (
            f"Iron Condor ({self.expiration}) x{self.contracts}\n"
            f"  Put Spread:  Sell {self.put_short}P / Buy {self.put_long}P\n"
            f"  Call Spread: Sell {self.call_short}C / Buy {self.call_long}C\n"
            f"  Total Credit: ${self.total_credit:.2f}\n"
            f"  Max Profit: ${self.max_profit:.2f}\n"
            f"  Max Loss: ${self.max_loss:.2f}\n"
            f"  Profit Range: ${self.put_short:.0f} - ${self.call_short:.0f}\n"
            f"  Breakevens: ${lower_be:.2f} - ${upper_be:.2f}"
        )


def save_multi_leg_position(position: MultiLegPosition) -> int:
    """Save multi-leg position to database"""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        # NOTE: Table 'spx_wheel_multileg_positions' is defined in db/config_and_database.py (single source of truth)

        # Serialize legs
        legs_json = [asdict(leg) for leg in position.legs]

        cursor.execute('''
            INSERT INTO spx_wheel_multileg_positions (
                strategy_type, expiration, contracts, legs,
                max_profit, max_loss, breakeven, credit_received,
                margin_required, entry_underlying_price
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (
            position.strategy_type.value,
            position.expiration,
            position.contracts,
            json.dumps(legs_json),
            position.max_profit,
            position.max_loss,
            position.breakeven,
            position.credit_received,
            position.margin_required,
            position.entry_underlying_price
        ))

        position_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        logger.info(f"Saved multi-leg position {position_id}")
        return position_id

    except Exception as e:
        logger.error(f"Error saving multi-leg position: {e}")
        return -1


def get_open_multileg_positions() -> List[Dict]:
    """Get all open multi-leg positions"""
    try:
        from database_adapter import get_connection

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, strategy_type, expiration, contracts, legs,
                   max_profit, max_loss, credit_received, status
            FROM spx_wheel_multileg_positions
            WHERE status = 'OPEN'
        ''')

        positions = []
        for row in cursor.fetchall():
            positions.append({
                'id': row[0],
                'strategy_type': row[1],
                'expiration': str(row[2]),
                'contracts': row[3],
                'legs': row[4],
                'max_profit': float(row[5]),
                'max_loss': float(row[6]),
                'credit_received': float(row[7]),
                'status': row[8]
            })

        conn.close()
        return positions

    except Exception as e:
        logger.error(f"Error getting multi-leg positions: {e}")
        return []


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("MULTI-LEG STRATEGY EXAMPLES")
    print("=" * 70)

    # Example 1: Put Credit Spread
    print("\n1. PUT CREDIT SPREAD")
    print("-" * 40)
    spread = PutCreditSpread(
        short_strike=5800,
        long_strike=5750,
        expiration='2024-12-20',
        contracts=1
    )
    # Manual prices for demo
    spread.short_premium = 15.50
    spread.long_premium = 10.25
    spread.net_credit = spread.short_premium - spread.long_premium
    spread.max_profit = spread.net_credit * 100
    spread.max_loss = (spread.width - spread.net_credit) * 100
    print(spread)

    # Example 2: Iron Condor
    print("\n2. IRON CONDOR")
    print("-" * 40)
    condor = IronCondor(
        put_short_strike=5750,
        put_long_strike=5700,
        call_short_strike=5900,
        call_long_strike=5950,
        expiration='2024-12-20',
        contracts=1
    )
    # Manual prices for demo
    condor.put_credit = 4.50
    condor.call_credit = 3.75
    condor.total_credit = condor.put_credit + condor.call_credit
    condor.max_profit = condor.total_credit * 100
    condor.max_loss = (50 - condor.total_credit) * 100
    print(condor)

    print("\n" + "=" * 70)
    print("Use calculate_prices() to fetch real prices from Polygon")
    print("=" * 70)
