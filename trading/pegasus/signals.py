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

# Oracle is the god of all trade decisions

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

# REMOVED: Ensemble Strategy and ML Regime Classifier - dead code

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
    """Generates SPX Iron Condor signals"""

    def __init__(self, config: PEGASUSConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        # GEX Calculator - Use Tradier for LIVE trading data
        # Kronos uses ORAT database (EOD) - only for backtesting, NOT live trading
        self.gex_calculator = None

        if TRADIER_GEX_AVAILABLE:
            try:
                # CRITICAL: SPX requires production API (sandbox doesn't support SPX)
                from data.gex_calculator import TradierGEXCalculator
                tradier_calc = TradierGEXCalculator(sandbox=False)
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"PEGASUS: Using Tradier GEX for LIVE trading (spot={test_result.get('spot_price')})")
                else:
                    logger.error("PEGASUS: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"PEGASUS: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("PEGASUS: NO GEX CALCULATOR AVAILABLE - Tradier required for live trading")

        # ARES ML Advisor (PRIMARY - Iron Condor ML model with ~70% win rate)
        self.ares_ml = None
        if ARES_ML_AVAILABLE:
            try:
                self.ares_ml = AresMLAdvisor()
                if self.ares_ml.is_trained:
                    logger.info(f"PEGASUS: ML Advisor v{self.ares_ml.model_version} loaded (PRIMARY)")
                else:
                    logger.info("PEGASUS: ML Advisor initialized (not yet trained)")
            except Exception as e:
                logger.warning(f"PEGASUS: ML Advisor init failed: {e}")

        # Oracle (BACKUP - used when ML not available)
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("PEGASUS: Oracle initialized (BACKUP)")
            except Exception as e:
                logger.warning(f"PEGASUS: Oracle init failed: {e}")

        # GEX Directional ML - predicts market direction from GEX structure
        self.gex_directional_ml = None
        if GEX_DIRECTIONAL_ML_AVAILABLE:
            try:
                self.gex_directional_ml = GEXDirectionalPredictor()
                logger.info("PEGASUS: GEX Directional ML initialized")
            except Exception as e:
                logger.debug(f"PEGASUS: GEX Directional ML init failed: {e}")

        # REMOVED: ML Regime Classifier initialization - dead code

    def get_gex_directional_prediction(self, gex_data: Dict, vix: float = None) -> Optional[Dict]:
        """
        Get GEX Directional ML prediction for market direction.

        For Iron Condors: Strong directional signal is INFORMATIONAL ONLY.
        """
        if not self.gex_directional_ml:
            return None

        try:
            # Build proper gex_data dict for predict() method
            spot = gex_data.get('spot_price', 0)
            call_wall = gex_data.get('major_pos_vol_level', gex_data.get('call_wall', spot))
            put_wall = gex_data.get('major_neg_vol_level', gex_data.get('put_wall', spot))
            flip_point = gex_data.get('flip_point', spot)

            ml_gex_data = {
                'spot_price': spot,
                'net_gex': gex_data.get('net_gex', 0),
                'gex_normalized': gex_data.get('gex_normalized', 0),
                'gex_regime': gex_data.get('gex_regime', 'NEUTRAL'),
                'call_wall': call_wall,
                'put_wall': put_wall,
                'flip_point': flip_point,
                'distance_to_flip_pct': ((flip_point - spot) / spot * 100) if spot > 0 else 0,
                'between_walls': put_wall < spot < call_wall if spot > 0 else True,
                'above_call_wall': spot > call_wall if spot > 0 else False,
                'below_put_wall': spot < put_wall if spot > 0 else False,
            }

            prediction = self.gex_directional_ml.predict(
                gex_data=ml_gex_data,
                vix=vix or 20.0
            )

            if prediction:
                return {
                    'direction': prediction.direction.value if hasattr(prediction.direction, 'value') else str(prediction.direction),
                    'confidence': prediction.confidence,
                    'probabilities': prediction.probabilities if hasattr(prediction, 'probabilities') else {}
                }
        except Exception as e:
            logger.warning(f"GEX Directional ML prediction failed: {e}")

        return None

    # REMOVED: get_ml_regime_prediction method - dead code

    # REMOVED: get_ensemble_boost method - dead code

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

        This model was trained on KRONOS backtests with ~70% win rate.
        It takes precedence over Oracle for trading decisions.
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
            logger.warning(f"PEGASUS ML prediction error: {e}")

        return None

    def get_oracle_advice(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Oracle prediction with FULL context for audit trail (BACKUP SOURCE).

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
                use_claude_validation=True,  # Enable Claude for transparency logging
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

                # NEUTRAL Regime Analysis (trend-based direction for NEUTRAL GEX)
                'neutral_derived_direction': getattr(prediction, 'neutral_derived_direction', ''),
                'neutral_confidence': getattr(prediction, 'neutral_confidence', 0),
                'neutral_reasoning': getattr(prediction, 'neutral_reasoning', ''),
                'ic_suitability': getattr(prediction, 'ic_suitability', 0),
                'bullish_suitability': getattr(prediction, 'bullish_suitability', 0),
                'bearish_suitability': getattr(prediction, 'bearish_suitability', 0),
                'trend_direction': getattr(prediction, 'trend_direction', ''),
                'trend_strength': getattr(prediction, 'trend_strength', 0),
                'position_in_range_pct': getattr(prediction, 'position_in_range_pct', 50.0),
                'wall_filter_passed': getattr(prediction, 'wall_filter_passed', False),
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
        """
        Check if VIX conditions allow trading.

        Returns (can_trade, reason).

        Only blocks in extreme crisis conditions (VIX > 50) to ensure
        the bot can trade every day under normal market conditions.
        """
        # VIX filter - only block in extreme conditions (VIX > 50)
        # This ensures the bot can trade daily under normal market conditions
        if vix > 50:
            return False, f"VIX ({vix:.1f}) extremely elevated - market crisis conditions"

        return True, f"VIX={vix:.1f} - trading allowed"

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

        # REMOVED: VIX, GEX regime, day of week adjustments
        # Oracle already analyzed all these factors in MarketContext.
        # Re-adjusting confidence based on the same factors is redundant.
        # Trust Oracle's win_probability output directly.

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

        vix = market['vix']

        # ============================================================
        # ML/ORACLE PREDICTIONS FIRST (SUPERSEDES VIX FILTER)
        #
        # CRITICAL: Oracle and ML already account for VIX in their predictions.
        # If ML/Oracle provides a good win probability, we TRADE regardless of VIX.
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

        # Check if ML/Oracle gives us a tradeable signal
        min_win_prob = self.config.min_win_probability
        ml_oracle_says_trade = effective_win_prob >= min_win_prob

        # Log ML/Oracle decision
        if ml_oracle_says_trade:
            logger.info(f"[PEGASUS] ML/Oracle SUPERSEDES VIX filter: {prediction_source} = {effective_win_prob:.0%} (>={min_win_prob:.0%})")
            # Check what VIX would have done (for logging only)
            can_trade, vix_reason = self.check_vix_filter(vix)
            if not can_trade:
                logger.info(f"[PEGASUS] VIX would have blocked ({vix_reason}) but ML/Oracle supersedes")
        else:
            logger.info(f"[PEGASUS] ML/Oracle: {effective_win_prob:.0%} (threshold: {min_win_prob:.0%})")
            # Only apply VIX filter if ML/Oracle doesn't give tradeable signal
            can_trade, vix_reason = self.check_vix_filter(vix)
            if not can_trade:
                logger.info(f"[PEGASUS SKIP] VIX filter: {vix_reason}, ML/Oracle also insufficient")
                return None

            # REMOVED: Market conditions fallback baseline
            # If Oracle returns 0 win probability, trust that decision.
            # Don't manufacture a baseline - Oracle already analyzed VIX, GEX, etc.
            if effective_win_prob <= 0:
                logger.info(f"[PEGASUS BLOCKED] ML/Oracle returned 0 win probability - no trade signal")
                return None

        # Log ML analysis FIRST (PRIMARY source)
        if ml_prediction:
            logger.info(f"[PEGASUS ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
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
            logger.info(f"[PEGASUS] ML Advisor not available, falling back to Oracle")

        # Log Oracle analysis (BACKUP source)
        if oracle:
            logger.info(f"[PEGASUS ORACLE ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
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
                    logger.info(f"[PEGASUS] Oracle advises SKIP_TODAY but ML override active")
                    logger.info(f"  ML Win Prob: {ml_win_prob:.1%} will be used instead")
                else:
                    logger.info(f"[PEGASUS ORACLE INFO] Oracle advises SKIP_TODAY (informational only)")
                    logger.info(f"  Bot will use its own threshold: {self.config.min_win_probability:.1%}")

        # Win probability threshold check - enforce minimum win probability
        min_win_prob = getattr(self.config, 'min_win_probability', 0.42)
        logger.info(f"[PEGASUS DECISION] Using {prediction_source} win probability: {effective_win_prob:.1%}")
        logger.info(f"[PEGASUS THRESHOLD] Minimum required: {min_win_prob:.1%}")

        if effective_win_prob < min_win_prob:
            logger.info(f"[PEGASUS BLOCKED] Win probability {effective_win_prob:.1%} < threshold {min_win_prob:.1%}")
            # Return an invalid signal with the reason
            return IronCondorSignal(
                spot_price=market['spot_price'],
                vix=market['vix'],
                expected_move=market['expected_move'],
                call_wall=market.get('call_wall', 0),
                put_wall=market.get('put_wall', 0),
                gex_regime=market.get('gex_regime', 'NEUTRAL'),
                put_short=0,
                put_long=0,
                call_short=0,
                call_long=0,
                expiration="",
                total_credit=0,
                max_loss=0,
                max_profit=0,
                confidence=effective_win_prob,
                reasoning=f"Win probability {effective_win_prob:.1%} below threshold {min_win_prob:.1%}",
                source="THRESHOLD_BLOCKED",
                is_valid=False,
            )

        if effective_win_prob <= 0:
            effective_win_prob = 0.50  # Default to 50% if no prediction
        logger.info(f"[PEGASUS PASSED] {prediction_source} Win Prob {effective_win_prob:.1%} >= threshold {min_win_prob:.1%}")

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
            logger.warning(f"Credit ${pricing['total_credit']:.2f} < ${self.config.min_credit} (proceeding anyway)")

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

            logger.info(f"[PEGASUS GEX DIRECTIONAL ML] Direction: {gex_dir}, Confidence: {gex_dir_conf:.1%}")

            if gex_dir == 'FLAT':
                # FLAT is ideal for Iron Condors - boost confidence
                confidence = min(0.95, confidence + 0.05)
            elif gex_dir_conf > 0.80:
                # Strong directional signal - reduce confidence for IC
                penalty = (gex_dir_conf - 0.80) * 0.30
                confidence = max(0.40, confidence - penalty)
                logger.info(f"  Strong {gex_dir} signal - IC confidence reduced to {confidence:.1%}")

        # REMOVED: ML Regime Classifier call - dead code

        # REMOVED: Ensemble Strategy call - dead code

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
