"""
JUBILEE Trader - Main Orchestrator

Coordinates all box spread operations: signal generation, execution,
position management, and capital tracking.
"""

import logging
from datetime import datetime, date, timedelta, time
from typing import Optional, Dict, Any, List

from .models import (
    BoxSpreadPosition,
    BoxSpreadSignal,
    JubileeConfig,
    BorrowingCostAnalysis,
    CapitalDeployment,
    DailyBriefing,
    PositionStatus,
    BoxSpreadStatus,
    TradingMode,
    # IC Trading Models
    JubileeICSignal,
    JubileeICPosition,
    JubileeICConfig,
    ICPositionStatus,
)
from .db import JubileeDatabase
from .signals import BoxSpreadSignalGenerator, JubileeICSignalGenerator
from .executor import BoxSpreadExecutor, JubileeICExecutor
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

# Thompson Sampling for position sizing (match SAMSON)
try:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerMixin = None

class JubileeTrader:
    """
    Main orchestrator for the JUBILEE box spread system.

    EDUCATIONAL NOTE - How JUBILEE Works:
    ========================================
    JUBILEE runs on a different schedule than other bots because
    box spreads are longer-term positions:

    1. DAILY: Check existing positions, update returns, check rolls
    2. WEEKLY: Analyze rates, generate new signals if favorable
    3. ON-DEMAND: Execute signals, close positions

    Unlike FORTRESS/SAMSON which trade every 5 minutes, JUBILEE
    focuses on strategic capital deployment over weeks/months.

    The trader coordinates:
    - Signal generation (finding good box spread opportunities)
    - Order execution (placing the 4-leg trades)
    - Position management (tracking returns, rolling positions)
    - Capital tracking (monitoring IC bot performance)
    """

    def __init__(self, config: Optional[JubileeConfig] = None):
        self.db = JubileeDatabase(bot_name="JUBILEE")
        self.config = config or self.db.load_config()
        self.signals = BoxSpreadSignalGenerator(self.config)
        self.executor = BoxSpreadExecutor(self.config, self.db)

    # ========== Main Trading Operations ==========

    def run_daily_cycle(self) -> Dict[str, Any]:
        """
        Run the daily cycle for JUBILEE.

        This is called once per day to:
        1. Update all position DTEs
        2. Calculate accrued costs
        3. Check for roll decisions
        4. Record equity snapshot
        5. Generate daily briefing
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"JUBILEE daily cycle starting at {now}")

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

                    # Fetch JUBILEE IC returns from jubilee_ic_closed_trades.
                    # The standalone IC trader tracks its own P&L — the legacy
                    # _fetch_ic_returns (FORTRESS/SAMSON/ANCHOR) is no longer used.
                    try:
                        ic_perf = self.db.get_ic_performance()
                        closed_stats = ic_perf.get('closed_trades', {})
                        open_stats = ic_perf.get('open_positions', {})
                        realized = closed_stats.get('total_pnl', 0) or 0
                        unrealized = open_stats.get('total_unrealized', 0) or 0
                        position.total_ic_returns = realized + unrealized
                    except Exception as ic_err:
                        logger.warning(f"Failed to fetch JUBILEE IC returns: {ic_err}")
                        position.total_ic_returns = 0.0
                    position.net_profit = position.total_ic_returns - position.cost_accrued_to_date

                    # Check for roll
                    roll_decision = self.executor.check_roll_decision(position)
                    if roll_decision['should_roll']:
                        # PAPER MODE: Auto-extend expiration instead of rolling.
                        # Paper box spreads are fictional - rolling them through
                        # the real signal/execution pipeline is the root cause of
                        # the recurring $0 capital bug. Just extend the date.
                        if self.config.mode == TradingMode.PAPER:
                            new_expiration = date.today() + timedelta(days=180)
                            position.expiration = new_expiration.strftime('%Y-%m-%d')
                            position.current_dte = 180
                            position.dte_at_entry = 180
                            logger.info(
                                f"JUBILEE PAPER: Auto-extended box spread {position.position_id} "
                                f"expiration to {position.expiration} (180 DTE). No roll needed."
                            )
                        else:
                            # LIVE MODE: Real positions need actual rolling
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

            logger.info(f"JUBILEE daily cycle complete: {result['positions_updated']} positions updated")

        except Exception as e:
            logger.error(f"JUBILEE daily cycle error: {e}")
            result['errors'].append(str(e))

        return result

    def run_signal_scan(self) -> Dict[str, Any]:
        """
        Scan for new box spread opportunities.

        This is typically run weekly or on-demand to find
        favorable box spread opportunities.
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"JUBILEE signal scan starting at {now}")

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
            logger.error(f"JUBILEE signal scan error: {e}")
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
        """Get comprehensive JUBILEE status"""
        # In PAPER mode, ensure a box spread exists so capital is never $0
        if self.config.mode == TradingMode.PAPER:
            positions = self.db.get_open_positions()
            has_viable = any(
                self._position_is_viable(p) for p in positions
            )
            if not has_viable:
                logger.info("PAPER MODE: No viable box spread on status check - creating one")
                self._create_emergency_paper_position()

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
        """
        Roll a position to a new expiration.

        IMPORTANT: Validates the replacement signal BEFORE closing the old
        position to avoid leaving the system with no box spread capital.
        """
        position = self.db.get_position(position_id)
        if not position:
            return {'success': False, 'error': 'Position not found'}

        # Step 1: Generate and validate the replacement signal FIRST
        signal = self.signals.generate_signal()
        if not signal or not signal.is_valid:
            logger.warning(
                f"Roll aborted for {position_id}: could not generate valid replacement signal. "
                f"Keeping existing position open to preserve IC trading capital."
            )
            return {
                'success': False,
                'error': 'Could not generate valid signal for roll - keeping existing position',
                'original_closed': False,
            }

        # Step 2: Now safe to close the old position
        close_result = self.executor.close_position(position, "rolled")
        if not close_result:
            return {'success': False, 'error': 'Failed to close current position'}

        # Step 3: Execute the new position
        new_position = self.executor.execute_signal(signal)
        if not new_position:
            # Old position is closed but new one failed to open.
            # Create an emergency paper box spread to keep IC trading alive.
            logger.error(
                f"Roll partially failed for {position_id}: old closed but new failed to execute. "
                f"Creating emergency paper box spread."
            )
            self._create_emergency_paper_position()
            return {
                'success': False,
                'error': 'Failed to open new position - emergency paper position created',
                'original_closed': True,
                'emergency_position_created': True,
            }

        return {
            'success': True,
            'old_position_id': position_id,
            'new_position_id': new_position.position_id,
            'new_expiration': signal.expiration,
        }

    def _create_emergency_paper_position(self) -> None:
        """
        Create an emergency paper box spread when a roll fails or no position exists.

        Borrows full account capital (from config.capital) via synthetic box spread.
        Uses the same sizing logic as JubileeICTrader._build_paper_box_position.
        """
        try:
            from .models import BoxSpreadPosition, PositionStatus

            now = datetime.now(CENTRAL_TZ)
            paper_dte = 180
            expiration_date = now + timedelta(days=paper_dte)
            expiration_str = expiration_date.strftime('%Y-%m-%d')

            # Derive box size from config capital — borrow the full account
            account_capital = self.config.capital
            strike_width = 50.0
            credit_per_contract = strike_width * 0.99  # 1% discount = borrowing cost
            multiplier = 100

            contracts = max(1, round(account_capital / (credit_per_contract * multiplier)))

            entry_credit = credit_per_contract
            theoretical_value = strike_width
            total_credit = entry_credit * contracts * multiplier
            total_owed = theoretical_value * contracts * multiplier
            borrowing_cost = total_owed - total_credit
            implied_rate = (borrowing_cost / total_owed) * (365.0 / paper_dte) * 100

            lower_strike = 5800.0
            upper_strike = lower_strike + strike_width
            reserve_amount = total_credit * 0.10

            logger.info(
                f"Emergency box spread: {contracts} contracts × ${strike_width} width "
                f"= ${total_credit:,.0f} borrowed (account capital: ${account_capital:,.0f})"
            )

            emergency_box = BoxSpreadPosition(
                position_id=f"EMERGENCY_BOX_{now.strftime('%Y%m%d_%H%M%S')}",
                ticker="SPX",
                lower_strike=lower_strike,
                upper_strike=upper_strike,
                strike_width=strike_width,
                expiration=expiration_str,
                dte_at_entry=paper_dte,
                current_dte=paper_dte,
                call_long_symbol=f"SPX{expiration_str.replace('-', '')}C{int(lower_strike)}",
                call_short_symbol=f"SPX{expiration_str.replace('-', '')}C{int(upper_strike)}",
                put_long_symbol=f"SPX{expiration_str.replace('-', '')}P{int(upper_strike)}",
                put_short_symbol=f"SPX{expiration_str.replace('-', '')}P{int(lower_strike)}",
                call_spread_order_id="EMERGENCY_CALL_ORDER",
                put_spread_order_id="EMERGENCY_PUT_ORDER",
                contracts=contracts,
                entry_credit=entry_credit,
                total_credit_received=total_credit,
                theoretical_value=theoretical_value,
                total_owed_at_expiration=total_owed,
                borrowing_cost=borrowing_cost,
                implied_annual_rate=implied_rate,
                daily_cost=borrowing_cost / paper_dte,
                cost_accrued_to_date=0.0,
                fed_funds_at_entry=4.38,
                margin_rate_at_entry=8.50,
                savings_vs_margin=(8.50 - implied_rate) * total_owed / 100,
                cash_deployed_to_ares=0.0,
                cash_deployed_to_titan=0.0,
                cash_deployed_to_pegasus=0.0,
                cash_held_in_reserve=reserve_amount,
                total_cash_deployed=total_credit,
                returns_from_ares=0.0,
                returns_from_titan=0.0,
                returns_from_pegasus=0.0,
                total_ic_returns=0.0,
                net_profit=0.0,
                spot_at_entry=5825.0,
                vix_at_entry=15.0,
                early_assignment_risk="LOW",
                current_margin_used=total_owed * 0.20,
                margin_cushion=total_owed * 0.30,
                status=PositionStatus.OPEN,
                open_time=now,
                position_explanation="EMERGENCY: Created after roll failure to maintain IC trading capital",
                daily_briefing="Emergency position - roll failed, this ensures IC trading continues"
            )
            # Save with retry - this is the capital source
            saved = False
            for attempt in range(3):
                if self.db.save_position(emergency_box):
                    saved = True
                    logger.info(f"Created emergency box spread: {emergency_box.position_id} with ${total_credit:,.0f}")
                    break
                else:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(f"Emergency box spread save failed (attempt {attempt + 1}/3), retrying in {delay}s...")
                    time.sleep(delay)

            if not saved:
                logger.error("CRITICAL: Failed to save emergency box spread after 3 attempts")
        except Exception as e:
            logger.error(f"CRITICAL: Failed to create emergency box spread: {e}", exc_info=True)

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
        fortress_total = sum(p.cash_deployed_to_ares for p in positions)
        samson_total = sum(p.cash_deployed_to_titan for p in positions)
        anchor_total = sum(p.cash_deployed_to_pegasus for p in positions)
        reserve_total = sum(p.cash_held_in_reserve for p in positions)

        # Returns by bot
        fortress_returns = sum(p.returns_from_ares for p in positions)
        samson_returns = sum(p.returns_from_titan for p in positions)
        anchor_returns = sum(p.returns_from_pegasus for p in positions)

        return {
            'total_cash_generated': sum(p.total_credit_received for p in positions),
            'deployment_summary': {
                'fortress': {
                    'deployed': fortress_total,
                    'returns': fortress_returns,
                    'roi': fortress_returns / fortress_total * 100 if fortress_total > 0 else 0,
                },
                'samson': {
                    'deployed': samson_total,
                    'returns': samson_returns,
                    'roi': samson_returns / samson_total * 100 if samson_total > 0 else 0,
                },
                'anchor': {
                    'deployed': anchor_total,
                    'returns': anchor_returns,
                    'roi': anchor_returns / anchor_total * 100 if anchor_total > 0 else 0,
                },
                'reserve': {
                    'amount': reserve_total,
                },
            },
            'total_deployed': fortress_total + samson_total + anchor_total,
            'total_returns': fortress_returns + samson_returns + anchor_returns,
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

## The JUBILEE Strategy

JUBILEE uses box spreads to:
1. Generate cash at low interest rates (often below margin rates)
2. Deploy that cash to IC bots (FORTRESS, SAMSON, ANCHOR)
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
        """Check if we should look for new box spread positions.

        The box spread opens ONCE and stays open until it needs to roll.
        Only scan for a new one if there are no viable positions.
        """
        # Only open a new box spread if none exist
        positions = self.db.get_open_positions()
        if positions:
            # Check if any are still viable (not expired)
            for pos in positions:
                try:
                    exp_date = datetime.strptime(pos.expiration, '%Y-%m-%d').date()
                    if (exp_date - date.today()).days > 0:
                        return False  # Already have a viable box spread
                except (ValueError, TypeError):
                    continue

        # Check if in trading window
        if not self._in_trading_window():
            return False

        return True

    def _get_skip_reason(self) -> str:
        """Get reason for skipping signal scan"""
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

    def _position_is_viable(self, position: BoxSpreadPosition) -> bool:
        """Check if a box spread position has non-expired DTE."""
        try:
            exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
            return (exp_date - date.today()).days > 0
        except (ValueError, TypeError):
            return False

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
        JUBILEE deployed borrowed capital to FORTRESS/SAMSON/ANCHOR.
        The new standalone model uses JubileeICTrader instead.

        Queries FORTRESS, SAMSON, and ANCHOR closed_trades tables to get
        actual realized P&L since this JUBILEE position was opened.

        Returns are proportionally attributed based on each bot's share
        of total IC capital at time of deployment.

        Fallback: Uses 100000.0 as default starting capital for each bot
        if their config tables don't have starting_capital set.
        """
        returns = {
            'fortress': 0.0,
            'samson': 0.0,
            'anchor': 0.0,
        }

        if not IC_DB_AVAILABLE:
            logger.warning("IC database not available - using estimated returns")
            return self._estimate_ic_returns(position)

        try:
            conn = get_connection()
            cur = conn.cursor()

            # Get the start date for this position
            start_date = position.open_time.strftime('%Y-%m-%d')

            # Query ARES/FORTRESS returns
            if position.cash_deployed_to_ares > 0:
                try:
                    cur.execute("""
                        SELECT COALESCE(SUM(realized_pnl), 0)
                        FROM fortress_positions
                        WHERE status IN ('closed', 'expired')
                        AND close_time >= %s::timestamp
                    """, (start_date,))
                    result = cur.fetchone()
                    total_fortress_pnl = float(result[0]) if result and result[0] else 0.0

                    # Get FORTRESS total capital to calculate attribution
                    cur.execute("""
                        SELECT value FROM fortress_config WHERE key = 'starting_capital'
                    """)
                    ares_cap_result = cur.fetchone()
                    fortress_capital = float(ares_cap_result[0]) if ares_cap_result else 100000.0

                    # Attribute returns proportionally
                    if fortress_capital > 0:
                        attribution_pct = position.cash_deployed_to_ares / fortress_capital
                        returns['fortress'] = total_fortress_pnl * min(attribution_pct, 1.0)

                    logger.debug(f"FORTRESS returns: ${returns['fortress']:.2f} (total: ${total_fortress_pnl:.2f}, attribution: {attribution_pct*100:.1f}%)")
                except Exception as e:
                    logger.warning(f"Failed to fetch FORTRESS returns: {e}")

            # Query TITAN/SAMSON returns
            if position.cash_deployed_to_titan > 0:
                try:
                    cur.execute("""
                        SELECT COALESCE(SUM(realized_pnl), 0)
                        FROM samson_positions
                        WHERE status IN ('closed', 'expired')
                        AND close_time >= %s::timestamp
                    """, (start_date,))
                    result = cur.fetchone()
                    total_samson_pnl = float(result[0]) if result and result[0] else 0.0

                    cur.execute("""
                        SELECT value FROM samson_config WHERE key = 'starting_capital'
                    """)
                    titan_cap_result = cur.fetchone()
                    samson_capital = float(titan_cap_result[0]) if titan_cap_result else 100000.0

                    if samson_capital > 0:
                        attribution_pct = position.cash_deployed_to_titan / samson_capital
                        returns['samson'] = total_samson_pnl * min(attribution_pct, 1.0)

                    logger.debug(f"SAMSON returns: ${returns['samson']:.2f}")
                except Exception as e:
                    logger.warning(f"Failed to fetch SAMSON returns: {e}")

            # Query ANCHOR returns
            if position.cash_deployed_to_pegasus > 0:
                try:
                    cur.execute("""
                        SELECT COALESCE(SUM(realized_pnl), 0)
                        FROM anchor_positions
                        WHERE status IN ('closed', 'expired')
                        AND close_time >= %s::timestamp
                    """, (start_date,))
                    result = cur.fetchone()
                    total_anchor_pnl = float(result[0]) if result and result[0] else 0.0

                    cur.execute("""
                        SELECT value FROM anchor_config WHERE key = 'starting_capital'
                    """)
                    anchor_cap_result = cur.fetchone()
                    anchor_capital = float(anchor_cap_result[0]) if anchor_cap_result else 100000.0

                    if anchor_capital > 0:
                        attribution_pct = position.cash_deployed_to_pegasus / anchor_capital
                        returns['anchor'] = total_anchor_pnl * min(attribution_pct, 1.0)

                    logger.debug(f"ANCHOR returns: ${returns['anchor']:.2f}")
                except Exception as e:
                    logger.warning(f"Failed to fetch ANCHOR returns: {e}")

            cur.close()
            conn.close()

            logger.info(f"IC returns for position {position.position_id}: "
                       f"FORTRESS=${returns['fortress']:.2f}, SAMSON=${returns['samson']:.2f}, ANCHOR=${returns['anchor']:.2f}")

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
        The new standalone model uses JubileeICTrader which tracks
        its own IC positions in jubilee_ic_positions table.

        Uses conservative 2.5% monthly return estimate as fallback.
        This is intentionally conservative to avoid overstating returns.
        """
        days_held = (date.today() - position.open_time.date()).days
        monthly_return_rate = 0.025  # 2.5% monthly estimate
        daily_rate = monthly_return_rate / 30

        return {
            'fortress': position.cash_deployed_to_ares * daily_rate * days_held,
            'samson': position.cash_deployed_to_titan * daily_rate * days_held,
            'anchor': position.cash_deployed_to_pegasus * daily_rate * days_held,
        }

    def _get_yesterday_rate(self) -> Optional[float]:
        """Get yesterday's box spread rate for comparison"""
        history = self.db.get_rate_history(days=2)
        if len(history) >= 2:
            return float(history[1].get('box_implied_rate', 0))
        return None


# Convenience function for scheduler
def run_jubilee_daily_cycle():
    """Run the daily JUBILEE cycle - called by scheduler"""
    trader = JubileeTrader()
    return trader.run_daily_cycle()


def run_jubilee_signal_scan():
    """Run JUBILEE signal scan - called weekly or on-demand"""
    trader = JubileeTrader()
    return trader.run_signal_scan()


# ==============================================================================
# JUBILEE IC TRADER
# ==============================================================================
# Orchestrates the Iron Condor trading side of JUBILEE.
# This is the "returns engine" that generates premium income from borrowed capital.
# ==============================================================================

class JubileeICTrader:
    """
    Main orchestrator for JUBILEE Iron Condor trading.

    EDUCATIONAL NOTE - IC Trading in JUBILEE:
    ============================================
    While the JubileeTrader handles long-term box spread borrowing,
    the JubileeICTrader handles daily IC trading that generates returns
    to exceed the borrowing costs.

    Schedule:
    - Run every 5-15 minutes during market hours
    - Check exit conditions on all open positions
    - Generate new signals when capital is available
    - Execute approved signals

    Key Differences from Other IC Bots (SAMSON, ANCHOR):
    - Uses borrowed capital from box spreads
    - All returns are tracked against specific box positions
    - Conservative sizing to protect borrowed capital
    - Requires Prophet approval before trading
    """

    def __init__(self, config: Optional[JubileeICConfig] = None):
        self.db = JubileeDatabase(bot_name="JUBILEE_IC")

        # Load and validate config
        self.config = config or self.db.load_ic_config()
        if not self.config:
            logger.warning("IC config is None, using defaults")
            self.config = JubileeICConfig()

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
            self.signal_gen = JubileeICSignalGenerator(self.config)
            self.executor = JubileeICExecutor(self.config, self.db)
        except Exception as e:
            logger.error(f"Failed to initialize IC trader components: {e}")
            raise RuntimeError(f"JubileeICTrader initialization failed: {e}")

    def run_trading_cycle(self) -> Dict[str, Any]:
        """
        Run a complete IC trading cycle.

        This is the main entry point, called every 5-15 minutes.
        """
        now = datetime.now(CENTRAL_TZ)
        logger.info(f"JUBILEE IC trading cycle starting at {now}")

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

            # Note: Equity snapshots are now event-driven (on open/close) to match SAMSON
            # No per-cycle snapshot needed

            logger.info(f"JUBILEE IC cycle complete: {result['positions_closed']} closed, new={bool(result['new_position'])}")

        except Exception as e:
            logger.error(f"JUBILEE IC trading cycle error: {e}")
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

                        # Save equity snapshot after closing position (match SAMSON: event-driven MTM)
                        try:
                            self.db.record_ic_equity_snapshot()
                            logger.info(f"[JUBILEE IC] Equity snapshot recorded after closing {position.position_id}")
                        except Exception as e:
                            logger.warning(f"[JUBILEE IC] Failed to record equity snapshot on close: {e}")

            except Exception as e:
                logger.error(f"Error checking position {position.position_id}: {e}")

        return {'checked': checked, 'closed': closed}

    def _can_open_new_position(self) -> bool:
        """Check if we can open a new IC position.

        Like SAMSON: no position count gates — capital is used for SIZING, not gating.
        UNLIKE SAMSON: JUBILEE has a box spread safety rail because IC losses
        can threaten the borrowed capital margin. This is the ONE gate that matters.
        """
        # BOX SPREAD SAFETY RAIL: Halt if daily IC losses exceed threshold
        daily_max = getattr(self.config, 'daily_max_ic_loss', 25000.0)
        if daily_max > 0:
            daily_pnl = self.db.get_ic_daily_realized_pnl()
            if daily_pnl < -daily_max:
                logger.warning(
                    f"[JUBILEE IC] SAFETY RAIL: Daily IC loss ${daily_pnl:,.2f} exceeds "
                    f"max ${-daily_max:,.2f} — halting new trades to protect box margin"
                )
                return False

        # BOX SPREAD SAFETY RAIL: Halt if cumulative drawdown exceeds threshold
        max_dd_pct = getattr(self.config, 'max_ic_drawdown_pct', 10.0)
        if max_dd_pct > 0:
            total_pnl = self.db.get_ic_total_realized_pnl()
            borrowed_capital = self._get_borrowed_capital()
            if borrowed_capital > 0:
                drawdown_pct = abs(min(0, total_pnl)) / borrowed_capital * 100
                if drawdown_pct >= max_dd_pct:
                    logger.warning(
                        f"[JUBILEE IC] SAFETY RAIL: Cumulative drawdown {drawdown_pct:.1f}% "
                        f"exceeds max {max_dd_pct:.1f}% — halting to protect box margin"
                    )
                    return False

        return True

    def _get_borrowed_capital(self) -> float:
        """Get total borrowed capital from box spreads (before IC margin subtraction)."""
        box_positions = self.db.get_open_positions()
        total = 0.0
        for box in box_positions:
            try:
                exp = box.expiration
                if isinstance(exp, str):
                    exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                elif hasattr(exp, 'date'):
                    exp_date = exp.date()
                else:
                    exp_date = exp
                if (exp_date - date.today()).days <= 0:
                    continue
            except (ValueError, TypeError, AttributeError):
                total += box.total_cash_deployed
                continue
            total += box.total_cash_deployed
        if total <= 0 and self.config.mode == TradingMode.PAPER:
            total = self.config.starting_capital
        return total

    def _get_skip_reason(self) -> str:
        """Get reason for not opening new position"""
        # Check safety rail first
        daily_max = getattr(self.config, 'daily_max_ic_loss', 25000.0)
        if daily_max > 0:
            daily_pnl = self.db.get_ic_daily_realized_pnl()
            if daily_pnl < -daily_max:
                return f"Daily IC loss ${daily_pnl:,.2f} exceeds safety rail (${-daily_max:,.2f})"

        max_dd_pct = getattr(self.config, 'max_ic_drawdown_pct', 10.0)
        if max_dd_pct > 0:
            total_pnl = self.db.get_ic_total_realized_pnl()
            borrowed = self._get_borrowed_capital()
            if borrowed > 0:
                dd_pct = abs(min(0, total_pnl)) / borrowed * 100
                if dd_pct >= max_dd_pct:
                    return f"Cumulative drawdown {dd_pct:.1f}% exceeds max {max_dd_pct:.1f}%"

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

        Capital flows from box spreads (borrowed money) to the IC trader.
        The box spread is the sole source of capital for IC trading.
        """
        # Ensure a box spread exists (creates or auto-extends in PAPER mode)
        self._ensure_paper_box_spread()

        # Get capital from box spread positions - the sole source
        box_positions = self.db.get_open_positions()

        # Calculate total capital from viable (non-expired) box spreads
        total_borrowed = 0.0
        for box in box_positions:
            try:
                # Handle both string and date expiration formats
                exp = box.expiration
                if isinstance(exp, str):
                    exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                elif hasattr(exp, 'date'):
                    exp_date = exp.date()
                else:
                    exp_date = exp
                if (exp_date - date.today()).days <= 0:
                    continue  # Skip expired positions
            except (ValueError, TypeError, AttributeError):
                # If we can't parse expiration, include the capital anyway
                # rather than silently skipping it
                logger.warning(f"[JUBILEE IC] Could not parse expiration '{box.expiration}' for {box.position_id} - including capital")
                total_borrowed += box.total_cash_deployed
                continue
            total_borrowed += box.total_cash_deployed

        # PAPER MODE FALLBACK: If no box capital exists, use config capital
        # so IC trading is never blocked by missing/expired/failed box spreads
        if total_borrowed <= 0 and self.config.mode == TradingMode.PAPER:
            fallback_capital = self.config.starting_capital
            logger.warning(
                f"PAPER MODE: No box spread capital available, using config "
                f"starting_capital (${fallback_capital:,.0f}) as fallback"
            )
            total_borrowed = fallback_capital

        # Subtract margin tied up by open IC positions (spread_width * contracts * 100)
        ic_positions = self.db.get_open_ic_positions()
        margin_in_use = 0.0
        for ic in ic_positions:
            margin_in_use += ic.spread_width * ic.contracts * 100
        total_borrowed -= margin_in_use

        logger.info(f"[JUBILEE IC] Available capital: ${max(0, total_borrowed):,.0f} (box borrowed minus ${margin_in_use:,.0f} IC margin in use)")

        return max(0, total_borrowed)

    def _ensure_paper_box_spread(self) -> None:
        """
        In PAPER mode, guarantee a viable box spread position always exists.

        The box spread is the SOLE source of borrowed capital for IC trading.
        This method must never silently fail - if a box spread doesn't exist,
        it creates one. If one is approaching expiration, it auto-extends it.
        Retries on failure to ensure the capital source is always available.
        """
        if self.config.mode != TradingMode.PAPER:
            return

        box_positions = self.db.get_open_positions()

        # Check viability and auto-extend any positions approaching threshold
        if box_positions:
            viable = False
            for pos in box_positions:
                try:
                    exp_date = datetime.strptime(pos.expiration, '%Y-%m-%d').date()
                    dte = (exp_date - date.today()).days
                    if dte > 30:
                        viable = True
                    elif dte > 0:
                        # Position approaching roll threshold - auto-extend it
                        new_expiration = date.today() + timedelta(days=180)
                        pos.expiration = new_expiration.strftime('%Y-%m-%d')
                        pos.current_dte = 180
                        saved = self.db.save_position(pos)
                        if saved:
                            logger.info(
                                f"PAPER MODE: Auto-extended {pos.position_id} to "
                                f"{pos.expiration} (was {dte} DTE)"
                            )
                            viable = True
                        else:
                            logger.error(f"PAPER MODE: Failed to save auto-extended position {pos.position_id}")
                    # else: DTE <= 0, skip this expired position
                except (ValueError, TypeError):
                    continue
            if viable:
                return  # Have at least one viable position providing capital

        # No viable box spread exists - create one with retry.
        # This is the capital source for IC trading, so failure is not acceptable.
        logger.info("PAPER MODE: No viable box spread - creating one for IC trading capital")
        try:
            synthetic_box = self._build_paper_box_position(
                position_id_prefix="PAPER_BOX",
                explanation="PAPER MODE: Synthetic box spread borrowing full account capital for IC trading",
            )
            # Save with retry - this is the capital source, failure is not acceptable
            saved = False
            for attempt in range(3):
                if self.db.save_position(synthetic_box):
                    saved = True
                    logger.info(
                        f"Created paper box spread: {synthetic_box.position_id} "
                        f"with ${synthetic_box.total_cash_deployed:,.0f} borrowed capital"
                    )
                    break
                else:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(
                        f"Box spread save failed (attempt {attempt + 1}/3), "
                        f"retrying in {delay}s..."
                    )
                    time.sleep(delay)

            if not saved:
                logger.error(
                    "CRITICAL: Failed to save paper box spread after 3 attempts. "
                    "IC trading will have no capital until next cycle."
                )
        except Exception as e:
            logger.error(f"CRITICAL: Failed to create paper box spread: {e}", exc_info=True)

    def _build_paper_box_position(
        self,
        position_id_prefix: str = "PAPER_BOX",
        explanation: str = "PAPER MODE: Synthetic box spread for IC trading",
    ) -> 'BoxSpreadPosition':
        """
        Build a paper box spread position sized to borrow full account capital.

        Box spread synthetic borrowing: you sell a box spread on SPX to receive
        cash (the "loan"). The credit received ≈ strike_width × contracts × 100,
        minus a small discount that represents the implied borrowing rate.

        Sizing is derived from config, not hardcoded:
        - Account capital comes from JubileeConfig.capital (via db.get_starting_capital)
        - Contracts are calculated to borrow the full amount
        - Strike width fixed at $50 (standard SPX box spread unit)
        - Entry credit = 99% of strike width (~4% annualized on 180 DTE)
        """
        from .models import BoxSpreadPosition, PositionStatus

        now = datetime.now(CENTRAL_TZ)
        paper_dte = 180
        expiration_date = now + timedelta(days=paper_dte)
        expiration_str = expiration_date.strftime('%Y-%m-%d')

        # Derive box size from config capital — borrow the full account
        account_capital = self.db.get_starting_capital()
        strike_width = 50.0
        credit_per_contract = strike_width * 0.99  # 1% discount = borrowing cost
        multiplier = 100  # Options multiplier

        # Calculate contracts needed to borrow full account capital
        contracts = max(1, round(account_capital / (credit_per_contract * multiplier)))

        # Calculate actual amounts from the contract count
        entry_credit = credit_per_contract
        theoretical_value = strike_width
        total_credit = entry_credit * contracts * multiplier
        total_owed = theoretical_value * contracts * multiplier
        borrowing_cost = total_owed - total_credit
        implied_rate = (borrowing_cost / total_owed) * (365.0 / paper_dte) * 100

        lower_strike = 5800.0
        upper_strike = lower_strike + strike_width
        reserve_amount = total_credit * 0.10  # 10% reserve

        logger.info(
            f"Building paper box spread: {contracts} contracts × ${strike_width} width "
            f"= ${total_credit:,.0f} borrowed (account capital: ${account_capital:,.0f})"
        )

        return BoxSpreadPosition(
            position_id=f"{position_id_prefix}_{now.strftime('%Y%m%d_%H%M%S')}",
            ticker="SPX",
            lower_strike=lower_strike,
            upper_strike=upper_strike,
            strike_width=strike_width,
            expiration=expiration_str,
            dte_at_entry=paper_dte,
            current_dte=paper_dte,
            call_long_symbol=f"SPX{expiration_str.replace('-', '')}C{int(lower_strike)}",
            call_short_symbol=f"SPX{expiration_str.replace('-', '')}C{int(upper_strike)}",
            put_long_symbol=f"SPX{expiration_str.replace('-', '')}P{int(upper_strike)}",
            put_short_symbol=f"SPX{expiration_str.replace('-', '')}P{int(lower_strike)}",
            call_spread_order_id=f"{position_id_prefix}_CALL_ORDER",
            put_spread_order_id=f"{position_id_prefix}_PUT_ORDER",
            contracts=contracts,
            entry_credit=entry_credit,
            total_credit_received=total_credit,
            theoretical_value=theoretical_value,
            total_owed_at_expiration=total_owed,
            borrowing_cost=borrowing_cost,
            implied_annual_rate=implied_rate,
            daily_cost=borrowing_cost / paper_dte,
            cost_accrued_to_date=0.0,
            fed_funds_at_entry=4.38,
            margin_rate_at_entry=8.50,
            savings_vs_margin=(8.50 - implied_rate) * total_owed / 100,
            cash_deployed_to_ares=0.0,
            cash_deployed_to_titan=0.0,
            cash_deployed_to_pegasus=0.0,
            cash_held_in_reserve=reserve_amount,
            total_cash_deployed=total_credit,
            returns_from_ares=0.0,
            returns_from_titan=0.0,
            returns_from_pegasus=0.0,
            total_ic_returns=0.0,
            net_profit=0.0,
            spot_at_entry=5825.0,
            vix_at_entry=15.0,
            early_assignment_risk="LOW",
            current_margin_used=total_owed * 0.20,
            margin_cushion=total_owed * 0.30,
            status=PositionStatus.OPEN,
            open_time=now,
            position_explanation=explanation,
            daily_briefing="Paper trading position - no real capital at risk",
        )

    def _get_source_box_position(self) -> Optional[str]:
        """
        Get the box position ID to link new IC trades to.

        IC trades are always linked to a box spread position (the source of capital).
        In PAPER mode, auto-creates a paper box spread if none exists.
        Never returns None in PAPER mode - IC trading must never be blocked.
        """
        # Ensure we have a box spread position (creates paper one if needed)
        self._ensure_paper_box_spread()

        box_positions = self.db.get_open_positions()
        if box_positions:
            # Use the most recently opened box position
            sorted_boxes = sorted(box_positions, key=lambda p: p.open_time, reverse=True)
            return sorted_boxes[0].position_id

        # PAPER MODE FALLBACK: If ensure_paper_box_spread failed silently,
        # use a synthetic box ID so IC trading is never blocked
        if self.config.mode == TradingMode.PAPER:
            logger.warning("[JUBILEE IC] No box positions found despite ensure_paper_box_spread - using synthetic ID")
            return "PAPER_BOX_FALLBACK"

        return None

    def _get_thompson_weight(self) -> float:
        """Get Thompson Sampling allocation weight for position sizing (match SAMSON)."""
        if not MATH_OPTIMIZER_AVAILABLE:
            return 1.0
        try:
            mixin = MathOptimizerMixin()
            if hasattr(mixin, 'math_get_allocation'):
                allocation = mixin.math_get_allocation()
                jubilee_alloc = allocation.get('allocations', {}).get('JUBILEE', 0.2)
                weight = jubilee_alloc / 0.2  # Normalize to 20% baseline
                logger.info(f"[JUBILEE IC] Thompson weight: {weight:.2f} (allocation: {jubilee_alloc:.1%})")
                return weight
        except Exception as e:
            logger.debug(f"[JUBILEE IC] Thompson allocation not available: {e}")
        return 1.0

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
            logger.warning("[JUBILEE IC] No open box spread position to fund IC trade")
            result['error'] = "No open box spread position to fund IC trade"
            return result

        # Get available capital
        available_capital = self._get_available_capital()
        logger.info(f"[JUBILEE IC] Available capital: ${available_capital:,.2f}, source box: {source_box_id}")

        # Get Thompson Sampling weight for position sizing (match SAMSON)
        thompson_weight = self._get_thompson_weight()

        # Generate signal
        signal = self.signal_gen.generate_signal(
            source_box_position_id=source_box_id,
            available_capital=available_capital,
            thompson_weight=thompson_weight,
        )

        if not signal:
            logger.warning("[JUBILEE IC] Signal generator returned None (no market data or Prophet unavailable)")
            result['error'] = "Failed to generate signal"
            return result

        result['signal_generated'] = True

        # Log the signal regardless of validity
        self.db.log_ic_signal(signal, was_executed=False)

        if not signal.is_valid:
            logger.info(f"[JUBILEE IC] Signal invalid: {signal.skip_reason}")
            result['error'] = f"Signal invalid: {signal.skip_reason}"
            return result

        logger.info(
            f"[JUBILEE IC] Valid signal: {signal.put_short_strike}/{signal.put_long_strike} PUT, "
            f"{signal.call_short_strike}/{signal.call_long_strike} CALL, "
            f"credit=${signal.total_credit:.4f}, contracts={signal.contracts}"
        )

        # Execute the signal
        position = self.executor.execute_signal(signal)
        if position:
            result['new_position'] = position.position_id
            logger.info(f"[JUBILEE IC] Position OPENED: {position.position_id}")

            # Update signal log with execution status (UPSERT marks it as executed)
            self.db.log_ic_signal(signal, was_executed=True, executed_position_id=position.position_id)

            # Save equity snapshot after opening position (match SAMSON: event-driven MTM)
            try:
                self.db.record_ic_equity_snapshot()
                logger.info(f"[JUBILEE IC] Equity snapshot recorded after opening {position.position_id}")
            except Exception as e:
                logger.warning(f"[JUBILEE IC] Failed to record equity snapshot on open: {e}")

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
            logger.error("[JUBILEE IC] Executor failed to create position from valid signal")
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

    def _position_to_dict(self, position: JubileeICPosition) -> Dict[str, Any]:
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
            # Prophet details - FULL reasoning for transparency
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
def run_jubilee_ic_cycle():
    """Run the JUBILEE IC trading cycle - called every 5-15 minutes"""
    trader = JubileeICTrader()
    return trader.run_trading_cycle()


def run_jubilee_ic_mtm_update():
    """Update mark-to-market for all open IC positions and record equity snapshot"""
    db = JubileeDatabase(bot_name="JUBILEE_IC")
    config = db.load_ic_config()
    executor = JubileeICExecutor(config, db)

    positions = db.get_open_ic_positions()
    updated = 0

    for position in positions:
        try:
            executor.update_position_mtm(position.position_id)
            updated += 1
        except Exception as e:
            logger.error(f"MTM update failed for {position.position_id}: {e}")

    # Always record equity snapshot after MTM update to preserve intraday state.
    # Even if no positions were updated (e.g., no open positions or all MTM fetches
    # failed), the snapshot captures realized P&L from closed trades so the
    # intraday chart has data points.
    snapshot_saved = False
    try:
        snapshot_saved = db.record_ic_equity_snapshot()
        if snapshot_saved:
            logger.info(f"IC equity snapshot recorded ({updated} positions updated)")
    except Exception as e:
        logger.error(f"Failed to record IC equity snapshot: {e}")

    return {'updated': updated, 'total': len(positions), 'snapshot_saved': snapshot_saved}
