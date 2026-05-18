"""GOLIATH platform-wide settings.

[GOLIATH-DELTA] yellow: kickoff prompt called for global.yaml; using a
Python module instead because pyyaml is not in requirements.txt
(workers use requirements.txt, not requirements-render.txt). The
intent and field names are preserved exactly. v0.3 todo can switch
to YAML if pyyaml lands in worker reqs.

Capital ramp (2026-05-18, paper-only): account_capital 5000 -> 25000
and platform_cap 750 -> 5000 per Leron directive to give GOLIATH more
research capital. paper_only remains True until V3-5 + Q3 sign-off.

Master spec section 5 + section 1.4 (current):
    account_capital            $25,000 paper research capital
    platform_cap               $5,000 (20%% of account)
    max_concurrent_positions   3 across all 5 instances
    paper_only                 True for v0.2 (live unlock = V3-5 + Q3 sign-off)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GlobalConfig:
    account_capital: float = 25000.0
    platform_cap: float = 5000.0
    max_concurrent_positions: int = 3
    paper_only: bool = True
    bot_guard_tag_prefix: str = "GOLIATH"


GLOBAL = GlobalConfig()
