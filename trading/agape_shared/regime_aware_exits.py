# trading/agape_shared/regime_aware_exits.py
"""Pure-function exit decision used by every AGAPE perp/futures bot when
its `use_regime_aware_exits` flag is on.

Mirrors trader._manage_no_loss_trailing's exit-priority order, but driven
by an ExitProfile (one per regime) and adds an MFE-giveback exit between
the existing trail-stop and the funding/time-based exits. State is passed
in as a plain dict so this stays unit-testable without a live DB.

Priority (first-match-wins):
  1. MAX_LOSS / EMERGENCY_STOP      (hard stops)
  2. PROFIT_TARGET                   (chop only — trend disables with 0)
  3. TRAIL_STOP                      (existing armed trail hit)
  4. MFE_GIVEBACK                    (NEW — closes when N% of peak gain bled back)
  5. MAX_HOLD_TIME                   (deadline)
  6. ARM_TRAIL or UPDATE_TRAIL       (if max_profit_pct crossed activation)
  7. NONE                            (no action this tick)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from trading.agape_shared.exit_profile import ExitProfile


# Don't fire MFE-giveback on noise — the run-up has to be at least this big.
_MFE_GIVEBACK_MIN_PCT = 0.5


class ExitAction(str, Enum):
    NONE = "none"
    CLOSE = "close"
    ARM_TRAIL = "arm_trail"
    UPDATE_TRAIL = "update_trail"


@dataclass
class ExitDecision:
    action: ExitAction
    reason: str = ""
    close_price: Optional[float] = None     # set for CLOSE
    new_stop: Optional[float] = None        # set for ARM_TRAIL / UPDATE_TRAIL


def _profit_pct(side: str, entry: float, current: float) -> float:
    if entry <= 0:
        return 0.0
    direction = 1.0 if side == "long" else -1.0
    return ((current - entry) / entry) * 100.0 * direction


def _max_profit_pct(side: str, entry: float, hwm: float) -> float:
    """% of peak favorable excursion since open."""
    if entry <= 0:
        return 0.0
    if side == "long":
        return max(0.0, (hwm - entry) / entry * 100.0)
    return max(0.0, (entry - hwm) / entry * 100.0)


def _giveback_floor(side: str, entry: float, hwm: float, giveback_pct: float) -> float:
    """The price level at which `giveback_pct` of the MFE has bled back."""
    if side == "long":
        return entry + (hwm - entry) * (1.0 - giveback_pct / 100.0)
    return entry - (entry - hwm) * (1.0 - giveback_pct / 100.0)


def evaluate_exit(state: Mapping[str, Any], profile: ExitProfile) -> ExitDecision:
    side = state["side"]
    entry = float(state["entry_price"])
    current = float(state["current_price"])
    hwm = float(state.get("high_water_mark") or entry)
    if hwm <= 0:
        hwm = entry
    open_age_hours = float(state.get("open_age_hours") or 0.0)
    trailing_active = bool(state.get("trailing_active") or False)
    current_stop = state.get("current_stop")

    profit_pct = _profit_pct(side, entry, current)
    max_profit_pct = _max_profit_pct(side, entry, hwm)

    # 1. MAX LOSS / EMERGENCY STOP
    if -profit_pct >= profile.max_unrealized_loss_pct:
        return ExitDecision(
            ExitAction.CLOSE,
            reason=f"MAX_LOSS_{profile.max_unrealized_loss_pct}pct",
            close_price=current,
        )
    if -profit_pct >= profile.emergency_stop_pct:
        return ExitDecision(ExitAction.CLOSE, reason="EMERGENCY_STOP", close_price=current)

    # 2. PROFIT TARGET (only when set)
    if profile.profit_target_pct > 0.0 and profit_pct >= profile.profit_target_pct:
        return ExitDecision(
            ExitAction.CLOSE,
            reason=f"PROFIT_TARGET_+{profit_pct:.2f}pct",
            close_price=current,
        )

    # 3. TRAIL STOP HIT
    if trailing_active and current_stop is not None:
        cs = float(current_stop)
        hit = (side == "long" and current <= cs) or (side != "long" and current >= cs)
        if hit:
            return ExitDecision(
                ExitAction.CLOSE,
                reason=f"TRAIL_STOP_+{profit_pct:.2f}pct",
                close_price=cs,
            )

    # 4. MFE GIVEBACK (new). Only if MFE was meaningful and giveback enabled.
    if profile.mfe_giveback_pct > 0.0 and max_profit_pct >= _MFE_GIVEBACK_MIN_PCT:
        floor = _giveback_floor(side, entry, hwm, profile.mfe_giveback_pct)
        below_floor = (side == "long" and current < floor) or (side != "long" and current > floor)
        if below_floor:
            return ExitDecision(
                ExitAction.CLOSE,
                reason=f"MFE_GIVEBACK_{int(profile.mfe_giveback_pct)}pct_of_+{max_profit_pct:.2f}pct",
                close_price=current,
            )

    # 5. MAX HOLD
    if open_age_hours >= profile.max_hold_hours:
        return ExitDecision(ExitAction.CLOSE, reason="MAX_HOLD_TIME", close_price=current)

    # 6a. ARM TRAIL on first cross of activation
    if (not trailing_active) and max_profit_pct >= profile.activation_pct:
        trail_dist = entry * (profile.trail_distance_pct / 100.0)
        if side == "long":
            new_stop = max(entry, hwm - trail_dist)
            # Only arm if current is above the stop; otherwise current already
            # violated the stop (price pulled back while below min MFE) — skip.
            if current >= new_stop:
                return ExitDecision(ExitAction.ARM_TRAIL, new_stop=new_stop)
        else:
            new_stop = min(entry, hwm + trail_dist)
            if current <= new_stop:
                return ExitDecision(ExitAction.ARM_TRAIL, new_stop=new_stop)

    # 6b. UPDATE TRAIL (move stop closer to hwm if it improved)
    if trailing_active:
        trail_dist = entry * (profile.trail_distance_pct / 100.0)
        if side == "long":
            new_stop = hwm - trail_dist
            if new_stop > (current_stop or 0) and new_stop >= entry:
                return ExitDecision(ExitAction.UPDATE_TRAIL, new_stop=new_stop)
        else:
            new_stop = hwm + trail_dist
            if current_stop is not None and new_stop < current_stop and new_stop <= entry:
                return ExitDecision(ExitAction.UPDATE_TRAIL, new_stop=new_stop)

    return ExitDecision(ExitAction.NONE)
