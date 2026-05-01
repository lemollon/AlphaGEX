"""Per-instance kill-switch triggers (I-K1, I-K2, I-K3).

Master spec section 6:
    I-K1  Instance drawdown > 30%% of allocation
    I-K2  5 consecutive losses on the instance
    I-K3  20 trades without an upside hit (>= +$50)

Each evaluate function takes primitive aggregated stats and returns
``Optional[KillEvent]`` -- caller is responsible for computing the
stats from closed-trade history. Decoupling keeps these unit-testable.
"""
from __future__ import annotations

from typing import Optional

from .state import KillEvent, KillScope

DRAWDOWN_THRESHOLD = 0.30
CONSECUTIVE_LOSS_THRESHOLD = 5
TRADES_WITHOUT_UPSIDE_THRESHOLD = 20
UPSIDE_HIT_DOLLARS = 50.0  # an "upside hit" is realized P&L >= +$50


def evaluate_drawdown(
    instance_name: str,
    drawdown_pct: float,
) -> Optional[KillEvent]:
    """I-K1: instance drawdown > 30%% of allocation.

    Args:
        instance_name: e.g. "GOLIATH-MSTU"
        drawdown_pct: peak-to-trough drawdown as a fraction
            (e.g. 0.35 = 35%%; spec uses strictly >, so 0.30 does not fire)
    """
    if drawdown_pct <= DRAWDOWN_THRESHOLD:
        return None
    return KillEvent(
        scope=KillScope.INSTANCE,
        instance_name=instance_name,
        trigger_id="I-K1",
        reason=(
            f"{instance_name} drawdown {drawdown_pct * 100:.1f}%% "
            f"> {DRAWDOWN_THRESHOLD * 100:.0f}%%"
        ),
        context={
            "drawdown_pct": float(drawdown_pct),
            "threshold": DRAWDOWN_THRESHOLD,
        },
    )


def evaluate_consecutive_losses(
    instance_name: str,
    consecutive_losses: int,
) -> Optional[KillEvent]:
    """I-K2: >= 5 consecutive losing trades on the instance."""
    if consecutive_losses < CONSECUTIVE_LOSS_THRESHOLD:
        return None
    return KillEvent(
        scope=KillScope.INSTANCE,
        instance_name=instance_name,
        trigger_id="I-K2",
        reason=(
            f"{instance_name} {consecutive_losses} consecutive losses "
            f">= {CONSECUTIVE_LOSS_THRESHOLD}"
        ),
        context={
            "consecutive_losses": int(consecutive_losses),
            "threshold": CONSECUTIVE_LOSS_THRESHOLD,
        },
    )


def evaluate_trades_without_upside(
    instance_name: str,
    trades_without_upside: int,
) -> Optional[KillEvent]:
    """I-K3: >= 20 consecutive trades without realized P&L >= +$50."""
    if trades_without_upside < TRADES_WITHOUT_UPSIDE_THRESHOLD:
        return None
    return KillEvent(
        scope=KillScope.INSTANCE,
        instance_name=instance_name,
        trigger_id="I-K3",
        reason=(
            f"{instance_name} {trades_without_upside} trades without "
            f">+${UPSIDE_HIT_DOLLARS:.0f} hit "
            f">= {TRADES_WITHOUT_UPSIDE_THRESHOLD}"
        ),
        context={
            "trades_without_upside": int(trades_without_upside),
            "threshold": TRADES_WITHOUT_UPSIDE_THRESHOLD,
            "upside_hit_dollars": UPSIDE_HIT_DOLLARS,
        },
    )
