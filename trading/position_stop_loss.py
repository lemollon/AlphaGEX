"""
Position-Level Stop Loss Management

Provides per-position stop loss tracking and monitoring for FORTRESS and SOLOMON.

Features:
- Configurable stop loss percentages per position
- Trailing stop support
- Time-based stop adjustments (tighter near expiration)
- Integration with both Iron Condors and Directional Spreads
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class StopLossType(Enum):
    """Types of stop loss mechanisms"""
    FIXED_PERCENTAGE = "fixed_percentage"      # Fixed % of entry
    PREMIUM_MULTIPLE = "premium_multiple"       # Multiple of premium collected (IC)
    TRAILING = "trailing"                       # Trail from high water mark
    TIME_DECAY = "time_decay"                   # Tightens as expiration approaches
    NONE = "none"                               # No stop loss (defined risk)


@dataclass
class StopLossConfig:
    """Configuration for position stop loss"""
    # Type of stop loss
    stop_type: StopLossType = StopLossType.FIXED_PERCENTAGE

    # Fixed percentage stop (for directional spreads)
    fixed_stop_pct: float = 75.0              # Exit at 75% loss (of entry)

    # Premium multiple stop (for Iron Condors)
    # Exit when loss exceeds X times the premium collected
    premium_multiple: float = 2.0              # Exit at 2x premium loss

    # Trailing stop parameters
    trail_start_profit_pct: float = 50.0       # Start trailing after 50% profit
    trail_distance_pct: float = 25.0           # Trail by 25% from peak

    # Time-decay stop (tightens near expiration)
    time_decay_enabled: bool = True
    hours_to_expiry_tight: float = 2.0         # Tighten stop within 2 hours
    tight_stop_multiplier: float = 0.5         # Reduce stop distance by 50%

    # Hard limits
    max_loss_pct: float = 100.0                # Never lose more than 100% of entry


@dataclass
class PositionStopLoss:
    """Stop loss state for a single position"""
    position_id: str
    stop_config: StopLossConfig = field(default_factory=StopLossConfig)

    # Entry info
    entry_price: float = 0.0                   # Entry cost (debit for spreads, credit for ICs)
    entry_time: datetime = field(default_factory=lambda: datetime.now(CENTRAL_TZ))
    expiration: Optional[datetime] = None

    # For Iron Condors
    premium_received: float = 0.0
    max_defined_loss: float = 0.0              # Spread width - premium

    # For trailing stop
    high_water_mark: float = 0.0               # Peak value (for profit trailing)
    low_water_mark: float = float('inf')       # Trough value (for loss tracking)

    # State
    stop_triggered: bool = False
    trigger_reason: str = ""
    trigger_time: Optional[datetime] = None
    trigger_price: float = 0.0


class PositionStopLossManager:
    """
    Manages stop losses for multiple positions.

    Designed to work with both FORTRESS (Iron Condors) and SOLOMON (Directional Spreads).
    """

    def __init__(self, default_config: Optional[StopLossConfig] = None):
        """Initialize the stop loss manager."""
        self.default_config = default_config or StopLossConfig()
        self.positions: Dict[str, PositionStopLoss] = {}
        logger.info("PositionStopLossManager initialized")

    def register_position(
        self,
        position_id: str,
        entry_price: float,
        expiration: Optional[datetime] = None,
        premium_received: float = 0.0,
        max_defined_loss: float = 0.0,
        config: Optional[StopLossConfig] = None
    ) -> PositionStopLoss:
        """
        Register a new position for stop loss tracking.

        Args:
            position_id: Unique identifier for the position
            entry_price: Entry cost (debit for spreads, credit for ICs)
            expiration: Option expiration datetime
            premium_received: For Iron Condors, the credit received
            max_defined_loss: For Iron Condors, max loss (width - credit)
            config: Custom stop loss config (uses default if not provided)

        Returns:
            PositionStopLoss object for the position
        """
        stop_loss = PositionStopLoss(
            position_id=position_id,
            stop_config=config or self.default_config,
            entry_price=entry_price,
            entry_time=datetime.now(CENTRAL_TZ),
            expiration=expiration,
            premium_received=premium_received,
            max_defined_loss=max_defined_loss,
            high_water_mark=entry_price,
            low_water_mark=entry_price
        )

        self.positions[position_id] = stop_loss
        logger.info(f"Registered position {position_id} for stop loss tracking "
                   f"(type: {stop_loss.stop_config.stop_type.value})")

        return stop_loss

    def unregister_position(self, position_id: str) -> None:
        """Remove a position from tracking."""
        if position_id in self.positions:
            del self.positions[position_id]
            logger.info(f"Unregistered position {position_id} from stop loss tracking")

    def check_stop_loss(
        self,
        position_id: str,
        current_value: float,
        current_price: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Check if a position's stop loss has been triggered.

        Args:
            position_id: Position identifier
            current_value: Current position value (positive = profit, negative = loss)
            current_price: Current underlying price (optional, for logging)

        Returns:
            Tuple of (triggered: bool, reason: str)
        """
        if position_id not in self.positions:
            return False, "Position not registered"

        stop_loss = self.positions[position_id]

        # Already triggered - don't check again
        if stop_loss.stop_triggered:
            return True, stop_loss.trigger_reason

        config = stop_loss.stop_config
        triggered = False
        reason = ""

        # Update water marks
        stop_loss.high_water_mark = max(stop_loss.high_water_mark, current_value)
        stop_loss.low_water_mark = min(stop_loss.low_water_mark, current_value)

        # Calculate loss percentage
        if stop_loss.entry_price > 0:
            loss_pct = ((stop_loss.entry_price - current_value) / stop_loss.entry_price) * 100
        else:
            loss_pct = 0

        # Time to expiration factor
        time_factor = 1.0
        if config.time_decay_enabled and stop_loss.expiration:
            now = datetime.now(CENTRAL_TZ)
            hours_to_expiry = (stop_loss.expiration - now).total_seconds() / 3600

            if hours_to_expiry < config.hours_to_expiry_tight:
                time_factor = config.tight_stop_multiplier
                logger.debug(f"Position {position_id}: Time decay active, "
                            f"{hours_to_expiry:.1f}h to expiry, factor={time_factor}")

        # Check based on stop type
        if config.stop_type == StopLossType.FIXED_PERCENTAGE:
            adjusted_stop = config.fixed_stop_pct * time_factor
            if loss_pct >= adjusted_stop:
                triggered = True
                reason = f"FIXED_STOP: Loss {loss_pct:.1f}% >= {adjusted_stop:.1f}%"

        elif config.stop_type == StopLossType.PREMIUM_MULTIPLE:
            # For Iron Condors: exit when loss exceeds X times premium
            if stop_loss.premium_received > 0:
                current_loss = stop_loss.entry_price - current_value
                premium_loss_multiple = current_loss / (stop_loss.premium_received * 100)
                adjusted_multiple = config.premium_multiple * time_factor

                if premium_loss_multiple >= adjusted_multiple:
                    triggered = True
                    reason = f"PREMIUM_STOP: Loss {premium_loss_multiple:.1f}x >= {adjusted_multiple:.1f}x premium"

        elif config.stop_type == StopLossType.TRAILING:
            # Trail from high water mark
            profit_pct = ((current_value - stop_loss.entry_price) / stop_loss.entry_price) * 100 \
                if stop_loss.entry_price > 0 else 0

            if profit_pct >= config.trail_start_profit_pct:
                # Calculate how much we've given back from peak
                peak_profit = stop_loss.high_water_mark - stop_loss.entry_price
                current_profit = current_value - stop_loss.entry_price

                if peak_profit > 0:
                    giveback_pct = ((peak_profit - current_profit) / peak_profit) * 100
                    adjusted_trail = config.trail_distance_pct / time_factor  # Tighten with time

                    if giveback_pct >= adjusted_trail:
                        triggered = True
                        reason = f"TRAILING_STOP: Gave back {giveback_pct:.1f}% >= {adjusted_trail:.1f}% from peak"

        # Always check hard max loss
        if not triggered and config.stop_type != StopLossType.NONE:
            if loss_pct >= config.max_loss_pct:
                triggered = True
                reason = f"MAX_LOSS_STOP: Loss {loss_pct:.1f}% >= {config.max_loss_pct:.1f}%"

        # Record trigger if hit
        if triggered:
            stop_loss.stop_triggered = True
            stop_loss.trigger_reason = reason
            stop_loss.trigger_time = datetime.now(CENTRAL_TZ)
            stop_loss.trigger_price = current_value

            logger.warning(f"STOP LOSS TRIGGERED for {position_id}: {reason}")

        return triggered, reason

    def check_all_positions(
        self,
        position_values: Dict[str, float]
    ) -> List[Tuple[str, str]]:
        """
        Check stop losses for multiple positions at once.

        Args:
            position_values: Dict of position_id -> current_value

        Returns:
            List of (position_id, reason) for triggered stops
        """
        triggered = []

        for position_id, current_value in position_values.items():
            is_triggered, reason = self.check_stop_loss(position_id, current_value)
            if is_triggered:
                triggered.append((position_id, reason))

        return triggered

    def get_position_stop_status(self, position_id: str) -> Optional[Dict[str, Any]]:
        """Get stop loss status for a position."""
        if position_id not in self.positions:
            return None

        stop_loss = self.positions[position_id]

        return {
            'position_id': position_id,
            'stop_type': stop_loss.stop_config.stop_type.value,
            'entry_price': stop_loss.entry_price,
            'high_water_mark': stop_loss.high_water_mark,
            'low_water_mark': stop_loss.low_water_mark,
            'stop_triggered': stop_loss.stop_triggered,
            'trigger_reason': stop_loss.trigger_reason,
            'trigger_time': stop_loss.trigger_time.isoformat() if stop_loss.trigger_time else None,
            'trigger_price': stop_loss.trigger_price
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get stop loss status for all tracked positions."""
        return {
            pos_id: self.get_position_stop_status(pos_id)
            for pos_id in self.positions
        }


# ============================================================================
# Factory Functions for FORTRESS and SOLOMON
# ============================================================================

def create_iron_condor_stop_config(
    premium_multiple: float = 2.0,
    use_time_decay: bool = True
) -> StopLossConfig:
    """
    Create stop loss config optimized for Iron Condors.

    Iron Condors have defined risk, but an early exit at 2x premium loss
    can prevent max loss scenarios.

    Args:
        premium_multiple: Exit when loss exceeds this multiple of premium
        use_time_decay: Tighten stops near expiration

    Returns:
        StopLossConfig for Iron Condors
    """
    return StopLossConfig(
        stop_type=StopLossType.PREMIUM_MULTIPLE,
        premium_multiple=premium_multiple,
        time_decay_enabled=use_time_decay,
        hours_to_expiry_tight=1.0,        # Tighten within 1 hour
        tight_stop_multiplier=0.75,        # Reduce multiple by 25%
        max_loss_pct=100.0
    )


def create_spread_stop_config(
    hard_stop_pct: float = 75.0,
    use_trailing: bool = True,
    trail_start_pct: float = 50.0,
    trail_distance_pct: float = 25.0
) -> StopLossConfig:
    """
    Create stop loss config optimized for Directional Spreads.

    Args:
        hard_stop_pct: Hard stop at this % loss
        use_trailing: Enable trailing stop after profit
        trail_start_pct: Start trailing after this % profit
        trail_distance_pct: Trail by this % from peak

    Returns:
        StopLossConfig for Directional Spreads
    """
    stop_type = StopLossType.TRAILING if use_trailing else StopLossType.FIXED_PERCENTAGE

    return StopLossConfig(
        stop_type=stop_type,
        fixed_stop_pct=hard_stop_pct,
        trail_start_profit_pct=trail_start_pct,
        trail_distance_pct=trail_distance_pct,
        time_decay_enabled=True,
        hours_to_expiry_tight=0.5,         # Tighten within 30 min
        tight_stop_multiplier=0.5,          # Cut stop distance in half
        max_loss_pct=hard_stop_pct
    )


# Singleton manager instance
_stop_loss_manager: Optional[PositionStopLossManager] = None


def get_stop_loss_manager() -> PositionStopLossManager:
    """Get the singleton stop loss manager instance."""
    global _stop_loss_manager
    if _stop_loss_manager is None:
        _stop_loss_manager = PositionStopLossManager()
    return _stop_loss_manager


# ============================================================================
# Integration Helpers
# ============================================================================

def check_position_stop_loss(
    position_id: str,
    current_value: float,
    entry_price: float = 0.0,
    premium_received: float = 0.0,
    expiration: Optional[datetime] = None,
    max_defined_loss: float = 0.0,
    stop_config: Optional[StopLossConfig] = None
) -> Tuple[bool, str]:
    """
    Convenience function to check stop loss for a position.

    Automatically registers the position if not already tracked.

    Args:
        position_id: Unique position identifier
        current_value: Current position value
        entry_price: Entry cost
        premium_received: For ICs, premium collected
        expiration: Option expiration
        max_defined_loss: For ICs, spread width - credit
        stop_config: Optional custom config

    Returns:
        Tuple of (triggered: bool, reason: str)
    """
    manager = get_stop_loss_manager()

    # Register if not tracked
    if position_id not in manager.positions:
        manager.register_position(
            position_id=position_id,
            entry_price=entry_price,
            expiration=expiration,
            premium_received=premium_received,
            max_defined_loss=max_defined_loss,
            config=stop_config
        )

    return manager.check_stop_loss(position_id, current_value)
