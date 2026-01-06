"""
PEGASUS - Signal Generation
=============================

Signal generation for SPX Iron Condors.
Uses $5 strike increments and larger expected moves.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

from .models import IronCondorSignal, PEGASUSConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Optional imports
try:
    from quant.oracle_advisor import OracleAdvisor
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

try:
    from data.unified_data_provider import get_price, get_vix
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class SignalGenerator:
    """Generates SPX Iron Condor signals"""

    def __init__(self, config: PEGASUSConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        self.gex_calculator = None
        if KRONOS_AVAILABLE:
            try:
                self.gex_calculator = KronosGEXCalculator()
                logger.info("PEGASUS: Kronos GEX initialized")
            except Exception as e:
                logger.warning(f"PEGASUS: Kronos GEX init failed: {e}")

        if not self.gex_calculator and TRADIER_GEX_AVAILABLE:
            try:
                from data.gex_calculator import get_gex_calculator
                self.gex_calculator = get_gex_calculator()
                logger.info("PEGASUS: Tradier GEX initialized")
            except Exception as e:
                logger.warning(f"PEGASUS: Tradier GEX init failed: {e}")

        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("PEGASUS: Oracle initialized")
            except Exception as e:
                logger.warning(f"PEGASUS: Oracle init failed: {e}")

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Get SPX market data"""
        try:
            # SPX price - try to get from SPX or derive from SPY
            spot = None
            if DATA_AVAILABLE:
                spot = get_price("SPX")
                if not spot:
                    # Fallback: SPY * 10 approximation
                    spy = get_price("SPY")
                    if spy:
                        spot = spy * 10

            if not spot:
                return None

            vix = 20.0
            if DATA_AVAILABLE:
                try:
                    vix = get_vix() or 20.0
                except Exception as e:
                    logger.debug(f"VIX fetch failed, using default: {e}")

            # GEX data (scale from SPY if needed)
            gex_data = self._get_gex_data()

            expected_move = self._calculate_expected_move(spot, vix)

            # Only scale GEX walls by 10 if data came from SPY (not SPX)
            scale = 10 if (gex_data and gex_data.get('from_spy', False)) else 1

            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0) * scale if gex_data else 0,
                'put_wall': gex_data.get('put_wall', 0) * scale if gex_data else 0,
                'gex_regime': gex_data.get('regime', 'NEUTRAL') if gex_data else 'NEUTRAL',
                # Kronos GEX context (scaled if from SPY)
                'flip_point': gex_data.get('flip_point', 0) * scale if gex_data else 0,
                'net_gex': gex_data.get('net_gex', 0) if gex_data else 0,
                'timestamp': datetime.now(CENTRAL_TZ),
            }
        except Exception as e:
            logger.error(f"Market data error: {e}")
            return None

    def _get_gex_data(self) -> Optional[Dict]:
        if not self.gex_calculator:
            return None
        try:
            gex = None
            from_spy = False

            # KronosGEXCalculator uses get_gex_for_today_or_recent() - returns SPX data
            if KRONOS_AVAILABLE and hasattr(self.gex_calculator, 'get_gex_for_today_or_recent'):
                gex_data, source = self.gex_calculator.get_gex_for_today_or_recent()
                if gex_data:
                    # KronosGEXCalculator returns GEXData dataclass, convert to dict
                    gex = {
                        'call_wall': getattr(gex_data, 'major_call_wall', 0) or 0,
                        'put_wall': getattr(gex_data, 'major_put_wall', 0) or 0,
                        'regime': getattr(gex_data, 'regime', 'NEUTRAL') or 'NEUTRAL',
                        'flip_point': getattr(gex_data, 'gamma_flip', 0) or 0,
                        'net_gex': getattr(gex_data, 'net_gex', 0) or 0,
                    }
                    from_spy = False  # Kronos uses SPX options data

            # TradierGEXCalculator uses get_gex(symbol) - try SPX first, fallback to SPY
            elif hasattr(self.gex_calculator, 'get_gex'):
                gex = self.gex_calculator.get_gex("SPX")
                from_spy = False
                if not gex or gex.get('error'):
                    gex = self.gex_calculator.get_gex("SPY")
                    from_spy = True if gex and not gex.get('error') else False

            if gex and not gex.get('error'):
                return {
                    'call_wall': gex.get('call_wall', gex.get('major_call_wall', 0)),
                    'put_wall': gex.get('put_wall', gex.get('major_put_wall', 0)),
                    'regime': gex.get('regime', 'NEUTRAL'),
                    # Kronos GEX context for audit
                    'flip_point': gex.get('flip_point', gex.get('gamma_flip', 0)),
                    'net_gex': gex.get('net_gex', 0),
                    'from_spy': from_spy,  # Track source for scaling
                }
        except Exception as e:
            logger.warning(f"GEX data fetch failed: {e}")
        return None

    def get_oracle_advice(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Oracle prediction with FULL context for audit trail.

        Uses get_pegasus_advice() for SPX Iron Condor specific advice.
        Returns dict with: confidence, win_probability, advice, top_factors, etc.
        """
        if not self.oracle:
            return None

        try:
            # Build MarketContext for Oracle
            from quant.oracle_advisor import MarketContext, GEXRegime

            # Determine GEX regime
            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL').upper()
            try:
                gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = MarketContext(
                spot_price=market_data['spot_price'],
                vix=market_data['vix'],
                gex_call_wall=market_data.get('call_wall', 0),
                gex_put_wall=market_data.get('put_wall', 0),
                gex_regime=gex_regime,
                gex_flip_point=market_data.get('flip_point', 0),
                gex_net=market_data.get('net_gex', 0),
                expected_move_pct=(market_data.get('expected_move', 0) / market_data.get('spot_price', 1) * 100) if market_data.get('spot_price') else 0,
            )

            # Call PEGASUS-specific advice method
            prediction = self.oracle.get_pegasus_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=False,  # Skip Claude for performance
                spread_width=self.config.spread_width,
            )

            if not prediction:
                return None

            # Extract top_factors as list of dicts for JSON storage
            top_factors = []
            if hasattr(prediction, 'top_factors') and prediction.top_factors:
                for factor_name, impact in prediction.top_factors:
                    top_factors.append({'factor': factor_name, 'impact': impact})

            return {
                'confidence': prediction.confidence,
                'win_probability': prediction.win_probability,
                'advice': prediction.advice.value if prediction.advice else 'HOLD',
                'top_factors': top_factors,
                'probabilities': {},
                'suggested_sd_multiplier': prediction.suggested_sd_multiplier,
                'use_gex_walls': getattr(prediction, 'use_gex_walls', True),
                'suggested_put_strike': getattr(prediction, 'suggested_put_strike', None),
                'suggested_call_strike': getattr(prediction, 'suggested_call_strike', None),
                'reasoning': prediction.reasoning or '',
            }
        except Exception as e:
            logger.warning(f"PEGASUS Oracle error: {e}")
            return None

    def _calculate_expected_move(self, spot: float, vix: float) -> float:
        """Calculate 1 SD expected move for SPX"""
        annual_factor = math.sqrt(252)
        daily_vol = (vix / 100) / annual_factor
        return round(spot * daily_vol, 2)

    def check_vix_filter(self, vix: float) -> Tuple[bool, str]:
        if self.config.vix_skip and vix > self.config.vix_skip:
            return False, f"VIX {vix:.1f} > {self.config.vix_skip}"
        return True, "OK"

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

        # 1. VIX factor adjustment - SPX is sensitive to VIX
        vix_importance = factor_map.get('vix', factor_map.get('vix_level', 0))
        if vix_importance > 0.2:  # VIX is significant factor
            if vix > 25:
                penalty = min(0.10, (vix - 25) * 0.015)  # SPX more sensitive
                confidence -= penalty
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX elevated ({vix:.1f}): -{penalty:.0%}")
            elif vix < 14:
                boost = min(0.05, (14 - vix) * 0.01)
                confidence += boost
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX low ({vix:.1f}): +{boost:.0%}")

        # 2. GEX regime factor adjustment
        gex_importance = factor_map.get('gex_regime', factor_map.get('net_gex', 0))
        if gex_importance > 0.15:
            if gex_regime == 'NEGATIVE':
                penalty = 0.06
                confidence -= penalty
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + NEGATIVE regime: -{penalty:.0%}")
            elif gex_regime == 'POSITIVE':
                boost = 0.04
                confidence += boost
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + POSITIVE regime: +{boost:.0%}")

        # 3. Day of week factor
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
                penalty = 0.04
                confidence -= penalty
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + Friday: -{penalty:.0%}")

        # Clamp confidence to reasonable range
        confidence = max(0.4, min(0.95, confidence))

        if adjustments:
            logger.info(f"[PEGASUS TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
            for adj in adjustments:
                logger.info(f"  - {adj}")

        return confidence, adjustments

    def calculate_strikes(
        self,
        spot: float,
        expected_move: float,
        call_wall: float = 0,
        put_wall: float = 0,
        oracle_put_strike: Optional[float] = None,
        oracle_call_strike: Optional[float] = None,
    ) -> Dict[str, float]:
        """Calculate SPX strikes with $5 rounding

        Priority:
        1. Oracle suggested strikes (if provided and valid)
        2. GEX walls (if available)
        3. SD-based strikes (fallback)
        """
        sd = self.config.sd_multiplier
        width = self.config.spread_width

        def round_to_5(x):
            return round(x / 5) * 5

        use_oracle = False
        use_gex = False

        # Priority 1: Oracle suggested strikes
        if oracle_put_strike and oracle_call_strike:
            put_dist = (spot - oracle_put_strike) / spot
            call_dist = (oracle_call_strike - spot) / spot
            if 0.005 <= put_dist <= 0.05 and 0.005 <= call_dist <= 0.05:
                put_short = round_to_5(oracle_put_strike)
                call_short = round_to_5(oracle_call_strike)
                use_oracle = True

        # Priority 2: GEX walls
        if not use_oracle and call_wall > 0 and put_wall > 0:
            put_short = round_to_5(put_wall)
            call_short = round_to_5(call_wall)
            use_gex = True

        # Priority 3: SD-based fallback
        if not use_oracle and not use_gex:
            put_short = round_to_5(spot - sd * expected_move)
            call_short = round_to_5(spot + sd * expected_move)

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

    def estimate_credits(self, spot: float, expected_move: float, put_short: float, call_short: float, vix: float) -> Dict[str, float]:
        """Estimate SPX IC credits"""
        width = self.config.spread_width

        put_dist = (spot - put_short) / expected_move
        call_dist = (call_short - spot) / expected_move
        vol_factor = vix / 20.0

        # SPX typically has higher premiums
        put_credit = width * 0.025 * vol_factor / max(put_dist, 0.5)
        call_credit = width * 0.025 * vol_factor / max(call_dist, 0.5)

        put_credit = max(0.50, min(put_credit, width * 0.35))
        call_credit = max(0.50, min(call_credit, width * 0.35))

        total = put_credit + call_credit
        max_profit = total * 100
        max_loss = (width - total) * 100

        return {
            'put_credit': round(put_credit, 2),
            'call_credit': round(call_credit, 2),
            'total_credit': round(total, 2),
            'max_profit': round(max_profit, 2),
            'max_loss': round(max_loss, 2),
        }

    def generate_signal(self) -> Optional[IronCondorSignal]:
        """Generate SPX Iron Condor signal with FULL Oracle/Kronos context"""
        market = self.get_market_data()
        if not market:
            return None

        can_trade, reason = self.check_vix_filter(market['vix'])
        if not can_trade:
            logger.info(f"VIX filter: {reason}")
            return None

        # Get Oracle advice (optional but provides confidence boost)
        oracle = self.get_oracle_advice(market)

        # Validate Oracle advice - SKIP_TODAY and win probability check
        # Log FULL Oracle analysis for frontend visibility
        if oracle:
            win_prob = oracle.get('win_probability', 0)
            oracle_confidence = oracle.get('confidence', 0)

            # Detailed Oracle Math Logging for Frontend
            logger.info(f"[PEGASUS ORACLE ANALYSIS]")
            logger.info(f"  Win Probability: {win_prob:.1%}")
            logger.info(f"  Confidence: {oracle_confidence:.1%}")
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
                oracle_confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                    oracle_confidence, oracle['top_factors'], market
                )

            # Log suggested adjustments
            logger.info(f"  Oracle Suggestions:")
            logger.info(f"    SD Multiplier: {oracle.get('suggested_sd_multiplier', 1.0):.2f}x")
            logger.info(f"    Use GEX Walls: {oracle.get('use_gex_walls', False)}")
            if oracle.get('suggested_put_strike'):
                logger.info(f"    Suggested Put Strike: ${oracle.get('suggested_put_strike')}")
            if oracle.get('suggested_call_strike'):
                logger.info(f"    Suggested Call Strike: ${oracle.get('suggested_call_strike')}")

            # Log reasoning
            if oracle.get('reasoning'):
                logger.info(f"  Oracle Reasoning: {oracle.get('reasoning')[:200]}...")

            if oracle.get('advice') == 'SKIP_TODAY':
                logger.info(f"[PEGASUS TRADE BLOCKED] Oracle advises SKIP_TODAY")
                logger.info(f"  Reason: {oracle.get('reasoning', 'No reason provided')}")
                return None

            # Validate win probability meets minimum threshold
            min_win_prob = self.config.min_win_probability
            if win_prob > 0 and win_prob < min_win_prob:
                logger.info(f"[PEGASUS TRADE BLOCKED] Win probability below threshold")
                logger.info(f"  Oracle Win Prob: {win_prob:.1%}")
                logger.info(f"  Minimum Required: {min_win_prob:.1%}")
                logger.info(f"  Shortfall: {(min_win_prob - win_prob):.1%}")
                return None

            logger.info(f"[PEGASUS ORACLE PASSED] Win Prob {win_prob:.1%} >= {min_win_prob:.1%} minimum")
        else:
            logger.info(f"[PEGASUS] Oracle not available, using default confidence")

        # Get Oracle suggested strikes if available
        oracle_put = oracle.get('suggested_put_strike') if oracle else None
        oracle_call = oracle.get('suggested_call_strike') if oracle else None
        strikes = self.calculate_strikes(
            market['spot_price'],
            market['expected_move'],
            market['call_wall'],
            market['put_wall'],
            oracle_put_strike=oracle_put,
            oracle_call_strike=oracle_call,
        )

        pricing = self.estimate_credits(
            market['spot_price'],
            market['expected_move'],
            strikes['put_short'],
            strikes['call_short'],
            market['vix'],
        )

        if pricing['total_credit'] < self.config.min_credit:
            logger.info(f"Credit ${pricing['total_credit']:.2f} < ${self.config.min_credit}")
            return None

        # Calculate expiration for SPXW weekly options (next Friday)
        # SPX weeklies expire every Friday (and some days have 0DTE)
        now = datetime.now(CENTRAL_TZ)
        days_until_friday = (4 - now.weekday()) % 7  # Friday is weekday 4
        if days_until_friday == 0 and now.hour >= 15:
            # It's Friday after 3 PM, use next Friday
            days_until_friday = 7
        expiration_date = now + timedelta(days=days_until_friday)
        expiration = expiration_date.strftime("%Y-%m-%d")

        # Build detailed reasoning (FULL audit trail)
        reasoning_parts = []
        reasoning_parts.append(f"SPX VIX={market['vix']:.1f}, EM=${market['expected_move']:.0f}")
        if strikes.get('using_oracle'):
            reasoning_parts.append(f"Oracle Strikes")
        elif strikes['using_gex']:
            reasoning_parts.append("GEX-Protected")
        else:
            reasoning_parts.append(f"{self.config.sd_multiplier} SD")

        # Oracle context for reasoning
        if oracle:
            reasoning_parts.append(f"Oracle: {oracle['advice']} ({oracle['confidence']:.0%})")
            if oracle['win_probability']:
                reasoning_parts.append(f"Win Prob: {oracle['win_probability']:.0%}")
            # Add top factor if available
            if oracle['top_factors']:
                top = oracle['top_factors'][0]
                reasoning_parts.append(f"Top Factor: {top['factor']}")

        reasoning = " | ".join(reasoning_parts)

        # Determine confidence (base 0.7, boost with Oracle)
        confidence = 0.7
        if oracle:
            if oracle['advice'] == 'ENTER' and oracle['confidence'] > 0.6:
                confidence = min(0.9, confidence + oracle['confidence'] * 0.2)
            elif oracle['advice'] == 'EXIT':
                confidence -= 0.2

        return IronCondorSignal(
            spot_price=market['spot_price'],
            vix=market['vix'],
            expected_move=market['expected_move'],
            call_wall=market['call_wall'],
            put_wall=market['put_wall'],
            gex_regime=market['gex_regime'],
            # Kronos GEX context
            flip_point=market.get('flip_point', 0),
            net_gex=market.get('net_gex', 0),
            # Strike recommendations
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
            # Oracle context (CRITICAL for audit)
            oracle_win_probability=oracle['win_probability'] if oracle else 0,
            oracle_advice=oracle['advice'] if oracle else '',
            oracle_top_factors=oracle['top_factors'] if oracle else [],
            oracle_suggested_sd=oracle['suggested_sd_multiplier'] if oracle else 1.0,
            oracle_use_gex_walls=oracle['use_gex_walls'] if oracle else False,
            oracle_probabilities=oracle['probabilities'] if oracle else {},
        )
