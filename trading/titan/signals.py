"""
TITAN - Signal Generation
===========================

Signal generation for aggressive SPX Iron Condors.
Uses closer strikes (0.8 SD) and relaxed thresholds.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

from .models import IronCondorSignal, TITANConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Optional imports
try:
    from quant.oracle_advisor import OracleAdvisor
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    OracleAdvisor = None

try:
    from quant.ares_ml_advisor import AresMLAdvisor
    ARES_ML_AVAILABLE = True
except ImportError:
    ARES_ML_AVAILABLE = False
    AresMLAdvisor = None

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

# GEX Directional ML - predicts BULLISH/BEARISH/FLAT from GEX structure
GEX_DIRECTIONAL_ML_AVAILABLE = False
try:
    from quant.gex_directional_ml import GEXDirectionalPredictor, Direction, DirectionalPrediction
    GEX_DIRECTIONAL_ML_AVAILABLE = True
except ImportError:
    GEXDirectionalPredictor = None
    Direction = None
    DirectionalPrediction = None


class SignalGenerator:
    """Generates aggressive SPX Iron Condor signals for TITAN"""

    def __init__(self, config: TITANConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        # GEX Calculator - Try Kronos first, but VERIFY it has FRESH data
        self.gex_calculator = None
        kronos_works = False

        if KRONOS_AVAILABLE:
            try:
                kronos_calc = KronosGEXCalculator()
                test_result = kronos_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    # Check data freshness - reject if older than 2 days
                    trade_date = test_result.get('trade_date', '')
                    if trade_date:
                        from datetime import datetime
                        try:
                            data_date = datetime.strptime(trade_date, '%Y-%m-%d')
                            days_old = (datetime.now() - data_date).days
                            if days_old <= 2:
                                self.gex_calculator = kronos_calc
                                kronos_works = True
                                logger.info(f"TITAN: Kronos GEX verified (spot={test_result.get('spot_price')}, date={trade_date})")
                            else:
                                logger.warning(f"TITAN: Kronos data too stale ({days_old} days old) - using Tradier")
                        except ValueError:
                            logger.warning("TITAN: Kronos has invalid trade_date - using Tradier")
                    else:
                        logger.warning("TITAN: Kronos returned no trade_date - using Tradier")
                else:
                    logger.warning("TITAN: Kronos returned no data - using Tradier")
            except Exception as e:
                logger.warning(f"TITAN: Kronos GEX init/test failed: {e}")

        if not kronos_works and TRADIER_GEX_AVAILABLE:
            try:
                # CRITICAL: SPX requires production API (sandbox doesn't support SPX)
                from data.gex_calculator import TradierGEXCalculator
                tradier_calc = TradierGEXCalculator(sandbox=False)
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"TITAN: Using Tradier GEX PRODUCTION (live spot={test_result.get('spot_price')})")
                else:
                    logger.error("TITAN: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"TITAN: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("TITAN: NO GEX CALCULATOR AVAILABLE")

        # ARES ML Advisor (PRIMARY - Iron Condor ML with ~70% win rate)
        self.ares_ml = None
        if ARES_ML_AVAILABLE:
            try:
                self.ares_ml = AresMLAdvisor()
                if self.ares_ml.is_trained:
                    logger.info(f"TITAN: ML Advisor v{self.ares_ml.model_version} loaded (PRIMARY)")
                else:
                    logger.info("TITAN: ML Advisor initialized (not yet trained)")
            except Exception as e:
                logger.warning(f"TITAN: ML Advisor init failed: {e}")

        # Oracle (BACKUP - used when ML not available)
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("TITAN: Oracle initialized (BACKUP)")
            except Exception as e:
                logger.warning(f"TITAN: Oracle init failed: {e}")

        # GEX Directional ML - predicts market direction from GEX structure
        self.gex_directional_ml = None
        if GEX_DIRECTIONAL_ML_AVAILABLE:
            try:
                self.gex_directional_ml = GEXDirectionalPredictor()
                logger.info("TITAN: GEX Directional ML initialized")
            except Exception as e:
                logger.debug(f"TITAN: GEX Directional ML init failed: {e}")

        # ML Regime Classifier - replaces hard-coded GEX thresholds
        self.ml_regime_classifier = None
        if ML_REGIME_AVAILABLE and MLRegimeClassifier:
            try:
                self.ml_regime_classifier = MLRegimeClassifier(symbol="SPX")
                logger.info("TITAN: ML Regime Classifier initialized")
            except Exception as e:
                logger.debug(f"TITAN: ML Regime Classifier init failed: {e}")

    def get_gex_directional_prediction(self, gex_data: Dict, vix: float = None) -> Optional[Dict]:
        """
        Get GEX Directional ML prediction for market direction.

        For Iron Condors: Strong directional signal suggests caution.
        """
        if not self.gex_directional_ml:
            return None

        try:
            prediction = self.gex_directional_ml.predict(
                net_gex=gex_data.get('net_gex', 0),
                call_wall=gex_data.get('major_pos_vol_level', 0),
                put_wall=gex_data.get('major_neg_vol_level', 0),
                flip_point=gex_data.get('flip_point', 0),
                spot_price=gex_data.get('spot_price', 0),
                vix=vix or 20.0
            )

            if prediction:
                return {
                    'direction': prediction.direction.value if hasattr(prediction.direction, 'value') else str(prediction.direction),
                    'confidence': prediction.confidence,
                    'probabilities': prediction.probabilities if hasattr(prediction, 'probabilities') else {}
                }
        except Exception as e:
            logger.debug(f"GEX Directional ML prediction failed: {e}")

        return None

    def get_ml_regime_prediction(self, gex_data: Dict, market_data: Dict) -> Optional[Dict]:
        """
        Get ML Regime Classifier prediction for market action.

        For Iron Condors:
        - SELL_PREMIUM = ideal, boost confidence
        - BUY_CALLS/BUY_PUTS = directional, reduce IC confidence
        - STAY_FLAT = neutral, slight boost
        """
        if not self.ml_regime_classifier:
            return None

        try:
            from datetime import datetime
            now = datetime.now()

            gex_normalized = gex_data.get('net_gex', 0) / 1e9 if gex_data.get('net_gex', 0) != 0 else 1.0
            vix = market_data.get('vix', 20.0)
            spot = market_data.get('spot_price', 0)
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
                iv_rank=market_data.get('iv_rank', 50.0),
                iv_hv_ratio=1.1,
                distance_to_flip=distance_to_flip,
                momentum_1h=0.0,
                momentum_4h=0.0,
                above_20ma=True,
                above_50ma=True,
                regime_duration=1,
                day_of_week=now.weekday(),
                days_to_opex=market_data.get('days_to_expiry', 0)
            )

            if prediction:
                return {
                    'action': prediction.predicted_action.value if hasattr(prediction.predicted_action, 'value') else str(prediction.predicted_action),
                    'confidence': prediction.confidence,
                    'probabilities': prediction.probabilities,
                    'is_trained': prediction.is_trained
                }
        except Exception as e:
            logger.debug(f"ML Regime Classifier prediction failed: {e}")

        return None

    def get_ensemble_boost(self, market_data: Dict, ml_prediction: Dict = None, oracle: Dict = None) -> Dict:
        """
        Get ensemble signal boost/confirmation for Iron Condor.
        """
        if not ENSEMBLE_AVAILABLE:
            return {'boost': 1.0, 'should_trade': True, 'confidence': 0.7, 'reasoning': 'Ensemble not available'}

        try:
            gex_data = {
                'recommended_action': 'SELL_IC',
                'confidence': 70,
                'reasoning': f"VIX={market_data.get('vix', 20):.1f}, EM=${market_data.get('expected_move', 0):.0f}"
            }

            ml_data = None
            if ml_prediction:
                ml_data = {
                    'predicted_action': 'SELL_IC',
                    'confidence': ml_prediction.get('confidence', 0) * 100,
                    'is_trained': True
                }

            current_regime = market_data.get('gex_regime', 'UNKNOWN')
            if current_regime == 'POSITIVE':
                current_regime = 'POSITIVE_GAMMA'
            elif current_regime == 'NEGATIVE':
                current_regime = 'NEGATIVE_GAMMA'

            ensemble = get_ensemble_signal(
                symbol="SPX",
                gex_data=gex_data,
                ml_prediction=ml_data,
                current_regime=current_regime
            )

            if ensemble:
                logger.info(f"[TITAN ENSEMBLE] Confidence: {ensemble.confidence:.0f}%, Size: {ensemble.position_size_multiplier:.0%}")
                return {
                    'boost': ensemble.position_size_multiplier,
                    'should_trade': ensemble.should_trade,
                    'confidence': ensemble.confidence / 100,
                    'reasoning': ensemble.reasoning
                }

        except Exception as e:
            logger.debug(f"Ensemble signal error: {e}")

        return {'boost': 1.0, 'should_trade': True, 'confidence': 0.7, 'reasoning': 'Ensemble fallback'}

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
                    # CRITICAL: Include spot_price from GEX calculator (uses production API)
                    # This avoids calling get_price() which uses sandbox and fails for SPX
                    'spot_price': gex.get('spot_price', 0),
                }
        except Exception as e:
            logger.warning(f"GEX data fetch failed: {e}")
        return None

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current GEX data - PUBLIC method for trader.

        Returns dict with: spot_price, call_wall, put_wall, gex_regime, vix
        """
        gex = self._get_gex_data()
        if not gex:
            logger.warning("No GEX data available")
            return None

        try:
            # CRITICAL: Use spot_price from GEX calculator (uses production API for SPX)
            # The global get_price() uses sandbox which doesn't support SPX
            spot = gex.get('spot_price', 0)

            # Scale spot if from SPY (GEX calculator fell back to SPY)
            if gex.get('from_spy', False) and spot > 0 and spot < 1000:
                spot = spot * 10  # Scale SPY price to SPX equivalent

            # Fallback to get_price() only if GEX calc didn't return spot
            if not spot and DATA_AVAILABLE:
                spot = get_price("SPX")
                if not spot:
                    spy = get_price("SPY")
                    if spy:
                        spot = spy * 10

            # Get VIX
            vix = 20.0
            if DATA_AVAILABLE:
                try:
                    vix = get_vix() or 20.0
                except Exception:
                    pass

            # Scale walls if from SPY
            scale = 10 if gex.get('from_spy', False) else 1

            return {
                'spot_price': spot,
                'underlying_price': spot,
                'call_wall': gex.get('call_wall', 0) * scale,
                'put_wall': gex.get('put_wall', 0) * scale,
                'gex_regime': gex.get('regime', 'NEUTRAL'),
                'regime': gex.get('regime', 'NEUTRAL'),
                'net_gex': gex.get('net_gex', 0),
                'flip_point': gex.get('flip_point', 0) * scale,
                'vix': vix,
                'from_spy': gex.get('from_spy', False),
                'timestamp': datetime.now(CENTRAL_TZ),
            }
        except Exception as e:
            logger.error(f"GEX fetch error: {e}")
            return None

    def get_ml_prediction(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get prediction from ARES ML Advisor (PRIMARY source for Iron Condors).

        TITAN is aggressive - uses 40% win probability threshold.
        ML model trained on KRONOS backtests with ~70% win rate.
        """
        if not self.ares_ml:
            return None

        try:
            now = datetime.now(CENTRAL_TZ)
            day_of_week = now.weekday()

            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL').upper()
            gex_regime_positive = 1 if gex_regime_str == 'POSITIVE' else 0

            spot = market_data['spot_price']
            flip_point = market_data.get('flip_point', spot)
            gex_distance_to_flip_pct = abs(spot - flip_point) / spot * 100 if spot > 0 else 0

            put_wall = market_data.get('put_wall', spot * 0.98)
            call_wall = market_data.get('call_wall', spot * 1.02)
            gex_between_walls = 1 if put_wall <= spot <= call_wall else 0

            prediction = self.ares_ml.predict(
                vix=market_data['vix'],
                day_of_week=day_of_week,
                price=spot,
                price_change_1d=market_data.get('price_change_1d', 0),
                expected_move_pct=(market_data.get('expected_move', 0) / spot * 100) if spot > 0 else 1.0,
                win_rate_30d=0.70,
                vix_percentile_30d=50,
                vix_change_1d=0,
                gex_normalized=market_data.get('gex_normalized', 0),
                gex_regime_positive=gex_regime_positive,
                gex_distance_to_flip_pct=gex_distance_to_flip_pct,
                gex_between_walls=gex_between_walls,
            )

            if prediction:
                top_factors = []
                if hasattr(prediction, 'top_factors') and prediction.top_factors:
                    for factor_name, impact in prediction.top_factors:
                        top_factors.append({'factor': factor_name, 'impact': impact})

                return {
                    'win_probability': prediction.win_probability,
                    'confidence': prediction.confidence,
                    'advice': prediction.advice.value if prediction.advice else 'SKIP_TODAY',
                    'suggested_risk_pct': prediction.suggested_risk_pct,
                    'suggested_sd_multiplier': prediction.suggested_sd_multiplier,
                    'top_factors': top_factors,
                    'probabilities': prediction.probabilities,
                    'model_version': prediction.model_version,
                    'model_name': 'ARES_ML_ADVISOR',
                }
        except Exception as e:
            logger.warning(f"TITAN ML prediction error: {e}")

        return None

    def get_oracle_advice(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Oracle prediction with FULL context for audit trail (BACKUP SOURCE).

        TITAN uses relaxed thresholds but ML takes precedence.
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

            # Call PEGASUS-specific advice method (TITAN inherits SPX IC strategy)
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
            logger.warning(f"TITAN Oracle error: {e}")
            return None

    def _calculate_expected_move(self, spot: float, vix: float) -> float:
        """Calculate 1 SD expected move for SPX"""
        annual_factor = math.sqrt(252)
        daily_vol = (vix / 100) / annual_factor
        return round(spot * daily_vol, 2)

    def check_vix_filter(self, vix: float) -> Tuple[bool, str]:
        """VIX filter disabled - always allow trading"""
        return True, "VIX check disabled"

    def adjust_confidence_from_top_factors(
        self,
        confidence: float,
        top_factors: List[Dict],
        market_data: Dict
    ) -> Tuple[float, List[str]]:
        """
        Adjust confidence based on Oracle's top contributing factors.

        TITAN uses smaller adjustments since it's more aggressive.
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

        # 1. VIX factor adjustment - SMALLER penalties for TITAN
        vix_importance = factor_map.get('vix', factor_map.get('vix_level', 0))
        if vix_importance > 0.2:
            if vix > 30:  # Higher threshold than PEGASUS (25)
                penalty = min(0.05, (vix - 30) * 0.008)  # Smaller penalty
                confidence -= penalty
                adjustments.append(f"VIX factor high + VIX elevated ({vix:.1f}): -{penalty:.0%}")
            elif vix < 14:
                boost = min(0.06, (14 - vix) * 0.012)  # Slightly larger boost
                confidence += boost
                adjustments.append(f"VIX factor high + VIX low ({vix:.1f}): +{boost:.0%}")

        # 2. GEX regime factor adjustment - SMALLER penalties
        gex_importance = factor_map.get('gex_regime', factor_map.get('net_gex', 0))
        if gex_importance > 0.15:
            if gex_regime == 'NEGATIVE':
                penalty = 0.03  # Smaller penalty (PEGASUS: 0.06)
                confidence -= penalty
                adjustments.append(f"GEX factor high + NEGATIVE regime: -{penalty:.0%}")
            elif gex_regime == 'POSITIVE':
                boost = 0.05  # Slightly larger boost
                confidence += boost
                adjustments.append(f"GEX factor high + POSITIVE regime: +{boost:.0%}")

        # 3. Day of week factor - TITAN trades any day
        dow_importance = factor_map.get('day_of_week', 0)
        if dow_importance > 0.15:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            day = datetime.now(ZoneInfo("America/Chicago")).weekday()
            if day in [0, 1]:  # Monday, Tuesday
                boost = 0.04
                confidence += boost
                adjustments.append(f"Day factor high + favorable day: +{boost:.0%}")
            # No Friday penalty for TITAN - we trade every day

        # Clamp confidence to reasonable range - LOWER minimum for TITAN
        confidence = max(0.35, min(0.95, confidence))  # Lower min (PEGASUS: 0.4)

        if adjustments:
            logger.info(f"[TITAN TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
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
        """Calculate SPX strikes with $5 rounding - CLOSER strikes for TITAN

        Priority:
        1. Oracle suggested strikes (if provided and valid)
        2. GEX walls (if available)
        3. SD-based strikes (fallback) - uses 0.8 SD (vs PEGASUS 1.0)
        """
        sd = self.config.sd_multiplier  # 0.8 for TITAN (closer to spot)
        width = self.config.spread_width  # $12 for TITAN

        def round_to_5(x):
            return round(x / 5) * 5

        use_oracle = False
        use_gex = False

        # Priority 1: Oracle suggested strikes
        if oracle_put_strike and oracle_call_strike:
            put_dist = (spot - oracle_put_strike) / spot
            call_dist = (oracle_call_strike - spot) / spot
            # Slightly wider tolerance for TITAN
            if 0.003 <= put_dist <= 0.06 and 0.003 <= call_dist <= 0.06:
                put_short = round_to_5(oracle_put_strike)
                call_short = round_to_5(oracle_call_strike)
                use_oracle = True

        # Priority 2: GEX walls
        if not use_oracle and call_wall > 0 and put_wall > 0:
            put_short = round_to_5(put_wall)
            call_short = round_to_5(call_wall)
            use_gex = True

        # Priority 3: SD-based fallback (0.8 SD for TITAN = closer strikes)
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
        """Estimate SPX IC credits for TITAN's wider spreads"""
        width = self.config.spread_width  # $12 for TITAN

        put_dist = (spot - put_short) / expected_move
        call_dist = (call_short - spot) / expected_move
        vol_factor = vix / 20.0

        # SPX typically has higher premiums - TITAN closer strikes = higher credit
        put_credit = width * 0.028 * vol_factor / max(put_dist, 0.4)  # Higher base
        call_credit = width * 0.028 * vol_factor / max(call_dist, 0.4)

        put_credit = max(0.40, min(put_credit, width * 0.40))  # Lower min, higher max
        call_credit = max(0.40, min(call_credit, width * 0.40))

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
        """Generate aggressive SPX Iron Condor signal for TITAN"""
        market = self.get_market_data()
        if not market:
            return None

        can_trade, reason = self.check_vix_filter(market['vix'])
        if not can_trade:
            logger.info(f"VIX filter: {reason}")
            return None

        # ============================================================
        # ML MODEL TAKES PRECEDENCE OVER ORACLE
        # ARES ML Advisor trained on KRONOS backtests (~70% win rate)
        # Oracle is only used as backup when ML is not available
        # ============================================================

        # Get ML prediction first (PRIMARY SOURCE)
        ml_prediction = self.get_ml_prediction(market)
        ml_win_prob = ml_prediction.get('win_probability', 0) if ml_prediction else 0
        ml_confidence = ml_prediction.get('confidence', 0) if ml_prediction else 0

        # Get Oracle advice (BACKUP SOURCE)
        oracle = self.get_oracle_advice(market)
        oracle_win_prob = oracle.get('win_probability', 0) if oracle else 0
        oracle_confidence = oracle.get('confidence', 0.7) if oracle else 0.7

        # Determine which source to use
        use_ml_prediction = ml_prediction is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        confidence = ml_confidence if use_ml_prediction else oracle_confidence
        prediction_source = "ARES_ML_ADVISOR" if use_ml_prediction else "ORACLE"

        # CRITICAL FALLBACK: TITAN is aggressive SPX IC bot - use lower threshold
        if effective_win_prob <= 0:
            gex_regime = market_data.get('gex_regime', 'NEUTRAL')
            baseline = 0.55  # TITAN is aggressive

            if vix < 15:
                baseline += 0.05
            elif vix > 30:
                baseline -= 0.08
            elif vix > 25:
                baseline -= 0.04

            if gex_regime == 'POSITIVE':
                baseline += 0.05
            elif gex_regime == 'NEGATIVE':
                baseline -= 0.03

            effective_win_prob = max(0.48, min(0.70, baseline))
            confidence = 0.55
            prediction_source = "MARKET_CONDITIONS_FALLBACK"
            logger.info(f"[TITAN FALLBACK] No ML/Oracle prediction - using market baseline: {effective_win_prob:.1%}")

        # Log ML analysis FIRST (PRIMARY source)
        if ml_prediction:
            logger.info(f"[TITAN ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
            logger.info(f"  Win Probability: {ml_win_prob:.1%}")
            logger.info(f"  Confidence: {ml_confidence:.1%}")
            logger.info(f"  Advice: {ml_prediction.get('advice', 'N/A')}")
            logger.info(f"  Model Version: {ml_prediction.get('model_version', 'unknown')}")
            logger.info(f"  Suggested SD: {ml_prediction.get('suggested_sd_multiplier', 1.0):.2f}x")

            if ml_prediction.get('top_factors'):
                logger.info(f"  Top Factors (Feature Importance):")
                for i, factor in enumerate(ml_prediction['top_factors'][:5], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    logger.info(f"    {i}. {factor_name}: {impact:.3f}")
        else:
            logger.info(f"[TITAN] ML Advisor not available, falling back to Oracle")

        # Log Oracle analysis (BACKUP source)
        if oracle:
            logger.info(f"[TITAN ORACLE ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
            logger.info(f"  Win Probability: {oracle_win_prob:.1%}")
            logger.info(f"  Confidence: {oracle_confidence:.1%}")
            logger.info(f"  Advice: {oracle.get('advice', 'N/A')}")

            if oracle.get('top_factors'):
                logger.info(f"  Top Factors:")
                for i, factor in enumerate(oracle['top_factors'][:3], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    direction = "+" if impact > 0 else ""
                    logger.info(f"    {i}. {factor_name}: {direction}{impact:.3f}")

                if not use_ml_prediction:
                    oracle_confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                        oracle_confidence, oracle['top_factors'], market
                    )
                    confidence = oracle_confidence

            if oracle.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[TITAN] Oracle advises SKIP_TODAY but ML override active")
                    logger.info(f"  ML Win Prob: {ml_win_prob:.1%} will be used instead")
                else:
                    logger.info(f"[TITAN ORACLE INFO] Oracle advises SKIP_TODAY (informational only)")
                    logger.info(f"  Bot will use its own aggressive threshold: {self.config.min_win_probability:.1%}")

        # Win probability threshold check DISABLED - always trade
        logger.info(f"[TITAN DECISION] Using {prediction_source} win probability: {effective_win_prob:.1%}")
        logger.info(f"[TITAN] Win probability threshold check DISABLED - proceeding with trade")
        if effective_win_prob <= 0:
            effective_win_prob = 0.50  # Default to 50% if no prediction
        logger.info(f"[TITAN PASSED] {prediction_source} Win Prob {effective_win_prob:.1%} - threshold disabled")

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

        # TITAN: Lower minimum credit ($0.50 vs PEGASUS $0.75)
        if pricing['total_credit'] < self.config.min_credit:
            logger.info(f"Credit ${pricing['total_credit']:.2f} < ${self.config.min_credit}")
            return None

        # Calculate expiration for SPXW weekly options (next Friday)
        now = datetime.now(CENTRAL_TZ)
        days_until_friday = (4 - now.weekday()) % 7
        if days_until_friday == 0 and now.hour >= 15:
            days_until_friday = 7
        expiration_date = now + timedelta(days=days_until_friday)
        expiration = expiration_date.strftime("%Y-%m-%d")

        # Build detailed reasoning
        reasoning_parts = []
        reasoning_parts.append(f"SPX VIX={market['vix']:.1f}, EM=${market['expected_move']:.0f}")
        if strikes.get('using_oracle'):
            reasoning_parts.append(f"Oracle Strikes")
        elif strikes['using_gex']:
            reasoning_parts.append("GEX-Protected")
        else:
            reasoning_parts.append(f"{self.config.sd_multiplier} SD (Aggressive)")

        # Oracle context for reasoning
        if oracle:
            reasoning_parts.append(f"Oracle: {oracle['advice']} ({oracle['confidence']:.0%})")
            if oracle['win_probability']:
                reasoning_parts.append(f"Win Prob: {oracle['win_probability']:.0%}")
            if oracle['top_factors']:
                top = oracle['top_factors'][0]
                reasoning_parts.append(f"Top Factor: {top['factor']}")

        reasoning = " | ".join(reasoning_parts)

        # TITAN: Higher base confidence, easier boost
        confidence = 0.65  # Higher base (PEGASUS: 0.7 but stricter)
        if oracle:
            if oracle['advice'] == 'ENTER' and oracle['confidence'] > 0.5:  # Lower threshold
                confidence = min(0.9, confidence + oracle['confidence'] * 0.25)
            elif oracle['advice'] == 'EXIT':
                confidence -= 0.15  # Smaller penalty

        # GEX Directional ML - Check if market is too directional for IC
        # Build GEX data dict from market for ML predictions
        gex_data = {
            'net_gex': market.get('net_gex', 0),
            'major_pos_vol_level': market.get('call_wall', 0),
            'major_neg_vol_level': market.get('put_wall', 0),
            'flip_point': market.get('flip_point', 0),
            'spot_price': market.get('spot_price', 0),
        }
        gex_dir_prediction = self.get_gex_directional_prediction(gex_data, market['vix'])
        if gex_dir_prediction:
            gex_dir = gex_dir_prediction.get('direction', 'FLAT')
            gex_dir_conf = gex_dir_prediction.get('confidence', 0)

            logger.info(f"[TITAN GEX DIRECTIONAL ML] Direction: {gex_dir}, Confidence: {gex_dir_conf:.1%}")

            if gex_dir == 'FLAT':
                # FLAT is ideal for Iron Condors - boost confidence
                confidence = min(0.95, confidence + 0.05)
            elif gex_dir_conf > 0.80:
                # Strong directional signal - reduce confidence for IC
                penalty = (gex_dir_conf - 0.80) * 0.30
                confidence = max(0.40, confidence - penalty)
                logger.info(f"  Strong {gex_dir} signal - IC confidence reduced to {confidence:.1%}")

        # ML Regime Classifier - Learned market regime detection
        regime_prediction = self.get_ml_regime_prediction(gex_data, market)
        if regime_prediction:
            regime_action = regime_prediction.get('action', 'STAY_FLAT')
            regime_conf = regime_prediction.get('confidence', 50) / 100.0

            logger.info(f"[TITAN ML REGIME] Action: {regime_action}, Confidence: {regime_conf:.1%}")

            if regime_action == 'SELL_PREMIUM':
                boost = min(0.08, regime_conf * 0.10)
                confidence = min(0.95, confidence + boost)
            elif regime_action in ('BUY_CALLS', 'BUY_PUTS') and regime_conf > 0.70:
                penalty = (regime_conf - 0.70) * 0.25
                confidence = max(0.40, confidence - penalty)
            elif regime_action == 'STAY_FLAT':
                confidence = min(0.90, confidence + 0.02)

        # Ensemble Strategy - Multi-signal confirmation
        ensemble_result = self.get_ensemble_boost(market, ml_prediction, oracle)
        if ensemble_result:
            if not ensemble_result.get('should_trade', True):
                logger.info(f"[TITAN ENSEMBLE BLOCKED] {ensemble_result.get('reasoning', 'No reason')}")
                return None

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
            oracle_suggested_sd=oracle['suggested_sd_multiplier'] if oracle else self.config.sd_multiplier,
            oracle_use_gex_walls=oracle['use_gex_walls'] if oracle else False,
            oracle_probabilities=oracle['probabilities'] if oracle else {},
        )
