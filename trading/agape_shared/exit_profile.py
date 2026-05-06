"""ExitProfile dataclass — the per-regime knobs each AGAPE perp/futures bot
selects between at trade entry. See
docs/superpowers/specs/2026-05-05-regime-aware-perp-exits-design.md.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields
from typing import Any, Dict


@dataclass
class ExitProfile:
    activation_pct: float
    trail_distance_pct: float
    profit_target_pct: float        # 0.0 disables the hard target (rides for trend)
    mfe_giveback_pct: float         # 0..100; 0 disables the giveback exit
    max_hold_hours: int
    max_unrealized_loss_pct: float
    emergency_stop_pct: float = 5.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExitProfile":
        names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in d.items() if k in names}
        return cls(**kwargs)


def default_chop_profile() -> ExitProfile:
    """Initial chop defaults from the design spec §2 table."""
    return ExitProfile(
        activation_pct=0.3,
        trail_distance_pct=0.15,
        profit_target_pct=1.0,
        mfe_giveback_pct=40.0,
        max_hold_hours=6,
        max_unrealized_loss_pct=1.5,
        emergency_stop_pct=5.0,
    )


def default_trend_profile() -> ExitProfile:
    """Initial trend defaults from the design spec §2 table."""
    return ExitProfile(
        activation_pct=0.7,
        trail_distance_pct=0.5,
        profit_target_pct=0.0,
        mfe_giveback_pct=60.0,
        max_hold_hours=24,
        max_unrealized_loss_pct=2.5,
        emergency_stop_pct=5.0,
    )
