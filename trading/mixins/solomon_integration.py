"""
Solomon Integration Mixin for Trading Bots
==========================================

Provides Solomon feedback loop integration for all trading bots:
- Kill switch checking before trading
- Outcome recording for feedback loop
- Version awareness for model loading
- Performance tracking

Usage:
    from trading.mixins.solomon_integration import SolomonIntegrationMixin

    class MyBot(SolomonIntegrationMixin):
        def __init__(self):
            self._init_solomon_integration("MY_BOT")

        def before_trade(self):
            if not self.solomon_can_trade():
                return False
            ...

        def after_trade(self, outcome, pnl):
            self.solomon_record_outcome(outcome, pnl)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_solomon = None
_solomon_available = None


def _get_solomon():
    """Lazy load Solomon to avoid import issues at module load time"""
    global _solomon, _solomon_available

    if _solomon_available is not None:
        return _solomon if _solomon_available else None

    try:
        from quant.solomon_feedback_loop import get_solomon, ActionType
        _solomon = get_solomon()
        _solomon_available = True
        return _solomon
    except ImportError:
        _solomon_available = False
        logger.debug("Solomon not available for bot integration")
        return None


class SolomonIntegrationMixin:
    """
    Mixin class providing Solomon feedback loop integration for trading bots.

    Attributes set by _init_solomon_integration:
        _solomon_bot_name: str - The bot identifier for Solomon
        _solomon_enabled: bool - Whether Solomon integration is active
    """

    def _init_solomon_integration(self, bot_name: str):
        """
        Initialize Solomon integration for this bot.

        Args:
            bot_name: The bot identifier (ARES, ATHENA, ATLAS, PHOENIX)
        """
        self._solomon_bot_name = bot_name
        self._solomon_enabled = True
        self._solomon_kill_check_cache = None
        self._solomon_kill_check_time = None

        # Log initialization
        solomon = _get_solomon()
        if solomon:
            logger.info(f"{bot_name}: Solomon integration initialized")
        else:
            logger.debug(f"{bot_name}: Solomon not available, running without feedback loop")

    def solomon_can_trade(self, cache_seconds: int = 60) -> bool:
        """
        Check if this bot is allowed to trade.

        Checks Solomon kill switch status. Results are cached to avoid
        excessive database queries.

        Args:
            cache_seconds: How long to cache the kill switch check

        Returns:
            True if trading is allowed, False if kill switch is active
        """
        if not self._solomon_enabled:
            return True

        solomon = _get_solomon()
        if not solomon:
            return True  # Allow trading if Solomon is not available

        # Check cache
        now = datetime.now(CENTRAL_TZ)
        if (self._solomon_kill_check_time and
            self._solomon_kill_check_cache is not None and
            (now - self._solomon_kill_check_time).total_seconds() < cache_seconds):
            return not self._solomon_kill_check_cache

        # Query kill switch status
        try:
            is_killed = solomon.is_bot_killed(self._solomon_bot_name)
            self._solomon_kill_check_cache = is_killed
            self._solomon_kill_check_time = now

            if is_killed:
                logger.warning(f"{self._solomon_bot_name}: Kill switch is ACTIVE - trading blocked")

            return not is_killed
        except Exception as e:
            logger.debug(f"{self._solomon_bot_name}: Could not check kill switch: {e}")
            return True  # Allow trading on error

    def solomon_record_outcome(
        self,
        trade_date: str,
        outcome: str,
        pnl: float,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Record a trade outcome to Solomon for feedback loop.

        Args:
            trade_date: Date of the trade (YYYY-MM-DD)
            outcome: Outcome type (MAX_PROFIT, PUT_BREACHED, CALL_BREACHED, LOSS, etc.)
            pnl: Realized P&L from the trade
            metadata: Additional metadata about the trade

        Returns:
            True if recorded successfully
        """
        if not self._solomon_enabled:
            return False

        solomon = _get_solomon()
        if not solomon:
            return False

        try:
            from quant.solomon_feedback_loop import ActionType

            solomon.log_action(
                bot_name=self._solomon_bot_name,
                action_type=ActionType.OUTCOME_RECORDED,
                description=f"Trade outcome: {outcome} (${pnl:+,.2f})",
                reason=f"Trade closed on {trade_date}",
                justification={
                    'outcome': outcome,
                    'pnl': pnl,
                    'trade_date': trade_date,
                    **(metadata or {})
                }
            )

            logger.info(f"{self._solomon_bot_name}: Outcome recorded to Solomon: {outcome} ${pnl:+,.2f}")
            return True
        except Exception as e:
            logger.debug(f"{self._solomon_bot_name}: Could not record outcome to Solomon: {e}")
            return False

    def solomon_log_decision(
        self,
        decision_type: str,
        description: str,
        reason: str = "",
        context: Dict[str, Any] = None
    ) -> bool:
        """
        Log a trading decision to Solomon audit log.

        Args:
            decision_type: Type of decision (ENTRY, EXIT, SKIP, etc.)
            description: Human-readable description
            reason: Why this decision was made
            context: Additional context data

        Returns:
            True if logged successfully
        """
        if not self._solomon_enabled:
            return False

        solomon = _get_solomon()
        if not solomon:
            return False

        try:
            from quant.solomon_feedback_loop import ActionType

            solomon.log_action(
                bot_name=self._solomon_bot_name,
                action_type=ActionType.FEEDBACK_LOOP_RUN,  # Generic action
                description=f"{decision_type}: {description}",
                reason=reason,
                justification=context or {}
            )
            return True
        except Exception as e:
            logger.debug(f"{self._solomon_bot_name}: Could not log decision to Solomon: {e}")
            return False

    def solomon_get_active_version(self) -> Optional[str]:
        """
        Get the currently active model version for this bot.

        Returns:
            Version string or None if not available
        """
        solomon = _get_solomon()
        if not solomon:
            return None

        try:
            version_info = solomon._get_active_version_info(self._solomon_bot_name)
            if version_info:
                return version_info.get('version_number')
            return None
        except Exception as e:
            logger.debug(f"{self._solomon_bot_name}: Could not get active version: {e}")
            return None

    def solomon_record_performance(self) -> bool:
        """
        Record a performance snapshot for this bot.

        Returns:
            True if recorded successfully
        """
        solomon = _get_solomon()
        if not solomon:
            return False

        try:
            snapshot_id = solomon.record_performance_snapshot(self._solomon_bot_name)
            return snapshot_id is not None
        except Exception as e:
            logger.debug(f"{self._solomon_bot_name}: Could not record performance: {e}")
            return False


# Convenience function for bots that don't use the mixin
def check_solomon_kill_switch(bot_name: str) -> bool:
    """
    Check if a bot's kill switch is active.

    Args:
        bot_name: The bot identifier

    Returns:
        True if kill switch is active (trading should stop)
    """
    solomon = _get_solomon()
    if not solomon:
        return False  # Allow trading if Solomon not available

    try:
        return solomon.is_bot_killed(bot_name)
    except Exception:
        return False


def record_bot_outcome(
    bot_name: str,
    trade_date: str,
    outcome: str,
    pnl: float,
    metadata: Dict[str, Any] = None
) -> bool:
    """
    Record a trade outcome to Solomon.

    Args:
        bot_name: The bot identifier
        trade_date: Date of the trade (YYYY-MM-DD)
        outcome: Outcome type
        pnl: Realized P&L
        metadata: Additional metadata

    Returns:
        True if recorded successfully
    """
    solomon = _get_solomon()
    if not solomon:
        return False

    try:
        from quant.solomon_feedback_loop import ActionType

        solomon.log_action(
            bot_name=bot_name,
            action_type=ActionType.OUTCOME_RECORDED,
            description=f"Trade outcome: {outcome} (${pnl:+,.2f})",
            reason=f"Trade closed on {trade_date}",
            justification={
                'outcome': outcome,
                'pnl': pnl,
                'trade_date': trade_date,
                **(metadata or {})
            }
        )
        return True
    except Exception:
        return False
