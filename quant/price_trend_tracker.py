"""
Price Trend Tracker - Real-time trend analysis for Oracle NEUTRAL regime
==========================================================================

Tracks price history across 5-minute scans to determine:
- Trend direction (UPTREND, DOWNTREND, SIDEWAYS)
- Trend strength (how consistent the move)
- Position within GEX wall range
- Strategy suitability scores

This enables NEUTRAL GEX regime to make intelligent directional decisions
instead of defaulting to FLAT/0.45 win probability.

Author: AlphaGEX Quant
Date: 2026-01-13
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TrendDirection(Enum):
    """Price trend direction"""
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"


@dataclass
class PricePoint:
    """Single price observation"""
    timestamp: datetime
    price: float
    high: float = 0
    low: float = 0


@dataclass
class TrendAnalysis:
    """Complete trend analysis result"""
    # Trend direction and strength
    direction: TrendDirection
    strength: float  # 0-1, how consistent the trend

    # Price history context
    price_now: float
    price_5m_ago: float
    price_15m_ago: float
    price_30m_ago: float
    price_60m_ago: float

    # Intraday range
    high_of_day: float
    low_of_day: float

    # Higher highs / higher lows detection
    is_higher_high: bool
    is_higher_low: bool
    is_lower_high: bool
    is_lower_low: bool

    # Derived direction for NEUTRAL regime
    derived_direction: str  # "BULLISH", "BEARISH", "FLAT"
    derived_confidence: float  # 0-1
    reasoning: str


@dataclass
class WallPositionAnalysis:
    """Analysis of price position relative to GEX walls"""
    # Wall values
    call_wall: float
    put_wall: float

    # Distances (as percentages)
    dist_to_call_wall_pct: float
    dist_to_put_wall_pct: float

    # Position in range (0% = at put wall, 100% = at call wall)
    position_in_range_pct: float

    # Wall range width
    wall_range_width_pct: float

    # Status flags
    is_contained: bool  # Price between put and call wall
    nearest_wall: str  # "CALL_WALL" or "PUT_WALL"
    nearest_wall_distance_pct: float

    # Breach risk based on momentum toward wall
    wall_breach_risk: str  # "LOW", "MEDIUM", "HIGH"


@dataclass
class StrategySuitability:
    """Strategy suitability scores based on market conditions"""
    # Iron Condor suitability (ARES, PEGASUS)
    ic_suitability: float  # 0-1
    ic_reasoning: List[str] = field(default_factory=list)

    # Directional spread suitability (ATHENA, ICARUS)
    bullish_suitability: float = 0.0  # 0-1
    bearish_suitability: float = 0.0  # 0-1
    directional_reasoning: List[str] = field(default_factory=list)

    # Recommended strategy
    recommended_strategy: str = "SKIP"  # "IRON_CONDOR", "BULL_SPREAD", "BEAR_SPREAD", "SKIP"


class PriceTrendTracker:
    """
    Singleton tracker that maintains rolling price history across scans.

    Usage:
        tracker = PriceTrendTracker.get_instance()
        tracker.update(symbol="SPY", price=693.04)
        trend = tracker.analyze_trend("SPY")
    """

    _instance = None
    _lock = None

    # Rolling window size (12 scans = 60 minutes at 5-min intervals)
    WINDOW_SIZE = 12

    def __new__(cls):
        if cls._instance is None:
            import threading
            cls._lock = threading.Lock()
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Price history per symbol (rolling window)
        self._price_history: Dict[str, deque] = {}

        # Daily high/low tracking
        self._daily_high: Dict[str, float] = {}
        self._daily_low: Dict[str, float] = {}
        self._last_date: Dict[str, str] = {}

        # Swing high/low for higher high/low detection
        self._swing_high: Dict[str, float] = {}
        self._swing_low: Dict[str, float] = {}

        self._initialized = True
        logger.info("PriceTrendTracker initialized")

    @classmethod
    def get_instance(cls) -> 'PriceTrendTracker':
        """Get singleton instance"""
        return cls()

    def update(self, symbol: str, price: float, high: float = None, low: float = None) -> None:
        """
        Update price history with new observation.
        Called on every 5-minute scan.
        """
        now = datetime.now(CENTRAL_TZ)
        today = now.strftime("%Y-%m-%d")

        # Initialize history for symbol if needed
        if symbol not in self._price_history:
            self._price_history[symbol] = deque(maxlen=self.WINDOW_SIZE)
            self._daily_high[symbol] = price
            self._daily_low[symbol] = price
            self._swing_high[symbol] = price
            self._swing_low[symbol] = price
            self._last_date[symbol] = today

        # Reset daily high/low on new day
        if self._last_date.get(symbol) != today:
            self._daily_high[symbol] = price
            self._daily_low[symbol] = price
            self._last_date[symbol] = today
            logger.info(f"[TrendTracker] New day for {symbol}, reset daily high/low")

        # Update daily high/low
        if price > self._daily_high[symbol]:
            self._daily_high[symbol] = price
        if price < self._daily_low[symbol]:
            self._daily_low[symbol] = price

        # Update swing high/low (for higher high/low detection)
        # Swing high: price that's higher than neighbors
        # Swing low: price that's lower than neighbors
        history = self._price_history[symbol]
        if len(history) >= 2:
            prev_price = history[-1].price
            prev_prev_price = history[-2].price if len(history) >= 2 else prev_price

            # Check for swing high
            if prev_price > prev_prev_price and prev_price > price:
                if prev_price > self._swing_high.get(symbol, 0):
                    self._swing_high[symbol] = prev_price

            # Check for swing low
            if prev_price < prev_prev_price and prev_price < price:
                if prev_price < self._swing_low.get(symbol, float('inf')):
                    self._swing_low[symbol] = prev_price

        # Add new price point
        point = PricePoint(
            timestamp=now,
            price=price,
            high=high or price,
            low=low or price
        )
        self._price_history[symbol].append(point)

        logger.debug(f"[TrendTracker] {symbol}: ${price:.2f} (history: {len(history)} points)")

    def analyze_trend(self, symbol: str) -> Optional[TrendAnalysis]:
        """
        Analyze price trend from history.
        Returns None if insufficient data.
        """
        if symbol not in self._price_history:
            return None

        history = list(self._price_history[symbol])
        if len(history) < 2:
            return None

        # Get price at various lookback periods
        price_now = history[-1].price
        price_5m_ago = history[-2].price if len(history) >= 2 else price_now
        price_15m_ago = history[-4].price if len(history) >= 4 else price_5m_ago
        price_30m_ago = history[-7].price if len(history) >= 7 else price_15m_ago
        price_60m_ago = history[0].price  # Oldest in window

        # Calculate trend direction
        direction, strength = self._calculate_trend(history)

        # Higher high / higher low detection
        is_higher_high = price_now > self._swing_high.get(symbol, price_now)
        is_higher_low = self._swing_low.get(symbol, price_now) > history[0].price if len(history) > 1 else False
        is_lower_high = self._swing_high.get(symbol, price_now) < history[0].price if len(history) > 1 else False
        is_lower_low = price_now < self._swing_low.get(symbol, price_now)

        # Derive direction for NEUTRAL regime
        derived_direction, derived_confidence, reasoning = self._derive_direction(
            direction, strength, is_higher_high, is_higher_low, is_lower_high, is_lower_low
        )

        return TrendAnalysis(
            direction=direction,
            strength=strength,
            price_now=price_now,
            price_5m_ago=price_5m_ago,
            price_15m_ago=price_15m_ago,
            price_30m_ago=price_30m_ago,
            price_60m_ago=price_60m_ago,
            high_of_day=self._daily_high.get(symbol, price_now),
            low_of_day=self._daily_low.get(symbol, price_now),
            is_higher_high=is_higher_high,
            is_higher_low=is_higher_low,
            is_lower_high=is_lower_high,
            is_lower_low=is_lower_low,
            derived_direction=derived_direction,
            derived_confidence=derived_confidence,
            reasoning=reasoning
        )

    def _calculate_trend(self, history: List[PricePoint]) -> Tuple[TrendDirection, float]:
        """Calculate trend direction and strength from price history"""
        if len(history) < 3:
            return TrendDirection.SIDEWAYS, 0.0

        prices = [p.price for p in history]

        # Count up moves vs down moves
        up_moves = 0
        down_moves = 0
        total_change = 0

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            total_change += change
            if change > 0:
                up_moves += 1
            elif change < 0:
                down_moves += 1

        total_moves = up_moves + down_moves
        if total_moves == 0:
            return TrendDirection.SIDEWAYS, 0.0

        # Trend strength = consistency of direction
        # If 80% of moves are in same direction = strong trend
        up_ratio = up_moves / total_moves
        down_ratio = down_moves / total_moves

        # Net price change as percentage
        start_price = prices[0]
        end_price = prices[-1]
        net_change_pct = (end_price - start_price) / start_price * 100

        # Determine direction
        if net_change_pct > 0.1 and up_ratio > 0.55:
            direction = TrendDirection.UPTREND
            strength = min(1.0, up_ratio + abs(net_change_pct) / 2)
        elif net_change_pct < -0.1 and down_ratio > 0.55:
            direction = TrendDirection.DOWNTREND
            strength = min(1.0, down_ratio + abs(net_change_pct) / 2)
        else:
            direction = TrendDirection.SIDEWAYS
            strength = max(up_ratio, down_ratio)

        return direction, strength

    def _derive_direction(
        self,
        trend: TrendDirection,
        strength: float,
        is_higher_high: bool,
        is_higher_low: bool,
        is_lower_high: bool,
        is_lower_low: bool
    ) -> Tuple[str, float, str]:
        """
        Derive directional signal for NEUTRAL GEX regime.

        This is the key logic that replaces the hardcoded FLAT direction.
        """
        reasoning_parts = []

        if trend == TrendDirection.UPTREND:
            direction = "BULLISH"
            confidence = 0.55 + (strength * 0.20)  # 55-75%
            reasoning_parts.append(f"UPTREND (strength: {strength:.1%})")

            if is_higher_high:
                confidence += 0.05
                reasoning_parts.append("making higher highs")
            if is_higher_low:
                confidence += 0.05
                reasoning_parts.append("higher lows confirm trend")

        elif trend == TrendDirection.DOWNTREND:
            direction = "BEARISH"
            confidence = 0.55 + (strength * 0.20)
            reasoning_parts.append(f"DOWNTREND (strength: {strength:.1%})")

            if is_lower_low:
                confidence += 0.05
                reasoning_parts.append("making lower lows")
            if is_lower_high:
                confidence += 0.05
                reasoning_parts.append("lower highs confirm trend")

        else:  # SIDEWAYS
            direction = "FLAT"
            confidence = 0.50  # Neutral, but NOT 0.45!
            reasoning_parts.append("SIDEWAYS - use wall proximity for direction")

        confidence = min(0.85, confidence)  # Cap at 85%
        reasoning = " | ".join(reasoning_parts)

        return direction, confidence, reasoning

    def analyze_wall_position(
        self,
        symbol: str,
        spot_price: float,
        call_wall: float,
        put_wall: float,
        trend: Optional[TrendAnalysis] = None
    ) -> WallPositionAnalysis:
        """
        Analyze price position relative to GEX walls.

        Returns detailed analysis of where price sits in the wall range
        and whether it's at risk of breaching a wall.
        """
        # Handle edge cases
        if call_wall <= 0 or put_wall <= 0 or call_wall <= put_wall:
            return WallPositionAnalysis(
                call_wall=call_wall,
                put_wall=put_wall,
                dist_to_call_wall_pct=0,
                dist_to_put_wall_pct=0,
                position_in_range_pct=50,
                wall_range_width_pct=0,
                is_contained=True,
                nearest_wall="UNKNOWN",
                nearest_wall_distance_pct=0,
                wall_breach_risk="LOW"
            )

        # Calculate distances (as percentages of spot price)
        dist_to_call_wall_pct = (call_wall - spot_price) / spot_price * 100
        dist_to_put_wall_pct = (spot_price - put_wall) / spot_price * 100

        # Position in range (0% = at put wall, 100% = at call wall)
        wall_range = call_wall - put_wall
        position_in_range_pct = (spot_price - put_wall) / wall_range * 100 if wall_range > 0 else 50

        # Wall range width
        wall_range_width_pct = wall_range / spot_price * 100

        # Containment check
        is_contained = put_wall <= spot_price <= call_wall

        # Nearest wall
        if abs(dist_to_call_wall_pct) < abs(dist_to_put_wall_pct):
            nearest_wall = "CALL_WALL"
            nearest_wall_distance_pct = abs(dist_to_call_wall_pct)
        else:
            nearest_wall = "PUT_WALL"
            nearest_wall_distance_pct = abs(dist_to_put_wall_pct)

        # Breach risk based on trend toward wall
        wall_breach_risk = "LOW"
        if trend:
            if trend.direction == TrendDirection.UPTREND and position_in_range_pct > 80:
                wall_breach_risk = "HIGH"
            elif trend.direction == TrendDirection.DOWNTREND and position_in_range_pct < 20:
                wall_breach_risk = "HIGH"
            elif trend.direction == TrendDirection.UPTREND and position_in_range_pct > 60:
                wall_breach_risk = "MEDIUM"
            elif trend.direction == TrendDirection.DOWNTREND and position_in_range_pct < 40:
                wall_breach_risk = "MEDIUM"

        return WallPositionAnalysis(
            call_wall=call_wall,
            put_wall=put_wall,
            dist_to_call_wall_pct=dist_to_call_wall_pct,
            dist_to_put_wall_pct=dist_to_put_wall_pct,
            position_in_range_pct=position_in_range_pct,
            wall_range_width_pct=wall_range_width_pct,
            is_contained=is_contained,
            nearest_wall=nearest_wall,
            nearest_wall_distance_pct=nearest_wall_distance_pct,
            wall_breach_risk=wall_breach_risk
        )

    def calculate_strategy_suitability(
        self,
        trend: TrendAnalysis,
        wall_position: WallPositionAnalysis,
        vix: float,
        gex_regime: str
    ) -> StrategySuitability:
        """
        Calculate strategy suitability scores based on all market conditions.

        This replaces the broken logic that always fails for NEUTRAL regime.
        """
        ic_score = 0.50  # Start neutral
        bullish_score = 0.50
        bearish_score = 0.50

        ic_reasoning = []
        dir_reasoning = []

        # =====================================================================
        # IRON CONDOR SUITABILITY
        # =====================================================================

        # NEUTRAL GEX is actually GOOD for IC (walls likely to hold)
        if gex_regime == "NEUTRAL":
            ic_score += 0.15
            ic_reasoning.append("+15% NEUTRAL GEX (balanced, walls holding)")
        elif gex_regime == "POSITIVE":
            ic_score += 0.20
            ic_reasoning.append("+20% POSITIVE GEX (mean reversion)")
        else:  # NEGATIVE
            ic_score -= 0.20
            ic_reasoning.append("-20% NEGATIVE GEX (trending, walls may break)")

        # Contained within walls = IC paradise
        if wall_position.is_contained:
            ic_score += 0.15
            ic_reasoning.append("+15% contained within walls")
        else:
            ic_score -= 0.25
            ic_reasoning.append("-25% outside wall range")

        # Sideways trend = perfect for IC
        if trend.direction == TrendDirection.SIDEWAYS:
            ic_score += 0.10
            ic_reasoning.append("+10% sideways trend (range-bound)")
        elif trend.strength > 0.6:
            ic_score -= 0.15
            ic_reasoning.append(f"-15% strong trend ({trend.strength:.0%} strength)")

        # Wide wall range = safer IC
        if wall_position.wall_range_width_pct > 1.5:
            ic_score += 0.05
            ic_reasoning.append(f"+5% wide range ({wall_position.wall_range_width_pct:.1f}%)")

        # VIX impact
        if 15 <= vix <= 22:
            ic_score += 0.10
            ic_reasoning.append(f"+10% VIX {vix:.1f} (ideal range)")
        elif vix > 30:
            ic_score -= 0.15
            ic_reasoning.append(f"-15% VIX {vix:.1f} (high volatility)")

        # Wall breach risk
        if wall_position.wall_breach_risk == "HIGH":
            ic_score -= 0.20
            ic_reasoning.append("-20% HIGH breach risk")
        elif wall_position.wall_breach_risk == "MEDIUM":
            ic_score -= 0.10
            ic_reasoning.append("-10% MEDIUM breach risk")

        # =====================================================================
        # DIRECTIONAL SUITABILITY (BULLISH)
        # =====================================================================

        if trend.derived_direction == "BULLISH":
            bullish_score += 0.20
            dir_reasoning.append("+20% bullish trend")
        elif trend.derived_direction == "BEARISH":
            bullish_score -= 0.15
            dir_reasoning.append("-15% bearish trend (fighting direction)")

        # Room to run up
        if wall_position.position_in_range_pct < 50:
            room_bonus = (50 - wall_position.position_in_range_pct) / 100
            bullish_score += room_bonus * 0.20
            dir_reasoning.append(f"+{room_bonus * 20:.0f}% room to call wall")
        elif wall_position.position_in_range_pct > 80:
            bullish_score -= 0.15
            dir_reasoning.append("-15% too close to call wall resistance")

        # Higher highs = bullish confirmation
        if trend.is_higher_high:
            bullish_score += 0.10
            dir_reasoning.append("+10% making higher highs")

        # =====================================================================
        # DIRECTIONAL SUITABILITY (BEARISH)
        # =====================================================================

        if trend.derived_direction == "BEARISH":
            bearish_score += 0.20
        elif trend.derived_direction == "BULLISH":
            bearish_score -= 0.15

        # Room to run down
        if wall_position.position_in_range_pct > 50:
            room_bonus = (wall_position.position_in_range_pct - 50) / 100
            bearish_score += room_bonus * 0.20
        elif wall_position.position_in_range_pct < 20:
            bearish_score -= 0.15

        # Lower lows = bearish confirmation
        if trend.is_lower_low:
            bearish_score += 0.10

        # =====================================================================
        # NORMALIZE AND DETERMINE RECOMMENDATION
        # =====================================================================

        ic_score = max(0.0, min(1.0, ic_score))
        bullish_score = max(0.0, min(1.0, bullish_score))
        bearish_score = max(0.0, min(1.0, bearish_score))

        # Determine recommended strategy
        max_directional = max(bullish_score, bearish_score)

        if ic_score >= 0.65 and ic_score > max_directional:
            recommended = "IRON_CONDOR"
        elif bullish_score >= 0.55 and bullish_score > bearish_score and bullish_score > ic_score:
            recommended = "BULL_SPREAD"
        elif bearish_score >= 0.55 and bearish_score > bullish_score and bearish_score > ic_score:
            recommended = "BEAR_SPREAD"
        elif ic_score >= 0.50:
            recommended = "IRON_CONDOR"
        elif max_directional >= 0.50:
            recommended = "BULL_SPREAD" if bullish_score > bearish_score else "BEAR_SPREAD"
        else:
            recommended = "SKIP"

        return StrategySuitability(
            ic_suitability=ic_score,
            ic_reasoning=ic_reasoning,
            bullish_suitability=bullish_score,
            bearish_suitability=bearish_score,
            directional_reasoning=dir_reasoning,
            recommended_strategy=recommended
        )

    def get_neutral_regime_direction(
        self,
        symbol: str,
        spot_price: float,
        call_wall: float,
        put_wall: float,
        wall_filter_pct: float = 3.0
    ) -> Tuple[str, float, str, bool]:
        """
        Main method for NEUTRAL GEX regime direction determination.

        This replaces the broken logic that returns FLAT for NEUTRAL.

        Returns:
            Tuple of (direction, confidence, reasoning, wall_filter_passed)
        """
        # Get trend analysis
        trend = self.analyze_trend(symbol)

        # Get wall position analysis
        wall_position = self.analyze_wall_position(
            symbol, spot_price, call_wall, put_wall, trend
        )

        reasoning_parts = []
        direction = "FLAT"
        confidence = 0.50
        wall_filter_passed = False

        # =====================================================================
        # STEP 1: Use trend for primary direction signal
        # =====================================================================
        if trend and trend.derived_direction != "FLAT":
            direction = trend.derived_direction
            confidence = trend.derived_confidence
            reasoning_parts.append(f"Trend: {trend.reasoning}")

        # =====================================================================
        # STEP 2: If trend is FLAT/SIDEWAYS, use wall proximity
        # =====================================================================
        if direction == "FLAT" or (trend and trend.direction == TrendDirection.SIDEWAYS):
            # Use wall proximity to determine direction
            if wall_position.position_in_range_pct < 35:
                # Lower third of range = near put wall = expect bounce
                direction = "BULLISH"
                confidence = 0.60
                reasoning_parts.append(f"Near put wall support ({wall_position.position_in_range_pct:.0f}% of range)")
            elif wall_position.position_in_range_pct > 65:
                # Upper third of range = near call wall = expect pullback
                direction = "BEARISH"
                confidence = 0.60
                reasoning_parts.append(f"Near call wall resistance ({wall_position.position_in_range_pct:.0f}% of range)")
            else:
                # Middle of range - still determine direction from nearest wall
                if wall_position.nearest_wall == "PUT_WALL":
                    direction = "BULLISH"
                    confidence = 0.55
                    reasoning_parts.append(f"Mid-range, closer to put wall ({wall_position.nearest_wall_distance_pct:.1f}%)")
                else:
                    direction = "BEARISH"
                    confidence = 0.55
                    reasoning_parts.append(f"Mid-range, closer to call wall ({wall_position.nearest_wall_distance_pct:.1f}%)")

        # =====================================================================
        # STEP 3: Adjust for wall proximity (reduces confidence near opposite wall)
        # =====================================================================
        if direction == "BULLISH" and wall_position.position_in_range_pct > 80:
            confidence -= 0.10
            reasoning_parts.append("Caution: approaching call wall resistance")
        elif direction == "BEARISH" and wall_position.position_in_range_pct < 20:
            confidence -= 0.10
            reasoning_parts.append("Caution: approaching put wall support")

        # =====================================================================
        # STEP 4: Wall filter check (now properly decoupled from direction)
        # =====================================================================
        if direction == "BULLISH":
            if wall_position.dist_to_put_wall_pct <= wall_filter_pct:
                wall_filter_passed = True
                reasoning_parts.append(f"Wall filter PASSED: {wall_position.dist_to_put_wall_pct:.2f}% from put wall (threshold: {wall_filter_pct}%)")
            else:
                reasoning_parts.append(f"Wall filter: {wall_position.dist_to_put_wall_pct:.2f}% from put wall (threshold: {wall_filter_pct}%)")
        elif direction == "BEARISH":
            if wall_position.dist_to_call_wall_pct <= wall_filter_pct:
                wall_filter_passed = True
                reasoning_parts.append(f"Wall filter PASSED: {wall_position.dist_to_call_wall_pct:.2f}% from call wall (threshold: {wall_filter_pct}%)")
            else:
                reasoning_parts.append(f"Wall filter: {wall_position.dist_to_call_wall_pct:.2f}% from call wall (threshold: {wall_filter_pct}%)")

        # =====================================================================
        # STEP 5: Boost confidence if wall filter passed
        # =====================================================================
        if wall_filter_passed:
            confidence = min(0.85, confidence + 0.10)

        reasoning = " | ".join(reasoning_parts)

        logger.info(f"[NEUTRAL Regime] {symbol}: {direction} ({confidence:.0%}) - {reasoning}")

        return direction, confidence, reasoning, wall_filter_passed

    def clear_history(self, symbol: str = None) -> None:
        """Clear price history (for testing or end of day)"""
        if symbol:
            if symbol in self._price_history:
                self._price_history[symbol].clear()
                logger.info(f"[TrendTracker] Cleared history for {symbol}")
        else:
            self._price_history.clear()
            self._daily_high.clear()
            self._daily_low.clear()
            logger.info("[TrendTracker] Cleared all history")


# Singleton accessor
def get_trend_tracker() -> PriceTrendTracker:
    """Get the singleton PriceTrendTracker instance"""
    return PriceTrendTracker.get_instance()
