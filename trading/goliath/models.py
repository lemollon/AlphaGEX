"""GOLIATH dataclasses and enums.

Phase 1.5 minimal scope: GoliathConfig with the 4 calibration parameters
that Phase 1.5 calibration empirically validates. Subsequent phases will
fill out additional fields (see Doc 3 Phase 6 for the full target shape).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GoliathConfig:
    """Per-instance GOLIATH configuration.

    A GOLIATH "instance" is a tuple (LETF, underlying) — e.g.
    GOLIATH-MSTU trades MSTU options using GEX data from MSTR.

    Phase 1.5 deliverable: this dataclass exists with its 4 calibration
    parameters at spec defaults. The Phase 1.5 calibration script reports
    whether these defaults are empirically supported. If [CALIB-ADJUST]
    tags emerge, the defaults below get updated in a follow-up commit.
    """

    instance_name: str       # e.g. "GOLIATH-MSTU"
    letf_ticker: str         # e.g. "MSTU"
    underlying_ticker: str   # e.g. "MSTR"
    leverage: float = 2.0    # Daily leverage of the LETF (all current instances are 2x)

    # ---- Calibration parameters (Phase 1.5 validates these) ----

    # Wall concentration threshold for "is this a wall?" classification.
    # Per spec: a wall is gamma >= 2x median of strikes within +/- 5% of spot.
    # Lower the threshold → more strikes classified as walls (more setups).
    wall_concentration_threshold: float = 2.0

    # Tracking-error fudge factor in the LETF strike-mapping algorithm.
    # Per spec formula: tracking_error = leverage * sigma * sqrt(t) * sqrt(2/3) * fudge
    # Lower fudge → tighter strike target band (more selective).
    tracking_error_fudge: float = 0.1

    # Volatility-drag scaling coefficient. Spec formula gives theoretical drag of
    # -0.5 * L * (L-1) * sigma^2 * t. This coefficient multiplies that to match
    # observed drag; 1.0 means theory matches reality. If observed drag is e.g.
    # 1.2x theoretical, set this to 1.2.
    drag_coefficient: float = 1.0

    # Window length (in trading days) for realized-vol calculations used by
    # strike mapping and the drag formula.
    realized_vol_window_days: int = 30
