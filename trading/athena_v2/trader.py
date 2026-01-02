"""
ATHENA V2 - Main Trading Orchestrator
=======================================

Clean, simple orchestration of all ATHENA components.

Design principles:
1. Single entry point for all trading operations
2. Clear flow: check -> signal -> execute -> manage
3. Database is THE source of truth
4. Minimal state in memory
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo

from .models import (
    SpreadPosition, PositionStatus, ATHENAConfig,
    TradingMode, DailySummary, CENTRAL_TZ
)
from .db import ATHENADatabase
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
    from trading.scan_activity_logger import log_athena_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_athena_scan = None
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

# Math Optimizer integration for enhanced trading decisions
try:
    from trading.mixins.math_optimizer_mixin import MathOptimizerMixin
    MATH_OPTIMIZER_AVAILABLE = True
except ImportError:
    MATH_OPTIMIZER_AVAILABLE = False
    MathOptimizerMixin = object  # Fallback to empty base class


class ATHENATrader(MathOptimizerMixin):
    """
    ATHENA V2 - Clean, modular directional spread trader.

    Usage:
        trader = ATHENATrader()
        result = trader.run_cycle()
    """

    def __init__(self, config: Optional[ATHENAConfig] = None):
        """
        Initialize ATHENA trader.

        Config is loaded from DB if not provided.
        """
        # Initialize database layer FIRST
        self.db = ATHENADatabase(bot_name="ATHENA")

        # Load config from DB or use provided
        self.config = config or self.db.load_config()

        # Initialize components
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config)

        # Learning Memory prediction tracking (position_id -> prediction_id)
        self._prediction_ids: Dict[str, str] = {}

        # Initialize Math Optimizers (HMM, Kalman, Thompson, Convex, HJB, MDP)
        if MATH_OPTIMIZER_AVAILABLE:
            self._init_math_optimizers("ATHENA", enabled=True)
            logger.info("ATHENA: Math optimizers enabled (HMM, Kalman, Thompson, Convex, HJB, MDP)")

        logger.info(
            f"ATHENA V2 initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}"
        )

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        This is the MAIN entry point called by the scheduler.

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
            'position': None
        }

        try:
            # Update heartbeat
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}")

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

        # Trading window check
        start_parts = self.config.entry_start.split(':')
        end_parts = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if now < start_time:
            return False, f"Before trading window ({self.config.entry_start})"
        if now > end_time:
            return False, f"After trading window ({self.config.entry_end})"

        # Daily trade limit
        daily_trades = self.db.get_daily_trades_count(today)
        if daily_trades >= self.config.max_daily_trades:
            return False, f"Daily limit reached ({self.config.max_daily_trades})"

        # Position limit
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
                    self.db.close_position(
                        position_id=pos.position_id,
                        close_price=close_price,
                        realized_pnl=pnl,
                        close_reason=reason
                    )
                    closed_count += 1
                    total_pnl += pnl

                    # Record outcome to Oracle for ML feedback loop
                    self._record_oracle_outcome(pos, reason, pnl)

                    # Record outcome to Learning Memory for self-improvement
                    if pos.position_id in self._prediction_ids:
                        self._record_learning_memory_outcome(
                            self._prediction_ids.pop(pos.position_id),
                            pnl,
                            reason
                        )

                    # Record to circuit breaker
                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception:
                            pass

                    # MATH OPTIMIZER: Record outcome for Thompson Sampling
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

            # Determine outcome type based on P&L
            # ATHENA trades directional spreads, so it's simpler: WIN or LOSS
            if pnl > 0:
                outcome = OracleTradeOutcome.MAX_PROFIT if 'PROFIT_TARGET' in close_reason else OracleTradeOutcome.PARTIAL_PROFIT
            else:
                outcome = OracleTradeOutcome.LOSS

            # Get trade date from position
            trade_date = pos.expiration if hasattr(pos, 'expiration') else datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

            # Record to Oracle using ATHENA bot name
            success = oracle.update_outcome(
                trade_date=trade_date,
                bot_name=OracleBotName.ATHENA,
                outcome=outcome,
                actual_pnl=pnl,
            )

            if success:
                logger.info(f"ATHENA: Recorded outcome to Oracle - {outcome.value}, P&L=${pnl:.2f}")
            else:
                logger.warning(f"ATHENA: Failed to record outcome to Oracle")

        except Exception as e:
            logger.warning(f"ATHENA: Oracle outcome recording failed: {e}")

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
            prediction = f"{signal.direction if hasattr(signal, 'direction') else 'directional'} spread profitable"
            prediction_id = memory.record_prediction(
                prediction_type="directional_spread_outcome",
                prediction=prediction,
                confidence=signal.confidence / 100 if hasattr(signal, 'confidence') else 0.7,
                context=context
            )

            logger.info(f"ATHENA: Learning Memory prediction recorded: {prediction_id}")
            return prediction_id

        except Exception as e:
            logger.warning(f"ATHENA: Learning Memory prediction failed: {e}")
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

            logger.info(f"ATHENA: Learning Memory outcome recorded: correct={was_correct}, P&L=${pnl:.2f}")

        except Exception as e:
            logger.warning(f"ATHENA: Learning Memory outcome recording failed: {e}")

    def _check_exit_conditions(
        self,
        pos: SpreadPosition,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """
        Check if a position should be closed.

        Returns (should_close, reason).
        """
        from datetime import timedelta

        # Expiration check
        if pos.expiration <= today:
            return True, "EXPIRED"

        # Force exit time check
        force_parts = self.config.force_exit.split(':')
        force_time = now.replace(hour=int(force_parts[0]), minute=int(force_parts[1]), second=0)
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
                entry_time = pos.entry_time if hasattr(pos, 'entry_time') else now - timedelta(hours=2)

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

    def _try_new_entry(self) -> Optional[SpreadPosition]:
        """
        Try to open a new position.

        Returns SpreadPosition if successful, None otherwise.
        """
        position, _ = self._try_new_entry_with_context()
        return position

    def _try_new_entry_with_context(self) -> tuple[Optional[SpreadPosition], Optional[Any]]:
        """
        Try to open a new position, returning both position and signal for logging.

        Returns (SpreadPosition, Signal) tuple.
        """
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
            return None, signal  # Return signal for logging even if invalid

        # MATH OPTIMIZER: Smooth Greeks if available
        if MATH_OPTIMIZER_AVAILABLE and hasattr(self, '_math_enabled') and self._math_enabled:
            try:
                if hasattr(signal, 'greeks') and signal.greeks:
                    smoothed = self.math_smooth_greeks(signal.greeks)
                    logger.debug(f"ATHENA: Smoothed Greeks applied")
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
                athena_alloc = allocation.get('allocations', {}).get('ATHENA', 0.2)
                thompson_weight = athena_alloc / 0.2  # Normalize to 20% baseline
                logger.info(f"ATHENA Thompson weight: {thompson_weight:.2f} (allocation: {athena_alloc:.1%})")
            except Exception as e:
                logger.debug(f"Thompson allocation skipped: {e}")

        # Execute the trade with Thompson-adjusted position sizing
        position = self.executor.execute_spread(signal, thompson_weight=thompson_weight)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database
        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position to DB", {'pos_id': position.position_id})
            # Still return position - it was executed
            logger.error(f"Position {position.position_id} executed but not saved to DB!")

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

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
        if not SCAN_LOGGER_AVAILABLE or not log_athena_scan:
            return

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

            # Build signal context
            signal = context.get('signal')
            signal_direction = ""
            signal_confidence = 0
            signal_win_probability = 0
            oracle_advice = ""
            oracle_reasoning = ""

            if signal:
                signal_direction = signal.direction
                signal_confidence = signal.confidence
                signal_win_probability = getattr(signal, 'win_probability', 0)
                oracle_advice = "ENTER" if signal.is_valid else "SKIP"
                oracle_reasoning = signal.reasoning

            # Build trade details if position opened
            position = context.get('position')

            log_athena_scan(
                outcome=outcome,
                decision_summary=decision,
                market_data=context.get('market_data'),
                gex_data=context.get('gex_data'),
                checks=context.get('checks', []),
                signal_source="ATHENA_V2",
                signal_direction=signal_direction,
                signal_confidence=signal_confidence,
                signal_win_probability=signal_win_probability,
                oracle_advice=oracle_advice,
                oracle_reasoning=oracle_reasoning,
                trade_executed=result.get('trades_opened', 0) > 0,
                error_message=error_msg,
                generate_ai_explanation=False,  # Keep it simple
            )
        except Exception as e:
            logger.warning(f"Failed to log scan activity: {e}")

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

        # Calculate unrealized P&L
        unrealized_pnl = 0.0
        for pos in positions:
            current_value = self.executor.get_position_current_value(pos)
            if current_value:
                pnl = (current_value - pos.entry_debit) * 100 * pos.contracts
                unrealized_pnl += pnl

        return {
            'bot_name': 'ATHENA',
            'version': 'V2',
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

    def force_close_all(self, reason: str = "MANUAL_CLOSE") -> Dict[str, Any]:
        """Force close all open positions"""
        positions = self.db.get_open_positions()
        results = []

        for pos in positions:
            success, close_price, pnl = self.executor.close_position(pos, reason)
            if success:
                self.db.close_position(
                    pos.position_id, close_price, pnl, reason
                )
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
                logger.info("ATHENA EOD: No expired positions to process")
                return result

            logger.info(f"ATHENA EOD: Processing {len(expired_positions)} expired position(s)")

            for pos in expired_positions:
                try:
                    # Get final underlying price for P&L calculation
                    current_price = self.executor._get_current_price()
                    if not current_price:
                        current_price = pos.underlying_at_entry
                        logger.warning(f"Could not get current price, using entry: ${current_price}")

                    # Calculate final P&L based on where price ended
                    final_pnl = self._calculate_expiration_pnl(pos, current_price)

                    # Mark position as expired in database
                    self.db.expire_position(pos.position_id, final_pnl)

                    # Record outcome for ML feedback
                    close_reason = "EXPIRED_PROFIT" if final_pnl > 0 else "EXPIRED_LOSS"
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
                        f"ATHENA EOD: Expired {pos.position_id} - "
                        f"Final price: ${current_price:.2f}, P&L: ${final_pnl:.2f}"
                    )

                except Exception as e:
                    logger.error(f"ATHENA EOD: Failed to process {pos.position_id}: {e}")
                    result['errors'].append(str(e))

            self.db.log("INFO", f"EOD processed {result['processed_count']} positions, P&L: ${result['total_pnl']:.2f}")

        except Exception as e:
            logger.error(f"ATHENA EOD processing failed: {e}")
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

        # Determine spread type from direction
        is_bullish = pos.direction.lower() in ('bull', 'bullish', 'call')

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


def run_athena_v2(config: Optional[ATHENAConfig] = None) -> ATHENATrader:
    """Factory function to create and return ATHENA trader"""
    return ATHENATrader(config)
