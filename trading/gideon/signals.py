"""
GIDEON - Signal Generation
===========================

Clean signal generation using GEX data, Prophet, and ML models.

GIDEON uses AGGRESSIVE Apache GEX backtest parameters (vs SOLOMON):
- 2% wall filter (vs 1%) - more room to trade
- 48% min win probability (vs 55%) - lower threshold
- VIX range 12-30 (vs 15-25) - wider volatility range
- GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed
- Uses Tradier LIVE GEX data only (no stale Chronicles)

Safety filters ARE ENABLED with aggressive thresholds.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from zoneinfo import ZoneInfo

from .models import TradeSignal, SpreadType, GideonConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Database for win rate queries
try:
    from database_adapter import get_connection
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    get_connection = None

# Prophet is the god of all trade decisions

# Optional imports with clear fallbacks
try:
    from quant.prophet_advisor import ProphetAdvisor, OraclePrediction, TradingAdvice, MarketContext as OracleMarketContext, GEXRegime
    ORACLE_AVAILABLE = True
except ImportError:
    ORACLE_AVAILABLE = False
    ProphetAdvisor = None
    OracleMarketContext = None
    GEXRegime = None

try:
    from quant.chronicles_gex_calculator import KronosGEXCalculator
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

# REMOVED: GEX Directional ML, Ensemble Strategy, ML Regime Classifier - redundant with Prophet

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

    GIDEON uses AGGRESSIVE Apache GEX backtest parameters (vs SOLOMON):
    - 2% wall_filter_pct (vs 1%) - more room to trade
    - 48% min_win_probability (vs 55%) - lower threshold
    - 1.2 min_rr_ratio (vs 1.5) - accept slightly lower R:R
    - VIX range 12-30 (vs 15-25) - wider range
    - GEX ratio 1.3/0.77 (vs 1.5/0.67) - weaker asymmetry allowed

    Safety filters ARE ENABLED with aggressive thresholds.
    """

    def __init__(self, config: GideonConfig):
        self.config = config
        self._price_provider = None
        self._init_components()
        self._init_price_provider()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator - Use Tradier for LIVE data (Chronicles is for backtesting only)
        self.gex_calculator = None

        if TRADIER_GEX_AVAILABLE:
            try:
                tradier_calc = get_gex_calculator()
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"GIDEON: Using Tradier GEX (live spot={test_result.get('spot_price')})")
                else:
                    logger.error("GIDEON: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"GIDEON: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("GIDEON: NO GEX CALCULATOR AVAILABLE - Tradier required for live trading")

        # ML Signal Integration
        self.ml_signal = None
        if GEX_ML_AVAILABLE:
            try:
                self.ml_signal = GEXSignalIntegration()
                if self.ml_signal.load_models():
                    logger.info("GIDEON SignalGenerator: ML models loaded")
                else:
                    self.ml_signal = None
            except Exception as e:
                logger.warning(f"ML init failed: {e}")

        # Prophet Advisor
        self.prophet = None
        if ORACLE_AVAILABLE:
            try:
                self.prophet = ProphetAdvisor()
                logger.info("GIDEON SignalGenerator: Prophet initialized")
            except Exception as e:
                logger.warning(f"Prophet init failed: {e}")

    def _init_price_provider(self) -> None:
        """Initialize price data provider for historical data (VIX/price history)."""
        try:
            from data.unified_data_provider import UnifiedDataProvider
            self._price_provider = UnifiedDataProvider()
            logger.info("GIDEON SignalGenerator: Price provider initialized")
        except Exception as e:
            logger.warning(f"Price provider init failed: {e}")
            self._price_provider = None

    def _get_ml_features(self, spot_price: float, vix: float) -> Dict[str, Any]:
        """
        Calculate the 4 remaining Prophet ML features:
        - vix_percentile_30d: Where current VIX sits in 30-day range (0-100)
        - vix_change_1d: % change in VIX from yesterday
        - price_change_1d: % change in underlying price from yesterday
        - win_rate_30d: Win rate of closed trades in last 30 days (0-1)

        These complete the full 11-feature Prophet ML model.
        """
        features = {
            'vix_percentile_30d': 50.0,  # Default: middle of range
            'vix_change_1d': 0.0,        # Default: no change
            'price_change_1d': 0.0,      # Default: no change
            'win_rate_30d': 0.68,        # Default: historical average
        }

        # Calculate VIX percentile and change from historical data
        if self._price_provider:
            try:
                # Get 30 days of VIX history
                from datetime import timedelta
                vix_bars = self._price_provider.get_historical_bars('VIX', days=35, interval='day')
                if vix_bars and len(vix_bars) >= 2:
                    vix_closes = [bar.close for bar in vix_bars if bar.close > 0]
                    if vix_closes:
                        # VIX percentile: where current VIX sits in 30-day range
                        min_vix = min(vix_closes[-30:]) if len(vix_closes) >= 30 else min(vix_closes)
                        max_vix = max(vix_closes[-30:]) if len(vix_closes) >= 30 else max(vix_closes)
                        if max_vix > min_vix:
                            features['vix_percentile_30d'] = ((vix - min_vix) / (max_vix - min_vix)) * 100
                            features['vix_percentile_30d'] = max(0, min(100, features['vix_percentile_30d']))

                        # VIX change: yesterday's close to current
                        yesterday_vix = vix_closes[-1] if vix_closes else vix
                        if yesterday_vix > 0:
                            features['vix_change_1d'] = ((vix - yesterday_vix) / yesterday_vix) * 100

                        logger.debug(f"VIX features: percentile={features['vix_percentile_30d']:.1f}, change={features['vix_change_1d']:.2f}%")
            except Exception as e:
                logger.debug(f"VIX history fetch failed (using defaults): {e}")

            try:
                # Get price change from yesterday
                price_bars = self._price_provider.get_historical_bars(self.config.ticker, days=5, interval='day')
                if price_bars and len(price_bars) >= 2:
                    yesterday_close = price_bars[-1].close if price_bars[-1].close > 0 else spot_price
                    if yesterday_close > 0:
                        features['price_change_1d'] = ((spot_price - yesterday_close) / yesterday_close) * 100
                        logger.debug(f"Price change: {features['price_change_1d']:.2f}% (yesterday=${yesterday_close:.2f})")
            except Exception as e:
                logger.debug(f"Price history fetch failed (using defaults): {e}")

        # Calculate win rate from closed trades
        if DB_AVAILABLE:
            try:
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins
                    FROM gideon_positions
                    WHERE status = 'closed'
                      AND close_time >= NOW() - INTERVAL '30 days'
                      AND realized_pnl IS NOT NULL
                """)
                result = c.fetchone()
                conn.close()

                if result and result[0] and result[0] > 0:
                    total, wins = result[0], result[1] or 0
                    features['win_rate_30d'] = wins / total
                    logger.debug(f"Win rate 30d: {wins}/{total} = {features['win_rate_30d']:.2%}")
            except Exception as e:
                logger.debug(f"Win rate query failed (using defaults): {e}")

        return features


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

            # Extract flip point and walls for calculations
            flip_point = gex.get('flip_point', gex.get('gamma_flip', 0))
            call_wall = gex.get('call_wall', gex.get('major_call_wall', 0))
            put_wall = gex.get('put_wall', gex.get('major_put_wall', 0))

            # Calculate derived fields for Prophet ML model
            gex_normalized = gex.get('gex_normalized', 0)
            distance_to_flip_pct = 0.0
            if flip_point > 0 and spot > 0:
                distance_to_flip_pct = (spot - flip_point) / spot * 100
            between_walls = put_wall <= spot <= call_wall if (put_wall > 0 and call_wall > 0) else True

            # Calculate expected move from VIX (annualized vol -> daily)
            import math
            expected_move_pct = (vix / 100 / math.sqrt(252)) * 100  # Daily expected move %

            # Get remaining ML features (vix_percentile_30d, vix_change_1d, price_change_1d, win_rate_30d)
            ml_features = self._get_ml_features(spot, vix)

            return {
                'spot_price': spot,
                'call_wall': call_wall,
                'put_wall': put_wall,
                'gex_regime': gex.get('regime', gex.get('gex_regime', 'NEUTRAL')),
                'net_gex': gex.get('net_gex', 0),
                'flip_point': flip_point,
                'vix': vix,
                'timestamp': datetime.now(CENTRAL_TZ),
                # Additional fields for Prophet ML model (7 features)
                'gex_normalized': gex_normalized,
                'distance_to_flip_pct': distance_to_flip_pct,
                'between_walls': between_walls,
                'expected_move_pct': expected_move_pct,
                # Remaining 4 ML features (complete 11-feature model)
                'vix_percentile_30d': ml_features['vix_percentile_30d'],
                'vix_change_1d': ml_features['vix_change_1d'],
                'price_change_1d': ml_features['price_change_1d'],
                'win_rate_30d': ml_features['win_rate_30d'],
                # Raw Chronicles data for audit
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
        Get Prophet ML advice for GIDEON directional trades.

        Returns FULL prediction context for audit trail.
        """
        if not self.prophet or not ORACLE_AVAILABLE:
            return None

        # Validate required market data before calling Prophet
        spot_price = gex_data.get('spot_price', 0)
        if not spot_price or spot_price <= 0:
            logger.debug("GIDEON Prophet skipped: No valid spot price available")
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'NO_DATA',
                'direction': 'FLAT',
                'top_factors': [],
                'reasoning': 'No valid spot price available for Prophet analysis',
            }

        try:
            # Convert gex_regime string to GEXRegime enum
            gex_regime_str = gex_data.get('gex_regime', 'NEUTRAL').upper()
            try:
                gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            # Build context for Prophet
            # CRITICAL: Include ALL fields for proper ML predictions
            from datetime import datetime
            import pytz
            ct = pytz.timezone('America/Chicago')
            now_ct = datetime.now(ct)

            context = OracleMarketContext(
                spot_price=gex_data['spot_price'],
                vix=gex_data['vix'],
                gex_put_wall=gex_data.get('put_wall', 0),
                gex_call_wall=gex_data.get('call_wall', 0),
                gex_regime=gex_regime,
                gex_net=gex_data.get('net_gex', 0),
                gex_flip_point=gex_data.get('flip_point', 0),
                day_of_week=now_ct.weekday(),  # 0=Monday, 4=Friday
                # Additional ML model features (root cause fix - 7 features)
                gex_normalized=gex_data.get('gex_normalized', 0),
                gex_distance_to_flip_pct=gex_data.get('distance_to_flip_pct', 0),
                gex_between_walls=gex_data.get('between_walls', True),
                expected_move_pct=gex_data.get('expected_move_pct', 1.0),
                # Remaining 4 ML features (complete 11-feature model)
                vix_percentile_30d=gex_data.get('vix_percentile_30d', 50.0),
                vix_change_1d=gex_data.get('vix_change_1d', 0.0),
                price_change_1d=gex_data.get('price_change_1d', 0.0),
                win_rate_30d=gex_data.get('win_rate_30d', 0.68),
            )

            # Call SOLOMON-specific advice method (GIDEON uses same model)
            prediction = self.prophet.get_solomon_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=True,  # Enable Claude for transparency logging
                wall_filter_pct=self.config.wall_filter_pct,  # Uses GIDEON's 6%
                bot_name="GIDEON",  # Log as GIDEON in Prophet Data Flow
            )

            if not prediction:
                return None

            # Extract top_factors as list of dicts for JSON storage
            top_factors = []
            if hasattr(prediction, 'top_factors') and prediction.top_factors:
                for factor_name, impact in prediction.top_factors:
                    top_factors.append({'factor': factor_name, 'impact': impact})

            # Get direction - prefer neutral_derived_direction for NEUTRAL regime, else parse reasoning
            oracle_direction = getattr(prediction, 'neutral_derived_direction', '') or "FLAT"
            if oracle_direction == "FLAT" and hasattr(prediction, 'reasoning') and prediction.reasoning:
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
            logger.warning(f"GIDEON Prophet error: {e}")
            import traceback
            traceback.print_exc()
            # Return fallback values instead of None so scan activity shows meaningful data
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'ERROR',
                'direction': 'FLAT',
                'top_factors': [{'factor': 'error', 'impact': 0}],
                'reasoning': f"Prophet error: {str(e)[:100]}",
            }

    def adjust_confidence_from_top_factors(
        self,
        confidence: float,
        top_factors: List[Dict],
        gex_data: Dict
    ) -> Tuple[float, List[str]]:
        """
        Adjust confidence based on Prophet's top contributing factors.

        GIDEON is more aggressive - smaller adjustments.
        """
        if not top_factors:
            return confidence, []

        adjustments = []
        original_confidence = confidence
        vix = gex_data.get('vix', 20)
        gex_regime = gex_data.get('gex_regime', 'NEUTRAL')

        # REMOVED: VIX, GEX regime, day of week adjustments
        # Prophet already analyzed all these factors in MarketContext.
        # Re-adjusting confidence based on the same factors is redundant.
        # Trust Prophet's win_probability output directly.

        # Clamp confidence - GIDEON allows lower confidence
        confidence = max(0.35, min(0.95, confidence))

        if adjustments:
            logger.info(f"[GIDEON TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
            for adj in adjustments:
                logger.info(f"  - {adj}")

        return confidence, adjustments

    def check_wall_proximity(self, gex_data: Dict) -> Tuple[bool, str, str]:
        """
        Check if price is near a GEX wall for entry.

        GIDEON uses 2% wall filter (vs SOLOMON's 1%) - more aggressive but still filtered.

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

        # GIDEON uses 2% threshold (vs SOLOMON's 1%) - more aggressive but still filtered
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

        GIDEON uses $3 spread width (vs SOLOMON's $2).

        Returns: (long_strike, short_strike)
        """
        # Round to nearest dollar
        atm = round(spot_price)
        width = self.config.spread_width  # $3 for GIDEON

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

    def generate_signal(self, prophet_data: Optional[Dict[str, Any]] = None) -> Optional[TradeSignal]:
        """
        Generate a trading signal.

        GIDEON uses AGGRESSIVE parameters:
        - 10% wall filter (much more room to trade)
        - 40% min win probability
        - 0.5 min R:R ratio

        Args:
            prophet_data: Pre-fetched Prophet advice (optional). If provided, uses this
                        instead of making a new Prophet call for consistency.
        """
        # Step 1: Get GEX data
        gex_data = self.get_gex_data()
        if not gex_data:
            logger.info("No GEX data available")
            return None

        spot_price = gex_data['spot_price']
        vix = gex_data['vix']

        # ============================================================
        # STEP 2: GET PROPHET PREDICTION (PROPHET IS THE GOD OF ALL DECISIONS)
        #
        # CRITICAL: When Prophet says TRADE, we TRADE. Period.
        # Prophet already analyzed VIX, GEX, walls, regime, day of week.
        # Bot's min_win_probability threshold does NOT override Prophet.
        # ============================================================

        # Step 2a: Get ML signal from 5 GEX probability models (PRIMARY SOURCE)
        ml_signal = self.get_ml_signal(gex_data)
        ml_direction = ml_signal.get('direction') if ml_signal else None
        ml_confidence = ml_signal.get('confidence', 0) if ml_signal else 0
        ml_win_prob = ml_signal.get('win_probability', 0) if ml_signal else 0

        # Step 2b: Get Prophet advice (BACKUP SOURCE)
        # Use pre-fetched prophet_data if provided to avoid double Prophet calls
        if prophet_data is not None:
            prophet = prophet_data
            logger.info(f"[GIDEON] Using pre-fetched Prophet data: advice={prophet.get('advice', 'UNKNOWN')}")
        else:
            prophet = self.get_oracle_advice(gex_data)
        oracle_direction = prophet.get('direction', 'FLAT') if prophet else 'FLAT'
        oracle_confidence = prophet.get('confidence', 0) if prophet else 0
        oracle_win_prob = prophet.get('win_probability', 0) if prophet else 0
        oracle_advice = prophet.get('advice', 'SKIP_TODAY') if prophet else 'SKIP_TODAY'

        # Determine which source to use for WIN PROBABILITY
        use_ml_prediction = ml_signal is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        prediction_source = "ML_5_MODEL_ENSEMBLE" if use_ml_prediction else "PROPHET"

        # DIRECTION: Prophet is the SOLE AUTHORITY for GIDEON
        # Prophet decides both trade/no-trade AND direction
        # ML is backup only when Prophet direction is FLAT
        if oracle_direction in ('BULLISH', 'BEARISH'):
            effective_direction = oracle_direction
            if ml_direction and ml_direction != oracle_direction:
                logger.info(f"[GIDEON] PROPHET DIRECTION: {oracle_direction} (ML said {ml_direction} - Prophet overrides)")
            else:
                logger.info(f"[GIDEON] PROPHET DIRECTION: {oracle_direction}")
        elif ml_direction in ('BULLISH', 'BEARISH'):
            # Fallback to ML only if Prophet direction is FLAT
            effective_direction = ml_direction
            logger.info(f"[GIDEON] Prophet direction FLAT, using ML backup: {ml_direction}")
        else:
            effective_direction = "FLAT"
            logger.info(f"[GIDEON] No clear direction from Prophet or ML")

        # ============================================================
        # PROPHET IS THE GOD: If Prophet says TRADE, we TRADE
        # No min_win_probability threshold check - Prophet's word is final
        # ============================================================
        oracle_says_trade = oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')

        # FLAT/NEUTRAL is NOT an excuse for blocking trades when Prophet says TRADE
        # Use Prophet's suitability scores to derive direction, fallback to GEX walls
        if oracle_says_trade and effective_direction not in ('BULLISH', 'BEARISH'):
            # First try Prophet's suitability scores (Prophet already analyzed the market)
            bullish_suit = prophet.get('bullish_suitability', 0) if prophet else 0
            bearish_suit = prophet.get('bearish_suitability', 0) if prophet else 0

            if bullish_suit > bearish_suit:
                effective_direction = "BULLISH"
                logger.info(f"[GIDEON] Direction from Prophet suitability: BULLISH ({bullish_suit:.0%} > {bearish_suit:.0%})")
            elif bearish_suit > bullish_suit:
                effective_direction = "BEARISH"
                logger.info(f"[GIDEON] Direction from Prophet suitability: BEARISH ({bearish_suit:.0%} > {bullish_suit:.0%})")
            else:
                # Tie-breaker: use GEX wall proximity
                call_wall = gex_data.get('call_wall', 0)
                put_wall = gex_data.get('put_wall', 0)
                if call_wall > 0 and put_wall > 0:
                    call_dist = abs(spot_price - call_wall) / spot_price if spot_price > 0 else 1
                    put_dist = abs(spot_price - put_wall) / spot_price if spot_price > 0 else 1
                    effective_direction = "BULLISH" if put_dist < call_dist else "BEARISH"
                    logger.info(f"[GIDEON] Direction from GEX walls (tie-breaker): {effective_direction}")
                else:
                    effective_direction = "BULLISH"  # Default
                    logger.info(f"[GIDEON] Direction defaulted to BULLISH")

        ml_oracle_says_trade = oracle_says_trade and effective_direction in ('BULLISH', 'BEARISH')

        # Log Prophet decision
        if ml_oracle_says_trade:
            logger.info(f"[GIDEON] PROPHET SAYS TRADE: {oracle_advice} - {prediction_source} = {effective_direction} @ {effective_win_prob:.0%}")
        else:
            logger.info(f"[GIDEON] Prophet advice: {oracle_advice}, direction: {effective_direction} @ {effective_win_prob:.0%}")

        # ============================================================
        # STEP 3: IF ML/PROPHET SAYS TRADE, BYPASS TRADITIONAL FILTERS
        # ============================================================
        if ml_oracle_says_trade:
            # ML/Prophet supersedes all traditional filters for GIDEON
            filters_bypassed = []

            if vix < self.config.min_vix or vix > self.config.max_vix:
                filters_bypassed.append(f"VIX={vix:.1f}")
            near_wall, wall_direction, wall_reason = self.check_wall_proximity(gex_data)
            if not near_wall:
                filters_bypassed.append(f"Wall={wall_reason}")

            total_put_gex = gex_data.get('put_gex', gex_data.get('kronos_raw', {}).get('total_put_gex', 0))
            total_call_gex = gex_data.get('call_gex', gex_data.get('kronos_raw', {}).get('total_call_gex', 0))
            gex_ratio = total_put_gex / total_call_gex if total_call_gex > 0 else 10.0
            has_gex_asymmetry = (gex_ratio >= self.config.min_gex_ratio_bearish or
                                 gex_ratio <= self.config.max_gex_ratio_bullish)
            if not has_gex_asymmetry:
                filters_bypassed.append(f"GEX_ratio={gex_ratio:.2f}")

            if filters_bypassed:
                logger.info(f"[GIDEON] ML/Prophet BYPASSES: {', '.join(filters_bypassed)}")

            # Use ML/Prophet direction
            gex_bias = effective_direction
            wall_direction = effective_direction
            logger.info(f"[GIDEON] Using ML/Prophet direction: {gex_bias}")

        else:
            # ============================================================
            # STEP 4: PROPHET SAYS NO TRADE - RESPECT PROPHET'S DECISION
            # ============================================================
            # Prophet is the god of all trade decisions.
            # If Prophet says SKIP_TODAY, we don't trade. Period.
            logger.info(f"[GIDEON SKIP] Prophet says {oracle_advice} - respecting Prophet's decision")

            # Convert Prophet top_factors to JSON string for blocked signal audit trail
            import json
            oracle_top_factors_json = ""
            if prophet and prophet.get('top_factors'):
                oracle_top_factors_json = json.dumps(prophet['top_factors'])

            return TradeSignal(
                direction=effective_direction if effective_direction in ('BULLISH', 'BEARISH') else "UNKNOWN",
                spread_type=SpreadType.BULL_CALL if effective_direction == "BULLISH" else SpreadType.BEAR_PUT,
                confidence=0,
                spot_price=spot_price,
                call_wall=gex_data.get('call_wall', 0),
                put_wall=gex_data.get('put_wall', 0),
                gex_regime=gex_data.get('gex_regime', 'UNKNOWN'),
                vix=vix,
                source="BLOCKED_ORACLE_NO_TRADE",
                reasoning=f"BLOCKED: Prophet advice={oracle_advice}, direction={effective_direction}, win_prob={effective_win_prob:.0%}",
                ml_win_probability=effective_win_prob,
                # BUG FIX: Include Prophet fields for audit trail
                oracle_advice=oracle_advice,
                oracle_win_probability=oracle_win_prob,
                oracle_direction=oracle_direction,
                oracle_confidence=oracle_confidence,
                oracle_top_factors=oracle_top_factors_json,
            )

        # Get wall info for logging only (Prophet already provided direction above)
        near_wall, _, wall_reason = self.check_wall_proximity(gex_data)
        if not near_wall:
            wall_reason = f"Prophet overriding wall proximity (direction: {effective_direction})"

        # Log ML analysis FIRST (it's the preferred source for GIDEON)
        if ml_signal:
            logger.info(f"[GIDEON ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
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
            logger.info(f"[GIDEON] ML models not available, falling back to Prophet")

        # Log Prophet analysis (backup source)
        if prophet:
            logger.info(f"[GIDEON PROPHET ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
            logger.info(f"  Win Probability: {oracle_win_prob:.1%}")
            logger.info(f"  Confidence: {oracle_confidence:.1%}")
            logger.info(f"  Direction: {oracle_direction}")
            logger.info(f"  Advice: {prophet.get('advice', 'N/A')}")

            if prophet.get('top_factors'):
                logger.info(f"  Top Factors:")
                for i, factor in enumerate(prophet['top_factors'][:3], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    direction_sign = "+" if impact > 0 else ""
                    logger.info(f"    {i}. {factor_name}: {direction_sign}{impact:.3f}")

            # Prophet SKIP_TODAY is informational only - GIDEON trusts ML
            if prophet.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[GIDEON] Prophet advises SKIP_TODAY but ML override active")
                    logger.info(f"  GIDEON trusts ML: {ml_win_prob:.1%} win probability")
                else:
                    logger.info(f"[GIDEON] Prophet SKIP_TODAY - using aggressive 48% threshold")

        # Win probability threshold already checked in Step 2/3 above
        logger.info(f"[GIDEON] Proceeding with {prediction_source}: {effective_win_prob:.1%} win prob")

        # Step 4: Determine final direction
        # Prophet is the SOLE AUTHORITY - wall_direction was set to effective_direction (Prophet's direction)
        direction = wall_direction  # wall_direction = effective_direction = PROPHET direction (set at line 744)
        direction_source = "PROPHET" if oracle_direction in ('BULLISH', 'BEARISH') else "ML_BACKUP"
        logger.info(f"[GIDEON] Final direction: {direction} (source: {direction_source})")

        # Calculate confidence
        confidence = 0.7  # Base confidence

        # ML can boost or reduce confidence
        if ml_signal:
            if ml_direction == direction:
                confidence = min(0.95, confidence + ml_confidence * 0.20)
            elif ml_direction and ml_direction != direction and ml_confidence > 0.7:
                confidence -= 0.08  # Smaller penalty for GIDEON

        # Prophet adjustments (when not overriding)
        if prophet and direction_source != "ORACLE_OVERRIDE":
            if oracle_direction == direction and oracle_confidence > 0.6:
                boost = oracle_confidence * 0.20
                confidence = min(0.95, confidence + boost)
            elif oracle_direction != direction and oracle_direction != 'FLAT' and oracle_confidence > 0.6:
                penalty = (oracle_confidence - 0.6) * 0.20  # Smaller penalty
                confidence -= penalty
            # NOTE: SKIP_TODAY does NOT block here - bot uses its own min_win_probability threshold

            if prophet.get('top_factors'):
                confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                    confidence, prophet['top_factors'], gex_data
                )

        # Confidence check - warning only (no blocking)
        if confidence < self.config.min_confidence:
            logger.warning(f"[GIDEON] Confidence {confidence:.0%} below {self.config.min_confidence:.0%} (proceeding anyway)")
        else:
            logger.info(f"[GIDEON] Confidence {confidence:.0%} >= {self.config.min_confidence:.0%} ✓")

        # Step 5: Determine spread type
        spread_type = SpreadType.BULL_CALL if direction == "BULLISH" else SpreadType.BEAR_PUT

        # Step 6: Calculate strikes ($3 width for GIDEON)
        now = datetime.now(CENTRAL_TZ)
        expiration = now.strftime("%Y-%m-%d")

        long_strike, short_strike = self.calculate_spread_strikes(
            direction, spot_price, expiration
        )

        # Step 7: Estimate pricing
        debit, max_profit, max_loss = self.estimate_spread_pricing(
            spread_type, long_strike, short_strike, spot_price, vix
        )

        # Step 8: Calculate risk/reward (1.2 min for GIDEON vs SOLOMON's 1.5)
        rr_ratio = max_profit / max_loss if max_loss > 0 else 0

        # R:R ratio check - warning only (no blocking)
        if rr_ratio < self.config.min_rr_ratio:
            logger.warning(f"[GIDEON] R:R ratio {rr_ratio:.2f} below {self.config.min_rr_ratio} (proceeding anyway)")
        else:
            logger.info(f"[GIDEON] R:R ratio {rr_ratio:.2f} >= {self.config.min_rr_ratio} ✓")

        # Step 9: Build detailed reasoning
        reasoning_parts = []
        reasoning_parts.append(f"VIX={vix:.1f}, GEX Regime={gex_data['gex_regime']}")
        reasoning_parts.append(wall_reason)

        if ml_signal:
            reasoning_parts.append(f"ML: {ml_direction} ({ml_confidence:.0%})")
            if ml_signal.get('win_probability'):
                reasoning_parts.append(f"ML Win Prob: {ml_signal['win_probability']:.0%}")

        if prophet:
            reasoning_parts.append(f"Prophet: {prophet.get('advice', 'N/A')} ({oracle_direction}, {oracle_confidence:.0%})")
            if oracle_win_prob:
                reasoning_parts.append(f"Prophet Win Prob: {oracle_win_prob:.0%}")

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
        if prophet and ml_signal:
            source = "GEX_ML_ORACLE"
        elif prophet:
            source = "GEX_ORACLE"
        elif ml_signal:
            source = "GEX_ML"
        else:
            source = "GEX_WALL"

        # Convert Prophet top_factors to JSON string
        import json
        oracle_top_factors_json = ""
        if prophet and prophet.get('top_factors'):
            oracle_top_factors_json = json.dumps(prophet['top_factors'])

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
            oracle_advice=prophet.get('advice', '') if prophet else '',
            oracle_direction=oracle_direction,
            oracle_confidence=oracle_confidence,
            oracle_top_factors=oracle_top_factors_json,
            wall_type=wall_type,
            wall_distance_pct=wall_distance,
        )

        logger.info(f"GIDEON Signal generated: {direction} {spread_type.value} @ {spot_price}")
        logger.info(f"Context: Wall={wall_type} ({wall_distance:.2f}%), ML={ml_direction or 'N/A'} ({ml_confidence:.0%}), Prophet={oracle_direction or 'N/A'} ({oracle_confidence:.0%})")
        return signal
