"""GOLIATH strike mapping package — Phase 2.

Per master spec section 3, this package translates an underlying gamma
wall into a 3-leg LETF structure (short put, long put, long call).

Modules (built in order):
    wall_finder  — Step 1: find qualifying gamma wall on the underlying
    letf_mapper  — Step 2: translate underlying wall price to LETF target
    leg_builder  — Build the 3-leg structure from the LETF target strike
    engine       — Orchestrator returning a TradeStructure or None

Calibration values come from GoliathConfig (Phase 1.5 dataclass).
"""
from .wall_finder import GammaStrike, Wall, find_wall

__all__ = ["GammaStrike", "Wall", "find_wall"]
