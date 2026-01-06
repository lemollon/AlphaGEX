"""
ICARUS - Signal Generation
===========================

Clean signal generation using GEX data, Oracle, and ML models.

ICARUS uses aggressive parameters:
- 10% wall filter (vs ATHENA's 3%)
- 40% min win probability (vs 48%)
- Trades far from walls for more opportunities
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from zoneinfo import ZoneInfo

from .models import TradeSignal, SpreadType, ICARUSConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Optional imports with clear fallbacks
try:
    from quant.oracle_advisor import OracleAdvisor, OraclePrediction, TradingAdvice, MarketContext as OracleMarketContext, GEXRegime
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None
    OracleMarketContext = None
    GEXRegime = None

try:
    from quant.kronos_gex_calculator import KronosGEXCalculator
    KRONOS_AVAILABLE = True
except ImportError:
    KRONOS_AVAILABLE = False
    KronosGEXCalculator = None

try:
    from quant.gex_signal_integration import GEXSignalIntegration
    GEX_ML_AVAILABLE = True
except ImportError:
    GEX_ML_AVAILABLE = False
    GEXSignalIntegration = None

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
    Generates trading signals from GEX data and ML models.

    ICARUS uses MORE AGGRESSIVE parameters than ATHENA:
    - 10% wall_filter_pct (vs 3%)
    - 40% min_win_probability (vs 48%)
    """

    def __init__(self, config: ICARUSConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator (try Kronos first, fallback to Tradier)
        self.gex_calculator = None
        if KRONOS_AVAILABLE:
            try:
                self.gex_calculator = KronosGEXCalculator()
                logger.info("ICARUS SignalGenerator: Using Kronos GEX")
            except Exception as e:
                logger.warning(f"Kronos init failed: {e}")

        if not self.gex_calculator and TRADIER_GEX_AVAILABLE:
            try:
                self.gex_calculator = get_gex_calculator()
                logger.info("ICARUS SignalGenerator: Using Tradier GEX fallback")
            except Exception as e:
                logger.warning(f"Tradier GEX init failed: {e}")

        # ML Signal Integration
        self.ml_signal = None
        if GEX_ML_AVAILABLE:
            try:
                self.ml_signal = GEXSignalIntegration()
                if self.ml_signal.load_models():
                    logger.info("ICARUS SignalGenerator: ML models loaded")
                else:
                    self.ml_signal = None
            except Exception as e:
                logger.warning(f"ML init failed: {e}")

        # Oracle Advisor
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ICARUS SignalGenerator: Oracle initialized")
            except Exception as e:
                logger.warning(f"Oracle init failed: {e}")

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current GEX data.

        Returns dict with: spot_price, call_wall, put_wall, gex_regime, vix
        """
        if not self.gex_calculator:
            logger.warning("No GEX calculator available")
            return None

        try:
            gex = self.gex_calculator.calculate_gex(self.config.ticker)
            if not gex:
                return None

            # Get VIX
            vix = 20.0
            if DATA_PROVIDER_AVAILABLE:
                try:
                    vix = get_vix() or 20.0
                except Exception:
                    pass

            return {
                'spot_price': gex.get('spot_price', gex.get('underlying_price', 0)),
                'call_wall': gex.get('call_wall', gex.get('major_call_wall', 0)),
                'put_wall': gex.get('put_wall', gex.get('major_put_wall', 0)),
                'gex_regime': gex.get('regime', gex.get('gex_regime', 'NEUTRAL')),
                'net_gex': gex.get('net_gex', 0),
                'flip_point': gex.get('flip_point', gex.get('gamma_flip', 0)),
                'vix': vix,
                'timestamp': datetime.now(CENTRAL_TZ),
                # Raw Kronos data for audit
                'kronos_raw': gex,
            }
        except Exception as e:
            logger.error(f"GEX fetch error: {e}")
            return None

    def get_ml_signal(self, gex_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get ML model prediction.

        Returns dict with: direction, confidence, win_probability
        """
        if not self.ml_signal:
            return None

        try:
            signal = self.ml_signal.get_combined_signal(
                ticker=self.config.ticker,
                spot_price=gex_data['spot_price'],
                call_wall=gex_data['call_wall'],
                put_wall=gex_data['put_wall'],
                vix=gex_data['vix'],
            )

            if signal:
                return {
                    'direction': signal.get('direction', 'NEUTRAL'),
                    'confidence': signal.get('confidence', 0),
                    'win_probability': signal.get('win_probability', 0),
                    'model_name': signal.get('model_name', 'unknown'),
                }
        except Exception as e:
            logger.warning(f"ML signal error: {e}")

        return None

    def get_oracle_advice(self, gex_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Oracle ML advice for ICARUS directional trades.

        Returns FULL prediction context for audit trail.
        """
        if not self.oracle or not ORACLE_AVAILABLE:
            return None

        try:
            # Convert gex_regime string to GEXRegime enum
            gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL').upper()
            try:
                gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            # Build context for Oracle
            context = OracleMarketContext(
                spot_price=gex_data['spot_price'],
                vix=gex_data['vix'],
                gex_put_wall=gex_data.get('put_wall', 0),
                gex_call_wall=gex_data.get('call_wall', 0),
                gex_regime=gex_regime,
                gex_net=gex_data.get('net_gex', 0),
                gex_flip_point=gex_data.get('flip_point', 0),
            )

            # Call ATHENA-specific advice method (ICARUS uses same model)
            prediction = self.oracle.get_athena_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=False,
                wall_filter_pct=self.config.wall_filter_pct,  # Uses ICARUS's 10%
            )

            if not prediction:
                return None

            # Extract top_factors as list of dicts for JSON storage
            top_factors = []
            if hasattr(prediction, 'top_factors') and prediction.top_factors:
                for factor_name, impact in prediction.top_factors:
                    top_factors.append({'factor': factor_name, 'impact': impact})

            # Determine Oracle's direction from reasoning
            oracle_direction = "FLAT"
            if hasattr(prediction, 'reasoning') and prediction.reasoning:
                if "BULLISH" in prediction.reasoning.upper() or "BULL" in prediction.reasoning.upper():
                    oracle_direction = "BULLISH"
                elif "BEARISH" in prediction.reasoning.upper() or "BEAR" in prediction.reasoning.upper():
                    oracle_direction = "BEARISH"

            return {
                'confidence': prediction.confidence,
                'win_probability': prediction.win_probability,
                'advice': prediction.advice.value if prediction.advice else 'HOLD',
                'direction': oracle_direction,
                'top_factors': top_factors,
                'reasoning': prediction.reasoning or '',
            }
        except Exception as e:
            logger.warning(f"ICARUS Oracle error: {e}")
            return None

    def adjust_confidence_from_top_factors(
        self,
        confidence: float,
        top_factors: List[Dict],
        gex_data: Dict
    ) -> Tuple[float, List[str]]:
        """
        Adjust confidence based on Oracle's top contributing factors.

        ICARUS is more aggressive - smaller adjustments.
        """
        if not top_factors:
            return confidence, []

        adjustments = []
        original_confidence = confidence
        vix = gex_data.get('vix', 20)
        gex_regime = gex_data.get('gex_regime', 'NEUTRAL')

        # Extract factor names and impacts
        factor_map = {}
        for f in top_factors[:5]:
            name = f.get('factor', f.get('feature', '')).lower()
            impact = f.get('impact', f.get('importance', 0))
            factor_map[name] = impact

        # 1. VIX factor - Higher VIX can be GOOD for directional trades
        vix_importance = factor_map.get('vix', factor_map.get('vix_level', 0))
        if vix_importance > 0.2:
            if 18 < vix < 28:  # Sweet spot for directional
                boost = 0.02  # Smaller boost for ICARUS (aggressive already)
                confidence += boost
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX in sweet spot ({vix:.1f}): +{boost:.0%}")
            elif vix > 35:  # Too volatile
                penalty = 0.03  # Smaller penalty for ICARUS
                confidence -= penalty
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX extreme ({vix:.1f}): -{penalty:.0%}")

        # 2. GEX regime - NEGATIVE regime favors directional trades
        gex_importance = factor_map.get('gex_regime', factor_map.get('net_gex', 0))
        if gex_importance > 0.15:
            if gex_regime == 'NEGATIVE':
                boost = 0.03  # ICARUS likes negative gamma
                confidence += boost
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + NEGATIVE regime: +{boost:.0%}")
            elif gex_regime == 'POSITIVE':
                penalty = 0.02  # Smaller penalty - ICARUS is aggressive
                confidence -= penalty
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + POSITIVE regime: -{penalty:.0%}")

        # 3. Day of week - Early week better for trends
        dow_importance = factor_map.get('day_of_week', 0)
        if dow_importance > 0.15:
            day = datetime.now(ZoneInfo("America/Chicago")).weekday()
            if day in [0, 1, 2]:  # Mon-Wed
                boost = 0.01
                confidence += boost
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + early week: +{boost:.0%}")
            elif day == 4:  # Friday
                penalty = 0.02
                confidence -= penalty
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + Friday: -{penalty:.0%}")

        # Clamp confidence - ICARUS allows lower confidence
        confidence = max(0.35, min(0.95, confidence))

        if adjustments:
            logger.info(f"[ICARUS TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
            for adj in adjustments:
                logger.info(f"  - {adj}")

        return confidence, adjustments

    def check_wall_proximity(self, gex_data: Dict) -> Tuple[bool, str, str]:
        """
        Check if price is near a GEX wall for entry.

        ICARUS uses 10% wall filter (vs ATHENA's 3%) - MUCH MORE RELAXED!

        Returns: (is_valid, direction, reason)
        """
        spot = gex_data['spot_price']
        call_wall = gex_data['call_wall']
        put_wall = gex_data['put_wall']

        if not spot or not call_wall or not put_wall:
            return False, "", "Missing price/wall data"

        # Calculate distances
        dist_to_put_wall_pct = ((spot - put_wall) / spot) * 100
        dist_to_call_wall_pct = ((call_wall - spot) / spot) * 100

        # ICARUS uses 10% threshold - much more relaxed!
        threshold = self.config.wall_filter_pct

        # Near put wall = bullish (support bounce)
        if abs(dist_to_put_wall_pct) <= threshold:
            return True, "BULLISH", f"Within {threshold}% of put wall (support)"

        # Near call wall = bearish (resistance rejection)
        if abs(dist_to_call_wall_pct) <= threshold:
            return True, "BEARISH", f"Within {threshold}% of call wall (resistance)"

        return False, "", f"Not near walls (put: {dist_to_put_wall_pct:.2f}%, call: {dist_to_call_wall_pct:.2f}%)"

    def calculate_spread_strikes(
        self,
        direction: str,
        spot_price: float,
        expiration: str
    ) -> Tuple[float, float]:
        """
        Calculate optimal spread strikes.

        ICARUS uses $3 spread width (vs ATHENA's $2).

        Returns: (long_strike, short_strike)
        """
        # Round to nearest dollar
        atm = round(spot_price)
        width = self.config.spread_width  # $3 for ICARUS

        if direction == "BULLISH":
            # Bull call spread: buy ATM call, sell OTM call
            long_strike = atm
            short_strike = atm + width
        else:
            # Bear put spread: buy ATM put, sell OTM put
            long_strike = atm
            short_strike = atm - width

        return long_strike, short_strike

    def estimate_spread_pricing(
        self,
        spread_type: SpreadType,
        long_strike: float,
        short_strike: float,
        spot_price: float,
        vix: float
    ) -> Tuple[float, float, float]:
        """
        Estimate spread debit, max profit, and max loss.

        Returns: (debit, max_profit, max_loss)
        """
        width = abs(short_strike - long_strike)

        # Estimate debit based on moneyness and VIX
        vol_factor = min(vix / 20.0, 1.5)

        # Base debit is roughly 35-40% of width for ATM 0DTE spreads
        base_debit_pct = 0.35 + (0.05 * vol_factor)
        debit = width * base_debit_pct

        # Max profit = width - debit
        max_profit = (width - debit) * 100  # Per contract

        # Max loss = debit
        max_loss = debit * 100  # Per contract

        return round(debit, 2), round(max_profit, 2), round(max_loss, 2)

    def generate_signal(self) -> Optional[TradeSignal]:
        """
        Generate a trading signal.

        ICARUS uses AGGRESSIVE parameters:
        - 10% wall filter (much more room to trade)
        - 40% min win probability
        - 0.5 min R:R ratio
        """
        # Step 1: Get GEX data
        gex_data = self.get_gex_data()
        if not gex_data:
            logger.info("No GEX data available")
            return None

        spot_price = gex_data['spot_price']
        vix = gex_data['vix']

        # Step 2: Check wall proximity (10% filter for ICARUS!)
        near_wall, wall_direction, wall_reason = self.check_wall_proximity(gex_data)
        if not near_wall:
            logger.info(f"ICARUS wall filter failed: {wall_reason}")
            return None

        # Step 3: Get ML signal (optional confirmation)
        ml_signal = self.get_ml_signal(gex_data)
        ml_direction = ml_signal.get('direction') if ml_signal else None
        ml_confidence = ml_signal.get('confidence', 0) if ml_signal else 0

        # Step 3.5: Get Oracle advice
        oracle = self.get_oracle_advice(gex_data)
        oracle_direction = oracle.get('direction', 'FLAT') if oracle else 'FLAT'
        oracle_confidence = oracle.get('confidence', 0) if oracle else 0
        oracle_win_prob = oracle.get('win_probability', 0) if oracle else 0

        # Step 3.6: Validate Oracle advice
        if oracle:
            logger.info(f"[ICARUS ORACLE ANALYSIS]")
            logger.info(f"  Win Probability: {oracle_win_prob:.1%}")
            logger.info(f"  Confidence: {oracle_confidence:.1%}")
            logger.info(f"  Direction: {oracle_direction}")
            logger.info(f"  Advice: {oracle.get('advice', 'N/A')}")
            logger.info(f"  Min Required: {self.config.min_win_probability:.1%}")

            if oracle.get('top_factors'):
                logger.info(f"  Top Factors:")
                for i, factor in enumerate(oracle['top_factors'][:5], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    direction_sign = "+" if impact > 0 else ""
                    logger.info(f"    {i}. {factor_name}: {direction_sign}{impact:.3f}")

            # SKIP_TODAY from Oracle overrides everything
            if oracle.get('advice') == 'SKIP_TODAY':
                logger.info(f"[ICARUS TRADE BLOCKED] Oracle advises SKIP_TODAY")
                return None

            # Validate win probability meets minimum threshold (40% for ICARUS)
            min_win_prob = self.config.min_win_probability
            if oracle_win_prob > 0 and oracle_win_prob < min_win_prob:
                logger.info(f"[ICARUS TRADE BLOCKED] Win probability below threshold")
                logger.info(f"  Oracle Win Prob: {oracle_win_prob:.1%}")
                logger.info(f"  Minimum Required: {min_win_prob:.1%}")
                return None

            logger.info(f"[ICARUS ORACLE PASSED] Win Prob {oracle_win_prob:.1%} >= {min_win_prob:.1%}")
        else:
            logger.info(f"[ICARUS] Oracle not available, using wall-based confidence only")

        # Log ML analysis if available
        if ml_signal:
            logger.info(f"[ICARUS ML ANALYSIS]")
            logger.info(f"  Direction: {ml_direction or 'N/A'}")
            logger.info(f"  Confidence: {ml_confidence:.1%}")
            logger.info(f"  Win Probability: {ml_signal.get('win_probability', 0):.1%}")

        # Step 4: Determine final direction
        direction = wall_direction
        direction_source = "WALL"

        # Check if Oracle should override wall direction
        oracle_override_threshold = 0.85
        oracle_win_prob_threshold = 0.60

        if oracle and oracle_direction != 'FLAT':
            if oracle_confidence >= oracle_override_threshold and oracle_win_prob >= oracle_win_prob_threshold:
                if oracle_direction != wall_direction:
                    logger.info(f"[ICARUS ORACLE OVERRIDE] Oracle overriding wall direction!")
                    logger.info(f"  Wall Direction: {wall_direction}")
                    logger.info(f"  Oracle Direction: {oracle_direction}")
                    direction = oracle_direction
                    direction_source = "ORACLE_OVERRIDE"

        # Calculate confidence
        if direction_source == "ORACLE_OVERRIDE":
            confidence = 0.75 + (oracle_confidence - oracle_override_threshold) * 0.5
            confidence = min(0.95, confidence)
        else:
            confidence = 0.7  # Base confidence from wall proximity

        # ML can boost or reduce confidence
        if ml_signal:
            if ml_direction == direction:
                confidence = min(0.95, confidence + ml_confidence * 0.20)
            elif ml_direction and ml_direction != direction and ml_confidence > 0.7:
                confidence -= 0.08  # Smaller penalty for ICARUS

        # Oracle adjustments (when not overriding)
        if oracle and direction_source != "ORACLE_OVERRIDE":
            if oracle_direction == direction and oracle_confidence > 0.6:
                boost = oracle_confidence * 0.20
                confidence = min(0.95, confidence + boost)
            elif oracle_direction != direction and oracle_direction != 'FLAT' and oracle_confidence > 0.6:
                penalty = (oracle_confidence - 0.6) * 0.20  # Smaller penalty
                confidence -= penalty
            if oracle.get('advice') == 'SKIP_TODAY':
                return None

            if oracle.get('top_factors'):
                confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                    confidence, oracle['top_factors'], gex_data
                )

        # ICARUS has lower confidence threshold (0.40)
        if confidence < 0.40:
            logger.info(f"Confidence too low: {confidence:.2f}")
            return None

        # Step 5: Determine spread type
        spread_type = SpreadType.BULL_CALL if direction == "BULLISH" else SpreadType.BEAR_PUT

        # Step 6: Calculate strikes ($3 width for ICARUS)
        now = datetime.now(CENTRAL_TZ)
        expiration = now.strftime("%Y-%m-%d")

        long_strike, short_strike = self.calculate_spread_strikes(
            direction, spot_price, expiration
        )

        # Step 7: Estimate pricing
        debit, max_profit, max_loss = self.estimate_spread_pricing(
            spread_type, long_strike, short_strike, spot_price, vix
        )

        # Step 8: Calculate risk/reward (0.5 min for ICARUS)
        rr_ratio = max_profit / max_loss if max_loss > 0 else 0

        if rr_ratio < self.config.min_rr_ratio:
            logger.info(f"R:R ratio {rr_ratio:.2f} below minimum {self.config.min_rr_ratio}")
            return None

        # Step 9: Build detailed reasoning
        reasoning_parts = []
        reasoning_parts.append(f"VIX={vix:.1f}, GEX Regime={gex_data['gex_regime']}")
        reasoning_parts.append(wall_reason)

        if ml_signal:
            reasoning_parts.append(f"ML: {ml_direction} ({ml_confidence:.0%})")
            if ml_signal.get('win_probability'):
                reasoning_parts.append(f"ML Win Prob: {ml_signal['win_probability']:.0%}")

        if oracle:
            reasoning_parts.append(f"Oracle: {oracle.get('advice', 'N/A')} ({oracle_direction}, {oracle_confidence:.0%})")
            if oracle_win_prob:
                reasoning_parts.append(f"Oracle Win Prob: {oracle_win_prob:.0%}")

        reasoning_parts.append(f"R:R = {rr_ratio:.2f}:1")
        reasoning = " | ".join(reasoning_parts)

        # Determine wall type and distance
        wall_type = ""
        wall_distance = 0
        if direction == "BULLISH":
            wall_type = "PUT_WALL"
            wall_distance = abs(((spot_price - gex_data['put_wall']) / spot_price) * 100)
        else:
            wall_type = "CALL_WALL"
            wall_distance = abs(((gex_data['call_wall'] - spot_price) / spot_price) * 100)

        # Determine source
        if oracle and ml_signal:
            source = "GEX_ML_ORACLE"
        elif oracle:
            source = "GEX_ORACLE"
        elif ml_signal:
            source = "GEX_ML"
        else:
            source = "GEX_WALL"

        # Convert Oracle top_factors to JSON string
        import json
        oracle_top_factors_json = ""
        if oracle and oracle.get('top_factors'):
            oracle_top_factors_json = json.dumps(oracle['top_factors'])

        signal = TradeSignal(
            direction=direction,
            spread_type=spread_type,
            confidence=confidence,
            spot_price=spot_price,
            call_wall=gex_data['call_wall'],
            put_wall=gex_data['put_wall'],
            gex_regime=gex_data['gex_regime'],
            vix=vix,
            flip_point=gex_data.get('flip_point', 0),
            net_gex=gex_data.get('net_gex', 0),
            long_strike=long_strike,
            short_strike=short_strike,
            expiration=expiration,
            estimated_debit=debit,
            max_profit=max_profit,
            max_loss=max_loss,
            rr_ratio=rr_ratio,
            source=source,
            reasoning=reasoning,
            ml_model_name=ml_signal.get('model_name', '') if ml_signal else '',
            ml_win_probability=ml_signal.get('win_probability', 0) if ml_signal else 0,
            ml_top_features='',
            oracle_win_probability=oracle_win_prob,
            oracle_advice=oracle.get('advice', '') if oracle else '',
            oracle_direction=oracle_direction,
            oracle_confidence=oracle_confidence,
            oracle_top_factors=oracle_top_factors_json,
            wall_type=wall_type,
            wall_distance_pct=wall_distance,
        )

        logger.info(f"ICARUS Signal generated: {direction} {spread_type.value} @ {spot_price}")
        logger.info(f"Context: Wall={wall_type} ({wall_distance:.2f}%), ML={ml_direction or 'N/A'} ({ml_confidence:.0%}), Oracle={oracle_direction or 'N/A'} ({oracle_confidence:.0%})")
        return signal
