"""
ICARUS - Main Trading Orchestrator
====================================

ICARUS is an aggressive clone of ATHENA with relaxed GEX wall filters
and trading parameters to give it more room to trade.

Key differences from ATHENA:
- 10% wall filter (vs 3%)
- 40% min win probability (vs 48%)
- 4% risk per trade (vs 2%)
- 10 max daily trades (vs 5)
- 5 max open positions (vs 3)
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

from .models import (
    SpreadPosition, PositionStatus, ICARUSConfig,
    TradingMode, DailySummary, SpreadType, CENTRAL_TZ
)
from .db import ICARUSDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

# Scan activity logging
try:
    from trading.scan_activity_logger import log_icarus_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
    print("✅ ICARUS: Scan activity logger loaded")
except ImportError as e:
    SCAN_LOGGER_AVAILABLE = False
    log_icarus_scan = None
    ScanOutcome = None
    CheckResult = None
    print(f"❌ ICARUS: Scan activity logger FAILED: {e}")

# ML Data Gatherer for comprehensive ML analysis logging
try:
    from trading.ml_data_gatherer import gather_ml_data
    ML_GATHERER_AVAILABLE = True
    print("✅ ICARUS: ML Data Gatherer loaded")
except ImportError as e:
    ML_GATHERER_AVAILABLE = False
    gather_ml_data = None
    print(f"⚠️ ICARUS: ML Data Gatherer not available: {e}")

# Oracle for outcome recording
try:
    from quant.oracle_advisor import OracleAdvisor, BotName as OracleBotName, TradeOutcome as OracleTradeOutcome
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleBotName = None
    OracleTradeOutcome = None

# Learning Memory for self-improvement tracking
try:
    from ai.gexis_learning_memory import get_learning_memory
    LEARNING_MEMORY_AVAILABLE = True
except ImportError:
    LEARNING_MEMORY_AVAILABLE = False
    get_learning_memory = None

# Math Optimizer integration
try:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerMixin = object

# Solomon Enhanced for feedback loop recording
try:
    from quant.solomon_enhancements import get_solomon_enhanced
    SOLOMON_ENHANCED_AVAILABLE = True
except ImportError:
    SOLOMON_ENHANCED_AVAILABLE = False
    get_solomon_enhanced = None

# Auto-Validation System for Thompson Sampling capital allocation
try:
    from quant.auto_validation_system import get_auto_validation_system, record_bot_outcome
    AUTO_VALIDATION_AVAILABLE = True
except ImportError:
    AUTO_VALIDATION_AVAILABLE = False
    get_auto_validation_system = None
    record_bot_outcome = None

# Market calendar for holiday checking
try:
    from trading.market_calendar import MarketCalendar
    MARKET_CALENDAR = MarketCalendar()
    MARKET_CALENDAR_AVAILABLE = True
except ImportError:
    MARKET_CALENDAR = None
    MARKET_CALENDAR_AVAILABLE = False

# Bot decision logging (for bot_decision_logs table - full audit trail)
try:
    from trading.bot_logger import (
        log_bot_decision, BotDecision, MarketContext as BotMarketContext,
        ClaudeContext, Alternative, RiskCheck, ExecutionTimeline,
        get_session_tracker, DecisionTracker
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None
    BotDecision = None


class ICARUSTrader(MathOptimizerMixin):
    """
    ICARUS - Aggressive directional spread trader.

    More aggressive than ATHENA with relaxed filters for more trading opportunities.

    Usage:
        trader = ICARUSTrader()
        result = trader.run_cycle()
    """

    def __init__(self, config: Optional[ICARUSConfig] = None):
        """Initialize ICARUS trader."""
        # Initialize database layer FIRST
        self.db = ICARUSDatabase(bot_name="ICARUS")

        # Load config from DB or use provided
        self.config = config or self.db.load_config()

        # Validate configuration at startup
        is_valid, error = self.config.validate()
        if not is_valid:
            logger.error(f"ICARUS config validation failed: {error}")
            raise ValueError(f"Invalid ICARUS configuration: {error}")

        # Initialize components
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config)

        # Learning Memory prediction tracking
        self._prediction_ids: Dict[str, str] = {}

        # Skip date functionality
        self.skip_date: Optional[datetime] = None

        # Math Optimizers DISABLED - Oracle is the sole decision maker
        if MATH_OPTIMIZER_AVAILABLE:
            self._init_math_optimizers("ICARUS", enabled=False)
            logger.info("ICARUS: Math optimizers DISABLED - Oracle controls all trading decisions")

        logger.info(
            f"ICARUS initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}, "
            f"wall_filter={self.config.wall_filter_pct}%"
        )

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        This is the MAIN entry point called by the scheduler.

        Args:
            close_only: If True, only manage existing positions (close expiring ones),
                       don't check conditions or try new entries. Used after market close.
        """
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'timestamp': now.isoformat(),
            'action': 'none',
            'trades_opened': 0,
            'trades_closed': 0,
            'realized_pnl': 0.0,
            'errors': [],
            'details': {}
        }

        scan_context = {
            'market_data': None,
            'gex_data': None,
            'signal': None,
            'checks': [],
            'oracle_data': None,
            'position': None
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}" + (" [CLOSE_ONLY]" if close_only else ""))

            # In close_only mode, skip market data fetch and conditions check
            # Just manage existing positions
            if close_only:
                logger.info("ICARUS running in CLOSE_ONLY mode - managing positions only")
                closed_count, close_pnl = self._manage_positions()
                result['trades_closed'] = closed_count
                result['realized_pnl'] = close_pnl
                result['action'] = 'close_only'
                result['details']['mode'] = 'close_only'

                if closed_count > 0:
                    self.db.log("INFO", f"CLOSE_ONLY: Closed {closed_count} positions, P&L: ${close_pnl:.2f}")
                else:
                    self.db.log("INFO", "CLOSE_ONLY: No positions to close")

                self._log_scan_activity(result, scan_context, skip_reason="Close-only mode after market")
                return result

            # CRITICAL: Fetch market data FIRST for ALL scans
            # This ensures we log comprehensive data even for skipped scans
            try:
                gex_data = self.signals.get_gex_data()
                if gex_data:
                    scan_context['market_data'] = {
                        'underlying_price': gex_data.get('spot_price', 0),
                        'symbol': self.config.ticker,
                        'vix': gex_data.get('vix', 0),
                        'expected_move': gex_data.get('expected_move', 0),
                    }
                    scan_context['gex_data'] = {
                        'regime': gex_data.get('gex_regime', 'UNKNOWN'),
                        'net_gex': gex_data.get('net_gex', 0),
                        'call_wall': gex_data.get('call_wall', 0),
                        'put_wall': gex_data.get('put_wall', 0),
                        'flip_point': gex_data.get('flip_point', 0),
                    }
                    # Also fetch Oracle advice for visibility
                    try:
                        oracle_advice = self.signals.get_oracle_advice(gex_data)
                        if oracle_advice:
                            scan_context['oracle_data'] = oracle_advice
                    except Exception as e:
                        logger.debug(f"Oracle fetch skipped: {e}")
            except Exception as e:
                logger.warning(f"Market data fetch failed: {e}")

            # Step 1: Check if we should trade
            can_trade, reason = self._check_trading_conditions(now, today)
            if not can_trade:
                result['action'] = 'skip'
                result['details']['skip_reason'] = reason
                self.db.log("INFO", f"Skipping: {reason}")
                self._log_scan_activity(result, scan_context, skip_reason=reason)
                self._log_bot_decision(result, scan_context, skip_reason=reason)
                return result

            # Step 2: Check and manage existing positions
            closed_count, close_pnl = self._manage_positions()
            result['trades_closed'] = closed_count
            result['realized_pnl'] = close_pnl

            # Step 3: Look for new entry if we have capacity
            open_positions = self.db.get_open_positions()
            if len(open_positions) < self.config.max_open_positions:
                # Pass early-fetched oracle_data to avoid double Oracle call (bug fix)
                position, signal = self._try_new_entry_with_context(oracle_data=scan_context.get('oracle_data'))
                result['trades_opened'] = 1 if position else 0
                if position:
                    result['action'] = 'opened'
                    result['details']['position'] = position.to_dict()
                    scan_context['position'] = position
                if signal:
                    scan_context['signal'] = signal
                    scan_context['market_data'] = {
                        'underlying_price': signal.spot_price,
                        'symbol': 'SPY',
                        'vix': signal.vix,
                    }
                    scan_context['gex_data'] = {
                        'regime': signal.gex_regime,
                        'call_wall': signal.call_wall,
                        'put_wall': signal.put_wall,
                    }

            if result['trades_closed'] > 0:
                result['action'] = 'closed' if result['action'] == 'none' else 'both'

            # Step 4: Update daily performance
            self._update_daily_summary(today, result)

            self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
            self._log_scan_activity(result, scan_context)
            self._log_bot_decision(result, scan_context)

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            import traceback
            traceback.print_exc()
            result['errors'].append(str(e))
            result['action'] = 'error'

            # CRITICAL: Log scan activity FIRST, before any other DB operations
            # This ensures we always have visibility into what happened, even if
            # subsequent database operations fail (which could cause silent scan stoppage)
            try:
                self._log_scan_activity(result, scan_context, error_msg=str(e))
            except Exception as log_err:
                logger.error(f"CRITICAL: Failed to log scan activity: {log_err}")

            try:
                self._log_bot_decision(result, scan_context, error_msg=str(e))
            except Exception as log_err:
                logger.error(f"Failed to log bot decision: {log_err}")

            # Then try to log to bot's own log (non-critical)
            try:
                self.db.log("ERROR", f"Cycle error: {e}")
            except Exception as db_err:
                logger.error(f"Failed to log to bot DB: {db_err}")

        return result

    def _check_trading_conditions(
        self,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """Check all conditions before trading."""
        # Weekend check
        if now.weekday() >= 5:
            return False, "Weekend"

        # Market holiday check
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            today_str = now.strftime("%Y-%m-%d")
            if not MARKET_CALENDAR.is_trading_day(today_str):
                return False, "Market holiday"

        # Skip date check
        if self.skip_date and self.skip_date == now.date():
            return False, f"Skipping by request"

        # Trading window check
        start_parts = self.config.entry_start.split(':')
        end_parts = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if now < start_time:
            return False, f"Before trading window ({self.config.entry_start})"
        if now > end_time:
            return False, f"After trading window ({self.config.entry_end})"

        # NOTE: Daily trade limit removed - Oracle decides trade frequency

        # Position limit (5 for ICARUS)
        open_count = self.db.get_position_count()
        if open_count >= self.config.max_open_positions:
            return False, f"Max positions ({self.config.max_open_positions})"

        return True, "Ready"

    def _manage_positions(self) -> tuple[int, float]:
        """Check all open positions for exit conditions."""
        positions = self.db.get_open_positions()
        closed_count = 0
        total_pnl = 0.0

        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        for pos in positions:
            should_close, reason = self._check_exit_conditions(pos, now, today)

            if should_close:
                success, close_price, pnl = self.executor.close_position(pos, reason)

                if success:
                    db_success = self.db.close_position(
                        position_id=pos.position_id,
                        close_price=close_price,
                        realized_pnl=pnl,
                        close_reason=reason
                    )
                    if not db_success:
                        logger.error(f"CRITICAL: Position {pos.position_id} closed but DB update failed!")
                    closed_count += 1
                    total_pnl += pnl

                    self._record_oracle_outcome(pos, reason, pnl)

                    # Record outcome to Solomon Enhanced for feedback loops
                    trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                    # Migration 023: Pass outcome_type, prediction_id, and direction data for feedback loop
                    outcome_type = self._determine_outcome_type(reason, pnl)
                    prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                    direction_predicted = self.db.get_direction_taken(pos.position_id)
                    direction_correct = pnl > 0  # For directional, profit = correct direction
                    self._record_solomon_outcome(pnl, trade_date, outcome_type, prediction_id, direction_predicted, direction_correct)

                    # Record outcome to Thompson Sampling for capital allocation
                    self._record_thompson_outcome(pnl)

                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            pnl,
                            reason
                        )

                    # MATH OPTIMIZER: Record outcome for Thompson Sampling (via mixin)
                    if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_record_outcome'):
                        try:
                            self.math_record_outcome(win=(pnl > 0), pnl=pnl)
                        except Exception as e:
                            logger.debug(f"Math optimizer outcome recording skipped: {e}")

                    self.db.log("INFO", f"Closed {pos.position_id}: {reason}, P&L=${pnl:.2f}")

        return closed_count, total_pnl

    def _record_oracle_outcome(self, pos: SpreadPosition, close_reason: str, pnl: float):
        """
        Record trade outcome to Oracle for ML feedback loop.

        Migration 023: Enhanced to pass prediction_id and direction_correct for
        accurate feedback loop tracking of directional strategy performance.
        """
        if not ORACLE_AVAILABLE:
            return

        try:
            oracle = OracleAdvisor()

            if pnl > 0:
                outcome = OracleTradeOutcome.MAX_PROFIT if 'PROFIT_TARGET' in close_reason else OracleTradeOutcome.PARTIAL_PROFIT
                outcome_type = 'WIN'
            else:
                outcome = OracleTradeOutcome.LOSS
                outcome_type = 'LOSS'

            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Migration 023: Get prediction_id and direction from database
            prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
            direction_predicted = self.db.get_direction_taken(pos.position_id)

            # Migration 023: Direction is correct if trade was profitable
            # For directional bots, profitability = direction prediction was correct
            direction_correct = pnl > 0

            # Record to Oracle with ICARUS's own bot name and enhanced feedback data
            success = oracle.update_outcome(
                trade_date=trade_date,
                bot_name=OracleBotName.ICARUS,
                outcome=outcome,
                actual_pnl=pnl,
                prediction_id=prediction_id,  # Migration 023: Direct linking
                outcome_type=outcome_type,  # Migration 023: Specific outcome classification
                direction_predicted=direction_predicted,  # Migration 023: BULLISH or BEARISH
                direction_correct=direction_correct,  # Migration 023: Was direction right?
            )

            if success:
                logger.info(f"ICARUS: Recorded outcome to Oracle - {outcome.value}, Dir={direction_predicted}, Correct={direction_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"ICARUS: Oracle outcome recording failed: {e}")

    def _record_solomon_outcome(
        self,
        pnl: float,
        trade_date: str,
        outcome_type: str = None,
        oracle_prediction_id: int = None,
        direction_predicted: str = None,
        direction_correct: bool = None
    ):
        """
        Record trade outcome to Solomon Enhanced for feedback loop tracking.

        Migration 023: Enhanced to pass strategy-level data for feedback loop analysis.

        This updates:
        - Consecutive loss tracking (triggers kill if threshold reached)
        - Bot performance metrics
        - Performance tracking for version comparison
        - Strategy-level analysis (Directional effectiveness)
        - Direction accuracy tracking for directional bots
        """
        if not SOLOMON_ENHANCED_AVAILABLE or not get_solomon_enhanced:
            return

        try:
            enhanced = get_solomon_enhanced()
            alerts = enhanced.record_trade_outcome(
                bot_name='ICARUS',
                pnl=pnl,
                trade_date=trade_date,
                capital_base=getattr(self.config, 'capital', 150000.0),
                # Migration 023: Enhanced feedback loop parameters
                outcome_type=outcome_type,
                strategy_type='DIRECTIONAL',  # ICARUS is a Directional bot
                oracle_prediction_id=oracle_prediction_id,
                direction_predicted=direction_predicted,  # Migration 023: BULLISH or BEARISH
                direction_correct=direction_correct  # Migration 023: Was direction prediction correct?
            )
            if alerts:
                for alert in alerts:
                    logger.warning(f"ICARUS Solomon alert: {alert}")
            logger.debug(f"ICARUS: Recorded outcome to Solomon - P&L=${pnl:.2f}, Dir={direction_predicted}, Correct={direction_correct}")
        except Exception as e:
            logger.warning(f"ICARUS: Solomon outcome recording failed: {e}")

    def _determine_outcome_type(self, close_reason: str, pnl: float) -> str:
        """
        Determine outcome type from close reason and P&L.

        Migration 023: Helper for feedback loop outcome classification.
        For directional strategies: WIN or LOSS based on P&L.

        Returns:
            str: Outcome type (WIN, LOSS)
        """
        if pnl > 0:
            return 'WIN'
        else:
            return 'LOSS'

    def _record_thompson_outcome(self, pnl: float):
        """
        Record trade outcome to Thompson Sampling for capital allocation.

        This updates the Beta distribution parameters for ICARUS,
        which affects future capital allocation across bots.
        """
        if not AUTO_VALIDATION_AVAILABLE or not record_bot_outcome:
            return

        try:
            record_bot_outcome('ICARUS', win=(pnl > 0), pnl=pnl)
            logger.debug(f"ICARUS: Recorded outcome to Thompson Sampling - P&L=${pnl:.2f}")
        except Exception as e:
            logger.warning(f"ICARUS: Thompson outcome recording failed: {e}")

    def _record_learning_memory_prediction(self, pos: SpreadPosition, signal) -> Optional[str]:
        """Record trade prediction to Learning Memory."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
            return None

        try:
            memory = get_learning_memory()

            context = {
                "gex_regime": signal.gex_regime if hasattr(signal, 'gex_regime') else "unknown",
                "vix": signal.vix if hasattr(signal, 'vix') else 20.0,
                "spot_price": signal.spot_price if hasattr(signal, 'spot_price') else 590.0,
                "direction": signal.direction if hasattr(signal, 'direction') else "unknown",
                "call_wall": signal.call_wall if hasattr(signal, 'call_wall') else 0,
                "put_wall": signal.put_wall if hasattr(signal, 'put_wall') else 0,
                "flip_point": getattr(signal, 'flip_point', 0),
                "day_of_week": datetime.now(CENTRAL_TZ).weekday(),
                "bot": "ICARUS"
            }

            prediction = f"{signal.direction if hasattr(signal, 'direction') else 'directional'} spread profitable (ICARUS)"
            prediction_id = memory.record_prediction(
                prediction_type="icarus_directional_outcome",
                prediction=prediction,
                confidence=signal.confidence if hasattr(signal, 'confidence') else 0.7,
                context=context
            )

            logger.info(f"ICARUS: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"ICARUS: Learning Memory prediction failed: {e}")
            return None

    def _record_learning_memory_outcome(self, prediction_id: str, pnl: float, close_reason: str):
        """Record trade outcome to Learning Memory."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory or not prediction_id:
            return

        try:
            memory = get_learning_memory()
            was_correct = pnl > 0

            memory.record_outcome(
                prediction_id=prediction_id,
                outcome=f"{close_reason}: ${pnl:.2f}",
                was_correct=was_correct,
                notes=f"P&L: ${pnl:.2f}, Reason: {close_reason}"
            )

            logger.info(f"ICARUS: Learning Memory outcome recorded: correct={was_correct}")

        except Exception as e:
            logger.warning(f"ICARUS: Learning Memory outcome recording failed: {e}")

    def _store_oracle_prediction(self, signal, position: SpreadPosition) -> int | None:
        """
        Store Oracle prediction to database AFTER position opens.

        Migration 023 (Option C): This is called ONLY when a position is opened,
        not during every scan. This ensures 1:1 prediction-to-position mapping.

        Returns:
            int: The oracle_prediction_id for linking, or None if storage failed
        """
        if not ORACLE_AVAILABLE:
            return None

        try:
            oracle = OracleAdvisor()

            from quant.oracle_advisor import MarketContext as OracleMarketContext, GEXRegime

            gex_regime_str = signal.gex_regime.upper() if signal.gex_regime else 'NEUTRAL'
            try:
                gex_regime = GEXRegime[gex_regime_str]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = OracleMarketContext(
                spot_price=signal.spot_price,
                vix=signal.vix,
                gex_regime=gex_regime,
                gex_call_wall=signal.call_wall,
                gex_put_wall=signal.put_wall,
                gex_flip_point=getattr(signal, 'flip_point', 0),
                gex_net=getattr(signal, 'net_gex', 0),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
            )

            from quant.oracle_advisor import OraclePrediction, TradingAdvice, BotName

            advice_str = getattr(signal, 'oracle_advice', 'TRADE_FULL')
            try:
                advice = TradingAdvice[advice_str] if advice_str else TradingAdvice.TRADE_FULL
            except (KeyError, ValueError):
                advice = TradingAdvice.TRADE_FULL

            # Get direction for directional bot tracking (Migration 023)
            direction_predicted = getattr(signal, 'direction', 'BULLISH')

            prediction = OraclePrediction(
                bot_name=BotName.ICARUS,
                advice=advice,
                win_probability=getattr(signal, 'oracle_win_probability', 0.6),
                confidence=signal.confidence,
                suggested_risk_pct=10.0,
                suggested_sd_multiplier=1.0,
                use_gex_walls=True,
                suggested_put_strike=signal.long_strike if signal.direction == 'BEARISH' else None,
                suggested_call_strike=signal.long_strike if signal.direction == 'BULLISH' else None,
                top_factors=[],
                reasoning=signal.reasoning,
                probabilities={},
            )

            # Store to database with position_id and strategy_recommendation (Migration 023)
            trade_date = position.expiration if hasattr(position, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            prediction_id = oracle.store_prediction(
                prediction,
                context,
                trade_date,
                position_id=position.position_id,  # Migration 023: Link to specific position
                strategy_recommendation='DIRECTIONAL'  # Migration 023: ICARUS uses Directional strategy
            )

            if prediction_id and isinstance(prediction_id, int):
                logger.info(f"ICARUS: Oracle prediction stored for {trade_date} (id={prediction_id}, Dir={direction_predicted}, Win Prob: {prediction.win_probability:.0%})")
                # Update position in database with the oracle_prediction_id and direction
                self.db.update_oracle_prediction_id(position.position_id, prediction_id, direction_predicted)
                return prediction_id
            elif prediction_id:  # True (backward compatibility)
                logger.info(f"ICARUS: Oracle prediction stored for {trade_date} (Win Prob: {prediction.win_probability:.0%})")
                return None
            else:
                logger.warning(f"ICARUS: Failed to store Oracle prediction for {trade_date}")
                return None

        except Exception as e:
            logger.warning(f"ICARUS: Oracle prediction storage failed: {e}")
            return None

    def _get_force_exit_time(self, now: datetime, today: str) -> datetime:
        """
        Get the effective force exit time.

        Force exit 10 minutes before market close.
        Normal market close: 3:00 PM CT (4:00 PM ET)
        """
        force_parts = self.config.force_exit.split(':')
        config_force_time = now.replace(hour=int(force_parts[0]), minute=int(force_parts[1]), second=0)

        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            close_hour, close_minute = MARKET_CALENDAR.get_market_close_time(today)
            # Early close: force exit 10 min before
            early_close_force = now.replace(hour=close_hour, minute=close_minute, second=0) - timedelta(minutes=10)

            if early_close_force < config_force_time:
                logger.info(f"ICARUS: Early close day - adjusting force exit to {early_close_force.strftime('%H:%M')}")
                return early_close_force

        return config_force_time

    def _check_exit_conditions(
        self,
        pos: SpreadPosition,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """
        Check if a position should be closed.

        Exit conditions (in priority order):
        1. FORCE_EXIT: Current time >= force exit time on expiration day
        2. EXPIRED: Position's expiration date is BEFORE today (past expiration)
        3. PROFIT_TARGET / STOP_LOSS: P&L targets

        NOTE: On expiration day, we use FORCE_EXIT (not EXPIRED) to ensure positions are
        closed at the proper time (10 min before market close), not at market open.
        """
        # Get force exit time (handles early close days)
        force_time = self._get_force_exit_time(now, today)

        # FORCE_EXIT: On expiration day, close at force exit time (10 min before market close)
        if pos.expiration == today and now >= force_time:
            return True, "FORCE_EXIT_TIME"

        # EXPIRED: Position is PAST expiration (should have been closed yesterday)
        if pos.expiration < today:
            logger.warning(f"Position {pos.position_id} is PAST expiration ({pos.expiration}) - closing immediately")
            return True, "EXPIRED"

        # Get current value with fallback handling
        current_value = self.executor.get_position_current_value(pos)
        if current_value is None:
            # PRICING FALLBACK: Don't silently block exits when pricing fails
            logger.warning(f"[ICARUS EXIT] Pricing unavailable for {pos.position_id}")

            # If we're within 30 minutes of force exit time, force close anyway
            force_time = self._get_force_exit_time(now, today)
            minutes_to_force = (force_time - now).total_seconds() / 60
            if minutes_to_force <= 30 and pos.expiration == today:
                logger.warning(f"[ICARUS EXIT] Force closing {pos.position_id} - pricing failed but {minutes_to_force:.0f}min to force exit")
                return True, "PRICING_FAILURE_NEAR_EXPIRY"

            # Log but don't block - we'll retry next cycle
            self.db.log("WARNING", f"Pricing unavailable for exit check: {pos.position_id}")
            return False, "PRICING_UNAVAILABLE"

        # Calculate current P&L percentage
        entry_cost = pos.entry_debit
        pnl_pct = ((current_value - entry_cost) / entry_cost) * 100 if entry_cost > 0 else 0

        # MATH OPTIMIZER: Use HJB for dynamic exit timing
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                current_pnl = current_value - entry_cost
                max_profit = pos.spread_width - entry_cost

                expiry_time = now.replace(hour=16, minute=0, second=0)
                entry_time = pos.open_time if hasattr(pos, 'open_time') and pos.open_time else now - timedelta(hours=2)

                hjb_result = self.math_should_exit(
                    current_pnl=current_pnl,
                    max_profit=max_profit,
                    entry_time=entry_time,
                    expiry_time=expiry_time,
                    current_volatility=0.15
                )

                if hjb_result.get('should_exit') and hjb_result.get('optimized'):
                    return True, f"HJB_OPTIMAL_{hjb_result.get('pnl_pct', 0)*100:.0f}%"

            except Exception as e:
                logger.debug(f"HJB exit check skipped: {e}")

        # ICARUS profit target (30%)
        max_profit_value = pos.spread_width
        profit_target = entry_cost + (max_profit_value - entry_cost) * (self.config.profit_target_pct / 100)
        if current_value >= profit_target:
            return True, f"PROFIT_TARGET_{self.config.profit_target_pct:.0f}%"

        # ICARUS stop loss (70%)
        stop_loss_value = entry_cost * (1 - self.config.stop_loss_pct / 100)
        if current_value <= stop_loss_value:
            return True, f"STOP_LOSS_{self.config.stop_loss_pct:.0f}%"

        return False, ""

    def _try_new_entry_with_context(self, oracle_data: dict = None) -> tuple[Optional[SpreadPosition], Optional[Any]]:
        """Try to open a new position, returning both position and signal.

        Args:
            oracle_data: Pre-fetched Oracle advice from run_cycle(). Passed to generate_signal()
                        to ensure consistency between scan logs and trade decision.
        """
        from typing import Any

        # MATH OPTIMIZER: Check regime before generating signal
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                # BUG FIX: Use get_gex_data() - get_market_snapshot doesn't exist
                market_data = self.signals.get_gex_data() if hasattr(self.signals, 'get_gex_data') else {}
                if market_data:
                    should_trade, regime_reason = self.math_should_trade_regime(market_data)
                    if not should_trade:
                        self.db.log("INFO", f"Math optimizer regime gate: {regime_reason}")
                        return None, None
            except Exception as e:
                logger.debug(f"Regime check skipped: {e}")

        # Generate signal - pass pre-fetched oracle_data to avoid double Oracle call
        signal = self.signals.generate_signal(oracle_data=oracle_data)
        if not signal:
            self.db.log("INFO", "No valid signal generated")
            return None, None

        if not signal.is_valid:
            self.db.log("INFO", f"Signal invalid: {signal.reasoning}")
            return None, signal

        # Log the signal
        self.db.log_signal(
            direction=signal.direction,
            spread_type=signal.spread_type.value,
            confidence=signal.confidence,
            spot_price=signal.spot_price,
            call_wall=signal.call_wall,
            put_wall=signal.put_wall,
            gex_regime=signal.gex_regime,
            vix=signal.vix,
            rr_ratio=signal.rr_ratio,
            was_executed=True,
            reasoning=signal.reasoning
        )

        # MATH OPTIMIZER: Get Thompson Sampling allocation weight
        thompson_weight = 1.0
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_get_allocation'):
            try:
                allocation = self.math_get_allocation()
                icarus_alloc = allocation.get('allocations', {}).get('ICARUS', 0.2)
                thompson_weight = icarus_alloc / 0.2
                logger.info(f"ICARUS Thompson weight: {thompson_weight:.2f}")
            except Exception as e:
                logger.debug(f"Thompson allocation skipped: {e}")

        # Execute the trade
        position = self.executor.execute_spread(signal, thompson_weight=thompson_weight)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database
        db_saved = self.db.save_position(position)
        if not db_saved:
            self.db.log("ERROR", "Failed to save position to DB")
            logger.error(f"CRITICAL: Position {position.position_id} executed but NOT saved!")
            import time
            time.sleep(0.5)
            db_saved = self.db.save_position(position)
            if not db_saved:
                position.db_persisted = False

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

        # Store Oracle prediction
        self._store_oracle_prediction(signal, position)

        # Record prediction to Learning Memory
        prediction_id = self._record_learning_memory_prediction(position, signal)
        if prediction_id:
            self._prediction_ids[position.position_id] = prediction_id

        return position, signal

    def _log_scan_activity(
        self,
        result: Dict,
        context: Dict,
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log scan activity for visibility and tracking"""
        if not SCAN_LOGGER_AVAILABLE or not log_icarus_scan:
            return

        try:
            if error_msg:
                outcome = ScanOutcome.ERROR
                decision = f"Error: {error_msg}"
            elif result.get('trades_opened', 0) > 0:
                outcome = ScanOutcome.TRADED
                decision = "Directional spread opened"
            elif skip_reason:
                if 'Weekend' in skip_reason or 'CLOSED' in skip_reason:
                    outcome = ScanOutcome.MARKET_CLOSED
                elif 'Before' in skip_reason:
                    outcome = ScanOutcome.BEFORE_WINDOW
                elif 'After' in skip_reason:
                    outcome = ScanOutcome.AFTER_WINDOW
                elif 'Daily limit' in skip_reason or 'Max positions' in skip_reason:
                    outcome = ScanOutcome.SKIP
                else:
                    outcome = ScanOutcome.NO_TRADE
                decision = skip_reason
            else:
                outcome = ScanOutcome.NO_TRADE
                decision = "No valid signal"

            signal = context.get('signal')
            oracle_data = context.get('oracle_data', {})
            signal_direction = ""
            signal_confidence = 0
            oracle_win_probability = 0
            oracle_confidence = 0
            oracle_advice = ""
            oracle_reasoning = ""
            oracle_top_factors = None

            # Extract signal data if available
            if signal:
                signal_direction = getattr(signal, 'direction', '')
                signal_confidence = getattr(signal, 'confidence', 0)
                oracle_win_probability = getattr(signal, 'oracle_win_probability', 0)
                oracle_confidence = getattr(signal, 'oracle_confidence', signal_confidence)

            # Extract Oracle data from context (fetched early for all scans)
            # Initialize NEUTRAL regime analysis fields
            neutral_derived_direction = ""
            neutral_confidence_val = 0
            neutral_reasoning = ""
            ic_suitability = 0
            bullish_suitability = 0
            bearish_suitability = 0
            trend_direction = ""
            trend_strength = 0
            position_in_range_pct = 50.0
            wall_filter_passed = False

            if oracle_data:
                oracle_advice = oracle_data.get('advice', oracle_data.get('recommendation', ''))
                oracle_reasoning = oracle_data.get('reasoning', oracle_data.get('full_reasoning', ''))
                oracle_win_probability = oracle_win_probability or oracle_data.get('win_probability', 0)
                oracle_confidence = oracle_confidence or oracle_data.get('confidence', 0)
                oracle_top_factors = oracle_data.get('top_factors', oracle_data.get('factors', []))
                # Extract NEUTRAL regime analysis fields
                neutral_derived_direction = oracle_data.get('neutral_derived_direction', '')
                neutral_confidence_val = oracle_data.get('neutral_confidence', 0)
                neutral_reasoning = oracle_data.get('neutral_reasoning', '')
                ic_suitability = oracle_data.get('ic_suitability', 0)
                bullish_suitability = oracle_data.get('bullish_suitability', 0)
                bearish_suitability = oracle_data.get('bearish_suitability', 0)
                trend_direction = oracle_data.get('trend_direction', '')
                trend_strength = oracle_data.get('trend_strength', 0)
                position_in_range_pct = oracle_data.get('position_in_range_pct', 50.0)
                wall_filter_passed = oracle_data.get('wall_filter_passed', False)

            # Gather comprehensive ML data for logging
            ml_kwargs = {}
            if ML_GATHERER_AVAILABLE and gather_ml_data:
                try:
                    market_data = context.get('market_data', {})
                    gex_data = context.get('gex_data', {})
                    ml_kwargs = gather_ml_data(
                        symbol=self.config.ticker,  # ICARUSConfig uses 'ticker' not 'symbol'
                        spot_price=market_data.get('spot_price', 0) if market_data else 0,
                        vix=market_data.get('vix', 0) if market_data else 0,
                        gex_data=gex_data,
                        market_data=market_data,
                        bot_name="ICARUS",
                        win_rate=0.60,  # ICARUS historical win rate
                        avg_win=180,
                        avg_loss=280,
                    )
                except Exception as ml_err:
                    logger.debug(f"ML data gathering failed (non-critical): {ml_err}")

            scan_id = log_icarus_scan(
                outcome=outcome,
                decision_summary=decision,
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                checks=context.get('checks', []),
                signal_source="ICARUS",
                signal_direction=signal_direction,
                signal_confidence=signal_confidence,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                oracle_win_probability=oracle_win_probability,
                oracle_confidence=oracle_confidence,
                oracle_top_factors=oracle_top_factors,
                min_win_probability_threshold=self.config.min_win_probability,
                trade_executed=result.get('trades_opened', 0) > 0,
                error_message=error_msg,
                # NEUTRAL Regime Analysis fields
                neutral_derived_direction=neutral_derived_direction,
                neutral_confidence=neutral_confidence_val,
                neutral_reasoning=neutral_reasoning,
                ic_suitability=ic_suitability,
                bullish_suitability=bullish_suitability,
                bearish_suitability=bearish_suitability,
                trend_direction=trend_direction,
                trend_strength=trend_strength,
                position_in_range_pct=position_in_range_pct,
                wall_filter_passed=wall_filter_passed,
                **ml_kwargs,  # Include all ML analysis data
            )
            if scan_id:
                logger.info(f"[ICARUS] Scan logged: {scan_id}")
            else:
                logger.warning("[ICARUS] Scan logging returned None - possible DB issue")
        except Exception as e:
            logger.error(f"[ICARUS] CRITICAL: Failed to log scan activity: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # FALLBACK: Try simple logging without ML kwargs
            try:
                fallback_scan_id = log_icarus_scan(
                    outcome=outcome,
                    decision_summary=f"{decision} [FALLBACK - ML data excluded]",
                    market_data=context.get('market_data'),
                    gex_data=context.get('gex_data'),
                    trade_executed=result.get('trades_opened', 0) > 0,
                    error_message=error_msg or f"Original logging failed: {str(e)[:100]}",
                )
                if fallback_scan_id:
                    logger.info(f"[ICARUS] Fallback scan logged: {fallback_scan_id}")
                else:
                    logger.error("[ICARUS] FALLBACK scan logging also failed!")
            except Exception as fallback_err:
                logger.error(f"[ICARUS] FALLBACK logging failed: {fallback_err}")

    def _log_bot_decision(
        self,
        result: Dict,
        context: Dict,
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log decision to bot_decision_logs table for full audit trail (BotLogsPage)"""
        if not BOT_LOGGER_AVAILABLE or not log_bot_decision:
            return

        try:
            signal = context.get('signal')
            position = context.get('position')
            market = context.get('market_data') or {}
            gex = context.get('gex_data') or {}

            # Determine decision type and action
            if error_msg:
                dec_type = "SKIP"
                action = "ERROR"
                reason = error_msg
            elif result.get('trades_opened', 0) > 0:
                dec_type = "ENTRY"
                action = "OPEN_SPREAD"
                reason = "Directional spread opened"
            elif skip_reason:
                dec_type = "SKIP"
                action = "SKIP"
                reason = skip_reason
            else:
                dec_type = "SKIP"
                action = "NO_TRADE"
                reason = "No valid signal"

            # Build market context
            market_ctx = BotMarketContext(
                spot_price=market.get('underlying_price', 0),
                vix=market.get('vix', 0),
                net_gex=gex.get('net_gex', 0),
                gex_regime=gex.get('regime', 'NEUTRAL'),
                flip_point=gex.get('flip_point', 0),
                call_wall=gex.get('call_wall', 0),
                put_wall=gex.get('put_wall', 0),
                trend=signal.direction if signal else "",
            )

            # Build Claude context from signal reasoning
            claude_ctx = ClaudeContext(
                prompt="",  # ICARUS doesn't use Claude prompts directly
                response=signal.reasoning if signal else reason,
                model="",
                tokens_used=0,
                response_time_ms=0,
                chain_name="",
                confidence=str(signal.confidence) if signal else "",
                warnings=[],
            )

            # Build trade details
            strike = 0
            expiration = None
            option_type = ""
            contracts = 0
            strategy = ""

            if position:
                strike = position.long_strike
                expiration = position.expiration
                option_type = "CALL" if position.spread_type == SpreadType.BULL_CALL else "PUT"
                contracts = position.contracts
                strategy = position.spread_type.value if position.spread_type else "SPREAD"

            decision = BotDecision(
                bot_name="ICARUS",
                decision_type=dec_type,
                action=action,
                symbol=self.config.ticker,
                strategy=strategy,
                strike=strike,
                expiration=expiration,
                option_type=option_type,
                contracts=contracts,
                market_context=market_ctx,
                claude_context=claude_ctx,
                entry_reasoning=signal.reasoning if signal and dec_type == "ENTRY" else "",
                strike_reasoning=f"Long: {position.long_strike}, Short: {position.short_strike}" if position else "",
                size_reasoning=f"{contracts} contracts at {self.config.risk_per_trade_pct}% risk" if position else "",
                passed_all_checks=dec_type == "ENTRY",
                blocked_reason=reason if dec_type == "SKIP" else "",
            )

            log_bot_decision(decision)
            logger.debug(f"Logged ICARUS decision: {action}")

        except Exception as e:
            logger.warning(f"Failed to log bot decision: {e}")

    def _update_daily_summary(self, today: str, cycle_result: Dict) -> None:
        """Update daily performance summary"""
        try:
            trades_today = self.db.get_daily_trades_count(today)
            open_positions = self.db.get_position_count()

            summary = DailySummary(
                date=today,
                trades_executed=trades_today,
                positions_closed=cycle_result.get('trades_closed', 0),
                realized_pnl=cycle_result.get('realized_pnl', 0),
                open_positions=open_positions,
            )

            self.db.update_daily_performance(summary)
        except Exception as e:
            logger.warning(f"Failed to update daily summary: {e}")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        positions = self.db.get_open_positions()
        daily_trades = self.db.get_daily_trades_count(today)

        # Calculate unrealized P&L (only if live pricing available)
        unrealized_pnl = 0.0
        has_live_pricing = False
        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value is not None:
                has_live_pricing = True
                pnl = (current_value - pos.entry_debit) * 100 * pos.contracts
                unrealized_pnl += pnl

        return {
            'bot_name': 'ICARUS',
            'version': 'V1',
            'mode': self.config.mode.value,
            'ticker': self.config.ticker,
            'status': 'active',
            'timestamp': now.isoformat(),
            'open_positions': len(positions),
            'max_positions': self.config.max_open_positions,
            'daily_trades': daily_trades,
            'max_daily_trades': self.config.max_daily_trades,
            'unrealized_pnl': unrealized_pnl if has_live_pricing else None,
            'has_live_pricing': has_live_pricing,
            'positions': [p.to_dict() for p in positions],
        }

    def get_positions(self) -> List[SpreadPosition]:
        """Get all open positions"""
        return self.db.get_open_positions()

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """Delegate to SignalGenerator for GEX data"""
        return self.signals.get_gex_data()

    def get_ml_signal(self, gex_data: Dict) -> Optional[Dict[str, Any]]:
        """Delegate to SignalGenerator for ML signal"""
        return self.signals.get_ml_signal(gex_data)

    def get_oracle_advice(self) -> Optional[Dict[str, Any]]:
        """Get Oracle advice with current GEX data"""
        gex_data = self.signals.get_gex_data()
        if not gex_data:
            return None
        return self.signals.get_oracle_advice(gex_data)

    def get_live_pnl(self) -> Dict[str, Any]:
        """Get live P&L for all open positions"""
        positions = self.db.get_open_positions()
        total_unrealized = 0.0
        has_live_pricing = False
        position_pnls = []

        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value is not None:
                has_live_pricing = True
                pnl = (current_value - pos.entry_debit) * 100 * pos.contracts
                total_unrealized += pnl
                position_pnls.append({
                    'position_id': pos.position_id,
                    'entry_debit': pos.entry_debit,
                    'current_value': current_value,
                    'unrealized_pnl': pnl,
                    'contracts': pos.contracts,
                })
            else:
                position_pnls.append({
                    'position_id': pos.position_id,
                    'entry_debit': pos.entry_debit,
                    'current_value': None,
                    'unrealized_pnl': None,
                    'contracts': pos.contracts,
                })

        return {
            'total_unrealized_pnl': total_unrealized if has_live_pricing else None,
            'has_live_pricing': has_live_pricing,
            'position_count': len(positions),
            'positions': position_pnls,
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
        }

    def force_close_all(self, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        """Force close all open positions"""
        positions = self.db.get_open_positions()
        results = []

        for pos in positions:
            success, close_price, pnl = self.executor.close_position(pos, reason)
            if success:
                self.db.close_position(pos.position_id, close_price, pnl, reason)
                self._record_oracle_outcome(pos, reason, pnl)
                if pos.position_id in self._prediction_ids:
                    self._record_learning_memory_outcome(
                        self._prediction_ids.pop(pos.position_id),
                        pnl,
                        reason
                    )
            results.append({
                'position_id': pos.position_id,
                'success': success,
                'pnl': pnl
            })

        return {
            'closed': len([r for r in results if r['success']]),
            'failed': len([r for r in results if not r['success']]),
            'total_pnl': sum(r['pnl'] for r in results if r['success']),
            'details': results
        }

    def process_expired_positions(self) -> Dict[str, Any]:
        """Process expired 0DTE positions at end of day."""
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'processed_count': 0,
            'total_pnl': 0.0,
            'positions': [],
            'errors': []
        }

        try:
            positions = self.db.get_open_positions()
            expired_positions = [p for p in positions if p.expiration <= today]

            if not expired_positions:
                logger.info("ICARUS EOD: No expired positions to process")
                return result

            logger.info(f"ICARUS EOD: Processing {len(expired_positions)} expired position(s)")

            for pos in expired_positions:
                try:
                    current_price = self.executor._get_current_price()
                    if not current_price:
                        current_price = pos.underlying_at_entry

                    final_pnl = self._calculate_expiration_pnl(pos, current_price)
                    close_price = (final_pnl / (100 * pos.contracts)) + pos.entry_debit if pos.contracts > 0 else 0

                    self.db.expire_position(pos.position_id, final_pnl, close_price)

                    close_reason = "EXPIRED_PROFIT" if final_pnl > 0 else "EXPIRED_LOSS"
                    self._record_oracle_outcome(pos, close_reason, final_pnl)

                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            final_pnl,
                            close_reason
                        )

                    result['processed_count'] += 1
                    result['total_pnl'] += final_pnl
                    result['positions'].append({
                        'position_id': pos.position_id,
                        'final_price': current_price,
                        'pnl': final_pnl,
                        'status': 'expired'
                    })

                    logger.info(f"ICARUS EOD: Expired {pos.position_id}, P&L: ${final_pnl:.2f}")

                except Exception as e:
                    logger.error(f"ICARUS EOD: Failed to process {pos.position_id}: {e}")
                    result['errors'].append(str(e))

            self.db.log("INFO", f"EOD processed {result['processed_count']} positions")

        except Exception as e:
            logger.error(f"ICARUS EOD processing failed: {e}")
            result['errors'].append(str(e))

        return result

    def _calculate_expiration_pnl(self, pos: SpreadPosition, final_price: float) -> float:
        """Calculate P&L at expiration based on final underlying price."""
        contracts = pos.contracts
        entry_cost = pos.entry_debit * 100 * contracts
        spread_width = pos.spread_width

        is_bullish = pos.spread_type == SpreadType.BULL_CALL

        if is_bullish:
            long_strike = pos.long_strike
            short_strike = pos.short_strike

            if final_price >= short_strike:
                spread_value = spread_width
            elif final_price <= long_strike:
                spread_value = 0
            else:
                spread_value = final_price - long_strike
        else:
            long_strike = pos.long_strike
            short_strike = pos.short_strike

            if final_price <= short_strike:
                spread_value = spread_width
            elif final_price >= long_strike:
                spread_value = 0
            else:
                spread_value = long_strike - final_price

        final_value = spread_value * 100 * contracts
        realized_pnl = final_value - entry_cost

        return realized_pnl


def run_icarus(config: Optional[ICARUSConfig] = None) -> ICARUSTrader:
    """Factory function to create and return ICARUS trader"""
    return ICARUSTrader(config)
