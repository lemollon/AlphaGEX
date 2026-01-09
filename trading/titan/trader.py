"""
TITAN - Main Trading Orchestrator
===================================

Aggressive SPX Iron Condor trading bot.
Multiple trades per day with $12 spreads and relaxed filters.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .models import (
    IronCondorPosition, PositionStatus, TITANConfig,
    TradingMode, DailySummary, CENTRAL_TZ
)
from .db import TITANDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

try:
    from trading.circuit_breaker import is_trading_enabled, record_trade_pnl
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    is_trading_enabled = None

# Scan activity logging
try:
    from trading.scan_activity_logger import log_titan_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
    print("✅ TITAN: Scan activity logger loaded")
except ImportError as e:
    SCAN_LOGGER_AVAILABLE = False
    log_titan_scan = None
    ScanOutcome = None
    CheckResult = None
    print(f"❌ TITAN: Scan activity logger FAILED: {e}")

# ML Data Gatherer for comprehensive ML analysis logging
try:
    from trading.ml_data_gatherer import gather_ml_data
    ML_GATHERER_AVAILABLE = True
    print("✅ TITAN: ML Data Gatherer loaded")
except ImportError as e:
    ML_GATHERER_AVAILABLE = False
    gather_ml_data = None
    print(f"⚠️ TITAN: ML Data Gatherer not available: {e}")

# Bot decision logging (for bot_decision_logs table)
try:
    from trading.bot_logger import (
        log_bot_decision, BotDecision, MarketContext as BotLogMarketContext,
        GEXContext, OracleContext, TradeDetails, RiskChecks, DecisionType
    )
    BOT_LOGGER_AVAILABLE = True
except ImportError:
    BOT_LOGGER_AVAILABLE = False
    log_bot_decision = None
    BotDecision = None

# Oracle for outcome recording
try:
    from quant.oracle_advisor import (
        OracleAdvisor, BotName as OracleBotName, TradeOutcome as OracleTradeOutcome,
        MarketContext as OracleMarketContext, GEXRegime, StrategyType, get_oracle
    )
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleBotName = None
    OracleTradeOutcome = None
    OracleMarketContext = None
    GEXRegime = None
    StrategyType = None
    get_oracle = None

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


class TITANTrader(MathOptimizerMixin):
    """
    TITAN - Aggressive SPX Iron Condor Trader

    Usage:
        trader = TITANTrader()
        result = trader.run_cycle()

    Key differences from PEGASUS:
    - Multiple trades per day (with cooldown)
    - Higher risk per trade (15% vs 10%)
    - Lower win probability threshold (40% vs 50%)
    - Closer strikes (0.8 SD vs 1.0 SD)
    - Faster profit taking (30% vs 50%)
    - More open positions allowed (10 vs 5)
    """

    def __init__(self, config: Optional[TITANConfig] = None):
        self.db = TITANDatabase(bot_name="TITAN")
        self.config = config or self.db.load_config()

        # Validate configuration at startup
        is_valid, error = self.config.validate()
        if not is_valid:
            logger.error(f"TITAN config validation failed: {error}")
            raise ValueError(f"Invalid TITAN configuration: {error}")

        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config, db=self.db)

        # Learning Memory prediction tracking (position_id -> prediction_id)
        self._prediction_ids: Dict[str, str] = {}

        # Initialize Math Optimizers (HMM, Thompson Sampling, HJB Exit)
        if MATH_OPTIMIZER_AVAILABLE:
            try:
                self._init_math_optimizers("TITAN", enabled=True)
                # TITAN is aggressive - allow ALL regimes except extreme gamma squeeze
                self.math_set_config('favorable_regimes', [
                    'LOW_VOLATILITY', 'MEAN_REVERTING', 'TRENDING_BULLISH',
                    'TRENDING_BEARISH', 'HIGH_VOLATILITY'
                ])
                self.math_set_config('avoid_regimes', ['GAMMA_SQUEEZE'])
                self.math_set_config('min_regime_confidence', 0.30)  # Very low threshold
                logger.info("TITAN: Math optimizers initialized - regime gate very relaxed for aggressive trading")
            except Exception as e:
                logger.warning(f"TITAN: Math optimizer init failed: {e}")

        logger.info(f"TITAN initialized: mode={self.config.mode.value}, preset={self.config.preset.value}")

    def run_cycle(self) -> Dict[str, Any]:
        """Run trading cycle - TITAN runs multiple times per day"""
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'timestamp': now.isoformat(),
            'action': 'none',
            'trade_opened': False,
            'positions_closed': 0,
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
            'oracle_data': None,
            'position': None
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}")

            # CRITICAL: Fetch market data FIRST for ALL scans
            # This ensures we log comprehensive data even for skipped scans
            try:
                gex_data = self.signals.get_gex_data() if hasattr(self, 'signals') else None
                if not gex_data and hasattr(self, 'gex_calculator'):
                    gex_data = self.gex_calculator.calculate_gex(self.config.ticker)
                if gex_data:
                    scan_context['market_data'] = {
                        'underlying_price': gex_data.get('spot_price', gex_data.get('underlying_price', 0)),
                        'symbol': self.config.ticker,
                        'vix': gex_data.get('vix', 0),
                        'expected_move': gex_data.get('expected_move', 0),
                    }
                    scan_context['gex_data'] = {
                        'regime': gex_data.get('gex_regime', gex_data.get('regime', 'UNKNOWN')),
                        'net_gex': gex_data.get('net_gex', 0),
                        'call_wall': gex_data.get('call_wall', gex_data.get('major_call_wall', 0)),
                        'put_wall': gex_data.get('put_wall', gex_data.get('major_put_wall', 0)),
                        'flip_point': gex_data.get('flip_point', gex_data.get('gamma_flip', 0)),
                    }
                    # Also fetch Oracle advice for visibility
                    try:
                        if hasattr(self, 'signals') and hasattr(self.signals, 'get_oracle_advice'):
                            oracle_advice = self.signals.get_oracle_advice(gex_data)
                            if oracle_advice:
                                scan_context['oracle_data'] = oracle_advice
                    except Exception as e:
                        logger.debug(f"Oracle fetch skipped: {e}")
            except Exception as e:
                logger.warning(f"Market data fetch failed: {e}")

            can_trade, reason = self._check_conditions(now, today)
            if not can_trade:
                result['action'] = 'skip'
                result['errors'].append(reason)
                result['details']['skip_reason'] = reason
                self.db.log("INFO", f"Skipping: {reason}")

                # Log skip to scan activity
                self._log_scan_activity(result, scan_context, skip_reason=reason)
                self._log_bot_decision(result, scan_context, skip_reason=reason)
                return result

            # Manage positions (exits)
            closed, pnl = self._manage_positions()
            result['positions_closed'] = closed
            result['realized_pnl'] = pnl

            # Try new entry (TITAN allows multiple per day)
            position, signal = self._try_entry_with_context()
            if position:
                result['trade_opened'] = True
                result['action'] = 'opened'
                result['details']['position'] = position.to_dict()
                scan_context['position'] = position
            if signal:
                scan_context['signal'] = signal
                scan_context['market_data'] = {
                    'underlying_price': signal.spot_price,
                    'symbol': 'SPX',
                    'vix': signal.vix,
                    'expected_move': signal.expected_move,
                }
                scan_context['gex_data'] = {
                    'regime': signal.gex_regime,
                    'call_wall': signal.call_wall,
                    'put_wall': signal.put_wall,
                }

            if closed > 0:
                result['action'] = 'closed' if result['action'] == 'none' else 'both'

            # Update daily performance
            self._update_daily_summary(today, result)

            self.db.update_heartbeat("IDLE", f"Complete: {result['action']}")

            # Log scan activity
            self._log_scan_activity(result, scan_context)
            self._log_bot_decision(result, scan_context)

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            result['errors'].append(str(e))
            result['action'] = 'error'

            self._log_scan_activity(result, scan_context, error_msg=str(e))
            self._log_bot_decision(result, scan_context, error_msg=str(e))

        return result

    def _check_conditions(self, now: datetime, today: str) -> tuple[bool, str]:
        if now.weekday() >= 5:
            return False, "Weekend"

        # Market holiday check
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            if not MARKET_CALENDAR.is_trading_day(today):
                return False, "Market holiday"

        start = self.config.entry_start.split(':')
        end = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start[0]), minute=int(start[1]), second=0)
        end_time = now.replace(hour=int(end[0]), minute=int(end[1]), second=0)

        if now < start_time:
            return False, f"Before {self.config.entry_start}"
        if now > end_time:
            return False, f"After {self.config.entry_end}"

        # Check position limits
        open_count = self.db.get_position_count()
        if open_count >= self.config.max_open_positions:
            return False, f"Max open positions ({self.config.max_open_positions}) reached"

        # TITAN: Check trade cooldown (time since last trade)
        last_trade = self.db.get_last_trade_time()
        if last_trade:
            cooldown = timedelta(minutes=self.config.trade_cooldown_minutes)
            if now - last_trade < cooldown:
                minutes_remaining = (cooldown - (now - last_trade)).seconds // 60
                return False, f"Cooldown: {minutes_remaining}min remaining"

        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                can, cb_reason = is_trading_enabled(self.db.get_position_count(), 0)
                if not can:
                    return False, f"Circuit breaker: {cb_reason}"
            except Exception as e:
                logger.warning(f"[TITAN] Circuit breaker check failed: {e}")

        return True, "Ready"

    def _manage_positions(self) -> tuple[int, float]:
        positions = self.db.get_open_positions()
        closed = 0
        total_pnl = 0.0

        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        for pos in positions:
            should_close, reason = self._check_exit(pos, now, today)
            if should_close:
                success, price, pnl = self.executor.close_position(pos, reason)

                # Handle partial close
                if success == 'partial_put':
                    self.db.partial_close_position(
                        position_id=pos.position_id,
                        close_price=price,
                        realized_pnl=pnl,
                        close_reason=reason,
                        closed_leg='put'
                    )
                    logger.error(
                        f"PARTIAL CLOSE: {pos.position_id} put leg closed but call failed. "
                        f"Manual intervention required."
                    )
                    total_pnl += pnl
                    continue

                if success:
                    db_success = self.db.close_position(pos.position_id, price, pnl, reason)
                    if not db_success:
                        logger.error(f"CRITICAL: Position {pos.position_id} closed but DB update failed!")
                    closed += 1
                    total_pnl += pnl

                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception as e:
                            logger.warning(f"[TITAN] Failed to record P&L to circuit breaker: {e}")

                    # Record outcome to Oracle for ML feedback
                    self._record_oracle_outcome(pos, reason, pnl)

                    # Record outcome to Learning Memory
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

        return closed, total_pnl

    def _record_oracle_outcome(self, pos: IronCondorPosition, close_reason: str, pnl: float):
        """Record trade outcome to Oracle for ML feedback loop"""
        if not ORACLE_AVAILABLE:
            return

        try:
            oracle = OracleAdvisor()

            # Determine outcome type
            if pnl > 0:
                if 'PROFIT' in close_reason or 'MAX_PROFIT' in close_reason:
                    outcome = OracleTradeOutcome.MAX_PROFIT
                else:
                    outcome = OracleTradeOutcome.PARTIAL_PROFIT
            else:
                if 'STOP_LOSS' in close_reason:
                    outcome = OracleTradeOutcome.LOSS
                elif 'CALL' in close_reason.upper() and 'BREACH' in close_reason.upper():
                    outcome = OracleTradeOutcome.CALL_BREACHED
                elif 'PUT' in close_reason.upper() and 'BREACH' in close_reason.upper():
                    outcome = OracleTradeOutcome.PUT_BREACHED
                else:
                    outcome = OracleTradeOutcome.LOSS

            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Record to Oracle using TITAN bot name
            success = oracle.update_outcome(
                trade_date=trade_date,
                bot_name=OracleBotName.TITAN if hasattr(OracleBotName, 'TITAN') else OracleBotName.PEGASUS,
                outcome=outcome,
                actual_pnl=pnl,
                put_strike=pos.put_short_strike if hasattr(pos, 'put_short_strike') else None,
                call_strike=pos.call_short_strike if hasattr(pos, 'call_short_strike') else None,
            )

            if success:
                logger.info(f"TITAN: Recorded outcome to Oracle - {outcome.value}, P&L=${pnl:.2f}")
            else:
                logger.warning(f"TITAN: Failed to record outcome to Oracle")

        except Exception as e:
            logger.warning(f"TITAN: Oracle outcome recording failed: {e}")

    def _record_learning_memory_prediction(self, pos: IronCondorPosition, signal) -> Optional[str]:
        """Record trade prediction to Learning Memory for self-improvement tracking."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory:
            return None

        try:
            memory = get_learning_memory()

            context = {
                "gex_regime": signal.gex_regime if hasattr(signal, 'gex_regime') else "unknown",
                "vix": signal.vix if hasattr(signal, 'vix') else 20.0,
                "spot_price": signal.spot_price if hasattr(signal, 'spot_price') else 5900.0,
                "call_wall": signal.call_wall if hasattr(signal, 'call_wall') else 0,
                "put_wall": signal.put_wall if hasattr(signal, 'put_wall') else 0,
                "flip_point": getattr(signal, 'flip_point', 0),
                "expected_move": signal.expected_move if hasattr(signal, 'expected_move') else 0,
                "day_of_week": datetime.now(CENTRAL_TZ).weekday(),
                "bot": "TITAN"  # Mark as TITAN prediction
            }

            prediction_id = memory.record_prediction(
                prediction_type="titan_spx_iron_condor_outcome",
                prediction=f"TITAN SPX IC profitable: {pos.put_short_strike}/{pos.call_short_strike}",
                confidence=signal.confidence if hasattr(signal, 'confidence') else 0.65,
                context=context
            )

            logger.info(f"TITAN: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"TITAN: Learning Memory prediction failed: {e}")
            return None

    def _record_learning_memory_outcome(self, prediction_id: str, pnl: float, close_reason: str):
        """Record trade outcome to Learning Memory for accuracy tracking."""
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

            logger.info(f"TITAN: Learning Memory outcome recorded: correct={was_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"TITAN: Learning Memory outcome recording failed: {e}")

    def _store_oracle_prediction(self, signal, position: IronCondorPosition):
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
                expected_move_pct=(signal.expected_move / signal.spot_price * 100) if signal.spot_price else 0,
            )

            from quant.oracle_advisor import OraclePrediction, TradingAdvice, BotName

            advice_str = getattr(signal, 'oracle_advice', 'TRADE_FULL')
            try:
                advice = TradingAdvice[advice_str] if advice_str else TradingAdvice.TRADE_FULL
            except (KeyError, ValueError):
                advice = TradingAdvice.TRADE_FULL

            prediction = OraclePrediction(
                bot_name=BotName.TITAN if hasattr(BotName, 'TITAN') else BotName.PEGASUS,
                advice=advice,
                win_probability=getattr(signal, 'oracle_win_probability', 0.65),
                confidence=signal.confidence,
                suggested_risk_pct=15.0,  # TITAN higher risk
                suggested_sd_multiplier=getattr(signal, 'oracle_suggested_sd', 0.8),
                use_gex_walls=getattr(signal, 'oracle_use_gex_walls', False),
                suggested_put_strike=signal.put_short,
                suggested_call_strike=signal.call_short,
                top_factors=[(f['factor'], f['impact']) for f in getattr(signal, 'oracle_top_factors', [])],
                reasoning=signal.reasoning,
                probabilities=getattr(signal, 'oracle_probabilities', {}),
            )

            trade_date = position.expiration if hasattr(position, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")
            success = oracle.store_prediction(prediction, context, trade_date)

            if success:
                logger.info(f"TITAN: Oracle prediction stored for {trade_date} (Win Prob: {prediction.win_probability:.0%})")
            else:
                logger.warning(f"TITAN: Failed to store Oracle prediction for {trade_date}")

        except Exception as e:
            logger.warning(f"TITAN: Oracle prediction storage failed: {e}")
            import traceback
            traceback.print_exc()

    def _get_force_exit_time(self, now: datetime, today: str) -> datetime:
        """Get the effective force exit time, accounting for early close days."""
        force = self.config.force_exit.split(':')
        config_force_time = now.replace(hour=int(force[0]), minute=int(force[1]), second=0)

        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            close_hour, close_minute = MARKET_CALENDAR.get_market_close_time(today)
            early_close_force = now.replace(hour=close_hour, minute=close_minute, second=0) - timedelta(minutes=5)

            if early_close_force < config_force_time:
                logger.info(f"TITAN: Early close day - adjusting force exit to {early_close_force.strftime('%H:%M')}")
                return early_close_force

        return config_force_time

    def _check_exit(self, pos: IronCondorPosition, now: datetime, today: str) -> tuple[bool, str]:
        try:
            today_date = datetime.strptime(today, "%Y-%m-%d").date()
            if isinstance(pos.expiration, str):
                expiration_date = datetime.strptime(pos.expiration, "%Y-%m-%d").date()
            else:
                expiration_date = pos.expiration if hasattr(pos.expiration, 'year') else datetime.strptime(str(pos.expiration), "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"Date parsing error in _check_exit: {e}")
            if pos.expiration <= today:
                return True, "EXPIRED"
            expiration_date = None
            today_date = None

        if expiration_date and today_date:
            if expiration_date <= today_date:
                return True, "EXPIRED"

            force_time = self._get_force_exit_time(now, today)
            if now >= force_time and expiration_date == today_date:
                return True, "FORCE_EXIT"
        else:
            force_time = self._get_force_exit_time(now, today)
            if now >= force_time and pos.expiration == today:
                return True, "FORCE_EXIT"

        current = self.executor.get_position_current_value(pos)
        if current is None:
            return False, ""

        # TITAN: Faster profit target (30% vs PEGASUS 50%)
        target = pos.total_credit * (1 - self.config.profit_target_pct / 100)
        if current <= target:
            return True, f"PROFIT_{self.config.profit_target_pct:.0f}%"

        # Stop loss
        if self.config.use_stop_loss:
            stop = pos.total_credit * self.config.stop_loss_multiple
            if current >= stop:
                return True, "STOP_LOSS"

        return False, ""

    def _try_entry_with_context(self) -> tuple[Optional[IronCondorPosition], Optional[Any]]:
        """Try to open a new Iron Condor, returning both position and signal for logging"""
        from typing import Any

        # MATH OPTIMIZER: Check regime before generating signal
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                market_data = self.signals.get_market_data()
                if market_data:
                    should_trade, regime_reason = self.math_should_trade_regime(market_data)
                    if not should_trade:
                        self.db.log("INFO", f"Math optimizer regime gate: {regime_reason}")
                        return None, None
            except Exception as e:
                logger.debug(f"Regime check skipped: {e}")

        signal = self.signals.generate_signal()
        if not signal:
            self.db.log("INFO", "No valid signal generated")
            return None, None

        if not signal.is_valid:
            self.db.log("INFO", f"Signal invalid: {signal.reasoning}")
            return None, signal

        # Log the signal
        self.db.log_signal(
            spot_price=signal.spot_price,
            vix=signal.vix,
            expected_move=signal.expected_move,
            call_wall=signal.call_wall,
            put_wall=signal.put_wall,
            gex_regime=signal.gex_regime,
            put_short=signal.put_short,
            put_long=signal.put_long,
            call_short=signal.call_short,
            call_long=signal.call_long,
            total_credit=signal.total_credit,
            confidence=signal.confidence,
            was_executed=True,
            reasoning=signal.reasoning,
        )

        position = self.executor.execute_iron_condor(signal)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position", {'pos_id': position.position_id})
            logger.error(f"Position {position.position_id} executed but not saved!")

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

        # Store Oracle prediction for ML feedback loop
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
        """Log scan activity for visibility"""
        if not SCAN_LOGGER_AVAILABLE or not log_titan_scan:
            return

        try:
            # Determine outcome
            if error_msg:
                outcome = ScanOutcome.ERROR
                decision = f"Error: {error_msg}"
            elif result.get('trade_opened'):
                outcome = ScanOutcome.TRADED
                decision = "TITAN SPX Iron Condor opened"
            elif skip_reason:
                if 'Weekend' in skip_reason or 'CLOSED' in skip_reason:
                    outcome = ScanOutcome.MARKET_CLOSED
                elif 'Before' in skip_reason:
                    outcome = ScanOutcome.BEFORE_WINDOW
                elif 'After' in skip_reason:
                    outcome = ScanOutcome.AFTER_WINDOW
                elif 'Cooldown' in skip_reason:
                    outcome = ScanOutcome.SKIP
                elif 'Max open positions' in skip_reason:
                    outcome = ScanOutcome.SKIP
                else:
                    outcome = ScanOutcome.NO_TRADE
                decision = skip_reason
            else:
                outcome = ScanOutcome.NO_TRADE
                decision = "No valid signal"

            signal = context.get('signal')
            oracle_data = context.get('oracle_data', {})
            signal_source = ""
            signal_confidence = 0
            oracle_advice = ""
            oracle_reasoning = ""
            oracle_win_probability = 0
            oracle_confidence = 0
            oracle_top_factors = None
            min_win_prob_threshold = self.config.min_win_probability

            # Extract Oracle data from context (fetched early for all scans)
            if oracle_data and not signal:
                oracle_advice = oracle_data.get('advice', oracle_data.get('recommendation', ''))
                oracle_reasoning = oracle_data.get('reasoning', oracle_data.get('full_reasoning', ''))
                oracle_win_probability = oracle_data.get('win_probability', 0)
                oracle_confidence = oracle_data.get('confidence', 0)
                oracle_top_factors = oracle_data.get('top_factors', oracle_data.get('factors', []))

            if signal:
                signal_source = signal.source
                signal_confidence = signal.confidence
                oracle_advice = getattr(signal, 'oracle_advice', '') or ("ENTER" if signal.is_valid else "SKIP")
                oracle_reasoning = signal.reasoning
                oracle_win_probability = getattr(signal, 'oracle_win_probability', 0)
                oracle_confidence = getattr(signal, 'oracle_confidence', signal.confidence)

                top_factors_raw = getattr(signal, 'oracle_top_factors', None)
                if top_factors_raw:
                    if isinstance(top_factors_raw, str):
                        try:
                            import json
                            oracle_top_factors = json.loads(top_factors_raw)
                        except Exception:
                            oracle_top_factors = [{'factor': 'parse_error', 'impact': 0}]
                    elif isinstance(top_factors_raw, list):
                        oracle_top_factors = top_factors_raw

            position = context.get('position')
            strike_selection = None
            contracts = 0
            premium = 0
            max_risk = 0

            if position:
                strike_selection = {
                    'put_long': position.put_long_strike,
                    'put_short': position.put_short_strike,
                    'call_short': position.call_short_strike,
                    'call_long': position.call_long_strike,
                }
                contracts = position.contracts
                premium = position.total_credit * 100 * contracts
                max_risk = position.max_loss

            # Gather comprehensive ML data for logging
            ml_kwargs = {}
            if ML_GATHERER_AVAILABLE and gather_ml_data:
                try:
                    market_data = context.get('market_data', {})
                    gex_data = context.get('gex_data', {})
                    ml_kwargs = gather_ml_data(
                        symbol="SPX",  # TITAN trades SPX
                        spot_price=market_data.get('spot_price', 0) if market_data else 0,
                        vix=market_data.get('vix', 0) if market_data else 0,
                        gex_data=gex_data,
                        market_data=market_data,
                        bot_name="TITAN",
                        win_rate=0.70,  # TITAN historical win rate
                        avg_win=250,
                        avg_loss=600,
                    )
                except Exception as ml_err:
                    logger.debug(f"ML data gathering failed (non-critical): {ml_err}")

            log_titan_scan(
                outcome=outcome,
                decision_summary=decision,
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                signal_source=signal_source,
                signal_confidence=signal_confidence,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                oracle_win_probability=oracle_win_probability,
                oracle_confidence=oracle_confidence,
                oracle_top_factors=oracle_top_factors,
                min_win_probability_threshold=min_win_prob_threshold,
                trade_executed=result.get('trade_opened', False),
                error_message=error_msg,
                generate_ai_explanation=False,
                **ml_kwargs,  # Include all ML analysis data
            )
        except Exception as e:
            logger.warning(f"Failed to log scan activity: {e}")

    def _log_bot_decision(
        self,
        result: Dict,
        context: Dict,
        decision_type: str = "SCAN",
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log decision to bot_decision_logs table for full audit trail"""
        if not BOT_LOGGER_AVAILABLE or not log_bot_decision:
            return

        try:
            signal = context.get('signal')
            position = context.get('position')
            market = context.get('market_data') or {}
            gex = context.get('gex_data') or {}

            if error_msg:
                dec_type = DecisionType.SKIP
                action = "ERROR"
                reason = error_msg
            elif result.get('trade_opened'):
                dec_type = DecisionType.ENTRY
                action = "OPEN_IC"
                reason = "TITAN SPX Iron Condor opened"
            elif skip_reason:
                dec_type = DecisionType.SKIP
                action = "SKIP"
                reason = skip_reason
            else:
                dec_type = DecisionType.SKIP
                action = "NO_TRADE"
                reason = "No valid signal"

            market_ctx = BotLogMarketContext(
                symbol="SPX",
                spot_price=market.get('underlying_price', 0),
                vix=market.get('vix', 0),
            )

            gex_ctx = GEXContext(
                regime=gex.get('regime', 'NEUTRAL'),
                call_wall=gex.get('call_wall', 0),
                put_wall=gex.get('put_wall', 0),
                net_gex=gex.get('net_gex', 0),
            )

            oracle_ctx = OracleContext(
                advice=signal.oracle_advice if signal else "",
                confidence=signal.confidence if signal else 0,
                win_probability=signal.oracle_win_probability if signal else 0,
                reasoning=signal.reasoning if signal else "",
            )

            trade_details = None
            if position:
                trade_details = TradeDetails(
                    contracts=position.contracts,
                    premium_collected=position.total_credit * 100 * position.contracts,
                    max_loss=position.max_loss,
                    expiration=position.expiration,
                )

            decision = BotDecision(
                bot_name="TITAN",
                decision_type=dec_type,
                action=action,
                symbol="SPX",
                what=f"TITAN {action}",
                why=reason,
                market_context=market_ctx,
                gex_context=gex_ctx,
                oracle_context=oracle_ctx,
                trade_details=trade_details,
            )

            log_bot_decision(decision)
            logger.debug(f"Logged TITAN decision: {action}")

        except Exception as e:
            logger.warning(f"Failed to log bot decision: {e}")

    def _update_daily_summary(self, today: str, cycle_result: Dict) -> None:
        """Update daily performance record"""
        try:
            # TITAN: Count all trades today (not just once per day)
            trades_today = self.db.get_trades_today()
            if cycle_result.get('trade_opened'):
                trades_today = max(trades_today, 1)

            summary = DailySummary(
                date=today,
                trades_executed=trades_today,
                positions_closed=cycle_result.get('positions_closed', 0),
                realized_pnl=cycle_result.get('realized_pnl', 0),
                open_positions=self.db.get_position_count(),
            )

            self.db.update_daily_performance(summary)
        except Exception as e:
            logger.warning(f"Failed to update daily summary: {e}")

    def get_status(self) -> Dict[str, Any]:
        now = datetime.now(CENTRAL_TZ)
        positions = self.db.get_open_positions()

        unrealized = 0.0
        for pos in positions:
            val = self.executor.get_position_current_value(pos)
            if val:
                unrealized += (pos.total_credit - val) * 100 * pos.contracts

        return {
            'bot_name': 'TITAN',
            'version': 'V1',
            'mode': self.config.mode.value,
            'ticker': 'SPX',
            'preset': self.config.preset.value,
            'open_positions': len(positions),
            'trades_today': self.db.get_trades_today(),
            'unrealized_pnl': unrealized,
            'timestamp': now.isoformat(),
        }

    def get_positions(self) -> List[IronCondorPosition]:
        return self.db.get_open_positions()

    def force_close_all(self, reason: str = "MANUAL") -> Dict[str, Any]:
        positions = self.db.get_open_positions()
        results = []

        for pos in positions:
            success, price, pnl = self.executor.close_position(pos, reason)
            if success:
                self.db.close_position(pos.position_id, price, pnl, reason)
                self._record_oracle_outcome(pos, reason, pnl)
                if pos.position_id in self._prediction_ids:
                    self._record_learning_memory_outcome(
                        self._prediction_ids.pop(pos.position_id),
                        pnl,
                        reason
                    )
            results.append({'position_id': pos.position_id, 'success': success, 'pnl': pnl})

        return {
            'closed': len([r for r in results if r['success']]),
            'total_pnl': sum(r['pnl'] for r in results if r['success']),
        }


def run_titan(config: Optional[TITANConfig] = None) -> TITANTrader:
    """Factory function"""
    return TITANTrader(config)
