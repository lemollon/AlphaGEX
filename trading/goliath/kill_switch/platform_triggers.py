"""Platform-level kill-switch triggers (P-K1, P-K2, P-K3, P-K4).

Master spec section 6:
    P-K1  Platform drawdown > 15%% of GOLIATH allocation
    P-K2  Single-trade loss > 1.5x defined max
    P-K3  VIX > 35 sustained 3+ days
    P-K4  Trading Volatility API down > 24 hours

Each evaluate function takes primitive aggregated stats. A returned
KillEvent has scope=PLATFORM and instance_name=None -- the kill applies
to all 5 instances.
"""
from __future__ import annotations

from typing import Optional

from .state import KillEvent, KillScope

PLATFORM_DRAWDOWN_THRESHOLD = 0.15
SINGLE_TRADE_LOSS_MULTIPLIER = 1.5
VIX_LEVEL_THRESHOLD = 35.0
VIX_SUSTAINED_DAYS_THRESHOLD = 3
TV_API_DOWN_HOURS_THRESHOLD = 24


def evaluate_platform_drawdown(platform_drawdown_pct: float) -> Optional[KillEvent]:
    """P-K1: platform drawdown > 15%%."""
    if platform_drawdown_pct <= PLATFORM_DRAWDOWN_THRESHOLD:
        return None
    return KillEvent(
        scope=KillScope.PLATFORM,
        instance_name=None,
        trigger_id="P-K1",
        reason=(
            f"Platform drawdown {platform_drawdown_pct * 100:.1f}%% "
            f"> {PLATFORM_DRAWDOWN_THRESHOLD * 100:.0f}%%"
        ),
        context={
            "platform_drawdown_pct": float(platform_drawdown_pct),
            "threshold": PLATFORM_DRAWDOWN_THRESHOLD,
        },
    )


def evaluate_single_trade_loss(
    last_trade_loss_dollars: float,
    last_trade_defined_max: float,
) -> Optional[KillEvent]:
    """P-K2: a single trade lost more than 1.5x its defined max.

    Args:
        last_trade_loss_dollars: realized loss as a positive number
            (i.e. abs(P&L)). Pass 0 if last trade was a winner.
        last_trade_defined_max: defined-max-loss for that trade.
    """
    if last_trade_defined_max <= 0:
        return None
    if last_trade_loss_dollars <= 0:
        return None
    threshold = SINGLE_TRADE_LOSS_MULTIPLIER * last_trade_defined_max
    if last_trade_loss_dollars <= threshold:
        return None
    return KillEvent(
        scope=KillScope.PLATFORM,
        instance_name=None,
        trigger_id="P-K2",
        reason=(
            f"Single trade loss \\${last_trade_loss_dollars:.2f} > "
            f"{SINGLE_TRADE_LOSS_MULTIPLIER}x defined max "
            f"\\${last_trade_defined_max:.2f} (threshold \\${threshold:.2f})"
        ),
        context={
            "last_trade_loss_dollars": float(last_trade_loss_dollars),
            "last_trade_defined_max": float(last_trade_defined_max),
            "threshold_multiplier": SINGLE_TRADE_LOSS_MULTIPLIER,
            "threshold_dollars": threshold,
        },
    )


def evaluate_vix_sustained(
    current_vix: float,
    days_above_threshold: int,
) -> Optional[KillEvent]:
    """P-K3: VIX > 35 for 3+ consecutive days.

    Args:
        current_vix: latest VIX print
        days_above_threshold: consecutive days (including today) where
            VIX has been above VIX_LEVEL_THRESHOLD.
    """
    if current_vix <= VIX_LEVEL_THRESHOLD:
        return None
    if days_above_threshold < VIX_SUSTAINED_DAYS_THRESHOLD:
        return None
    return KillEvent(
        scope=KillScope.PLATFORM,
        instance_name=None,
        trigger_id="P-K3",
        reason=(
            f"VIX {current_vix:.2f} > {VIX_LEVEL_THRESHOLD} sustained "
            f"{days_above_threshold} days >= {VIX_SUSTAINED_DAYS_THRESHOLD}"
        ),
        context={
            "current_vix": float(current_vix),
            "days_above_threshold": int(days_above_threshold),
            "vix_threshold": VIX_LEVEL_THRESHOLD,
            "days_threshold": VIX_SUSTAINED_DAYS_THRESHOLD,
        },
    )


def evaluate_tv_api_down(tv_api_down_hours: float) -> Optional[KillEvent]:
    """P-K4: TV API unreachable > 24 hours."""
    if tv_api_down_hours <= TV_API_DOWN_HOURS_THRESHOLD:
        return None
    return KillEvent(
        scope=KillScope.PLATFORM,
        instance_name=None,
        trigger_id="P-K4",
        reason=(
            f"TV API down {tv_api_down_hours:.1f}h > "
            f"{TV_API_DOWN_HOURS_THRESHOLD}h"
        ),
        context={
            "tv_api_down_hours": float(tv_api_down_hours),
            "threshold_hours": TV_API_DOWN_HOURS_THRESHOLD,
        },
    )
