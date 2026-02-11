"""
SOLOMON V2 - Main Trading Orchestrator
=======================================

Clean, simple orchestration of all SOLOMON components.

Design principles:
1. Single entry point for all trading operations
2. Clear flow: check -> signal -> execute -> manage
3. Database is THE source of truth
4. Minimal state in memory
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

from .models import (
    SpreadPosition, PositionStatus, SolomonConfig,
    TradingMode, DailySummary, SpreadType, CENTRAL_TZ
)
from .db import SolomonDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

# Scan activity logging
try:
    from trading.scan_activity_logger import log_solomon_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
    print("✅ SOLOMON: Scan activity logger loaded")
except ImportError as e:
    SCAN_LOGGER_AVAILABLE = False
    log_solomon_scan = None
    ScanOutcome = None
    CheckResult = None
    print(f"❌ SOLOMON: Scan activity logger FAILED: {e}")

# ML Data Gatherer for comprehensive ML analysis logging
try:
    from trading.ml_data_gatherer import gather_ml_data
    ML_GATHERER_AVAILABLE = True
    print("✅ SOLOMON: ML Data Gatherer loaded")
except ImportError as e:
    ML_GATHERER_AVAILABLE = False
    gather_ml_data = None
    print(f"⚠️ SOLOMON: ML Data Gatherer not available: {e}")

# Prophet for outcome recording
try:
    from quant.prophet_advisor import ProphetAdvisor, BotName as ProphetBotName, TradeOutcome as ProphetTradeOutcome
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None
    ProphetBotName = None
    ProphetTradeOutcome = None

# Learning Memory for self-improvement tracking
try:
    from ai.counselor_learning_memory import get_learning_memory
    LEARNING_MEMORY_AVAILABLE = True
except ImportError:
    LEARNING_MEMORY_AVAILABLE = False
    get_learning_memory = None

# Math Optimizer integration for enhanced trading decisions
try:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerMixin = object  # Fallback to empty base class

# Proverbs Enhanced for feedback loop recording
try:
    from quant.proverbs_enhancements import get_proverbs_enhanced
    PROVERBS_ENHANCED_AVAILABLE = True
except ImportError:
    PROVERBS_ENHANCED_AVAILABLE = False
    get_proverbs_enhanced = None

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


class SolomonTrader(MathOptimizerMixin):
    """
    SOLOMON V2 - Clean, modular directional spread trader.

    Usage:
        trader = SolomonTrader()
        result = trader.run_cycle()
    """

    def __init__(self, config: Optional[SolomonConfig] = None):
        """
        Initialize SOLOMON trader.

        Config is loaded from DB if not provided.
        """
        # Initialize database layer FIRST
        self.db = SolomonDatabase(bot_name="SOLOMON")

        # Load config from DB or use provided
        self.config = config or self.db.load_config()

        # Validate configuration at startup
        is_valid, error = self.config.validate()
        if not is_valid:
            logger.error(f"SOLOMON config validation failed: {error}")
            raise ValueError(f"Invalid SOLOMON configuration: {error}")

        # Initialize components
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config)

        # Learning Memory prediction tracking (position_id -> prediction_id)
        self._prediction_ids: Dict[str, str] = {}

        # Skip date functionality - set via API to skip trading for a specific day
        self.skip_date: Optional[datetime] = None

        # Math Optimizers DISABLED - Prophet is the sole decision maker
        if MATH_OPTIMIZER_AVAILABLE:
            self._init_math_optimizers("SOLOMON", enabled=False)
            logger.info("SOLOMON: Math optimizers DISABLED - Prophet controls all trading decisions")

        logger.info(
            f"SOLOMON V2 initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}"
        )

    def run_cycle(self, close_only: bool = False) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        This is the MAIN entry point called by the scheduler.

        Args:
            close_only: If True, only manage existing positions (close expiring ones),
                       don't check conditions or try new entries. Used after market close.

        Returns dict with cycle results.
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

        # Track context for scan activity logging
        scan_context = {
            'market_data': None,
            'gex_data': None,
            'signal': None,
            'checks': [],
            'prophet_data': None,
            'position': None
        }

        try:
            # Update heartbeat
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}" + (" [CLOSE_ONLY]" if close_only else ""))

            # In close_only mode, skip market data fetch and conditions check
            # Just manage existing positions
            if close_only:
                logger.info("SOLOMON running in CLOSE_ONLY mode - managing positions only")
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

            # Check Proverbs kill switch — blocks NEW entries but allows close_only
            if PROVERBS_ENHANCED_AVAILABLE and get_proverbs_enhanced:
                try:
                    enhanced = get_proverbs_enhanced()
                    if enhanced and enhanced.proverbs.is_bot_killed('SOLOMON'):
                        logger.warning("[SOLOMON] Kill switch ACTIVE — skipping cycle (no new entries)")
                        result['action'] = 'kill_switch_active'
                        self._log_scan_activity(result, scan_context, skip_reason="Kill switch active")
                        return result
                except Exception as e:
                    logger.debug(f"[SOLOMON] Kill switch check failed (fail-open): {e}")

            # CRITICAL: Fetch market data FIRST for ALL scans
            # This ensures we log comprehensive data even for skipped scans
            try:
                # Use get_market_data() which includes expected_move (required for Prophet)
                market_data = self.signals.get_market_data() if hasattr(self.signals, 'get_market_data') else None
                gex_data = self.signals.get_gex_data()

                if gex_data:
                    scan_context['market_data'] = {
                        'underlying_price': gex_data.get('spot_price', 0),
                        'symbol': self.config.ticker,
                        'vix': gex_data.get('vix', 0),
                        'expected_move': market_data.get('expected_move', 0) if market_data else 0,
                    }
                    scan_context['gex_data'] = {
                        'regime': gex_data.get('gex_regime', 'UNKNOWN'),
                        'net_gex': gex_data.get('net_gex', 0),
                        'call_wall': gex_data.get('call_wall', 0),
                        'put_wall': gex_data.get('put_wall', 0),
                        'flip_point': gex_data.get('flip_point', 0),
                    }
                    # Fetch Prophet advice using FULL market_data (includes expected_move)
                    try:
                        oracle_advice = self.signals.get_prophet_advice(market_data if market_data else gex_data)
                        if oracle_advice:
                            scan_context['prophet_data'] = oracle_advice
                    except Exception as e:
                        logger.debug(f"Prophet fetch skipped: {e}")
            except Exception as e:
                logger.warning(f"Market data fetch failed: {e}")

            # Step 1: Check if we should trade
            can_trade, reason = self._check_trading_conditions(now, today)
            if not can_trade:
                result['action'] = 'skip'
                result['details']['skip_reason'] = reason
                self.db.log("INFO", f"Skipping: {reason}")

                # Log skip to scan activity
                self._log_scan_activity(result, scan_context, skip_reason=reason)
                return result

            # Step 2: Check and manage existing positions
            closed_count, close_pnl = self._manage_positions()
            result['trades_closed'] = closed_count
            result['realized_pnl'] = close_pnl

            # Step 3: Look for new entry if we have capacity
            open_positions = self.db.get_open_positions()
            if len(open_positions) < self.config.max_open_positions:
                # Pass early-fetched prophet_data to avoid double Prophet call (bug fix)
                position, signal = self._try_new_entry_with_context(prophet_data=scan_context.get('prophet_data'))
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

            # Log scan activity
            self._log_scan_activity(result, scan_context)

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
        """
        Check all conditions before trading.

        Returns (can_trade, reason).
        """
        # Weekend check
        if now.weekday() >= 5:
            return False, "Weekend"

        # Market holiday check
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            today_str = now.strftime("%Y-%m-%d")
            if not MARKET_CALENDAR.is_trading_day(today_str):
                return False, "Market holiday"

        # Skip date check (set via API to skip trading for the day)
        if self.skip_date and self.skip_date == now.date():
            return False, f"Skipping by request (skip_date={self.skip_date.isoformat()})"

        # Trading window check
        start_parts = self.config.entry_start.split(':')
        end_parts = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if now < start_time:
            return False, f"Before trading window ({self.config.entry_start})"
        if now > end_time:
            return False, f"After trading window ({self.config.entry_end})"

        # NOTE: Daily trade limit removed - Prophet decides trade frequency

        # Position limit
        open_count = self.db.get_position_count()
        if open_count >= self.config.max_open_positions:
            return False, f"Max positions ({self.config.max_open_positions})"

        return True, "Ready"

    def _manage_positions(self) -> tuple[int, float]:
        """
        Check all open positions for exit conditions.

        Returns (positions_closed, total_pnl).
        """
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

                    # Record outcome to Prophet for ML feedback loop
                    self._record_oracle_outcome(pos, reason, pnl)

                    # Record outcome to Proverbs Enhanced for feedback loops
                    trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                    # Migration 023: Pass outcome_type, prediction_id, and direction data for feedback loop
                    outcome_type = self._determine_outcome_type(reason, pnl)
                    prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                    direction_predicted = self.db.get_direction_taken(pos.position_id)
                    direction_correct = pnl > 0  # For directional, profit = correct direction
                    self._record_proverbs_outcome(pnl, trade_date, outcome_type, prediction_id, direction_predicted, direction_correct)

                    # Record outcome to Thompson Sampling for capital allocation
                    self._record_thompson_outcome(pnl)

                    # Record outcome to Learning Memory for self-improvement
                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            pnl,
                            reason
                        )

                    # MATH OPTIMIZER: Record outcome for Thompson Sampling
                    if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_record_outcome'):
                        try:
                            self.math_record_outcome(win=(pnl > 0), pnl=pnl)
                        except Exception as e:
                            logger.debug(f"Thompson outcome recording skipped: {e}")

                    self.db.log("INFO", f"Closed {pos.position_id}: {reason}, P&L=${pnl:.2f}")

                    # Save equity snapshot after closing position (for real-time equity curve)
                    self.db.save_equity_snapshot(
                        balance=self.db.get_current_balance(),
                        realized_pnl=pnl,
                        open_positions=self.db.get_position_count(),
                        note=f"Closed {pos.position_id}: {reason}"
                    )

        return closed_count, total_pnl

    def _record_oracle_outcome(self, pos: SpreadPosition, close_reason: str, pnl: float):
        """
        Record trade outcome to Prophet for ML feedback loop.

        Migration 023: Enhanced to pass prediction_id and direction_correct for
        accurate feedback loop tracking of directional strategy performance.
        """
        if not PROPHET_AVAILABLE:
            return

        try:
            prophet = ProphetAdvisor()

            # Determine outcome type based on P&L
            # SOLOMON trades directional spreads, so it's simpler: WIN or LOSS
            if pnl > 0:
                outcome = ProphetTradeOutcome.MAX_PROFIT if 'PROFIT_TARGET' in close_reason else ProphetTradeOutcome.PARTIAL_PROFIT
                outcome_type = 'WIN'
            else:
                outcome = ProphetTradeOutcome.LOSS
                outcome_type = 'LOSS'

            # Get trade date from position
            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Migration 023: Get prediction_id and direction from database
            prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
            direction_predicted = self.db.get_direction_taken(pos.position_id)

            # Migration 023: Direction is correct if trade was profitable
            # For directional bots, profitability = direction prediction was correct
            direction_correct = pnl > 0

            # Record to Prophet using SOLOMON bot name with enhanced feedback data
            success = prophet.update_outcome(
                trade_date=trade_date,
                bot_name=ProphetBotName.SOLOMON,
                outcome=outcome,
                actual_pnl=pnl,
                prediction_id=prediction_id,  # Migration 023: Direct linking
                outcome_type=outcome_type,  # Migration 023: Specific outcome classification
                direction_predicted=direction_predicted,  # Migration 023: BULLISH or BEARISH
                direction_correct=direction_correct,  # Migration 023: Was direction right?
            )

            if success:
                logger.info(f"SOLOMON: Recorded outcome to Prophet - {outcome.value}, Dir={direction_predicted}, Correct={direction_correct}, P&L=${pnl:.2f}")
            else:
                logger.warning(f"SOLOMON: Failed to record outcome to Prophet")

        except Exception as e:
            logger.warning(f"SOLOMON: Prophet outcome recording failed: {e}")

    def _record_proverbs_outcome(
        self,
        pnl: float,
        trade_date: str,
        outcome_type: str = None,
        oracle_prediction_id: int = None,
        direction_predicted: str = None,
        direction_correct: bool = None
    ):
        """
        Record trade outcome to Proverbs Enhanced for feedback loop tracking.

        Migration 023: Enhanced to pass strategy-level data for feedback loop analysis.

        This updates:
        - Consecutive loss tracking (triggers kill if threshold reached)
        - Daily P&L monitoring (triggers kill if max loss reached)
        - Performance tracking for version comparison
        - Strategy-level analysis (Directional effectiveness)
        - Direction accuracy tracking for directional bots
        """
        if not PROVERBS_ENHANCED_AVAILABLE or not get_proverbs_enhanced:
            return

        try:
            enhanced = get_proverbs_enhanced()
            alerts = enhanced.record_trade_outcome(
                bot_name='SOLOMON',
                pnl=pnl,
                trade_date=trade_date,
                capital_base=getattr(self, 'config', {}).get('capital', 100000.0)
                if hasattr(self.config, 'get') else 100000.0,
                # Migration 023: Enhanced feedback loop parameters
                outcome_type=outcome_type,
                strategy_type='DIRECTIONAL',  # SOLOMON is a Directional bot
                oracle_prediction_id=oracle_prediction_id,
                direction_predicted=direction_predicted,  # Migration 023: BULLISH or BEARISH
                direction_correct=direction_correct  # Migration 023: Was direction prediction correct?
            )

            if alerts:
                for alert in alerts:
                    logger.warning(f"SOLOMON Proverbs Alert: {alert}")

            logger.debug(f"SOLOMON: Recorded outcome to Proverbs Enhanced - P&L=${pnl:.2f}, Dir={direction_predicted}, Correct={direction_correct}")

        except Exception as e:
            logger.warning(f"SOLOMON: Proverbs outcome recording failed: {e}")

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

        This updates the Beta distribution parameters for SOLOMON,
        which affects future capital allocation across bots.
        """
        if not AUTO_VALIDATION_AVAILABLE or not record_bot_outcome:
            return

        try:
            record_bot_outcome('SOLOMON', win=(pnl > 0), pnl=pnl)
            logger.debug(f"SOLOMON: Recorded outcome to Thompson Sampling - P&L=${pnl:.2f}")
        except Exception as e:
            logger.warning(f"SOLOMON: Thompson outcome recording failed: {e}")

    def _record_learning_memory_prediction(self, pos: SpreadPosition, signal) -> Optional[str]:
        """
        Record trade prediction to Learning Memory for self-improvement tracking.

        Returns prediction_id if recorded, None otherwise.
        """
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
            return None

        try:
            memory = get_learning_memory()

            # Build context from signal and position
            context = {
                "gex_regime": signal.gex_regime if hasattr(signal, 'gex_regime') else "unknown",
                "vix": signal.vix if hasattr(signal, 'vix') else 20.0,
                "spot_price": signal.spot_price if hasattr(signal, 'spot_price') else 590.0,
                "direction": signal.direction if hasattr(signal, 'direction') else "unknown",
                "call_wall": signal.call_wall if hasattr(signal, 'call_wall') else 0,
                "put_wall": signal.put_wall if hasattr(signal, 'put_wall') else 0,
                "flip_point": getattr(signal, 'flip_point', 0),
                "day_of_week": datetime.now(CENTRAL_TZ).weekday()
            }

            # Record directional prediction
            # Note: signal.confidence is already 0-1 from ML, not 0-100
            prediction = f"{signal.direction if hasattr(signal, 'direction') else 'directional'} spread profitable"
            prediction_id = memory.record_prediction(
                prediction_type="directional_spread_outcome",
                prediction=prediction,
                confidence=signal.confidence if hasattr(signal, 'confidence') else 0.7,
                context=context
            )

            logger.info(f"SOLOMON: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"SOLOMON: Learning Memory prediction failed: {e}")
            return None

    def _record_learning_memory_outcome(self, prediction_id: str, pnl: float, close_reason: str):
        """Record trade outcome to Learning Memory for accuracy tracking."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory or not prediction_id:
            return

        try:
            memory = get_learning_memory()

            # Determine if prediction was correct (profitable = correct)
            was_correct = pnl > 0

            memory.record_outcome(
                prediction_id=prediction_id,
                outcome=f"{close_reason}: ${pnl:.2f}",
                was_correct=was_correct,
                notes=f"P&L: ${pnl:.2f}, Reason: {close_reason}"
            )

            logger.info(f"SOLOMON: Learning Memory outcome recorded: correct={was_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"SOLOMON: Learning Memory outcome recording failed: {e}")

    def _store_oracle_prediction(self, signal, position: SpreadPosition) -> int | None:
        """
        Store Prophet prediction to database AFTER position opens.

        Migration 023 (Option C): This is called ONLY when a position is opened,
        not during every scan. This ensures 1:1 prediction-to-position mapping.

        This is CRITICAL for the ML feedback loop:
        1. store_prediction() creates the record in prophet_predictions table
        2. We link the prediction to this position via position_id
        3. After trade closes, update_outcome() updates that record with actual results
        4. Prophet uses this data for continuous model improvement

        Returns:
            int: The oracle_prediction_id for linking, or None if storage failed
        """
        if not PROPHET_AVAILABLE:
            return None

        try:
            prophet = ProphetAdvisor()

            # Build MarketContext from signal
            from quant.prophet_advisor import MarketContext as ProphetMarketContext, GEXRegime

            gex_regime_str = signal.gex_regime.upper() if signal.gex_regime else 'NEUTRAL'
            try:
                gex_regime = GEXRegime[gex_regime_str]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = ProphetMarketContext(
                spot_price=signal.spot_price,
                vix=signal.vix,
                gex_regime=gex_regime,
                gex_call_wall=signal.call_wall,
                gex_put_wall=signal.put_wall,
                gex_flip_point=getattr(signal, 'flip_point', 0),
                gex_net=getattr(signal, 'net_gex', 0),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
            )

            # Build ProphetPrediction from signal's Prophet context
            from quant.prophet_advisor import ProphetPrediction, TradingAdvice, BotName

            # Determine advice from signal
            advice_str = getattr(signal, 'oracle_advice', 'TRADE_FULL')
            try:
                advice = TradingAdvice[advice_str] if advice_str else TradingAdvice.TRADE_FULL
            except (KeyError, ValueError):
                advice = TradingAdvice.TRADE_FULL

            # Get direction for directional bot tracking (Migration 023)
            direction_predicted = getattr(signal, 'direction', 'BULLISH')

            prediction = ProphetPrediction(
                bot_name=BotName.SOLOMON,
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
            prediction_id = prophet.store_prediction(
                prediction,
                context,
                trade_date,
                position_id=position.position_id,  # Migration 023: Link to specific position
                strategy_recommendation='DIRECTIONAL'  # Migration 023: SOLOMON uses Directional strategy
            )

            if prediction_id and isinstance(prediction_id, int):
                logger.info(f"SOLOMON: Prophet prediction stored for {trade_date} (id={prediction_id}, Dir={direction_predicted}, Win Prob: {prediction.win_probability:.0%})")
                # Update position in database with the oracle_prediction_id and direction
                self.db.update_oracle_prediction_id(position.position_id, prediction_id, direction_predicted)
                return prediction_id
            elif prediction_id:  # True (backward compatibility)
                logger.info(f"SOLOMON: Prophet prediction stored for {trade_date} (Win Prob: {prediction.win_probability:.0%})")
                return None
            else:
                logger.warning(f"SOLOMON: Failed to store Prophet prediction for {trade_date}")
                return None

        except Exception as e:
            logger.warning(f"SOLOMON: Prophet prediction storage failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _store_oracle_prediction_for_scan(
        self,
        signal,
        prophet_data: Dict[str, Any],
        market_data: Dict[str, Any],
        decision: str
    ):
        """
        Store Prophet prediction to database for ALL scans (not just traded).

        This provides visibility into Prophet decisions even when no trade is executed.
        Critical for debugging "why isn't the bot trading?" scenarios.

        Args:
            signal: The generated signal (may be invalid)
            prophet_data: Prophet advice dict from get_prophet_advice()
            market_data: Market conditions at scan time
            decision: The decision made (TRADED, NO_TRADE, SKIP, etc.)
        """
        if not PROPHET_AVAILABLE:
            return

        try:
            prophet = ProphetAdvisor()
            from quant.prophet_advisor import MarketContext as ProphetMarketContext, GEXRegime
            from quant.prophet_advisor import ProphetPrediction, TradingAdvice, BotName

            # Build MarketContext
            gex_regime_str = market_data.get('gex_regime', market_data.get('regime', 'NEUTRAL'))
            if isinstance(gex_regime_str, str):
                gex_regime_str = gex_regime_str.upper()
            else:
                gex_regime_str = 'NEUTRAL'
            try:
                gex_regime = GEXRegime[gex_regime_str]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            spot_price = market_data.get('underlying_price', market_data.get('spot_price', 0))
            context = ProphetMarketContext(
                spot_price=spot_price,
                vix=market_data.get('vix', 0),
                gex_regime=gex_regime,
                gex_call_wall=market_data.get('call_wall', 0),
                gex_put_wall=market_data.get('put_wall', 0),
                gex_flip_point=market_data.get('flip_point', 0),
                gex_net=market_data.get('net_gex', 0),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
            )

            # Get advice from prophet_data or signal
            advice_str = prophet_data.get('advice', 'SKIP_TODAY') if prophet_data else 'SKIP_TODAY'
            if signal and hasattr(signal, 'oracle_advice') and signal.oracle_advice:
                advice_str = signal.oracle_advice
            try:
                advice = TradingAdvice[advice_str] if advice_str else TradingAdvice.SKIP_TODAY
            except (KeyError, ValueError):
                advice = TradingAdvice.SKIP_TODAY

            # Get win probability
            win_prob = 0
            if prophet_data:
                win_prob = prophet_data.get('win_probability', 0)
            if signal and hasattr(signal, 'oracle_win_probability') and signal.oracle_win_probability > win_prob:
                win_prob = signal.oracle_win_probability

            # Get confidence
            confidence = 0
            if prophet_data:
                confidence = prophet_data.get('confidence', 0)
            if signal and hasattr(signal, 'confidence') and signal.confidence > confidence:
                confidence = signal.confidence

            # Get top factors
            top_factors = []
            if prophet_data and prophet_data.get('top_factors'):
                factors = prophet_data['top_factors']
                if isinstance(factors, list):
                    for f in factors:
                        if isinstance(f, dict):
                            top_factors.append((f.get('factor', 'unknown'), f.get('impact', 0)))
                        elif isinstance(f, tuple):
                            top_factors.append(f)

            # Build reasoning
            reasoning = f"Decision: {decision}"
            if prophet_data and prophet_data.get('reasoning'):
                reasoning = prophet_data['reasoning']
            if signal and signal.reasoning:
                reasoning = signal.reasoning

            prediction = ProphetPrediction(
                bot_name=BotName.SOLOMON,
                advice=advice,
                win_probability=win_prob,
                confidence=confidence,
                suggested_risk_pct=prophet_data.get('suggested_risk_pct', 0) if prophet_data else 0,
                suggested_sd_multiplier=1.0,
                use_gex_walls=True,
                suggested_put_strike=signal.long_strike if signal and signal.direction == 'BEARISH' else None,
                suggested_call_strike=signal.long_strike if signal and signal.direction == 'BULLISH' else None,
                top_factors=top_factors,
                reasoning=reasoning,
                probabilities=prophet_data.get('probabilities', {}) if prophet_data else {},
            )

            # Store to database - use today's date for non-traded scans
            trade_date = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            success = prophet.store_prediction(prediction, context, trade_date)

            if success:
                logger.debug(f"SOLOMON: Prophet scan prediction stored (Win Prob: {win_prob:.0%}, Decision: {decision})")
            else:
                logger.debug(f"SOLOMON: Prophet scan prediction storage returned False")

        except Exception as e:
            logger.debug(f"SOLOMON: Prophet scan prediction storage skipped: {e}")

    def _get_force_exit_time(self, now: datetime, today: str) -> datetime:
        """
        Get the effective force exit time, accounting for early close days.

        On early close days (Christmas Eve, day after Thanksgiving), market closes at 12:00 PM CT.
        We should force exit 5 minutes before market close instead of using the normal config.
        """
        # Default force exit from config
        force_parts = self.config.force_exit.split(':')
        config_force_time = now.replace(hour=int(force_parts[0]), minute=int(force_parts[1]), second=0)

        # Check if today is an early close day
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            close_hour, close_minute = MARKET_CALENDAR.get_market_close_time(today)
            # Early close: force exit 10 min before market close
            early_close_force = now.replace(hour=close_hour, minute=close_minute, second=0) - timedelta(minutes=10)

            # Use the earlier of config time and early close time
            if early_close_force < config_force_time:
                logger.info(f"SOLOMON: Early close day - adjusting force exit from {self.config.force_exit} to {early_close_force.strftime('%H:%M')}")
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
            logger.warning(f"[SOLOMON EXIT] Pricing unavailable for {pos.position_id}")

            # If we're within 30 minutes of force exit time, force close anyway
            force_time = self._get_force_exit_time(now, today)
            minutes_to_force = (force_time - now).total_seconds() / 60
            if minutes_to_force <= 30 and pos.expiration == today:
                logger.warning(f"[SOLOMON EXIT] Force closing {pos.position_id} - pricing failed but {minutes_to_force:.0f}min to force exit")
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
                # Field is 'open_time' not 'entry_time'
                entry_time = pos.open_time if hasattr(pos, 'open_time') and pos.open_time else now - timedelta(hours=2)

                hjb_result = self.math_should_exit(
                    current_pnl=current_pnl,
                    max_profit=max_profit,
                    entry_time=entry_time,
                    expiry_time=expiry_time,
                    current_volatility=0.15
                )

                if hjb_result.get('should_exit') and hjb_result.get('optimized'):
                    reason = hjb_result.get('reason', 'HJB_OPTIMAL_EXIT')
                    self.db.log("INFO", f"HJB exit signal: {reason}")
                    return True, f"HJB_OPTIMAL_{hjb_result.get('pnl_pct', 0)*100:.0f}%"

            except Exception as e:
                logger.debug(f"HJB exit check skipped: {e}")

        # Fallback: Standard profit target (50% of max profit)
        max_profit_value = pos.spread_width  # Max value at expiration
        profit_target = entry_cost + (max_profit_value - entry_cost) * (self.config.profit_target_pct / 100)
        if current_value >= profit_target:
            return True, f"PROFIT_TARGET_{self.config.profit_target_pct:.0f}%"

        # Stop loss (50% of max loss)
        stop_loss_value = entry_cost * (1 - self.config.stop_loss_pct / 100)
        if current_value <= stop_loss_value:
            return True, f"STOP_LOSS_{self.config.stop_loss_pct:.0f}%"

        return False, ""

    def _try_new_entry_with_context(self, prophet_data: dict = None) -> tuple[Optional[SpreadPosition], Optional[Any]]:
        """
        Try to open a new position, returning both position and signal for logging.

        Args:
            prophet_data: Pre-fetched Prophet advice from run_cycle(). Passed to generate_signal()
                        to ensure consistency between scan logs and trade decision.

        Returns (SpreadPosition, Signal) tuple.
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

        # Generate signal - pass pre-fetched prophet_data to avoid double Prophet call
        signal = self.signals.generate_signal(prophet_data=prophet_data)
        if not signal:
            self.db.log("INFO", "No valid signal generated")
            return None, None

        if not signal.is_valid:
            self.db.log("INFO", f"Signal invalid: {signal.reasoning}")
            return None, signal  # Return signal for logging even if invalid

        # MATH OPTIMIZER: Smooth Greeks if available
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                if hasattr(signal, 'greeks') and signal.greeks:
                    smoothed = self.math_smooth_greeks(signal.greeks)
                    logger.debug(f"SOLOMON: Smoothed Greeks applied")
            except Exception as e:
                logger.debug(f"Greeks smoothing skipped: {e}")

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
        thompson_weight = 1.0  # Default neutral weight
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_get_allocation'):
            try:
                allocation = self.math_get_allocation()
                # Convert allocation percentage to weight (20% baseline = 1.0)
                # So 30% = 1.5x, 10% = 0.5x
                solomon_alloc = allocation.get('allocations', {}).get('SOLOMON', 0.2)
                thompson_weight = solomon_alloc / 0.2  # Normalize to 20% baseline
                logger.info(f"SOLOMON Thompson weight: {thompson_weight:.2f} (allocation: {solomon_alloc:.1%})")
            except Exception as e:
                logger.debug(f"Thompson allocation skipped: {e}")

        # Execute the trade with Thompson-adjusted position sizing
        position = self.executor.execute_spread(signal, thompson_weight=thompson_weight)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database - CRITICAL for position tracking
        db_saved = self.db.save_position(position)
        if not db_saved:
            self.db.log("ERROR", "Failed to save position to DB", {'pos_id': position.position_id})
            logger.error(
                f"CRITICAL: Position {position.position_id} executed but NOT saved to DB! "
                f"Position will NOT be managed (no stop loss, no expiration handling). "
                f"Manual intervention required."
            )
            # Attempt one retry after brief pause
            import time
            time.sleep(0.5)
            db_saved = self.db.save_position(position)
            if db_saved:
                logger.info(f"Position {position.position_id} saved to DB on retry")
            else:
                logger.error(f"CRITICAL: Position {position.position_id} DB save retry failed!")
                # Mark the position as not persisted for caller awareness
                position.db_persisted = False

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

        # Save equity snapshot after opening position (for real-time equity curve)
        self.db.save_equity_snapshot(
            balance=self.db.get_current_balance(),
            realized_pnl=0,
            open_positions=self.db.get_position_count(),
            note=f"Opened {position.position_id}"
        )

        # CRITICAL: Store Prophet prediction for ML feedback loop
        # This enables update_outcome to find and update the prediction record
        self._store_oracle_prediction(signal, position)

        # Record prediction to Learning Memory for self-improvement tracking
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
        print(f"[SOLOMON DEBUG] _log_scan_activity called at {datetime.now(CENTRAL_TZ).strftime('%I:%M:%S %p CT')}")
        if not SCAN_LOGGER_AVAILABLE or not log_solomon_scan:
            print(f"[SOLOMON DEBUG] Scan logging SKIPPED: SCAN_LOGGER_AVAILABLE={SCAN_LOGGER_AVAILABLE}, log_solomon_scan={log_solomon_scan is not None}")
            logger.warning(f"[SOLOMON] Scan logging SKIPPED: SCAN_LOGGER_AVAILABLE={SCAN_LOGGER_AVAILABLE}, log_solomon_scan={log_solomon_scan is not None}")
            return
        print(f"[SOLOMON DEBUG] Proceeding with scan logging...")

        try:
            # Determine outcome
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

            # Build signal context with FULL Prophet data for frontend visibility
            signal = context.get('signal')
            prophet_data = context.get('prophet_data', {})
            signal_direction = ""
            signal_confidence = 0
            signal_win_probability = 0
            oracle_advice = ""
            oracle_reasoning = ""
            oracle_win_probability = 0
            oracle_confidence = 0
            oracle_top_factors = None
            oracle_probabilities = None
            oracle_suggested_strikes = None
            oracle_thresholds = None
            min_win_prob_threshold = self.config.min_win_probability

            # ALWAYS set thresholds - this should never be 0
            oracle_thresholds = {
                'min_win_probability': min_win_prob_threshold,
                'wall_distance_threshold': getattr(self.config, 'wall_distance_threshold', 0.01),
            }

            # Extract Prophet data from context FIRST (fetched early for all scans)
            # This ensures we always have Prophet data even if signal doesn't have it
            # Initialize NEUTRAL regime analysis fields
            neutral_derived_direction = ""
            neutral_confidence = 0
            neutral_reasoning = ""
            ic_suitability = 0
            bullish_suitability = 0
            bearish_suitability = 0
            trend_direction = ""
            trend_strength = 0
            position_in_range_pct = 50.0
            wall_filter_passed = False

            if prophet_data:
                oracle_advice = prophet_data.get('advice', prophet_data.get('recommendation', ''))
                oracle_reasoning = prophet_data.get('reasoning', prophet_data.get('full_reasoning', ''))
                oracle_win_probability = prophet_data.get('win_probability', 0)
                oracle_confidence = prophet_data.get('confidence', 0)
                oracle_top_factors = prophet_data.get('top_factors', prophet_data.get('factors', []))
                # Extract NEUTRAL regime analysis fields
                neutral_derived_direction = prophet_data.get('neutral_derived_direction', '')
                neutral_confidence = prophet_data.get('neutral_confidence', 0)
                neutral_reasoning = prophet_data.get('neutral_reasoning', '')
                ic_suitability = prophet_data.get('ic_suitability', 0)
                bullish_suitability = prophet_data.get('bullish_suitability', 0)
                bearish_suitability = prophet_data.get('bearish_suitability', 0)
                trend_direction = prophet_data.get('trend_direction', '')
                trend_strength = prophet_data.get('trend_strength', 0)
                position_in_range_pct = prophet_data.get('position_in_range_pct', 50.0)
                wall_filter_passed = prophet_data.get('wall_filter_passed', False)

            # If we have a signal, use signal data (but don't override Prophet data with zeros)
            if signal:
                signal_direction = signal.direction
                signal_confidence = signal.confidence
                signal_win_probability = getattr(signal, 'ml_win_probability', 0)

                # Only override Prophet data if signal has it (don't replace with zeros)
                signal_oracle_advice = getattr(signal, 'oracle_advice', '')
                if signal_oracle_advice:
                    oracle_advice = signal_oracle_advice
                elif not oracle_advice:
                    oracle_advice = "ENTER" if signal.is_valid else "SKIP"

                if signal.reasoning:
                    oracle_reasoning = signal.reasoning

                # Only override win probability if signal has a non-zero value
                signal_oracle_wp = getattr(signal, 'oracle_win_probability', 0)
                if signal_oracle_wp > 0:
                    oracle_win_probability = signal_oracle_wp

                signal_oracle_conf = getattr(signal, 'oracle_confidence', 0)
                if signal_oracle_conf > 0:
                    oracle_confidence = signal_oracle_conf
                elif oracle_confidence == 0:
                    oracle_confidence = signal.confidence

                # Get top factors (may be JSON string or list) - only if signal has them
                top_factors_raw = getattr(signal, 'oracle_top_factors', None)
                if top_factors_raw:
                    if isinstance(top_factors_raw, str):
                        try:
                            import json
                            oracle_top_factors = json.loads(top_factors_raw)
                        except Exception:
                            pass  # Keep existing oracle_top_factors
                    elif isinstance(top_factors_raw, list):
                        oracle_top_factors = top_factors_raw

            # Build trade details if position opened
            position = context.get('position')

            # Gather comprehensive ML data for logging
            ml_kwargs = {}
            if ML_GATHERER_AVAILABLE and gather_ml_data:
                try:
                    market_data = context.get('market_data', {})
                    gex_data = context.get('gex_data', {})
                    ml_kwargs = gather_ml_data(
                        symbol=self.config.ticker,  # SolomonConfig uses 'ticker' not 'symbol'
                        spot_price=market_data.get('spot_price', 0) if market_data else 0,
                        vix=market_data.get('vix', 0) if market_data else 0,
                        gex_data=gex_data,
                        market_data=market_data,
                        bot_name="SOLOMON",
                        win_rate=0.65,  # SOLOMON historical win rate
                        avg_win=200,
                        avg_loss=300,
                    )
                except Exception as ml_err:
                    logger.debug(f"ML data gathering failed (non-critical): {ml_err}")

            scan_id = log_solomon_scan(
                outcome=outcome,
                decision_summary=decision,
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                checks=context.get('checks', []),
                signal_source="SOLOMON_V2",
                signal_direction=signal_direction,
                signal_confidence=signal_confidence,
                signal_win_probability=signal_win_probability,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                oracle_win_probability=oracle_win_probability,
                oracle_confidence=oracle_confidence,
                oracle_top_factors=oracle_top_factors,
                oracle_probabilities=oracle_probabilities,
                oracle_suggested_strikes=oracle_suggested_strikes,
                oracle_thresholds=oracle_thresholds,
                min_win_probability_threshold=min_win_prob_threshold,
                trade_executed=result.get('trades_opened', 0) > 0,
                error_message=error_msg,
                generate_ai_explanation=False,  # Keep it simple
                # NEUTRAL Regime Analysis fields
                neutral_derived_direction=neutral_derived_direction,
                neutral_confidence=neutral_confidence,
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
                print(f"[SOLOMON DEBUG] ✅ Scan logged successfully: {scan_id}")
                logger.info(f"[SOLOMON] Scan logged: {scan_id}")
            else:
                print(f"[SOLOMON DEBUG] ❌ Scan logging returned None - check database!")
                logger.warning("[SOLOMON] Scan logging returned None - possible DB issue")

            # Migration 023 (Option C): NO LONGER store Prophet predictions for non-traded scans.
            # Predictions are ONLY stored when a position is actually opened.
            # This ensures 1:1 prediction-to-position mapping for accurate feedback loop.
            # Scan activity is still logged to solomon_scan_activity for debugging visibility.
            # (Removed call to _store_oracle_prediction_for_scan)

        except Exception as e:
            print(f"[SOLOMON DEBUG] ❌ EXCEPTION in _log_scan_activity: {e}")
            import traceback
            print(traceback.format_exc())
            logger.error(f"[SOLOMON] CRITICAL: Failed to log scan activity: {e}")
            logger.error(traceback.format_exc())
            # FALLBACK: Try simple logging without ML kwargs
            try:
                fallback_scan_id = log_solomon_scan(
                    outcome=outcome,
                    decision_summary=f"{decision} [FALLBACK - ML data excluded]",
                    market_data=context.get('market_data'),
                    gex_data=context.get('gex_data'),
                    trade_executed=result.get('trades_opened', 0) > 0,
                    error_message=error_msg or f"Original logging failed: {str(e)[:100]}",
                    generate_ai_explanation=False,
                )
                if fallback_scan_id:
                    logger.info(f"[SOLOMON] Fallback scan logged: {fallback_scan_id}")
                else:
                    logger.error("[SOLOMON] FALLBACK scan logging also failed!")
            except Exception as fallback_err:
                logger.error(f"[SOLOMON] FALLBACK logging failed: {fallback_err}")

    def _update_daily_summary(self, today: str, cycle_result: Dict) -> None:
        """Update daily performance summary"""
        try:
            # Get current daily stats
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
            'bot_name': 'SOLOMON',
            'version': 'V2',
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

    def get_prophet_advice(self) -> Optional[Dict[str, Any]]:
        """Get Prophet advice with current GEX data"""
        gex_data = self.signals.get_gex_data()
        if not gex_data:
            return None
        return self.signals.get_prophet_advice(gex_data)

    def get_live_pnl(self) -> Dict[str, Any]:
        """Get live P&L for all open positions"""
        positions = self.db.get_open_positions()
        total_unrealized = 0.0
        position_pnls = []

        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value:
                pnl = (current_value - pos.entry_debit) * 100 * pos.contracts
                total_unrealized += pnl
                position_pnls.append({
                    'position_id': pos.position_id,
                    'entry_debit': pos.entry_debit,
                    'current_value': current_value,
                    'unrealized_pnl': pnl,
                    'contracts': pos.contracts,
                })

        return {
            'total_unrealized_pnl': total_unrealized,
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
                db_success = self.db.close_position(
                    pos.position_id, close_price, pnl, reason
                )
                if not db_success:
                    logger.error(f"CRITICAL: Failed to close {pos.position_id} in database! P&L ${pnl:.2f} not recorded.")
                # Record outcome to Prophet for ML feedback
                self._record_oracle_outcome(pos, reason, pnl)
                # Record outcome to Proverbs Enhanced for feedback loops
                trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                # Migration 023: Pass outcome_type, prediction_id, and direction data for feedback loop
                outcome_type = self._determine_outcome_type(reason, pnl)
                prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                direction_predicted = self.db.get_direction_taken(pos.position_id)
                direction_correct = pnl > 0  # For directional, profit = correct direction
                self._record_proverbs_outcome(pnl, trade_date, outcome_type, prediction_id, direction_predicted, direction_correct)
                # Record outcome to Thompson Sampling for capital allocation
                self._record_thompson_outcome(pnl)
                # Record outcome to Learning Memory for self-improvement
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
        """
        Process expired 0DTE positions at end of day.

        Called by scheduler at 3:00 PM CT to handle positions that expired
        during the trading day. For directional spreads:
        - Bull Call Spread: max profit if price >= long strike
        - Bear Put Spread: max profit if price <= long strike
        - Otherwise: calculate value based on final price

        Returns dict with processing results for logging.
        """
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'processed_count': 0,
            'total_pnl': 0.0,
            'positions': [],
            'errors': []
        }

        try:
            # Get all open positions expiring today or earlier
            positions = self.db.get_open_positions()
            expired_positions = [p for p in positions if p.expiration <= today]

            if not expired_positions:
                logger.info("SOLOMON EOD: No expired positions to process")
                return result

            logger.info(f"SOLOMON EOD: Processing {len(expired_positions)} expired position(s)")

            for pos in expired_positions:
                try:
                    # Get final underlying price for P&L calculation
                    current_price = self.executor._get_current_price()
                    if not current_price:
                        current_price = pos.underlying_at_entry
                        logger.warning(f"Could not get current price, using entry: ${current_price}")

                    # Calculate final P&L based on where price ended
                    final_pnl = self._calculate_expiration_pnl(pos, current_price)

                    # Calculate estimated close price (spread value at expiration)
                    # This is the intrinsic value the spread expired with
                    close_price = (final_pnl / (100 * pos.contracts)) + pos.entry_debit if pos.contracts > 0 else 0

                    # Mark position as expired in database with close price for audit trail
                    db_success = self.db.expire_position(pos.position_id, final_pnl, close_price)
                    if not db_success:
                        logger.error(f"CRITICAL: Failed to expire {pos.position_id} in database! P&L ${final_pnl:.2f} not recorded.")
                        result['errors'].append(f"DB update failed for {pos.position_id}")

                    # Record outcome for ML feedback
                    close_reason = "EXPIRED_PROFIT" if final_pnl > 0 else "EXPIRED_LOSS"
                    self._record_oracle_outcome(pos, close_reason, final_pnl)

                    # Record outcome to Proverbs Enhanced for feedback loops
                    trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
                    # Migration 023: Pass outcome_type, prediction_id, and direction data for feedback loop
                    outcome_type = self._determine_outcome_type(close_reason, final_pnl)
                    prediction_id = self.db.get_oracle_prediction_id(pos.position_id)
                    direction_predicted = self.db.get_direction_taken(pos.position_id)
                    direction_correct = final_pnl > 0  # For directional, profit = correct direction
                    self._record_proverbs_outcome(final_pnl, trade_date, outcome_type, prediction_id, direction_predicted, direction_correct)

                    # Record outcome to Thompson Sampling for capital allocation
                    self._record_thompson_outcome(final_pnl)

                    # Record to Learning Memory
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

                    logger.info(
                        f"SOLOMON EOD: Expired {pos.position_id} - "
                        f"Final price: ${current_price:.2f}, P&L: ${final_pnl:.2f}"
                    )

                except Exception as e:
                    logger.error(f"SOLOMON EOD: Failed to process {pos.position_id}: {e}")
                    result['errors'].append(str(e))

            self.db.log("INFO", f"EOD processed {result['processed_count']} positions, P&L: ${result['total_pnl']:.2f}")

        except Exception as e:
            logger.error(f"SOLOMON EOD processing failed: {e}")
            result['errors'].append(str(e))

        return result

    def _calculate_expiration_pnl(self, pos: SpreadPosition, final_price: float) -> float:
        """
        Calculate P&L at expiration based on final underlying price.

        For directional debit spreads:
        - Bull Call Spread: Long lower strike call, short higher strike call
          - Max profit when price >= long strike + spread_width
          - Max loss when price <= long strike
        - Bear Put Spread: Long higher strike put, short lower strike put
          - Max profit when price <= long strike - spread_width
          - Max loss when price >= long strike
        """
        contracts = pos.contracts
        entry_cost = pos.entry_debit * 100 * contracts  # Total cost paid
        spread_width = pos.spread_width  # Max value the spread can reach

        # Determine spread type from spread_type enum
        is_bullish = pos.spread_type == SpreadType.BULL_CALL

        if is_bullish:
            # Bull Call Spread: long_strike is lower, short_strike is higher
            # Value at expiration depends on where price is relative to strikes
            long_strike = pos.long_strike
            short_strike = pos.short_strike

            if final_price >= short_strike:
                # Max profit: spread is worth full width
                spread_value = spread_width
            elif final_price <= long_strike:
                # Max loss: spread is worthless
                spread_value = 0
            else:
                # Partial value: spread is worth (price - long_strike)
                spread_value = final_price - long_strike
        else:
            # Bear Put Spread: long_strike is higher, short_strike is lower
            long_strike = pos.long_strike
            short_strike = pos.short_strike

            if final_price <= short_strike:
                # Max profit: spread is worth full width
                spread_value = spread_width
            elif final_price >= long_strike:
                # Max loss: spread is worthless
                spread_value = 0
            else:
                # Partial value: spread is worth (long_strike - price)
                spread_value = long_strike - final_price

        # P&L = spread value at expiration - entry cost
        final_value = spread_value * 100 * contracts
        realized_pnl = final_value - entry_cost

        return realized_pnl


def run_solomon_v2(config: Optional[SolomonConfig] = None) -> SolomonTrader:
    """Factory function to create and return SOLOMON trader"""
    return SolomonTrader(config)
