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

# Circuit breaker import
try:
    from trading.circuit_breaker import is_trading_enabled, record_trade_pnl
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    is_trading_enabled = None

# Scan activity logging
try:
    from trading.scan_activity_logger import log_icarus_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_icarus_scan = None
    ScanOutcome = None
    CheckResult = None

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

        # Initialize Math Optimizers
        if MATH_OPTIMIZER_AVAILABLE:
            self._init_math_optimizers("ICARUS", enabled=True)
            # ICARUS is aggressive - allow trading in most regimes
            self.math_set_config('favorable_regimes', [
                'TRENDING_BULLISH', 'TRENDING_BEARISH', 'MEAN_REVERTING',
                'LOW_VOLATILITY', 'HIGH_VOLATILITY'
            ])
            self.math_set_config('avoid_regimes', ['GAMMA_SQUEEZE'])
            self.math_set_config('min_regime_confidence', 0.35)  # Even lower for aggressive
            logger.info("ICARUS: Math optimizers enabled - aggressive regime gate")

        logger.info(
            f"ICARUS initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}, "
            f"wall_filter={self.config.wall_filter_pct}%"
        )

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        This is the MAIN entry point called by the scheduler.
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
            'position': None
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}")

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
                position, signal = self._try_new_entry_with_context()
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
            self.db.log("ERROR", f"Cycle error: {e}")
            self._log_scan_activity(result, scan_context, error_msg=str(e))
            self._log_bot_decision(result, scan_context, error_msg=str(e))

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

        # Daily trade limit (10 for ICARUS)
        daily_trades = self.db.get_daily_trades_count(today)
        if daily_trades >= self.config.max_daily_trades:
            return False, f"Daily limit reached ({self.config.max_daily_trades})"

        # Position limit (5 for ICARUS)
        open_count = self.db.get_position_count()
        if open_count >= self.config.max_open_positions:
            return False, f"Max positions ({self.config.max_open_positions})"

        # Circuit breaker
        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                can_trade, cb_reason = is_trading_enabled(
                    current_positions=open_count,
                    margin_used=0
                )
                if not can_trade:
                    return False, f"Circuit breaker: {cb_reason}"
            except Exception as e:
                logger.warning(f"Circuit breaker check failed: {e}")

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

                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            pnl,
                            reason
                        )

                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception as e:
                            logger.warning(f"[ICARUS] Failed to record P&L to circuit breaker: {e}")

                    if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_record_outcome'):
                        try:
                            self.math_record_outcome(win=(pnl > 0), pnl=pnl)
                        except Exception as e:
                            logger.debug(f"Thompson outcome recording skipped: {e}")

                    self.db.log("INFO", f"Closed {pos.position_id}: {reason}, P&L=${pnl:.2f}")

        return closed_count, total_pnl

    def _record_oracle_outcome(self, pos: SpreadPosition, close_reason: str, pnl: float):
        """Record trade outcome to Oracle for ML feedback loop"""
        if not ORACLE_AVAILABLE:
            return

        try:
            oracle = OracleAdvisor()

            if pnl > 0:
                outcome = OracleTradeOutcome.MAX_PROFIT if 'PROFIT_TARGET' in close_reason else OracleTradeOutcome.PARTIAL_PROFIT
            else:
                outcome = OracleTradeOutcome.LOSS

            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Record to Oracle - use ATHENA bot name since ICARUS uses same model
            # Note: In future could add ICARUS to OracleBotName enum
            success = oracle.update_outcome(
                trade_date=trade_date,
                bot_name=OracleBotName.ATHENA,  # Uses ATHENA model
                outcome=outcome,
                actual_pnl=pnl,
            )

            if success:
                logger.info(f"ICARUS: Recorded outcome to Oracle - {outcome.value}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"ICARUS: Oracle outcome recording failed: {e}")

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

    def _store_oracle_prediction(self, signal, position: SpreadPosition):
        """Store Oracle prediction to database BEFORE trade execution."""
        if not ORACLE_AVAILABLE:
            return

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

            prediction = OraclePrediction(
                bot_name=BotName.ATHENA,  # Uses ATHENA model
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

            trade_date = position.expiration if hasattr(position, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            success = oracle.store_prediction(prediction, context, trade_date)

            if success:
                logger.info(f"ICARUS: Oracle prediction stored for {trade_date}")

        except Exception as e:
            logger.warning(f"ICARUS: Oracle prediction storage failed: {e}")

    def _get_force_exit_time(self, now: datetime, today: str) -> datetime:
        """Get the effective force exit time."""
        force_parts = self.config.force_exit.split(':')
        config_force_time = now.replace(hour=int(force_parts[0]), minute=int(force_parts[1]), second=0)

        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            close_hour, close_minute = MARKET_CALENDAR.get_market_close_time(today)
            early_close_force = now.replace(hour=close_hour, minute=close_minute, second=0) - timedelta(minutes=5)

            if early_close_force < config_force_time:
                logger.info(f"ICARUS: Early close day - adjusting force exit")
                return early_close_force

        return config_force_time

    def _check_exit_conditions(
        self,
        pos: SpreadPosition,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """Check if a position should be closed."""
        # Expiration check
        if pos.expiration <= today:
            return True, "EXPIRED"

        # Force exit time check
        force_time = self._get_force_exit_time(now, today)
        if now >= force_time and pos.expiration == today:
            return True, "FORCE_EXIT_TIME"

        # Get current value
        current_value = self.executor.get_position_current_value(pos)
        if current_value is None:
            return False, ""

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

    def _try_new_entry_with_context(self) -> tuple[Optional[SpreadPosition], Optional[Any]]:
        """Try to open a new position, returning both position and signal."""
        from typing import Any

        # MATH OPTIMIZER: Check regime before generating signal
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                market_data = self.signals.get_market_snapshot() if hasattr(self.signals, 'get_market_snapshot') else {}
                if market_data:
                    should_trade, regime_reason = self.math_should_trade_regime(market_data)
                    if not should_trade:
                        self.db.log("INFO", f"Math optimizer regime gate: {regime_reason}")
                        return None, None
            except Exception as e:
                logger.debug(f"Regime check skipped: {e}")

        # Generate signal
        signal = self.signals.generate_signal()
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
            signal_direction = ""
            signal_confidence = 0
            oracle_win_probability = 0
            oracle_confidence = 0

            if signal:
                signal_direction = signal.direction
                signal_confidence = signal.confidence
                oracle_win_probability = getattr(signal, 'oracle_win_probability', 0)
                oracle_confidence = getattr(signal, 'oracle_confidence', signal.confidence)

            log_icarus_scan(
                outcome=outcome,
                decision_summary=decision,
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                checks=context.get('checks', []),
                signal_source="ICARUS",
                signal_direction=signal_direction,
                signal_confidence=signal_confidence,
                oracle_win_probability=oracle_win_probability,
                oracle_confidence=oracle_confidence,
                min_win_probability_threshold=self.config.min_win_probability,
                trade_executed=result.get('trades_opened', 0) > 0,
                error_message=error_msg,
            )
        except Exception as e:
            logger.warning(f"Failed to log scan activity: {e}")

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

        unrealized_pnl = 0.0
        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value:
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
            'unrealized_pnl': unrealized_pnl,
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
