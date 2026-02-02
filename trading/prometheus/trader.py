"""
PROMETHEUS Trader - Main Orchestrator

Coordinates all box spread operations: signal generation, execution,
position management, and capital tracking.
"""

import logging
from datetime import datetime, date, timedelta, time
from typing import Optional, Dict, Any, List

from .models import (
    BoxSpreadPosition,
    BoxSpreadSignal,
    PrometheusConfig,
    BorrowingCostAnalysis,
    CapitalDeployment,
    DailyBriefing,
    PositionStatus,
    BoxSpreadStatus,
    TradingMode,
    # IC Trading Models
    PrometheusICSignal,
    PrometheusICPosition,
    PrometheusICConfig,
    ICPositionStatus,
)
from .db import PrometheusDatabase
from .signals import BoxSpreadSignalGenerator, PrometheusICSignalGenerator
from .executor import BoxSpreadExecutor, PrometheusICExecutor
from .tracing import get_tracer

logger = logging.getLogger(__name__)

# Get global tracer instance for metrics
tracer = get_tracer()

# Import IC bot database adapters for real returns integration
try:
    from database_adapter import get_connection
    IC_DB_AVAILABLE = True
except ImportError:
    IC_DB_AVAILABLE = False
    logger.warning("Database adapter not available - IC returns will be estimated")

# Central timezone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")


class PrometheusTrader:
    """
    Main orchestrator for the PROMETHEUS box spread system.

    EDUCATIONAL NOTE - How PROMETHEUS Works:
    ========================================
    PROMETHEUS runs on a different schedule than other bots because
    box spreads are longer-term positions:

    1. DAILY: Check existing positions, update returns, check rolls
    2. WEEKLY: Analyze rates, generate new signals if favorable
    3. ON-DEMAND: Execute signals, close positions

    Unlike ARES/TITAN which trade every 5 minutes, PROMETHEUS
    focuses on strategic capital deployment over weeks/months.

    The trader coordinates:
    - Signal generation (finding good box spread opportunities)
    - Order execution (placing the 4-leg trades)
    - Position management (tracking returns, rolling positions)
    - Capital tracking (monitoring IC bot performance)
    """

    def __init__(self, config: Optional[PrometheusConfig] = None):
        self.db = PrometheusDatabase(bot_name="PROMETHEUS")
        self.config = config or self.db.load_config()
        self.signals = BoxSpreadSignalGenerator(self.config)
        self.executor = BoxSpreadExecutor(self.config, self.db)

    # ========== Main Trading Operations ==========

    def run_daily_cycle(self) -> Dict[str, Any]:
        """
        Run the daily cycle for PROMETHEUS.

        This is called once per day to:
        1. Update all position DTEs
        2. Calculate accrued costs
        3. Check for roll decisions
        4. Record equity snapshot
        5. Generate daily briefing
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"PROMETHEUS daily cycle starting at {now}")

        result = {
            'cycle_time': now,
            'positions_updated': 0,
            'roll_candidates': [],
            'daily_briefing': None,
            'errors': [],
        }

        try:
            # Get all open positions
            positions = self.db.get_open_positions()

            for position in positions:
                try:
                    # Update DTE
                    exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
                    position.current_dte = (exp_date - date.today()).days

                    # Update cost accrual
                    days_held = (date.today() - position.open_time.date()).days
                    position.cost_accrued_to_date = position.daily_cost * days_held

                    # Fetch IC bot returns (would integrate with actual bots)
                    ic_returns = self._fetch_ic_returns(position)
                    position.returns_from_ares = ic_returns.get('ares', 0)
                    position.returns_from_titan = ic_returns.get('titan', 0)
                    position.returns_from_pegasus = ic_returns.get('pegasus', 0)
                    position.total_ic_returns = sum(ic_returns.values())
                    position.net_profit = position.total_ic_returns - position.cost_accrued_to_date

                    # Check for roll
                    roll_decision = self.executor.check_roll_decision(position)
                    if roll_decision['should_roll']:
                        result['roll_candidates'].append({
                            'position_id': position.position_id,
                            'current_dte': roll_decision['current_dte'],
                            'reasoning': roll_decision['reasoning'],
                        })

                    # Save updated position
                    self.db.save_position(position)
                    result['positions_updated'] += 1

                except Exception as e:
                    logger.error(f"Error updating position {position.position_id}: {e}")
                    result['errors'].append(str(e))

            # Record equity snapshot
            self.db.record_equity_snapshot()

            # Generate daily briefing
            result['daily_briefing'] = self.generate_daily_briefing()

            logger.info(f"PROMETHEUS daily cycle complete: {result['positions_updated']} positions updated")

        except Exception as e:
            logger.error(f"PROMETHEUS daily cycle error: {e}")
            result['errors'].append(str(e))

        return result

    def run_signal_scan(self) -> Dict[str, Any]:
        """
        Scan for new box spread opportunities.

        This is typically run weekly or on-demand to find
        favorable box spread opportunities.
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"PROMETHEUS signal scan starting at {now}")

        result = {
            'scan_time': now,
            'signal': None,
            'rate_analysis': None,
            'should_trade': False,
            'reason': '',
        }

        try:
            # Check if we should look for new positions
            if not self._should_scan_for_signals():
                result['reason'] = self._get_skip_reason()
                return result

            # Analyze current rates
            rate_analysis = self.signals.analyze_current_rates()
            result['rate_analysis'] = rate_analysis.to_dict()
            self.db.save_rate_analysis(rate_analysis)

            if not rate_analysis.is_favorable:
                result['reason'] = f"Rates not favorable: {rate_analysis.recommendation}"
                return result

            # Generate signal
            signal = self.signals.generate_signal()
            if not signal:
                result['reason'] = "No valid signal generated"
                return result

            result['signal'] = signal.to_dict()

            if signal.is_valid:
                result['should_trade'] = True
                result['reason'] = "Valid signal generated - ready to execute"
            else:
                result['reason'] = f"Signal invalid: {signal.skip_reason}"

            # Log the signal
            self.db.log_signal(signal, was_executed=False)

        except Exception as e:
            logger.error(f"PROMETHEUS signal scan error: {e}")
            result['reason'] = f"Error: {str(e)}"

        return result

    def execute_signal(self, signal: BoxSpreadSignal) -> Dict[str, Any]:
        """Execute a box spread signal"""
        result = {
            'execution_time': datetime.now(CENTRAL_TZ),
            'position': None,
            'success': False,
            'error': None,
        }

        try:
            position = self.executor.execute_signal(signal)
            if position:
                result['position'] = position.to_dict()
                result['success'] = True

                # Update signal as executed
                self.db.log_signal(
                    signal,
                    was_executed=True,
                    executed_position_id=position.position_id
                )
            else:
                result['error'] = "Execution failed"

        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            result['error'] = str(e)

        return result

    # ========== Position Management ==========

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive PROMETHEUS status"""
        positions = self.db.get_open_positions()
        performance = self.db.get_performance_summary()
        config = self.config.to_dict()

        # Calculate totals
        total_borrowed = sum(p.total_credit_received for p in positions)
        total_deployed = sum(p.total_cash_deployed for p in positions)
        total_returns = sum(p.total_ic_returns for p in positions)
        total_costs = sum(p.cost_accrued_to_date for p in positions)
        net_unrealized = total_returns - total_costs

        # Determine system status
        system_status = self._determine_system_status(positions)

        return {
            'system_status': system_status.value,
            'mode': self.config.mode.value,
            'ticker': self.config.ticker,
            'capital': self.config.capital,
            'open_positions': len(positions),
            'total_borrowed': total_borrowed,
            'total_deployed': total_deployed,
            'total_ic_returns': total_returns,
            'total_borrowing_costs': total_costs,
            'net_unrealized_pnl': net_unrealized,
            'performance': performance,
            'config': config,
            'in_trading_window': self._in_trading_window(),
            'last_updated': datetime.now(CENTRAL_TZ).isoformat(),
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions with current metrics"""
        positions = self.db.get_open_positions()
        return [p.to_dict() for p in positions]

    def close_position(
        self,
        position_id: str,
        reason: str = "manual"
    ) -> Dict[str, Any]:
        """Close a specific position"""
        position = self.db.get_position(position_id)
        if not position:
            return {'success': False, 'error': 'Position not found'}

        success = self.executor.close_position(position, reason)
        return {
            'success': success,
            'position_id': position_id,
            'close_reason': reason,
        }

    def roll_position(
        self,
        position_id: str,
        target_expiration: str = None
    ) -> Dict[str, Any]:
        """Roll a position to a new expiration"""
        position = self.db.get_position(position_id)
        if not position:
            return {'success': False, 'error': 'Position not found'}

        # Close current position
        close_result = self.executor.close_position(position, "rolled")
        if not close_result:
            return {'success': False, 'error': 'Failed to close current position'}

        # Generate new signal for the roll
        signal = self.signals.generate_signal()
        if not signal or not signal.is_valid:
            return {
                'success': False,
                'error': 'Could not generate valid signal for roll',
                'original_closed': True,
            }

        # Execute new position
        new_position = self.executor.execute_signal(signal)
        if not new_position:
            return {
                'success': False,
                'error': 'Failed to open new position',
                'original_closed': True,
            }

        return {
            'success': True,
            'old_position_id': position_id,
            'new_position_id': new_position.position_id,
            'new_expiration': signal.expiration,
        }

    # ========== Analytics & Reporting ==========

    def generate_daily_briefing(self) -> Dict[str, Any]:
        """Generate comprehensive daily briefing"""
        now = datetime.now(CENTRAL_TZ)
        positions = self.db.get_open_positions()
        performance = self.db.get_performance_summary()

        # Calculate metrics
        total_borrowed = sum(p.total_credit_received for p in positions)
        total_deployed = sum(p.total_cash_deployed for p in positions)
        total_returns = sum(p.total_ic_returns for p in positions)
        total_costs = sum(p.cost_accrued_to_date for p in positions)
        net_profit = total_returns - total_costs

        # Margin calculations
        total_margin = sum(p.current_margin_used for p in positions)
        margin_capacity = self.config.capital * (self.config.max_margin_pct / 100)
        margin_remaining = margin_capacity - total_margin

        # Risk metrics
        assignment_risks = [p for p in positions if p.early_assignment_risk in ['HIGH', 'MEDIUM']]
        nearest_expiry = min([
            (datetime.strptime(p.expiration, '%Y-%m-%d').date() - date.today()).days
            for p in positions
        ]) if positions else 999

        # Rate analysis
        rate_analysis = self.signals.analyze_current_rates()
        yesterday_rate = self._get_yesterday_rate()
        rate_change = rate_analysis.box_implied_rate - yesterday_rate if yesterday_rate else 0

        # Generate recommendations and warnings
        recommendations = []
        warnings = []

        if nearest_expiry < 30:
            recommendations.append(f"Consider rolling position expiring in {nearest_expiry} days")

        if margin_remaining < margin_capacity * 0.2:
            warnings.append("Margin utilization high - consider reducing exposure")

        if assignment_risks:
            warnings.append(f"{len(assignment_risks)} position(s) with elevated assignment risk")

        if rate_analysis.is_favorable and len(positions) < self.config.max_positions:
            recommendations.append("Rates are favorable - consider adding new position")

        # Educational tip
        tips = [
            "Box spreads work best on European-style options (SPX) to avoid early assignment.",
            "The implied rate should be compared to your broker's margin rate to assess value.",
            "Longer-dated box spreads typically have better (lower) implied rates.",
            "Always maintain margin buffer for unexpected market moves.",
            "Monitor IC bot performance - your profit depends on them outperforming box cost.",
            "Rolling positions early avoids gamma risk near expiration.",
            "Consider the bid-ask spread when calculating true borrowing cost.",
        ]
        daily_tip = tips[date.today().timetuple().tm_yday % len(tips)]

        # Average rate
        avg_rate = sum(p.implied_annual_rate for p in positions) / len(positions) if positions else 0

        briefing = DailyBriefing(
            briefing_date=date.today(),
            briefing_time=now,
            system_status=self._determine_system_status(positions),
            total_open_positions=len(positions),
            total_borrowed_amount=total_borrowed,
            total_cash_deployed=total_deployed,
            total_margin_used=total_margin,
            margin_remaining=margin_remaining,
            total_borrowing_cost_to_date=total_costs,
            average_borrowing_rate=avg_rate,
            comparison_to_margin_rate=self.config.capital * (rate_analysis.broker_margin_rate / 100) - total_costs,
            total_ic_returns_to_date=total_returns,
            net_profit_to_date=net_profit,
            roi_on_strategy=net_profit / total_borrowed * 100 if total_borrowed > 0 else 0,
            highest_assignment_risk_position=assignment_risks[0].position_id if assignment_risks else "",
            days_until_nearest_expiration=nearest_expiry,
            current_box_rate=rate_analysis.box_implied_rate,
            rate_vs_yesterday=rate_change,
            rate_trend_7d=rate_analysis.rate_trend,
            recommended_actions=recommendations,
            warnings=warnings,
            daily_tip=daily_tip,
        )

        # Persist daily briefing to database for historical analysis
        briefing_dict = briefing.to_dict()
        self.db.save_daily_briefing(briefing_dict)

        return briefing_dict

    def get_rate_analysis(self) -> Dict[str, Any]:
        """Get current rate analysis"""
        analysis = self.signals.analyze_current_rates()
        return analysis.to_dict()

    def get_capital_flow(self) -> Dict[str, Any]:
        """Get comprehensive capital flow analysis"""
        positions = self.db.get_open_positions()
        deployments = self.db.get_active_deployments()

        # Total by bot
        ares_total = sum(p.cash_deployed_to_ares for p in positions)
        titan_total = sum(p.cash_deployed_to_titan for p in positions)
        pegasus_total = sum(p.cash_deployed_to_pegasus for p in positions)
        reserve_total = sum(p.cash_held_in_reserve for p in positions)

        # Returns by bot
        ares_returns = sum(p.returns_from_ares for p in positions)
        titan_returns = sum(p.returns_from_titan for p in positions)
        pegasus_returns = sum(p.returns_from_pegasus for p in positions)

        return {
            'total_cash_generated': sum(p.total_credit_received for p in positions),
            'deployment_summary': {
                'ares': {
                    'deployed': ares_total,
                    'returns': ares_returns,
                    'roi': ares_returns / ares_total * 100 if ares_total > 0 else 0,
                },
                'titan': {
                    'deployed': titan_total,
                    'returns': titan_returns,
                    'roi': titan_returns / titan_total * 100 if titan_total > 0 else 0,
                },
                'pegasus': {
                    'deployed': pegasus_total,
                    'returns': pegasus_returns,
                    'roi': pegasus_returns / pegasus_total * 100 if pegasus_total > 0 else 0,
                },
                'reserve': {
                    'amount': reserve_total,
                },
            },
            'total_deployed': ares_total + titan_total + pegasus_total,
            'total_returns': ares_returns + titan_returns + pegasus_returns,
            'active_deployments': len(deployments),
        }

    def get_education_content(self, topic: str = "overview") -> Dict[str, Any]:
        """Get educational content about box spreads"""
        content = {
            'overview': {
                'title': 'Box Spread Synthetic Borrowing - Overview',
                'content': """
# What is a Box Spread?

A box spread is an options strategy that combines a bull call spread with a bear
put spread at the same strikes. This creates a position with a **guaranteed payoff**
at expiration, regardless of where the underlying price ends up.

## Why "Synthetic Borrowing"?

When you SELL a box spread:
- You receive cash TODAY (the discounted present value)
- You "owe" a fixed amount at EXPIRATION (the strike width)
- The difference is your borrowing cost

This is mathematically identical to taking out a loan!

## The PROMETHEUS Strategy

PROMETHEUS uses box spreads to:
1. Generate cash at low interest rates (often below margin rates)
2. Deploy that cash to IC bots (ARES, TITAN, PEGASUS)
3. Earn premium from Iron Condors
4. Profit = IC Returns - Box Spread Cost

## Key Advantages

- Lower borrowing cost than margin
- No margin calls (fixed obligation at expiration)
- Tax-efficient on 1256 contracts (SPX)
- Leverages existing IC strategy expertise
""",
            },
            'mechanics': {
                'title': 'Box Spread Mechanics',
                'content': """
# How Box Spreads Work

## The 4 Legs

A box spread consists of 4 option legs:

1. **Buy Call at Lower Strike** (long call)
2. **Sell Call at Upper Strike** (short call)
3. **Buy Put at Upper Strike** (long put)
4. **Sell Put at Lower Strike** (short put)

## Example: 5900/5950 SPX Box

- Buy SPX 5900 Call
- Sell SPX 5950 Call
- Buy SPX 5950 Put
- Sell SPX 5900 Put

At expiration, this ALWAYS equals $50 (the strike width).

## Why is it Guaranteed?

No matter where SPX ends up:
- If SPX > 5950: Calls are worth $50, puts are worthless → Box = $50
- If SPX < 5900: Puts are worth $50, calls are worthless → Box = $50
- If 5900 < SPX < 5950: Combined value still = $50

## The Borrowing Math

If the box trades at $49.50 (present value):
- You sell for $49.50 × 100 = $4,950 per contract
- At expiration, you owe $50 × 100 = $5,000
- Borrowing cost = $50 per contract

Implied rate = ($50 / $4,950) × (365 / DTE) × 100%
""",
            },
            'risks': {
                'title': 'Box Spread Risks',
                'content': """
# Understanding Box Spread Risks

## 1. Early Assignment Risk (American-Style Options)

**The Biggest Risk!**

American-style options (SPY) can be exercised any time. If one leg is
assigned early, your box spread breaks apart and you face:
- Potential losses from the disrupted position
- Need to manage unexpected stock position
- Possible dividend-related assignments

**Solution**: Use European-style options (SPX, XSP) which can ONLY be
exercised at expiration. This eliminates assignment risk entirely.

## 2. Execution Risk

Box spreads require executing 4 legs. Risks include:
- Legging risk if not executed as a combo
- Wider bid-ask spreads on illiquid strikes
- Fill prices worse than expected

**Solution**: Use combo orders, trade liquid strikes, use limit orders.

## 3. Margin Risk

Some brokers require significant margin for box spreads.
- Could tie up more capital than expected
- Margin calls if account equity drops

**Solution**: Understand your broker's requirements before trading.

## 4. IC Performance Risk

Your profit depends on IC bots outperforming the box spread cost.
If IC bots underperform, you could lose money on the strategy.

**Solution**: Only use proven IC strategies, maintain reserves.
""",
            },
            'comparison': {
                'title': 'Box Spreads vs Alternatives',
                'content': """
# Comparing Borrowing Methods

## Box Spread Synthetic Borrowing

| Aspect | Box Spread | Margin Loan | Personal Loan |
|--------|------------|-------------|---------------|
| Typical Rate | 4-5% | 7-9% | 8-12% |
| Collateral | Option margin | Securities | Varies |
| Margin Calls | No | Yes | No |
| Tax Treatment | 1256 (60/40) | None | Interest deductible? |
| Complexity | High | Low | Low |
| Max Term | Up to 1 year | Indefinite | Fixed term |

## When Box Spreads Make Sense

✅ Good candidates:
- Large position sizes ($100K+)
- Access to SPX options
- Strong IC bot performance
- Understanding of options

❌ Not ideal for:
- Small accounts
- No SPX access
- Risk-averse investors
- Options beginners

## Break-Even Analysis

For box spreads to be profitable:
- IC monthly returns must exceed box monthly cost
- Box cost at 4.5% annual = 0.375% monthly
- IC returns of 2-4% monthly = significant profit potential
""",
            },
        }

        return content.get(topic, content['overview'])

    # ========== Internal Helpers ==========

    def _should_scan_for_signals(self) -> bool:
        """Check if we should look for new positions"""
        positions = self.db.get_open_positions()

        # Check max positions
        if len(positions) >= self.config.max_positions:
            return False

        # Check if in trading window
        if not self._in_trading_window():
            return False

        return True

    def _get_skip_reason(self) -> str:
        """Get reason for skipping signal scan"""
        positions = self.db.get_open_positions()

        if len(positions) >= self.config.max_positions:
            return f"At max positions ({self.config.max_positions})"

        if not self._in_trading_window():
            return "Outside trading window"

        return "Unknown"

    def _in_trading_window(self) -> bool:
        """Check if within trading hours"""
        now = datetime.now(CENTRAL_TZ)
        current_time = now.time()

        start = datetime.strptime(self.config.entry_start, '%H:%M').time()
        end = datetime.strptime(self.config.entry_end, '%H:%M').time()

        return start <= current_time <= end

    def _determine_system_status(
        self,
        positions: List[BoxSpreadPosition]
    ) -> BoxSpreadStatus:
        """Determine overall system status"""
        if not positions:
            return BoxSpreadStatus.ACTIVE

        # Check for assignment risk
        high_risk = any(p.early_assignment_risk == 'HIGH' for p in positions)
        if high_risk:
            return BoxSpreadStatus.ASSIGNMENT_ALERT

        # Check margin
        total_margin = sum(p.current_margin_used for p in positions)
        margin_capacity = self.config.capital * (self.config.max_margin_pct / 100)
        if total_margin > margin_capacity * 0.9:
            return BoxSpreadStatus.MARGIN_WARNING

        return BoxSpreadStatus.ACTIVE

    def _fetch_ic_returns(
        self,
        position: BoxSpreadPosition
    ) -> Dict[str, float]:
        """
        Fetch REAL returns from IC bots for the deployed capital.

        LEGACY NOTE: This method is for the OLD capital deployment model where
        PROMETHEUS deployed borrowed capital to ARES/TITAN/PEGASUS.
        The new standalone model uses PrometheusICTrader instead.

        Queries ARES, TITAN, and PEGASUS closed_trades tables to get
        actual realized P&L since this PROMETHEUS position was opened.

        Returns are proportionally attributed based on each bot's share
        of total IC capital at time of deployment.

        Fallback: Uses 100000.0 as default starting capital for each bot
        if their config tables don't have starting_capital set.
        """
        returns = {
            'ares': 0.0,
            'titan': 0.0,
            'pegasus': 0.0,
        }

        if not IC_DB_AVAILABLE:
            logger.warning("IC database not available - using estimated returns")
            return self._estimate_ic_returns(position)

        try:
            conn = get_connection()
            cur = conn.cursor()

            # Get the start date for this position
            start_date = position.open_time.strftime('%Y-%m-%d')

            # Query ARES returns
            if position.cash_deployed_to_ares > 0:
                try:
                    cur.execute("""
                        SELECT COALESCE(SUM(realized_pnl), 0)
                        FROM ares_positions
                        WHERE status IN ('closed', 'expired')
                        AND close_time >= %s::timestamp
                    """, (start_date,))
                    result = cur.fetchone()
                    total_ares_pnl = float(result[0]) if result and result[0] else 0.0

                    # Get ARES total capital to calculate attribution
                    cur.execute("""
                        SELECT value FROM ares_config WHERE key = 'starting_capital'
                    """)
                    ares_cap_result = cur.fetchone()
                    ares_capital = float(ares_cap_result[0]) if ares_cap_result else 100000.0

                    # Attribute returns proportionally
                    if ares_capital > 0:
                        attribution_pct = position.cash_deployed_to_ares / ares_capital
                        returns['ares'] = total_ares_pnl * min(attribution_pct, 1.0)

                    logger.debug(f"ARES returns: ${returns['ares']:.2f} (total: ${total_ares_pnl:.2f}, attribution: {attribution_pct*100:.1f}%)")
                except Exception as e:
                    logger.warning(f"Failed to fetch ARES returns: {e}")

            # Query TITAN returns
            if position.cash_deployed_to_titan > 0:
                try:
                    cur.execute("""
                        SELECT COALESCE(SUM(realized_pnl), 0)
                        FROM titan_positions
                        WHERE status IN ('closed', 'expired')
                        AND close_time >= %s::timestamp
                    """, (start_date,))
                    result = cur.fetchone()
                    total_titan_pnl = float(result[0]) if result and result[0] else 0.0

                    cur.execute("""
                        SELECT value FROM titan_config WHERE key = 'starting_capital'
                    """)
                    titan_cap_result = cur.fetchone()
                    titan_capital = float(titan_cap_result[0]) if titan_cap_result else 100000.0

                    if titan_capital > 0:
                        attribution_pct = position.cash_deployed_to_titan / titan_capital
                        returns['titan'] = total_titan_pnl * min(attribution_pct, 1.0)

                    logger.debug(f"TITAN returns: ${returns['titan']:.2f}")
                except Exception as e:
                    logger.warning(f"Failed to fetch TITAN returns: {e}")

            # Query PEGASUS returns
            if position.cash_deployed_to_pegasus > 0:
                try:
                    cur.execute("""
                        SELECT COALESCE(SUM(realized_pnl), 0)
                        FROM pegasus_positions
                        WHERE status IN ('closed', 'expired')
                        AND close_time >= %s::timestamp
                    """, (start_date,))
                    result = cur.fetchone()
                    total_pegasus_pnl = float(result[0]) if result and result[0] else 0.0

                    cur.execute("""
                        SELECT value FROM pegasus_config WHERE key = 'starting_capital'
                    """)
                    pegasus_cap_result = cur.fetchone()
                    pegasus_capital = float(pegasus_cap_result[0]) if pegasus_cap_result else 100000.0

                    if pegasus_capital > 0:
                        attribution_pct = position.cash_deployed_to_pegasus / pegasus_capital
                        returns['pegasus'] = total_pegasus_pnl * min(attribution_pct, 1.0)

                    logger.debug(f"PEGASUS returns: ${returns['pegasus']:.2f}")
                except Exception as e:
                    logger.warning(f"Failed to fetch PEGASUS returns: {e}")

            cur.close()
            conn.close()

            logger.info(f"IC returns for position {position.position_id}: "
                       f"ARES=${returns['ares']:.2f}, TITAN=${returns['titan']:.2f}, PEGASUS=${returns['pegasus']:.2f}")

        except Exception as e:
            logger.error(f"Failed to fetch IC returns: {e}")
            return self._estimate_ic_returns(position)

        return returns

    def _estimate_ic_returns(
        self,
        position: BoxSpreadPosition
    ) -> Dict[str, float]:
        """
        Fallback: Estimate IC returns when database unavailable.

        LEGACY NOTE: This method is for the OLD capital deployment model.
        The new standalone model uses PrometheusICTrader which tracks
        its own IC positions in prometheus_ic_positions table.

        Uses conservative 2.5% monthly return estimate as fallback.
        This is intentionally conservative to avoid overstating returns.
        """
        days_held = (date.today() - position.open_time.date()).days
        monthly_return_rate = 0.025  # 2.5% monthly estimate
        daily_rate = monthly_return_rate / 30

        return {
            'ares': position.cash_deployed_to_ares * daily_rate * days_held,
            'titan': position.cash_deployed_to_titan * daily_rate * days_held,
            'pegasus': position.cash_deployed_to_pegasus * daily_rate * days_held,
        }

    def _get_yesterday_rate(self) -> Optional[float]:
        """Get yesterday's box spread rate for comparison"""
        history = self.db.get_rate_history(days=2)
        if len(history) >= 2:
            return float(history[1].get('box_implied_rate', 0))
        return None


# Convenience function for scheduler
def run_prometheus_daily_cycle():
    """Run the daily PROMETHEUS cycle - called by scheduler"""
    trader = PrometheusTrader()
    return trader.run_daily_cycle()


def run_prometheus_signal_scan():
    """Run PROMETHEUS signal scan - called weekly or on-demand"""
    trader = PrometheusTrader()
    return trader.run_signal_scan()


# ==============================================================================
# PROMETHEUS IC TRADER
# ==============================================================================
# Orchestrates the Iron Condor trading side of PROMETHEUS.
# This is the "returns engine" that generates premium income from borrowed capital.
# ==============================================================================

class PrometheusICTrader:
    """
    Main orchestrator for PROMETHEUS Iron Condor trading.

    EDUCATIONAL NOTE - IC Trading in PROMETHEUS:
    ============================================
    While the PrometheusTrader handles long-term box spread borrowing,
    the PrometheusICTrader handles daily IC trading that generates returns
    to exceed the borrowing costs.

    Schedule:
    - Run every 5-15 minutes during market hours
    - Check exit conditions on all open positions
    - Generate new signals when capital is available
    - Execute approved signals

    Key Differences from Other IC Bots (TITAN, PEGASUS):
    - Uses borrowed capital from box spreads
    - All returns are tracked against specific box positions
    - Conservative sizing to protect borrowed capital
    - Requires Oracle approval before trading
    """

    def __init__(self, config: Optional[PrometheusICConfig] = None):
        self.db = PrometheusDatabase(bot_name="PROMETHEUS_IC")

        # Load and validate config
        self.config = config or self.db.load_ic_config()
        if not self.config:
            logger.warning("IC config is None, using defaults")
            self.config = PrometheusICConfig()

        # Validate critical config fields
        if not hasattr(self.config, 'enabled'):
            logger.error("IC config missing 'enabled' field, defaulting to True")
            self.config.enabled = True
        if not hasattr(self.config, 'starting_capital') or self.config.starting_capital <= 0:
            logger.warning(f"IC config invalid starting_capital, using 500000")
            self.config.starting_capital = 500000.0
        if not hasattr(self.config, 'mode'):
            logger.warning("IC config missing 'mode', defaulting to PAPER")
            self.config.mode = TradingMode.PAPER

        # Initialize components with validated config
        try:
            self.signal_gen = PrometheusICSignalGenerator(self.config)
            self.executor = PrometheusICExecutor(self.config, self.db)
        except Exception as e:
            logger.error(f"Failed to initialize IC trader components: {e}")
            raise RuntimeError(f"PrometheusICTrader initialization failed: {e}")

    def run_trading_cycle(self) -> Dict[str, Any]:
        """
        Run a complete IC trading cycle.

        This is the main entry point, called every 5-15 minutes.
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"PROMETHEUS IC trading cycle starting at {now}")

        result = {
            'cycle_time': now,
            'positions_checked': 0,
            'positions_closed': 0,
            'new_position': None,
            'signal_generated': False,
            'cooldown_active': False,
            'errors': [],
        }

        try:
            # Check if enabled
            if not self.config.enabled:
                result['skip_reason'] = "IC trading disabled"
                return result

            # Check if in trading window
            if not self._in_trading_window():
                result['skip_reason'] = "Outside trading window"
                return result

            # Step 1: Check exit conditions on all open positions
            exit_results = self._check_all_exits()
            result['positions_checked'] = exit_results['checked']
            result['positions_closed'] = exit_results['closed']

            # Step 2: Check for new trading opportunity
            if self._can_open_new_position():
                signal_result = self._generate_and_execute_signal()
                result['signal_generated'] = signal_result.get('signal_generated', False)
                result['new_position'] = signal_result.get('new_position')
                if signal_result.get('error'):
                    result['errors'].append(signal_result['error'])
            else:
                result['cooldown_active'] = True
                result['skip_reason'] = self._get_skip_reason()

            # Step 3: Record equity snapshot (per STANDARDS.md)
            try:
                self.db.record_ic_equity_snapshot()
            except Exception as e:
                logger.warning(f"Failed to record IC equity snapshot: {e}")
                result['errors'].append(f"Equity snapshot failed: {e}")

            logger.info(f"PROMETHEUS IC cycle complete: {result['positions_closed']} closed, new={bool(result['new_position'])}")

        except Exception as e:
            logger.error(f"PROMETHEUS IC trading cycle error: {e}")
            result['errors'].append(str(e))

        return result

    def _check_all_exits(self) -> Dict[str, Any]:
        """Check exit conditions on all open IC positions"""
        positions = self.db.get_open_ic_positions()
        checked = 0
        closed = 0

        for position in positions:
            try:
                checked += 1
                should_close, reason = self.executor.check_exit_conditions(position)

                if should_close:
                    success = self.executor.close_position(position.position_id, reason)
                    if success:
                        closed += 1
                        logger.info(f"Closed IC position {position.position_id}: {reason}")

            except Exception as e:
                logger.error(f"Error checking position {position.position_id}: {e}")

        return {'checked': checked, 'closed': closed}

    def _can_open_new_position(self) -> bool:
        """Check if we can open a new IC position"""
        # Check max positions
        open_positions = self.db.get_open_ic_positions()
        if len(open_positions) >= self.config.max_positions:
            return False

        # Check daily limit (0 = unlimited)
        if self.config.max_trades_per_day > 0:
            daily_trades = self.db.get_daily_ic_trades_count()
            if daily_trades >= self.config.max_trades_per_day:
                return False

        # Check cooldown
        if self._in_cooldown():
            return False

        # Check available capital
        available = self._get_available_capital()
        if available < self.config.min_capital_per_trade:
            return False

        return True

    def _get_skip_reason(self) -> str:
        """Get reason for not opening new position"""
        open_positions = self.db.get_open_ic_positions()
        if len(open_positions) >= self.config.max_positions:
            return f"At max positions ({self.config.max_positions})"

        # Check daily limit (0 = unlimited)
        if self.config.max_trades_per_day > 0:
            daily_trades = self.db.get_daily_ic_trades_count()
            if daily_trades >= self.config.max_trades_per_day:
                return f"Daily trade limit reached ({self.config.max_trades_per_day})"

        if self._in_cooldown():
            return "In cooldown period after recent trade"

        available = self._get_available_capital()
        if available < self.config.min_capital_per_trade:
            return f"Insufficient capital (${available:,.2f} < ${self.config.min_capital_per_trade:,.2f})"

        return "Unknown"

    def _in_cooldown(self) -> bool:
        """
        Check if in cooldown period after last trade.

        Uses different cooldown periods for wins vs losses:
        - After a win: shorter cooldown (config.cooldown_after_win_minutes)
        - After a loss: longer cooldown (config.cooldown_after_loss_minutes)
        - Default: config.cooldown_minutes_after_trade
        """
        try:
            last_trade_time = self.db.get_last_ic_trade_time()
            if not last_trade_time:
                return False

            # Determine cooldown based on last closed trade result
            last_result = self.db.get_last_ic_trade_result()
            if last_result and last_result.get('close_time'):
                # Use win/loss specific cooldown
                if last_result.get('was_winner'):
                    cooldown_minutes = self.config.cooldown_after_win_minutes
                else:
                    cooldown_minutes = self.config.cooldown_after_loss_minutes
            else:
                # Fallback to generic cooldown
                cooldown_minutes = self.config.cooldown_minutes_after_trade

            cooldown_end = last_trade_time + timedelta(minutes=cooldown_minutes)

            # Handle timezone comparison - make both aware or both naive
            now = datetime.now(CENTRAL_TZ)
            if cooldown_end.tzinfo is None:
                # last_trade_time was naive, make it aware
                cooldown_end = cooldown_end.replace(tzinfo=CENTRAL_TZ)

            return now < cooldown_end
        except Exception as e:
            logger.warning(f"Error checking cooldown: {e}")
            return False  # If we can't check, assume not in cooldown

    def _get_available_capital(self) -> float:
        """
        Get capital available for IC trading from box spread positions.

        IC trading uses borrowed capital from box spreads.
        In PAPER mode, auto-creates a paper box spread if none exists.
        """
        # Ensure we have a box spread position (creates paper one if needed)
        self._ensure_paper_box_spread()

        # Get capital from box spread positions
        box_positions = self.db.get_open_positions()  # Box spreads
        if not box_positions:
            return 0.0

        # Calculate total capital available for IC trading
        total_available = 0.0
        for box in box_positions:
            # Use the total cash deployed minus any already allocated to open IC positions
            total_available += box.total_cash_deployed

        # Subtract capital currently in use by open IC positions
        ic_positions = self.db.get_open_ic_positions()
        for ic in ic_positions:
            total_available -= ic.total_credit_received  # Margin tied up

        return max(0, total_available)

    def _ensure_paper_box_spread(self) -> None:
        """
        In PAPER mode, create a synthetic box spread position if none exists.
        This provides the borrowed capital for IC trading.
        """
        if self.config.mode != TradingMode.PAPER:
            return

        box_positions = self.db.get_open_positions()
        if box_positions:
            return  # Already have positions

        # Create a synthetic paper box spread with $500K borrowed
        logger.info("PAPER MODE: Creating synthetic box spread position for IC trading capital")
        try:
            from .models import BoxSpreadPosition, PositionStatus

            now = datetime.now(CENTRAL_TZ)
            expiration_date = now + timedelta(days=90)
            expiration_str = expiration_date.strftime('%Y-%m-%d')

            # $500K notional: 100 contracts * $50 strike width * 100 multiplier
            contracts = 100
            strike_width = 50.0
            lower_strike = 5800.0
            upper_strike = lower_strike + strike_width
            entry_credit = 49.50  # Slight discount = borrowing cost
            theoretical_value = strike_width  # $50 at expiration
            total_credit = entry_credit * contracts * 100  # $495,000
            total_owed = theoretical_value * contracts * 100  # $500,000
            borrowing_cost = total_owed - total_credit  # $5,000
            implied_rate = (borrowing_cost / total_owed) * (365.0 / 90) * 100  # ~4%

            synthetic_box = BoxSpreadPosition(
                # Position identification
                position_id=f"PAPER_BOX_{now.strftime('%Y%m%d_%H%M%S')}",
                ticker="SPX",

                # Leg details
                lower_strike=lower_strike,
                upper_strike=upper_strike,
                strike_width=strike_width,
                expiration=expiration_str,
                dte_at_entry=90,
                current_dte=90,

                # Leg symbols (synthetic for paper)
                call_long_symbol=f"SPX{expiration_str.replace('-', '')}C{int(lower_strike)}",
                call_short_symbol=f"SPX{expiration_str.replace('-', '')}C{int(upper_strike)}",
                put_long_symbol=f"SPX{expiration_str.replace('-', '')}P{int(upper_strike)}",
                put_short_symbol=f"SPX{expiration_str.replace('-', '')}P{int(lower_strike)}",

                # Order IDs (synthetic for paper)
                call_spread_order_id="PAPER_CALL_ORDER",
                put_spread_order_id="PAPER_PUT_ORDER",

                # Execution prices
                contracts=contracts,
                entry_credit=entry_credit,
                total_credit_received=total_credit,
                theoretical_value=theoretical_value,
                total_owed_at_expiration=total_owed,

                # Borrowing cost tracking
                borrowing_cost=borrowing_cost,
                implied_annual_rate=implied_rate,
                daily_cost=borrowing_cost / 90,
                cost_accrued_to_date=0.0,

                # Comparison benchmarks
                fed_funds_at_entry=4.38,
                margin_rate_at_entry=8.50,
                savings_vs_margin=(8.50 - implied_rate) * total_owed / 100,

                # Capital deployment - ALL goes to PROMETHEUS IC trading
                cash_deployed_to_ares=0.0,
                cash_deployed_to_titan=0.0,
                cash_deployed_to_pegasus=0.0,
                cash_held_in_reserve=50000.0,  # 10% reserve
                total_cash_deployed=total_credit,  # $495K available

                # Returns tracking (starts at 0)
                returns_from_ares=0.0,
                returns_from_titan=0.0,
                returns_from_pegasus=0.0,
                total_ic_returns=0.0,
                net_profit=0.0,

                # Market context
                spot_at_entry=5825.0,
                vix_at_entry=15.0,

                # Risk monitoring
                early_assignment_risk="LOW",
                current_margin_used=100000.0,
                margin_cushion=150000.0,

                # Status
                status=PositionStatus.OPEN,
                open_time=now,

                # Educational
                position_explanation="PAPER MODE: Synthetic box spread providing $500K capital for IC trading",
                daily_briefing="Paper trading position - no real capital at risk"
            )
            self.db.save_position(synthetic_box)
            logger.info(f"Created paper box spread: {synthetic_box.position_id} with ${total_credit:,.0f} capital")
        except Exception as e:
            logger.error(f"Failed to create paper box spread: {e}", exc_info=True)

    def _get_source_box_position(self) -> Optional[str]:
        """
        Get the box position ID to link new IC trades to.

        IC trades are always linked to a box spread position (the source of capital).
        In PAPER mode, auto-creates a paper box spread if none exists.
        """
        # Ensure we have a box spread position (creates paper one if needed)
        self._ensure_paper_box_spread()

        box_positions = self.db.get_open_positions()
        if not box_positions:
            return None

        # Use the most recently opened box position
        sorted_boxes = sorted(box_positions, key=lambda p: p.open_time, reverse=True)
        return sorted_boxes[0].position_id

    def _generate_and_execute_signal(self) -> Dict[str, Any]:
        """Generate an IC signal and execute if approved"""
        result = {
            'signal_generated': False,
            'new_position': None,
            'error': None,
        }

        # Get source box position
        source_box_id = self._get_source_box_position()
        if not source_box_id:
            result['error'] = "No open box spread position to fund IC trade"
            return result

        # Get available capital
        available_capital = self._get_available_capital()

        # Generate signal
        signal = self.signal_gen.generate_signal(
            source_box_position_id=source_box_id,
            available_capital=available_capital,
        )

        if not signal:
            result['error'] = "Failed to generate signal"
            return result

        result['signal_generated'] = True

        # Log the signal regardless of validity
        self.db.log_ic_signal(signal, was_executed=False)

        if not signal.is_valid:
            result['error'] = f"Signal invalid: {signal.skip_reason}"
            return result

        # Execute the signal
        position = self.executor.execute_signal(signal)
        if position:
            result['new_position'] = position.position_id

            # Update the box position's IC returns tracking
            self.db.log_action(
                action="IC_TRADE_EXECUTED",
                message=f"IC trade {position.position_id} linked to box {source_box_id}",
                level="INFO",
                details={
                    'ic_position_id': position.position_id,
                    'source_box_id': source_box_id,
                    'credit_received': position.total_credit_received,
                    'oracle_confidence': signal.oracle_confidence,
                },
                position_id=source_box_id,
            )
        else:
            result['error'] = "Failed to execute signal"

        return result

    def _in_trading_window(self) -> bool:
        """Check if within IC trading hours"""
        now = datetime.now(CENTRAL_TZ)

        # Check if weekend
        if now.weekday() >= 5:
            return False

        current_time = now.time()
        start = datetime.strptime(self.config.entry_start, '%H:%M').time()
        end = datetime.strptime(self.config.entry_end, '%H:%M').time()

        return start <= current_time <= end

    # ========== Status & Monitoring ==========

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive IC trading status"""
        ic_positions = self.db.get_open_ic_positions()
        ic_performance = self.db.get_ic_performance()

        total_unrealized = sum(p.unrealized_pnl for p in ic_positions)
        total_credit = sum(p.total_credit_received for p in ic_positions)

        # Determine trading_active status and reason
        in_window = self._in_trading_window()
        in_cooldown = self._in_cooldown()
        can_trade = self._can_open_new_position()
        available_capital = self._get_available_capital()

        # trading_active = enabled AND in trading window (can actually execute trades)
        trading_active = self.config.enabled and in_window

        # Determine inactive reason for clarity
        inactive_reason = None
        if not self.config.enabled:
            inactive_reason = "IC trading is disabled in configuration"
        elif not in_window:
            inactive_reason = "Outside trading hours (8:30 AM - 3:00 PM CT)"
        elif in_cooldown:
            inactive_reason = "In cooldown period after recent trade"
        elif available_capital <= 0:
            inactive_reason = "No capital available from box spreads"
        elif not can_trade:
            inactive_reason = self._get_skip_reason()

        return {
            'enabled': self.config.enabled,
            'trading_active': trading_active,
            'inactive_reason': inactive_reason,
            'mode': self.config.mode.value,
            'ticker': self.config.ticker,
            'open_positions': len(ic_positions),
            'total_credit_outstanding': total_credit,
            'total_unrealized_pnl': total_unrealized,
            'performance': ic_performance,
            'in_trading_window': in_window,
            'in_cooldown': in_cooldown,
            'available_capital': available_capital,
            'can_trade': can_trade,
            'daily_trades': self.db.get_daily_ic_trades_count(),
            'max_daily_trades': 'unlimited' if self.config.max_trades_per_day == 0 else self.config.max_trades_per_day,
            'last_updated': datetime.now(CENTRAL_TZ).isoformat(),
        }

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open IC positions"""
        positions = self.db.get_open_ic_positions()
        return [self._position_to_dict(p) for p in positions]

    def _position_to_dict(self, position: PrometheusICPosition) -> Dict[str, Any]:
        """Convert IC position to dictionary with full details for reconciliation"""
        return {
            'position_id': position.position_id,
            'source_box_position_id': position.source_box_position_id,
            'ticker': position.ticker,
            # Full strike details for reconciliation display
            'put_short_strike': position.put_short_strike,
            'put_long_strike': position.put_long_strike,
            'call_short_strike': position.call_short_strike,
            'call_long_strike': position.call_long_strike,
            # Formatted spreads for display
            'put_spread': f"{position.put_long_strike}/{position.put_short_strike}",
            'call_spread': f"{position.call_short_strike}/{position.call_long_strike}",
            'spread_width': position.spread_width,
            'expiration': position.expiration,
            'dte': position.current_dte,
            'contracts': position.contracts,
            # Credit and P&L
            'entry_credit': position.entry_credit,
            'total_credit_received': position.total_credit_received,
            'max_loss': position.max_loss,
            'current_value': position.current_value,
            'unrealized_pnl': position.unrealized_pnl,
            'pnl_pct': (position.unrealized_pnl / position.total_credit_received * 100) if position.total_credit_received else 0,
            # Status and timing
            'status': position.status.value,
            'open_time': position.open_time.isoformat() if position.open_time else None,
            # Oracle details - FULL reasoning for transparency
            'oracle_confidence': position.oracle_confidence_at_entry,
            'oracle_reasoning': position.oracle_reasoning,
            # Market context at entry
            'spot_at_entry': position.spot_at_entry,
            'vix_at_entry': position.vix_at_entry,
            'gamma_regime_at_entry': position.gamma_regime_at_entry,
            # Risk management rules
            'stop_loss_pct': position.stop_loss_pct,
            'profit_target_pct': position.profit_target_pct,
        }

    def close_position(self, position_id: str, reason: str = "manual") -> Dict[str, Any]:
        """Manually close an IC position"""
        success = self.executor.close_position(position_id, reason)
        return {
            'success': success,
            'position_id': position_id,
            'close_reason': reason,
        }

    def get_equity_curve(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get IC trading equity curve"""
        return self.db.get_ic_equity_curve(limit)

    def get_closed_trades(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get closed IC trade history"""
        return self.db.get_ic_closed_trades(limit)


# Convenience functions for scheduler
def run_prometheus_ic_cycle():
    """Run the PROMETHEUS IC trading cycle - called every 5-15 minutes"""
    trader = PrometheusICTrader()
    return trader.run_trading_cycle()


def run_prometheus_ic_mtm_update():
    """Update mark-to-market for all open IC positions and record equity snapshot"""
    db = PrometheusDatabase(bot_name="PROMETHEUS_IC")
    config = db.load_ic_config()
    executor = PrometheusICExecutor(config, db)

    positions = db.get_open_ic_positions()
    updated = 0

    for position in positions:
        try:
            executor.update_position_mtm(position.position_id)
            updated += 1
        except Exception as e:
            logger.error(f"MTM update failed for {position.position_id}: {e}")

    # CRITICAL: Record equity snapshot after MTM update to preserve intraday state
    # This ensures unrealized P&L is tracked for the intraday equity curve
    snapshot_saved = False
    if updated > 0:
        try:
            snapshot_saved = db.record_ic_equity_snapshot()
            if snapshot_saved:
                logger.info(f"IC equity snapshot recorded with {updated} positions updated")
        except Exception as e:
            logger.error(f"Failed to record IC equity snapshot: {e}")

    return {'updated': updated, 'total': len(positions), 'snapshot_saved': snapshot_saved}
