"""
ICARUS - Order Executor
========================

Clean order execution via Tradier (paper or live).

ICARUS uses aggressive position sizing:
- 4% risk per trade (vs ATHENA's 2%)
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from .models import (
    SpreadPosition, SpreadType, PositionStatus,
    TradeSignal, ICARUSConfig, TradingMode, CENTRAL_TZ
)

# Monte Carlo Kelly for intelligent position sizing
KELLY_AVAILABLE = False
try:
    from quant.monte_carlo_kelly import get_safe_position_size
    KELLY_AVAILABLE = True
except ImportError:
    pass

# Position Management Agent - tracks entry conditions and alerts on regime changes
POSITION_MGMT_AVAILABLE = False
try:
    from ai.position_management_agent import PositionManagementAgent
    POSITION_MGMT_AVAILABLE = True
except ImportError:
    PositionManagementAgent = None

# SOLOMON Feedback Loop - continuous learning system
SOLOMON_AVAILABLE = False
try:
    from quant.solomon_feedback_loop import SolomonFeedbackLoop, ProposalStatus
    SOLOMON_AVAILABLE = True
except ImportError:
    SolomonFeedbackLoop = None
    ProposalStatus = None

# SOLOMON Enhancements - risk guardrails (consecutive loss kill, max daily loss)
SOLOMON_ENHANCEMENTS_AVAILABLE = False
try:
    from quant.solomon_enhancements import ConsecutiveLossTracker, DailyLossTracker, ENHANCED_GUARDRAILS
    SOLOMON_ENHANCEMENTS_AVAILABLE = True
except ImportError:
    ConsecutiveLossTracker = None
    DailyLossTracker = None
    ENHANCED_GUARDRAILS = None

# SOLOMON Notifications - multi-channel alerts
SOLOMON_NOTIFICATIONS_AVAILABLE = False
try:
    from quant.solomon_notifications import SolomonNotifications
    SOLOMON_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    SolomonNotifications = None

# SOLOMON AI Analyst - Claude-powered performance analysis
SOLOMON_AI_AVAILABLE = False
try:
    from quant.solomon_ai_analyst import SolomonAIAnalyst
    SOLOMON_AI_AVAILABLE = True
except ImportError:
    SolomonAIAnalyst = None

# AI Trade Recommendations - Claude Haiku generates entry/exit triggers
AI_TRADE_RECOMMENDATIONS_AVAILABLE = False
try:
    from ai.ai_trade_recommendations import AITradeRecommendation
    AI_TRADE_RECOMMENDATIONS_AVAILABLE = True
except ImportError:
    AITradeRecommendation = None

# Smart Trade Advisor - self-learning trade advisor
SMART_ADVISOR_AVAILABLE = False
try:
    from ai.ai_trade_advisor import SmartTradeAdvisor
    SMART_ADVISOR_AVAILABLE = True
except ImportError:
    SmartTradeAdvisor = None

# AI Strategy Optimizer - analyzes backtest results, suggests improvements
STRATEGY_OPTIMIZER_AVAILABLE = False
try:
    from ai.ai_strategy_optimizer import StrategyOptimizerAgent
    STRATEGY_OPTIMIZER_AVAILABLE = True
except ImportError:
    StrategyOptimizerAgent = None

# ML Pattern Learner - pattern recognition for confidence calibration
PATTERN_LEARNER_AVAILABLE = False
try:
    from ai.autonomous_ml_pattern_learner import PatternLearner
    PATTERN_LEARNER_AVAILABLE = True
except ImportError:
    PatternLearner = None

# LangChain Intelligence - AI decision backbone
LANGCHAIN_INTELLIGENCE_AVAILABLE = False
try:
    from ai.langchain_intelligence import LangChainIntelligence
    LANGCHAIN_INTELLIGENCE_AVAILABLE = True
except ImportError:
    LangChainIntelligence = None

# Autonomous AI Reasoning - strike selection, sizing, exit decisions
AI_REASONING_AVAILABLE = False
try:
    from ai.autonomous_ai_reasoning import AutonomousAIReasoning
    AI_REASONING_AVAILABLE = True
except ImportError:
    AutonomousAIReasoning = None

# GEXIS Extended Thinking - deeper reasoning for complex decisions
GEXIS_THINKING_AVAILABLE = False
try:
    from ai.gexis_extended_thinking import ExtendedThinking
    GEXIS_THINKING_AVAILABLE = True
except ImportError:
    ExtendedThinking = None

# GEXIS Knowledge - context management for decisions
GEXIS_KNOWLEDGE_AVAILABLE = False
try:
    from ai.gexis_knowledge import GEXISKnowledge
    GEXIS_KNOWLEDGE_AVAILABLE = True
except ImportError:
    GEXISKnowledge = None

# GEXIS Learning Memory - persistent learning
GEXIS_MEMORY_AVAILABLE = False
try:
    from ai.gexis_learning_memory import GEXISLearningMemory
    GEXIS_MEMORY_AVAILABLE = True
except ImportError:
    GEXISLearningMemory = None

logger = logging.getLogger(__name__)

# Tradier import with fallback
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

# Data provider for quotes
try:
    from data.unified_data_provider import get_quote, get_price
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class OrderExecutor:
    """
    Executes spread orders via Tradier.

    ICARUS uses aggressive position sizing:
    - 4% risk per trade (vs ATHENA's 2%)
    - Thompson Sampling weight scales position size
    """

    def __init__(self, config: ICARUSConfig):
        self.config = config
        self.tradier = None

        if TRADIER_AVAILABLE and config.mode != TradingMode.PAPER:
            try:
                self.tradier = TradierDataFetcher(sandbox=False)
                logger.info("ICARUS OrderExecutor: Tradier initialized for LIVE trading")
            except Exception as e:
                logger.error(f"ICARUS OrderExecutor: Tradier init failed: {e}")

        # Position Management Agent - tracks entry conditions for exit timing
        self.position_mgmt = None
        if POSITION_MGMT_AVAILABLE:
            try:
                self.position_mgmt = PositionManagementAgent()
                logger.info("ICARUS OrderExecutor: Position Management Agent initialized")
            except Exception as e:
                logger.debug(f"Position Management Agent init failed: {e}")

    def execute_spread(
        self,
        signal: TradeSignal,
        thompson_weight: float = 1.0
    ) -> Optional[SpreadPosition]:
        """
        Execute a spread trade based on the signal.

        Args:
            signal: The trade signal to execute
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)

        Returns SpreadPosition on success, None on failure.
        """
        if self.config.mode == TradingMode.PAPER:
            return self._execute_paper(signal, thompson_weight)
        else:
            return self._execute_live(signal, thompson_weight)

    def _execute_paper(self, signal: TradeSignal, thompson_weight: float = 1.0) -> Optional[SpreadPosition]:
        """Execute paper trade (simulation)."""
        try:
            now = datetime.now(CENTRAL_TZ)
            position_id = f"ICARUS-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            # Calculate contracts based on risk, scaled by Thompson allocation
            contracts = self._calculate_position_size(signal.max_loss, thompson_weight)

            # Recalculate P&L based on contracts
            max_loss = signal.max_loss * contracts
            max_profit = signal.max_profit * contracts

            position = SpreadPosition(
                position_id=position_id,
                spread_type=signal.spread_type,
                ticker=self.config.ticker,
                long_strike=signal.long_strike,
                short_strike=signal.short_strike,
                expiration=signal.expiration,
                entry_debit=signal.estimated_debit,
                contracts=contracts,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                vix_at_entry=signal.vix,
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                oracle_confidence=signal.oracle_confidence,
                ml_direction=signal.oracle_direction,  # Use oracle direction since ML doesn't predict direction
                ml_confidence=signal.ml_win_probability,  # Use ML win probability as confidence proxy
                ml_model_name=signal.ml_model_name,
                ml_win_probability=signal.ml_win_probability,
                ml_top_features=signal.ml_top_features,
                wall_type=signal.wall_type,
                wall_distance_pct=signal.wall_distance_pct,
                trade_reasoning=signal.reasoning,
                order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"ICARUS PAPER TRADE: {signal.spread_type.value} "
                f"{signal.long_strike}/{signal.short_strike} "
                f"x{contracts} @ ${signal.estimated_debit:.2f}"
            )

            return position

        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: TradeSignal, thompson_weight: float = 1.0) -> Optional[SpreadPosition]:
        """Execute live trade via Tradier."""
        if not self.tradier:
            logger.error("Live execution requested but Tradier not available")
            return None

        try:
            now = datetime.now(CENTRAL_TZ)

            # Determine option type
            option_type = "call" if signal.spread_type == SpreadType.BULL_CALL else "put"

            # Get real quotes for the spread
            spread_quote = self._get_spread_quote(
                signal.long_strike,
                signal.short_strike,
                signal.expiration,
                option_type
            )

            if not spread_quote:
                logger.error("Failed to get spread quotes")
                return None

            actual_debit = spread_quote['mid_price']

            # Calculate contracts with Thompson allocation weight
            contracts = self._calculate_position_size(actual_debit * 100, thompson_weight)

            # Place the order
            order_result = self.tradier.place_vertical_spread(
                symbol=self.config.ticker,
                expiration=signal.expiration,
                long_strike=signal.long_strike,
                short_strike=signal.short_strike,
                option_type=option_type,
                quantity=contracts,
                limit_price=round(actual_debit, 2)
            )

            if not order_result or not order_result.get('order'):
                logger.error(f"Order placement failed: {order_result}")
                return None

            order_info = order_result['order']
            order_id = str(order_info.get('id', 'UNKNOWN'))

            # Validate order status
            order_status = order_info.get('status', 'unknown')
            if order_status in ['rejected', 'canceled', 'error']:
                logger.error(f"Order {order_id} was {order_status}")
                return None

            # Calculate P&L
            spread_width = abs(signal.short_strike - signal.long_strike)
            max_profit = (spread_width - actual_debit) * 100 * contracts
            max_loss = actual_debit * 100 * contracts

            position = SpreadPosition(
                position_id=f"ICARUS-LIVE-{order_id}",
                spread_type=signal.spread_type,
                ticker=self.config.ticker,
                long_strike=signal.long_strike,
                short_strike=signal.short_strike,
                expiration=signal.expiration,
                entry_debit=actual_debit,
                contracts=contracts,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                vix_at_entry=signal.vix,
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                oracle_confidence=signal.oracle_confidence,
                ml_direction=signal.oracle_direction,  # Use oracle direction since ML doesn't predict direction
                ml_confidence=signal.ml_win_probability,  # Use ML win probability as confidence proxy
                ml_model_name=signal.ml_model_name,
                ml_win_probability=signal.ml_win_probability,
                ml_top_features=signal.ml_top_features,
                wall_type=signal.wall_type,
                wall_distance_pct=signal.wall_distance_pct,
                trade_reasoning=signal.reasoning,
                order_id=order_id,
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"ICARUS LIVE TRADE: {signal.spread_type.value} "
                f"{signal.long_strike}/{signal.short_strike} "
                f"x{contracts} @ ${actual_debit:.2f} [Order: {order_id}]"
            )

            return position

        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_position(
        self,
        position: SpreadPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """
        Close a position.

        Returns: (success, close_price, realized_pnl)
        """
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            return self._close_live(position, reason)

    def _close_paper(
        self,
        position: SpreadPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close paper position with simulated pricing"""
        try:
            current_price = self._get_current_price()
            if not current_price:
                logger.warning(f"Could not fetch current price, using entry price")
                current_price = position.underlying_at_entry

            close_price = self._estimate_spread_value(position, current_price)
            pnl_per_contract = (close_price - position.entry_debit) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"ICARUS PAPER CLOSE: {position.position_id} "
                f"@ ${close_price:.2f} P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Paper close failed: {e}")
            return False, 0, 0

    def _close_live(
        self,
        position: SpreadPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close live position via Tradier"""
        if not self.tradier:
            logger.error("Cannot close live position - Tradier not available")
            return False, 0, 0

        try:
            option_type = "call" if position.spread_type == SpreadType.BULL_CALL else "put"

            spread_quote = self._get_spread_quote(
                position.long_strike,
                position.short_strike,
                position.expiration,
                option_type
            )

            if not spread_quote:
                logger.error("Failed to get closing quotes")
                return False, 0, 0

            close_price = spread_quote['mid_price']

            order_result = self.tradier.place_vertical_spread(
                symbol=self.config.ticker,
                expiration=position.expiration,
                long_strike=position.long_strike,
                short_strike=position.short_strike,
                option_type=option_type,
                quantity=position.contracts,
                limit_price=round(close_price, 2),
                is_closing=True
            )

            if not order_result or not order_result.get('order'):
                logger.error(f"Close order failed: {order_result}")
                return False, 0, 0

            pnl_per_contract = (close_price - position.entry_debit) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"ICARUS LIVE CLOSE: {position.position_id} "
                f"@ ${close_price:.2f} P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Live close failed: {e}")
            return False, 0, 0

    def _get_kelly_position_size(self) -> Optional[Dict]:
        """Get Monte Carlo Kelly-based position sizing for ICARUS."""
        if not KELLY_AVAILABLE:
            return None

        try:
            from database_adapter import DatabaseAdapter
            db = DatabaseAdapter()

            trades = db.execute_query("""
                SELECT pnl_realized, entry_debit, max_loss
                FROM autonomous_closed_trades
                WHERE bot_name = 'ICARUS'
                AND closed_at > NOW() - INTERVAL '90 days'
                ORDER BY closed_at DESC
                LIMIT 100
            """)

            if not trades or len(trades) < 20:
                return None

            wins = [t for t in trades if t['pnl_realized'] > 0]
            losses = [t for t in trades if t['pnl_realized'] <= 0]
            capital = 100_000

            win_rate = len(wins) / len(trades)
            avg_win_pct = sum(t['pnl_realized'] for t in wins) / len(wins) / capital * 100 if wins else 0
            avg_loss_pct = abs(sum(t['pnl_realized'] for t in losses) / len(losses) / capital * 100) if losses else 10

            kelly_result = get_safe_position_size(
                win_rate=win_rate,
                avg_win=avg_win_pct,
                avg_loss=avg_loss_pct,
                sample_size=len(trades),
                account_size=capital,
                max_risk_pct=self.config.risk_per_trade_pct * 2
            )

            logger.info(f"[ICARUS KELLY] Win Rate: {win_rate:.1%}, Safe Kelly: {kelly_result['kelly_safe']:.1f}%")
            return kelly_result

        except Exception as e:
            logger.debug(f"[KELLY] Error: {e}")
            return None

    def _calculate_position_size(self, max_loss_per_contract: float, thompson_weight: float = 1.0) -> int:
        """
        Calculate position size using Monte Carlo Kelly criterion.

        ICARUS uses aggressive 4% risk per trade, but Kelly can optimize further.
        """
        capital = 100_000

        if max_loss_per_contract <= 0:
            return 1

        # Try Kelly-based sizing first
        kelly_result = self._get_kelly_position_size()

        if kelly_result and kelly_result.get('kelly_safe', 0) > 0:
            kelly_risk_pct = kelly_result['kelly_safe']
            max_risk = capital * (kelly_risk_pct / 100)
            sizing_source = "KELLY"
            logger.info(f"[ICARUS] Using Kelly-safe sizing: {kelly_risk_pct:.1f}% risk")
        else:
            max_risk = capital * (self.config.risk_per_trade_pct / 100)
            sizing_source = "CONFIG"

        base_contracts = max_risk / max_loss_per_contract

        clamped_weight = max(0.5, min(2.0, thompson_weight))
        adjusted_contracts = int(base_contracts * clamped_weight)

        if abs(thompson_weight - 1.0) > 0.05:
            logger.info(f"[ICARUS {sizing_source}] Thompson: weight={thompson_weight:.2f}, base={base_contracts:.1f}, adjusted={adjusted_contracts}")

        return max(1, min(adjusted_contracts, 50))

    def _get_current_price(self) -> Optional[float]:
        """Get current underlying price"""
        if DATA_AVAILABLE:
            try:
                return get_price(self.config.ticker)
            except Exception:
                pass
        return None

    def _get_spread_quote(
        self,
        long_strike: float,
        short_strike: float,
        expiration: str,
        option_type: str
    ) -> Optional[Dict[str, float]]:
        """Get quote for the spread"""
        if not self.tradier:
            return None

        try:
            long_symbol = self._build_option_symbol(
                self.config.ticker, expiration, long_strike, option_type
            )
            short_symbol = self._build_option_symbol(
                self.config.ticker, expiration, short_strike, option_type
            )

            long_quote = self.tradier.get_option_quote(long_symbol)
            short_quote = self.tradier.get_option_quote(short_symbol)

            if long_quote and short_quote:
                long_mid = (long_quote.get('bid', 0) + long_quote.get('ask', 0)) / 2
                short_mid = (short_quote.get('bid', 0) + short_quote.get('ask', 0)) / 2
                mid_price = long_mid - short_mid

                return {
                    'long_bid': long_quote.get('bid', 0),
                    'long_ask': long_quote.get('ask', 0),
                    'short_bid': short_quote.get('bid', 0),
                    'short_ask': short_quote.get('ask', 0),
                    'mid_price': max(0.01, mid_price),
                }
        except Exception as e:
            logger.warning(f"Failed to get spread quote: {e}")

        return None

    def _build_option_symbol(
        self,
        ticker: str,
        expiration: str,
        strike: float,
        option_type: str
    ) -> str:
        """Build OCC option symbol"""
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        opt_char = "C" if option_type.lower() == "call" else "P"
        strike_str = f"{int(strike * 1000):08d}"
        return f"{ticker}{exp_str}{opt_char}{strike_str}"

    def _estimate_spread_value(
        self,
        position: SpreadPosition,
        current_price: float
    ) -> float:
        """Estimate current spread value for paper trading"""
        spread_width = abs(position.short_strike - position.long_strike)

        if position.spread_type == SpreadType.BULL_CALL:
            if current_price >= position.short_strike:
                return spread_width
            elif current_price <= position.long_strike:
                return 0
            else:
                pct_itm = (current_price - position.long_strike) / spread_width
                return spread_width * pct_itm
        else:
            if current_price <= position.short_strike:
                return spread_width
            elif current_price >= position.long_strike:
                return 0
            else:
                pct_itm = (position.long_strike - current_price) / spread_width
                return spread_width * pct_itm

    def get_position_current_value(
        self,
        position: SpreadPosition
    ) -> Optional[float]:
        """Get current value of a position"""
        if self.config.mode == TradingMode.PAPER:
            current_price = self._get_current_price()
            if current_price:
                return self._estimate_spread_value(position, current_price)
            return None
        else:
            option_type = "call" if position.spread_type == SpreadType.BULL_CALL else "put"
            spread_quote = self._get_spread_quote(
                position.long_strike,
                position.short_strike,
                position.expiration,
                option_type
            )
            if spread_quote:
                return spread_quote['mid_price']
            return None

    def store_entry_conditions(self, position_id: int, gex_data: Dict) -> bool:
        """
        Store entry conditions when position is opened.

        This enables the Position Management Agent to detect when market
        conditions change significantly from entry (GEX regime flip, etc.)
        """
        if not self.position_mgmt:
            return False

        try:
            self.position_mgmt.store_entry_conditions(position_id, gex_data)
            logger.info(f"[ICARUS] Entry conditions stored for position {position_id}")
            return True
        except Exception as e:
            logger.debug(f"Failed to store entry conditions: {e}")
            return False

    def check_position_conditions(self, position: Dict, current_gex: Dict) -> Dict:
        """
        Check if current conditions differ from entry conditions.

        Returns alerts if GEX regime flipped, flip point moved significantly, etc.
        This helps with exit timing - exit early if thesis is invalidated.
        """
        if not self.position_mgmt:
            return {'alerts': [], 'severity': 'info', 'should_exit_early': False}

        try:
            result = self.position_mgmt.check_position_conditions(position, current_gex)

            # Add should_exit_early flag for critical alerts
            should_exit = result.get('severity') == 'critical'
            result['should_exit_early'] = should_exit

            if result.get('alerts'):
                for alert in result['alerts']:
                    logger.info(f"[ICARUS CONDITION ALERT] {alert['type']}: {alert['message']}")
                    if alert.get('suggestion'):
                        logger.info(f"  Suggestion: {alert['suggestion']}")

            return result

        except Exception as e:
            logger.debug(f"Failed to check position conditions: {e}")
            return {'alerts': [], 'severity': 'info', 'should_exit_early': False}
