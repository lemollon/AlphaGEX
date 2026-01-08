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
from typing import Optional, Dict, Any, Tuple, List
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
    from quant.ares_ml_advisor import AresMLAdvisor, MLPrediction
    ARES_ML_AVAILABLE = True
except ImportError:
    ARES_ML_AVAILABLE = False
    AresMLAdvisor = None
    MLPrediction = None

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
# Can confirm or contradict IC positioning
GEX_DIRECTIONAL_ML_AVAILABLE = False
try:
    from quant.gex_directional_ml import GEXDirectionalPredictor, Direction, DirectionalPrediction
    GEX_DIRECTIONAL_ML_AVAILABLE = True
except ImportError:
    GEXDirectionalPredictor = None
    Direction = None
    DirectionalPrediction = None


class SignalGenerator:
    """
    Generates Iron Condor signals using GEX data and market analysis.
    """

    def __init__(self, config: ARESConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator - Try Kronos first, but VERIFY it has FRESH data
        # Kronos uses ORAT database which is historical (EOD) and may be stale
        self.gex_calculator = None
        kronos_works = False

        if KRONOS_AVAILABLE:
            try:
                kronos_calc = KronosGEXCalculator()
                # CRITICAL: Test if Kronos has RECENT data (within 2 trading days)
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
                                logger.info(f"ARES: Kronos GEX verified (spot={test_result.get('spot_price')}, date={trade_date})")
                            else:
                                logger.warning(f"ARES: Kronos data too stale ({days_old} days old) - falling back to Tradier")
                        except ValueError:
                            logger.warning(f"ARES: Kronos has invalid trade_date format - falling back")
                    else:
                        logger.warning("ARES: Kronos returned no trade_date - falling back")
                else:
                    logger.warning("ARES: Kronos returned no data - falling back")
            except Exception as e:
                logger.warning(f"ARES: Kronos init/test failed: {e}")

        # Fall back to Tradier for LIVE data if Kronos didn't work
        if not kronos_works and TRADIER_GEX_AVAILABLE:
            try:
                tradier_calc = get_gex_calculator()
                # Verify Tradier works with live data
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"ARES: Using Tradier GEX (live spot={test_result.get('spot_price')})")
                else:
                    logger.error("ARES: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"ARES: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("ARES: NO GEX CALCULATOR AVAILABLE - trading will be limited")

        # ARES ML Advisor (PRIMARY - trained on KRONOS backtests with ~70% win rate)
        self.ares_ml = None
        if ARES_ML_AVAILABLE:
            try:
                self.ares_ml = AresMLAdvisor()
                if self.ares_ml.is_trained:
                    logger.info(f"ARES SignalGenerator: ML Advisor v{self.ares_ml.model_version} loaded (PRIMARY)")
                else:
                    logger.info("ARES SignalGenerator: ML Advisor initialized (not yet trained)")
            except Exception as e:
                logger.warning(f"ARES ML Advisor init failed: {e}")

        # Oracle Advisor (BACKUP - used when ML not available)
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ARES SignalGenerator: Oracle initialized (BACKUP)")
            except Exception as e:
                logger.warning(f"Oracle init failed: {e}")

        # Ensemble Strategy Weighter - combines multiple signal sources
        self.ensemble_available = ENSEMBLE_AVAILABLE
        if ENSEMBLE_AVAILABLE:
            logger.info("ARES SignalGenerator: Ensemble Strategy available")

        # GEX Directional ML - predicts market direction from GEX structure
        # For Iron Condors: if strongly directional, may want to skip or adjust strikes
        self.gex_directional_ml = None
        if GEX_DIRECTIONAL_ML_AVAILABLE:
            try:
                self.gex_directional_ml = GEXDirectionalPredictor()
                logger.info("ARES SignalGenerator: GEX Directional ML initialized")
            except Exception as e:
                logger.debug(f"GEX Directional ML init failed: {e}")

        # ML Regime Classifier - replaces hard-coded GEX thresholds
        # For Iron Condors: SELL_PREMIUM = good, directional = reduce confidence
        self.ml_regime_classifier = None
        if ML_REGIME_AVAILABLE and MLRegimeClassifier:
            try:
                self.ml_regime_classifier = MLRegimeClassifier(symbol=self.config.ticker)
                logger.info("ARES SignalGenerator: ML Regime Classifier initialized")
            except Exception as e:
                logger.debug(f"ML Regime Classifier init failed: {e}")

    def get_gex_directional_prediction(self, gex_data: Dict, vix: float = None) -> Optional[Dict]:
        """
        Get GEX Directional ML prediction for market direction.

        For Iron Condors: Strong directional signal suggests caution.
        - FLAT/NEUTRAL = good for IC (rangebound)
        - BULLISH with high confidence = may want to widen call side
        - BEARISH with high confidence = may want to widen put side
        """
        if not self.gex_directional_ml:
            return None

        try:
            # Build features from GEX data
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

            # Extract features from market data
            gex_normalized = gex_data.get('net_gex', 0) / 1e9 if gex_data.get('net_gex', 0) != 0 else 1.0
            vix = market_data.get('vix', 20.0)
            spot = market_data.get('spot_price', 0)
            flip_point = gex_data.get('flip_point', spot)

            # Calculate distance to flip as percentage
            distance_to_flip = ((spot - flip_point) / spot * 100) if spot > 0 else 0

            prediction = self.ml_regime_classifier.predict(
                gex_normalized=gex_normalized,
                gex_percentile=50.0,  # Use neutral if not available
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
        Get ensemble signal boost/confirmation from multiple strategy sources.

        The ensemble combines: GEX signals, ML predictions, and Oracle with learned weights.
        Returns a multiplier for position sizing based on signal agreement.
        """
        if not ENSEMBLE_AVAILABLE:
            return {'boost': 1.0, 'should_trade': True, 'confidence': 0.7, 'reasoning': 'Ensemble not available'}

        try:
            # Build GEX data for ensemble
            gex_data = {
                'recommended_action': 'SELL_IC',  # Iron Condor is neutral/range-bound
                'confidence': 70,
                'reasoning': f"VIX={market_data.get('vix', 20):.1f}, EM=${market_data.get('expected_move', 0):.0f}"
            }

            # Build ML prediction data
            ml_data = None
            if ml_prediction:
                ml_data = {
                    'predicted_action': 'SELL_IC',
                    'confidence': ml_prediction.get('confidence', 0) * 100,
                    'is_trained': True
                }

            # Get current regime from GEX
            current_regime = market_data.get('gex_regime', 'UNKNOWN')
            if current_regime == 'POSITIVE':
                current_regime = 'POSITIVE_GAMMA'
            elif current_regime == 'NEGATIVE':
                current_regime = 'NEGATIVE_GAMMA'

            # Get ensemble signal
            ensemble = get_ensemble_signal(
                symbol=self.config.ticker,
                gex_data=gex_data,
                ml_prediction=ml_data,
                current_regime=current_regime
            )

            if ensemble:
                logger.info(f"[ARES ENSEMBLE] Signal: {ensemble.final_signal.value}, "
                           f"Confidence: {ensemble.confidence:.0f}%, "
                           f"Size Multiplier: {ensemble.position_size_multiplier:.0%}")

                return {
                    'boost': ensemble.position_size_multiplier,
                    'should_trade': ensemble.should_trade,
                    'confidence': ensemble.confidence / 100,
                    'signal': ensemble.final_signal.value,
                    'reasoning': ensemble.reasoning
                }

        except Exception as e:
            logger.debug(f"Ensemble signal error: {e}")

        return {'boost': 1.0, 'should_trade': True, 'confidence': 0.7, 'reasoning': 'Ensemble fallback'}

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

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current GEX data - PUBLIC method for trader.

        Returns dict with: spot_price, call_wall, put_wall, gex_regime, vix
        """
        if not self.gex_calculator:
            logger.warning("No GEX calculator available")
            return None

        try:
            gex = self.gex_calculator.calculate_gex(self.config.ticker)
            if not gex:
                return None

            # Get spot price
            spot = 0.0
            if DATA_PROVIDER_AVAILABLE:
                spot = get_price(self.config.ticker)
            if not spot:
                spot = gex.get('spot_price', gex.get('underlying_price', 0))

            # Get VIX
            vix = 20.0
            if DATA_PROVIDER_AVAILABLE:
                try:
                    vix = get_vix() or 20.0
                except Exception:
                    pass

            return {
                'spot_price': spot,
                'underlying_price': spot,
                'call_wall': gex.get('call_wall', gex.get('major_call_wall', 0)),
                'put_wall': gex.get('put_wall', gex.get('major_put_wall', 0)),
                'gex_regime': gex.get('regime', gex.get('gex_regime', 'NEUTRAL')),
                'regime': gex.get('regime', gex.get('gex_regime', 'NEUTRAL')),
                'net_gex': gex.get('net_gex', 0),
                'flip_point': gex.get('flip_point', gex.get('gamma_flip', 0)),
                'vix': vix,
                'timestamp': datetime.now(CENTRAL_TZ),
            }
        except Exception as e:
            logger.error(f"GEX fetch error: {e}")
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

    def get_ml_prediction(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get prediction from ARES ML Advisor (PRIMARY prediction source).

        This model was trained on KRONOS backtests with ~70% win rate.
        It takes precedence over Oracle for trading decisions.

        Returns dict with:
        - win_probability: Calibrated probability of winning (key metric)
        - confidence: Model confidence score
        - advice: TRADE_FULL, TRADE_REDUCED, or SKIP_TODAY
        - suggested_risk_pct: Position size recommendation
        - suggested_sd_multiplier: Strike width recommendation
        - top_factors: Feature importances explaining the decision
        """
        if not self.ares_ml:
            return None

        try:
            now = datetime.now(CENTRAL_TZ)
            day_of_week = now.weekday()

            # Calculate GEX features
            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL').upper()
            gex_regime_positive = 1 if gex_regime_str == 'POSITIVE' else 0

            spot = market_data['spot_price']
            flip_point = market_data.get('flip_point', spot)
            gex_distance_to_flip_pct = abs(spot - flip_point) / spot * 100 if spot > 0 else 0

            put_wall = market_data.get('put_wall', spot * 0.98)
            call_wall = market_data.get('call_wall', spot * 1.02)
            gex_between_walls = 1 if put_wall <= spot <= call_wall else 0

            # Get ML prediction
            prediction = self.ares_ml.predict(
                vix=market_data['vix'],
                day_of_week=day_of_week,
                price=spot,
                price_change_1d=market_data.get('price_change_1d', 0),
                expected_move_pct=(market_data.get('expected_move', 0) / spot * 100) if spot > 0 else 1.0,
                win_rate_30d=0.70,  # Use historical baseline
                vix_percentile_30d=50,  # Default if not available
                vix_change_1d=0,
                gex_normalized=market_data.get('gex_normalized', 0),
                gex_regime_positive=gex_regime_positive,
                gex_distance_to_flip_pct=gex_distance_to_flip_pct,
                gex_between_walls=gex_between_walls,
            )

            if prediction:
                # Format top factors for logging
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
            logger.warning(f"ARES ML prediction error: {e}")
            import traceback
            traceback.print_exc()

        return None

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

        # ============================================================
        # Step 3: ML MODEL TAKES PRECEDENCE OVER ORACLE
        # ARES ML Advisor trained on KRONOS backtests (~70% win rate)
        # Oracle is only used as backup when ML is not available
        # ============================================================

        # Step 3a: Try ML prediction first (PRIMARY SOURCE)
        ml_prediction = self.get_ml_prediction(market_data)
        ml_win_prob = ml_prediction.get('win_probability', 0) if ml_prediction else 0
        ml_confidence = ml_prediction.get('confidence', 0) if ml_prediction else 0

        # Step 3b: Get Oracle advice (BACKUP SOURCE)
        oracle = self.get_oracle_advice(market_data)
        oracle_win_prob = oracle.get('win_probability', 0) if oracle else 0
        oracle_confidence = oracle.get('confidence', 0.7) if oracle else 0.7

        # Determine which source to use
        use_ml_prediction = ml_prediction is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        confidence = ml_confidence if use_ml_prediction else oracle_confidence
        prediction_source = "ARES_ML_ADVISOR" if use_ml_prediction else "ORACLE"

        # Log ML analysis FIRST (PRIMARY source)
        if ml_prediction:
            logger.info(f"[ARES ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
            logger.info(f"  Win Probability: {ml_win_prob:.1%}")
            logger.info(f"  Confidence: {ml_confidence:.1%}")
            logger.info(f"  Advice: {ml_prediction.get('advice', 'N/A')}")
            logger.info(f"  Model Version: {ml_prediction.get('model_version', 'unknown')}")
            logger.info(f"  Suggested Risk: {ml_prediction.get('suggested_risk_pct', 10):.1f}%")
            logger.info(f"  Suggested SD: {ml_prediction.get('suggested_sd_multiplier', 1.0):.2f}x")

            if ml_prediction.get('top_factors'):
                logger.info(f"  Top Factors (Feature Importance):")
                for i, factor in enumerate(ml_prediction['top_factors'][:5], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    logger.info(f"    {i}. {factor_name}: {impact:.3f}")
        else:
            logger.info(f"[ARES] ML Advisor not available, falling back to Oracle")

        # Log Oracle analysis (BACKUP source)
        if oracle:
            logger.info(f"[ARES ORACLE ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
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

                # APPLY top_factors to adjust confidence based on current conditions
                if not use_ml_prediction:
                    confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                        confidence, oracle['top_factors'], market_data
                    )

            # Oracle SKIP_TODAY is informational only when ML is available
            if oracle.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[ARES] Oracle advises SKIP_TODAY but ML override active")
                    logger.info(f"  ML Win Prob: {ml_win_prob:.1%} will be used instead")
                else:
                    logger.info(f"[ARES ORACLE INFO] Oracle advises SKIP_TODAY (informational only)")
                    logger.info(f"  Bot will use its own threshold: {self.config.min_win_probability:.1%}")

        # Validate win probability meets minimum threshold (using effective source)
        min_win_prob = self.config.min_win_probability
        logger.info(f"[ARES DECISION] Using {prediction_source} win probability: {effective_win_prob:.1%}")

        if effective_win_prob > 0 and effective_win_prob < min_win_prob:
            logger.info(f"[ARES TRADE BLOCKED] Win probability below threshold")
            logger.info(f"  {prediction_source} Win Prob: {effective_win_prob:.1%}")
            logger.info(f"  Minimum Required: {min_win_prob:.1%}")
            logger.info(f"  Shortfall: {(min_win_prob - effective_win_prob):.1%}")
            return None

        # Use ML's suggested SD multiplier if available
        win_probability = effective_win_prob
        if use_ml_prediction and ml_prediction.get('suggested_sd_multiplier'):
            self._ml_suggested_sd = ml_prediction.get('suggested_sd_multiplier', 1.0)

        logger.info(f"[ARES PASSED] {prediction_source} Win Prob {win_probability:.1%} >= {min_win_prob:.1%} minimum")

        # ============================================================
        # GEX DIRECTIONAL ML - Check if market is too directional for IC
        # Iron Condors work best in rangebound markets (FLAT prediction)
        # Strong directional signal = reduce confidence or skip
        # ============================================================
        # Build GEX data dict from market_data for ML predictions
        gex_data = {
            'net_gex': market_data.get('net_gex', 0),
            'major_pos_vol_level': market_data.get('call_wall', 0),
            'major_neg_vol_level': market_data.get('put_wall', 0),
            'flip_point': market_data.get('flip_point', 0),
            'spot_price': market_data.get('spot_price', 0),
        }
        gex_dir_prediction = self.get_gex_directional_prediction(gex_data, vix)
        if gex_dir_prediction:
            gex_dir = gex_dir_prediction.get('direction', 'FLAT')
            gex_dir_conf = gex_dir_prediction.get('confidence', 0)

            logger.info(f"[ARES GEX DIRECTIONAL ML] Direction: {gex_dir}, Confidence: {gex_dir_conf:.1%}")

            if gex_dir == 'FLAT':
                # FLAT is ideal for Iron Condors - boost confidence
                confidence = min(0.95, confidence + 0.05)
                logger.info(f"  FLAT prediction = ideal for IC, confidence boosted to {confidence:.1%}")
            elif gex_dir_conf > 0.80:
                # Strong directional signal - reduce confidence for IC
                penalty = (gex_dir_conf - 0.80) * 0.30  # Max 6% penalty at 100% confidence
                confidence = max(0.40, confidence - penalty)
                logger.info(f"  Strong {gex_dir} signal ({gex_dir_conf:.0%}) - IC confidence reduced to {confidence:.1%}")
            elif gex_dir_conf > 0.65:
                # Moderate directional signal - small penalty
                penalty = (gex_dir_conf - 0.65) * 0.15  # Max 2.25% penalty
                confidence = max(0.45, confidence - penalty)
                logger.info(f"  Moderate {gex_dir} signal - IC confidence adjusted to {confidence:.1%}")

        # ============================================================
        # ML REGIME CLASSIFIER - Learned market regime detection
        # For Iron Condors: SELL_PREMIUM = ideal, directional = reduce confidence
        # ============================================================
        regime_prediction = self.get_ml_regime_prediction(gex_data, market_data)
        if regime_prediction:
            regime_action = regime_prediction.get('action', 'STAY_FLAT')
            regime_conf = regime_prediction.get('confidence', 50) / 100.0

            logger.info(f"[ARES ML REGIME] Action: {regime_action}, Confidence: {regime_conf:.1%}")

            if regime_action == 'SELL_PREMIUM':
                # Perfect for Iron Condors - boost confidence
                boost = min(0.08, regime_conf * 0.10)
                confidence = min(0.95, confidence + boost)
                logger.info(f"  SELL_PREMIUM regime = ideal for IC, confidence boosted to {confidence:.1%}")
            elif regime_action in ('BUY_CALLS', 'BUY_PUTS'):
                # Directional regime - reduce IC confidence
                if regime_conf > 0.70:
                    penalty = (regime_conf - 0.70) * 0.25
                    confidence = max(0.40, confidence - penalty)
                    logger.info(f"  {regime_action} regime ({regime_conf:.0%}) - IC confidence reduced to {confidence:.1%}")
            elif regime_action == 'STAY_FLAT':
                # Neutral - slight boost for IC
                confidence = min(0.90, confidence + 0.02)
                logger.info(f"  STAY_FLAT regime = neutral for IC, confidence: {confidence:.1%}")

        # ============================================================
        # Step 3.5: ENSEMBLE STRATEGY - Multi-signal confirmation
        # Combines GEX, ML, and learned regime weights for position sizing
        # ============================================================
        ensemble_result = self.get_ensemble_boost(market_data, ml_prediction, oracle)
        if ensemble_result:
            if not ensemble_result.get('should_trade', True):
                logger.info(f"[ARES ENSEMBLE BLOCKED] Ensemble says don't trade: {ensemble_result.get('reasoning', 'No reason')}")
                return None

            ensemble_boost = ensemble_result.get('boost', 1.0)
            if ensemble_boost != 1.0:
                logger.info(f"[ARES ENSEMBLE] Position size multiplier: {ensemble_boost:.0%}")

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
