"""
HERACLES - Signal Generator
============================

GEX-based signal generation for MES futures scalping.

Strategy Logic:
- POSITIVE GAMMA: Mean reversion - fade moves, price tends to revert toward flip point
- NEGATIVE GAMMA: Momentum - trade breakouts, price tends to accelerate away from flip point

Uses n+1 GEX data for overnight trading (forward-looking levels).

ML Approval Workflow:
- ML model must be explicitly approved before it's used for predictions
- Use /api/heracles/ml/approve to activate ML after reviewing training results

A/B Test for Dynamic Stops:
- When enabled, 50% of trades use fixed stops, 50% use dynamic stops
- Allows comparison of stop strategies on real trades
"""

import logging
import random
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from .models import (
    FuturesSignal, TradeDirection, GammaRegime, SignalSource,
    HERACLESConfig, BayesianWinTracker, MES_POINT_VALUE, CENTRAL_TZ
)

# ML Advisor - loaded lazily to avoid circular imports
_ml_advisor = None
_ml_load_attempted = False

# Cache for config values to avoid repeated DB lookups
_config_cache = {}
_config_cache_time = None
CONFIG_CACHE_TTL_SECONDS = 60

logger = logging.getLogger(__name__)


def _get_ml_advisor():
    """Lazy-load the ML advisor singleton."""
    global _ml_advisor, _ml_load_attempted

    if _ml_load_attempted:
        return _ml_advisor

    _ml_load_attempted = True
    try:
        from .ml import HERACLESMLAdvisor
        _ml_advisor = HERACLESMLAdvisor()
        if _ml_advisor.model is not None:
            logger.info("HERACLES ML Advisor loaded successfully from database")
        else:
            logger.info("HERACLES ML Advisor initialized but no model trained yet")
    except Exception as e:
        logger.warning(f"Could not load HERACLES ML Advisor: {e}")
        _ml_advisor = None

    return _ml_advisor


def _get_config_value(key: str, default: Any = None) -> Any:
    """Get a config value from the database with caching."""
    global _config_cache, _config_cache_time

    now = datetime.now()

    # Check if cache is stale
    if _config_cache_time is None or (now - _config_cache_time).total_seconds() > CONFIG_CACHE_TTL_SECONDS:
        _config_cache = {}
        _config_cache_time = now

    # Return cached value if available
    if key in _config_cache:
        return _config_cache[key]

    # Fetch from database
    try:
        from database_adapter import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_value FROM heracles_config WHERE config_key = %s",
            (key,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            value = row[0]
            # Try to parse as boolean
            if value and value.lower() in ('true', 'false'):
                value = value.lower() == 'true'
            _config_cache[key] = value
            return value
    except Exception as e:
        logger.warning(f"Failed to get config value {key}: {e}")

    return default


def _set_config_value(key: str, value: Any) -> bool:
    """Set a config value in the database."""
    global _config_cache

    try:
        from database_adapter import get_connection
        import json

        conn = get_connection()
        cursor = conn.cursor()

        # Convert value to string for storage
        if isinstance(value, bool):
            str_value = 'true' if value else 'false'
        elif isinstance(value, (dict, list)):
            str_value = json.dumps(value)
        else:
            str_value = str(value)

        cursor.execute("""
            INSERT INTO heracles_config (config_key, config_value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (config_key) DO UPDATE SET
                config_value = EXCLUDED.config_value,
                updated_at = NOW()
        """, (key, str_value))

        conn.commit()
        conn.close()

        # Update cache
        _config_cache[key] = value
        return True
    except Exception as e:
        logger.error(f"Failed to set config value {key}: {e}")
        return False


def is_ml_approved() -> bool:
    """Check if ML model has been approved for use."""
    return _get_config_value('ml_approved', False) == True or _get_config_value('ml_approved', 'false') == 'true'


def approve_ml_model() -> bool:
    """Approve the ML model for use in signal generation."""
    return _set_config_value('ml_approved', True)


def revoke_ml_approval() -> bool:
    """Revoke ML model approval (revert to Bayesian)."""
    return _set_config_value('ml_approved', False)


def is_ab_test_enabled() -> bool:
    """Check if A/B test for dynamic stops is enabled."""
    return _get_config_value('ab_test_stops_enabled', False) == True or _get_config_value('ab_test_stops_enabled', 'false') == 'true'


def enable_ab_test() -> bool:
    """Enable A/B test for dynamic vs fixed stops."""
    return _set_config_value('ab_test_stops_enabled', True)


def disable_ab_test() -> bool:
    """Disable A/B test (use dynamic stops only)."""
    return _set_config_value('ab_test_stops_enabled', False)


def get_ab_assignment() -> str:
    """
    Get A/B test assignment for current trade.

    Returns 'FIXED' or 'DYNAMIC' with 50% probability each.
    Only called when A/B test is enabled.
    """
    return 'FIXED' if random.random() < 0.5 else 'DYNAMIC'


class HERACLESSignalGenerator:
    """
    Generates trading signals based on GEX analysis.

    Core Logic:
    1. Determine gamma regime (positive/negative)
    2. Positive gamma: Look for mean reversion setups (fade extremes)
    3. Negative gamma: Look for momentum breakouts (trade with trend)
    4. Calculate win probability using Bayesian tracker
    5. Position size using Fixed Fractional + ATR
    """

    def __init__(self, config: HERACLESConfig, win_tracker: BayesianWinTracker):
        self.config = config
        self.win_tracker = win_tracker

    def generate_signal(
        self,
        current_price: float,
        gex_data: Dict[str, Any],
        vix: float,
        atr: float,
        account_balance: float,
        is_overnight: bool = False
    ) -> Optional[FuturesSignal]:
        """
        Generate a trading signal based on current market conditions.

        Args:
            current_price: Current MES price
            gex_data: GEX analysis data (flip_point, call_wall, put_wall, net_gex)
            vix: Current VIX level
            atr: Current ATR in points
            account_balance: Current account balance
            is_overnight: Whether this is overnight session (use n+1 GEX)

        Returns:
            FuturesSignal if conditions met, None otherwise
        """
        try:
            # Extract GEX data with fallbacks for invalid/missing values
            # GEX data is already scaled to MES levels by get_gex_data_for_heracles()
            # Use 'or' to handle None values (key exists but value is None)
            flip_point = gex_data.get('flip_point') or 0
            call_wall = gex_data.get('call_wall') or 0
            put_wall = gex_data.get('put_wall') or 0
            net_gex = gex_data.get('net_gex') or 0
            gex_ratio = gex_data.get('gex_ratio') or 1.0

            # Fallback to synthetic GEX levels if data is invalid
            # CRITICAL: If flip_point = current_price, distance = 0, and NO signals can be generated
            # We must offset the flip_point to allow signal generation
            gex_is_synthetic = False
            if flip_point <= 0:
                # When GEX data unavailable, create synthetic levels that allow trading
                # Offset flip_point by 1% below current price (assumes slight bullish bias from historical data)
                # This allows mean reversion SHORT signals when price is above flip_point
                # and mean reversion LONG signals when price is below flip_point
                synthetic_offset_pct = 0.01  # 1% offset
                flip_point = current_price * (1 - synthetic_offset_pct)
                gex_is_synthetic = True
                logger.warning(
                    f"GEX flip_point unavailable - using SYNTHETIC flip_point={flip_point:.2f} "
                    f"({synthetic_offset_pct*100:.1f}% below current_price={current_price:.2f}). "
                    f"Signal quality may be reduced. Check SPX GEX data source."
                )
            if call_wall <= 0:
                call_wall = current_price + 50  # 50 MES points above
                if gex_is_synthetic:
                    logger.debug(f"Using synthetic call_wall={call_wall:.2f}")
            if put_wall <= 0:
                put_wall = current_price - 50  # 50 MES points below
                if gex_is_synthetic:
                    logger.debug(f"Using synthetic put_wall={put_wall:.2f}")

            # For overnight, use n+1 (next day's expected levels)
            if is_overnight:
                # Use 'or 0' to handle None values (key exists but value is None)
                n1_flip = gex_data.get('n1_flip_point') or 0
                n1_call = gex_data.get('n1_call_wall') or 0
                n1_put = gex_data.get('n1_put_wall') or 0
                # Only use n+1 data if valid
                if n1_flip > 0:
                    flip_point = n1_flip
                if n1_call > 0:
                    call_wall = n1_call
                if n1_put > 0:
                    put_wall = n1_put

            # Determine gamma regime
            gamma_regime = self._determine_gamma_regime(net_gex)

            # Log signal generation context for debugging
            logger.debug(
                f"Signal generation: price={current_price:.2f}, flip={flip_point:.2f}, "
                f"net_gex={net_gex:.2e}, regime={gamma_regime.value}"
            )

            # Generate signal based on regime
            if gamma_regime == GammaRegime.POSITIVE:
                signal = self._generate_mean_reversion_signal(
                    current_price, flip_point, call_wall, put_wall,
                    vix, atr, net_gex, gamma_regime
                )
            else:
                signal = self._generate_momentum_signal(
                    current_price, flip_point, call_wall, put_wall,
                    vix, atr, net_gex, gamma_regime
                )

            if signal is None:
                logger.debug(
                    f"No signal generated: regime={gamma_regime.value}, "
                    f"distance_from_flip={((current_price - flip_point) / flip_point) * 100:.2f}%"
                )
                return None

            # Calculate win probability (uses ML if trained, otherwise Bayesian)
            signal.win_probability = self._calculate_win_probability(gamma_regime, signal, is_overnight)

            # Check minimum probability threshold
            if signal.win_probability < self.config.min_win_probability:
                logger.info(f"Signal rejected: win_prob {signal.win_probability:.2%} < min {self.config.min_win_probability:.2%}")
                return None

            # Calculate position size
            signal.contracts = self.config.calculate_position_size(
                account_balance, atr, current_price
            )

            # Set stop and breakeven prices (with A/B test support)
            signal, stop_type, stop_points = self._set_stop_levels(signal, atr)

            # Store stop info on signal for tracking (used by trader to save to DB)
            signal.stop_type = stop_type
            signal.stop_points_used = stop_points

            logger.info(
                f"Generated {signal.direction.value} signal: "
                f"price={current_price:.2f}, regime={gamma_regime.value}, "
                f"win_prob={signal.win_probability:.2%}, contracts={signal.contracts}, "
                f"stop_type={stop_type}, stop_pts={stop_points:.2f}"
            )

            return signal

        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return None

    def _determine_gamma_regime(self, net_gex: float) -> GammaRegime:
        """
        Determine current gamma regime.

        POSITIVE GAMMA (net_gex > 0):
        - Market makers are long gamma
        - They sell into rallies, buy dips
        - Price tends to mean revert
        - Strategy: FADE moves away from flip point

        NEGATIVE GAMMA (net_gex < 0):
        - Market makers are short gamma
        - They buy into rallies, sell dips
        - Price tends to accelerate (momentum)
        - Strategy: TRADE with momentum on breakouts
        """
        if net_gex > self.config.positive_gamma_threshold:
            return GammaRegime.POSITIVE
        elif net_gex < self.config.negative_gamma_threshold:
            return GammaRegime.NEGATIVE
        else:
            return GammaRegime.NEUTRAL

    def _generate_mean_reversion_signal(
        self,
        current_price: float,
        flip_point: float,
        call_wall: float,
        put_wall: float,
        vix: float,
        atr: float,
        net_gex: float,
        gamma_regime: GammaRegime
    ) -> Optional[FuturesSignal]:
        """
        Generate mean reversion signal for positive gamma.

        Logic:
        - Price above flip point → expect pullback → SHORT
        - Price below flip point → expect bounce → LONG
        - Further from flip point = stronger signal (more stretched)
        """
        # Safety check for division by zero
        if flip_point <= 0:
            logger.warning(f"Invalid flip_point={flip_point}, cannot generate mean reversion signal")
            return None

        distance_from_flip = current_price - flip_point
        distance_pct = (distance_from_flip / flip_point) * 100

        # Need some distance from flip point to fade
        min_distance_pct = self.config.flip_point_proximity_pct

        # Signal strength based on distance
        confidence = min(0.95, 0.5 + (abs(distance_pct) / 2))

        logger.debug(
            f"Mean reversion check: distance_pct={distance_pct:.2f}%, "
            f"min_distance_pct={min_distance_pct}%, exceeds={abs(distance_pct) > min_distance_pct}"
        )

        if distance_pct > min_distance_pct:
            # Price above flip - expect mean reversion down
            direction = TradeDirection.SHORT
            source = SignalSource.GEX_MEAN_REVERSION
            reasoning = (
                f"POSITIVE GAMMA mean reversion: Price {current_price:.2f} is "
                f"{distance_pct:.2f}% above flip point {flip_point:.2f}. "
                f"Expect pullback toward flip. Call wall at {call_wall:.2f}."
            )

        elif distance_pct < -min_distance_pct:
            # Price below flip - expect mean reversion up
            direction = TradeDirection.LONG
            source = SignalSource.GEX_MEAN_REVERSION
            reasoning = (
                f"POSITIVE GAMMA mean reversion: Price {current_price:.2f} is "
                f"{abs(distance_pct):.2f}% below flip point {flip_point:.2f}. "
                f"Expect bounce toward flip. Put wall at {put_wall:.2f}."
            )

        else:
            # Too close to flip point - no trade
            return None

        return FuturesSignal(
            direction=direction,
            confidence=confidence,
            source=source,
            current_price=current_price,
            gamma_regime=gamma_regime,
            gex_value=net_gex,
            flip_point=flip_point,
            call_wall=call_wall,
            put_wall=put_wall,
            vix=vix,
            atr=atr,
            entry_price=current_price,
            reasoning=reasoning
        )

    def _generate_momentum_signal(
        self,
        current_price: float,
        flip_point: float,
        call_wall: float,
        put_wall: float,
        vix: float,
        atr: float,
        net_gex: float,
        gamma_regime: GammaRegime
    ) -> Optional[FuturesSignal]:
        """
        Generate momentum signal for negative gamma.

        ENHANCED LOGIC - Negative gamma amplifies moves in BOTH directions:

        1. BREAKOUT SIGNALS (price beyond flip):
           - Price above flip + momentum → LONG (continuation)
           - Price below flip + momentum → SHORT (continuation)

        2. WALL BOUNCE SIGNALS (bidirectional opportunity):
           - Price near PUT WALL (support) → LONG even if below flip
           - Price near CALL WALL (resistance) → SHORT even if above flip

        In negative gamma, strong moves can happen from walls towards flip.
        This captures bullish opportunities below flip and bearish opportunities above flip.
        """
        # Safety check for invalid prices
        if flip_point <= 0 or call_wall <= 0 or put_wall <= 0:
            logger.warning(f"Invalid GEX levels: flip={flip_point}, call={call_wall}, put={put_wall}")
            return None

        distance_from_flip = current_price - flip_point

        # Breakout threshold for flip-based signals
        breakout_threshold = atr * self.config.breakout_atr_threshold

        # Wall proximity threshold - within 1.5 ATR of wall is "near"
        wall_proximity_threshold = atr * 1.5

        # Calculate distance to walls
        distance_to_call_wall = call_wall - current_price
        distance_to_put_wall = current_price - put_wall

        # Calculate ranges for confidence
        call_to_flip_range = max(1.0, call_wall - flip_point)  # Min 1 point
        flip_to_put_range = max(1.0, flip_point - put_wall)    # Min 1 point
        total_range = call_to_flip_range + flip_to_put_range

        logger.debug(
            f"Momentum check: distance_from_flip={distance_from_flip:.2f} pts, "
            f"distance_to_put={distance_to_put_wall:.2f}, distance_to_call={distance_to_call_wall:.2f}, "
            f"wall_proximity_threshold={wall_proximity_threshold:.2f} pts"
        )

        direction = None
        source = None
        confidence = 0.0
        reasoning = ""

        # =====================================================================
        # PRIORITY 1: Classic breakout signals (price has broken through flip)
        # =====================================================================
        if distance_from_flip > breakout_threshold:
            # Above flip - momentum LONG (continuation)
            direction = TradeDirection.LONG
            source = SignalSource.GEX_MOMENTUM
            confidence = min(0.90, 0.5 + (distance_to_call_wall / call_to_flip_range) * 0.4)
            reasoning = (
                f"NEGATIVE GAMMA momentum: Price {current_price:.2f} broke "
                f"{breakout_threshold:.2f} pts above flip {flip_point:.2f}. "
                f"Momentum continuation expected. Target call wall at {call_wall:.2f}."
            )

        elif distance_from_flip < -breakout_threshold:
            # Below flip - momentum SHORT (continuation)
            direction = TradeDirection.SHORT
            source = SignalSource.GEX_MOMENTUM
            confidence = min(0.90, 0.5 + (distance_to_put_wall / flip_to_put_range) * 0.4)
            reasoning = (
                f"NEGATIVE GAMMA momentum: Price {current_price:.2f} broke "
                f"{breakout_threshold:.2f} pts below flip {flip_point:.2f}. "
                f"Momentum continuation expected. Target put wall at {put_wall:.2f}."
            )

        # =====================================================================
        # PRIORITY 2: Wall bounce signals (bidirectional momentum opportunity)
        # These allow LONG below flip and SHORT above flip
        # =====================================================================
        elif distance_to_put_wall < wall_proximity_threshold and distance_to_put_wall > 0:
            # Near PUT WALL (support) - LONG targeting flip
            # This captures bullish opportunity BELOW the flip point
            direction = TradeDirection.LONG
            source = SignalSource.GEX_WALL_BOUNCE
            # Confidence based on how much room to flip and VIX
            room_to_flip = abs(distance_from_flip)
            confidence = min(0.80, 0.55 + (room_to_flip / flip_to_put_range) * 0.25)
            # Reduce confidence in very high VIX (wall may break)
            if vix > 25:
                confidence *= 0.9
            reasoning = (
                f"NEGATIVE GAMMA wall bounce: Price {current_price:.2f} near put wall "
                f"{put_wall:.2f} (dist={distance_to_put_wall:.2f}). "
                f"Bullish momentum opportunity - targeting flip {flip_point:.2f}. "
                f"In neg gamma, strong moves happen from walls."
            )
            logger.info(
                f"Wall bounce LONG below flip: price={current_price:.2f}, "
                f"flip={flip_point:.2f}, put_wall={put_wall:.2f}, conf={confidence:.2%}"
            )

        elif distance_to_call_wall < wall_proximity_threshold and distance_to_call_wall > 0:
            # Near CALL WALL (resistance) - SHORT targeting flip
            # This captures bearish opportunity ABOVE the flip point
            direction = TradeDirection.SHORT
            source = SignalSource.GEX_WALL_BOUNCE
            # Confidence based on how much room to flip
            room_to_flip = abs(distance_from_flip)
            confidence = min(0.80, 0.55 + (room_to_flip / call_to_flip_range) * 0.25)
            # Reduce confidence in very high VIX (wall may break)
            if vix > 25:
                confidence *= 0.9
            reasoning = (
                f"NEGATIVE GAMMA wall bounce: Price {current_price:.2f} near call wall "
                f"{call_wall:.2f} (dist={distance_to_call_wall:.2f}). "
                f"Bearish momentum opportunity - targeting flip {flip_point:.2f}. "
                f"In neg gamma, strong moves happen from walls."
            )
            logger.info(
                f"Wall bounce SHORT above flip: price={current_price:.2f}, "
                f"flip={flip_point:.2f}, call_wall={call_wall:.2f}, conf={confidence:.2%}"
            )

        else:
            # No clear signal - price in no-man's land (between walls, near flip)
            logger.debug(
                f"No momentum signal: price in neutral zone. "
                f"dist_from_flip={distance_from_flip:.2f}, not near walls"
            )
            return None

        return FuturesSignal(
            direction=direction,
            confidence=confidence,
            source=source,
            current_price=current_price,
            gamma_regime=gamma_regime,
            gex_value=net_gex,
            flip_point=flip_point,
            call_wall=call_wall,
            put_wall=put_wall,
            vix=vix,
            atr=atr,
            entry_price=current_price,
            reasoning=reasoning
        )

    def _calculate_win_probability(
        self,
        gamma_regime: GammaRegime,
        signal: FuturesSignal,
        is_overnight: bool = False
    ) -> float:
        """
        Calculate win probability using ML (if approved and trained) or Bayesian fallback.

        ML Prediction (when trained AND approved):
        - Uses XGBoost model trained on historical trade outcomes
        - Features: VIX, ATR, gamma regime, distance to levels, time factors
        - REQUIRES explicit approval via /api/heracles/ml/approve

        Bayesian Fallback (before ML training or approval):
        - Starts with prior, updates based on regime-specific win rate
        - Blends with signal confidence
        """
        # Try ML prediction first (if model is trained AND approved)
        ml_advisor = _get_ml_advisor()
        ml_approved = is_ml_approved()

        if ml_advisor is not None and ml_advisor.model is not None and ml_approved:
            try:
                # Build feature dict for ML prediction
                # Must match FEATURE_COLS in ml.py exactly
                distance_to_flip_pct = 0
                if signal.flip_point and signal.flip_point > 0:
                    distance_to_flip_pct = ((signal.current_price - signal.flip_point) / signal.flip_point) * 100

                distance_to_call_wall_pct = 0
                if signal.call_wall and signal.call_wall > 0:
                    distance_to_call_wall_pct = ((signal.call_wall - signal.current_price) / signal.current_price) * 100

                distance_to_put_wall_pct = 0
                if signal.put_wall and signal.put_wall > 0:
                    distance_to_put_wall_pct = ((signal.current_price - signal.put_wall) / signal.current_price) * 100

                now = datetime.now(CENTRAL_TZ)

                features = {
                    'vix': signal.vix or 18.0,
                    'atr': signal.atr or 5.0,
                    'gamma_regime_encoded': 1 if gamma_regime == GammaRegime.POSITIVE else (
                        -1 if gamma_regime == GammaRegime.NEGATIVE else 0
                    ),
                    'distance_to_flip_pct': distance_to_flip_pct,
                    'distance_to_call_wall_pct': distance_to_call_wall_pct,
                    'distance_to_put_wall_pct': distance_to_put_wall_pct,
                    'day_of_week': now.weekday(),
                    'hour_of_day': now.hour,
                    'is_overnight': 1 if is_overnight else 0,
                    'positive_gamma_win_rate': self.win_tracker.get_regime_probability(GammaRegime.POSITIVE),
                    'negative_gamma_win_rate': self.win_tracker.get_regime_probability(GammaRegime.NEGATIVE),
                    'signal_confidence': signal.confidence,
                }

                ml_result = ml_advisor.predict(features)
                if ml_result and 'win_probability' in ml_result:
                    ml_prob = ml_result['win_probability']
                    logger.debug(
                        f"ML win probability: {ml_prob:.2%} (confidence: {ml_result.get('confidence', 'N/A')})"
                    )
                    return round(ml_prob, 4)

            except Exception as e:
                logger.warning(f"ML prediction failed, falling back to Bayesian: {e}")
        elif ml_advisor is not None and ml_advisor.model is not None and not ml_approved:
            logger.debug("ML model trained but not approved - using Bayesian fallback")

        # Bayesian fallback (when ML not available or not approved)
        return self._calculate_bayesian_probability(gamma_regime, signal)

    def _calculate_bayesian_probability(
        self,
        gamma_regime: GammaRegime,
        signal: FuturesSignal
    ) -> float:
        """
        Calculate win probability using Bayesian + confidence blend.
        Used as fallback when ML model is not trained.
        """
        # Get regime-specific Bayesian probability
        bayesian_prob = self.win_tracker.get_regime_probability(gamma_regime)

        # Blend with signal confidence
        # More weight to Bayesian as we collect more data
        bayesian_weight = min(0.7, 0.3 + (self.win_tracker.total_trades / 100))
        confidence_weight = 1 - bayesian_weight

        blended_prob = (bayesian_prob * bayesian_weight) + (signal.confidence * confidence_weight)

        # VIX adjustment - higher VIX = more uncertainty = lower probability
        if signal.vix > 25:
            vix_penalty = (signal.vix - 25) * 0.01  # 1% penalty per VIX point above 25
            blended_prob = max(0.3, blended_prob - vix_penalty)
        elif signal.vix < 15:
            # Low VIX = calmer markets = slight boost
            blended_prob = min(0.85, blended_prob + 0.02)

        return round(blended_prob, 4)

    def _set_stop_levels(self, signal: FuturesSignal, atr: float) -> Tuple[FuturesSignal, str, float]:
        """
        Set stop loss levels based on A/B test assignment or dynamic by default.

        A/B Test Mode (when enabled):
        - 50% trades use FIXED stop (base config value unchanged)
        - 50% trades use DYNAMIC stop (VIX/ATR/regime adjusted)

        Default Mode (A/B disabled):
        - All trades use DYNAMIC stops

        Dynamic Stop Logic:
        1. Base stop from config (default 2.5 points)
        2. VIX adjustment: widen when VIX > 20, tighten when VIX < 15
        3. ATR adjustment: scale based on current volatility vs average
        4. Regime adjustment: tighter for positive gamma (mean reversion)

        Returns:
            Tuple of (signal, stop_type, stop_points_used)
            stop_type is 'FIXED' or 'DYNAMIC'
            stop_points_used is the actual stop distance in points
        """
        base_stop = self.config.initial_stop_points

        # Determine stop type based on A/B test status
        if is_ab_test_enabled():
            stop_type = get_ab_assignment()
        else:
            # Default to dynamic when A/B test is disabled
            stop_type = 'DYNAMIC'

        # Calculate stop distance based on assignment
        if stop_type == 'FIXED':
            stop_distance = base_stop
            logger.info(
                f"A/B Test: FIXED stop selected - using base stop of {base_stop:.2f} pts"
            )
        else:
            # Calculate dynamic stop distance
            stop_distance = self._calculate_dynamic_stop(
                base_stop=base_stop,
                vix=signal.vix,
                atr=atr,
                gamma_regime=signal.gamma_regime
            )
            logger.info(
                f"{'A/B Test: ' if is_ab_test_enabled() else ''}DYNAMIC stop: "
                f"base={base_stop:.2f}, vix={signal.vix:.1f}, atr={atr:.2f}, "
                f"regime={signal.gamma_regime.value}, final={stop_distance:.2f} pts"
            )

        if signal.direction == TradeDirection.LONG:
            signal.stop_price = signal.entry_price - stop_distance
            signal.target_price = signal.entry_price + self.config.profit_target_points
        else:
            signal.stop_price = signal.entry_price + stop_distance
            signal.target_price = signal.entry_price - self.config.profit_target_points

        return signal, stop_type, stop_distance

    def _calculate_dynamic_stop(
        self,
        base_stop: float,
        vix: float,
        atr: float,
        gamma_regime: GammaRegime
    ) -> float:
        """
        Calculate dynamic stop distance based on market conditions.

        Args:
            base_stop: Base stop distance from config (default 2.5 pts)
            vix: Current VIX level
            atr: Current ATR in points
            gamma_regime: Current gamma regime

        Returns:
            Adjusted stop distance in points

        Logic:
        1. VIX ADJUSTMENT (primary factor):
           - VIX < 15: Tighten stop by 20% (calm markets, less room needed)
           - VIX 15-20: Use base stop (normal conditions)
           - VIX 20-25: Widen stop by 20% (elevated volatility)
           - VIX 25-30: Widen stop by 40%
           - VIX > 30: Widen stop by 60% (high volatility, need more room)

        2. ATR ADJUSTMENT (secondary factor):
           - ATR < 3 pts: Tighten by 15% (low intraday vol)
           - ATR 3-5 pts: No adjustment (normal)
           - ATR 5-8 pts: Widen by 15%
           - ATR > 8 pts: Widen by 30% (high intraday vol)

        3. REGIME ADJUSTMENT (tertiary factor):
           - POSITIVE gamma: Tighten by 10% (mean reversion = tighter stops)
           - NEGATIVE gamma: Widen by 10% (momentum = more room for swings)
           - NEUTRAL: No adjustment

        Final stop = base_stop * vix_mult * atr_mult * regime_mult
        Capped between 1.5 and 6 points to maintain profitability.
        """
        # 1. VIX Adjustment
        if vix <= 0:
            vix_multiplier = 1.0  # Default if VIX unavailable
        elif vix < 15:
            vix_multiplier = 0.80  # Calm markets - tighten 20%
        elif vix < 20:
            vix_multiplier = 1.0   # Normal - use base
        elif vix < 25:
            vix_multiplier = 1.20  # Elevated - widen 20%
        elif vix < 30:
            vix_multiplier = 1.40  # High - widen 40%
        else:
            vix_multiplier = 1.60  # Very high - widen 60%

        # 2. ATR Adjustment
        if atr <= 0:
            atr_multiplier = 1.0  # Default if ATR unavailable
        elif atr < 3:
            atr_multiplier = 0.85  # Low intraday vol - tighten 15%
        elif atr < 5:
            atr_multiplier = 1.0   # Normal
        elif atr < 8:
            atr_multiplier = 1.15  # Higher vol - widen 15%
        else:
            atr_multiplier = 1.30  # High vol - widen 30%

        # 3. Regime Adjustment
        if gamma_regime == GammaRegime.POSITIVE:
            regime_multiplier = 0.90  # Mean reversion - tighter (10% tighter)
        elif gamma_regime == GammaRegime.NEGATIVE:
            regime_multiplier = 1.10  # Momentum - more room (10% wider)
        else:
            regime_multiplier = 1.0   # Neutral - no adjustment

        # Calculate final stop
        dynamic_stop = base_stop * vix_multiplier * atr_multiplier * regime_multiplier

        # Cap between 1.5 and 6 points for profitability
        # Too tight (<1.5) = stopped out by noise
        # Too wide (>6) = risk/reward deteriorates
        MIN_STOP = 1.5
        MAX_STOP = 6.0

        capped_stop = max(MIN_STOP, min(MAX_STOP, dynamic_stop))

        if capped_stop != dynamic_stop:
            logger.debug(
                f"Dynamic stop capped: calculated={dynamic_stop:.2f}, "
                f"capped={capped_stop:.2f} (range {MIN_STOP}-{MAX_STOP})"
            )

        return round(capped_stop, 2)

    def check_wall_bounce(
        self,
        current_price: float,
        gex_data: Dict[str, Any],
        vix: float,
        atr: float
    ) -> Optional[FuturesSignal]:
        """
        Check for wall bounce setup (price near call/put wall).

        Walls act as support/resistance. Trading bounces off walls
        can be profitable in both gamma regimes.
        """
        call_wall = gex_data.get('call_wall') or (current_price + 100)
        put_wall = gex_data.get('put_wall') or (current_price - 100)
        flip_point = gex_data.get('flip_point') or current_price
        net_gex = gex_data.get('net_gex') or 0

        gamma_regime = self._determine_gamma_regime(net_gex)

        # Distance to walls as percentage
        distance_to_call_pct = ((call_wall - current_price) / current_price) * 100
        distance_to_put_pct = ((current_price - put_wall) / current_price) * 100

        # Near wall threshold (0.3%)
        wall_threshold = 0.3

        if distance_to_call_pct < wall_threshold:
            # Near call wall - expect rejection, SHORT
            return FuturesSignal(
                direction=TradeDirection.SHORT,
                confidence=0.65,
                source=SignalSource.GEX_WALL_BOUNCE,
                current_price=current_price,
                gamma_regime=gamma_regime,
                gex_value=net_gex,
                flip_point=flip_point,
                call_wall=call_wall,
                put_wall=put_wall,
                vix=vix,
                atr=atr,
                entry_price=current_price,
                reasoning=f"WALL BOUNCE: Price {current_price:.2f} near call wall {call_wall:.2f}. Expect rejection."
            )

        elif distance_to_put_pct < wall_threshold:
            # Near put wall - expect bounce, LONG
            return FuturesSignal(
                direction=TradeDirection.LONG,
                confidence=0.65,
                source=SignalSource.GEX_WALL_BOUNCE,
                current_price=current_price,
                gamma_regime=gamma_regime,
                gex_value=net_gex,
                flip_point=flip_point,
                call_wall=call_wall,
                put_wall=put_wall,
                vix=vix,
                atr=atr,
                entry_price=current_price,
                reasoning=f"WALL BOUNCE: Price {current_price:.2f} near put wall {put_wall:.2f}. Expect bounce."
            )

        return None

    def check_flip_point_trade(
        self,
        current_price: float,
        gex_data: Dict[str, Any],
        vix: float,
        atr: float
    ) -> Optional[FuturesSignal]:
        """
        Check for flip point trade (price crossing flip point).

        Flip point crossings can signal regime changes and directional moves.
        """
        flip_point = gex_data.get('flip_point') or current_price
        prev_price = gex_data.get('prev_price') or current_price
        call_wall = gex_data.get('call_wall') or (current_price + 50)
        put_wall = gex_data.get('put_wall') or (current_price - 50)
        net_gex = gex_data.get('net_gex') or 0

        gamma_regime = self._determine_gamma_regime(net_gex)

        # Check for flip point crossover
        crossed_above = prev_price < flip_point <= current_price
        crossed_below = prev_price > flip_point >= current_price

        if crossed_above:
            return FuturesSignal(
                direction=TradeDirection.LONG,
                confidence=0.60,
                source=SignalSource.GEX_FLIP_POINT,
                current_price=current_price,
                gamma_regime=gamma_regime,
                gex_value=net_gex,
                flip_point=flip_point,
                call_wall=call_wall,
                put_wall=put_wall,
                vix=vix,
                atr=atr,
                entry_price=current_price,
                reasoning=f"FLIP POINT CROSS: Price crossed above flip {flip_point:.2f}. Bullish signal."
            )

        elif crossed_below:
            return FuturesSignal(
                direction=TradeDirection.SHORT,
                confidence=0.60,
                source=SignalSource.GEX_FLIP_POINT,
                current_price=current_price,
                gamma_regime=gamma_regime,
                gex_value=net_gex,
                flip_point=flip_point,
                call_wall=call_wall,
                put_wall=put_wall,
                vix=vix,
                atr=atr,
                entry_price=current_price,
                reasoning=f"FLIP POINT CROSS: Price crossed below flip {flip_point:.2f}. Bearish signal."
            )

        return None


def get_gex_data_for_heracles(symbol: str = "SPX") -> Dict[str, Any]:
    """
    Fetch GEX data for HERACLES signal generation.

    This connects to the existing AlphaGEX GEX calculation infrastructure.

    IMPORTANT: HERACLES trades MES futures which track the S&P 500 index (~5900 level).
    We use SPX options data (also at ~5900 level) for accurate GEX levels.
    SPX requires Tradier PRODUCTION keys (sandbox doesn't support SPX).

    SPX = S&P 500 Index (~5900)
    MES = Micro E-mini S&P 500 futures (~5900, tracks SPX directly)
    SPY = SPDR S&P 500 ETF (~590, 1/10th of SPX)
    """
    try:
        # Use TradierGEXCalculator with sandbox=False for SPX (production keys required)
        from data.gex_calculator import TradierGEXCalculator

        # SPX requires production API (sandbox doesn't support index options)
        calculator = TradierGEXCalculator(sandbox=False)
        gex_result = calculator.calculate_gex(symbol)

        if gex_result:
            # SPX GEX levels are already at the correct scale for MES (~5900)
            # No scaling needed - SPX and MES are both at S&P 500 index level
            flip_point = gex_result.get('flip_point', 0)
            call_wall = gex_result.get('call_wall', 0)
            put_wall = gex_result.get('put_wall', 0)
            net_gex = gex_result.get('net_gex', 0)
            spot_price = gex_result.get('spot_price', 0)

            # If walls are 0 or invalid but we have flip_point, estimate walls
            # This handles the case where Tradier doesn't provide gamma for SPX
            if flip_point > 0:
                if call_wall <= 0:
                    # Estimate call wall as 1% above flip point
                    call_wall = flip_point * 1.01
                    logger.debug(f"Estimated call_wall: {call_wall:.2f} (flip * 1.01)")
                if put_wall <= 0:
                    # Estimate put wall as 1% below flip point
                    put_wall = flip_point * 0.99
                    logger.debug(f"Estimated put_wall: {put_wall:.2f} (flip * 0.99)")

            # If net_gex is 0 but we have valid walls, estimate regime from price position
            # This is a heuristic when gamma data isn't available
            if net_gex == 0 and flip_point > 0 and spot_price > 0:
                # Positive GEX when price is between walls (mean reversion environment)
                # Use small positive value to trigger mean reversion strategy
                net_gex = 1e6  # Small positive = positive gamma regime
                logger.debug(f"Estimated net_gex as positive (mean reversion)")

            logger.info(
                f"HERACLES GEX data for {symbol}: flip={flip_point:.2f}, "
                f"call_wall={call_wall:.2f}, put_wall={put_wall:.2f}, net_gex={net_gex:.2e}"
            )

            return {
                'flip_point': flip_point,
                'call_wall': call_wall,
                'put_wall': put_wall,
                'net_gex': net_gex,
                'gex_ratio': gex_result.get('gex_ratio', 1.0),
                # n+1 data for overnight (if available)
                'n1_flip_point': gex_result.get('n1_flip_point'),
                'n1_call_wall': gex_result.get('n1_call_wall'),
                'n1_put_wall': gex_result.get('n1_put_wall'),
            }

        logger.warning(f"GEX calculator returned no data for {symbol}")

    except Exception as e:
        logger.warning(f"Could not get GEX data from calculator: {e}")

    # Try API endpoint as fallback (SPX endpoint)
    try:
        import requests
        response = requests.get(f"http://localhost:8000/api/gex/{symbol}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            # SPX data is already at correct scale for MES
            return {
                'flip_point': data.get('flip_point', 0),
                'call_wall': data.get('call_wall', 0),
                'put_wall': data.get('put_wall', 0),
                'net_gex': data.get('net_gex', 0),
                'gex_ratio': data.get('gex_ratio', 1.0),
            }
    except Exception as e:
        logger.warning(f"Could not get GEX data from API: {e}")

    # Return empty data if all fails
    logger.error(f"Failed to get GEX data for {symbol} - HERACLES signals will use fallback prices")
    return {
        'flip_point': 0,
        'call_wall': 0,
        'put_wall': 0,
        'net_gex': 0,
        'gex_ratio': 1.0,
    }
