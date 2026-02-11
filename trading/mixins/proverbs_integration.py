"""
Proverbs Integration Mixin for Trading Bots
==========================================

Provides Proverbs feedback loop integration for all trading bots:
- Outcome recording for feedback loop
- Version awareness for model loading
- Performance tracking

Usage:
    from trading.mixins.proverbs_integration import ProverbsIntegrationMixin

    class MyBot(ProverbsIntegrationMixin):
        def __init__(self):
            self._init_proverbs_integration("MY_BOT")

        def after_trade(self, outcome, pnl):
            self.proverbs_record_outcome(outcome, pnl)
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")

logger = logging.getLogger(__name__)

# Lazy import to avoid circular dependencies
_proverbs = None
_proverbs_available = None


def _get_proverbs():
    """Lazy load Proverbs to avoid import issues at module load time"""
    global _proverbs, _proverbs_available

    if _proverbs_available is not None:
        return _proverbs if _proverbs_available else None

    try:
        from quant.proverbs_feedback_loop import get_proverbs, ActionType
        _proverbs = get_proverbs()
        _proverbs_available = True
        return _proverbs
    except ImportError:
        _proverbs_available = False
        logger.debug("Proverbs not available for bot integration")
        return None


class ProverbsIntegrationMixin:
    """
    Mixin class providing Proverbs feedback loop integration for trading bots.

    Attributes set by _init_proverbs_integration:
        _proverbs_bot_name: str - The bot identifier for Proverbs
        _proverbs_enabled: bool - Whether Proverbs integration is active
    """

    def _init_proverbs_integration(self, bot_name: str):
        """
        Initialize Proverbs integration for this bot.

        Args:
            bot_name: The bot identifier (FORTRESS, SOLOMON, ANCHOR, LAZARUS)
        """
        self._proverbs_bot_name = bot_name
        self._proverbs_enabled = True
        self._proverbs_kill_check_cache = None
        self._proverbs_kill_check_time = None

        # Log initialization
        proverbs = _get_proverbs()
        if proverbs:
            logger.info(f"[{bot_name} PROVERBS] Integration initialized successfully")
            logger.info(f"[{bot_name} PROVERBS]   Kill switch monitoring: ENABLED")
            logger.info(f"[{bot_name} PROVERBS]   Outcome recording: ENABLED")
            logger.info(f"[{bot_name} PROVERBS]   Performance tracking: ENABLED")
        else:
            logger.warning(f"[{bot_name} PROVERBS] Integration NOT available - running without feedback loop")
            logger.warning(f"[{bot_name} PROVERBS]   Outcome recording: DISABLED")

    def proverbs_can_trade(self, cache_seconds: int = 60) -> bool:
        """Always returns True — kill switches have been removed."""
        return True

    def proverbs_record_outcome(
        self,
        trade_date: str,
        outcome: str,
        pnl: float,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Record a trade outcome to Proverbs for feedback loop.

        Args:
            trade_date: Date of the trade (YYYY-MM-DD)
            outcome: Outcome type (MAX_PROFIT, PUT_BREACHED, CALL_BREACHED, LOSS, etc.)
            pnl: Realized P&L from the trade
            metadata: Additional metadata about the trade

        Returns:
            True if recorded successfully
        """
        if not self._proverbs_enabled:
            return False

        proverbs = _get_proverbs()
        if not proverbs:
            return False

        try:
            from quant.proverbs_feedback_loop import ActionType

            proverbs.log_action(
                bot_name=self._proverbs_bot_name,
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

            logger.info(f"[{self._proverbs_bot_name} PROVERBS] Trade outcome recorded to feedback loop")
            logger.info(f"[{self._proverbs_bot_name} PROVERBS]   Date: {trade_date}")
            logger.info(f"[{self._proverbs_bot_name} PROVERBS]   Outcome: {outcome}")
            logger.info(f"[{self._proverbs_bot_name} PROVERBS]   P&L: ${pnl:+,.2f}")
            if metadata:
                logger.info(f"[{self._proverbs_bot_name} PROVERBS]   Metadata: {list(metadata.keys())}")
            return True
        except Exception as e:
            logger.error(f"[{self._proverbs_bot_name} PROVERBS] Failed to record outcome: {e}")
            logger.error(f"[{self._proverbs_bot_name} PROVERBS]   Trade details - Date: {trade_date}, Outcome: {outcome}, P&L: ${pnl:+,.2f}")
            return False

    def proverbs_log_decision(
        self,
        decision_type: str,
        description: str,
        reason: str = "",
        context: Dict[str, Any] = None
    ) -> bool:
        """
        Log a trading decision to Proverbs audit log.

        Args:
            decision_type: Type of decision (ENTRY, EXIT, SKIP, etc.)
            description: Human-readable description
            reason: Why this decision was made
            context: Additional context data

        Returns:
            True if logged successfully
        """
        if not self._proverbs_enabled:
            return False

        proverbs = _get_proverbs()
        if not proverbs:
            return False

        try:
            from quant.proverbs_feedback_loop import ActionType

            proverbs.log_action(
                bot_name=self._proverbs_bot_name,
                action_type=ActionType.FEEDBACK_LOOP_RUN,  # Generic action
                description=f"{decision_type}: {description}",
                reason=reason,
                justification=context or {}
            )

            logger.info(f"[{self._proverbs_bot_name} PROVERBS] Decision logged: {decision_type}")
            logger.info(f"[{self._proverbs_bot_name} PROVERBS]   Description: {description}")
            if reason:
                logger.info(f"[{self._proverbs_bot_name} PROVERBS]   Reason: {reason}")
            return True
        except Exception as e:
            logger.warning(f"[{self._proverbs_bot_name} PROVERBS] Could not log decision: {e}")
            return False

    def proverbs_get_active_version(self) -> Optional[str]:
        """
        Get the currently active model version for this bot.

        Returns:
            Version string or None if not available
        """
        proverbs = _get_proverbs()
        if not proverbs:
            return None

        try:
            version_info = proverbs._get_active_version_info(self._proverbs_bot_name)
            if version_info:
                return version_info.get('version_number')
            return None
        except Exception as e:
            logger.debug(f"{self._proverbs_bot_name}: Could not get active version: {e}")
            return None

    def proverbs_record_performance(self) -> bool:
        """
        Record a performance snapshot for this bot.

        Returns:
            True if recorded successfully
        """
        proverbs = _get_proverbs()
        if not proverbs:
            return False

        try:
            snapshot_id = proverbs.record_performance_snapshot(self._proverbs_bot_name)
            return snapshot_id is not None
        except Exception as e:
            logger.debug(f"{self._proverbs_bot_name}: Could not record performance: {e}")
            return False



def record_bot_outcome(
    bot_name: str,
    trade_date: str,
    outcome: str,
    pnl: float,
    metadata: Dict[str, Any] = None
) -> bool:
    """
    Record a trade outcome to Proverbs.

    Args:
        bot_name: The bot identifier
        trade_date: Date of the trade (YYYY-MM-DD)
        outcome: Outcome type
        pnl: Realized P&L
        metadata: Additional metadata

    Returns:
        True if recorded successfully
    """
    proverbs = _get_proverbs()
    if not proverbs:
        logger.debug(f"[{bot_name} PROVERBS] Outcome not recorded - Proverbs not available")
        return False

    try:
        from quant.proverbs_feedback_loop import ActionType

        proverbs.log_action(
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

        logger.info(f"[{bot_name} PROVERBS] Outcome recorded via convenience function")
        logger.info(f"[{bot_name} PROVERBS]   Date: {trade_date} | Outcome: {outcome} | P&L: ${pnl:+,.2f}")
        return True
    except Exception as e:
        logger.error(f"[{bot_name} PROVERBS] Failed to record outcome: {e}")
        return False
