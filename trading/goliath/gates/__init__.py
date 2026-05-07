"""GOLIATH entry gates G02-G10 (originally G01-G10 per master spec section 2).

G01 (spy_gex SPY-extreme-negative-gamma macro filter) was removed
2026-05-07 -- the placeholder threshold was uncalibrated and rejected
nearly every trading day.

Gate roster (run in order; first non-PASS stops the chain):
    G02 underlying_gex           -- Per-LETF underlying GEX regime check
    G03 wall_present             -- Underlying has identifiable positive
                                    gamma wall below spot (delegates to
                                    Phase 2 wall_finder)
    G04 earnings_window          -- Underlying earnings not within 7 days
    G05 iv_rank                  -- LETF IV rank >= 60 (cold-start
                                    fail-closed per spec Q6)
    G06 oi_per_leg               -- All 3 LETF legs have OI >= 200
    G07 bid_ask_per_leg          -- Bid-ask <= 20%% of mid on each leg
    G08 net_cost_ratio           -- Net cost <= 30%% of long-call mid
    G09 ma_trend                 -- Underlying above 50-day MA
    G10 platform_position_cap    -- Total open GOLIATH positions <= 3

Public API exposes the gate base types here. Each gate module is loaded
on-demand by the orchestrator (orchestrator.py).
"""
from .base import GateOutcome, GateResult

__all__ = ["GateOutcome", "GateResult"]
