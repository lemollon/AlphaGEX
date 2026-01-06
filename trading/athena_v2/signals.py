"""
ATHENA V2 - Signal Generation
==============================

Clean signal generation using GEX data, Oracle, and ML models.

Design principles:
1. One clear signal generation flow
2. All signal sources combined in one place
3. Explicit confidence and reasoning
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from zoneinfo import ZoneInfo

from .models import TradeSignal, SpreadType, ATHENAConfig, CENTRAL_TZ

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

# GEX Directional ML - predicts BULLISH/BEARISH/FLAT from GEX structure
GEX_DIRECTIONAL_ML_AVAILABLE = False
try:
    from quant.gex_directional_ml import GEXDirectionalPredictor, Direction, DirectionalPrediction
    GEX_DIRECTIONAL_ML_AVAILABLE = True
except ImportError:
    GEXDirectionalPredictor = None
    Direction = None
    DirectionalPrediction = None

# Ensemble Strategy - combines multiple signal sources with learned weights
ENSEMBLE_AVAILABLE = False
try:
    from quant.ensemble_strategy import get_ensemble_signal, EnsembleSignal, StrategySignal
    ENSEMBLE_AVAILABLE = True
except ImportError:
    get_ensemble_signal = None
    EnsembleSignal = None
    StrategySignal = None


class SignalGenerator:
    """
    Generates trading signals from GEX data and ML models.

    Single entry point for all signal logic.
    """

    def __init__(self, config: ATHENAConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator (try Kronos first, fallback to Tradier)
        self.gex_calculator = None
        if KRONOS_AVAILABLE:
            try:
                self.gex_calculator = KronosGEXCalculator()
                logger.info("SignalGenerator: Using Kronos GEX")
            except Exception as e:
                logger.warning(f"Kronos init failed: {e}")

        if not self.gex_calculator and TRADIER_GEX_AVAILABLE:
            try:
                self.gex_calculator = get_gex_calculator()
                logger.info("SignalGenerator: Using Tradier GEX fallback")
            except Exception as e:
                logger.warning(f"Tradier GEX init failed: {e}")

        # ML Signal Integration
        self.ml_signal = None
        if GEX_ML_AVAILABLE:
            try:
                self.ml_signal = GEXSignalIntegration()
                if self.ml_signal.load_models():
                    logger.info("SignalGenerator: ML models loaded")
                else:
                    self.ml_signal = None
            except Exception as e:
                logger.warning(f"ML init failed: {e}")

        # Oracle Advisor
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("SignalGenerator: Oracle initialized")
            except Exception as e:
                logger.warning(f"Oracle init failed: {e}")

        # GEX Directional ML - predicts BULLISH/BEARISH/FLAT from GEX structure
        self.gex_directional_ml = None
        if GEX_DIRECTIONAL_ML_AVAILABLE:
            try:
                self.gex_directional_ml = GEXDirectionalPredictor()
                # Try to load pre-trained model
                if hasattr(self.gex_directional_ml, 'load_model'):
                    self.gex_directional_ml.load_model()
                logger.info("SignalGenerator: GEX Directional ML initialized")
            except Exception as e:
                logger.warning(f"GEX Directional ML init failed: {e}")

    def get_gex_directional_prediction(self, gex_data: Dict, vix: float = 20.0) -> Optional[Dict]:
        """
        Get GEX Directional ML prediction (BULLISH/BEARISH/FLAT).

        Uses trained XGBoost model to predict market direction from GEX structure.
        This is ADDITIONAL signal confidence for directional bots.
        """
        if not self.gex_directional_ml:
            return None

        try:
            prediction = self.gex_directional_ml.predict(gex_data, vix)

            if prediction:
                result = {
                    'direction': prediction.direction.value,  # BULLISH/BEARISH/FLAT
                    'confidence': prediction.confidence,
                    'probabilities': prediction.probabilities,
                    'model_name': 'GEX_DIRECTIONAL_ML',
                }

                logger.info(f"[ATHENA GEX DIRECTIONAL ML] Direction: {prediction.direction.value}, "
                           f"Confidence: {prediction.confidence:.1%}")

                return result

        except Exception as e:
            logger.debug(f"GEX Directional ML prediction error: {e}")

        return None

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
        Get Oracle ML advice for ATHENA directional trades.

        Returns FULL prediction context for audit trail including:
        - win_probability: The key metric!
        - confidence: Model confidence
        - direction: BULLISH, BEARISH, or FLAT
        - top_factors: WHY Oracle made this decision
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

            # Call ATHENA-specific advice method
            prediction = self.oracle.get_athena_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=False,  # Skip Claude for performance
                wall_filter_pct=self.config.wall_filter_pct,
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
            logger.warning(f"ATHENA Oracle error: {e}")
            return None

    def adjust_confidence_from_top_factors(
        self,
        confidence: float,
        top_factors: List[Dict],
        gex_data: Dict
    ) -> Tuple[float, List[str]]:
        """
        Adjust confidence based on Oracle's top contributing factors.

        ATHENA uses directional spreads, so factor adjustments are different from ICs.
        Focus on factors that indicate directional momentum vs mean reversion.

        Returns (adjusted_confidence, adjustment_reasons).
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
                boost = 0.03
                confidence += boost
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX in sweet spot ({vix:.1f}): +{boost:.0%}")
            elif vix > 35:  # Too volatile
                penalty = 0.05
                confidence -= penalty
                adjustments.append(f"VIX factor high ({vix_importance:.2f}) + VIX extreme ({vix:.1f}): -{penalty:.0%}")

        # 2. GEX regime - NEGATIVE regime favors directional trades
        gex_importance = factor_map.get('gex_regime', factor_map.get('net_gex', 0))
        if gex_importance > 0.15:
            if gex_regime == 'NEGATIVE':
                boost = 0.04  # ATHENA likes negative gamma
                confidence += boost
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + NEGATIVE regime (favors directional): +{boost:.0%}")
            elif gex_regime == 'POSITIVE':
                penalty = 0.03  # Mean reversion more likely
                confidence -= penalty
                adjustments.append(f"GEX factor high ({gex_importance:.2f}) + POSITIVE regime (mean reverting): -{penalty:.0%}")

        # 3. Day of week - Early week better for trends
        dow_importance = factor_map.get('day_of_week', 0)
        if dow_importance > 0.15:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            day = datetime.now(ZoneInfo("America/Chicago")).weekday()
            if day in [0, 1, 2]:  # Mon-Wed
                boost = 0.02
                confidence += boost
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + early week: +{boost:.0%}")
            elif day == 4:  # Friday
                penalty = 0.03
                confidence -= penalty
                adjustments.append(f"Day factor high ({dow_importance:.2f}) + Friday expiry risk: -{penalty:.0%}")

        # Clamp confidence
        confidence = max(0.4, min(0.95, confidence))

        if adjustments:
            logger.info(f"[ATHENA TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
            for adj in adjustments:
                logger.info(f"  - {adj}")

        return confidence, adjustments

    def check_wall_proximity(self, gex_data: Dict) -> Tuple[bool, str, str]:
        """
        Check if price is near a GEX wall for entry.

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

        Returns: (long_strike, short_strike)
        """
        # Round to nearest dollar
        atm = round(spot_price)
        width = self.config.spread_width

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
        # This is a rough estimate - real pricing comes from option chain
        # For 0DTE ATM spreads, debit is typically 35-45% of width
        vol_factor = min(vix / 20.0, 1.5)  # Cap vol factor to prevent extreme estimates

        # Base debit is roughly 35-40% of width for ATM 0DTE spreads
        # This gives R:R of 1.5-1.86 which is more realistic
        base_debit_pct = 0.35 + (0.05 * vol_factor)  # 35-42.5% range
        debit = width * base_debit_pct

        # Max profit = width - debit
        max_profit = (width - debit) * 100  # Per contract

        # Max loss = debit
        max_loss = debit * 100  # Per contract

        return round(debit, 2), round(max_profit, 2), round(max_loss, 2)

    def generate_signal(self) -> Optional[TradeSignal]:
        """
        Generate a trading signal.

        This is the MAIN entry point for signal generation.
        Returns a TradeSignal if conditions are met, None otherwise.
        """
        # Step 1: Get GEX data
        gex_data = self.get_gex_data()
        if not gex_data:
            logger.info("No GEX data available")
            return None

        spot_price = gex_data['spot_price']
        vix = gex_data['vix']

        # Step 2: Check wall proximity
        near_wall, wall_direction, wall_reason = self.check_wall_proximity(gex_data)
        if not near_wall:
            logger.info(f"Wall filter failed: {wall_reason}")
            return None

        # Step 3: Get ML signal from 5 GEX probability models (PREFERRED SOURCE)
        ml_signal = self.get_ml_signal(gex_data)
        ml_direction = ml_signal.get('direction') if ml_signal else None
        ml_confidence = ml_signal.get('confidence', 0) if ml_signal else 0
        ml_win_prob = ml_signal.get('win_probability', 0) if ml_signal else 0

        # Step 3.5: Get Oracle advice (BACKUP SOURCE - ML takes precedence)
        oracle = self.get_oracle_advice(gex_data)
        oracle_direction = oracle.get('direction', 'FLAT') if oracle else 'FLAT'
        oracle_confidence = oracle.get('confidence', 0) if oracle else 0
        oracle_win_prob = oracle.get('win_probability', 0) if oracle else 0

        # ============================================================
        # ML MODEL TAKES PRECEDENCE OVER ORACLE
        # The 5 GEX probability models were backtested with high win rates
        # Oracle is only used as backup when ML is not available
        # ============================================================

        # Determine which source to use for win probability
        use_ml_prediction = ml_signal is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        prediction_source = "ML_5_MODEL_ENSEMBLE" if use_ml_prediction else "ORACLE"

        # Log ML analysis FIRST (it's the preferred source)
        if ml_signal:
            logger.info(f"[ATHENA ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
            logger.info(f"  Direction: {ml_direction or 'N/A'}")
            logger.info(f"  Confidence: {ml_confidence:.1%}")
            logger.info(f"  Win Probability: {ml_win_prob:.1%}")
            logger.info(f"  Model: {ml_signal.get('model_name', 'GEX_5_MODEL_ENSEMBLE')}")
            if ml_signal.get('model_predictions'):
                preds = ml_signal['model_predictions']
                logger.info(f"  Model Breakdown:")
                logger.info(f"    Flip Gravity: {preds.get('flip_gravity', 0):.1%}")
                logger.info(f"    Magnet Attraction: {preds.get('magnet_attraction', 0):.1%}")
                logger.info(f"    Pin Zone: {preds.get('pin_zone', 0):.1%}")
        else:
            logger.info(f"[ATHENA] ML models not available, falling back to Oracle")

        # Log Oracle analysis (backup source)
        if oracle:
            logger.info(f"[ATHENA ORACLE ANALYSIS] {'(BACKUP - ML unavailable)' if not use_ml_prediction else '(informational)'}")
            logger.info(f"  Win Probability: {oracle_win_prob:.1%}")
            logger.info(f"  Confidence: {oracle_confidence:.1%}")
            logger.info(f"  Direction: {oracle_direction}")
            logger.info(f"  Advice: {oracle.get('advice', 'N/A')}")

            if oracle.get('top_factors'):
                logger.info(f"  Top Factors:")
                for i, factor in enumerate(oracle['top_factors'][:3], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    direction_sign = "+" if impact > 0 else ""
                    logger.info(f"    {i}. {factor_name}: {direction_sign}{impact:.3f}")

            # Oracle SKIP_TODAY is informational only when ML is available
            if oracle.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[ATHENA] Oracle advises SKIP_TODAY but ML override active")
                    logger.info(f"  ML Win Prob: {ml_win_prob:.1%} will be used instead")
                else:
                    logger.info(f"[ATHENA ORACLE INFO] Oracle advises SKIP_TODAY (informational only)")
                    logger.info(f"  Bot will use its own threshold: {self.config.min_win_probability:.1%}")

        # Validate win probability meets minimum threshold (using effective source)
        min_win_prob = self.config.min_win_probability
        logger.info(f"[ATHENA DECISION] Using {prediction_source} win probability: {effective_win_prob:.1%}")

        if effective_win_prob > 0 and effective_win_prob < min_win_prob:
            logger.info(f"[ATHENA TRADE BLOCKED] Win probability below threshold")
            logger.info(f"  {prediction_source} Win Prob: {effective_win_prob:.1%}")
            logger.info(f"  Minimum Required: {min_win_prob:.1%}")
            logger.info(f"  Shortfall: {(min_win_prob - effective_win_prob):.1%}")
            return None

        logger.info(f"[ATHENA PASSED] {prediction_source} Win Prob {effective_win_prob:.1%} >= {min_win_prob:.1%} minimum")

        # Step 4: Determine final direction
        # IMPROVED: Oracle with very high confidence can override wall direction
        direction = wall_direction
        direction_source = "WALL"

        # Check if Oracle should override wall direction
        # Oracle can override when: confidence >= 85% AND win_prob >= 60% AND direction is not FLAT
        oracle_override_threshold = 0.85
        oracle_win_prob_threshold = 0.60

        if oracle and oracle_direction != 'FLAT':
            if oracle_confidence >= oracle_override_threshold and oracle_win_prob >= oracle_win_prob_threshold:
                if oracle_direction != wall_direction:
                    logger.info(f"[ATHENA ORACLE OVERRIDE] Oracle overriding wall direction!")
                    logger.info(f"  Wall Direction: {wall_direction}")
                    logger.info(f"  Oracle Direction: {oracle_direction}")
                    logger.info(f"  Oracle Confidence: {oracle_confidence:.0%} (threshold: {oracle_override_threshold:.0%})")
                    logger.info(f"  Oracle Win Prob: {oracle_win_prob:.0%} (threshold: {oracle_win_prob_threshold:.0%})")
                    direction = oracle_direction
                    direction_source = "ORACLE_OVERRIDE"

        # Calculate confidence based on direction source
        if direction_source == "ORACLE_OVERRIDE":
            # Higher base confidence when Oracle is driving the direction
            confidence = 0.75 + (oracle_confidence - oracle_override_threshold) * 0.5  # 0.75 to 0.825
            confidence = min(0.95, confidence)
            logger.info(f"Using Oracle-driven confidence: {confidence:.0%}")
        else:
            # Wall-based confidence (original logic)
            confidence = 0.7  # Base confidence from wall proximity

        # ML can boost or reduce confidence
        if ml_signal:
            if ml_direction == direction:
                confidence = min(0.95, confidence + ml_confidence * 0.20)
            elif ml_direction and ml_direction != direction and ml_confidence > 0.7:
                # Penalty when ML disagrees
                confidence -= 0.10

        # ============================================================
        # GEX DIRECTIONAL ML - Additional direction confirmation layer
        # Trained XGBoost model predicts BULLISH/BEARISH/FLAT from GEX structure
        # ============================================================
        gex_dir_prediction = self.get_gex_directional_prediction(gex_data, vix)
        if gex_dir_prediction:
            gex_dir = gex_dir_prediction.get('direction', 'FLAT')
            gex_dir_conf = gex_dir_prediction.get('confidence', 0)

            logger.info(f"[ATHENA GEX DIRECTIONAL ML] Direction: {gex_dir}, Confidence: {gex_dir_conf:.1%}")

            # Map GEX direction to ATHENA direction
            gex_direction_map = {'BULLISH': 'BULLISH', 'BEARISH': 'BEARISH', 'FLAT': None}
            mapped_gex_dir = gex_direction_map.get(gex_dir)

            if mapped_gex_dir == direction and gex_dir_conf > 0.6:
                # GEX Directional ML confirms direction - boost confidence
                boost = gex_dir_conf * 0.15  # Up to 15% boost
                confidence = min(0.95, confidence + boost)
                logger.info(f"[GEX DIR ML CONFIRMS] {gex_dir} matches {direction} (+{boost:.1%} confidence)")
            elif mapped_gex_dir and mapped_gex_dir != direction and gex_dir_conf > 0.7:
                # GEX Directional ML disagrees strongly - reduce confidence
                penalty = (gex_dir_conf - 0.7) * 0.20  # Up to 6% penalty
                confidence -= penalty
                logger.info(f"[GEX DIR ML DISAGREES] {gex_dir} vs {direction} (-{penalty:.1%} confidence)")

        # Oracle adjustments (when not overriding)
        if oracle and direction_source != "ORACLE_OVERRIDE":
            if oracle_direction == direction and oracle_confidence > 0.6:
                # Oracle confirms wall direction - boost confidence more significantly
                boost = oracle_confidence * 0.20  # Increased from 0.15
                confidence = min(0.95, confidence + boost)
                logger.info(f"Oracle confirms direction {direction} with {oracle_confidence:.0%} confidence (+{boost:.0%})")
            elif oracle_direction != direction and oracle_direction != 'FLAT' and oracle_confidence > 0.6:
                # Oracle disagrees - scale penalty by Oracle's confidence
                penalty = (oracle_confidence - 0.6) * 0.25  # 0% to 10% penalty
                confidence -= penalty
                logger.info(f"Oracle disagrees: {oracle_direction} vs wall {direction} (-{penalty:.0%})")
            # NOTE: Oracle SKIP_TODAY is informational only - ML win prob takes precedence
            # See earlier logic at line 544-551 - bot uses its own min_win_probability threshold

            # APPLY top_factors to adjust confidence based on current conditions
            if oracle.get('top_factors'):
                confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                    confidence, oracle['top_factors'], gex_data
                )

        # Lower threshold since wall proximity is the core strategy
        if confidence < 0.45:
            logger.info(f"Confidence too low: {confidence:.2f}")
            return None

        # Step 5: Determine spread type
        spread_type = SpreadType.BULL_CALL if direction == "BULLISH" else SpreadType.BEAR_PUT

        # Step 6: Calculate strikes
        # Get expiration (0DTE)
        now = datetime.now(CENTRAL_TZ)
        expiration = now.strftime("%Y-%m-%d")

        long_strike, short_strike = self.calculate_spread_strikes(
            direction, spot_price, expiration
        )

        # Step 7: Estimate pricing
        debit, max_profit, max_loss = self.estimate_spread_pricing(
            spread_type, long_strike, short_strike, spot_price, vix
        )

        # Step 8: Calculate risk/reward
        rr_ratio = max_profit / max_loss if max_loss > 0 else 0

        if rr_ratio < self.config.min_rr_ratio:
            logger.info(f"R:R ratio {rr_ratio:.2f} below minimum {self.config.min_rr_ratio}")
            return None

        # Step 9: Build detailed reasoning (FULL audit trail)
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

        # Determine source based on what's available
        if oracle and ml_signal:
            source = "GEX_ML_ORACLE"
        elif oracle:
            source = "GEX_ORACLE"
        elif ml_signal:
            source = "GEX_ML"
        else:
            source = "GEX_WALL"

        # Convert Oracle top_factors to JSON string for storage
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
            # Kronos context
            flip_point=gex_data.get('flip_point', 0),
            net_gex=gex_data.get('net_gex', 0),
            # Strikes
            long_strike=long_strike,
            short_strike=short_strike,
            expiration=expiration,
            # Pricing
            estimated_debit=debit,
            max_profit=max_profit,
            max_loss=max_loss,
            rr_ratio=rr_ratio,
            # Source and reasoning
            source=source,
            reasoning=reasoning,
            # ML context (for audit)
            ml_model_name=ml_signal.get('model_name', '') if ml_signal else '',
            ml_win_probability=ml_signal.get('win_probability', 0) if ml_signal else 0,
            ml_top_features='',  # Could extract from model if available
            # Oracle context (for audit)
            oracle_win_probability=oracle_win_prob,
            oracle_advice=oracle.get('advice', '') if oracle else '',
            oracle_direction=oracle_direction,
            oracle_confidence=oracle_confidence,
            oracle_top_factors=oracle_top_factors_json,
            # Wall context
            wall_type=wall_type,
            wall_distance_pct=wall_distance,
        )

        logger.info(f"Signal generated: {direction} {spread_type.value} @ {spot_price}")
        logger.info(f"Context: Wall={wall_type} ({wall_distance:.2f}%), ML={ml_direction or 'N/A'} ({ml_confidence:.0%}), Oracle={oracle_direction or 'N/A'} ({oracle_confidence:.0%})")
        return signal
