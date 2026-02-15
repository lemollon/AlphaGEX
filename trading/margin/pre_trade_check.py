"""
Pre-Trade Margin Check Integration.

Provides a simple function that existing bot execution code can call
BEFORE placing any order. This is additive - it wraps around existing
trade logic without modifying it.

Usage in any bot executor:
    from trading.margin.pre_trade_check import check_margin_before_trade

    # Before executing:
    approved, reason = check_margin_before_trade(
        bot_name="AGAPE_BTC_PERP",
        symbol="BTC-PERP",
        side="long",
        quantity=0.001,
        entry_price=100000.0,
    )
    if not approved:
        logger.warning(f"Trade rejected by margin check: {reason}")
        return None
    # ... proceed with existing execution logic
"""

import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


def check_margin_before_trade(
    bot_name: str,
    symbol: str,
    side: str,
    quantity: float,
    entry_price: float,
    leverage: Optional[float] = None,
    account_equity: Optional[float] = None,
) -> Tuple[bool, str]:
    """Check if a proposed trade passes margin requirements.

    This is the primary integration point for existing bot code.
    Call this BEFORE placing any order.

    Args:
        bot_name: The bot identifier (e.g., 'AGAPE_BTC_PERP')
        symbol: Trading symbol (e.g., 'BTC-PERP', 'ES')
        side: 'long' or 'short'
        quantity: Position size
        entry_price: Expected entry price
        leverage: Optional leverage override (for perps)
        account_equity: Optional equity override

    Returns:
        Tuple of (approved: bool, reason: str)
        If approved is False, reason explains why.

    Note:
        If margin system is unavailable, returns (True, "margin_system_unavailable")
        to avoid blocking trades when margin tracking isn't loaded.
    """
    try:
        from trading.margin.margin_monitor import get_margin_monitor

        monitor = get_margin_monitor(enabled=False)  # Don't start polling
        proposed = {
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": entry_price,
            "leverage": leverage,
        }

        result = monitor.check_margin_for_trade(
            bot_name, proposed, account_equity=account_equity
        )

        if result is None:
            # Margin system can't determine - allow trade but warn
            logger.debug(f"Margin check unavailable for {bot_name} - allowing trade")
            return True, "margin_data_unavailable"

        if result["approved"]:
            logger.debug(
                f"Margin check APPROVED for {bot_name}: "
                f"usage={result['new_margin_usage_pct']:.1f}%"
            )
            return True, "approved"
        else:
            logger.warning(
                f"Margin check REJECTED for {bot_name}: {result['reason']}"
            )
            return False, result["reason"]

    except ImportError:
        # Margin module not installed - allow trade
        logger.debug("Margin module not available - allowing trade")
        return True, "margin_module_not_available"
    except Exception as e:
        # Never block trades due to margin system errors
        logger.warning(f"Margin check error for {bot_name}: {e} - allowing trade")
        return True, f"margin_check_error: {e}"


def get_position_liquidation_price(
    bot_name: str,
    side: str,
    entry_price: float,
    quantity: float,
    account_equity: Optional[float] = None,
) -> Optional[float]:
    """Calculate the liquidation price for a position.

    Utility function for bots that want to display or track liquidation price.

    Returns:
        Liquidation price or None if not calculable
    """
    try:
        from trading.margin.margin_config import get_bot_margin_config
        from trading.margin.margin_engine import MarginEngine

        config = get_bot_margin_config(bot_name)
        if not config:
            return None

        engine = MarginEngine(config)

        if account_equity is None:
            # Try to get from monitor
            from trading.margin.margin_monitor import get_margin_monitor
            monitor = get_margin_monitor(enabled=False)
            metrics = monitor.get_bot_margin_metrics(bot_name)
            if metrics:
                account_equity = metrics.account_equity
            else:
                return None

        return engine.calc_liquidation_price(
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            account_equity=account_equity,
            total_maintenance_margin_other=0.0,
        )
    except Exception as e:
        logger.debug(f"Could not calculate liquidation price: {e}")
        return None
