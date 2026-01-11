"""
Pin Risk Analyzer - Comprehensive Options Pinning Analysis

Analyzes gamma exposure, max pain, and dealer positioning to assess
the risk of price pinning for options traders.

Key Features:
- Dynamic support for any optionable symbol
- GEX-based gamma regime detection
- Max pain gravitational analysis
- Dealer hedging behavior assessment
- Pin probability scoring
- Trading implications and recommendations
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================

class GammaRegime(Enum):
    """Gamma regime based on price relative to flip point"""
    POSITIVE = "positive"      # Price above flip - dealers long gamma, dampen moves
    NEGATIVE = "negative"      # Price below flip - dealers short gamma, amplify moves
    NEUTRAL = "neutral"        # At or very near flip point
    UNKNOWN = "unknown"


class PinRiskLevel(Enum):
    """Overall pin risk assessment"""
    HIGH = "high"              # Score 60-100: Strong pinning expected
    MODERATE = "moderate"      # Score 40-59: Significant pin gravity
    LOW_MODERATE = "low_moderate"  # Score 20-39: Some pin risk
    LOW = "low"                # Score 0-19: Minimal pinning expected


@dataclass
class GammaLevels:
    """Key gamma-derived price levels"""
    flip_point: float = 0.0      # Zero gamma crossing
    call_wall: float = 0.0       # Highest call gamma strike (resistance)
    put_wall: float = 0.0        # Highest put gamma strike (support)
    max_pain: float = 0.0        # Strike with max OI / pain minimization
    net_gex: float = 0.0         # Net gamma exposure in billions
    call_gex: float = 0.0        # Call-side gamma
    put_gex: float = 0.0         # Put-side gamma

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PinFactor:
    """Individual factor contributing to pin risk"""
    name: str
    score: int                    # Points contributing to total score
    description: str              # Human-readable explanation
    is_bullish: Optional[bool] = None  # True=bullish, False=bearish, None=neutral

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TradingImplication:
    """Specific trading implication for a position type"""
    position_type: str            # e.g., "long_calls", "long_puts", "iron_condor"
    outlook: str                  # "favorable", "unfavorable", "neutral"
    reasoning: str
    recommendation: str

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PinRiskAnalysis:
    """Complete pin risk analysis result"""
    symbol: str
    timestamp: datetime

    # Current market state
    spot_price: float = 0.0
    friday_range_pct: float = 0.0      # Previous Friday's trading range

    # Gamma levels
    gamma_levels: GammaLevels = field(default_factory=GammaLevels)

    # Gamma regime
    gamma_regime: GammaRegime = GammaRegime.UNKNOWN
    gamma_regime_description: str = ""

    # Distance metrics
    distance_to_max_pain_pct: float = 0.0
    distance_to_flip_pct: float = 0.0
    distance_to_call_wall_pct: float = 0.0
    distance_to_put_wall_pct: float = 0.0

    # Pin scoring
    pin_risk_score: int = 0            # 0-100 score
    pin_risk_level: PinRiskLevel = PinRiskLevel.LOW
    pin_factors: List[PinFactor] = field(default_factory=list)

    # Expected range
    expected_range_low: float = 0.0
    expected_range_high: float = 0.0
    expected_range_pct: float = 0.0

    # Days to expiration context
    days_to_weekly_expiry: int = 0
    is_expiration_day: bool = False

    # Trading implications
    trading_implications: List[TradingImplication] = field(default_factory=list)

    # What would break the pin
    pin_breakers: List[str] = field(default_factory=list)

    # Overall assessment
    summary: str = ""
    long_call_outlook: str = ""        # "dangerous", "challenging", "favorable"

    # Data quality
    data_sources: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'spot_price': self.spot_price,
            'friday_range_pct': self.friday_range_pct,
            'gamma_levels': self.gamma_levels.to_dict(),
            'gamma_regime': self.gamma_regime.value,
            'gamma_regime_description': self.gamma_regime_description,
            'distance_to_max_pain_pct': self.distance_to_max_pain_pct,
            'distance_to_flip_pct': self.distance_to_flip_pct,
            'distance_to_call_wall_pct': self.distance_to_call_wall_pct,
            'distance_to_put_wall_pct': self.distance_to_put_wall_pct,
            'pin_risk_score': self.pin_risk_score,
            'pin_risk_level': self.pin_risk_level.value,
            'pin_factors': [f.to_dict() for f in self.pin_factors],
            'expected_range_low': self.expected_range_low,
            'expected_range_high': self.expected_range_high,
            'expected_range_pct': self.expected_range_pct,
            'days_to_weekly_expiry': self.days_to_weekly_expiry,
            'is_expiration_day': self.is_expiration_day,
            'trading_implications': [t.to_dict() for t in self.trading_implications],
            'pin_breakers': self.pin_breakers,
            'summary': self.summary,
            'long_call_outlook': self.long_call_outlook,
            'data_sources': self.data_sources,
            'warnings': self.warnings
        }


# ============================================================================
# PIN RISK ANALYZER ENGINE
# ============================================================================

class PinRiskAnalyzer:
    """
    Comprehensive Pin Risk Analysis Engine

    Analyzes options data to determine the probability of price pinning
    and provides actionable insights for options traders.
    """

    def __init__(self):
        self.gex_calculator = None
        self.tradier = None
        self.tv_api = None

        self._init_data_providers()

    def _init_data_providers(self):
        """Initialize data provider connections"""
        # Try TradingVolatility API first (primary GEX source)
        try:
            from core_classes_and_engines import TradingVolatilityAPI
            self.tv_api = TradingVolatilityAPI()
            logger.info("✅ TradingVolatility API initialized for pin risk")
        except Exception as e:
            logger.warning(f"⚠️  TradingVolatility API not available: {e}")

        # Try Tradier GEX calculator (fallback)
        try:
            from data.gex_calculator import TradierGEXCalculator
            self.gex_calculator = TradierGEXCalculator(sandbox=False)
            logger.info("✅ Tradier GEX Calculator initialized for pin risk")
        except Exception as e:
            logger.warning(f"⚠️  Tradier GEX Calculator not available: {e}")

        # Try Tradier for quotes
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            self.tradier = TradierDataFetcher()
            logger.info("✅ Tradier Data Fetcher initialized for pin risk")
        except Exception as e:
            logger.warning(f"⚠️  Tradier Data Fetcher not available: {e}")

    def analyze(self, symbol: str) -> PinRiskAnalysis:
        """
        Perform comprehensive pin risk analysis for a symbol.

        Args:
            symbol: Stock ticker symbol (e.g., 'NVDA', 'SPY', 'AAPL')

        Returns:
            PinRiskAnalysis with complete pin risk assessment
        """
        symbol = symbol.upper()
        now = datetime.now(CENTRAL_TZ)

        analysis = PinRiskAnalysis(
            symbol=symbol,
            timestamp=now
        )

        # Step 1: Get GEX data
        gex_data = self._get_gex_data(symbol)
        if not gex_data:
            analysis.warnings.append("Unable to fetch GEX data - analysis limited")
            return analysis

        # Step 2: Populate gamma levels
        analysis.gamma_levels = GammaLevels(
            flip_point=gex_data.get('flip_point', gex_data.get('gamma_flip', 0)),
            call_wall=gex_data.get('call_wall', 0),
            put_wall=gex_data.get('put_wall', 0),
            max_pain=gex_data.get('max_pain', 0),
            net_gex=gex_data.get('net_gex', 0),
            call_gex=gex_data.get('call_gex', 0),
            put_gex=gex_data.get('put_gex', 0)
        )

        analysis.spot_price = gex_data.get('spot_price', 0)
        analysis.data_sources.append(gex_data.get('data_source', 'unknown'))

        # Step 3: Determine gamma regime
        analysis.gamma_regime, analysis.gamma_regime_description = self._determine_gamma_regime(
            analysis.spot_price,
            analysis.gamma_levels.flip_point,
            analysis.gamma_levels.net_gex
        )

        # Step 4: Calculate distance metrics
        self._calculate_distances(analysis)

        # Step 5: Calculate days to expiry
        self._calculate_expiry_timing(analysis, now)

        # Step 6: Calculate pin risk score
        self._calculate_pin_risk_score(analysis)

        # Step 7: Calculate expected range
        self._calculate_expected_range(analysis)

        # Step 8: Generate trading implications
        self._generate_trading_implications(analysis)

        # Step 9: Identify pin breakers
        self._identify_pin_breakers(analysis)

        # Step 10: Generate summary
        self._generate_summary(analysis)

        return analysis

    def _get_gex_data(self, symbol: str) -> Optional[Dict]:
        """Fetch GEX data from available sources"""

        # Try TradingVolatility API first (best for SPY/SPX)
        if self.tv_api:
            try:
                gex_data = self.tv_api.get_net_gamma(symbol)
                if gex_data and 'error' not in gex_data:
                    gex_data['data_source'] = 'trading_volatility'
                    return gex_data
            except Exception as e:
                logger.warning(f"TradingVolatility API failed for {symbol}: {e}")

        # Try Tradier GEX calculator
        if self.gex_calculator:
            try:
                gex_data = self.gex_calculator.get_gex(symbol)
                if gex_data and 'error' not in gex_data:
                    gex_data['data_source'] = 'tradier_calculated'
                    return gex_data
            except Exception as e:
                logger.warning(f"Tradier GEX Calculator failed for {symbol}: {e}")

        return None

    def _determine_gamma_regime(
        self,
        spot: float,
        flip_point: float,
        net_gex: float
    ) -> Tuple[GammaRegime, str]:
        """Determine gamma regime and its implications"""

        if not flip_point or not spot:
            return GammaRegime.UNKNOWN, "Unable to determine gamma regime"

        pct_from_flip = ((spot - flip_point) / spot) * 100 if spot > 0 else 0

        if abs(pct_from_flip) < 0.5:
            regime = GammaRegime.NEUTRAL
            description = (
                f"Price at gamma flip point (${flip_point:.2f}). "
                "This is an unstable equilibrium - expect increased volatility "
                "as dealers transition between hedging regimes."
            )
        elif spot > flip_point:
            regime = GammaRegime.POSITIVE
            description = (
                f"POSITIVE GAMMA: Price ${spot:.2f} is {pct_from_flip:.1f}% above "
                f"flip point ${flip_point:.2f}. Dealers are LONG gamma - they BUY dips "
                "and SELL rallies, DAMPENING price moves. This creates a range-bound, "
                "mean-reverting environment favorable for premium sellers."
            )
        else:
            regime = GammaRegime.NEGATIVE
            description = (
                f"NEGATIVE GAMMA: Price ${spot:.2f} is {abs(pct_from_flip):.1f}% below "
                f"flip point ${flip_point:.2f}. Dealers are SHORT gamma - they SELL dips "
                "and BUY rallies, AMPLIFYING price moves. This creates trending, "
                "momentum-driven environment favorable for directional trades."
            )

        return regime, description

    def _calculate_distances(self, analysis: PinRiskAnalysis):
        """Calculate percentage distances to key levels"""
        spot = analysis.spot_price
        if spot <= 0:
            return

        gl = analysis.gamma_levels

        if gl.max_pain > 0:
            analysis.distance_to_max_pain_pct = ((spot - gl.max_pain) / spot) * 100

        if gl.flip_point > 0:
            analysis.distance_to_flip_pct = ((spot - gl.flip_point) / spot) * 100

        if gl.call_wall > 0:
            analysis.distance_to_call_wall_pct = ((gl.call_wall - spot) / spot) * 100

        if gl.put_wall > 0:
            analysis.distance_to_put_wall_pct = ((spot - gl.put_wall) / spot) * 100

    def _calculate_expiry_timing(self, analysis: PinRiskAnalysis, now: datetime):
        """Calculate days to weekly options expiration"""
        weekday = now.weekday()  # 0=Monday, 4=Friday

        if weekday <= 4:  # Monday-Friday
            days_to_friday = 4 - weekday
        else:  # Saturday/Sunday
            days_to_friday = (4 - weekday) + 7

        analysis.days_to_weekly_expiry = days_to_friday
        analysis.is_expiration_day = (days_to_friday == 0)

    def _calculate_pin_risk_score(self, analysis: PinRiskAnalysis):
        """
        Calculate pin risk score (0-100) based on multiple factors.

        Higher score = higher probability of pinning
        """
        score = 0
        factors = []

        # Factor 1: Distance to max pain (0-30 points)
        if analysis.gamma_levels.max_pain > 0:
            pct_from_max_pain = abs(analysis.distance_to_max_pain_pct)
            if pct_from_max_pain < 1.0:
                points = 30
                desc = f"VERY CLOSE to max pain ({pct_from_max_pain:.2f}%) - strong gravitational pull"
            elif pct_from_max_pain < 2.0:
                points = 20
                desc = f"Close to max pain ({pct_from_max_pain:.2f}%) - significant gravitational pull"
            elif pct_from_max_pain < 3.0:
                points = 10
                desc = f"Near max pain ({pct_from_max_pain:.2f}%) - some gravitational pull"
            else:
                points = 0
                desc = f"Away from max pain ({pct_from_max_pain:.2f}%) - minimal gravitational pull"

            score += points
            factors.append(PinFactor(
                name="max_pain_proximity",
                score=points,
                description=desc
            ))

        # Factor 2: Gamma regime (0-25 points)
        net_gex = analysis.gamma_levels.net_gex
        if analysis.gamma_regime == GammaRegime.POSITIVE or net_gex > 0:
            points = 25
            desc = f"Positive GEX ({net_gex:.4f}B) - dealers dampen moves, high pin probability"
            factors.append(PinFactor(
                name="gamma_regime",
                score=points,
                description=desc,
                is_bullish=False  # Bad for directional longs
            ))
            score += points
        elif analysis.gamma_regime == GammaRegime.NEGATIVE or net_gex < 0:
            points = -10  # Reduces pin risk
            desc = f"Negative GEX ({net_gex:.4f}B) - dealers amplify moves, lower pin probability"
            factors.append(PinFactor(
                name="gamma_regime",
                score=max(0, points),  # Don't show negative
                description=desc,
                is_bullish=True  # Good for directional longs
            ))
            score = max(0, score + points)

        # Factor 3: Price between walls (0-15 points)
        gl = analysis.gamma_levels
        spot = analysis.spot_price
        if gl.put_wall > 0 and gl.call_wall > 0 and spot > 0:
            if gl.put_wall < spot < gl.call_wall:
                wall_range = gl.call_wall - gl.put_wall
                wall_range_pct = (wall_range / spot) * 100
                points = 15
                desc = f"Price BETWEEN walls (${gl.put_wall:.0f}-${gl.call_wall:.0f}, {wall_range_pct:.1f}% range) - contained environment"
            elif spot >= gl.call_wall:
                points = 10
                desc = f"Price AT or ABOVE call wall ${gl.call_wall:.0f} - resistance overhead"
            else:
                points = 10
                desc = f"Price AT or BELOW put wall ${gl.put_wall:.0f} - support below"

            score += points
            factors.append(PinFactor(
                name="wall_positioning",
                score=points,
                description=desc
            ))

        # Factor 4: Expiration timing (0-30 points)
        if analysis.is_expiration_day:
            points = 30
            desc = "TODAY is expiration day - HIGHEST pin risk, gamma at maximum"
        elif analysis.days_to_weekly_expiry == 1:
            points = 20
            desc = "Tomorrow is expiration - HIGH pin gravity, gamma accelerating"
        elif analysis.days_to_weekly_expiry <= 2:
            points = 10
            desc = f"{analysis.days_to_weekly_expiry} days to weekly expiry - increasing pin gravity"
        else:
            points = 0
            desc = f"{analysis.days_to_weekly_expiry} days to expiry - lower time-based pin pressure"

        score += points
        factors.append(PinFactor(
            name="expiration_timing",
            score=points,
            description=desc
        ))

        # Factor 5: Tight trading range indicator (inferred from GEX)
        if analysis.gamma_regime == GammaRegime.POSITIVE and net_gex > 0.5:
            points = 10
            desc = "Strong positive gamma suggests tight recent ranges"
            score += points
            factors.append(PinFactor(
                name="range_compression",
                score=points,
                description=desc
            ))

        # Cap at 100
        analysis.pin_risk_score = min(100, max(0, score))
        analysis.pin_factors = factors

        # Determine risk level
        if analysis.pin_risk_score >= 60:
            analysis.pin_risk_level = PinRiskLevel.HIGH
        elif analysis.pin_risk_score >= 40:
            analysis.pin_risk_level = PinRiskLevel.MODERATE
        elif analysis.pin_risk_score >= 20:
            analysis.pin_risk_level = PinRiskLevel.LOW_MODERATE
        else:
            analysis.pin_risk_level = PinRiskLevel.LOW

    def _calculate_expected_range(self, analysis: PinRiskAnalysis):
        """Estimate expected price range based on gamma positioning"""
        spot = analysis.spot_price
        gl = analysis.gamma_levels

        if spot <= 0:
            return

        # Use walls as bounds if available
        if gl.put_wall > 0 and gl.call_wall > 0:
            analysis.expected_range_low = gl.put_wall
            analysis.expected_range_high = gl.call_wall
        else:
            # Estimate based on gamma regime
            if analysis.gamma_regime == GammaRegime.POSITIVE:
                # Compressed range
                pct_range = 2.0
            elif analysis.gamma_regime == GammaRegime.NEGATIVE:
                # Expanded range
                pct_range = 5.0
            else:
                # Normal range
                pct_range = 3.0

            analysis.expected_range_low = spot * (1 - pct_range / 100)
            analysis.expected_range_high = spot * (1 + pct_range / 100)

        analysis.expected_range_pct = (
            (analysis.expected_range_high - analysis.expected_range_low) / spot * 100
        )

    def _generate_trading_implications(self, analysis: PinRiskAnalysis):
        """Generate specific trading implications for different position types"""
        implications = []

        risk_level = analysis.pin_risk_level
        gamma_regime = analysis.gamma_regime
        gl = analysis.gamma_levels
        spot = analysis.spot_price

        # Long Calls
        if risk_level in [PinRiskLevel.HIGH, PinRiskLevel.MODERATE]:
            implications.append(TradingImplication(
                position_type="long_calls",
                outlook="unfavorable",
                reasoning=(
                    f"Pin risk score {analysis.pin_risk_score}/100 indicates strong gravitational pull. "
                    f"{'Positive gamma means dealers sell rallies, creating resistance.' if gamma_regime == GammaRegime.POSITIVE else ''} "
                    f"Upside to call wall: {analysis.distance_to_call_wall_pct:.1f}% (${gl.call_wall:.0f})."
                ),
                recommendation=(
                    "Consider: 1) Rolling to further expiration to outlast the pin, "
                    "2) Converting to spreads to reduce theta exposure, "
                    "3) Wait for negative gamma environment or catalyst."
                )
            ))
            analysis.long_call_outlook = "dangerous" if risk_level == PinRiskLevel.HIGH else "challenging"
        else:
            implications.append(TradingImplication(
                position_type="long_calls",
                outlook="favorable" if gamma_regime == GammaRegime.NEGATIVE else "neutral",
                reasoning=(
                    f"Pin risk score {analysis.pin_risk_score}/100 suggests lower pinning pressure. "
                    f"{'Negative gamma means dealers amplify moves, supporting trends.' if gamma_regime == GammaRegime.NEGATIVE else ''}"
                ),
                recommendation=(
                    "Directional moves more likely. "
                    "Still watch call wall resistance at ${:.0f}.".format(gl.call_wall) if gl.call_wall > 0 else ""
                )
            ))
            analysis.long_call_outlook = "favorable" if gamma_regime == GammaRegime.NEGATIVE else "neutral"

        # Long Puts
        if risk_level in [PinRiskLevel.HIGH, PinRiskLevel.MODERATE]:
            implications.append(TradingImplication(
                position_type="long_puts",
                outlook="unfavorable",
                reasoning=(
                    f"Same pinning dynamics affect puts. "
                    f"{'Positive gamma means dealers buy dips, creating support.' if gamma_regime == GammaRegime.POSITIVE else ''} "
                    f"Downside to put wall: {analysis.distance_to_put_wall_pct:.1f}% (${gl.put_wall:.0f})."
                ),
                recommendation="Similar to calls - roll out, convert to spreads, or wait for catalyst."
            ))

        # Iron Condors / Premium Selling
        if risk_level in [PinRiskLevel.HIGH, PinRiskLevel.MODERATE]:
            implications.append(TradingImplication(
                position_type="iron_condor",
                outlook="favorable",
                reasoning=(
                    f"High pin risk score ({analysis.pin_risk_score}) favors range-bound strategies. "
                    f"Expected range: ${analysis.expected_range_low:.0f}-${analysis.expected_range_high:.0f} "
                    f"({analysis.expected_range_pct:.1f}%)."
                ),
                recommendation=(
                    f"Consider short strikes outside put wall ${gl.put_wall:.0f} "
                    f"and call wall ${gl.call_wall:.0f}."
                )
            ))
        else:
            implications.append(TradingImplication(
                position_type="iron_condor",
                outlook="unfavorable" if gamma_regime == GammaRegime.NEGATIVE else "neutral",
                reasoning=(
                    f"Lower pin risk ({analysis.pin_risk_score}) and "
                    f"{'negative gamma amplifies moves' if gamma_regime == GammaRegime.NEGATIVE else 'neutral positioning'} "
                    "increases risk of breaching short strikes."
                ),
                recommendation="Widen strikes or reduce position size if selling premium."
            ))

        # Straddles/Strangles (Long Vol)
        if gamma_regime == GammaRegime.NEGATIVE or risk_level == PinRiskLevel.LOW:
            implications.append(TradingImplication(
                position_type="long_straddle",
                outlook="favorable",
                reasoning=(
                    f"{'Negative gamma environment amplifies moves.' if gamma_regime == GammaRegime.NEGATIVE else 'Low pin risk.'} "
                    "Breakout potential higher."
                ),
                recommendation="Long volatility strategies may outperform."
            ))
        else:
            implications.append(TradingImplication(
                position_type="long_straddle",
                outlook="unfavorable",
                reasoning=(
                    f"High pin risk ({analysis.pin_risk_score}) and positive gamma "
                    "compress moves, hurting long vol positions."
                ),
                recommendation="Avoid long straddles/strangles in pinning environment."
            ))

        analysis.trading_implications = implications

    def _identify_pin_breakers(self, analysis: PinRiskAnalysis):
        """Identify what would break the pinning pattern"""
        breakers = []
        gl = analysis.gamma_levels
        spot = analysis.spot_price

        # Break above call wall
        if gl.call_wall > 0:
            breakers.append(
                f"Break above call wall at ${gl.call_wall:.2f} with volume "
                f"(+{analysis.distance_to_call_wall_pct:.1f}% from current)"
            )

        # Break below flip point
        if gl.flip_point > 0 and analysis.gamma_regime == GammaRegime.POSITIVE:
            breakers.append(
                f"Drop below gamma flip at ${gl.flip_point:.2f} would flip dealers short gamma, "
                "amplifying subsequent moves"
            )

        # Catalyst events
        breakers.append(
            "Significant news catalyst (earnings, product announcement, macro data)"
        )

        # Broader market momentum
        breakers.append(
            "Strong broader market momentum (SPY/QQQ breaking key levels)"
        )

        # Options expiration
        if not analysis.is_expiration_day:
            breakers.append(
                f"Wait for weekly expiration ({analysis.days_to_weekly_expiry} days) - "
                "gamma decay reduces pin gravity"
            )

        # Volume surge
        breakers.append(
            "Unusual volume surge (2x+ average) indicating institutional flow"
        )

        analysis.pin_breakers = breakers

    def _generate_summary(self, analysis: PinRiskAnalysis):
        """Generate human-readable summary"""
        risk_level = analysis.pin_risk_level.value.upper().replace('_', ' ')

        if analysis.pin_risk_level == PinRiskLevel.HIGH:
            summary = (
                f"{analysis.symbol} shows HIGH pin risk (score: {analysis.pin_risk_score}/100). "
                f"Price ${analysis.spot_price:.2f} is in a {analysis.gamma_regime.value} gamma environment "
                f"with strong gravitational pull toward max pain ${analysis.gamma_levels.max_pain:.2f}. "
                "Long directional options face significant headwinds. "
                "Premium selling strategies (iron condors, credit spreads) are favored."
            )
        elif analysis.pin_risk_level == PinRiskLevel.MODERATE:
            summary = (
                f"{analysis.symbol} shows MODERATE pin risk (score: {analysis.pin_risk_score}/100). "
                f"Price ${analysis.spot_price:.2f} is experiencing pin gravity but breakouts are possible "
                "with sufficient catalyst. Monitor key levels closely."
            )
        elif analysis.pin_risk_level == PinRiskLevel.LOW_MODERATE:
            summary = (
                f"{analysis.symbol} shows LOW-MODERATE pin risk (score: {analysis.pin_risk_score}/100). "
                f"Some gravitational pull exists but directional moves are achievable. "
                "Consider the gamma regime when timing entries."
            )
        else:
            summary = (
                f"{analysis.symbol} shows LOW pin risk (score: {analysis.pin_risk_score}/100). "
                f"Gamma positioning does not strongly favor pinning. "
                "Directional strategies have reasonable probability of success."
            )

        analysis.summary = summary


# ============================================================================
# SINGLETON ACCESS
# ============================================================================

_pin_risk_analyzer: Optional[PinRiskAnalyzer] = None


def get_pin_risk_analyzer() -> PinRiskAnalyzer:
    """Get singleton PinRiskAnalyzer instance"""
    global _pin_risk_analyzer
    if _pin_risk_analyzer is None:
        _pin_risk_analyzer = PinRiskAnalyzer()
    return _pin_risk_analyzer


def analyze_pin_risk(symbol: str) -> Dict:
    """
    Convenience function to analyze pin risk for a symbol.

    Args:
        symbol: Stock ticker symbol

    Returns:
        Dictionary with complete pin risk analysis
    """
    analyzer = get_pin_risk_analyzer()
    analysis = analyzer.analyze(symbol)
    return analysis.to_dict()
