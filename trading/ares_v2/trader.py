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
from datetime import datetime
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

# Scan activity logging
try:
    from trading.scan_activity_logger import log_ares_scan, ScanOutcome, CheckResult
    SCAN_LOGGER_AVAILABLE = True
except ImportError:
    SCAN_LOGGER_AVAILABLE = False
    log_ares_scan = None
    ScanOutcome = None
    CheckResult = None


class ARESTrader:
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

        # Initialize components
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config)

        logger.info(
            f"ARES V2 initialized: mode={self.config.mode.value}, "
            f"ticker={self.config.ticker}, preset={self.config.preset.value}"
        )

    def run_cycle(self) -> Dict[str, Any]:
        """
        Run a single trading cycle.

        ARES only trades once per day.
        This method is called by the scheduler.
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

            # Step 1: Check trading conditions
            can_trade, reason = self._check_trading_conditions(now, today)
            if not can_trade:
                result['action'] = 'skip'
                result['details']['skip_reason'] = reason
                result['errors'].append(reason)
                self.db.log("INFO", f"Skipping: {reason}")

                # Log skip to scan activity
                self._log_scan_activity(result, scan_context, reason)
                return result

            # Step 2: Check and manage existing positions
            closed_count, close_pnl = self._manage_positions()
            result['positions_closed'] = closed_count
            result['realized_pnl'] = close_pnl

            # Step 3: Try to open new position (once per day)
            if not self.db.has_traded_today(today):
                position, signal = self._try_new_entry_with_context()
                if position:
                    result['trade_opened'] = True
                    result['action'] = 'opened'
                    result['details']['position'] = position.to_dict()
                    scan_context['position'] = position
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

            if result['positions_closed'] > 0:
                result['action'] = 'closed' if result['action'] == 'none' else 'both'

            # Step 4: Update daily summary
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

    def _check_trading_conditions(
        self,
        now: datetime,
        today: str
    ) -> tuple[bool, str]:
        """Check all conditions before trading"""
        # Weekend check
        if now.weekday() >= 5:
            return False, "Weekend"

        # Trading window
        start_parts = self.config.entry_start.split(':')
        end_parts = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start_parts[0]), minute=int(start_parts[1]), second=0)
        end_time = now.replace(hour=int(end_parts[0]), minute=int(end_parts[1]), second=0)

        if now < start_time:
            return False, f"Before trading window ({self.config.entry_start})"
        if now > end_time:
            return False, f"After trading window ({self.config.entry_end})"

        # Already traded today (ARES = 1 trade/day)
        if self.db.has_traded_today(today):
            return False, "Already traded today"

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

                if success:
                    self.db.close_position(
                        position_id=pos.position_id,
                        close_price=close_price,
                        realized_pnl=pnl,
                        close_reason=reason
                    )
                    closed_count += 1
                    total_pnl += pnl

                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception:
                            pass

                    self.db.log("INFO", f"Closed {pos.position_id}: {reason}, P&L=${pnl:.2f}")

        return closed_count, total_pnl

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

        # Force exit time
        force_parts = self.config.force_exit.split(':')
        force_time = now.replace(hour=int(force_parts[0]), minute=int(force_parts[1]), second=0)
        if now >= force_time and pos.expiration == today:
            return True, "FORCE_EXIT_TIME"

        # Get current value
        current_value = self.executor.get_position_current_value(pos)
        if current_value is None:
            return False, ""

        # Profit target (50% of credit received)
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

        # Execute the trade
        position = self.executor.execute_iron_condor(signal)
        if not position:
            self.db.log("ERROR", "Execution failed", {'signal': signal.reasoning})
            return None, signal

        # Save to database
        if not self.db.save_position(position):
            self.db.log("ERROR", "Failed to save position", {'pos_id': position.position_id})
            logger.error(f"Position {position.position_id} executed but not saved!")

        self.db.log("INFO", f"Opened: {position.position_id}", position.to_dict())

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
            if success:
                self.db.close_position(pos.position_id, close_price, pnl, reason)
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


def run_ares_v2(config: Optional[ARESConfig] = None) -> ARESTrader:
    """Factory function to create ARES trader"""
    return ARESTrader(config)
