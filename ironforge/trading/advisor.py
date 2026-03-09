"""
IronForge Advisor
==================

Lightweight, rule-based advisory system for IronForge bots.
Produces Oracle-compatible output (win_probability, confidence, advice, top_factors)
using VIX, expected move, day of week, and spot distance to strikes.

No ML models, no external dependencies — pure rules engine.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple

from .models import BotConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)


@dataclass
class AdvisorResult:
    """Oracle-compatible advisory output."""
    advice: str = "SKIP"              # TRADE_FULL, TRADE_REDUCED, SKIP
    win_probability: float = 0.5
    confidence: float = 0.5
    top_factors: List[Tuple[str, float]] = field(default_factory=list)
    reasoning: str = ""
    suggested_sd: float = 0.0         # 0 = use default


# ── Base win probability for Iron Condors ──
# Historical IC win rate with 1.2 SD strikes is roughly 65-70%.
BASE_WIN_PROBABILITY = 0.65


def evaluate(
    vix: float,
    spot: float,
    expected_move: float,
    dte_mode: str = "2DTE",
    config: BotConfig = None,
) -> AdvisorResult:
    """
    Evaluate market conditions and return an advisory result.

    Rules engine adjustments to base win probability:
    - VIX level: ideal (15-22) → +0.10, low (<15) → -0.05, elevated (22-28) → -0.05, high (>28) → -0.15
    - Day of week: Tue-Thu → +0.08, Mon → +0.03, Fri → -0.10
    - Expected move ratio: tight (<1%) → +0.08, normal (1-2%) → 0, wide (>2%) → -0.08
    - DTE factor: 2DTE → +0.03 (more decay), 1DTE → -0.02 (tighter, riskier)
    """
    now = datetime.now(CENTRAL_TZ)
    day_of_week = now.weekday()  # 0=Mon, 4=Fri

    win_prob = BASE_WIN_PROBABILITY
    factors: List[Tuple[str, float]] = []

    # ── VIX scoring ──
    if 15 <= vix <= 22:
        adj = 0.10
        factors.append(("VIX_IDEAL", adj))
    elif vix < 15:
        adj = -0.05
        factors.append(("VIX_LOW_PREMIUMS", adj))
    elif 22 < vix <= 28:
        adj = -0.05
        factors.append(("VIX_ELEVATED", adj))
    else:  # >28
        adj = -0.15
        factors.append(("VIX_HIGH_RISK", adj))
    win_prob += adj

    # ── Day of week scoring ──
    if day_of_week in (1, 2, 3):  # Tue, Wed, Thu
        adj = 0.08
        factors.append(("DAY_OPTIMAL", adj))
    elif day_of_week == 0:  # Mon
        adj = 0.03
        factors.append(("DAY_MONDAY", adj))
    elif day_of_week == 4:  # Fri
        adj = -0.10
        factors.append(("DAY_FRIDAY_RISK", adj))
    else:  # Weekend (shouldn't trade)
        adj = -0.20
        factors.append(("DAY_WEEKEND", adj))
    win_prob += adj

    # ── Expected move ratio ──
    em_ratio = (expected_move / spot * 100) if spot > 0 else 1.0
    if em_ratio < 1.0:
        adj = 0.08
        factors.append(("EM_TIGHT", adj))
    elif em_ratio <= 2.0:
        adj = 0.0
        factors.append(("EM_NORMAL", adj))
    else:
        adj = -0.08
        factors.append(("EM_WIDE", adj))
    win_prob += adj

    # ── DTE factor ──
    if dte_mode == "2DTE":
        adj = 0.03
        factors.append(("DTE_2DAY_DECAY", adj))
    elif dte_mode == "0DTE":
        adj = -0.05
        factors.append(("DTE_0DAY_AGGRESSIVE", adj))
    else:
        adj = -0.02
        factors.append(("DTE_1DAY_TIGHT", adj))
    win_prob += adj

    # Clamp to valid range
    win_prob = max(0.10, min(0.95, win_prob))

    # ── Confidence based on factor agreement ──
    positive_count = sum(1 for _, adj in factors if adj > 0)
    negative_count = sum(1 for _, adj in factors if adj < 0)
    total_factors = len(factors)

    if positive_count == total_factors:
        confidence = 0.85
    elif negative_count == total_factors:
        confidence = 0.25
    elif positive_count > negative_count:
        confidence = 0.60 + (positive_count / total_factors) * 0.20
    else:
        confidence = 0.40

    confidence = max(0.10, min(0.95, confidence))

    # ── Advice decision ──
    min_wp = config.min_win_probability if config else 0.42
    suggested_sd = 0.0

    if win_prob >= 0.60 and confidence >= 0.50:
        advice = "TRADE_FULL"
    elif win_prob >= min_wp and confidence >= 0.35:
        advice = "TRADE_REDUCED"
        # Suggest wider strikes for marginal conditions
        suggested_sd = 1.4
    else:
        advice = "SKIP"

    # ── Build reasoning string ──
    factor_strs = [f"{name}({adj:+.2f})" for name, adj in factors]
    reasoning = (
        f"Advisor: {advice} | WP={win_prob:.2f} conf={confidence:.2f} | "
        f"VIX={vix:.1f} EM={em_ratio:.2f}% DOW={day_of_week} | "
        f"Factors: {', '.join(factor_strs)}"
    )

    result = AdvisorResult(
        advice=advice,
        win_probability=round(win_prob, 4),
        confidence=round(confidence, 4),
        top_factors=factors,
        reasoning=reasoning,
        suggested_sd=suggested_sd,
    )

    logger.info(f"IronForge Advisor: {reasoning}")
    return result
