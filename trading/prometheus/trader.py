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
)
from .db import PrometheusDatabase
from .signals import BoxSpreadSignalGenerator
from .executor import BoxSpreadExecutor

logger = logging.getLogger(__name__)

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
            comparison_to_margin_rate=self.config.capital * 0.085 - total_costs,  # 8.5% margin
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

        return briefing.to_dict()

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

        Queries ARES, TITAN, and PEGASUS closed_trades tables to get
        actual realized P&L since this PROMETHEUS position was opened.

        Returns are proportionally attributed based on each bot's share
        of total IC capital at time of deployment.
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

        Uses conservative 2.5% monthly return estimate.
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
