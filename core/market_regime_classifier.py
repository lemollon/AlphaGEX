"""
market_regime_classifier.py - UNIFIED Market Regime Classification System

This is the SINGLE SOURCE OF TRUTH for both backtester and live trading.
Every trading decision flows through this classifier.

CORE PRINCIPLE: No whiplash. Once a regime is established, it persists until
market conditions MATERIALLY change (not just noise).

Decision Matrix:
- SELL_PREMIUM: High IV + Positive Gamma + Range-bound = Iron Condor/Credit Spreads
- BUY_CALLS: Negative Gamma + Below Flip + Bullish Catalyst = Long Calls
- BUY_PUTS: Negative Gamma + Above Flip + Bearish Catalyst = Long Puts
- STAY_FLAT: Uncertain regime or transitioning = No new positions

Author: AlphaGEX
Date: 2025-11-26
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import json

# Database connection
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# UNIFIED Data Provider (Tradier primary, Polygon fallback)
try:
    from data.unified_data_provider import get_data_provider, get_quote, get_options_chain, get_gex, get_vix
    UNIFIED_DATA_AVAILABLE = True
except ImportError:
    UNIFIED_DATA_AVAILABLE = False

# Legacy Polygon helper (fallback)
try:
    from data.polygon_data_fetcher import PolygonDataFetcher as PolygonHelper
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False

# Tradier for live options data and execution
try:
    from tradier_data_fetcher import TradierDataFetcher, TradierExecutor
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False

# Volatility Surface Integration - Skew and Term Structure Analysis
try:
    from .volatility_surface_integration import (
        VolatilitySurfaceAnalyzer,
        EnhancedVolatilityData,
        SkewRegime,
        TermStructureRegime,
        integrate_with_classifier
    )
    VOL_SURFACE_AVAILABLE = True
except ImportError:
    VOL_SURFACE_AVAILABLE = False
    print("Warning: Volatility surface integration not available")

# ML Pattern Learner Integration
try:
    from ai.autonomous_ml_pattern_learner import get_pattern_learner, PatternLearner
    ML_LEARNER_AVAILABLE = True
except ImportError:
    ML_LEARNER_AVAILABLE = False
    print("Warning: ML Pattern Learner not available")


class MarketAction(Enum):
    """The ONLY actions the system can take"""
    SELL_PREMIUM = "SELL_PREMIUM"      # Iron Condor, Credit Spreads, Strangles
    BUY_CALLS = "BUY_CALLS"            # Long calls, Bull Call Spreads
    BUY_PUTS = "BUY_PUTS"              # Long puts, Bear Put Spreads
    STAY_FLAT = "STAY_FLAT"            # No new positions, preserve capital
    CLOSE_POSITIONS = "CLOSE_POSITIONS"  # Exit everything, regime changed


class VolatilityRegime(Enum):
    """IV relative to historical range"""
    EXTREME_HIGH = "EXTREME_HIGH"  # IV Rank > 80 - SELL premium
    HIGH = "HIGH"                   # IV Rank 60-80 - Lean sell premium
    NORMAL = "NORMAL"               # IV Rank 40-60 - Neutral
    LOW = "LOW"                     # IV Rank 20-40 - Lean buy premium
    EXTREME_LOW = "EXTREME_LOW"     # IV Rank < 20 - BUY premium (cheap)


class GammaRegime(Enum):
    """Dealer gamma positioning"""
    STRONG_NEGATIVE = "STRONG_NEGATIVE"  # < -2B - Explosive moves
    NEGATIVE = "NEGATIVE"                 # -2B to -500M - Momentum amplified
    NEUTRAL = "NEUTRAL"                   # -500M to +500M - Mixed
    POSITIVE = "POSITIVE"                 # +500M to +2B - Mean reversion
    STRONG_POSITIVE = "STRONG_POSITIVE"   # > +2B - Price pinning


class TrendRegime(Enum):
    """Price trend relative to key levels"""
    STRONG_UPTREND = "STRONG_UPTREND"
    UPTREND = "UPTREND"
    RANGE_BOUND = "RANGE_BOUND"
    DOWNTREND = "DOWNTREND"
    STRONG_DOWNTREND = "STRONG_DOWNTREND"


@dataclass
class RegimeClassification:
    """Complete market regime classification"""
    timestamp: datetime
    symbol: str

    # Core regime components
    volatility_regime: VolatilityRegime
    gamma_regime: GammaRegime
    trend_regime: TrendRegime

    # Key metrics
    iv_rank: float              # 0-100, where current IV sits in 52-week range
    iv_percentile: float        # 0-100, % of days IV was lower
    current_iv: float           # Current implied volatility
    historical_vol: float       # Realized/historical volatility
    iv_hv_ratio: float          # IV/HV - >1 means IV overpriced

    net_gex: float              # Net gamma exposure in $
    flip_point: float           # Zero gamma level
    spot_price: float           # Current price
    distance_to_flip_pct: float # % distance from flip

    vix: float                  # VIX level
    vix_term_structure: str     # "contango" or "backwardation"

    # THE DECISION (required fields - must come before optional fields with defaults)
    recommended_action: MarketAction
    confidence: float           # 0-100
    reasoning: str

    # Persistence tracking
    regime_start_time: datetime
    bars_in_regime: int         # How many bars we've been in this regime
    regime_changed: bool        # Did regime just change?

    # Risk parameters
    max_position_size_pct: float  # Max % of capital for this regime
    stop_loss_pct: float          # Recommended stop loss %
    profit_target_pct: float      # Recommended profit target %

    # Optional fields with defaults (must come after required fields)
    previous_action: Optional[MarketAction] = None

    # Volatility Surface Analysis (NEW - provides skew and term structure insight)
    skew_regime: Optional[str] = None           # From vol surface: EXTREME_PUT_SKEW, HIGH_PUT_SKEW, etc.
    skew_25d: Optional[float] = None            # 25-delta skew (put IV - call IV)
    term_structure_regime: Optional[str] = None # STEEP_CONTANGO, BACKWARDATION, etc.
    vol_surface_bias: Optional[str] = None      # 'bullish', 'neutral', 'bearish' from surface
    recommended_dte: Optional[int] = None       # Best DTE from term structure analysis
    should_sell_premium: Optional[bool] = None  # Surface says sell premium?

    # ML Pattern Learner Analysis (enhances decision confidence)
    ml_win_probability: Optional[float] = None   # 0-1 probability from ML model
    ml_recommendation: Optional[str] = None      # ML says: STRONG_BUY, BUY, HOLD, SELL, STRONG_SELL
    ml_confidence_boost: Optional[float] = None  # How much ML adjusts confidence (-20 to +20)
    ml_model_trained: bool = False               # Is the ML model actually trained?


class MarketRegimeClassifier:
    """
    Unified classifier for all trading decisions.

    ANTI-WHIPLASH RULES:
    1. Regime must persist for MIN_BARS_FOR_REGIME before acting
    2. Regime change requires MATERIAL change (not just noise)
    3. Once in a trade, stay until stop/target hit OR regime MATERIALLY changes
    4. No new positions during regime transition
    """

    # Anti-whiplash parameters
    MIN_BARS_FOR_REGIME = 3           # Must see regime for 3 bars before acting
    REGIME_CHANGE_THRESHOLD = 0.20    # 20% change in key metric to trigger regime change
    DECISION_COOLDOWN_BARS = 2        # Wait 2 bars after regime change before new trades

    # IV Rank thresholds
    IV_EXTREME_HIGH = 80
    IV_HIGH = 60
    IV_LOW = 40
    IV_EXTREME_LOW = 20

    # GEX thresholds (in billions)
    GEX_STRONG_NEGATIVE = -2e9
    GEX_NEGATIVE = -0.5e9
    GEX_POSITIVE = 0.5e9
    GEX_STRONG_POSITIVE = 2e9

    def __init__(self, symbol: str = "SPY"):
        self.symbol = symbol
        self.current_regime: Optional[RegimeClassification] = None
        self.regime_history: List[RegimeClassification] = []
        self.bars_in_current_regime = 0
        self.last_action_bar = 0
        self.total_bars = 0

        # Load persisted state if available
        self._load_persisted_state()

    def _load_persisted_state(self):
        """Load last known regime from database for continuity"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            # Get most recent regime classification
            c.execute("""
                SELECT regime_data, created_at
                FROM regime_classifications
                WHERE symbol = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (self.symbol,))

            row = c.fetchone()
            if row:
                regime_data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                # Only use if less than 1 hour old
                if datetime.now() - row[1] < timedelta(hours=1):
                    self.bars_in_current_regime = regime_data.get('bars_in_regime', 0)
                    print(f"Loaded persisted regime state: {regime_data.get('recommended_action')}")

            conn.close()
        except Exception as e:
            print(f"Could not load persisted regime state: {e}")

    def _persist_regime(self, regime: RegimeClassification):
        """Save regime to database for crash recovery and backtesting"""
        if not DB_AVAILABLE:
            return

        try:
            conn = get_connection()
            c = conn.cursor()

            regime_data = {
                'volatility_regime': regime.volatility_regime.value,
                'gamma_regime': regime.gamma_regime.value,
                'trend_regime': regime.trend_regime.value,
                'iv_rank': regime.iv_rank,
                'iv_percentile': regime.iv_percentile,
                'net_gex': regime.net_gex,
                'flip_point': regime.flip_point,
                'spot_price': regime.spot_price,
                'vix': regime.vix,
                'recommended_action': regime.recommended_action.value,
                'confidence': regime.confidence,
                'reasoning': regime.reasoning,
                'bars_in_regime': regime.bars_in_regime,
                'regime_changed': regime.regime_changed
            }

            c.execute("""
                INSERT INTO regime_classifications
                (symbol, regime_data, recommended_action, confidence, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                self.symbol,
                json.dumps(regime_data),
                regime.recommended_action.value,
                regime.confidence,
                regime.timestamp
            ))

            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Could not persist regime: {e}")

    def calculate_iv_rank(self, current_iv: float, iv_history: List[float]) -> Tuple[float, float]:
        """
        Calculate IV Rank and IV Percentile

        IV Rank = (Current IV - 52-week Low) / (52-week High - 52-week Low) * 100
        IV Percentile = % of days current IV was lower than today

        Args:
            current_iv: Current implied volatility (e.g., 0.20 for 20%)
            iv_history: List of historical IV values (252 trading days ideal)

        Returns:
            (iv_rank, iv_percentile)
        """
        if not iv_history or len(iv_history) < 20:
            # Not enough data, assume normal
            return 50.0, 50.0

        iv_min = min(iv_history)
        iv_max = max(iv_history)

        # IV Rank
        if iv_max - iv_min > 0:
            iv_rank = (current_iv - iv_min) / (iv_max - iv_min) * 100
        else:
            iv_rank = 50.0

        # IV Percentile
        days_lower = sum(1 for iv in iv_history if iv < current_iv)
        iv_percentile = days_lower / len(iv_history) * 100

        return max(0, min(100, iv_rank)), max(0, min(100, iv_percentile))

    def classify_volatility_regime(self, iv_rank: float) -> VolatilityRegime:
        """Classify volatility regime based on IV Rank"""
        if iv_rank >= self.IV_EXTREME_HIGH:
            return VolatilityRegime.EXTREME_HIGH
        elif iv_rank >= self.IV_HIGH:
            return VolatilityRegime.HIGH
        elif iv_rank >= self.IV_LOW:
            return VolatilityRegime.NORMAL
        elif iv_rank >= self.IV_EXTREME_LOW:
            return VolatilityRegime.LOW
        else:
            return VolatilityRegime.EXTREME_LOW

    def classify_gamma_regime(self, net_gex: float) -> GammaRegime:
        """Classify gamma regime based on net GEX"""
        if net_gex <= self.GEX_STRONG_NEGATIVE:
            return GammaRegime.STRONG_NEGATIVE
        elif net_gex <= self.GEX_NEGATIVE:
            return GammaRegime.NEGATIVE
        elif net_gex >= self.GEX_STRONG_POSITIVE:
            return GammaRegime.STRONG_POSITIVE
        elif net_gex >= self.GEX_POSITIVE:
            return GammaRegime.POSITIVE
        else:
            return GammaRegime.NEUTRAL

    def classify_trend_regime(
        self,
        spot: float,
        flip_point: float,
        momentum_1h: float,
        momentum_4h: float,
        above_20ma: bool,
        above_50ma: bool
    ) -> TrendRegime:
        """Classify trend regime based on price action"""
        # Calculate position relative to flip
        pct_from_flip = (spot - flip_point) / flip_point * 100 if flip_point > 0 else 0

        # Strong uptrend: Above flip, above MAs, positive momentum
        if pct_from_flip > 1 and above_20ma and above_50ma and momentum_4h > 0.5:
            return TrendRegime.STRONG_UPTREND

        # Strong downtrend: Below flip, below MAs, negative momentum
        if pct_from_flip < -1 and not above_20ma and not above_50ma and momentum_4h < -0.5:
            return TrendRegime.STRONG_DOWNTREND

        # Uptrend
        if momentum_4h > 0.2 and (above_20ma or pct_from_flip > 0.5):
            return TrendRegime.UPTREND

        # Downtrend
        if momentum_4h < -0.2 and (not above_20ma or pct_from_flip < -0.5):
            return TrendRegime.DOWNTREND

        # Range-bound
        return TrendRegime.RANGE_BOUND

    def determine_action(
        self,
        vol_regime: VolatilityRegime,
        gamma_regime: GammaRegime,
        trend_regime: TrendRegime,
        iv_hv_ratio: float,
        distance_to_flip_pct: float,
        vix: float,
        vol_surface_data: Optional[Dict] = None,  # Volatility surface analysis
        ml_prediction_data: Optional[Dict] = None  # ML Pattern Learner prediction
    ) -> Tuple[MarketAction, float, str]:
        """
        THE DECISION MATRIX

        This is where we decide SELL_PREMIUM vs BUY_DIRECTIONAL

        Now enhanced with:
        - VOLATILITY SURFACE analysis (skew, term structure)
        - ML PATTERN LEARNER predictions (win probability, recommendation)

        Returns:
            (action, confidence, reasoning)
        """
        reasons = []
        confidence = 50.0

        # Extract ML insights if available
        ml_trained = ml_prediction_data.get('model_trained', False) if ml_prediction_data else False
        ml_win_prob = ml_prediction_data.get('win_probability') if ml_prediction_data else None
        ml_rec = ml_prediction_data.get('recommendation') if ml_prediction_data else None
        if ml_trained and ml_win_prob:
            reasons.append(f"ML: {ml_win_prob:.0%} win prob ({ml_rec})")

        # Extract vol surface insights if available
        vs_bias = None
        vs_should_sell = None
        vs_skew_regime = None
        vs_term_regime = None
        if vol_surface_data:
            vs_bias = vol_surface_data.get('directional_bias')  # 'bullish', 'neutral', 'bearish'
            vs_should_sell = vol_surface_data.get('should_sell_premium')
            vs_skew_regime = vol_surface_data.get('skew_regime')
            vs_term_regime = vol_surface_data.get('term_structure_regime')
            if vs_bias:
                reasons.append(f"VOL SURFACE BIAS: {vs_bias.upper()}")
            if vs_skew_regime:
                reasons.append(f"Skew regime: {vs_skew_regime}")

        # ================================================================
        # SCENARIO 1: SELL PREMIUM CONDITIONS
        # High IV + Positive Gamma + Range-bound = Perfect for selling
        # NOW ENHANCED: Vol surface confirms with contango + neutral skew
        # ================================================================
        if vol_regime in [VolatilityRegime.EXTREME_HIGH, VolatilityRegime.HIGH]:
            if gamma_regime in [GammaRegime.POSITIVE, GammaRegime.STRONG_POSITIVE]:
                if trend_regime == TrendRegime.RANGE_BOUND:
                    # IDEAL SELL PREMIUM SETUP
                    confidence = 85.0
                    reasons.append(f"HIGH IV ({vol_regime.value}) = expensive premiums to sell")
                    reasons.append(f"POSITIVE GAMMA ({gamma_regime.value}) = dealers pin price")
                    reasons.append("RANGE-BOUND = low risk of breakout")

                    if iv_hv_ratio > 1.2:
                        confidence += 5
                        reasons.append(f"IV/HV ratio {iv_hv_ratio:.2f} = IV overpriced vs realized")

                    # VOL SURFACE ENHANCEMENT
                    if vs_should_sell is True:
                        confidence += 5
                        reasons.append("VOL SURFACE CONFIRMS: Sell premium conditions (skew + term structure)")
                    if vs_term_regime and 'CONTANGO' in str(vs_term_regime).upper():
                        confidence += 3
                        reasons.append(f"Term structure {vs_term_regime} favors theta decay")

                    return MarketAction.SELL_PREMIUM, min(95, confidence), "\n".join(reasons)

                # Trending but positive gamma - still can sell, smaller size
                elif trend_regime in [TrendRegime.UPTREND, TrendRegime.DOWNTREND]:
                    confidence = 65.0
                    reasons.append(f"HIGH IV + POSITIVE GAMMA = can sell premium")
                    reasons.append(f"BUT trending ({trend_regime.value}) = use directional bias")
                    return MarketAction.SELL_PREMIUM, confidence, "\n".join(reasons)

        # ================================================================
        # SCENARIO 2: BUY CALLS CONDITIONS
        # Negative Gamma + Below Flip + Any IV = Squeeze potential
        # NOW ENHANCED: Vol surface skew confirms bullish bias
        # ================================================================
        if gamma_regime in [GammaRegime.NEGATIVE, GammaRegime.STRONG_NEGATIVE]:
            if distance_to_flip_pct < -0.5:  # Below flip point
                confidence = 70.0
                reasons.append(f"NEGATIVE GAMMA ({gamma_regime.value}) = dealers amplify moves")
                reasons.append(f"BELOW FLIP by {abs(distance_to_flip_pct):.1f}% = squeeze potential")

                if trend_regime in [TrendRegime.UPTREND, TrendRegime.STRONG_UPTREND]:
                    confidence += 10
                    reasons.append("UPTREND momentum aligned with squeeze thesis")

                if vol_regime in [VolatilityRegime.LOW, VolatilityRegime.EXTREME_LOW]:
                    confidence += 5
                    reasons.append("LOW IV = cheap calls, asymmetric payoff")
                elif vol_regime in [VolatilityRegime.EXTREME_HIGH]:
                    confidence -= 10
                    reasons.append("HIGH IV = expensive calls, but move could be explosive")

                if vix > 25:
                    confidence += 5
                    reasons.append(f"VIX {vix:.1f} = fear elevated, squeeze more violent")

                # VOL SURFACE ENHANCEMENT
                if vs_bias == 'bullish':
                    confidence += 5
                    reasons.append("VOL SURFACE: Bullish skew confirms call thesis")
                elif vs_skew_regime and 'CALL' in str(vs_skew_regime).upper():
                    confidence += 5
                    reasons.append(f"Skew {vs_skew_regime} = bullish confirmation")
                if vs_term_regime and 'BACKWARDATION' in str(vs_term_regime).upper():
                    confidence += 3
                    reasons.append("Backwardation = near-term fear, explosive move potential")

                return MarketAction.BUY_CALLS, min(90, confidence), "\n".join(reasons)

        # ================================================================
        # SCENARIO 3: BUY PUTS CONDITIONS
        # Negative Gamma + Above Flip + Bearish = Breakdown potential
        # NOW ENHANCED: Vol surface skew confirms bearish bias
        # ================================================================
        if gamma_regime in [GammaRegime.NEGATIVE, GammaRegime.STRONG_NEGATIVE]:
            if distance_to_flip_pct > 0.5:  # Above flip point
                confidence = 70.0
                reasons.append(f"NEGATIVE GAMMA ({gamma_regime.value}) = dealers amplify moves")
                reasons.append(f"ABOVE FLIP by {distance_to_flip_pct:.1f}% = breakdown potential")

                if trend_regime in [TrendRegime.DOWNTREND, TrendRegime.STRONG_DOWNTREND]:
                    confidence += 10
                    reasons.append("DOWNTREND momentum aligned with breakdown thesis")

                if vol_regime in [VolatilityRegime.LOW, VolatilityRegime.EXTREME_LOW]:
                    confidence += 5
                    reasons.append("LOW IV = cheap puts, asymmetric payoff")

                # VOL SURFACE ENHANCEMENT
                if vs_bias == 'bearish':
                    confidence += 5
                    reasons.append("VOL SURFACE: Bearish skew confirms put thesis")
                elif vs_skew_regime and 'PUT_SKEW' in str(vs_skew_regime).upper():
                    confidence += 5
                    reasons.append(f"Skew {vs_skew_regime} = elevated downside protection demand")
                if vs_term_regime and 'BACKWARDATION' in str(vs_term_regime).upper():
                    confidence += 3
                    reasons.append("Backwardation = near-term fear, breakdown potential")

                return MarketAction.BUY_PUTS, min(90, confidence), "\n".join(reasons)

        # ================================================================
        # SCENARIO 4: EXTREME HIGH IV + RANGE = SELL PREMIUM (even neutral gamma)
        # When VIX is very high and market is range-bound, premium is expensive
        # ================================================================
        if vol_regime == VolatilityRegime.EXTREME_HIGH:
            if trend_regime == TrendRegime.RANGE_BOUND:
                confidence = 70.0
                reasons.append(f"EXTREME HIGH IV ({vol_regime.value}) = very expensive premiums")
                reasons.append("RANGE-BOUND market = lower risk of directional breakout")
                if iv_hv_ratio > 1.3:
                    confidence += 10
                    reasons.append(f"IV/HV ratio {iv_hv_ratio:.2f} = IV significantly overpriced")
                reasons.append("Use smaller size due to neutral gamma (no dealer support)")
                return MarketAction.SELL_PREMIUM, confidence, "\n".join(reasons)

        # ================================================================
        # SCENARIO 5: LOW IV = BUY PREMIUM (it's cheap)
        # ================================================================
        if vol_regime == VolatilityRegime.EXTREME_LOW:
            confidence = 60.0
            reasons.append("EXTREME LOW IV = options are cheap, buy premium")

            if trend_regime in [TrendRegime.UPTREND, TrendRegime.STRONG_UPTREND]:
                reasons.append("Uptrend = favor calls")
                return MarketAction.BUY_CALLS, confidence, "\n".join(reasons)
            elif trend_regime in [TrendRegime.DOWNTREND, TrendRegime.STRONG_DOWNTREND]:
                reasons.append("Downtrend = favor puts")
                return MarketAction.BUY_PUTS, confidence, "\n".join(reasons)
            else:
                reasons.append("No clear trend = wait for direction")
                return MarketAction.STAY_FLAT, 40.0, "\n".join(reasons)

        # ================================================================
        # SCENARIO 6: NEUTRAL/UNCLEAR = STAY FLAT
        # ================================================================
        reasons.append(f"Vol regime: {vol_regime.value}")
        reasons.append(f"Gamma regime: {gamma_regime.value}")
        reasons.append(f"Trend regime: {trend_regime.value}")
        reasons.append("No clear edge - preserve capital")

        return MarketAction.STAY_FLAT, 30.0, "\n".join(reasons)

    def check_regime_change(
        self,
        new_vol_regime: VolatilityRegime,
        new_gamma_regime: GammaRegime,
        new_trend_regime: TrendRegime
    ) -> bool:
        """
        Check if regime has MATERIALLY changed (not just noise)

        ANTI-WHIPLASH: Only trigger change if:
        1. Volatility regime changed by 2+ levels (e.g., LOW to HIGH)
        2. OR Gamma flipped from positive to negative (or vice versa)
        3. OR Trend reversed (uptrend to downtrend)
        """
        if self.current_regime is None:
            return True

        old = self.current_regime

        # Check volatility change (must be 2+ levels)
        vol_levels = list(VolatilityRegime)
        old_vol_idx = vol_levels.index(old.volatility_regime)
        new_vol_idx = vol_levels.index(new_vol_regime)
        if abs(new_vol_idx - old_vol_idx) >= 2:
            return True

        # Check gamma flip (positive <-> negative)
        positive_gammas = [GammaRegime.POSITIVE, GammaRegime.STRONG_POSITIVE]
        negative_gammas = [GammaRegime.NEGATIVE, GammaRegime.STRONG_NEGATIVE]

        was_positive = old.gamma_regime in positive_gammas
        was_negative = old.gamma_regime in negative_gammas
        is_positive = new_gamma_regime in positive_gammas
        is_negative = new_gamma_regime in negative_gammas

        if (was_positive and is_negative) or (was_negative and is_positive):
            return True

        # Check trend reversal
        uptrends = [TrendRegime.UPTREND, TrendRegime.STRONG_UPTREND]
        downtrends = [TrendRegime.DOWNTREND, TrendRegime.STRONG_DOWNTREND]

        was_up = old.trend_regime in uptrends
        was_down = old.trend_regime in downtrends
        is_up = new_trend_regime in uptrends
        is_down = new_trend_regime in downtrends

        if (was_up and is_down) or (was_down and is_up):
            return True

        return False

    def classify(
        self,
        spot_price: float,
        net_gex: float,
        flip_point: float,
        current_iv: float,
        iv_history: List[float],
        historical_vol: float,
        vix: float,
        vix_term_structure: str,
        momentum_1h: float,
        momentum_4h: float,
        above_20ma: bool,
        above_50ma: bool,
        timestamp: Optional[datetime] = None,
        vol_surface_data: Optional[Dict] = None,  # Volatility surface analysis
        ml_prediction_data: Optional[Dict] = None  # ML Pattern Learner prediction
    ) -> RegimeClassification:
        """
        MAIN CLASSIFICATION METHOD

        Call this every bar (5 minutes in live, or per backtest bar)
        It handles anti-whiplash logic internally.

        Returns complete RegimeClassification with recommended action.
        """
        if timestamp is None:
            timestamp = datetime.now()

        self.total_bars += 1

        # Calculate IV metrics
        iv_rank, iv_percentile = self.calculate_iv_rank(current_iv, iv_history)
        iv_hv_ratio = current_iv / historical_vol if historical_vol > 0 else 1.0

        # Classify each component
        vol_regime = self.classify_volatility_regime(iv_rank)
        gamma_regime = self.classify_gamma_regime(net_gex)

        distance_to_flip = (spot_price - flip_point) / flip_point * 100 if flip_point > 0 else 0

        trend_regime = self.classify_trend_regime(
            spot_price, flip_point, momentum_1h, momentum_4h, above_20ma, above_50ma
        )

        # Check if regime changed
        regime_changed = self.check_regime_change(vol_regime, gamma_regime, trend_regime)

        if regime_changed:
            self.bars_in_current_regime = 1
        else:
            self.bars_in_current_regime += 1

        # Extract volatility surface data if available
        skew_regime = None
        skew_25d = None
        term_structure_regime = None
        vol_surface_bias = None
        recommended_dte = None
        should_sell = None

        if vol_surface_data:
            skew_regime = vol_surface_data.get('skew_regime')
            skew_25d = vol_surface_data.get('skew_25d')
            term_structure_regime = vol_surface_data.get('term_structure_regime')
            vol_surface_bias = vol_surface_data.get('directional_bias')
            recommended_dte = vol_surface_data.get('recommended_dte')
            should_sell = vol_surface_data.get('should_sell_premium')

        # Extract ML prediction data if available
        ml_win_prob = None
        ml_recommendation = None
        ml_confidence_boost = 0.0
        ml_model_trained = False

        if ml_prediction_data:
            ml_win_prob = ml_prediction_data.get('win_probability')
            ml_recommendation = ml_prediction_data.get('recommendation')
            ml_model_trained = ml_prediction_data.get('model_trained', False)
            # Calculate confidence boost from ML: +/-20 based on win probability
            if ml_win_prob is not None and ml_model_trained:
                ml_confidence_boost = (ml_win_prob - 0.5) * 40  # Range: -20 to +20

        # Determine action (enhanced with vol surface and ML if available)
        action, confidence, reasoning = self.determine_action(
            vol_regime, gamma_regime, trend_regime, iv_hv_ratio, distance_to_flip, vix,
            vol_surface_data=vol_surface_data,
            ml_prediction_data=ml_prediction_data
        )

        # Apply ML confidence adjustment (only if model is trained)
        if ml_model_trained and ml_confidence_boost != 0:
            confidence = min(95, max(10, confidence + ml_confidence_boost))
            reasoning += f"\n\nML BOOST: {ml_confidence_boost:+.1f} (win prob: {ml_win_prob:.1%})"

        # ANTI-WHIPLASH: Don't act until regime is established
        if self.bars_in_current_regime < self.MIN_BARS_FOR_REGIME:
            original_action = action
            action = MarketAction.STAY_FLAT
            reasoning = (
                f"WAITING FOR REGIME CONFIRMATION\n"
                f"Bars in regime: {self.bars_in_current_regime}/{self.MIN_BARS_FOR_REGIME}\n"
                f"Pending action: {original_action.value}\n"
                f"Original reasoning:\n{reasoning}"
            )
            confidence = 20.0

        # ANTI-WHIPLASH: Cooldown after regime change
        bars_since_change = self.total_bars - self.last_action_bar
        if regime_changed and bars_since_change < self.DECISION_COOLDOWN_BARS:
            action = MarketAction.STAY_FLAT
            reasoning = f"REGIME TRANSITION COOLDOWN\n{reasoning}"
            confidence = 20.0

        # Get previous action
        previous_action = self.current_regime.recommended_action if self.current_regime else None

        # Calculate position sizing based on confidence
        if confidence >= 80:
            max_position_pct = 0.15  # 15% max
            stop_loss_pct = 0.20
            profit_target_pct = 0.50
        elif confidence >= 60:
            max_position_pct = 0.10  # 10% max
            stop_loss_pct = 0.25
            profit_target_pct = 0.40
        else:
            max_position_pct = 0.05  # 5% max
            stop_loss_pct = 0.30
            profit_target_pct = 0.30

        # Build classification (including vol surface and ML data if available)
        classification = RegimeClassification(
            timestamp=timestamp,
            symbol=self.symbol,
            volatility_regime=vol_regime,
            gamma_regime=gamma_regime,
            trend_regime=trend_regime,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            current_iv=current_iv,
            historical_vol=historical_vol,
            iv_hv_ratio=iv_hv_ratio,
            net_gex=net_gex,
            flip_point=flip_point,
            spot_price=spot_price,
            distance_to_flip_pct=distance_to_flip,
            vix=vix,
            vix_term_structure=vix_term_structure,
            # Volatility surface fields
            skew_regime=skew_regime,
            skew_25d=skew_25d,
            term_structure_regime=term_structure_regime,
            vol_surface_bias=vol_surface_bias,
            recommended_dte=recommended_dte,
            should_sell_premium=should_sell,
            # ML Pattern Learner fields
            ml_win_probability=ml_win_prob,
            ml_recommendation=ml_recommendation,
            ml_confidence_boost=ml_confidence_boost,
            ml_model_trained=ml_model_trained,
            # Decision fields
            recommended_action=action,
            confidence=confidence,
            reasoning=reasoning,
            regime_start_time=self.current_regime.regime_start_time if self.current_regime and not regime_changed else timestamp,
            bars_in_regime=self.bars_in_current_regime,
            regime_changed=regime_changed,
            previous_action=previous_action,
            max_position_size_pct=max_position_pct,
            stop_loss_pct=stop_loss_pct,
            profit_target_pct=profit_target_pct
        )

        # Update state
        self.current_regime = classification
        self.regime_history.append(classification)

        # Keep history bounded
        if len(self.regime_history) > 1000:
            self.regime_history = self.regime_history[-500:]

        # Persist to database
        self._persist_regime(classification)

        # Update last action bar if we're taking action
        if action not in [MarketAction.STAY_FLAT]:
            self.last_action_bar = self.total_bars

        return classification

    def get_strategy_for_action(self, action: MarketAction, regime: RegimeClassification) -> Dict:
        """
        Convert action to specific strategy parameters

        Returns dict with:
        - strategy_name: str
        - option_type: str
        - dte_range: Tuple[int, int]
        - delta_target: float
        - strike_selection: str
        """
        if action == MarketAction.SELL_PREMIUM:
            # Iron Condor or Strangle based on confidence
            if regime.confidence >= 80:
                return {
                    'strategy_name': 'Iron Condor',
                    'option_type': 'spread',
                    'dte_range': (30, 45),  # 30-45 DTE for theta
                    'delta_target': 0.16,    # ~84% POP
                    'strike_selection': 'delta_based',
                    'legs': ['sell_put', 'buy_put', 'sell_call', 'buy_call'],
                    'wing_width': 5  # $5 wide wings
                }
            else:
                return {
                    'strategy_name': 'Credit Spread',
                    'option_type': 'spread',
                    'dte_range': (21, 35),
                    'delta_target': 0.20,
                    'strike_selection': 'delta_based',
                    'direction': 'put_spread' if regime.trend_regime in [TrendRegime.UPTREND, TrendRegime.STRONG_UPTREND] else 'call_spread'
                }

        elif action == MarketAction.BUY_CALLS:
            # Long calls or bull call spread
            if regime.volatility_regime in [VolatilityRegime.LOW, VolatilityRegime.EXTREME_LOW]:
                # Cheap IV = can buy naked calls
                return {
                    'strategy_name': 'Long Call',
                    'option_type': 'call',
                    'dte_range': (14, 30),
                    'delta_target': 0.40,  # ATM-ish
                    'strike_selection': 'atm_plus_1'
                }
            else:
                # High IV = use spread to reduce cost
                return {
                    'strategy_name': 'Bull Call Spread',
                    'option_type': 'spread',
                    'dte_range': (7, 21),
                    'delta_target': 0.50,
                    'strike_selection': 'atm_to_flip',
                    'spread_width': 5
                }

        elif action == MarketAction.BUY_PUTS:
            if regime.volatility_regime in [VolatilityRegime.LOW, VolatilityRegime.EXTREME_LOW]:
                return {
                    'strategy_name': 'Long Put',
                    'option_type': 'put',
                    'dte_range': (14, 30),
                    'delta_target': -0.40,
                    'strike_selection': 'atm_minus_1'
                }
            else:
                return {
                    'strategy_name': 'Bear Put Spread',
                    'option_type': 'spread',
                    'dte_range': (7, 21),
                    'delta_target': -0.50,
                    'strike_selection': 'atm_to_flip',
                    'spread_width': 5
                }

        else:  # STAY_FLAT or CLOSE_POSITIONS
            return {
                'strategy_name': 'No Trade',
                'option_type': None,
                'reason': regime.reasoning
            }

    def to_dict(self) -> Dict:
        """Serialize current state for API/logging"""
        if self.current_regime is None:
            return {'status': 'not_initialized'}

        r = self.current_regime
        return {
            'timestamp': r.timestamp.isoformat(),
            'symbol': r.symbol,
            'volatility_regime': r.volatility_regime.value,
            'gamma_regime': r.gamma_regime.value,
            'trend_regime': r.trend_regime.value,
            'iv_rank': round(r.iv_rank, 1),
            'iv_percentile': round(r.iv_percentile, 1),
            'iv_hv_ratio': round(r.iv_hv_ratio, 2),
            'net_gex_billions': round(r.net_gex / 1e9, 2),
            'flip_point': round(r.flip_point, 2),
            'spot_price': round(r.spot_price, 2),
            'distance_to_flip_pct': round(r.distance_to_flip_pct, 2),
            'vix': round(r.vix, 1),
            'recommended_action': r.recommended_action.value,
            'confidence': round(r.confidence, 1),
            'reasoning': r.reasoning,
            'bars_in_regime': r.bars_in_regime,
            'regime_changed': r.regime_changed,
            'max_position_size_pct': round(r.max_position_size_pct * 100, 1),
            'stop_loss_pct': round(r.stop_loss_pct * 100, 1),
            'profit_target_pct': round(r.profit_target_pct * 100, 1)
        }


# ============================================================================
# CONVENIENCE FUNCTIONS FOR LIVE TRADING AND BACKTESTING
# ============================================================================

# Global classifier instances (one per symbol)
_classifiers: Dict[str, MarketRegimeClassifier] = {}


def get_classifier(symbol: str = "SPY") -> MarketRegimeClassifier:
    """Get or create classifier for symbol"""
    if symbol not in _classifiers:
        _classifiers[symbol] = MarketRegimeClassifier(symbol)
    return _classifiers[symbol]


def classify_market_now(
    symbol: str = "SPY",
    spot_price: float = None,
    net_gex: float = None,
    flip_point: float = None,
    current_iv: float = None,
    iv_history: List[float] = None,
    historical_vol: float = None,
    vix: float = None,
    momentum_1h: float = 0,
    momentum_4h: float = 0,
    above_20ma: bool = True,
    above_50ma: bool = True
) -> RegimeClassification:
    """
    Convenience function for live trading - fetches missing data automatically
    """
    classifier = get_classifier(symbol)

    # If data not provided, fetch it
    if spot_price is None or net_gex is None:
        # This would fetch from your data sources
        # For now, raise error to force explicit data
        raise ValueError("spot_price and net_gex are required")

    # Defaults for optional params
    if flip_point is None:
        flip_point = spot_price * 0.98  # Assume 2% below
    if current_iv is None:
        current_iv = 0.20  # 20% default
    if iv_history is None:
        iv_history = [0.18] * 252  # Flat history
    if historical_vol is None:
        historical_vol = 0.18
    if vix is None:
        vix = 18.0

    return classifier.classify(
        spot_price=spot_price,
        net_gex=net_gex,
        flip_point=flip_point,
        current_iv=current_iv,
        iv_history=iv_history,
        historical_vol=historical_vol,
        vix=vix,
        vix_term_structure="contango",
        momentum_1h=momentum_1h,
        momentum_4h=momentum_4h,
        above_20ma=above_20ma,
        above_50ma=above_50ma
    )


def reset_classifier(symbol: str = "SPY"):
    """Reset classifier state (e.g., for new backtest run)"""
    if symbol in _classifiers:
        del _classifiers[symbol]


# ============================================================================
# TRADIER EXECUTION INTEGRATION
# ============================================================================

def execute_with_tradier(
    symbol: str = "SPY",
    position_size: int = 1,
    default_dte: int = 7,
    delta_target: float = 0.30
) -> dict:
    """
    Execute the current regime recommendation via Tradier.

    This is the bridge between classification and execution.

    Args:
        symbol: Underlying symbol (SPY, SPX)
        position_size: Number of contracts
        default_dte: Default days to expiration
        delta_target: Target delta for options

    Returns:
        Execution result dictionary
    """
    if not TRADIER_AVAILABLE:
        return {
            'success': False,
            'error': 'Tradier not available - check TRADIER_API_KEY in .env'
        }

    try:
        # Get current regime classification
        classifier = get_classifier(symbol)
        classification = classifier.current_regime

        if not classification:
            return {
                'success': False,
                'error': 'No regime classification available - call classify() first'
            }

        # Create executor
        executor = TradierExecutor(
            symbol=symbol,
            max_position_size=position_size * 2,  # Allow some buffer
            default_dte=default_dte,
            delta_target=delta_target
        )

        # Execute based on classification
        action = classification.recommended_action.value
        result = executor.execute_regime_action(
            action=action,
            position_size=position_size
        )

        return {
            'success': True,
            'action': action,
            'confidence': classification.confidence,
            'order_result': result,
            'classification': {
                'volatility_regime': classification.volatility_regime.value,
                'gamma_regime': classification.gamma_regime.value,
                'trend_regime': classification.trend_regime.value,
                'iv_rank': classification.iv_rank,
                'net_gex': classification.net_gex
            }
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def get_tradier_portfolio(symbol: str = "SPY") -> dict:
    """
    Get current portfolio state from Tradier.

    Args:
        symbol: Filter positions by underlying (or 'ALL' for everything)

    Returns:
        Portfolio summary
    """
    if not TRADIER_AVAILABLE:
        return {'error': 'Tradier not available'}

    try:
        executor = TradierExecutor(symbol=symbol)
        return executor.get_portfolio_summary()
    except Exception as e:
        return {'error': str(e)}


# ============================================================================
# DATABASE SCHEMA FOR REGIME TRACKING
# ============================================================================

CREATE_REGIME_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS regime_classifications (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    regime_data JSONB NOT NULL,
    recommended_action VARCHAR(50) NOT NULL,
    confidence FLOAT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    INDEX idx_regime_symbol_time (symbol, created_at)
);
"""


if __name__ == "__main__":
    # Test the classifier
    classifier = MarketRegimeClassifier("SPY")

    # Simulate a few bars
    test_cases = [
        # High IV, Positive Gamma, Range-bound = SELL PREMIUM
        {
            'spot_price': 580.0,
            'net_gex': 2.5e9,
            'flip_point': 575.0,
            'current_iv': 0.28,
            'iv_history': [0.15 + i*0.001 for i in range(252)],  # Rising IV
            'historical_vol': 0.18,
            'vix': 22.0,
            'momentum_1h': 0.1,
            'momentum_4h': 0.05,
            'above_20ma': True,
            'above_50ma': True
        },
        # Negative Gamma, Below Flip = BUY CALLS
        {
            'spot_price': 570.0,
            'net_gex': -1.5e9,
            'flip_point': 575.0,
            'current_iv': 0.22,
            'iv_history': [0.20] * 252,
            'historical_vol': 0.18,
            'vix': 20.0,
            'momentum_1h': 0.3,
            'momentum_4h': 0.5,
            'above_20ma': True,
            'above_50ma': True
        }
    ]

    for i, params in enumerate(test_cases):
        print(f"\n{'='*60}")
        print(f"TEST CASE {i+1}")
        print(f"{'='*60}")

        result = classifier.classify(
            vix_term_structure="contango",
            **params
        )

        print(f"\nVolatility Regime: {result.volatility_regime.value}")
        print(f"Gamma Regime: {result.gamma_regime.value}")
        print(f"Trend Regime: {result.trend_regime.value}")
        print(f"\nIV Rank: {result.iv_rank:.1f}")
        print(f"IV/HV Ratio: {result.iv_hv_ratio:.2f}")
        print(f"\n>>> RECOMMENDED ACTION: {result.recommended_action.value}")
        print(f">>> CONFIDENCE: {result.confidence:.0f}%")
        print(f"\nReasoning:\n{result.reasoning}")
        print(f"\nPosition Size: {result.max_position_size_pct*100:.0f}% max")
        print(f"Stop Loss: {result.stop_loss_pct*100:.0f}%")
        print(f"Profit Target: {result.profit_target_pct*100:.0f}%")
