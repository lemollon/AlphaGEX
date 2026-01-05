"""
ARES V2 - Main Trading Orchestrator
=====================================

Clean, simple orchestration for Iron Condor trading.

ARES trades SPY Iron Condors:
- One trade per day (0DTE)
- Bull Put + Bear Call spread
- GEX-protected or SD-based strikes
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

from .models import (
    IronCondorPosition, PositionStatus, ARESConfig,
    TradingMode, DailySummary, CENTRAL_TZ
)
from .db import ARESDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

# Circuit breaker
try:
    from trading.circuit_breaker import is_trading_enabled, record_trade_pnl
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    is_trading_enabled = None

# Market calendar for holiday checking
try:
    from trading.market_calendar import MarketCalendar
    MARKET_CALENDAR = MarketCalendar()
    MARKET_CALENDAR_AVAILABLE = True
except ImportError:
    MARKET_CALENDAR = None
    MARKET_CALENDAR_AVAILABLE = False

# Scan activity logging
try:
    from trading.scan_activity_logger import log_ares_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_ares_scan = None
    ScanOutcome = None
    CheckResult = None

# Oracle for outcome recording and strategy recommendations
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

# Math Optimizer integration for enhanced trading decisions
try:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerMixin = object  # Fallback to empty base class


class ARESTrader(MathOptimizerMixin):
    """
    ARES V2 - Clean, modular Iron Condor trader for SPY.

    Usage:
        trader = ARESTrader()
        result = trader.run_cycle()
    """

    def __init__(self, config: Optional[ARESConfig] = None):
        """Initialize ARES trader"""
        # Database layer FIRST
        self.db = ARESDatabase(bot_name="ARES")

        # Load config from DB or use provided
        self.config = config or self.db.load_config()

        # Validate configuration at startup
        is_valid, error = self.config.validate()
        if not is_valid:
            logger.error(f"ARES config validation failed: {error}")
            raise ValueError(f"Invalid ARES configuration: {error}")

        # Initialize components
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config, db=self.db)

        # Learning Memory prediction tracking (position_id -> prediction_id)
        self._prediction_ids: Dict[str, str] = {}

        # Initialize Math Optimizers (HMM, Kalman, Thompson, Convex, HJB, MDP)
        if MATH_OPTIMIZER_AVAILABLE:
            self._init_math_optimizers("ARES", enabled=True)
            logger.info("ARES: Math optimizers enabled (HMM, Kalman, Thompson, Convex, HJB, MDP)")

        logger.info(
            f"ARES V2 initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}, preset={self.config.preset.value}"
        )

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        ARES can trade up to max_trades_per_day (default: 3).
        Allows re-entry after a position closes profitably.
        This method is called by the scheduler every 5 minutes.
        """
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
            'position': None
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}")

            # Step 1: ALWAYS check and manage existing positions FIRST
            # This ensures we monitor positions even if we can't open new ones
            closed_count, close_pnl = self._manage_positions()
            result['positions_closed'] = closed_count
            result['realized_pnl'] = close_pnl

            if closed_count > 0:
                result['action'] = 'closed'
                self.db.log("INFO", f"Closed {closed_count} position(s), P&L: ${close_pnl:.2f}")

            # Step 2: Check basic trading conditions (time window, weekend, circuit breaker)
            can_trade, reason = self._check_basic_conditions(now)
            if not can_trade:
                if result['action'] == 'none':
                    result['action'] = 'skip'
                result['details']['skip_reason'] = reason
                self.db.log("INFO", f"Entry skipped: {reason}")
                self._log_scan_activity(result, scan_context, reason)
                self._update_daily_summary(today, result)
                self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
                return result

            # Step 3: Check daily trade limit (max 3 trades per day)
            trades_today = self.db.get_trades_today_count(today)
            max_trades = getattr(self.config, 'max_trades_per_day', 3)
            open_positions = self.db.get_position_count()

            if trades_today >= max_trades:
                if result['action'] == 'none':
                    result['action'] = 'monitoring'
                result['details']['skip_reason'] = f'Daily limit reached ({trades_today}/{max_trades} trades)'
                self.db.log("DEBUG", f"Daily trade limit reached: {trades_today}/{max_trades}")
                self._log_scan_activity(result, scan_context, result['details']['skip_reason'])
                self._update_daily_summary(today, result)
                self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
                return result

            # Step 4: Check if we already have an open position (only 1 at a time)
            if open_positions > 0:
                if result['action'] == 'none':
                    result['action'] = 'monitoring'
                result['details']['skip_reason'] = f'Position already open ({open_positions})'
                self.db.log("DEBUG", f"Already have {open_positions} open position(s)")
                self._log_scan_activity(result, scan_context, result['details']['skip_reason'])
                self._update_daily_summary(today, result)
                self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
                return result

            # Step 5: Check Oracle strategy recommendation
            strategy_rec = self._check_strategy_recommendation()
            if strategy_rec:
                scan_context['strategy_recommendation'] = {
                    'recommended': strategy_rec.recommended_strategy.value if hasattr(strategy_rec, 'recommended_strategy') else 'IRON_CONDOR',
                    'vix_regime': strategy_rec.vix_regime.value if hasattr(strategy_rec, 'vix_regime') else 'NORMAL',
                    'ic_suitability': strategy_rec.ic_suitability if hasattr(strategy_rec, 'ic_suitability') else 1.0,
                    'reasoning': strategy_rec.reasoning if hasattr(strategy_rec, 'reasoning') else ''
                }

                if hasattr(strategy_rec, 'recommended_strategy'):
                    if strategy_rec.recommended_strategy == StrategyType.SKIP:
                        if result['action'] == 'none':
                            result['action'] = 'skip'
                        result['details']['skip_reason'] = f"Oracle recommends SKIP: {strategy_rec.reasoning}"
                        self.db.log("INFO", f"Oracle SKIP: {strategy_rec.reasoning}")
                        self._log_scan_activity(result, scan_context, result['details']['skip_reason'])
                        self._update_daily_summary(today, result)
                        self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
                        return result
                    elif strategy_rec.recommended_strategy == StrategyType.DIRECTIONAL:
                        self.db.log("INFO", f"Oracle suggests ATHENA: {strategy_rec.reasoning}")
                        result['details']['oracle_suggests_athena'] = True
                        if strategy_rec.ic_suitability < 0.4:
                            if result['action'] == 'none':
                                result['action'] = 'skip'
                            result['details']['skip_reason'] = f"IC suitability too low ({strategy_rec.ic_suitability:.0%})"
                            self._log_scan_activity(result, scan_context, result['details']['skip_reason'])
                            self._update_daily_summary(today, result)
                            self.db.update_heartbeat("IDLE", f"Cycle complete: {result['action']}")
                            return result

            # Step 6: Try to open new position
            position, signal = self._try_new_entry_with_context()
            if position:
                result['trade_opened'] = True
                result['action'] = 'opened' if result['action'] == 'none' else 'both'
                result['details']['position'] = position.to_dict()
                result['details']['trade_number'] = trades_today + 1
                scan_context['position'] = position
                self.db.log("INFO", f"Opened trade #{trades_today + 1} of {max_trades} today")
            if signal:
                scan_context['signal'] = signal
                scan_context['market_data'] = {
                    'underlying_price': signal.spot_price,
                    'symbol': 'SPY',
                    'vix': signal.vix,
                    'expected_move': signal.expected_move,
                }
                scan_context['gex_data'] = {
                    'regime': signal.gex_regime,
                    'call_wall': signal.call_wall,
                    'put_wall': signal.put_wall,
                }

            # Step 7: Update daily summary
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
            self.db.log("ERROR", f"Cycle error: {e}")

            # Log error to scan activity
            self._log_scan_activity(result, scan_context, error_msg=str(e))

        return result

    def _log_scan_activity(
        self,
        result: Dict,
        context: Dict,
        skip_reason: str = "",
        error_msg: str = ""
    ):
        """Log scan activity for visibility"""
        if not SCAN_LOGGER_AVAILABLE or not log_ares_scan:
            return

        try:
            # Determine outcome
            if error_msg:
                outcome = ScanOutcome.ERROR
                decision = f"Error: {error_msg}"
            elif result.get('trade_opened'):
                outcome = ScanOutcome.TRADED
                decision = "Iron Condor opened"
            elif skip_reason:
                if 'Weekend' in skip_reason or 'CLOSED' in skip_reason:
                    outcome = ScanOutcome.MARKET_CLOSED
                elif 'Before' in skip_reason:
                    outcome = ScanOutcome.BEFORE_WINDOW
                elif 'After' in skip_reason:
                    outcome = ScanOutcome.AFTER_WINDOW
                elif 'Already traded' in skip_reason:
                    outcome = ScanOutcome.SKIP
                else:
                    outcome = ScanOutcome.NO_TRADE
                decision = skip_reason
            else:
                outcome = ScanOutcome.NO_TRADE
                decision = "No valid signal"

            # Build signal context
            signal = context.get('signal')
            signal_source = ""
            signal_confidence = 0
            oracle_advice = ""
            oracle_reasoning = ""

            if signal:
                signal_source = signal.source
                signal_confidence = signal.confidence
                oracle_advice = "ENTER" if signal.is_valid else "SKIP"
                oracle_reasoning = signal.reasoning

            # Build trade details if position opened
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

            log_ares_scan(
                outcome=outcome,
                decision_summary=decision,
                action_taken=result.get('action', 'none'),
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                signal_source=signal_source,
                signal_confidence=signal_confidence,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                trade_executed=result.get('trade_opened', False),
                position_id=position.position_id if position else "",
                strike_selection=strike_selection,
                contracts=contracts,
                premium_collected=premium,
                max_risk=max_risk,
                error_message=error_msg,
                generate_ai_explanation=False,  # Keep it simple for now
            )
        except Exception as e:
            logger.warning(f"Failed to log scan activity: {e}")

    def _check_basic_conditions(self, now: datetime) -> tuple[bool, str]:
        """Check basic trading conditions (time window, weekend, holidays, circuit breaker)"""
        # Weekend check
        if now.weekday() >= 5:
            return False, "Weekend"

        # Market holiday check
        if MARKET_CALENDAR_AVAILABLE and MARKET_CALENDAR:
            today_str = now.strftime("%Y-%m-%d")
            if not MARKET_CALENDAR.is_trading_day(today_str):
                return False, "Market holiday"

        # Trading window
        start_parts = self.config.entry_start.split(':')
        end_parts = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if now < start_time:
            return False, f"Before trading window ({self.config.entry_start})"
        if now > end_time:
            return False, f"After trading window ({self.config.entry_end})"

        # Circuit breaker
        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                open_count = self.db.get_position_count()
                can_trade, cb_reason = is_trading_enabled(
                    current_positions=open_count,
                    margin_used=0
                )
                if not can_trade:
                    return False, f"Circuit breaker: {cb_reason}"
            except Exception as e:
                logger.warning(f"Circuit breaker check failed: {e}")

        return True, "Ready"

    def _check_strategy_recommendation(self):
        """
        Check Oracle for strategy recommendation.

        Oracle determines if current conditions favor:
        - IRON_CONDOR: Price will stay pinned (good for ARES)
        - DIRECTIONAL: Price will move (better for ATHENA)
        - SKIP: Too risky to trade

        Returns:
            StrategyRecommendation or None if Oracle unavailable
        """
        if not ORACLE_AVAILABLE or not get_oracle:
            return None

        try:
            oracle = get_oracle()

            # Get current market data
            try:
                from core_classes_and_engines import TradingVolatilityAPI
                api = TradingVolatilityAPI()
                gex_data = api.get_gex_levels('SPY')

                spot_price = gex_data.get('spot_price', 590)
                vix = gex_data.get('vix', 20)
                gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL')
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)
                flip_point = gex_data.get('flip_point', 0)
                net_gex = gex_data.get('net_gex', 0)
            except Exception as e:
                logger.warning(f"Could not fetch market data for strategy check: {e}")
                # Use defaults - let ARES proceed
                return None

            # Convert GEX regime string to enum
            try:
                gex_regime = GEXRegime[gex_regime_str.upper()]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            # Build market context
            context = OracleMarketContext(
                spot_price=spot_price,
                vix=vix,
                gex_regime=gex_regime,
                gex_call_wall=call_wall,
                gex_put_wall=put_wall,
                gex_flip_point=flip_point,
                gex_net=net_gex,
                day_of_week=datetime.now(CENTRAL_TZ).weekday()
            )

            # Get strategy recommendation
            recommendation = oracle.get_strategy_recommendation(context)

            logger.info(
                f"Oracle strategy rec: {recommendation.recommended_strategy.value}, "
                f"VIX regime: {recommendation.vix_regime.value}, "
                f"IC suitability: {recommendation.ic_suitability:.0%}"
            )

            return recommendation

        except Exception as e:
            logger.warning(f"Oracle strategy check failed: {e}")
            return None

    def _manage_positions(self) -> tuple[int, float]:
        """Check open positions for exit conditions"""
        positions = self.db.get_open_positions()
        closed_count = 0
        total_pnl = 0.0

        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        for pos in positions:
            should_close, reason = self._check_exit_conditions(pos, now, today)

            if should_close:
                success, close_price, pnl = self.executor.close_position(pos, reason)

                # Handle partial close (put closed but call failed)
                if success == 'partial_put':
                    self.db.partial_close_position(
                        position_id=pos.position_id,
                        close_price=close_price,
                        realized_pnl=pnl,
                        close_reason=reason,
                        closed_leg='put'
                    )
                    logger.error(
                        f"PARTIAL CLOSE: {pos.position_id} put leg closed but call failed. "
                        f"Manual intervention required to close call spread."
                    )
                    # Don't count as fully closed, but track the partial P&L
                    total_pnl += pnl
                    continue

                if success:
                    db_success = self.db.close_position(
                        position_id=pos.position_id,
                        close_price=close_price,
                        realized_pnl=pnl,
                        close_reason=reason
                    )
                    if not db_success:
                        logger.error(f"CRITICAL: Position {pos.position_id} closed in Tradier but DB update failed!")
                        # Still count it as closed since Tradier position is closed
                    closed_count += 1
                    total_pnl += pnl

                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception:
                            pass

                    # Record outcome to Oracle for ML feedback loop
                    self._record_oracle_outcome(pos, reason, pnl)

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

        return closed_count, total_pnl

    def _record_oracle_outcome(self, pos: IronCondorPosition, close_reason: str, pnl: float):
        """Record trade outcome to Oracle for ML feedback loop"""
        if not ORACLE_AVAILABLE:
            return

        try:
            oracle = OracleAdvisor()

            # Determine outcome type based on close reason and P&L
            if pnl > 0:
                if 'PROFIT_TARGET' in close_reason or 'MAX_PROFIT' in close_reason:
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

            # Get trade date from position
            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Record to Oracle
            success = oracle.update_outcome(
                trade_date=trade_date,
                bot_name=OracleBotName.ARES,
                outcome=outcome,
                actual_pnl=pnl,
                put_strike=pos.put_short_strike if hasattr(pos, 'put_short_strike') else None,
                call_strike=pos.call_short_strike if hasattr(pos, 'call_short_strike') else None,
            )

            if success:
                logger.info(f"ARES: Recorded outcome to Oracle - {outcome.value}, P&L=${pnl:.2f}")
            else:
                logger.warning(f"ARES: Failed to record outcome to Oracle")

        except Exception as e:
            logger.warning(f"ARES: Oracle outcome recording failed: {e}")

    def _record_learning_memory_prediction(self, pos: IronCondorPosition, signal) -> Optional[str]:
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
                "call_wall": signal.call_wall if hasattr(signal, 'call_wall') else 0,
                "put_wall": signal.put_wall if hasattr(signal, 'put_wall') else 0,
                "flip_point": getattr(signal, 'flip_point', 0),
                "expected_move": signal.expected_move if hasattr(signal, 'expected_move') else 0,
                "day_of_week": datetime.now(CENTRAL_TZ).weekday()
            }

            # Record prediction: IC will be profitable (price stays within wings)
            # Note: signal.confidence is already 0-1 from Oracle, not 0-100
            prediction_id = memory.record_prediction(
                prediction_type="iron_condor_outcome",
                prediction=f"IC profitable: {pos.put_short_strike}/{pos.call_short_strike}",
                confidence=signal.confidence if hasattr(signal, 'confidence') else 0.7,
                context=context
            )

            logger.info(f"ARES: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"ARES: Learning Memory prediction failed: {e}")
            return None

    def _record_learning_memory_outcome(self, prediction_id: str, pnl: float, close_reason: str):
        """Record trade outcome to Learning Memory for accuracy tracking."""
        if not LEARNING_MEMORY_AVAILABLE or not get_learning_memory or not prediction_id:
            return

        try:
            memory = get_learning_memory()

            # Determine if prediction was correct (profitable = correct for IC)
            was_correct = pnl > 0

            memory.record_outcome(
                prediction_id=prediction_id,
                outcome=f"{close_reason}: ${pnl:.2f}",
                was_correct=was_correct,
                notes=f"P&L: ${pnl:.2f}, Reason: {close_reason}"
            )

            logger.info(f"ARES: Learning Memory outcome recorded: correct={was_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"ARES: Learning Memory outcome recording failed: {e}")

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
            # Early close: 12:00 PM CT - force exit at 11:55 AM CT
            early_close_force = now.replace(hour=close_hour, minute=close_minute, second=0) - timedelta(minutes=5)

            # Use the earlier of config time and early close time
            if early_close_force < config_force_time:
                logger.info(f"ARES: Early close day - adjusting force exit from {self.config.force_exit} to {early_close_force.strftime('%H:%M')}")
                return early_close_force

        return config_force_time

    def _check_exit_conditions(
        self,
        pos: IronCondorPosition,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """Check if IC should be closed"""
        # Expiration check
        if pos.expiration <= today:
            return True, "EXPIRED"

        # Force exit time (handles early close days)
        force_time = self._get_force_exit_time(now, today)
        if now >= force_time and pos.expiration == today:
            return True, "FORCE_EXIT_TIME"

        # Get current value
        current_value = self.executor.get_position_current_value(pos)
        if current_value is None:
            return False, ""

        # MATH OPTIMIZER: Use HJB for dynamic exit timing
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                # Calculate current P&L
                current_pnl = pos.total_credit - current_value
                max_profit = pos.total_credit

                # Get expiry time (end of day)
                expiry_time = now.replace(hour=16, minute=0, second=0)  # Market close

                # Get entry time from position (field is 'open_time' not 'entry_time')
                entry_time = pos.open_time if hasattr(pos, 'open_time') and pos.open_time else now - timedelta(hours=2)

                # Check HJB exit signal
                hjb_result = self.math_should_exit(
                    current_pnl=current_pnl,
                    max_profit=max_profit,
                    entry_time=entry_time,
                    expiry_time=expiry_time,
                    current_volatility=0.15  # Could get from VIX
                )

                if hjb_result.get('should_exit') and hjb_result.get('optimized'):
                    # Use reason from HJB if available and non-empty, otherwise construct one
                    raw_reason = hjb_result.get('reason', '')
                    pnl_pct = hjb_result.get('pnl_pct', 0)
                    reason = raw_reason if raw_reason else f"HJB_OPTIMAL_{pnl_pct*100:.0f}%"
                    self.db.log("INFO", f"HJB exit signal: {reason}")
                    return True, reason

            except Exception as e:
                logger.debug(f"HJB exit check skipped: {e}")

        # Fallback: Standard profit target (50% of credit received)
        profit_target_value = pos.total_credit * (1 - self.config.profit_target_pct / 100)
        if current_value <= profit_target_value:
            return True, f"PROFIT_TARGET_{self.config.profit_target_pct:.0f}%"

        # Stop loss (if enabled)
        if self.config.use_stop_loss:
            stop_loss_value = pos.total_credit * self.config.stop_loss_multiple
            if current_value >= stop_loss_value:
                return True, f"STOP_LOSS_{self.config.stop_loss_multiple}X"

        return False, ""

    def _try_new_entry(self) -> Optional[IronCondorPosition]:
        """Try to open a new Iron Condor"""
        position, _ = self._try_new_entry_with_context()
        return position

    def _try_new_entry_with_context(self) -> tuple[Optional[IronCondorPosition], Optional[Any]]:
        """Try to open a new Iron Condor, returning both position and signal for logging"""
        from .signals import IronCondorSignal

        # MATH OPTIMIZER: Check regime before generating signal
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            # Get market data for regime check (VIX from signal generator)
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
            return None, signal  # Return signal for logging even if invalid

        # MATH OPTIMIZER: Smooth Greeks if available
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                if hasattr(signal, 'greeks') and signal.greeks:
                    smoothed = self.math_smooth_greeks(signal.greeks)
                    logger.debug(f"ARES: Smoothed Greeks applied")
            except Exception as e:
                logger.debug(f"Greeks smoothing skipped: {e}")

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

        # MATH OPTIMIZER: Get Thompson Sampling allocation weight
        thompson_weight = 1.0  # Default neutral weight
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, 'math_get_allocation'):
            try:
                allocation = self.math_get_allocation()
                # Convert allocation percentage to weight (20% baseline = 1.0)
                # So 30% = 1.5x, 10% = 0.5x
                ares_alloc = allocation.get('allocations', {}).get('ARES', 0.2)
                thompson_weight = ares_alloc / 0.2  # Normalize to 20% baseline
                logger.info(f"ARES Thompson weight: {thompson_weight:.2f} (allocation: {ares_alloc:.1%})")
            except Exception as e:
                logger.debug(f"Thompson allocation skipped: {e}")

        # Execute the trade with Thompson-adjusted position sizing
        position = self.executor.execute_iron_condor(signal, thompson_weight=thompson_weight)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database - CRITICAL: Only return position if save succeeds
        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position to database", {'pos_id': position.position_id})
            logger.error(f"Position {position.position_id} executed but not saved to database!")
            # Return None to indicate trade did NOT complete successfully
            # This prevents scan activity from showing "TRADED" when position isn't persisted
            return None, signal

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

        # Record prediction to Learning Memory for self-improvement tracking
        prediction_id = self._record_learning_memory_prediction(position, signal)
        if prediction_id:
            self._prediction_ids[position.position_id] = prediction_id

        return position, signal

    def _update_daily_summary(self, today: str, cycle_result: Dict) -> None:
        """Update daily performance"""
        try:
            traded = 1 if cycle_result.get('trade_opened') else 0
            if self.db.has_traded_today(today):
                traded = 1

            summary = DailySummary(
                date=today,
                trades_executed=traded,
                positions_closed=cycle_result.get('positions_closed', 0),
                realized_pnl=cycle_result.get('realized_pnl', 0),
                open_positions=self.db.get_position_count(),
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
        has_traded = self.db.has_traded_today(today)

        # Calculate unrealized P&L
        unrealized_pnl = 0.0
        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value:
                pnl = (pos.total_credit - current_value) * 100 * pos.contracts
                unrealized_pnl += pnl

        return {
            'bot_name': 'ARES',
            'version': 'V2',
            'mode': self.config.mode.value,
            'ticker': self.config.ticker,
            'preset': self.config.preset.value,
            'status': 'active',
            'timestamp': now.isoformat(),
            'open_positions': len(positions),
            'traded_today': has_traded,
            'unrealized_pnl': unrealized_pnl,
            'positions': [p.to_dict() for p in positions],
        }

    def get_positions(self) -> List[IronCondorPosition]:
        """Get all open positions"""
        return self.db.get_open_positions()

    def force_close_all(self, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        """Force close all open positions"""
        positions = self.db.get_open_positions()
        results = []

        for pos in positions:
            success, close_price, pnl = self.executor.close_position(pos, reason)

            # Handle partial close (put closed but call failed)
            if success == 'partial_put':
                self.db.partial_close_position(
                    position_id=pos.position_id,
                    close_price=close_price,
                    realized_pnl=pnl,
                    close_reason=reason,
                    closed_leg='put'
                )
                results.append({
                    'position_id': pos.position_id,
                    'success': 'partial',
                    'pnl': pnl,
                    'note': 'Put leg closed, call leg requires manual close'
                })
                continue

            if success:
                self.db.close_position(pos.position_id, close_price, pnl, reason)
                # Record outcome to Oracle for ML feedback
                self._record_oracle_outcome(pos, reason, pnl)
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
            'closed': len([r for r in results if r['success'] == True]),
            'partial': len([r for r in results if r['success'] == 'partial']),
            'failed': len([r for r in results if r['success'] == False]),
            'total_pnl': sum(r['pnl'] for r in results),
            'details': results
        }

    def process_expired_positions(self) -> Dict[str, Any]:
        """
        Process expired 0DTE positions at end of day.

        Called by scheduler at 3:05 PM CT to handle positions that expired
        during the trading day. For 0DTE options:
        - If price stayed within IC wings → max profit (credit received)
        - If price breached a wing → calculate loss based on final price

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
            # Get all open positions expiring today
            positions = self.db.get_open_positions()
            expired_positions = [p for p in positions if p.expiration <= today]

            if not expired_positions:
                logger.info("ARES EOD: No expired positions to process")
                return result

            logger.info(f"ARES EOD: Processing {len(expired_positions)} expired position(s)")

            for pos in expired_positions:
                try:
                    # Get final underlying price for P&L calculation
                    current_price = self.executor._get_current_price()
                    if not current_price:
                        current_price = pos.underlying_at_entry
                        logger.warning(f"Could not get current price, using entry: ${current_price}")

                    # Calculate final P&L based on where price ended
                    final_pnl = self._calculate_expiration_pnl(pos, current_price)

                    # Calculate IC close price (value at expiration)
                    # For Iron Condor: close_price = 0 if max profit, or intrinsic value if breached
                    close_price = pos.total_credit - (final_pnl / (100 * pos.contracts)) if pos.contracts > 0 else 0

                    # Mark position as expired in database with close price for audit
                    self.db.expire_position(pos.position_id, final_pnl, close_price)

                    # Record outcome for ML feedback
                    # Zero P&L is breakeven, not a loss
                    close_reason = "EXPIRED_PROFIT" if final_pnl >= 0 else "EXPIRED_LOSS"
                    self._record_oracle_outcome(pos, close_reason, final_pnl)

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
                        f"ARES EOD: Expired {pos.position_id} - "
                        f"Final price: ${current_price:.2f}, P&L: ${final_pnl:.2f}"
                    )

                except Exception as e:
                    logger.error(f"ARES EOD: Failed to process {pos.position_id}: {e}")
                    result['errors'].append(str(e))

            self.db.log("INFO", f"EOD processed {result['processed_count']} positions, P&L: ${result['total_pnl']:.2f}")

        except Exception as e:
            logger.error(f"ARES EOD processing failed: {e}")
            result['errors'].append(str(e))

        return result

    def _calculate_expiration_pnl(self, pos: IronCondorPosition, final_price: float) -> float:
        """
        Calculate P&L at expiration based on final underlying price.

        For 0DTE Iron Condors:
        - If price between short strikes → max profit (keep full credit)
        - If price outside long strikes → max loss
        - If price between short and long → partial loss
        """
        contracts = pos.contracts
        credit_received = pos.total_credit * 100 * contracts

        # Check if price stayed in the "safe zone"
        if pos.put_short_strike <= final_price <= pos.call_short_strike:
            # Max profit - IC expired worthless
            return credit_received

        # Check put side breach
        if final_price < pos.put_short_strike:
            if final_price <= pos.put_long_strike:
                # Max loss on put side
                put_loss = pos.spread_width * 100 * contracts
            else:
                # Partial loss on put side
                put_loss = (pos.put_short_strike - final_price) * 100 * contracts
            return credit_received - put_loss

        # Check call side breach
        if final_price > pos.call_short_strike:
            if final_price >= pos.call_long_strike:
                # Max loss on call side
                call_loss = pos.spread_width * 100 * contracts
            else:
                # Partial loss on call side
                call_loss = (final_price - pos.call_short_strike) * 100 * contracts
            return credit_received - call_loss

        # Should not reach here
        return credit_received


def run_ares_v2(config: Optional[ARESConfig] = None) -> ARESTrader:
    """Factory function to create ARES trader"""
    return ARESTrader(config)
