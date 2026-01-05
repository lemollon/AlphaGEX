"""
ARES V2 - Signal Generation
=============================

Clean signal generation for Iron Condor trades.
Uses GEX data, Oracle ML, and expected move calculations.

Key concepts:
- SD multiplier: 1.0 = strikes OUTSIDE expected move (standard IC)
- GEX walls: Use put/call walls as additional protection
- VIX filtering: Skip high volatility days
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from zoneinfo import ZoneInfo

from .models import (
    IronCondorSignal, ARESConfig, StrategyPreset,
    STRATEGY_PRESETS, CENTRAL_TZ
)

logger = logging.getLogger(__name__)

# Optional imports with fallbacks
try:
    from quant.oracle_advisor import OracleAdvisor, OraclePrediction
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None

try:
    from quant.kronos_gex_calculator import KronosGEXCalculator
    KRONOS_AVAILABLE = True
except ImportError:
    KRONOS_AVAILABLE = False
    KronosGEXCalculator = None

try:
    from data.gex_calculator import get_gex_calculator
    TRADIER_GEX_AVAILABLE = True
except ImportError:
    TRADIER_GEX_AVAILABLE = False
    get_gex_calculator = None

try:
    from data.unified_data_provider import get_price, get_vix
    DATA_PROVIDER_AVAILABLE = True
except ImportError:
    DATA_PROVIDER_AVAILABLE = False


class SignalGenerator:
    """
    Generates Iron Condor signals using GEX data and market analysis.
    """

    def __init__(self, config: ARESConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator
        self.gex_calculator = None
        if KRONOS_AVAILABLE:
            try:
                self.gex_calculator = KronosGEXCalculator()
                logger.info("ARES SignalGenerator: Using Kronos GEX")
            except Exception as e:
                logger.warning(f"Kronos init failed: {e}")

        if not self.gex_calculator and TRADIER_GEX_AVAILABLE:
            try:
                self.gex_calculator = get_gex_calculator()
                logger.info("ARES SignalGenerator: Using Tradier GEX fallback")
            except Exception as e:
                logger.warning(f"Tradier GEX init failed: {e}")

        # Oracle Advisor
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ARES SignalGenerator: Oracle initialized")
            except Exception as e:
                logger.warning(f"Oracle init failed: {e}")

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Get current market data including price, VIX, and GEX"""
        try:
            # Get spot price
            spot = None
            if DATA_PROVIDER_AVAILABLE:
                spot = get_price(self.config.ticker)

            if not spot:
                logger.warning("Could not get spot price")
                return None

            # Get VIX
            vix = 20.0
            if DATA_PROVIDER_AVAILABLE:
                try:
                    vix = get_vix() or 20.0
                except Exception:
                    pass

            # Get GEX data
            gex_data = self._get_gex_data()

            # Calculate expected move (1 SD)
            expected_move = self._calculate_expected_move(spot, vix)

            now = datetime.now(CENTRAL_TZ)
            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0) if gex_data else 0,
                'put_wall': gex_data.get('put_wall', 0) if gex_data else 0,
                'gex_regime': gex_data.get('regime', 'NEUTRAL') if gex_data else 'NEUTRAL',
                'net_gex': gex_data.get('net_gex', 0) if gex_data else 0,
                'flip_point': gex_data.get('flip_point', 0) if gex_data else 0,
                'timestamp': now,
                'data_age_seconds': 0,  # Fresh data
            }
        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    def _get_gex_data(self) -> Optional[Dict[str, Any]]:
        """Get GEX data from calculator"""
        if not self.gex_calculator:
            return None

        try:
            gex = self.gex_calculator.calculate_gex(self.config.ticker)
            if gex:
                return {
                    'call_wall': gex.get('call_wall', gex.get('major_call_wall', 0)),
                    'put_wall': gex.get('put_wall', gex.get('major_put_wall', 0)),
                    'regime': gex.get('regime', gex.get('gex_regime', 'NEUTRAL')),
                    'net_gex': gex.get('net_gex', 0),
                    'flip_point': gex.get('flip_point', gex.get('gamma_flip', 0)),
                }
        except Exception as e:
            logger.warning(f"GEX fetch error: {e}")

        return None

    def _calculate_expected_move(self, spot: float, vix: float) -> float:
        """
        Calculate expected daily move (1 SD).

        Formula: Expected Move = Spot * (VIX / 100) / sqrt(252)
        """
        annual_factor = math.sqrt(252)  # Trading days per year
        daily_vol = (vix / 100) / annual_factor
        expected_move = spot * daily_vol
        return round(expected_move, 2)

    def check_vix_filter(self, vix: float) -> Tuple[bool, str]:
        """
        Check if VIX conditions allow trading.

        Returns (can_trade, reason).
        """
        vix_skip = self.config.vix_skip

        if vix_skip and vix > vix_skip:
            return False, f"VIX {vix:.1f} > {vix_skip} threshold"

        return True, "VIX within range"

    def adjust_confidence_from_top_factors(
        self,
        confidence: float,
        top_factors: List[Dict],
        market_data: Dict
    ) -> Tuple[float, List[str]]:
        """
        Adjust confidence based on Oracle's top contributing factors.

        The top_factors reveal which features most influenced Oracle's prediction.
        Use this insight to further calibrate confidence based on current conditions.

        Returns (adjusted_confidence, adjustment_reasons).
        """
        if not top_factors:
            return confidence, []

        adjustments = []
        original_confidence = confidence
        vix = market_data.get('vix', 20)
        gex_regime = market_data.get('gex_regime', 'NEUTRAL')

        # Extract factor names and impacts
        factor_map = {}
        for f in top_factors[:5]:  # Only consider top 5 factors
            name = f.get('factor', f.get('feature', '')).lower()
            impact = f.get('impact', f.get('importance', 0))
            factor_map[name] = impact

        # 1. VIX factor adjustment
        # If VIX is a major factor AND current VIX is elevated, adjust confidence
        vix_importance = factor_map.get('vix', factor_map.get('vix_level', 0))
        if vix_importance > 0.2:  # VIX is significant factor
            if vix > 25:
                penalty = min(0.08, (vix - 25) * 0.01)  # Up to 8% penalty
                confidence -= penalty
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX elevated ({vix:.1f}): -{penalty:.0%}")
            elif vix < 14:
                boost = min(0.05, (14 - vix) * 0.01)  # Up to 5% boost for low VIX
                confidence += boost
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX low ({vix:.1f}): +{boost:.0%}")

        # 2. GEX regime factor adjustment
        # If GEX is major factor AND regime is negative, reduce confidence for IC
        gex_importance = factor_map.get('gex_regime', factor_map.get('net_gex', 0))
        if gex_importance > 0.15:  # GEX is significant factor
            if gex_regime == 'NEGATIVE':
                penalty = 0.05
                confidence -= penalty
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + NEGATIVE regime: -{penalty:.0%}")
            elif gex_regime == 'POSITIVE':
                boost = 0.03
                confidence += boost
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + POSITIVE regime: +{boost:.0%}")

        # 3. Day of week factor (Monday/Tuesday traditionally better for ICs)
        dow_importance = factor_map.get('day_of_week', 0)
        if dow_importance > 0.15:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            day = datetime.now(ZoneInfo("America/Chicago")).weekday()
            if day in [0, 1]:  # Monday, Tuesday
                boost = 0.03
                confidence += boost
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + favorable day: +{boost:.0%}")
            elif day == 4:  # Friday
                penalty = 0.03
                confidence -= penalty
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + Friday: -{penalty:.0%}")

        # Clamp confidence to reasonable range
        confidence = max(0.4, min(0.95, confidence))

        if adjustments:
            logger.info(f"[TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
            for adj in adjustments:
                logger.info(f"  - {adj}")

        return confidence, adjustments

    def calculate_strikes(
        self,
        spot_price: float,
        expected_move: float,
        call_wall: float = 0,
        put_wall: float = 0,
        oracle_put_strike: Optional[float] = None,
        oracle_call_strike: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Calculate Iron Condor strikes.

        Priority:
        1. Oracle suggested strikes (if provided and valid)
        2. GEX walls (if available)
        3. SD-based strikes (fallback)
        """
        sd = self.config.sd_multiplier
        width = self.config.spread_width

        # Round to $1 for SPY
        def round_strike(x):
            return round(x)

        # Determine short strikes with Oracle priority
        use_oracle = False
        use_gex = False

        # Priority 1: Oracle suggested strikes (must be reasonable distance from spot)
        if oracle_put_strike and oracle_call_strike:
            # Validate Oracle strikes are reasonable (between 0.5% and 5% from spot)
            put_dist = (spot_price - oracle_put_strike) / spot_price
            call_dist = (oracle_call_strike - spot_price) / spot_price
            if 0.005 <= put_dist <= 0.05 and 0.005 <= call_dist <= 0.05:
                put_short = round_strike(oracle_put_strike)
                call_short = round_strike(oracle_call_strike)
                use_oracle = True
                logger.info(f"Using Oracle strikes: Put short ${put_short}, Call short ${call_short}")

        # Priority 2: GEX walls (only if Oracle not used)
        if not use_oracle and call_wall > 0 and put_wall > 0:
            put_short = round_strike(put_wall)
            call_short = round_strike(call_wall)
            use_gex = True
            logger.info(f"Using GEX walls: Put short ${put_short}, Call short ${call_short}")

        # Priority 3: SD-based fallback (only if neither Oracle nor GEX)
        if not use_oracle and not use_gex:
            put_short = round_strike(spot_price - sd * expected_move)
            call_short = round_strike(spot_price + sd * expected_move)
            logger.info(f"Using SD-based: Put short ${put_short}, Call short ${call_short}")

        # Long strikes are spread_width away from shorts
        put_long = put_short - width
        call_long = call_short + width

        return {
            'put_short': put_short,
            'put_long': put_long,
            'call_short': call_short,
            'call_long': call_long,
            'using_gex': use_gex,
            'using_oracle': use_oracle,
            'source': 'ORACLE' if use_oracle else ('GEX' if use_gex else 'SD'),
        }

    def estimate_credits(
        self,
        spot_price: float,
        expected_move: float,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
        vix: float
    ) -> Dict[str, float]:
        """
        Estimate credits for the Iron Condor.

        This is a rough estimate - real pricing comes from option chain.
        """
        # Distance from spot to strikes (normalized)
        put_dist = (spot_price - put_short) / expected_move
        call_dist = (call_short - spot_price) / expected_move

        # Base credit estimate (rough approximation)
        # Closer to ATM = higher credit, further = lower credit
        vol_factor = vix / 20.0  # Normalize to VIX 20
        spread_width = put_short - put_long

        # Estimate per-spread credit (0.5 - 1.5% of spread width typically)
        put_credit = spread_width * 0.015 * vol_factor / max(put_dist, 0.5)
        call_credit = spread_width * 0.015 * vol_factor / max(call_dist, 0.5)

        # Cap at reasonable values
        put_credit = max(0.02, min(put_credit, spread_width * 0.4))
        call_credit = max(0.02, min(call_credit, spread_width * 0.4))

        total_credit = put_credit + call_credit
        max_profit = total_credit * 100  # Per contract
        max_loss = (spread_width - total_credit) * 100

        return {
            'put_credit': round(put_credit, 2),
            'call_credit': round(call_credit, 2),
            'total_credit': round(total_credit, 2),
            'max_profit': round(max_profit, 2),
            'max_loss': round(max_loss, 2),
        }

    def get_oracle_advice(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Oracle ML advice if available.

        Returns FULL prediction context for audit trail including:
        - win_probability: The key metric!
        - confidence: Model confidence
        - top_factors: WHY Oracle made this decision
        - suggested_sd_multiplier: Risk adjustment
        - use_gex_walls: Whether to use GEX wall strikes
        - probabilities: Raw probability dict
        """
        if not self.oracle:
            return None

        try:
            # Build context for Oracle using correct field names
            from quant.oracle_advisor import MarketContext as OracleMarketContext, GEXRegime

            # Convert gex_regime string to GEXRegime enum
            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL').upper()
            try:
                gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = OracleMarketContext(
                spot_price=market_data['spot_price'],
                vix=market_data['vix'],
                gex_put_wall=market_data['put_wall'],
                gex_call_wall=market_data['call_wall'],
                gex_regime=gex_regime,
                gex_net=market_data.get('net_gex', 0),
                gex_flip_point=market_data.get('flip_point', 0),
                expected_move_pct=(market_data.get('expected_move', 0) / market_data.get('spot_price', 1) * 100) if market_data.get('spot_price') else 0,
            )

            # Call correct method: get_ares_advice instead of get_prediction
            # Pass all VIX filtering parameters for proper skip logic
            prediction = self.oracle.get_ares_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=False,  # Skip Claude for performance during live trading
                vix_hard_skip=getattr(self.config, 'vix_skip', 32.0) or 32.0,
                vix_monday_friday_skip=getattr(self.config, 'vix_monday_friday_skip', 30.0) or 0.0,
                vix_streak_skip=getattr(self.config, 'vix_streak_skip', 28.0) or 0.0,
                recent_losses=getattr(self, '_recent_losses', 0),
            )

            if prediction:
                # Extract top_factors as list of dicts for JSON storage
                top_factors = []
                if hasattr(prediction, 'top_factors') and prediction.top_factors:
                    for factor_name, impact in prediction.top_factors:
                        top_factors.append({'factor': factor_name, 'impact': impact})

                return {
                    # Core metrics
                    'confidence': prediction.confidence,
                    'win_probability': getattr(prediction, 'win_probability', 0),
                    'advice': prediction.advice.value if prediction.advice else 'HOLD',
                    'reasoning': prediction.reasoning,

                    # Decision factors (WHY)
                    'top_factors': top_factors,
                    'probabilities': getattr(prediction, 'probabilities', {}),

                    # Suggested adjustments
                    'suggested_sd_multiplier': getattr(prediction, 'suggested_sd_multiplier', 1.0),
                    'use_gex_walls': getattr(prediction, 'use_gex_walls', False),
                    'suggested_put_strike': getattr(prediction, 'suggested_put_strike', None),
                    'suggested_call_strike': getattr(prediction, 'suggested_call_strike', None),
                    'suggested_risk_pct': getattr(prediction, 'suggested_risk_pct', 10.0),
                }
        except Exception as e:
            logger.warning(f"Oracle advice error: {e}")
            import traceback
            traceback.print_exc()

        return None

    def generate_signal(self) -> Optional[IronCondorSignal]:
        """
        Generate an Iron Condor signal.

        This is the MAIN entry point for signal generation.

        Returns signal with FULL context for audit trail:
        - Market data (spot, VIX, expected move)
        - Kronos GEX data (walls, regime, flip point, net GEX)
        - Oracle prediction (win probability, top factors, advice)
        - Strike selection rationale
        - Credit/risk calculations
        """
        # Step 1: Get market data (includes Kronos GEX)
        market_data = self.get_market_data()
        if not market_data:
            logger.info("No market data available")
            return None

        spot = market_data['spot_price']
        vix = market_data['vix']
        expected_move = market_data['expected_move']

        # Step 1.5: Validate data freshness (max 2 minutes old)
        data_timestamp = market_data.get('timestamp')
        if data_timestamp:
            data_age = (datetime.now(CENTRAL_TZ) - data_timestamp).total_seconds()
            if data_age > 120:  # 2 minutes
                logger.warning(f"Market data is {data_age:.0f}s old (>120s), refetching...")
                market_data = self.get_market_data()
                if not market_data:
                    logger.info("No fresh market data available")
                    return None
                spot = market_data['spot_price']
                vix = market_data['vix']
                expected_move = market_data['expected_move']

        # Step 2: Check VIX filter
        can_trade, vix_reason = self.check_vix_filter(vix)
        if not can_trade:
            logger.info(f"VIX filter blocked: {vix_reason}")
            return None

        # Step 3: Get Oracle advice (FULL context)
        oracle = self.get_oracle_advice(market_data)
        confidence = oracle.get('confidence', 0.7) if oracle else 0.7
        win_probability = oracle.get('win_probability', 0) if oracle else 0

        # Step 3.5: Validate Oracle advice - SKIP_TODAY overrides everything
        # Log FULL Oracle analysis for frontend visibility
        if oracle:
            # Detailed Oracle Math Logging for Frontend
            logger.info(f"[ARES ORACLE ANALYSIS]")
            logger.info(f"  Win Probability: {win_probability:.1%}")
            logger.info(f"  Confidence: {confidence:.1%}")
            logger.info(f"  Advice: {oracle.get('advice', 'N/A')}")
            logger.info(f"  Min Required: {self.config.min_win_probability:.1%}")

            # Log top factors that influenced the prediction
            if oracle.get('top_factors'):
                logger.info(f"  Top Factors Influencing Prediction:")
                for i, factor in enumerate(oracle['top_factors'][:5], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    direction = "+" if impact > 0 else ""
                    logger.info(f"    {i}. {factor_name}: {direction}{impact:.3f}")

                # APPLY top_factors to adjust confidence based on current conditions
                confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                    confidence, oracle['top_factors'], market_data
                )

            # Log probability breakdown if available
            if oracle.get('probabilities'):
                probs = oracle['probabilities']
                logger.info(f"  Probability Breakdown:")
                for outcome, prob in probs.items():
                    logger.info(f"    {outcome}: {prob:.1%}")

            # Log suggested adjustments
            logger.info(f"  Oracle Suggestions:")
            logger.info(f"    SD Multiplier: {oracle.get('suggested_sd_multiplier', 1.0):.2f}x")
            logger.info(f"    Use GEX Walls: {oracle.get('use_gex_walls', False)}")
            if oracle.get('suggested_put_strike'):
                logger.info(f"    Suggested Put Strike: ${oracle.get('suggested_put_strike')}")
            if oracle.get('suggested_call_strike'):
                logger.info(f"    Suggested Call Strike: ${oracle.get('suggested_call_strike')}")

            if oracle.get('advice') == 'SKIP_TODAY':
                logger.info(f"[ARES TRADE BLOCKED] Oracle advises SKIP_TODAY")
                logger.info(f"  Reason: {oracle.get('reasoning', 'No reason provided')}")
                return None

            # Validate win probability meets minimum threshold
            min_win_prob = self.config.min_win_probability
            if win_probability > 0 and win_probability < min_win_prob:
                logger.info(f"[ARES TRADE BLOCKED] Win probability below threshold")
                logger.info(f"  Oracle Win Prob: {win_probability:.1%}")
                logger.info(f"  Minimum Required: {min_win_prob:.1%}")
                logger.info(f"  Shortfall: {(min_win_prob - win_probability):.1%}")
                return None

            logger.info(f"[ARES ORACLE PASSED] Win Prob {win_probability:.1%} >= {min_win_prob:.1%} minimum")
        else:
            logger.info(f"[ARES] Oracle not available, using default confidence {confidence:.1%}")

        # Step 4: Calculate strikes (Oracle > GEX > SD priority)
        use_gex_walls = oracle.get('use_gex_walls', False) if oracle else False
        oracle_put = oracle.get('suggested_put_strike') if oracle else None
        oracle_call = oracle.get('suggested_call_strike') if oracle else None
        strikes = self.calculate_strikes(
            spot_price=spot,
            expected_move=expected_move,
            call_wall=market_data['call_wall'] if use_gex_walls else 0,
            put_wall=market_data['put_wall'] if use_gex_walls else 0,
            oracle_put_strike=oracle_put,
            oracle_call_strike=oracle_call,
        )

        # Step 5: Estimate credits
        pricing = self.estimate_credits(
            spot_price=spot,
            expected_move=expected_move,
            put_short=strikes['put_short'],
            put_long=strikes['put_long'],
            call_short=strikes['call_short'],
            call_long=strikes['call_long'],
            vix=vix,
        )

        # Step 6: Validate minimum credit
        if pricing['total_credit'] < self.config.min_credit:
            logger.info(f"Credit ${pricing['total_credit']:.2f} below minimum ${self.config.min_credit}")
            return None

        # Step 7: Get expiration (0DTE)
        now = datetime.now(CENTRAL_TZ)
        expiration = now.strftime("%Y-%m-%d")

        # Step 8: Build detailed reasoning (FULL audit trail)
        reasoning_parts = []
        reasoning_parts.append(f"VIX={vix:.1f}, Expected Move=${expected_move:.2f}")
        reasoning_parts.append(f"GEX Regime={market_data['gex_regime']}")

        if strikes.get('using_oracle'):
            reasoning_parts.append(f"Oracle Strikes: Put ${strikes['put_short']}, Call ${strikes['call_short']}")
        elif strikes['using_gex']:
            reasoning_parts.append(f"GEX-Protected: Put Wall ${market_data['put_wall']}, Call Wall ${market_data['call_wall']}")
        else:
            reasoning_parts.append(f"{self.config.sd_multiplier} SD strikes")

        if oracle:
            reasoning_parts.append(f"Oracle: {oracle.get('advice', 'N/A')} (Win Prob: {win_probability:.0%}, Conf: {confidence:.0%})")
            if oracle.get('top_factors'):
                top_factors_str = ", ".join([f"{f['factor']}: {f['impact']:.2f}" for f in oracle['top_factors'][:3]])
                reasoning_parts.append(f"Top Factors: {top_factors_str}")

        reasoning = " | ".join(reasoning_parts)

        # Build signal with FULL context
        signal = IronCondorSignal(
            # Market context
            spot_price=spot,
            vix=vix,
            expected_move=expected_move,
            call_wall=market_data['call_wall'],
            put_wall=market_data['put_wall'],
            gex_regime=market_data['gex_regime'],

            # Kronos context
            flip_point=market_data.get('flip_point', 0),
            net_gex=market_data.get('net_gex', 0),

            # Strikes
            put_short=strikes['put_short'],
            put_long=strikes['put_long'],
            call_short=strikes['call_short'],
            call_long=strikes['call_long'],
            expiration=expiration,

            # Pricing
            estimated_put_credit=pricing['put_credit'],
            estimated_call_credit=pricing['call_credit'],
            total_credit=pricing['total_credit'],
            max_loss=pricing['max_loss'],
            max_profit=pricing['max_profit'],

            # Signal quality
            confidence=confidence,
            reasoning=reasoning,
            source=strikes.get('source', 'SD'),

            # Oracle context (FULL for audit)
            oracle_win_probability=win_probability,
            oracle_advice=oracle.get('advice', '') if oracle else '',
            oracle_top_factors=oracle.get('top_factors', []) if oracle else [],
            oracle_suggested_sd=oracle.get('suggested_sd_multiplier', 1.0) if oracle else 1.0,
            oracle_use_gex_walls=oracle.get('use_gex_walls', False) if oracle else False,
            oracle_probabilities=oracle.get('probabilities', {}) if oracle else {},
        )

        logger.info(f"Signal: IC {strikes['put_long']}/{strikes['put_short']}-{strikes['call_short']}/{strikes['call_long']} @ ${pricing['total_credit']:.2f}")
        logger.info(f"Oracle: Win Prob={win_probability:.0%}, Advice={oracle.get('advice', 'N/A') if oracle else 'N/A'}")
        return signal
