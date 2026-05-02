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
    strict: bool = False,
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
        strict: If True, BLOCK trades when margin system is unavailable.
                Use strict=True for leveraged products (futures, perpetuals)
                where trading without margin checks risks liquidation.
                Use strict=False (default) for options/spot where max loss
                is defined at entry.

    Returns:
        Tuple of (approved: bool, reason: str)
        If approved is False, reason explains why.

    Note:
        When strict=False (default): margin system errors allow the trade
        through to avoid blocking when margin tracking isn't loaded.
        When strict=True: margin system errors BLOCK the trade. This is
        the correct behavior for futures/perpetuals where you can lose
        more than your account balance if margin isn't tracked.
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
            if strict:
                logger.warning(
                    f"MARGIN BLOCKED {bot_name}: margin data unavailable "
                    f"(strict mode - cannot trade without margin verification)"
                )
                return False, "margin_data_unavailable_strict"
            logger.debug(f"Margin check unavailable for {bot_name} - allowing trade")
            return True, "margin_data_unavailable"

        if result["approved"]:
            logger.info(
                f"MARGIN APPROVED {bot_name}: {side} {quantity} {symbol} @ "
                f"${entry_price:,.2f} | usage={result['new_margin_usage_pct']:.1f}%"
            )
            return True, "approved"
        else:
            logger.warning(
                f"MARGIN REJECTED {bot_name}: {result['reason']}"
            )
            return False, result["reason"]

    except ImportError:
        if strict:
            logger.error(
                f"MARGIN BLOCKED {bot_name}: margin module not installed "
                f"(strict mode - cannot trade leveraged products without margin system)"
            )
            return False, "margin_module_not_available_strict"
        logger.debug("Margin module not available - allowing trade")
        return True, "margin_module_not_available"
    except Exception as e:
        if strict:
            logger.error(
                f"MARGIN BLOCKED {bot_name}: margin check error: {e} "
                f"(strict mode - cannot trade leveraged products without margin verification)"
            )
            return False, f"margin_check_error_strict: {e}"
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


def current_margin_usage_pct(
    bot_name: str,
    perp_symbol: str,
    open_positions: list,
    account_equity: float,
    current_price: Optional[float] = None,
) -> Optional[float]:
    """Compute current margin usage % across all open perp positions.

    Mirrors the math used by the per-bot /margin endpoint so the trader
    sees the same number the dashboard does. Returns None if the margin
    spec for this perp can't be found (caller should fail open).
    """
    try:
        from trading.shared.margin_engine import MarginCalculator
        from trading.shared.margin_config import PERPETUAL_MARGIN_SPECS

        spec = PERPETUAL_MARGIN_SPECS.get(perp_symbol, {})
        if not spec:
            return None
        if not open_positions or account_equity <= 0:
            return 0.0

        position_margins = []
        for pos in open_positions:
            pos_price = current_price or pos.get("entry_price", 0)
            if not pos_price:
                continue
            leverage = pos.get("leverage_at_entry") or spec.get("default_leverage", 10)
            result = MarginCalculator.calculate_perpetual_margin(
                entry_price=pos["entry_price"],
                current_price=pos_price,
                quantity=pos.get("quantity", 0),
                side=pos.get("side", "long"),
                leverage=leverage,
                margin_mode="isolated",
                maintenance_margin_rate=spec.get("maintenance_margin_rate", 0.004),
                account_equity=account_equity,
                funding_rate=pos.get("funding_rate_at_entry", 0) or 0,
                funding_interval_hours=spec.get("funding_interval_hours", 8),
            )
            position_margins.append(result)

        if not position_margins:
            return 0.0
        summary = MarginCalculator.aggregate_positions(
            position_margins, account_equity, "crypto_perp"
        )
        return float(summary.get("margin_usage_pct", 0.0))
    except Exception as e:
        logger.debug(f"current_margin_usage_pct({bot_name}) failed: {e}")
        return None


def is_margin_over_threshold(
    bot_name: str,
    perp_symbol: str,
    open_positions: list,
    account_equity: float,
    threshold_pct: float = 70.0,
    current_price: Optional[float] = None,
) -> Tuple[bool, float]:
    """True if current margin usage already exceeds the open-new-trades cap.

    Returns (blocked, current_usage_pct). On computation failure returns
    (False, 0.0) — fail open so a transient error never freezes the bot,
    while still surfacing the call site that asked.
    """
    usage = current_margin_usage_pct(
        bot_name=bot_name,
        perp_symbol=perp_symbol,
        open_positions=open_positions,
        account_equity=account_equity,
        current_price=current_price,
    )
    if usage is None:
        return False, 0.0
    return usage >= threshold_pct, usage
