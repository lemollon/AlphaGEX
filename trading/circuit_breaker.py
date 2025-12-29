"""
CIRCUIT BREAKER / KILL SWITCH

Emergency stop and risk management for SPX wheel trading:

1. MAX DAILY LOSS - Stop trading if daily loss exceeds threshold
2. MAX POSITION LOSS - Stop loss on individual positions
3. MAX OPEN POSITIONS - Don't open beyond limit
4. KILL SWITCH - Immediately disable all trading
5. TRADING HOURS - Only trade during market hours

This was MISSING - adding it now for proper risk management!

USAGE:
    from trading.circuit_breaker import CircuitBreaker, is_trading_enabled

    cb = CircuitBreaker()

    # Check if trading is allowed
    if cb.can_trade():
        # ... execute trade

    # Disable all trading (emergency)
    cb.activate_kill_switch("Manual shutdown")

    # Check status
    status = cb.get_status()
"""

import os
import sys
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    ACTIVE = "ACTIVE"           # Normal operation
    TRIPPED = "TRIPPED"         # Tripped due to limits exceeded
    KILLED = "KILLED"           # Manually killed
    DISABLED = "DISABLED"       # System disabled


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker limits"""
    # Daily loss limit (as percentage of capital)
    max_daily_loss_pct: float = 3.0  # 3% max daily loss

    # Daily loss limit (absolute dollars)
    max_daily_loss_dollars: float = 30000.0  # $30k max daily loss

    # Max position loss before stop out (as percentage of entry premium)
    max_position_loss_pct: float = 200.0  # 2x premium = stop out

    # Max open positions
    max_open_positions: int = 5

    # Max total margin usage (as percentage of equity)
    max_margin_pct: float = 50.0  # 50% max margin

    # Consecutive loss protection
    max_consecutive_losses: int = 3  # Stop trading after 3 consecutive losses
    consecutive_loss_cooldown_hours: float = 24.0  # Hours to wait after hitting limit

    # Trading hours (24h format)
    trading_start_hour: int = 9
    trading_start_minute: int = 30
    trading_end_hour: int = 16
    trading_end_minute: int = 0

    # Auto-reset next day
    auto_reset_daily: bool = True


class CircuitBreaker:
    """
    Circuit breaker system for SPX wheel trading.

    Provides:
    - Kill switch for emergency stop
    - Daily loss limits
    - Position limits
    - Trading hours enforcement
    """

    def __init__(self, config: CircuitBreakerConfig = None, capital: float = 1000000):
        self.config = config or CircuitBreakerConfig()
        self.capital = capital

        # State
        self.state = CircuitBreakerState.ACTIVE
        self.trip_reason: Optional[str] = None
        self.trip_time: Optional[datetime] = None
        self.last_reset: datetime = datetime.now(CENTRAL_TZ)

        # Daily tracking
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.current_date: date = datetime.now(CENTRAL_TZ).date()

        # Consecutive loss tracking
        self.consecutive_losses: int = 0
        self.consecutive_loss_cooldown_until: Optional[datetime] = None
        self.last_trade_result: Optional[bool] = None  # True = win, False = loss

        # Trip history
        self.trip_history: list = []

        # Load persistent state
        self._load_state()

    def _get_state_file(self) -> str:
        """Get path to persistent state file"""
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data',
            'circuit_breaker_state.json'
        )

    def _load_state(self):
        """Load state from persistent storage"""
        try:
            state_file = self._get_state_file()
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    data = json.load(f)

                # Check if kill switch was activated
                if data.get('state') == 'KILLED':
                    self.state = CircuitBreakerState.KILLED
                    self.trip_reason = data.get('trip_reason', 'Kill switch active')
                    self.trip_time = datetime.fromisoformat(data.get('trip_time', datetime.now(CENTRAL_TZ).isoformat()))
                    logger.warning(f"Circuit breaker loaded in KILLED state: {self.trip_reason}")

                # Load daily data if same day
                saved_date = data.get('current_date')
                if saved_date == str(datetime.now(CENTRAL_TZ).date()):
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.daily_trades = data.get('daily_trades', 0)

                self.trip_history = data.get('trip_history', [])

        except Exception as e:
            logger.warning(f"Could not load circuit breaker state: {e}")

    def _save_state(self):
        """Save state to persistent storage"""
        try:
            state_file = self._get_state_file()
            os.makedirs(os.path.dirname(state_file), exist_ok=True)

            data = {
                'state': self.state.value,
                'trip_reason': self.trip_reason,
                'trip_time': self.trip_time.isoformat() if self.trip_time else None,
                'daily_pnl': self.daily_pnl,
                'daily_trades': self.daily_trades,
                'current_date': str(self.current_date),
                'trip_history': self.trip_history[-50:],  # Keep last 50
                'last_updated': datetime.now(CENTRAL_TZ).isoformat()
            }

            with open(state_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Could not save circuit breaker state: {e}")

    def _check_daily_reset(self):
        """Check if we should reset daily counters"""
        today = datetime.now(CENTRAL_TZ).date()

        if today > self.current_date:
            # New day - reset counters
            if self.config.auto_reset_daily and self.state == CircuitBreakerState.TRIPPED:
                logger.info("Circuit breaker auto-resetting for new trading day")
                self.state = CircuitBreakerState.ACTIVE
                self.trip_reason = None
                self.trip_time = None

            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.current_date = today
            self.last_reset = datetime.now(CENTRAL_TZ)
            self._save_state()

    def is_within_trading_hours(self) -> bool:
        """Check if current time is within trading hours"""
        now = datetime.now(CENTRAL_TZ)

        # Weekend check
        if now.weekday() >= 5:
            return False

        # Time check
        start_time = now.replace(
            hour=self.config.trading_start_hour,
            minute=self.config.trading_start_minute,
            second=0,
            microsecond=0
        )
        end_time = now.replace(
            hour=self.config.trading_end_hour,
            minute=self.config.trading_end_minute,
            second=0,
            microsecond=0
        )

        return start_time <= now <= end_time

    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """Check if daily loss limit is exceeded"""
        # Percentage check
        loss_pct = abs(self.daily_pnl) / self.capital * 100 if self.daily_pnl < 0 else 0

        if loss_pct >= self.config.max_daily_loss_pct:
            return False, f"Daily loss {loss_pct:.2f}% exceeds limit {self.config.max_daily_loss_pct}%"

        # Absolute dollar check
        if self.daily_pnl < 0 and abs(self.daily_pnl) >= self.config.max_daily_loss_dollars:
            return False, f"Daily loss ${abs(self.daily_pnl):,.2f} exceeds limit ${self.config.max_daily_loss_dollars:,.2f}"

        return True, "Within limits"

    def check_position_count(self, current_count: int) -> Tuple[bool, str]:
        """Check if position count is within limits"""
        if current_count >= self.config.max_open_positions:
            return False, f"Open positions {current_count} at limit {self.config.max_open_positions}"

        return True, f"Positions OK ({current_count}/{self.config.max_open_positions})"

    def check_margin_usage(self, margin_used: float) -> Tuple[bool, str]:
        """Check if margin usage is within limits"""
        margin_pct = margin_used / self.capital * 100

        if margin_pct >= self.config.max_margin_pct:
            return False, f"Margin usage {margin_pct:.1f}% exceeds limit {self.config.max_margin_pct}%"

        return True, f"Margin OK ({margin_pct:.1f}%)"

    def can_trade(
        self,
        current_positions: int = 0,
        margin_used: float = 0
    ) -> Tuple[bool, str]:
        """
        Master check if trading is allowed.

        Returns:
            (can_trade, reason)
        """
        # Reset daily if new day
        self._check_daily_reset()

        # Kill switch check
        if self.state == CircuitBreakerState.KILLED:
            return False, f"KILL SWITCH ACTIVE: {self.trip_reason}"

        # Tripped check
        if self.state == CircuitBreakerState.TRIPPED:
            return False, f"CIRCUIT TRIPPED: {self.trip_reason}"

        # Trading hours check
        if not self.is_within_trading_hours():
            return False, "Outside trading hours"

        # Daily loss check
        within_loss, loss_msg = self.check_daily_loss_limit()
        if not within_loss:
            self._trip_breaker(loss_msg)
            return False, loss_msg

        # Consecutive loss cooldown check
        if self.consecutive_loss_cooldown_until:
            if datetime.now(CENTRAL_TZ) < self.consecutive_loss_cooldown_until:
                remaining = self.consecutive_loss_cooldown_until - datetime.now(CENTRAL_TZ)
                return False, f"Consecutive loss cooldown ({self.consecutive_losses} losses). {remaining.seconds // 60} min remaining"
            else:
                # Cooldown expired, clear it
                self.consecutive_loss_cooldown_until = None
                logger.info("Consecutive loss cooldown expired")

        # Position count check
        within_positions, pos_msg = self.check_position_count(current_positions)
        if not within_positions:
            return False, pos_msg

        # Margin check
        within_margin, margin_msg = self.check_margin_usage(margin_used)
        if not within_margin:
            return False, margin_msg

        return True, "Trading allowed"

    def _trip_breaker(self, reason: str):
        """Trip the circuit breaker"""
        self.state = CircuitBreakerState.TRIPPED
        self.trip_reason = reason
        self.trip_time = datetime.now(CENTRAL_TZ)

        self.trip_history.append({
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'reason': reason,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades
        })

        self._save_state()

        logger.critical(f"CIRCUIT BREAKER TRIPPED: {reason}")

        # Try to send alert
        try:
            from trading.alerts import get_alerts
            alerts = get_alerts()
            alerts.send_email(
                "CIRCUIT BREAKER TRIPPED",
                f"Trading has been stopped.\n\nReason: {reason}\n\n"
                f"Daily P&L: ${self.daily_pnl:,.2f}\n"
                f"Daily Trades: {self.daily_trades}",
                "CRITICAL"
            )
        except Exception as e:
            logger.error(f"Could not send circuit breaker alert: {e}")

    def activate_kill_switch(self, reason: str = "Manual kill switch"):
        """
        Activate emergency kill switch.

        This completely stops all trading until manually reset.
        """
        self.state = CircuitBreakerState.KILLED
        self.trip_reason = reason
        self.trip_time = datetime.now(CENTRAL_TZ)

        self.trip_history.append({
            'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
            'reason': f"KILL SWITCH: {reason}",
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades
        })

        self._save_state()

        logger.critical(f"KILL SWITCH ACTIVATED: {reason}")
        print(f"\n{'='*60}")
        print("🔴 KILL SWITCH ACTIVATED")
        print(f"{'='*60}")
        print(f"Reason: {reason}")
        print(f"Time: {self.trip_time}")
        print(f"\nAll trading is now DISABLED.")
        print(f"To resume, run: python trading/circuit_breaker.py --reset")
        print(f"{'='*60}\n")

        # Send alert
        try:
            from trading.alerts import get_alerts
            alerts = get_alerts()
            alerts.send_email(
                "KILL SWITCH ACTIVATED",
                f"All trading has been STOPPED!\n\nReason: {reason}\n\n"
                f"Time: {self.trip_time}\n\n"
                f"To resume trading, manually reset the circuit breaker.",
                "CRITICAL"
            )
        except Exception as e:
            logger.warning(f"Could not send circuit breaker alert: {e}")

    def reset(self, confirm: bool = False):
        """
        Reset the circuit breaker.

        Requires explicit confirmation.
        """
        if not confirm:
            print("To reset circuit breaker, call reset(confirm=True)")
            return False

        old_state = self.state
        self.state = CircuitBreakerState.ACTIVE
        self.trip_reason = None
        self.trip_time = None
        self._save_state()

        logger.info(f"Circuit breaker reset from {old_state.value} to ACTIVE")
        print(f"✓ Circuit breaker reset to ACTIVE")
        return True

    def record_pnl(self, pnl: float, trade_id: Optional[str] = None):
        """
        Record P&L for a trade.

        Tracks consecutive losses and triggers cooldown if limit exceeded.
        """
        self._check_daily_reset()
        self.daily_pnl += pnl
        self.daily_trades += 1

        # Track consecutive losses
        is_loss = pnl < 0
        if is_loss:
            self.consecutive_losses += 1
            self.last_trade_result = False
            logger.info(f"Consecutive losses: {self.consecutive_losses}/{self.config.max_consecutive_losses}")
        else:
            # Reset streak on win
            self.consecutive_losses = 0
            self.last_trade_result = True
            self.consecutive_loss_cooldown_until = None  # Clear any cooldown

        self._save_state()

        # Check if we should trip due to daily loss
        within_limits, msg = self.check_daily_loss_limit()
        if not within_limits:
            self._trip_breaker(msg)
            return

        # Check if we should enter cooldown due to consecutive losses
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            cooldown_until = datetime.now(CENTRAL_TZ) + timedelta(hours=self.config.consecutive_loss_cooldown_hours)
            self.consecutive_loss_cooldown_until = cooldown_until
            reason = f"Consecutive loss limit hit ({self.consecutive_losses} losses). Cooldown until {cooldown_until.strftime('%H:%M')}"
            self._trip_breaker(reason)
            logger.warning(f"Circuit breaker: {reason}")

    def get_status(self) -> Dict:
        """Get current circuit breaker status"""
        self._check_daily_reset()

        loss_pct = abs(self.daily_pnl) / self.capital * 100 if self.daily_pnl < 0 else 0
        margin_remaining = self.config.max_daily_loss_pct - loss_pct

        return {
            'state': self.state.value,
            'can_trade': self.state == CircuitBreakerState.ACTIVE,
            'trip_reason': self.trip_reason,
            'trip_time': self.trip_time.isoformat() if self.trip_time else None,
            'daily_pnl': self.daily_pnl,
            'daily_pnl_pct': -loss_pct if self.daily_pnl < 0 else self.daily_pnl / self.capital * 100,
            'daily_trades': self.daily_trades,
            'loss_limit_remaining_pct': margin_remaining,
            'loss_limit_remaining_dollars': self.config.max_daily_loss_dollars - abs(min(0, self.daily_pnl)),
            'consecutive_losses': self.consecutive_losses,
            'max_consecutive_losses': self.config.max_consecutive_losses,
            'consecutive_loss_cooldown_until': self.consecutive_loss_cooldown_until.isoformat() if self.consecutive_loss_cooldown_until else None,
            'limits': {
                'max_daily_loss_pct': self.config.max_daily_loss_pct,
                'max_daily_loss_dollars': self.config.max_daily_loss_dollars,
                'max_position_loss_pct': self.config.max_position_loss_pct,
                'max_open_positions': self.config.max_open_positions,
                'max_margin_pct': self.config.max_margin_pct,
                'max_consecutive_losses': self.config.max_consecutive_losses
            },
            'last_reset': self.last_reset.isoformat(),
            'trip_count_today': sum(1 for t in self.trip_history if t.get('timestamp', '').startswith(str(self.current_date)))
        }


# Global instance
_circuit_breaker = None


def get_circuit_breaker(capital: float = 1000000) -> CircuitBreaker:
    """Get global circuit breaker instance"""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(capital=capital)
    return _circuit_breaker


def is_trading_enabled(current_positions: int = 0, margin_used: float = 0) -> Tuple[bool, str]:
    """Quick check if trading is enabled"""
    return get_circuit_breaker().can_trade(current_positions, margin_used)


def activate_kill_switch(reason: str = "Manual kill switch"):
    """Activate the kill switch"""
    get_circuit_breaker().activate_kill_switch(reason)


def reset_circuit_breaker(confirm: bool = False):
    """Reset the circuit breaker"""
    return get_circuit_breaker().reset(confirm)


def record_trade_pnl(pnl: float):
    """Record P&L from a trade"""
    get_circuit_breaker().record_pnl(pnl)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Circuit Breaker Control')
    parser.add_argument('--status', action='store_true', help='Show status')
    parser.add_argument('--kill', type=str, help='Activate kill switch with reason')
    parser.add_argument('--reset', action='store_true', help='Reset circuit breaker')
    parser.add_argument('--test-trip', action='store_true', help='Test trip with simulated loss')
    args = parser.parse_args()

    cb = CircuitBreaker()

    if args.status or not any([args.kill, args.reset, args.test_trip]):
        status = cb.get_status()
        print("\n" + "=" * 60)
        print("CIRCUIT BREAKER STATUS")
        print("=" * 60)
        print(f"State:           {status['state']}")
        print(f"Can Trade:       {'YES' if status['can_trade'] else 'NO'}")
        if status['trip_reason']:
            print(f"Trip Reason:     {status['trip_reason']}")
        print(f"\nDaily P&L:       ${status['daily_pnl']:,.2f} ({status['daily_pnl_pct']:+.2f}%)")
        print(f"Daily Trades:    {status['daily_trades']}")
        print(f"\nLimits:")
        print(f"  Max Daily Loss:   {status['limits']['max_daily_loss_pct']}% / ${status['limits']['max_daily_loss_dollars']:,.0f}")
        print(f"  Max Positions:    {status['limits']['max_open_positions']}")
        print(f"  Max Margin:       {status['limits']['max_margin_pct']}%")
        print(f"\nLoss Remaining:  {status['loss_limit_remaining_pct']:.2f}% / ${status['loss_limit_remaining_dollars']:,.2f}")
        print("=" * 60)

    elif args.kill:
        cb.activate_kill_switch(args.kill)

    elif args.reset:
        confirm = input("Are you sure you want to reset the circuit breaker? (yes/no): ")
        if confirm.lower() == 'yes':
            cb.reset(confirm=True)
        else:
            print("Reset cancelled")

    elif args.test_trip:
        print("Testing circuit breaker trip with simulated loss...")
        cb.record_pnl(-35000)  # Exceeds $30k limit
        status = cb.get_status()
        print(f"State after test: {status['state']}")
        print("Resetting for production...")
        cb.reset(confirm=True)
