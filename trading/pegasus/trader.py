"""
PEGASUS - Main Trading Orchestrator
=====================================

SPX Iron Condor trading bot.
One trade per day with $10 spreads.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from .models import (
    IronCondorPosition, PositionStatus, PEGASUSConfig,
    TradingMode, DailySummary, CENTRAL_TZ
)
from .db import PEGASUSDatabase
from .signals import SignalGenerator
from .executor import OrderExecutor

logger = logging.getLogger(__name__)

try:
    from trading.circuit_breaker import is_trading_enabled, record_trade_pnl
    CIRCUIT_BREAKER_AVAILABLE = True
except ImportError:
    CIRCUIT_BREAKER_AVAILABLE = False
    is_trading_enabled = None


class PEGASUSTrader:
    """
    PEGASUS - SPX Iron Condor Trader

    Usage:
        trader = PEGASUSTrader()
        result = trader.run_cycle()
    """

    def __init__(self, config: Optional[PEGASUSConfig] = None):
        self.db = PEGASUSDatabase(bot_name="PEGASUS")
        self.config = config or self.db.load_config()
        self.signals = SignalGenerator(self.config)
        self.executor = OrderExecutor(self.config)

        logger.info(f"PEGASUS initialized: mode={self.config.mode.value}, preset={self.config.preset.value}")

    def run_cycle(self) -> Dict[str, Any]:
        """Run trading cycle"""
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        result = {
            'timestamp': now.isoformat(),
            'action': 'none',
            'trade_opened': False,
            'positions_closed': 0,
            'realized_pnl': 0.0,
            'errors': [],
        }

        try:
            self.db.update_heartbeat("SCANNING", f"Cycle at {now.strftime('%I:%M %p')}")

            can_trade, reason = self._check_conditions(now, today)
            if not can_trade:
                result['action'] = 'skip'
                result['errors'].append(reason)
                return result

            # Manage positions
            closed, pnl = self._manage_positions()
            result['positions_closed'] = closed
            result['realized_pnl'] = pnl

            # Try new entry
            if not self.db.has_traded_today(today):
                pos = self._try_entry()
                if pos:
                    result['trade_opened'] = True
                    result['action'] = 'opened'

            if closed > 0:
                result['action'] = 'closed' if result['action'] == 'none' else 'both'

            self.db.update_heartbeat("IDLE", f"Complete: {result['action']}")

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            result['errors'].append(str(e))
            result['action'] = 'error'

        return result

    def _check_conditions(self, now: datetime, today: str) -> tuple[bool, str]:
        if now.weekday() >= 5:
            return False, "Weekend"

        start = self.config.entry_start.split(':')
        end = self.config.entry_end.split(':')
        start_time = now.replace(hour=int(start[0]), minute=int(start[1]), second=0)
        end_time = now.replace(hour=int(end[0]), minute=int(end[1]), second=0)

        if now < start_time:
            return False, f"Before {self.config.entry_start}"
        if now > end_time:
            return False, f"After {self.config.entry_end}"

        if self.db.has_traded_today(today):
            return False, "Already traded today"

        if CIRCUIT_BREAKER_AVAILABLE and is_trading_enabled:
            try:
                can, cb_reason = is_trading_enabled(self.db.get_position_count(), 0)
                if not can:
                    return False, f"Circuit breaker: {cb_reason}"
            except Exception:
                pass

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
                if success:
                    self.db.close_position(pos.position_id, price, pnl, reason)
                    closed += 1
                    total_pnl += pnl

                    if CIRCUIT_BREAKER_AVAILABLE and record_trade_pnl:
                        try:
                            record_trade_pnl(pnl)
                        except Exception:
                            pass

        return closed, total_pnl

    def _check_exit(self, pos: IronCondorPosition, now: datetime, today: str) -> tuple[bool, str]:
        if pos.expiration <= today:
            return True, "EXPIRED"

        force = self.config.force_exit.split(':')
        force_time = now.replace(hour=int(force[0]), minute=int(force[1]), second=0)
        if now >= force_time and pos.expiration == today:
            return True, "FORCE_EXIT"

        current = self.executor.get_position_current_value(pos)
        if current is None:
            return False, ""

        # Profit target
        target = pos.total_credit * (1 - self.config.profit_target_pct / 100)
        if current <= target:
            return True, f"PROFIT_{self.config.profit_target_pct:.0f}%"

        # Stop loss
        if self.config.use_stop_loss:
            stop = pos.total_credit * self.config.stop_loss_multiple
            if current >= stop:
                return True, "STOP_LOSS"

        return False, ""

    def _try_entry(self) -> Optional[IronCondorPosition]:
        signal = self.signals.generate_signal()
        if not signal or not signal.is_valid:
            return None

        position = self.executor.execute_iron_condor(signal)
        if position:
            self.db.save_position(position)
            self.db.log("INFO", f"Opened: {position.position_id}")

        return position

    def get_status(self) -> Dict[str, Any]:
        now = datetime.now(CENTRAL_TZ)
        positions = self.db.get_open_positions()

        unrealized = 0.0
        for pos in positions:
            val = self.executor.get_position_current_value(pos)
            if val:
                unrealized += (pos.total_credit - val) * 100 * pos.contracts

        return {
            'bot_name': 'PEGASUS',
            'version': 'V1',
            'mode': self.config.mode.value,
            'ticker': 'SPX',
            'preset': self.config.preset.value,
            'open_positions': len(positions),
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
            results.append({'position_id': pos.position_id, 'success': success, 'pnl': pnl})

        return {
            'closed': len([r for r in results if r['success']]),
            'total_pnl': sum(r['pnl'] for r in results if r['success']),
        }


def run_pegasus(config: Optional[PEGASUSConfig] = None) -> PEGASUSTrader:
    """Factory function"""
    return PEGASUSTrader(config)
