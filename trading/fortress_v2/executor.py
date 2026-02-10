"""
FORTRESS V2 - Order Executor
=========================

Clean order execution for Iron Condors via Tradier.

Iron Condor = Bull Put Spread + Bear Call Spread
Both are credit spreads (receive premium).
"""

import logging
import uuid
import time
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, Callable, TypeVar
from zoneinfo import ZoneInfo
from functools import wraps

from .models import (
    IronCondorPosition, PositionStatus,
    IronCondorSignal, FortressConfig, TradingMode, CENTRAL_TZ
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

# PROVERBS Feedback Loop - continuous learning system
PROVERBS_AVAILABLE = False
try:
    from quant.proverbs_feedback_loop import ProverbsFeedbackLoop, ProposalStatus
    PROVERBS_AVAILABLE = True
except ImportError:
    ProverbsFeedbackLoop = None
    ProposalStatus = None

# PROVERBS Enhancements - risk guardrails (consecutive loss kill, max daily loss)
PROVERBS_ENHANCEMENTS_AVAILABLE = False
try:
    from quant.proverbs_enhancements import ConsecutiveLossTracker, DailyLossTracker, ENHANCED_GUARDRAILS
    PROVERBS_ENHANCEMENTS_AVAILABLE = True
except ImportError:
    ConsecutiveLossTracker = None
    DailyLossTracker = None
    ENHANCED_GUARDRAILS = None

# PROVERBS Notifications - multi-channel alerts
PROVERBS_NOTIFICATIONS_AVAILABLE = False
try:
    from quant.proverbs_notifications import ProverbsNotifications
    PROVERBS_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    ProverbsNotifications = None

# PROVERBS AI Analyst - Claude-powered performance analysis
PROVERBS_AI_AVAILABLE = False
try:
    from quant.proverbs_ai_analyst import ProverbsAIAnalyst
    PROVERBS_AI_AVAILABLE = True
except ImportError:
    ProverbsAIAnalyst = None

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

# COUNSELOR Extended Thinking - deeper reasoning for complex decisions
COUNSELOR_THINKING_AVAILABLE = False
try:
    from ai.counselor_extended_thinking import ExtendedThinking
    COUNSELOR_THINKING_AVAILABLE = True
except ImportError:
    ExtendedThinking = None

# COUNSELOR Knowledge - context management for decisions
COUNSELOR_KNOWLEDGE_AVAILABLE = False
try:
    from ai.counselor_knowledge import CounselorKnowledge
    COUNSELOR_KNOWLEDGE_AVAILABLE = True
except ImportError:
    CounselorKnowledge = None

# COUNSELOR Learning Memory - persistent learning
COUNSELOR_MEMORY_AVAILABLE = False
try:
    from ai.counselor_learning_memory import CounselorLearningMemory
    COUNSELOR_MEMORY_AVAILABLE = True
except ImportError:
    CounselorLearningMemory = None

logger = logging.getLogger(__name__)

T = TypeVar('T')


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator for retrying Tradier API calls with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        logger.warning(
                            f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"API call failed after {max_retries + 1} attempts: {e}")
            raise last_exception
        return wrapper
    return decorator

# Tradier import
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

# Data provider
try:
    from data.unified_data_provider import get_price
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class OrderExecutor:
    """
    Executes Iron Condor orders via Tradier.

    Handles both paper (simulated) and live execution.

    MATH OPTIMIZER INTEGRATION:
    - Thompson Sampling weight scales position size based on bot performance
    - Higher allocation = larger positions when bot is performing well
    """

    def __init__(self, config: FortressConfig, db=None):
        self.config = config
        self.tradier = None
        self.tradier_2 = None  # Second sandbox account for trade mirroring
        self.tradier_init_error = None  # Track initialization error for status reporting
        self.db = db  # Optional DB reference for orphaned order tracking
        self.paper_trading_enabled = True  # Always run paper trades alongside live

        if TRADIER_AVAILABLE and config.mode == TradingMode.LIVE:
            # CRITICAL: Check for sandbox credentials BEFORE attempting init
            # This prevents silent failures where trades never execute
            from unified_config import APIConfig
            sandbox_key = APIConfig.TRADIER_SANDBOX_API_KEY
            sandbox_account = APIConfig.TRADIER_SANDBOX_ACCOUNT_ID

            if not sandbox_key or not sandbox_account:
                missing = []
                if not sandbox_key:
                    missing.append("TRADIER_SANDBOX_API_KEY")
                if not sandbox_account:
                    missing.append("TRADIER_SANDBOX_ACCOUNT_ID")
                self.tradier_init_error = f"Missing credentials: {', '.join(missing)}"
                logger.error(f"FORTRESS OrderExecutor: CANNOT EXECUTE TRADES - {self.tradier_init_error}")
                logger.error("FORTRESS OrderExecutor: Set these environment variables to enable sandbox trading")
            else:
                try:
                    # FORTRESS uses SANDBOX Tradier account (not production)
                    self.tradier = TradierDataFetcher(sandbox=True)
                    logger.info("FORTRESS OrderExecutor: Tradier initialized for LIVE trading (SANDBOX account)")
                    logger.info(f"FORTRESS OrderExecutor: Account ID {sandbox_account[:4]}...{sandbox_account[-4:] if len(sandbox_account) > 8 else ''}")
                except Exception as e:
                    self.tradier_init_error = str(e)
                    logger.error(f"FORTRESS OrderExecutor: Tradier init failed - {e}")
                    logger.error("FORTRESS OrderExecutor: Trades will NOT execute until this is resolved")

            # Initialize second sandbox account for trade mirroring (optional)
            sandbox_key_2 = APIConfig.TRADIER_FORTRESS_SANDBOX_API_KEY_2
            sandbox_account_2 = APIConfig.TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2

            if sandbox_key_2 and sandbox_account_2:
                try:
                    self.tradier_2 = TradierDataFetcher(
                        api_key=sandbox_key_2,
                        account_id=sandbox_account_2,
                        sandbox=True
                    )
                    logger.info("FORTRESS OrderExecutor: Second Tradier account initialized for trade mirroring")
                    logger.info(f"FORTRESS OrderExecutor: Account 2 ID {sandbox_account_2[:4]}...{sandbox_account_2[-4:] if len(sandbox_account_2) > 8 else ''}")
                except Exception as e:
                    logger.warning(f"FORTRESS OrderExecutor: Second account init failed (trades will still execute on primary): {e}")
            else:
                logger.warning("FORTRESS OrderExecutor: Second account NOT configured - set TRADIER_FORTRESS_SANDBOX_API_KEY_2 and TRADIER_FORTRESS_SANDBOX_ACCOUNT_ID_2")

            logger.info(f"FORTRESS OrderExecutor: Paper trading alongside live: ENABLED")

        # Position Management Agent - tracks entry conditions for exit timing
        self.position_mgmt = None
        if POSITION_MGMT_AVAILABLE:
            try:
                self.position_mgmt = PositionManagementAgent()
                logger.info("FORTRESS OrderExecutor: Position Management Agent initialized")
            except Exception as e:
                logger.debug(f"Position Management Agent init failed: {e}")

    @property
    def can_execute_trades(self) -> bool:
        """Check if executor can actually place trades in Tradier."""
        return self.tradier is not None

    def get_execution_status(self) -> dict:
        """Get detailed execution capability status for monitoring."""
        return {
            "can_execute": self.can_execute_trades,
            "tradier_initialized": self.tradier is not None,
            "tradier_2_initialized": self.tradier_2 is not None,
            "paper_trading_enabled": self.paper_trading_enabled,
            "accounts_active": sum([
                self.tradier is not None,
                self.tradier_2 is not None,
                self.paper_trading_enabled,
            ]),
            "init_error": self.tradier_init_error,
            "mode": self.config.mode.value if hasattr(self.config.mode, 'value') else str(self.config.mode),
        }

    def _mirror_ic_to_second_account(
        self,
        signal: IronCondorSignal,
        contracts: int,
        limit_price: float
    ) -> None:
        """
        Mirror an Iron Condor trade to the second sandbox account.

        Fire and forget - no tracking, no error propagation.
        Primary account trade has already succeeded when this is called.
        """
        if not self.tradier_2:
            return

        try:
            result = self.tradier_2.place_iron_condor(
                symbol=self.config.ticker,
                expiration=signal.expiration,
                put_long=signal.put_long,
                put_short=signal.put_short,
                call_short=signal.call_short,
                call_long=signal.call_long,
                quantity=contracts,
                limit_price=round(limit_price, 2),
            )
            if result and result.get('order'):
                order_id = result['order'].get('id', 'UNKNOWN')
                logger.info(f"FORTRESS MIRROR: IC mirrored to account 2 [Order: {order_id}]")
            else:
                logger.warning(f"FORTRESS MIRROR: IC mirror to account 2 returned no order: {result}")
        except Exception as e:
            logger.warning(f"FORTRESS MIRROR: IC mirror to account 2 failed (non-blocking): {e}")

    def _mirror_close_to_second_account(
        self,
        position: IronCondorPosition,
        put_value: float,
        call_value: float
    ) -> None:
        """
        Mirror a close order to the second sandbox account.

        Fire and forget - no tracking, no error propagation.
        """
        if not self.tradier_2:
            return

        try:
            # Close put spread on second account
            self.tradier_2.place_vertical_spread(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.put_short_strike,
                short_strike=position.put_long_strike,
                option_type="put",
                quantity=position.contracts,
                limit_price=round(put_value, 2),
            )

            # Close call spread on second account
            self.tradier_2.place_vertical_spread(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.call_short_strike,
                short_strike=position.call_long_strike,
                option_type="call",
                quantity=position.contracts,
                limit_price=round(call_value, 2),
            )

            logger.info(f"FORTRESS MIRROR: Close mirrored to account 2 for {position.position_id}")
        except Exception as e:
            logger.warning(f"FORTRESS MIRROR: Close mirror to account 2 failed (non-blocking): {e}")

    def _send_orphaned_order_alert(
        self,
        order_id: str,
        order_type: str,
        strikes: Dict,
        contracts: int,
        error_msg: str
    ):
        """
        Send critical push notification for orphaned orders requiring manual intervention.

        This is called when an Iron Condor spread fails mid-execution and rollback also fails,
        leaving one leg open that requires manual closing.
        """
        try:
            from backend.push_notification_service import get_push_service
            push_service = get_push_service()
            if not push_service:
                logger.warning("Push service unavailable for orphaned order alert")
                return

            title = f"🚨 FORTRESS ORPHANED ORDER - MANUAL ACTION REQUIRED"
            body = (
                f"Order {order_id} ({order_type}) stuck open!\n"
                f"Strikes: {strikes}\n"
                f"Contracts: {contracts}\n"
                f"Error: {error_msg[:100]}"
            )

            stats = push_service.broadcast_notification(
                title=title,
                body=body,
                alert_type='orphaned_order',
                alert_level='CRITICAL'
            )
            logger.info(f"Orphaned order alert sent: {stats.get('sent', 0)} delivered")

        except Exception as e:
            logger.error(f"Failed to send orphaned order alert: {e}")

    def _tradier_place_spread_with_retry(
        self,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict]:
        """
        Place a vertical spread order with retry logic.

        Retries on network errors and transient API failures.

        Args:
            max_retries: Number of retry attempts
            **kwargs: All arguments passed to tradier.place_vertical_spread()
        """
        if not self.tradier:
            return None

        last_error = None
        for attempt in range(max_retries):
            try:
                result = self.tradier.place_vertical_spread(**kwargs)
                if result:
                    return result
                # If result is None/falsy but no exception, don't retry
                logger.warning(f"Tradier returned empty result on attempt {attempt + 1}")
                return None
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 1.0 * (2 ** attempt)  # 1s, 2s, 4s
                    logger.warning(
                        f"Tradier API error (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Tradier API failed after {max_retries} attempts: {e}")

        # If we exhausted retries, raise the last error
        if last_error:
            raise last_error
        return None

    def _tradier_place_ic_with_retry(
        self,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict]:
        """
        Place a 4-leg Iron Condor order with retry logic.

        Uses Tradier's native multileg order to send all 4 legs atomically.

        Args:
            max_retries: Number of retry attempts
            **kwargs: All arguments passed to tradier.place_iron_condor()
        """
        if not self.tradier:
            return None

        last_error = None
        for attempt in range(max_retries):
            try:
                result = self.tradier.place_iron_condor(**kwargs)
                if result:
                    return result
                logger.warning(f"Tradier IC returned empty result on attempt {attempt + 1}")
                return None
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 1.0 * (2 ** attempt)  # 1s, 2s, 4s
                    logger.warning(
                        f"Tradier IC API error (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Tradier IC API failed after {max_retries} attempts: {e}")

        if last_error:
            raise last_error
        return None

    def _tradier_get_quote_with_retry(
        self,
        symbol: str,
        max_retries: int = 2
    ) -> Optional[Dict]:
        """
        Get option quote with retry logic.

        Uses fewer retries than order placement since quotes are less critical.
        """
        if not self.tradier:
            return None

        for attempt in range(max_retries):
            try:
                result = self.tradier.get_option_quote(symbol)
                if result:
                    return result
                return None
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 0.5 * (2 ** attempt)  # 0.5s, 1s
                    logger.debug(f"Quote fetch error (attempt {attempt + 1}): {e}. Retrying...")
                    time.sleep(delay)
                else:
                    logger.warning(f"Quote fetch failed after {max_retries} attempts: {e}")

        return None

    def execute_iron_condor(
        self,
        signal: IronCondorSignal,
        thompson_weight: float = 1.0
    ) -> Optional[IronCondorPosition]:
        """
        Execute an Iron Condor trade on all configured accounts.

        In LIVE mode: Executes on primary Tradier, mirrors to secondary Tradier,
        AND saves a paper trade record for comparison tracking.

        In PAPER mode: Only executes paper trade (internal simulation).

        Args:
            signal: The trade signal to execute
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)
                            Values > 1.0 increase position size for hot bots
                            Values < 1.0 decrease position size for cold bots

        Returns IronCondorPosition on success, None on failure.
        """
        if self.config.mode == TradingMode.PAPER:
            return self._execute_paper(signal, thompson_weight)
        else:
            # LIVE mode: Execute on both Tradier sandbox accounts AND run paper simulation
            live_position = self._execute_live(signal, thompson_weight)

            # Also run paper trade simulation for comparison tracking
            # The paper trade uses internal pricing model (not Tradier fills)
            if self.paper_trading_enabled and live_position:
                try:
                    paper_position = self._execute_paper(signal, thompson_weight)
                    if paper_position and self.db:
                        self.db.log(
                            "PAPER_TRADE",
                            f"Paper trade opened: {paper_position.position_id} "
                            f"{signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                            f"x{paper_position.contracts} @ ${signal.total_credit:.2f} credit",
                            {
                                'paper_position_id': paper_position.position_id,
                                'live_position_id': live_position.position_id,
                                'paper_contracts': paper_position.contracts,
                                'paper_credit': signal.total_credit,
                                'live_credit': live_position.total_credit,
                            }
                        )
                        logger.info(f"FORTRESS PAPER: Paper trade {paper_position.position_id} tracked alongside live {live_position.position_id}")
                except Exception as e:
                    logger.warning(f"FORTRESS PAPER: Paper trade tracking failed (non-blocking): {e}")

            return live_position

    def _execute_paper(self, signal: IronCondorSignal, thompson_weight: float = 1.0) -> Optional[IronCondorPosition]:
        """Execute paper trade (simulation)"""
        try:
            now = datetime.now(CENTRAL_TZ)
            position_id = f"FORTRESS-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            # Calculate contracts based on risk, scaled by Thompson allocation
            contracts = self._calculate_position_size(signal.max_loss, thompson_weight)

            # Calculate actual P&L values
            spread_width = signal.put_short - signal.put_long
            max_profit = signal.total_credit * 100 * contracts
            max_loss = (spread_width - signal.total_credit) * 100 * contracts

            # Convert Prophet top_factors to JSON string for DB storage
            import json
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=position_id,
                ticker=self.config.ticker,
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Chronicles context
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Prophet context (FULL audit trail)
                oracle_confidence=signal.oracle_confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                # Order tracking
                put_order_id="PAPER",
                call_order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"PAPER IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${signal.total_credit:.2f} credit"
            )

            return position

        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: IronCondorSignal, thompson_weight: float = 1.0) -> Optional[IronCondorPosition]:
        """Execute live Iron Condor via Tradier"""
        if not self.tradier:
            logger.error("Live execution requested but Tradier not available")
            return None

        try:
            now = datetime.now(CENTRAL_TZ)

            # Get real quotes for the IC
            ic_quote = self._get_iron_condor_quote(signal)
            if not ic_quote:
                logger.error("Failed to get IC quotes")
                return None

            actual_credit = ic_quote['total_credit']
            # Apply Thompson allocation weight to position size
            contracts = self._calculate_position_size(ic_quote['max_loss_per_contract'] * 100, thompson_weight)

            # Execute as single 4-leg Iron Condor order (atomic - all legs fill together or none)
            # Using retry wrapper for network resilience
            ic_result = self._tradier_place_ic_with_retry(
                symbol=self.config.ticker,
                expiration=signal.expiration,
                put_long=signal.put_long,
                put_short=signal.put_short,
                call_short=signal.call_short,
                call_long=signal.call_long,
                quantity=contracts,
                limit_price=round(actual_credit, 2),
            )

            if not ic_result or not ic_result.get('order'):
                logger.error(f"Iron Condor order failed: {ic_result}")
                return None

            # Single order ID for the entire IC (use for both fields for backward compatibility)
            ic_order_id = str(ic_result['order'].get('id', 'UNKNOWN'))
            put_order_id = ic_order_id
            call_order_id = ic_order_id

            # Calculate P&L
            spread_width = signal.put_short - signal.put_long
            max_profit = actual_credit * 100 * contracts
            max_loss = (spread_width - actual_credit) * 100 * contracts

            # Convert Prophet top_factors to JSON string for DB storage
            import json
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=f"FORTRESS-LIVE-{put_order_id}",
                ticker=self.config.ticker,
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=ic_quote['put_credit'],
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=ic_quote['call_credit'],
                contracts=contracts,
                spread_width=spread_width,
                total_credit=actual_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Chronicles context
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Prophet context (FULL audit trail)
                oracle_confidence=signal.oracle_confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                # Order tracking
                put_order_id=put_order_id,
                call_order_id=call_order_id,
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"LIVE IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${actual_credit:.2f} [Order: {ic_order_id}]"
            )

            # Mirror trade to second account (fire and forget - no tracking)
            self._mirror_ic_to_second_account(signal, contracts, actual_credit)

            return position

        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_position(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """
        Close an Iron Condor position.

        In LIVE mode, also closes the corresponding paper position if it exists.

        Returns: (success, close_price, realized_pnl)
        """
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            result = self._close_live(position, reason)

            # Log paper close simulation alongside live close
            if self.paper_trading_enabled and self.db and result[0] is True:
                try:
                    paper_success, paper_close_price, paper_pnl = self._close_paper(position, reason)
                    if paper_success:
                        self.db.log(
                            "PAPER_CLOSE",
                            f"Paper close for {position.position_id}: "
                            f"Paper P&L=${paper_pnl:.2f}, Live P&L=${result[2]:.2f}, "
                            f"Reason={reason}",
                            {
                                'position_id': position.position_id,
                                'paper_pnl': paper_pnl,
                                'live_pnl': result[2],
                                'paper_close_price': paper_close_price,
                                'live_close_price': result[1],
                            }
                        )
                        logger.info(f"FORTRESS PAPER: Close tracked - Paper P&L=${paper_pnl:.2f} vs Live P&L=${result[2]:.2f}")
                except Exception as e:
                    logger.debug(f"FORTRESS PAPER: Paper close tracking failed (non-blocking): {e}")

            return result

    def _close_paper(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close paper position with simulated pricing"""
        try:
            # BUG FIX: Use mark-to-market for consistency with unrealized P&L display
            # The old estimation formula gave values inconsistent with what unrealized showed,
            # causing positions showing -$3k unrealized to suddenly "close" as a +$2k win.
            close_price = None
            try:
                from trading.mark_to_market import calculate_ic_mark_to_market
                mtm = calculate_ic_mark_to_market(
                    underlying="SPY",
                    expiration=position.expiration,
                    put_short=position.put_short_strike,
                    put_long=position.put_long_strike,
                    call_short=position.call_short_strike,
                    call_long=position.call_long_strike,
                    contracts=position.contracts,
                    entry_credit=position.total_credit,
                    use_cache=False
                )
                if mtm.get('success') and mtm.get('current_value') is not None:
                    close_price = mtm['current_value']
                    logger.info(f"PAPER CLOSE MTM: {position.position_id} close_value=${close_price:.4f}")
            except Exception as e:
                logger.debug(f"MTM failed for paper close, using estimation: {e}")

            # Fallback to estimation if MTM fails
            if close_price is None:
                current_price = self._get_current_price()
                if not current_price:
                    current_price = position.underlying_at_entry
                close_price = self._estimate_ic_value(position, current_price)

            # P&L = credit received - debit to close
            # For IC: we received total_credit, now we pay close_price to close
            pnl_per_contract = (position.total_credit - close_price) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"PAPER CLOSE: {position.position_id} "
                f"@ ${close_price:.2f}, P&L: ${realized_pnl:.2f} [{reason}]"
            )

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Paper close failed: {e}")
            return False, 0, 0

    def _close_live(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """Close live IC position via Tradier"""
        if not self.tradier:
            logger.error("Cannot close - Tradier not available")
            return False, 0, 0

        try:
            # Get current IC quote
            ic_quote = self._get_position_quote(position)
            if not ic_quote:
                logger.error("Failed to get closing quotes")
                return False, 0, 0

            close_price = ic_quote['total_value']

            # Close put spread by reversing (buy back short, sell long = debit spread)
            # Using retry wrapper for network resilience
            put_result = self._tradier_place_spread_with_retry(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.put_short_strike,  # Buy back what we sold
                short_strike=position.put_long_strike,   # Sell what we bought
                option_type="put",
                quantity=position.contracts,
                limit_price=round(ic_quote['put_value'], 2),
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Failed to close put spread: {put_result}")
                return False, 0, 0

            # Close call spread by reversing - with retry
            call_result = self._tradier_place_spread_with_retry(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.call_short_strike,  # Buy back what we sold
                short_strike=position.call_long_strike,   # Sell what we bought
                option_type="call",
                quantity=position.contracts,
                limit_price=round(ic_quote['call_value'], 2),
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Failed to close call spread (put was closed!): {call_result}")
                # Partial close - put side closed but call failed
                partial_pnl = (position.put_credit - ic_quote['put_value']) * 100 * position.contracts
                logger.warning(f"PARTIAL CLOSE: Put side closed, P&L=${partial_pnl:.2f}")
                # Return special tuple indicating partial close (success=False but with 'partial' marker)
                # Caller should handle this by marking position as partial_close in DB
                return 'partial_put', ic_quote['put_value'], partial_pnl

            # P&L calculation
            pnl_per_contract = (position.total_credit - close_price) * 100
            realized_pnl = pnl_per_contract * position.contracts

            logger.info(
                f"LIVE CLOSE: {position.position_id} "
                f"@ ${close_price:.2f}, P&L: ${realized_pnl:.2f} [{reason}]"
            )

            # Mirror close to second account (fire and forget)
            self._mirror_close_to_second_account(position, ic_quote['put_value'], ic_quote['call_value'])

            return True, close_price, realized_pnl

        except Exception as e:
            logger.error(f"Live close failed: {e}")
            return False, 0, 0

    def close_call_spread_only(
        self,
        position: IronCondorPosition,
        reason: str
    ) -> Tuple[bool, float, float]:
        """
        Close only the call spread leg of a partially closed Iron Condor.

        This is used for retry logic when put leg closed but call leg failed.

        Returns: (success, close_price, realized_pnl)
        """
        if self.config.mode == TradingMode.PAPER:
            # Paper mode: simulate call leg close
            try:
                current_price = self._get_current_price()
                if not current_price:
                    current_price = position.underlying_at_entry

                # Estimate call spread value only
                call_value = self._estimate_spread_value(
                    position.call_short_strike,
                    position.call_long_strike,
                    current_price,
                    'call'
                )
                call_pnl = (position.call_credit - call_value) * 100 * position.contracts

                logger.info(f"PAPER CLOSE (call only): {position.position_id}, P&L: ${call_pnl:.2f}")
                return True, call_value, call_pnl

            except Exception as e:
                logger.error(f"Paper close (call only) failed: {e}")
                return False, 0, 0

        # Live mode: close call spread via Tradier
        if not self.tradier:
            logger.error("Cannot close call spread - Tradier not available")
            return False, 0, 0

        try:
            # Get current call spread quote
            call_quote = self._get_spread_quote(
                position.ticker,
                position.expiration,
                position.call_short_strike,
                position.call_long_strike,
                'call'
            )

            if not call_quote:
                logger.error("Failed to get call spread quote for retry")
                return False, 0, 0

            call_value = call_quote.get('value', 0)

            # Close call spread by reversing
            call_result = self._tradier_place_spread_with_retry(
                symbol=position.ticker,
                expiration=position.expiration,
                long_strike=position.call_short_strike,  # Buy back what we sold
                short_strike=position.call_long_strike,   # Sell what we bought
                option_type="call",
                quantity=position.contracts,
                limit_price=round(call_value, 2),
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Retry: Failed to close call spread: {call_result}")
                return False, 0, 0

            # Calculate call leg P&L
            call_pnl = (position.call_credit - call_value) * 100 * position.contracts

            logger.info(
                f"LIVE CLOSE (call only): {position.position_id} "
                f"@ ${call_value:.2f}, P&L: ${call_pnl:.2f} [{reason}]"
            )

            return True, call_value, call_pnl

        except Exception as e:
            logger.error(f"Live close (call only) failed: {e}")
            return False, 0, 0

    def _estimate_spread_value(
        self,
        short_strike: float,
        long_strike: float,
        current_price: float,
        option_type: str
    ) -> float:
        """Estimate value of a single spread for paper trading."""
        spread_width = abs(short_strike - long_strike)

        if option_type == 'call':
            if current_price >= long_strike:
                return spread_width  # Max loss
            elif current_price <= short_strike:
                return 0.01  # Near worthless
            else:
                return current_price - short_strike
        else:  # put
            if current_price <= long_strike:
                return spread_width  # Max loss
            elif current_price >= short_strike:
                return 0.01  # Near worthless
            else:
                return short_strike - current_price

    def _get_spread_quote(
        self,
        symbol: str,
        expiration: str,
        short_strike: float,
        long_strike: float,
        option_type: str
    ) -> Optional[Dict]:
        """Get current quote for a single spread."""
        if not self.tradier:
            return None

        try:
            # Get individual option quotes
            # Note: _build_option_symbol gets ticker from self.config.ticker
            short_symbol = self._build_option_symbol(short_strike, expiration, option_type)
            long_symbol = self._build_option_symbol(long_strike, expiration, option_type)

            quotes = self.tradier.get_quotes([short_symbol, long_symbol])
            if not quotes or len(quotes) < 2:
                return None

            short_quote = next((q for q in quotes if str(int(short_strike)) in q.get('symbol', '')), None)
            long_quote = next((q for q in quotes if str(int(long_strike)) in q.get('symbol', '')), None)

            if not short_quote or not long_quote:
                return None

            # For closing a credit spread, we buy back the short and sell the long
            # Value = short ask - long bid (what we pay to close)
            short_ask = short_quote.get('ask', 0) or 0
            long_bid = long_quote.get('bid', 0) or 0
            value = short_ask - long_bid

            return {
                'value': max(0.01, value),
                'short_ask': short_ask,
                'long_bid': long_bid
            }

        except Exception as e:
            logger.error(f"Get spread quote failed: {e}")
            return None

    def _get_kelly_position_size(self, max_loss_per_contract: float) -> Optional[Dict]:
        """
        Get Monte Carlo Kelly-based position sizing recommendation.

        Uses historical win rate and avg win/loss to calculate safe position size
        that survives 95% of Monte Carlo simulations.

        Returns:
            Dict with kelly recommendation or None if not available
        """
        if not KELLY_AVAILABLE:
            return None

        try:
            # Get historical performance from database
            from database_adapter import DatabaseAdapter
            db = DatabaseAdapter()

            # Query closed FORTRESS trades for win rate calculation
            # BUG FIX: Query fortress_positions table instead of autonomous_closed_trades
            # Use COALESCE to handle legacy data with NULL close_time
            trades = db.execute_query("""
                SELECT realized_pnl as pnl_realized, total_credit as entry_credit, max_loss
                FROM fortress_positions
                WHERE status IN ('closed', 'expired')
                AND COALESCE(close_time, open_time) > NOW() - INTERVAL '90 days'
                ORDER BY COALESCE(close_time, open_time) DESC
                LIMIT 100
            """)

            if not trades or len(trades) < 20:
                logger.debug("[KELLY] Insufficient trade history for Kelly sizing (<20 trades)")
                return None

            # Calculate win rate and payoffs
            wins = [t for t in trades if t['pnl_realized'] > 0]
            losses = [t for t in trades if t['pnl_realized'] <= 0]

            win_rate = len(wins) / len(trades)
            avg_win_pct = sum(t['pnl_realized'] for t in wins) / len(wins) / self.config.capital * 100 if wins else 0
            avg_loss_pct = abs(sum(t['pnl_realized'] for t in losses) / len(losses) / self.config.capital * 100) if losses else 10

            # Get Kelly-safe position size
            kelly_result = get_safe_position_size(
                win_rate=win_rate,
                avg_win=avg_win_pct,
                avg_loss=avg_loss_pct,
                sample_size=len(trades),
                account_size=self.config.capital,
                max_risk_pct=self.config.risk_per_trade_pct * 2  # Allow up to 2x config as ceiling
            )

            logger.info(f"[FORTRESS KELLY] Win Rate: {win_rate:.1%}, Safe Kelly: {kelly_result['kelly_safe']:.1f}%, "
                       f"Ruin Prob: {kelly_result['prob_ruin']:.1f}%")

            return kelly_result

        except Exception as e:
            logger.debug(f"[KELLY] Error calculating Kelly size: {e}")
            return None

    def _calculate_position_size(self, max_loss_per_contract: float, thompson_weight: float = 1.0) -> int:
        """
        Calculate position size based on risk settings, Kelly criterion, and Thompson allocation.

        Uses Monte Carlo Kelly sizing when available (survives 95% of simulations),
        falls back to fixed risk_per_trade_pct otherwise.

        Args:
            max_loss_per_contract: Maximum loss per contract in dollars
            thompson_weight: Thompson Sampling allocation weight (0.5-2.0)
                            - 1.0 = neutral (standard sizing)
                            - 1.5 = bot is performing well, increase size 50%
                            - 0.7 = bot is underperforming, reduce size 30%

        Returns:
            Number of contracts to trade (minimum 1)
        """
        capital = self.config.capital

        if max_loss_per_contract <= 0:
            return 1

        # Try Kelly-based sizing first (Monte Carlo stress-tested)
        kelly_result = self._get_kelly_position_size(max_loss_per_contract)

        if kelly_result and kelly_result.get('kelly_safe', 0) > 0:
            # Use Kelly-safe percentage (survives 95% of Monte Carlo scenarios)
            kelly_risk_pct = kelly_result['kelly_safe']
            max_risk = capital * (kelly_risk_pct / 100)
            sizing_source = "KELLY"
            logger.info(f"[FORTRESS] Using Kelly-safe sizing: {kelly_risk_pct:.1f}% risk")
        else:
            # Fallback to config-based fixed risk
            max_risk = capital * (self.config.risk_per_trade_pct / 100)
            sizing_source = "CONFIG"

        # Base position size from risk calculation
        base_contracts = max_risk / max_loss_per_contract

        # Apply Thompson Sampling weight (clamped to reasonable bounds)
        # Weight is normalized so 20% allocation (1/5 bots) = 1.0
        # Higher allocation = larger positions, lower = smaller
        clamped_weight = max(0.5, min(2.0, thompson_weight))
        adjusted_contracts = int(base_contracts * clamped_weight)

        # Log sizing decision
        if abs(thompson_weight - 1.0) > 0.05:
            logger.info(f"[FORTRESS {sizing_source}] Thompson: weight={thompson_weight:.2f}, base={base_contracts:.1f}, adjusted={adjusted_contracts}")

        return max(1, min(adjusted_contracts, self.config.max_contracts))

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
            logger.info(f"[FORTRESS] Entry conditions stored for position {position_id}")
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
                    logger.info(f"[FORTRESS CONDITION ALERT] {alert['type']}: {alert['message']}")
                    if alert.get('suggestion'):
                        logger.info(f"  Suggestion: {alert['suggestion']}")

            return result

        except Exception as e:
            logger.debug(f"Failed to check position conditions: {e}")
            return {'alerts': [], 'severity': 'info', 'should_exit_early': False}

    def _get_current_price(self) -> Optional[float]:
        """Get current underlying price from multiple sources with fallbacks."""
        ticker = self.config.ticker  # Usually 'SPY'

        # Try unified data provider first
        if DATA_AVAILABLE:
            try:
                price = get_price(ticker)
                if price and price > 0:
                    return price
            except Exception as e:
                logger.debug(f"Unified data provider failed for {ticker}: {e}")

        # Try Tradier directly as fallback
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            import os
            # Check TRADIER_PROD_API_KEY first (matches unified_config.py priority)
            api_key = os.environ.get('TRADIER_PROD_API_KEY') or os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_SANDBOX_API_KEY')
            if api_key:
                is_sandbox = api_key == os.environ.get('TRADIER_SANDBOX_API_KEY')
                tradier = TradierDataFetcher(api_key=api_key, sandbox=is_sandbox)
                quote = tradier.get_quote(ticker)
                if quote and quote.get('last'):
                    price = float(quote['last'])
                    if price > 0:
                        logger.debug(f"Got {ticker} price from Tradier: ${price:.2f}")
                        return price
        except Exception as e:
            logger.debug(f"Tradier direct fetch failed for {ticker}: {e}")

        logger.warning(f"Could not get {ticker} price from any source")
        return None

    def _get_iron_condor_quote(self, signal: IronCondorSignal) -> Optional[Dict[str, float]]:
        """Get real quotes for IC"""
        if not self.tradier:
            return None

        try:
            # Get quotes for all 4 legs
            put_long_quote = self._get_option_quote(signal.put_long, signal.expiration, "put")
            put_short_quote = self._get_option_quote(signal.put_short, signal.expiration, "put")
            call_short_quote = self._get_option_quote(signal.call_short, signal.expiration, "call")
            call_long_quote = self._get_option_quote(signal.call_long, signal.expiration, "call")

            if not all([put_long_quote, put_short_quote, call_short_quote, call_long_quote]):
                return None

            # Reject quotes where short leg bids are zero - means no real market
            if put_short_quote['bid'] <= 0 or call_short_quote['bid'] <= 0:
                logger.warning(
                    f"IC quote rejected: short leg bids are zero "
                    f"(put_short bid={put_short_quote['bid']}, call_short bid={call_short_quote['bid']}). "
                    f"No valid market for this IC."
                )
                return None

            # Bull Put Spread credit = short bid - long ask
            put_credit = put_short_quote['bid'] - put_long_quote['ask']

            # Bear Call Spread credit = short bid - long ask
            call_credit = call_short_quote['bid'] - call_long_quote['ask']

            total_credit = put_credit + call_credit

            # Reject if total credit is below minimum viable threshold
            # $0.05 is the absolute minimum for a real IC trade to be worth executing
            min_viable_credit = 0.05
            if total_credit < min_viable_credit:
                logger.warning(
                    f"IC quote rejected: total credit ${total_credit:.2f} below minimum "
                    f"${min_viable_credit:.2f} (put=${put_credit:.2f}, call=${call_credit:.2f}). "
                    f"Skipping trade."
                )
                return None

            spread_width = signal.put_short - signal.put_long
            max_loss = spread_width - total_credit

            return {
                'put_credit': put_credit,
                'call_credit': call_credit,
                'total_credit': total_credit,
                'max_loss_per_contract': max_loss,
            }
        except Exception as e:
            logger.warning(f"IC quote error: {e}")
            return None

    def _get_position_quote(self, position: IronCondorPosition) -> Optional[Dict[str, float]]:
        """Get current quote for an open position"""
        if not self.tradier:
            return None

        try:
            put_long = self._get_option_quote(position.put_long_strike, position.expiration, "put")
            put_short = self._get_option_quote(position.put_short_strike, position.expiration, "put")
            call_short = self._get_option_quote(position.call_short_strike, position.expiration, "call")
            call_long = self._get_option_quote(position.call_long_strike, position.expiration, "call")

            if not all([put_long, put_short, call_short, call_long]):
                return None

            # To close, we buy back what we sold (ask) and sell what we bought (bid)
            put_value = put_short['ask'] - put_long['bid']  # Cost to close put spread
            call_value = call_short['ask'] - call_long['bid']  # Cost to close call spread

            return {
                'put_value': max(0, put_value),
                'call_value': max(0, call_value),
                'total_value': put_value + call_value,
            }
        except Exception as e:
            logger.warning(f"Position quote error: {e}")
            return None

    def _get_option_quote(self, strike: float, expiration: str, option_type: str) -> Optional[Dict]:
        """Get quote for a single option - with retry for network resilience"""
        if not self.tradier:
            return None

        try:
            symbol = self._build_option_symbol(strike, expiration, option_type)
            # Use retry wrapper for quote fetches
            quote = self._tradier_get_quote_with_retry(symbol)
            if quote:
                return {
                    'bid': quote.get('bid', 0),
                    'ask': quote.get('ask', 0),
                    'mid': (quote.get('bid', 0) + quote.get('ask', 0)) / 2,
                }
        except Exception:
            pass
        return None

    def _build_option_symbol(self, strike: float, expiration: str, option_type: str) -> str:
        """Build OCC option symbol"""
        ticker = self.config.ticker
        exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        exp_str = exp_date.strftime("%y%m%d")
        opt_char = "C" if option_type.lower() == "call" else "P"
        strike_str = f"{int(strike * 1000):08d}"
        return f"{ticker}{exp_str}{opt_char}{strike_str}"

    def _estimate_ic_value(self, position: IronCondorPosition, current_price: float) -> float:
        """Estimate current IC value for paper trading"""
        # Simplified estimation based on how close price is to strikes

        # If price is in the "safe zone" (between short strikes), IC is worth less
        if position.put_short_strike < current_price < position.call_short_strike:
            # Calculate how centered we are
            put_dist = (current_price - position.put_short_strike) / position.spread_width
            call_dist = (position.call_short_strike - current_price) / position.spread_width

            # IC loses value as it approaches expiration while in safe zone
            # Simple decay model: value = credit * (time_factor + proximity_factor)
            proximity_factor = min(put_dist, call_dist) / 2
            return position.total_credit * max(0.1, 0.5 - proximity_factor * 0.3)

        # If price breaches a short strike, IC gains value (loss for us)
        # BUG FIX: Removed arbitrary +0.2 buffer that caused unrealized losses to be
        # overstated vs actual settlement. Now uses pure intrinsic value.
        elif current_price <= position.put_short_strike:
            # Put side is ITM
            intrinsic = position.put_short_strike - current_price
            return min(position.spread_width, intrinsic)
        else:
            # Call side is ITM
            intrinsic = current_price - position.call_short_strike
            return min(position.spread_width, intrinsic)

    def get_position_current_value(self, position: IronCondorPosition) -> Optional[float]:
        """Get current value of an IC position"""
        if self.config.mode == TradingMode.PAPER:
            current_price = self._get_current_price()
            if current_price:
                return self._estimate_ic_value(position, current_price)
            return None
        else:
            quote = self._get_position_quote(position)
            return quote['total_value'] if quote else None
