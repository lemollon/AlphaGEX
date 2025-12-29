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


class ATHENATrader:
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

                    # Record to circuit breaker
                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception:
                            pass

                    self.db.log("INFO", f"Closed {pos.position_id}: {reason}, P&L=${pnl:.2f}")

        return closed_count, total_pnl

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

        # Profit target (50% of max profit)
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

        # Generate signal
        signal = self.signals.generate_signal()
        if not signal:
            self.db.log("INFO", "No valid signal generated")
            return None, None

        if not signal.is_valid:
            self.db.log("INFO", f"Signal invalid: {signal.reasoning}")
            return None, signal  # Return signal for logging even if invalid

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

        # Execute the trade
        position = self.executor.execute_spread(signal)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database
        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position to DB", {'pos_id': position.position_id})
            # Still return position - it was executed
            logger.error(f"Position {position.position_id} executed but not saved to DB!")

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

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


def run_athena_v2(config: Optional[ATHENAConfig] = None) -> ATHENATrader:
    """Factory function to create and return ATHENA trader"""
    return ATHENATrader(config)
