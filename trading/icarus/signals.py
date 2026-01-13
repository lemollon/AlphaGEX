"""
ICARUS - Signal Generation
===========================

Clean signal generation using GEX data, Oracle, and ML models.

ICARUS uses AGGRESSIVE Apache GEX backtest parameters (vs ATHENA):
- 2% wall filter (vs 1%) - more room to trade
- 48% min win probability (vs 55%) - lower threshold
- VIX range 12-30 (vs 15-25) - wider volatility range
- GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed
- Uses Tradier LIVE GEX data only (no stale Kronos)

Safety filters ARE ENABLED with aggressive thresholds.
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

# ML Regime Classifier - replaces hard-coded GEX thresholds with learned models
ML_REGIME_AVAILABLE = False
try:
    from quant.ml_regime_classifier import MLRegimeClassifier, MLPrediction as RegimePrediction, MLRegimeAction
    ML_REGIME_AVAILABLE = True
except ImportError:
    MLRegimeClassifier = None
    RegimePrediction = None
    MLRegimeAction = None

# IV Solver - accurate implied volatility calculation
IV_SOLVER_AVAILABLE = False
try:
    from quant.iv_solver import IVSolver, calculate_iv_from_price
    IV_SOLVER_AVAILABLE = True
except ImportError:
    IVSolver = None
    calculate_iv_from_price = None

# Walk-Forward Optimizer - parameter validation
WALK_FORWARD_AVAILABLE = False
try:
    from quant.walk_forward_optimizer import WalkForwardOptimizer, WalkForwardResult
    WALK_FORWARD_AVAILABLE = True
except ImportError:
    WalkForwardOptimizer = None
    WalkForwardResult = None


class SignalGenerator:
    """
    Generates trading signals from GEX data and ML models.

    ICARUS uses AGGRESSIVE Apache GEX backtest parameters (vs ATHENA):
    - 2% wall_filter_pct (vs 1%) - more room to trade
    - 48% min_win_probability (vs 55%) - lower threshold
    - 1.2 min_rr_ratio (vs 1.5) - accept slightly lower R:R
    - VIX range 12-30 (vs 15-25) - wider range
    - GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed

    Safety filters ARE ENABLED with aggressive thresholds.
    """

    def __init__(self, config: ICARUSConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator - Use Tradier for LIVE data (Kronos is for backtesting only)
        self.gex_calculator = None

        if TRADIER_GEX_AVAILABLE:
            try:
                tradier_calc = get_gex_calculator()
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"ICARUS: Using Tradier GEX (live spot={test_result.get('spot_price')})")
                else:
                    logger.error("ICARUS: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"ICARUS: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("ICARUS: NO GEX CALCULATOR AVAILABLE - Tradier required for live trading")

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

        # GEX Directional ML - predicts BULLISH/BEARISH/FLAT from GEX structure
        self.gex_directional_ml = None
        if GEX_DIRECTIONAL_ML_AVAILABLE:
            try:
                self.gex_directional_ml = GEXDirectionalPredictor()
                if hasattr(self.gex_directional_ml, 'load_model'):
                    self.gex_directional_ml.load_model()
                logger.info("ICARUS SignalGenerator: GEX Directional ML initialized")
            except Exception as e:
                logger.warning(f"GEX Directional ML init failed: {e}")

        # ML Regime Classifier - replaces hard-coded GEX thresholds
        self.ml_regime_classifier = None
        if ML_REGIME_AVAILABLE and MLRegimeClassifier:
            try:
                self.ml_regime_classifier = MLRegimeClassifier(symbol=self.config.ticker)
                logger.info("ICARUS SignalGenerator: ML Regime Classifier initialized")
            except Exception as e:
                logger.debug(f"ML Regime Classifier init failed: {e}")

    def get_gex_directional_prediction(self, gex_data: Dict, vix: float = 20.0) -> Optional[Dict]:
        """
        Get GEX Directional ML prediction (BULLISH/BEARISH/FLAT).

        Uses trained XGBoost model to predict market direction from GEX structure.
        """
        if not self.gex_directional_ml:
            return None

        try:
            prediction = self.gex_directional_ml.predict(gex_data, vix)

            if prediction:
                result = {
                    'direction': prediction.direction.value,
                    'confidence': prediction.confidence,
                    'probabilities': prediction.probabilities,
                    'model_name': 'GEX_DIRECTIONAL_ML',
                }

                logger.info(f"[ICARUS GEX DIRECTIONAL ML] Direction: {prediction.direction.value}, "
                           f"Confidence: {prediction.confidence:.1%}")

                return result

        except Exception as e:
            logger.debug(f"GEX Directional ML prediction error: {e}")

        return None

    def get_ml_regime_prediction(self, gex_data: Dict, direction: str = None) -> Optional[Dict]:
        """
        Get ML Regime Classifier prediction for market action.

        For Directional Bots (ICARUS):
        - BUY_CALLS aligns with BULLISH direction = boost confidence
        - BUY_PUTS aligns with BEARISH direction = boost confidence
        - SELL_PREMIUM/STAY_FLAT suggests rangebound = reduce directional confidence
        """
        if not self.ml_regime_classifier:
            return None

        try:
            from datetime import datetime
            now = datetime.now()

            gex_normalized = gex_data.get('net_gex', 0) / 1e9 if gex_data.get('net_gex', 0) != 0 else 1.0
            vix = gex_data.get('vix', 20.0)
            spot = gex_data.get('spot_price', 0)
            flip_point = gex_data.get('flip_point', spot)
            distance_to_flip = ((spot - flip_point) / spot * 100) if spot > 0 else 0

            prediction = self.ml_regime_classifier.predict(
                gex_normalized=gex_normalized,
                gex_percentile=50.0,
                gex_change_1d=0.0,
                gex_change_5d=0.0,
                vix=vix,
                vix_percentile=50.0,
                vix_change_1d=0.0,
                iv_rank=50.0,
                iv_hv_ratio=1.1,
                distance_to_flip=distance_to_flip,
                momentum_1h=0.0,
                momentum_4h=0.0,
                above_20ma=True,
                above_50ma=True,
                regime_duration=1,
                day_of_week=now.weekday(),
                days_to_opex=0
            )

            if prediction:
                return {
                    'action': prediction.predicted_action.value if hasattr(prediction.predicted_action, 'value') else str(prediction.predicted_action),
                    'confidence': prediction.confidence,
                    'probabilities': prediction.probabilities,
                    'is_trained': prediction.is_trained,
                    'aligns_with_direction': direction and (
                        (direction == 'BULLISH' and str(prediction.predicted_action.value) == 'BUY_CALLS') or
                        (direction == 'BEARISH' and str(prediction.predicted_action.value) == 'BUY_PUTS')
                    )
                }
        except Exception as e:
            logger.debug(f"ML Regime Classifier prediction failed: {e}")

        return None

    def get_ensemble_boost(self, gex_data: Dict, direction: str, oracle: Dict = None) -> Dict:
        """
        Get ensemble signal boost/confirmation for directional spreads.
        """
        if not ENSEMBLE_AVAILABLE:
            return {'boost': 1.0, 'should_trade': True, 'confidence': 0.7, 'reasoning': 'Ensemble not available'}

        try:
            action = 'BUY_CALLS' if direction == 'BULLISH' else 'BUY_PUTS'

            gex_signal = {
                'recommended_action': action,
                'confidence': 70,
                'reasoning': f"Wall direction: {direction}"
            }

            current_regime = gex_data.get('gex_regime', 'UNKNOWN')
            if current_regime == 'POSITIVE':
                current_regime = 'POSITIVE_GAMMA'
            elif current_regime == 'NEGATIVE':
                current_regime = 'NEGATIVE_GAMMA'

            ensemble = get_ensemble_signal(
                symbol=self.config.ticker,
                gex_data=gex_signal,
                ml_prediction=None,
                current_regime=current_regime
            )

            if ensemble:
                logger.info(f"[ICARUS ENSEMBLE] Confidence: {ensemble.confidence:.0f}%, Size: {ensemble.position_size_multiplier:.0%}")
                return {
                    'boost': ensemble.position_size_multiplier,
                    'should_trade': ensemble.should_trade,
                    'confidence': ensemble.confidence / 100,
                    'reasoning': ensemble.reasoning
                }

        except Exception as e:
            logger.debug(f"Ensemble signal error: {e}")

        return {'boost': 1.0, 'should_trade': True, 'confidence': 0.7, 'reasoning': 'Ensemble fallback'}

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

            # Get spot price - try GEX calculator first, then data provider fallback
            spot = gex.get('spot_price', gex.get('underlying_price', 0))
            if not spot or spot <= 0:
                # Fallback to data provider if GEX calculator didn't return spot
                if DATA_PROVIDER_AVAILABLE:
                    spot = get_price(self.config.ticker)
                    if spot and spot > 0:
                        logger.debug(f"Using spot price from data provider fallback: ${spot:.2f}")
                if not spot or spot <= 0:
                    logger.warning("Could not get spot price from GEX calculator or data provider")
                    return None

            # Get VIX
            vix = 20.0
            if DATA_PROVIDER_AVAILABLE:
                try:
                    vix = get_vix() or 20.0
                except Exception:
                    pass

            return {
                'spot_price': spot,
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

        # Validate required market data before calling Oracle
        spot_price = gex_data.get('spot_price', 0)
        if not spot_price or spot_price <= 0:
            logger.debug("ICARUS Oracle skipped: No valid spot price available")
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'NO_DATA',
                'direction': 'FLAT',
                'top_factors': [],
                'reasoning': 'No valid spot price available for Oracle analysis',
            }

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
            import traceback
            traceback.print_exc()
            # Return fallback values instead of None so scan activity shows meaningful data
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'ERROR',
                'direction': 'FLAT',
                'top_factors': [{'factor': 'error', 'impact': 0}],
                'reasoning': f"Oracle error: {str(e)[:100]}",
            }

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

        ICARUS uses 2% wall filter (vs ATHENA's 1%) - more aggressive but still filtered.

        Returns: (is_valid, direction, reason)
        """
        spot = gex_data['spot_price']
        call_wall = gex_data['call_wall']
        put_wall = gex_data['put_wall']

        if not spot or not call_wall or not put_wall:
            return False, "", "Missing price/wall data"

        # Calculate distances (as percentages, always positive)
        dist_to_put_wall_pct = abs((spot - put_wall) / spot) * 100
        dist_to_call_wall_pct = abs((call_wall - spot) / spot) * 100

        # ICARUS uses 2% threshold (vs ATHENA's 1%) - more aggressive but still filtered
        threshold = self.config.wall_filter_pct

        # Check which wall is within threshold
        near_put = dist_to_put_wall_pct <= threshold
        near_call = dist_to_call_wall_pct <= threshold

        # If both walls are within threshold, use the CLOSER one
        if near_put and near_call:
            if dist_to_put_wall_pct <= dist_to_call_wall_pct:
                return True, "BULLISH", f"Closer to put wall ({dist_to_put_wall_pct:.2f}% vs call {dist_to_call_wall_pct:.2f}%)"
            else:
                return True, "BEARISH", f"Closer to call wall ({dist_to_call_wall_pct:.2f}% vs put {dist_to_put_wall_pct:.2f}%)"

        # Near put wall = bullish (support bounce)
        if near_put:
            return True, "BULLISH", f"Within {threshold}% of put wall (support)"

        # Near call wall = bearish (resistance rejection)
        if near_call:
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

        # VIX filter - aggressive range (12-30 vs ATHENA's 15-25)
        if vix < self.config.min_vix:
            logger.info(f"[ICARUS SKIP] VIX {vix:.1f} below minimum {self.config.min_vix} (no premium)")
            return None
        if vix > self.config.max_vix:
            logger.info(f"[ICARUS SKIP] VIX {vix:.1f} above maximum {self.config.max_vix} (too volatile)")
            return None
        logger.info(f"[ICARUS] VIX {vix:.1f} in range [{self.config.min_vix}-{self.config.max_vix}] ✓")

        # Wall proximity check - BLOCKING (aggressive 2% threshold)
        near_wall, wall_direction, wall_reason = self.check_wall_proximity(gex_data)
        if not near_wall:
            logger.info(f"[ICARUS SKIP] {wall_reason} - not near GEX wall")
            return None
        logger.info(f"[ICARUS] Wall proximity: {wall_reason} ✓")

        # GEX Ratio Asymmetry Check (aggressive thresholds: 1.3/0.77)
        total_put_gex = gex_data.get('put_gex', gex_data.get('kronos_raw', {}).get('total_put_gex', 0))
        total_call_gex = gex_data.get('call_gex', gex_data.get('kronos_raw', {}).get('total_call_gex', 0))
        gex_ratio = total_put_gex / total_call_gex if total_call_gex > 0 else 10.0

        # Check if GEX ratio shows directional asymmetry (more relaxed than ATHENA)
        has_gex_asymmetry = (gex_ratio >= self.config.min_gex_ratio_bearish or
                             gex_ratio <= self.config.max_gex_ratio_bullish)
        if not has_gex_asymmetry:
            logger.info(f"[ICARUS SKIP] GEX ratio {gex_ratio:.2f} not asymmetric enough "
                       f"(need >{self.config.min_gex_ratio_bearish} bearish or <{self.config.max_gex_ratio_bullish} bullish)")
            return None
        gex_bias = "BEARISH" if gex_ratio >= self.config.min_gex_ratio_bearish else "BULLISH"
        logger.info(f"[ICARUS] GEX ratio {gex_ratio:.2f} shows {gex_bias} asymmetry ✓")

        # Step 3: Get ML signal from 5 GEX probability models (PREFERRED SOURCE)
        # ICARUS is AGGRESSIVE - ML models backtested with high win rates take precedence
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
        # ICARUS: ML MODEL TAKES PRECEDENCE OVER ORACLE
        # ICARUS is aggressive - trusts ML models with 40% threshold
        # Oracle's conservative 55% threshold is ignored
        # ============================================================

        use_ml_prediction = ml_signal is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        prediction_source = "ML_5_MODEL_ENSEMBLE" if use_ml_prediction else "ORACLE"

        # CRITICAL FALLBACK: If neither ML nor Oracle provides a win probability,
        # use market-conditions-based baseline. ICARUS is aggressive so lower threshold.
        if effective_win_prob <= 0:
            gex_regime = gex_data.get('gex_regime', 'NEUTRAL')
            baseline = 0.52  # ICARUS is aggressive - lower baseline

            vix = gex_data.get('vix', 20)
            if vix < 15:
                baseline += 0.05
            elif vix > 30:
                baseline -= 0.08
            elif vix > 25:
                baseline -= 0.04

            if gex_regime in ('POSITIVE', 'NEGATIVE'):
                baseline += 0.03  # Either direction works for directional

            effective_win_prob = max(0.48, min(0.65, baseline))
            prediction_source = "MARKET_CONDITIONS_FALLBACK"
            logger.info(f"[ICARUS FALLBACK] No ML/Oracle prediction - using market baseline: {effective_win_prob:.1%}")

        # Log ML analysis FIRST (it's the preferred source for ICARUS)
        if ml_signal:
            logger.info(f"[ICARUS ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
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
            logger.info(f"[ICARUS] ML models not available, falling back to Oracle")

        # Log Oracle analysis (backup source)
        if oracle:
            logger.info(f"[ICARUS ORACLE ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
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

            # Oracle SKIP_TODAY is informational only - ICARUS trusts ML
            if oracle.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[ICARUS] Oracle advises SKIP_TODAY but ML override active")
                    logger.info(f"  ICARUS trusts ML: {ml_win_prob:.1%} win probability")
                else:
                    logger.info(f"[ICARUS] Oracle SKIP_TODAY - using aggressive 48% threshold")

        # Win probability threshold check - aggressive 48% (vs ATHENA's 55%)
        logger.info(f"[ICARUS DECISION] Using {prediction_source} win probability: {effective_win_prob:.1%}")
        if effective_win_prob < self.config.min_win_probability:
            logger.info(f"[ICARUS SKIP] Win probability {effective_win_prob:.1%} below minimum {self.config.min_win_probability:.0%}")
            return None
        logger.info(f"[ICARUS] Win probability {effective_win_prob:.1%} >= {self.config.min_win_probability:.0%} ✓")

        # Step 4: Determine final direction
        direction = wall_direction
        direction_source = "WALL"

        # Check if Oracle should override wall direction
        # RAISED from 85%/60% to 90%/70% - GEX walls are PRIMARY, Oracle override should be rare
        oracle_override_threshold = 0.90
        oracle_win_prob_threshold = 0.70

        if oracle and oracle_direction != 'FLAT':
            if oracle_confidence >= oracle_override_threshold and oracle_win_prob >= oracle_win_prob_threshold:
                if oracle_direction != wall_direction:
                    logger.info(f"[ICARUS ORACLE OVERRIDE] Oracle overriding wall direction!")
                    logger.info(f"  Wall Direction: {wall_direction}")
                    logger.info(f"  Oracle Direction: {oracle_direction}")
                    logger.info(f"  Oracle Confidence: {oracle_confidence:.0%} (threshold: {oracle_override_threshold:.0%})")
                    logger.info(f"  Oracle Win Prob: {oracle_win_prob:.0%} (threshold: {oracle_win_prob_threshold:.0%})")
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

        # ============================================================
        # GEX DIRECTIONAL ML - Additional direction confirmation layer
        # Trained XGBoost model predicts BULLISH/BEARISH/FLAT from GEX structure
        # ============================================================
        gex_dir_prediction = self.get_gex_directional_prediction(gex_data, vix)
        if gex_dir_prediction:
            gex_dir = gex_dir_prediction.get('direction', 'FLAT')
            gex_dir_conf = gex_dir_prediction.get('confidence', 0)

            logger.info(f"[ICARUS GEX DIRECTIONAL ML] Direction: {gex_dir}, Confidence: {gex_dir_conf:.1%}")

            # Map GEX direction to ICARUS direction
            gex_direction_map = {'BULLISH': 'BULLISH', 'BEARISH': 'BEARISH', 'FLAT': None}
            mapped_gex_dir = gex_direction_map.get(gex_dir)

            if mapped_gex_dir == direction and gex_dir_conf > 0.6:
                # GEX Directional ML confirms direction - boost confidence
                boost = gex_dir_conf * 0.15
                confidence = min(0.95, confidence + boost)
                logger.info(f"[GEX DIR ML CONFIRMS] {gex_dir} matches {direction} (+{boost:.1%} confidence)")
            elif mapped_gex_dir and mapped_gex_dir != direction and gex_dir_conf > 0.7:
                # GEX Directional ML disagrees strongly - reduce confidence (smaller for aggressive ICARUS)
                penalty = (gex_dir_conf - 0.7) * 0.15
                confidence -= penalty
                logger.info(f"[GEX DIR ML DISAGREES] {gex_dir} vs {direction} (-{penalty:.1%} confidence)")

        # ML Regime Classifier - Learned market regime detection
        regime_prediction = self.get_ml_regime_prediction(gex_data, direction)
        if regime_prediction:
            regime_action = regime_prediction.get('action', 'STAY_FLAT')
            regime_conf = regime_prediction.get('confidence', 50) / 100.0
            aligns = regime_prediction.get('aligns_with_direction', False)

            logger.info(f"[ICARUS ML REGIME] Action: {regime_action}, Confidence: {regime_conf:.1%}, Aligns: {aligns}")

            if aligns and regime_conf > 0.60:
                # ML Regime aligns with directional signal - boost confidence
                boost = min(0.10, (regime_conf - 0.60) * 0.25)
                confidence = min(0.95, confidence + boost)
                logger.info(f"  Regime aligns with {direction} (+{boost:.1%} confidence)")
            elif regime_action in ('SELL_PREMIUM', 'STAY_FLAT') and regime_conf > 0.70:
                # ML thinks market is rangebound - reduce directional confidence (smaller for aggressive ICARUS)
                penalty = (regime_conf - 0.70) * 0.10
                confidence = max(0.40, confidence - penalty)
                logger.info(f"  Regime suggests rangebound (-{penalty:.1%} confidence)")

        # Ensemble Strategy - Position sizing info only (Oracle decides trades)
        # ORACLE IS THE GOD OF ALL TRADE DECISIONS - Ensemble cannot block
        ensemble_result = self.get_ensemble_boost(gex_data, direction, oracle)
        if ensemble_result:
            should_trade = ensemble_result.get('should_trade', True)
            logger.info(f"[ICARUS ENSEMBLE] Info: should_trade={should_trade} (NOT blocking, Oracle decides)")

        # Oracle adjustments (when not overriding)
        if oracle and direction_source != "ORACLE_OVERRIDE":
            if oracle_direction == direction and oracle_confidence > 0.6:
                boost = oracle_confidence * 0.20
                confidence = min(0.95, confidence + boost)
            elif oracle_direction != direction and oracle_direction != 'FLAT' and oracle_confidence > 0.6:
                penalty = (oracle_confidence - 0.6) * 0.20  # Smaller penalty
                confidence -= penalty
            # NOTE: SKIP_TODAY does NOT block here - bot uses its own min_win_probability threshold

            if oracle.get('top_factors'):
                confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                    confidence, oracle['top_factors'], gex_data
                )

        # Confidence check (ORACLE IS GOD - no blocking, info only)
        if confidence < self.config.min_confidence:
            logger.warning(f"[ICARUS] Confidence {confidence:.0%} below {self.config.min_confidence:.0%} - PROCEEDING (Oracle approved)")
        else:
            logger.info(f"[ICARUS] Confidence {confidence:.0%} >= {self.config.min_confidence:.0%} ✓")

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

        # Step 8: Calculate risk/reward (1.2 min for ICARUS vs ATHENA's 1.5)
        rr_ratio = max_profit / max_loss if max_loss > 0 else 0

        if rr_ratio < self.config.min_rr_ratio:
            logger.warning(f"[ICARUS] R:R ratio {rr_ratio:.2f} below {self.config.min_rr_ratio} - PROCEEDING (Oracle approved)")
        else:
            logger.info(f"[ICARUS] R:R ratio {rr_ratio:.2f} >= {self.config.min_rr_ratio} ✓")

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
