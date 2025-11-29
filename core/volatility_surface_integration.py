"""
Volatility Surface Enhanced Classifier

This module integrates the volatility surface into trading decisions.
The volatility surface provides:
1. Skew information (put skew = bearish sentiment)
2. Term structure (contango/backwardation)
3. IV percentiles by strike (find cheap/expensive options)

HOW TRADERS USE THIS:
- High put skew (>5%) → Market expects downside, favor put spreads
- Flat/positive skew → Market neutral/bullish, favor call spreads
- Steep term structure → Use longer DTE (collect more theta)
- Inverted term structure → Use shorter DTE (IV likely to rise)

Author: AlphaGEX
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Import volatility surface
try:
    from utils.volatility_surface import (
        VolatilitySurface,
        SkewMetrics,
        TermStructure,
        create_surface_from_chain
    )
    VOL_SURFACE_AVAILABLE = True
except ImportError:
    VOL_SURFACE_AVAILABLE = False
    print("Warning: volatility_surface module not available")


class SkewRegime(Enum):
    """Volatility skew classification"""
    EXTREME_PUT_SKEW = "EXTREME_PUT_SKEW"    # >8% - Crash protection bid
    HIGH_PUT_SKEW = "HIGH_PUT_SKEW"          # 4-8% - Bearish sentiment
    NORMAL_SKEW = "NORMAL_SKEW"              # 1-4% - Normal equity skew
    FLAT_SKEW = "FLAT_SKEW"                  # -1% to 1% - Neutral
    CALL_SKEW = "CALL_SKEW"                  # <-1% - Bullish (rare for indices)


class TermStructureRegime(Enum):
    """IV term structure classification"""
    STEEP_CONTANGO = "STEEP_CONTANGO"        # Long DTE IV much higher
    NORMAL_CONTANGO = "NORMAL_CONTANGO"      # Typical upward slope
    FLAT = "FLAT"                            # Similar IV across DTEs
    BACKWARDATION = "BACKWARDATION"          # Short DTE IV higher (fear)
    STEEP_BACKWARDATION = "STEEP_BACKWARDATION"  # Extreme fear


@dataclass
class EnhancedVolatilityData:
    """Complete volatility data from surface analysis"""
    # Basic IV metrics
    atm_iv: float
    iv_rank: float
    iv_percentile: float

    # Skew metrics
    skew_25d: float              # 25-delta skew (put IV - call IV)
    risk_reversal: float         # Directional indicator
    butterfly: float             # Smile curvature
    skew_regime: SkewRegime

    # Term structure
    term_slope: float            # IV change per day
    term_regime: TermStructureRegime
    front_month_iv: float
    back_month_iv: float

    # Trading recommendations from surface
    recommended_dte: int         # Best DTE given term structure
    iv_percentile_at_dte: float  # Is this DTE cheap or expensive?

    def get_directional_bias(self) -> str:
        """
        Get directional bias from skew

        Returns: 'bearish', 'neutral', or 'bullish'
        """
        if self.skew_regime in [SkewRegime.EXTREME_PUT_SKEW, SkewRegime.HIGH_PUT_SKEW]:
            return 'bearish'
        elif self.skew_regime == SkewRegime.CALL_SKEW:
            return 'bullish'
        return 'neutral'

    def should_sell_premium(self) -> Tuple[bool, str]:
        """
        Determine if conditions favor selling premium

        Returns: (should_sell, reasoning)
        """
        reasons = []
        score = 0

        # High IV rank = good for selling
        if self.iv_rank > 60:
            score += 2
            reasons.append(f"IV Rank {self.iv_rank:.0f}% (elevated)")
        elif self.iv_rank > 40:
            score += 1
            reasons.append(f"IV Rank {self.iv_rank:.0f}% (normal)")

        # Contango = theta works in your favor
        if self.term_regime in [TermStructureRegime.STEEP_CONTANGO, TermStructureRegime.NORMAL_CONTANGO]:
            score += 1
            reasons.append("Term structure in contango (theta favorable)")

        # Normal skew = balanced risk
        if self.skew_regime == SkewRegime.NORMAL_SKEW:
            score += 1
            reasons.append("Normal skew (balanced)")

        should_sell = score >= 3

        return should_sell, " | ".join(reasons)

    def get_optimal_strategy(self) -> Dict:
        """
        Get optimal strategy based on surface analysis

        Returns dict with strategy parameters
        """
        strategy = {
            'strategy_type': None,
            'direction': None,
            'dte_recommendation': self.recommended_dte,
            'reasoning': []
        }

        # High put skew + high IV = sell put spreads
        if self.skew_regime in [SkewRegime.HIGH_PUT_SKEW, SkewRegime.EXTREME_PUT_SKEW]:
            if self.iv_rank > 50:
                strategy['strategy_type'] = 'SELL_PUT_SPREAD'
                strategy['direction'] = 'bullish'
                strategy['reasoning'].append(
                    f"High put skew ({self.skew_25d:.1%}) means puts are overpriced - sell them"
                )

        # Low IV + call skew = buy calls
        elif self.skew_regime == SkewRegime.CALL_SKEW:
            if self.iv_rank < 40:
                strategy['strategy_type'] = 'BUY_CALL'
                strategy['direction'] = 'bullish'
                strategy['reasoning'].append(
                    f"Call skew with low IV ({self.iv_rank:.0f}%) - calls are cheap"
                )

        # Normal conditions + high IV = iron condor
        elif self.skew_regime in [SkewRegime.NORMAL_SKEW, SkewRegime.FLAT_SKEW]:
            if self.iv_rank > 60:
                strategy['strategy_type'] = 'IRON_CONDOR'
                strategy['direction'] = 'neutral'
                strategy['reasoning'].append(
                    f"Normal skew + elevated IV ({self.iv_rank:.0f}%) - premium selling"
                )

        # Backwardation = short-term fear, be cautious
        if self.term_regime in [TermStructureRegime.BACKWARDATION, TermStructureRegime.STEEP_BACKWARDATION]:
            strategy['reasoning'].append(
                "CAUTION: Term structure inverted - expect volatility expansion"
            )
            strategy['dte_recommendation'] = min(14, self.recommended_dte)

        return strategy


class VolatilitySurfaceAnalyzer:
    """
    Analyzes volatility surface for trading decisions

    Usage:
        analyzer = VolatilitySurfaceAnalyzer(spot_price=450.0)
        analyzer.update_from_options_chain(chain_data)

        vol_data = analyzer.get_enhanced_volatility_data()
        print(f"Skew Regime: {vol_data.skew_regime}")
        print(f"Directional Bias: {vol_data.get_directional_bias()}")

        strategy = vol_data.get_optimal_strategy()
        print(f"Recommended: {strategy['strategy_type']}")
    """

    def __init__(self, spot_price: float, risk_free_rate: float = 0.045):
        self.spot = spot_price
        self.rf = risk_free_rate
        self.surface: Optional[VolatilitySurface] = None
        self.iv_history: List[float] = []  # For IV rank calculation

    def update_from_options_chain(self, chains: Dict[int, List[Dict]]) -> bool:
        """
        Update surface from options chain data

        Args:
            chains: Dict mapping DTE to list of option data
                    Each option: {'strike': float, 'iv': float, 'delta': float, ...}

        Returns:
            True if surface fit successful
        """
        if not VOL_SURFACE_AVAILABLE:
            return False

        self.surface = VolatilitySurface(self.spot, self.rf)

        for dte, chain in chains.items():
            self.surface.add_iv_chain(chain, dte)

        return self.surface.fit(method='spline')

    def update_iv_history(self, iv: float):
        """Add IV observation to history for rank calculation"""
        self.iv_history.append(iv)
        # Keep 252 trading days of history
        if len(self.iv_history) > 252:
            self.iv_history = self.iv_history[-252:]

    def _calculate_iv_rank(self, current_iv: float) -> float:
        """Calculate IV rank (0-100)"""
        if len(self.iv_history) < 10:
            return 50.0  # Default if insufficient history

        min_iv = min(self.iv_history)
        max_iv = max(self.iv_history)

        if max_iv == min_iv:
            return 50.0

        return (current_iv - min_iv) / (max_iv - min_iv) * 100

    def _calculate_iv_percentile(self, current_iv: float) -> float:
        """Calculate IV percentile (% of days IV was lower)"""
        if len(self.iv_history) < 10:
            return 50.0

        below = sum(1 for iv in self.iv_history if iv < current_iv)
        return below / len(self.iv_history) * 100

    def _classify_skew_regime(self, skew_25d: float) -> SkewRegime:
        """Classify skew regime from 25-delta skew"""
        if skew_25d > 0.08:
            return SkewRegime.EXTREME_PUT_SKEW
        elif skew_25d > 0.04:
            return SkewRegime.HIGH_PUT_SKEW
        elif skew_25d > 0.01:
            return SkewRegime.NORMAL_SKEW
        elif skew_25d > -0.01:
            return SkewRegime.FLAT_SKEW
        else:
            return SkewRegime.CALL_SKEW

    def _classify_term_structure(self, slope: float) -> TermStructureRegime:
        """Classify term structure regime"""
        # Slope is IV change per day
        if slope > 0.002:  # >0.2% per day
            return TermStructureRegime.STEEP_CONTANGO
        elif slope > 0.0005:
            return TermStructureRegime.NORMAL_CONTANGO
        elif slope > -0.0005:
            return TermStructureRegime.FLAT
        elif slope > -0.002:
            return TermStructureRegime.BACKWARDATION
        else:
            return TermStructureRegime.STEEP_BACKWARDATION

    def _get_recommended_dte(self, term_regime: TermStructureRegime, iv_rank: float) -> int:
        """
        Get recommended DTE based on term structure and IV rank

        Logic:
        - High IV + contango: Use 30-45 DTE (maximum theta decay)
        - Low IV + contango: Use 45-60 DTE (more time for move)
        - Backwardation: Use 7-21 DTE (front month overpriced)
        """
        if term_regime in [TermStructureRegime.BACKWARDATION, TermStructureRegime.STEEP_BACKWARDATION]:
            return 14  # Short DTE when term structure inverted

        if iv_rank > 70:
            return 30  # High IV = shorter DTE for premium selling
        elif iv_rank > 40:
            return 45  # Normal IV = standard theta targeting
        else:
            return 60  # Low IV = longer DTE for directional plays

    def get_enhanced_volatility_data(self, target_dte: int = 30) -> EnhancedVolatilityData:
        """
        Get complete volatility analysis for trading decisions

        Args:
            target_dte: Primary DTE to analyze

        Returns:
            EnhancedVolatilityData with all metrics and recommendations
        """
        # If no surface available, return defaults
        if self.surface is None or not self.surface.is_fitted:
            return self._get_default_vol_data()

        # Get ATM IV
        atm_iv = self.surface.get_iv(self.spot, target_dte)
        self.update_iv_history(atm_iv)

        # Calculate IV rank and percentile
        iv_rank = self._calculate_iv_rank(atm_iv)
        iv_percentile = self._calculate_iv_percentile(atm_iv)

        # Get skew metrics
        skew_metrics = self.surface.get_skew_metrics(target_dte)
        skew_regime = self._classify_skew_regime(skew_metrics.skew_25d)

        # Get term structure
        term_structure = self.surface.get_term_structure()
        term_regime = self._classify_term_structure(term_structure.slope)

        # Recommended DTE
        recommended_dte = self._get_recommended_dte(term_regime, iv_rank)

        # IV percentile at recommended DTE
        iv_at_dte = self.surface.get_iv(self.spot, recommended_dte)
        iv_pct_at_dte = self._calculate_iv_percentile(iv_at_dte)

        return EnhancedVolatilityData(
            atm_iv=atm_iv,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            skew_25d=skew_metrics.skew_25d,
            risk_reversal=skew_metrics.risk_reversal_25d,
            butterfly=skew_metrics.butterfly_25d,
            skew_regime=skew_regime,
            term_slope=term_structure.slope,
            term_regime=term_regime,
            front_month_iv=term_structure.spot_iv,
            back_month_iv=list(term_structure.term_ivs.values())[-1] if term_structure.term_ivs else atm_iv,
            recommended_dte=recommended_dte,
            iv_percentile_at_dte=iv_pct_at_dte
        )

    def _get_default_vol_data(self) -> EnhancedVolatilityData:
        """Return default data when surface not available"""
        return EnhancedVolatilityData(
            atm_iv=0.20,
            iv_rank=50.0,
            iv_percentile=50.0,
            skew_25d=0.03,
            risk_reversal=-0.03,
            butterfly=0.01,
            skew_regime=SkewRegime.NORMAL_SKEW,
            term_slope=0.001,
            term_regime=TermStructureRegime.NORMAL_CONTANGO,
            front_month_iv=0.20,
            back_month_iv=0.22,
            recommended_dte=30,
            iv_percentile_at_dte=50.0
        )


def integrate_with_classifier(classifier, vol_analyzer: VolatilitySurfaceAnalyzer) -> Dict:
    """
    Integrate volatility surface data with market regime classifier

    This shows HOW traders use the volatility surface:
    1. Get enhanced vol data from surface
    2. Use skew to inform directional bias
    3. Use term structure to select DTE
    4. Combine with GEX data for final decision

    Args:
        classifier: MarketRegimeClassifier instance
        vol_analyzer: VolatilitySurfaceAnalyzer with fitted surface

    Returns:
        Dict with enhanced trading recommendation
    """
    vol_data = vol_analyzer.get_enhanced_volatility_data()

    # Get directional bias from skew
    skew_bias = vol_data.get_directional_bias()

    # Get strategy recommendation from surface
    surface_strategy = vol_data.get_optimal_strategy()

    # Check if conditions favor premium selling
    should_sell, sell_reasoning = vol_data.should_sell_premium()

    return {
        'volatility_surface': {
            'atm_iv': vol_data.atm_iv,
            'iv_rank': vol_data.iv_rank,
            'skew_regime': vol_data.skew_regime.value,
            'term_regime': vol_data.term_regime.value,
            'skew_25d': vol_data.skew_25d,
        },
        'recommendations': {
            'directional_bias': skew_bias,
            'should_sell_premium': should_sell,
            'sell_reasoning': sell_reasoning,
            'recommended_dte': vol_data.recommended_dte,
            'strategy_from_surface': surface_strategy,
        },
        'risk_adjustments': {
            'reduce_size_if_backwardation': vol_data.term_regime in [
                TermStructureRegime.BACKWARDATION,
                TermStructureRegime.STEEP_BACKWARDATION
            ],
            'favor_spreads_if_high_iv': vol_data.iv_rank > 60,
            'use_longer_dte_if_contango': vol_data.term_regime in [
                TermStructureRegime.STEEP_CONTANGO,
                TermStructureRegime.NORMAL_CONTANGO
            ]
        }
    }
