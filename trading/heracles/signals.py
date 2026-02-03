"""
HERACLES - Signal Generator
============================

GEX-based signal generation for MES futures scalping.

Strategy Logic:
- POSITIVE GAMMA: Mean reversion - fade moves, price tends to revert toward flip point
- NEGATIVE GAMMA: Momentum - trade breakouts, price tends to accelerate away from flip point

Uses n+1 GEX data for overnight trading (forward-looking levels).
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from .models import (
    FuturesSignal, TradeDirection, GammaRegime, SignalSource,
    HERACLESConfig, BayesianWinTracker, MES_POINT_VALUE, CENTRAL_TZ
)

logger = logging.getLogger(__name__)


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

            # Fallback to reasonable defaults if GEX data is invalid
            # Use current_price as flip point if GEX data unavailable
            if flip_point <= 0:
                flip_point = current_price
                logger.warning(f"GEX flip_point invalid, using current_price={current_price:.2f}")
            if call_wall <= 0:
                call_wall = current_price + 50  # 50 MES points above
            if put_wall <= 0:
                put_wall = current_price - 50  # 50 MES points below

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

            # Calculate win probability
            signal.win_probability = self._calculate_win_probability(gamma_regime, signal)

            # Check minimum probability threshold
            if signal.win_probability < self.config.min_win_probability:
                logger.info(f"Signal rejected: win_prob {signal.win_probability:.2%} < min {self.config.min_win_probability:.2%}")
                return None

            # Calculate position size
            signal.contracts = self.config.calculate_position_size(
                account_balance, atr, current_price
            )

            # Set stop and breakeven prices
            signal = self._set_stop_levels(signal, atr)

            logger.info(
                f"Generated {signal.direction.value} signal: "
                f"price={current_price:.2f}, regime={gamma_regime.value}, "
                f"win_prob={signal.win_probability:.2%}, contracts={signal.contracts}"
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

        Logic:
        - Price breaking above flip point → momentum up → LONG
        - Price breaking below flip point → momentum down → SHORT
        - Use ATR for breakout confirmation
        """
        # Safety check for invalid prices
        if flip_point <= 0 or call_wall <= 0 or put_wall <= 0:
            logger.warning(f"Invalid GEX levels: flip={flip_point}, call={call_wall}, put={put_wall}")
            return None

        distance_from_flip = current_price - flip_point

        # Need breakout through flip point plus ATR threshold
        breakout_threshold = atr * self.config.breakout_atr_threshold

        logger.debug(
            f"Momentum check: distance={distance_from_flip:.2f} pts, "
            f"breakout_threshold={breakout_threshold:.2f} pts (ATR={atr:.2f}*{self.config.breakout_atr_threshold}), "
            f"exceeds={abs(distance_from_flip) > breakout_threshold}"
        )

        # Calculate distance to walls
        distance_to_call_wall = call_wall - current_price
        distance_to_put_wall = current_price - put_wall

        # Protect against division by zero in confidence calculation
        call_to_flip_range = max(1.0, call_wall - flip_point)  # Min 1 point
        flip_to_put_range = max(1.0, flip_point - put_wall)    # Min 1 point

        if distance_from_flip > breakout_threshold:
            # Breaking out above flip - momentum long
            direction = TradeDirection.LONG
            source = SignalSource.GEX_MOMENTUM
            # Confidence higher if more room to call wall
            confidence = min(0.90, 0.5 + (distance_to_call_wall / call_to_flip_range) * 0.4)
            reasoning = (
                f"NEGATIVE GAMMA momentum: Price {current_price:.2f} broke "
                f"{breakout_threshold:.2f} pts above flip {flip_point:.2f}. "
                f"Momentum continuation expected. Target call wall at {call_wall:.2f}."
            )

        elif distance_from_flip < -breakout_threshold:
            # Breaking out below flip - momentum short
            direction = TradeDirection.SHORT
            source = SignalSource.GEX_MOMENTUM
            # Confidence higher if more room to put wall
            confidence = min(0.90, 0.5 + (distance_to_put_wall / flip_to_put_range) * 0.4)
            reasoning = (
                f"NEGATIVE GAMMA momentum: Price {current_price:.2f} broke "
                f"{breakout_threshold:.2f} pts below flip {flip_point:.2f}. "
                f"Momentum continuation expected. Target put wall at {put_wall:.2f}."
            )

        else:
            # No clear breakout - no trade
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
        signal: FuturesSignal
    ) -> float:
        """
        Calculate win probability using Bayesian + confidence blend.

        Starts with Bayesian prior, updates based on:
        - Historical regime-specific win rate
        - Signal confidence
        - VIX conditions
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

    def _set_stop_levels(self, signal: FuturesSignal, atr: float) -> FuturesSignal:
        """
        Set stop loss levels based on config.

        For scalping, use FIXED tight stops (3 points = $15 per contract).
        ATR-based stops are too wide for MES scalping.
        """
        # Use fixed stop for scalping - tight stops are essential
        # ATR-based stops were causing 42-point stops (way too wide)
        stop_distance = self.config.initial_stop_points  # 3 points = $15

        if signal.direction == TradeDirection.LONG:
            signal.stop_price = signal.entry_price - stop_distance
            signal.target_price = signal.entry_price + (stop_distance * 2)  # 2:1 R:R
        else:
            signal.stop_price = signal.entry_price + stop_distance
            signal.target_price = signal.entry_price - (stop_distance * 2)

        return signal

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
