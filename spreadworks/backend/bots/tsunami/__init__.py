"""TSUNAMI — defined-risk put credit spreads + long calls on leveraged single-name ETFs.

Multi-instance research bot. Five instances (TSUNAMI-MSTU, TSUNAMI-TSLL,
TSUNAMI-NVDL, TSUNAMI-CONL, TSUNAMI-AMDL) trade options on leveraged ETFs
while consuming GEX data from the underlying stocks (MSTR, TSLA, NVDA, COIN, AMD).

Phase status (as of Apr 2026):
    Phase 0   complete: investigation, spec deltas, implementation plan
    Phase 1   complete: TV v2 client + coverage smoke test (6/6 PASS)
    Phase 1.5 in progress: calibration of spec parameters
    Phase 2+  pending

Public exports:
    TsunamiConfig — per-instance configuration dataclass
    TSUNAMI_INSTANCES — registry of the 5 LETF instances (added in Phase 6)
"""

from .models import TsunamiConfig

__all__ = ["TsunamiConfig"]
