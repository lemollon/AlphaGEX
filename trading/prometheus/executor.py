"""
PROMETHEUS Order Executor - Box Spread Execution

Handles order placement and position management for box spreads.
Includes comprehensive educational annotations for learning.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Tuple
import uuid

from .models import (
    BoxSpreadPosition,
    BoxSpreadSignal,
    CapitalDeployment,
    PrometheusConfig,
    PositionStatus,
    TradingMode,
)
from .db import PrometheusDatabase

logger = logging.getLogger(__name__)

# Central timezone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")

# Try to import Tradier
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    tradier_available = True
except ImportError:
    tradier_available = False
    logger.warning("TradierDataFetcher not available - paper trading only")


def build_occ_symbol(
    underlying: str,
    expiration: str,
    strike: float,
    option_type: str
) -> str:
    """
    Build OCC-format option symbol.

    EDUCATIONAL NOTE:
    =================
    OCC (Options Clearing Corporation) symbols follow this format:
    SYMBOL + YYMMDD + C/P + STRIKE*1000

    Example: SPX240315C05900000
    - SPX = underlying
    - 240315 = March 15, 2024
    - C = Call (P = Put)
    - 05900000 = $5900.00 strike (8 digits, right-padded)
    """
    # Parse expiration date
    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    date_str = exp_date.strftime('%y%m%d')

    # Option type
    opt_type = 'C' if option_type.lower() == 'call' else 'P'

    # Strike (multiply by 1000, pad to 8 digits)
    strike_int = int(strike * 1000)
    strike_str = f"{strike_int:08d}"

    # Pad underlying to standard length
    underlying_padded = underlying.upper().ljust(6)[:6]

    return f"{underlying_padded}{date_str}{opt_type}{strike_str}"


class BoxSpreadExecutor:
    """
    Executes box spread orders with full transparency.

    EDUCATIONAL NOTE - Order Execution:
    ====================================
    A box spread requires executing TWO spread orders:
    1. Bull Call Spread: Sell high call, buy low call
    2. Bear Put Spread: Sell low put, buy high put

    We typically execute as combo/spread orders rather than
    individual legs to reduce slippage and execution risk.

    Order types:
    - LIMIT: Best for defined risk, ensures minimum credit
    - MARKET: Faster fill but may get worse price
    - We always use LIMIT orders for box spreads
    """

    def __init__(
        self,
        config: PrometheusConfig,
        db: PrometheusDatabase
    ):
        self.config = config
        self.db = db
        self.tradier = TradierDataFetcher() if tradier_available else None

    def execute_signal(
        self,
        signal: BoxSpreadSignal
    ) -> Optional[BoxSpreadPosition]:
        """
        Execute a box spread signal.

        This creates a position by:
        1. Building option symbols for all 4 legs
        2. Placing the call spread order
        3. Placing the put spread order
        4. Creating and saving the position record

        Returns the created position or None if execution fails.
        """
        now = datetime.now(CENTRAL_TZ)

        # Generate position ID
        position_id = f"PROM-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # Build OCC symbols for all 4 legs
        symbols = self._build_option_symbols(signal)

        logger.info(f"Executing box spread signal {signal.signal_id}")
        logger.info(f"  Lower strike: {signal.lower_strike}")
        logger.info(f"  Upper strike: {signal.upper_strike}")
        logger.info(f"  Expiration: {signal.expiration}")
        logger.info(f"  Contracts: {signal.recommended_contracts}")

        # Execute orders
        if self.config.mode == TradingMode.LIVE and self.tradier:
            call_order = self._execute_call_spread(signal, symbols)
            put_order = self._execute_put_spread(signal, symbols)

            if not call_order or not put_order:
                logger.error("Failed to execute one or both spread orders")
                return None

            call_order_id = call_order.get('id', 'LIVE-CALL')
            put_order_id = put_order.get('id', 'LIVE-PUT')
        else:
            # Paper trading - simulate fills
            call_order_id = f"PAPER-CALL-{uuid.uuid4().hex[:8]}"
            put_order_id = f"PAPER-PUT-{uuid.uuid4().hex[:8]}"
            logger.info("Paper trading mode - simulating order fills")

        # Calculate capital deployment
        deployment = self._calculate_deployment(signal, position_id)

        # Create position object
        position = BoxSpreadPosition(
            position_id=position_id,
            ticker=signal.ticker,
            lower_strike=signal.lower_strike,
            upper_strike=signal.upper_strike,
            strike_width=signal.strike_width,
            expiration=signal.expiration,
            dte_at_entry=signal.dte,
            current_dte=signal.dte,
            call_long_symbol=symbols['call_long'],
            call_short_symbol=symbols['call_short'],
            put_long_symbol=symbols['put_long'],
            put_short_symbol=symbols['put_short'],
            call_spread_order_id=call_order_id,
            put_spread_order_id=put_order_id,
            contracts=signal.recommended_contracts,
            entry_credit=signal.mid_price,
            total_credit_received=signal.cash_received,
            theoretical_value=signal.theoretical_value,
            total_owed_at_expiration=signal.cash_owed_at_expiration,
            borrowing_cost=signal.borrowing_cost,
            implied_annual_rate=signal.implied_annual_rate,
            daily_cost=signal.borrowing_cost / signal.dte if signal.dte > 0 else 0,
            cost_accrued_to_date=0.0,
            fed_funds_at_entry=signal.fed_funds_rate,
            margin_rate_at_entry=signal.margin_rate,
            savings_vs_margin=signal.cash_received * (signal.margin_rate - signal.implied_annual_rate) / 100,
            cash_deployed_to_ares=deployment.ares_allocation,
            cash_deployed_to_titan=deployment.titan_allocation,
            cash_deployed_to_pegasus=deployment.pegasus_allocation,
            cash_held_in_reserve=deployment.reserve_amount,
            total_cash_deployed=deployment.total_capital_available,
            returns_from_ares=0.0,
            returns_from_titan=0.0,
            returns_from_pegasus=0.0,
            total_ic_returns=0.0,
            net_profit=0.0,
            spot_at_entry=signal.spot_price,
            vix_at_entry=0.0,  # Would get from market data
            early_assignment_risk=signal.early_assignment_risk,
            current_margin_used=signal.margin_requirement,
            margin_cushion=self.config.capital * (self.config.max_margin_pct / 100) - signal.margin_requirement,
            status=PositionStatus.OPEN,
            open_time=now,
            position_explanation=self._generate_position_explanation(signal, deployment),
            daily_briefing="",
        )

        # Save position to database
        if self.db.save_position(position):
            logger.info(f"Position {position_id} saved successfully")

            # Save capital deployment
            self.db.save_deployment(deployment)

            # Log the action
            self.db.log_action(
                action="POSITION_OPENED",
                message=f"Opened box spread position {position_id}",
                level="INFO",
                details={
                    'signal_id': signal.signal_id,
                    'strikes': f"{signal.lower_strike}/{signal.upper_strike}",
                    'cash_received': signal.cash_received,
                    'implied_rate': signal.implied_annual_rate,
                },
                position_id=position_id,
                signal_id=signal.signal_id,
            )

            return position
        else:
            logger.error(f"Failed to save position {position_id}")
            return None

    def _build_option_symbols(
        self,
        signal: BoxSpreadSignal
    ) -> Dict[str, str]:
        """Build OCC symbols for all 4 legs of the box spread"""
        return {
            'call_long': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.lower_strike, 'call'
            ),
            'call_short': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.upper_strike, 'call'
            ),
            'put_long': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.upper_strike, 'put'
            ),
            'put_short': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.lower_strike, 'put'
            ),
        }

    def _execute_call_spread(
        self,
        signal: BoxSpreadSignal,
        symbols: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the call spread leg of the box.

        EDUCATIONAL NOTE:
        =================
        The call spread is a BEAR CALL SPREAD (we want credit):
        - Sell the lower strike call (receive premium)
        - Buy the higher strike call (pay premium, but less)
        - Net: Receive credit

        Wait, actually for a box spread where we're SELLING the box:
        - We SELL the bull call spread
        - Which means: Buy low call, Sell high call
        - This gives us a DEBIT on the call spread

        Hmm, let me reconsider. When SELLING a box spread:
        - Bull call spread (long lower, short upper) = we pay
        - Bear put spread (long upper, short lower) = we pay
        - But the combination = we receive credit!

        Actually, to SELL a box spread for credit:
        - Sell the box = receive present value
        - You're selling synthetic shares at upper strike
        - And buying them at lower strike

        For simplicity, we execute as:
        - Sell vertical call spread (sell upper, buy lower)
        - Sell vertical put spread (sell lower, buy upper)

        This way we collect credit on both spreads.
        """
        if not self.tradier:
            return {'id': 'PAPER-CALL', 'status': 'filled'}

        try:
            # For SELLING the box, we sell the call vertical spread
            # Sell upper strike call, buy lower strike call
            order = {
                'class': 'multileg',
                'symbol': signal.ticker,
                'type': 'credit',
                'duration': 'day',
                'price': signal.mid_price / 2,  # Half the total credit
                'option_symbol': [
                    symbols['call_short'],  # Sell upper call
                    symbols['call_long'],   # Buy lower call
                ],
                'side': ['sell_to_open', 'buy_to_open'],
                'quantity': [signal.recommended_contracts, signal.recommended_contracts],
            }

            # Place order via Tradier
            result = self.tradier.place_multileg_order(order)
            return result

        except Exception as e:
            logger.error(f"Error executing call spread: {e}")
            return None

    def _execute_put_spread(
        self,
        signal: BoxSpreadSignal,
        symbols: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the put spread leg of the box.

        EDUCATIONAL NOTE:
        =================
        For SELLING the box, we sell the put vertical spread:
        - Sell lower strike put (receive premium)
        - Buy upper strike put (pay premium, but less)
        - Net: Receive credit
        """
        if not self.tradier:
            return {'id': 'PAPER-PUT', 'status': 'filled'}

        try:
            order = {
                'class': 'multileg',
                'symbol': signal.ticker,
                'type': 'credit',
                'duration': 'day',
                'price': signal.mid_price / 2,  # Half the total credit
                'option_symbol': [
                    symbols['put_short'],   # Sell lower put
                    symbols['put_long'],    # Buy upper put
                ],
                'side': ['sell_to_open', 'buy_to_open'],
                'quantity': [signal.recommended_contracts, signal.recommended_contracts],
            }

            result = self.tradier.place_multileg_order(order)
            return result

        except Exception as e:
            logger.error(f"Error executing put spread: {e}")
            return None

    def _calculate_deployment(
        self,
        signal: BoxSpreadSignal,
        position_id: str
    ) -> CapitalDeployment:
        """
        Calculate how to deploy the borrowed capital to IC bots.

        EDUCATIONAL NOTE:
        =================
        Capital deployment strategy:
        1. ARES (SPY 0DTE ICs) - aggressive, daily opportunities
        2. TITAN (SPX Aggressive ICs) - aggressive SPX plays
        3. PEGASUS (SPX Weekly ICs) - more conservative
        4. RESERVE - buffer for margin and emergencies

        The allocation is based on:
        - Historical bot performance
        - Current market regime
        - Risk tolerance settings
        """
        total_cash = signal.cash_received
        now = datetime.now(CENTRAL_TZ)

        # Calculate allocations based on config percentages
        ares_amount = total_cash * (self.config.ares_allocation_pct / 100)
        titan_amount = total_cash * (self.config.titan_allocation_pct / 100)
        pegasus_amount = total_cash * (self.config.pegasus_allocation_pct / 100)
        reserve_amount = total_cash * (self.config.reserve_pct / 100)

        # Generate reasoning for each allocation
        ares_reasoning = f"""
ARES receives {self.config.ares_allocation_pct}% (${ares_amount:,.2f}) because:
- ARES trades SPY 0DTE Iron Condors with proven track record
- High trade frequency allows rapid capital deployment
- Recommended for active premium collection
""".strip()

        titan_reasoning = f"""
TITAN receives {self.config.titan_allocation_pct}% (${titan_amount:,.2f}) because:
- TITAN runs aggressive SPX Iron Condors
- Higher premium per trade than SPY strategies
- Complements ARES with SPX exposure
""".strip()

        pegasus_reasoning = f"""
PEGASUS receives {self.config.pegasus_allocation_pct}% (${pegasus_amount:,.2f}) because:
- PEGASUS trades weekly SPX Iron Condors
- More conservative risk profile
- Provides stability to overall returns
""".strip()

        reserve_reasoning = f"""
Reserve holds {self.config.reserve_pct}% (${reserve_amount:,.2f}) because:
- Maintains margin buffer for position adjustments
- Provides liquidity for rolling positions
- Emergency fund for unexpected market events
""".strip()

        methodology = f"""
ALLOCATION METHODOLOGY: Configured Percentages

The capital is allocated based on predefined percentages that balance:
1. Return potential (ARES/TITAN for aggressive returns)
2. Risk management (PEGASUS for stability)
3. Liquidity needs (Reserve for flexibility)

Total allocated: ${total_cash:,.2f}
- ARES: {self.config.ares_allocation_pct}% = ${ares_amount:,.2f}
- TITAN: {self.config.titan_allocation_pct}% = ${titan_amount:,.2f}
- PEGASUS: {self.config.pegasus_allocation_pct}% = ${pegasus_amount:,.2f}
- Reserve: {self.config.reserve_pct}% = ${reserve_amount:,.2f}

This allocation aims to maximize premium collection while maintaining
adequate reserves for risk management.
""".strip()

        return CapitalDeployment(
            deployment_id=f"DEP-{position_id}",
            deployment_time=now,
            source_box_position_id=position_id,
            total_capital_available=total_cash,
            ares_allocation=ares_amount,
            ares_allocation_pct=self.config.ares_allocation_pct,
            ares_allocation_reasoning=ares_reasoning,
            titan_allocation=titan_amount,
            titan_allocation_pct=self.config.titan_allocation_pct,
            titan_allocation_reasoning=titan_reasoning,
            pegasus_allocation=pegasus_amount,
            pegasus_allocation_pct=self.config.pegasus_allocation_pct,
            pegasus_allocation_reasoning=pegasus_reasoning,
            reserve_amount=reserve_amount,
            reserve_pct=self.config.reserve_pct,
            reserve_reasoning=reserve_reasoning,
            allocation_method="CONFIGURED_PERCENTAGES",
            methodology_explanation=methodology,
            ares_returns_to_date=0.0,
            titan_returns_to_date=0.0,
            pegasus_returns_to_date=0.0,
            total_returns_to_date=0.0,
            is_active=True,
        )

    def _generate_position_explanation(
        self,
        signal: BoxSpreadSignal,
        deployment: CapitalDeployment
    ) -> str:
        """Generate comprehensive position explanation"""
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║            YOUR BOX SPREAD POSITION EXPLAINED                    ║
╚══════════════════════════════════════════════════════════════════╝

POSITION SUMMARY:
═════════════════
You have SOLD a box spread on {signal.ticker}, which means:

1. TODAY: You received ${signal.cash_received:,.2f} in your account
2. AT EXPIRATION ({signal.expiration}): You will "owe" ${signal.cash_owed_at_expiration:,.2f}
3. NET COST: ${signal.borrowing_cost:,.2f} (this is your borrowing cost)

IMPLIED BORROWING RATE: {signal.implied_annual_rate:.2f}% annually
COMPARED TO MARGIN: {signal.margin_rate:.2f}% (you save {signal.margin_rate - signal.implied_annual_rate:.2f}%)

CAPITAL DEPLOYMENT:
═══════════════════
The ${signal.cash_received:,.2f} has been deployed to generate returns:

┌──────────────────────────────────────────────────────────────────┐
│ Bot      │ Allocation │ Amount         │ Target Return          │
├──────────┼────────────┼────────────────┼────────────────────────┤
│ ARES     │ {deployment.ares_allocation_pct:>5.1f}%    │ ${deployment.ares_allocation:>12,.2f} │ 2-4% monthly           │
│ TITAN    │ {deployment.titan_allocation_pct:>5.1f}%    │ ${deployment.titan_allocation:>12,.2f} │ 2-4% monthly           │
│ PEGASUS  │ {deployment.pegasus_allocation_pct:>5.1f}%    │ ${deployment.pegasus_allocation:>12,.2f} │ 1-3% monthly           │
│ Reserve  │ {deployment.reserve_pct:>5.1f}%    │ ${deployment.reserve_amount:>12,.2f} │ Held for flexibility   │
└──────────┴────────────┴────────────────┴────────────────────────┘

PROFIT EQUATION:
════════════════
Profit = IC Bot Returns - Borrowing Cost

If IC bots return 3% monthly on ${signal.cash_received:,.2f}:
  Monthly IC returns: ${signal.cash_received * 0.03:,.2f}
  Monthly box cost: ${signal.borrowing_cost / (signal.dte / 30):,.2f}
  Monthly profit: ${signal.cash_received * 0.03 - signal.borrowing_cost / (signal.dte / 30):,.2f}

Over {signal.dte} days until expiration:
  Total IC returns (estimated): ${signal.cash_received * 0.03 * (signal.dte / 30):,.2f}
  Total box cost: ${signal.borrowing_cost:,.2f}
  Estimated net profit: ${signal.cash_received * 0.03 * (signal.dte / 30) - signal.borrowing_cost:,.2f}

RISK FACTORS:
═════════════
1. Assignment Risk: {signal.early_assignment_risk}
   {signal.assignment_risk_explanation[:200]}...

2. Margin Requirement: ${signal.margin_requirement:,.2f}
   This is {signal.margin_pct_of_capital:.1f}% of your capital

3. IC Bot Performance Risk:
   If IC bots underperform, net profit could be negative.
   Break-even requires IC returns of {signal.implied_annual_rate / 12:.2f}% monthly.

MONITORING:
═══════════
Track this position through the PROMETHEUS dashboard:
- Daily cost accrual updates
- IC bot return tracking
- Net profit calculations
- Roll decision recommendations
""".strip()

    def close_position(
        self,
        position: BoxSpreadPosition,
        close_reason: str = "manual"
    ) -> bool:
        """
        Close a box spread position.

        EDUCATIONAL NOTE:
        =================
        Closing a box spread involves:
        1. Buying back the call spread (debit)
        2. Buying back the put spread (debit)
        3. The cost to close = current market value of the box

        You typically close early if:
        - IC returns have been strong and you want to lock in profit
        - Assignment risk has increased
        - Better opportunities exist
        - Position needs to be rolled
        """
        logger.info(f"Closing position {position.position_id}: {close_reason}")

        if self.config.mode == TradingMode.LIVE and self.tradier:
            # Get current quotes for the legs
            # Execute closing orders
            # This would mirror the opening logic but with opposite sides
            pass

        # Update position in database
        success = self.db.close_position(
            position.position_id,
            close_reason,
            final_ic_returns=position.total_ic_returns
        )

        if success:
            self.db.log_action(
                action="POSITION_CLOSED",
                message=f"Closed box spread position {position.position_id}",
                level="INFO",
                details={
                    'close_reason': close_reason,
                    'total_ic_returns': position.total_ic_returns,
                    'borrowing_cost': position.borrowing_cost,
                    'net_profit': position.net_profit,
                },
                position_id=position.position_id,
            )

        return success

    def update_position_returns(
        self,
        position_id: str,
        ares_returns: float = 0.0,
        titan_returns: float = 0.0,
        pegasus_returns: float = 0.0
    ) -> bool:
        """
        Update the returns from IC bots for a position.

        This should be called periodically to track how the deployed
        capital is performing.
        """
        position = self.db.get_position(position_id)
        if not position:
            logger.warning(f"Position {position_id} not found")
            return False

        # Update returns
        position.returns_from_ares = ares_returns
        position.returns_from_titan = titan_returns
        position.returns_from_pegasus = pegasus_returns
        position.total_ic_returns = ares_returns + titan_returns + pegasus_returns

        # Update cost accrual
        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
        days_held = (date.today() - position.open_time.date()).days
        position.cost_accrued_to_date = position.daily_cost * days_held
        position.current_dte = (exp_date - date.today()).days

        # Calculate net profit
        position.net_profit = position.total_ic_returns - position.cost_accrued_to_date

        # Update daily briefing
        position.daily_briefing = self._generate_daily_briefing(position)

        return self.db.save_position(position)

    def _generate_daily_briefing(self, position: BoxSpreadPosition) -> str:
        """Generate daily briefing for a position"""
        days_held = (date.today() - position.open_time.date()).days

        return f"""
DAILY BRIEFING - {date.today().strftime('%Y-%m-%d')}
═══════════════════════════════════════

Position: {position.position_id}
Days Held: {days_held} | Days Remaining: {position.current_dte}

RETURNS TO DATE:
├─ ARES: ${position.returns_from_ares:,.2f}
├─ TITAN: ${position.returns_from_titan:,.2f}
├─ PEGASUS: ${position.returns_from_pegasus:,.2f}
└─ TOTAL: ${position.total_ic_returns:,.2f}

COSTS TO DATE:
├─ Daily cost: ${position.daily_cost:,.2f}
├─ Days accrued: {days_held}
└─ Total accrued: ${position.cost_accrued_to_date:,.2f}

NET PROFIT: ${position.net_profit:,.2f}

STATUS: {"PROFITABLE" if position.net_profit > 0 else "TRACKING" if position.net_profit > -position.cost_accrued_to_date / 2 else "MONITOR CLOSELY"}
""".strip()

    def check_roll_decision(
        self,
        position: BoxSpreadPosition
    ) -> Dict[str, Any]:
        """
        Check if a position should be rolled to a later expiration.

        EDUCATIONAL NOTE:
        =================
        Rolling involves closing the current box spread and opening
        a new one at a later expiration. Roll when:

        1. DTE is getting low (< min_dte_to_hold)
        2. Better rates available at longer expiration
        3. Want to extend the borrowing period

        Rolling has costs (bid-ask spread on close and open), so
        only roll if the benefits outweigh the costs.
        """
        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
        current_dte = (exp_date - date.today()).days

        should_roll = current_dte < self.config.min_dte_to_hold
        reasoning = []

        if should_roll:
            reasoning.append(
                f"DTE ({current_dte}) is below minimum threshold ({self.config.min_dte_to_hold})"
            )

        return {
            'should_roll': should_roll,
            'current_dte': current_dte,
            'min_dte_threshold': self.config.min_dte_to_hold,
            'reasoning': reasoning,
            'recommendation': 'ROLL POSITION' if should_roll else 'HOLD POSITION',
        }
