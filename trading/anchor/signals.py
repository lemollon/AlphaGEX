"""
ANCHOR - Signal Generation
=============================

Signal generation for SPX Iron Condors.
Uses $5 strike increments and larger expected moves.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List

from .models import IronCondorSignal, AnchorConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Prophet is the god of all trade decisions

# Optional imports
try:
    from quant.prophet_advisor import ProphetAdvisor
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None

try:
    from quant.fortress_ml_advisor import FortressMLAdvisor
    FORTRESS_ML_AVAILABLE = True
except ImportError:
    FORTRESS_ML_AVAILABLE = False
    FortressMLAdvisor = None

try:
    from quant.chronicles_gex_calculator import ChroniclesGEXCalculator
    CHRONICLES_AVAILABLE = True
except ImportError:
    CHRONICLES_AVAILABLE = False
    ChroniclesGEXCalculator = None

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

# REMOVED: GEX Directional ML - redundant with Prophet


class SignalGenerator:
    """Generates SPX Iron Condor signals"""

    def __init__(self, config: AnchorConfig):
        self.config = config
        self._init_components()
        self._init_tradier()

    def _init_components(self) -> None:
        # GEX Calculator - Use Tradier for LIVE trading data
        # Chronicles uses ORAT database (EOD) - only for backtesting, NOT live trading
        self.gex_calculator = None

        if TRADIER_GEX_AVAILABLE:
            try:
                # CRITICAL: SPX requires production API (sandbox doesn't support SPX)
                from data.gex_calculator import TradierGEXCalculator
                tradier_calc = TradierGEXCalculator(sandbox=False)
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"ANCHOR: Using Tradier GEX for LIVE trading (spot={test_result.get('spot_price')})")
                else:
                    logger.error("ANCHOR: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"ANCHOR: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("ANCHOR: NO GEX CALCULATOR AVAILABLE - Tradier required for live trading")

        # FORTRESS ML Advisor (PRIMARY - Iron Condor ML model with ~70% win rate)
        self.fortress_ml = None
        if FORTRESS_ML_AVAILABLE:
            try:
                self.fortress_ml = FortressMLAdvisor()
                if self.fortress_ml.is_trained:
                    logger.info(f"ANCHOR: ML Advisor v{self.fortress_ml.model_version} loaded (PRIMARY)")
                else:
                    logger.info("ANCHOR: ML Advisor initialized (not yet trained)")
            except Exception as e:
                logger.warning(f"ANCHOR: ML Advisor init failed: {e}")

        # Prophet (BACKUP - used when ML not available)
        self.prophet = None
        if PROPHET_AVAILABLE:
            try:
                self.prophet = ProphetAdvisor()
                logger.info("ANCHOR: Prophet initialized (BACKUP)")
            except Exception as e:
                logger.warning(f"ANCHOR: Prophet init failed: {e}")

    def _init_tradier(self) -> None:
        """Initialize Tradier for real option quotes.

        CRITICAL: Use production API for SPX (sandbox doesn't support SPX).
        This enables real bid/ask quotes for accurate credit estimation.
        """
        self.tradier = None
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            # Use production API for SPX quotes (sandbox doesn't support SPX)
            self.tradier = TradierDataFetcher(sandbox=False)
            # Test connectivity
            test_quote = self.tradier.get_quote("SPX")
            if test_quote and test_quote.get('last', 0) > 0:
                logger.info(f"ANCHOR: Tradier production API connected (SPX=${test_quote.get('last', 0):.2f})")
            else:
                logger.warning("ANCHOR: Tradier connected but SPX quote unavailable")
        except Exception as e:
            logger.warning(f"ANCHOR: Tradier init failed, using estimated credits: {e}")
            self.tradier = None


    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Get SPX market data"""
        try:
            # GEX data (fetch first - it has spot_price from production API)
            gex_data = self._get_gex_data()

            # CRITICAL: Use spot_price from GEX calculator FIRST (uses production API for SPX)
            # The global get_price() uses sandbox which doesn't support SPX
            spot = None
            if gex_data:
                spot = gex_data.get('spot_price', 0)
                # Scale if from SPY
                if gex_data.get('from_spy', False) and spot > 0 and spot < 1000:
                    spot = spot * 10

            # Fallback to get_price() only if GEX calc didn't return spot
            if not spot and DATA_AVAILABLE:
                spot = get_price("SPX")
                if not spot:
                    # Fallback: SPY * 10 approximation
                    spy = get_price("SPY")
                    if spy:
                        spot = spy * 10

            if not spot:
                logger.warning("ANCHOR: No spot price available from GEX calc or price API")
                return None

            vix = 20.0
            if DATA_AVAILABLE:
                try:
                    fetched_vix = get_vix()
                    if fetched_vix and fetched_vix >= 10:
                        vix = fetched_vix
                except Exception as e:
                    logger.debug(f"VIX fetch failed, using default: {e}")

            expected_move = self._calculate_expected_move(spot, vix)
            # Ensure minimum expected move (0.5% of spot)
            min_em = spot * 0.005
            if expected_move < min_em:
                expected_move = min_em

            # Only scale GEX walls by 10 if data came from SPY (not SPX)
            scale = 10 if (gex_data and gex_data.get('from_spy', False)) else 1

            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0) * scale if gex_data else 0,
                'put_wall': gex_data.get('put_wall', 0) * scale if gex_data else 0,
                'gex_regime': gex_data.get('regime', 'NEUTRAL') if gex_data else 'NEUTRAL',
                # Chronicles GEX context (scaled if from SPY)
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

            # ChroniclesGEXCalculator uses get_gex_for_today_or_recent() - returns SPX data
            if CHRONICLES_AVAILABLE and hasattr(self.gex_calculator, 'get_gex_for_today_or_recent'):
                gex_data, source = self.gex_calculator.get_gex_for_today_or_recent()
                if gex_data:
                    # ChroniclesGEXCalculator returns GEXData dataclass, convert to dict
                    gex = {
                        'call_wall': getattr(gex_data, 'major_call_wall', 0) or 0,
                        'put_wall': getattr(gex_data, 'major_put_wall', 0) or 0,
                        'regime': getattr(gex_data, 'regime', 'NEUTRAL') or 'NEUTRAL',
                        'flip_point': getattr(gex_data, 'gamma_flip', 0) or 0,
                        'net_gex': getattr(gex_data, 'net_gex', 0) or 0,
                    }
                    from_spy = False  # Chronicles uses SPX options data

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
                    # Chronicles GEX context for audit
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
        Get prediction from FORTRESS ML Advisor (PRIMARY source for Iron Condors).

        This model was trained on CHRONICLES backtests with ~70% win rate.
        It takes precedence over Prophet for trading decisions.
        """
        if not self.fortress_ml:
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

            prediction = self.fortress_ml.predict(
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
            logger.warning(f"ANCHOR ML prediction error: {e}")

        return None

    def get_prophet_advice(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Prophet prediction with FULL context for audit trail (BACKUP SOURCE).

        Uses get_anchor_advice() for SPX Iron Condor specific advice.
        Returns dict with: confidence, win_probability, advice, top_factors, etc.
        """
        if not self.prophet:
            return None

        try:
            # Build MarketContext for Prophet
            from quant.prophet_advisor import MarketContext, GEXRegime

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

            # Call ANCHOR-specific advice method
            prediction = self.prophet.get_anchor_advice(
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
            logger.warning(f"ANCHOR Prophet error: {e}")
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
        Adjust confidence based on Prophet's top contributing factors.

        The top_factors reveal which features most influenced Prophet's prediction.
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
        # Prophet already analyzed all these factors in MarketContext.
        # Re-adjusting confidence based on the same factors is redundant.
        # Trust Prophet's win_probability output directly.

        # Clamp confidence to reasonable range
        confidence = max(0.4, min(0.95, confidence))

        if adjustments:
            logger.info(f"[ANCHOR TOP_FACTORS ADJUSTMENTS] {original_confidence:.0%} -> {confidence:.0%}")
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
        """Calculate SPX strikes with $5 rounding and MINIMUM 1 SD distance.

        ANCHOR RULE: Strikes must ALWAYS be at least 1 SD from spot.
        GEX walls and Prophet suggestions are only used if they are >= 1 SD away.
        This prevents tight strikes that can blow up the account.

        Priority:
        1. Prophet suggested strikes (if provided and valid AND >= 1 SD away)
        2. GEX walls (if available AND >= 1 SD away)
        3. SD-based strikes (guaranteed 1 SD minimum)
        """
        sd = self.config.sd_multiplier
        width = self.config.spread_width

        def round_to_5(x):
            return round(x / 5) * 5

        # Ensure minimum expected move (0.5% of spot)
        min_expected_move = spot * 0.005
        effective_em = max(expected_move, min_expected_move)

        # Calculate MINIMUM strike distances (1 SD from spot)
        min_put_short = spot - effective_em  # 1 SD below spot
        min_call_short = spot + effective_em  # 1 SD above spot

        use_oracle = False
        use_gex = False

        # Priority 1: Prophet suggested strikes (ONLY if >= 1 SD away)
        if oracle_put_strike and oracle_call_strike:
            # Check if Prophet strikes are at least 1 SD away from spot
            oracle_put_ok = oracle_put_strike <= min_put_short
            oracle_call_ok = oracle_call_strike >= min_call_short
            if oracle_put_ok and oracle_call_ok:
                put_short = round_to_5(oracle_put_strike)
                call_short = round_to_5(oracle_call_strike)
                use_oracle = True
                logger.info(f"[ANCHOR STRIKES] Using Prophet: put={put_short}, call={call_short} (>= 1 SD)")
            else:
                logger.info(f"[ANCHOR STRIKES] Prophet strikes too tight (put={oracle_put_strike}, call={oracle_call_strike}), using SD-based")

        # Priority 2: GEX walls (ONLY if >= 1 SD away)
        if not use_oracle and call_wall > 0 and put_wall > 0:
            gex_put_ok = put_wall <= min_put_short
            gex_call_ok = call_wall >= min_call_short
            if gex_put_ok and gex_call_ok:
                put_short = round_to_5(put_wall)
                call_short = round_to_5(call_wall)
                use_gex = True
                logger.info(f"[ANCHOR STRIKES] Using GEX walls: put={put_short}, call={call_short} (>= 1 SD)")
            else:
                logger.info(f"[ANCHOR STRIKES] GEX walls too tight (put={put_wall}, call={call_wall}), using SD-based")

        # Priority 3: SD-based (guaranteed minimum 1 SD)
        if not use_oracle and not use_gex:
            put_short = round_to_5(spot - sd * effective_em)
            call_short = round_to_5(spot + sd * effective_em)
            logger.info(f"[ANCHOR STRIKES] Using {sd} SD: put={put_short}, call={call_short}")

        put_long = put_short - width
        call_long = call_short + width

        return {
            'put_short': put_short,
            'put_long': put_long,
            'call_short': call_short,
            'call_long': call_long,
            'using_gex': use_gex,
            'using_oracle': use_oracle,
            'source': 'PROPHET' if use_oracle else ('GEX' if use_gex else 'SD'),
        }

    def get_real_credits(
        self,
        expiration: str,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
    ) -> Optional[Dict[str, float]]:
        """
        Get REAL option credits from Tradier production API.

        This fetches actual bid/ask quotes for SPX options to get accurate
        credit values instead of using formula estimation.

        Returns:
            Dict with put_credit, call_credit, total_credit, etc. or None if unavailable
        """
        if not self.tradier:
            logger.debug("ANCHOR: Tradier not available, cannot get real credits")
            return None

        try:
            # Build OCC symbols for each leg
            # SPXW uses weekly format: SPXW + YYMMDD + C/P + Strike*1000 (8 digits)
            from datetime import datetime as dt
            exp_date = dt.strptime(expiration, '%Y-%m-%d')
            exp_str = exp_date.strftime('%y%m%d')

            def build_symbol(strike: float, opt_type: str) -> str:
                strike_str = f"{int(strike * 1000):08d}"
                return f"SPXW{exp_str}{opt_type}{strike_str}"

            put_short_sym = build_symbol(put_short, 'P')
            put_long_sym = build_symbol(put_long, 'P')
            call_short_sym = build_symbol(call_short, 'C')
            call_long_sym = build_symbol(call_long, 'C')

            # Get quotes for all four legs
            put_short_quote = self.tradier.get_option_quote(put_short_sym)
            put_long_quote = self.tradier.get_option_quote(put_long_sym)
            call_short_quote = self.tradier.get_option_quote(call_short_sym)
            call_long_quote = self.tradier.get_option_quote(call_long_sym)

            # Check if all quotes are valid
            if not all([put_short_quote, put_long_quote, call_short_quote, call_long_quote]):
                logger.warning(f"ANCHOR: Missing option quotes for {expiration}")
                return None

            # Calculate spread credits
            # Put spread: sell short put, buy long put
            # We receive: bid of short - ask of long
            put_short_bid = float(put_short_quote.get('bid', 0) or 0)
            put_long_ask = float(put_long_quote.get('ask', 0) or 0)
            put_credit = put_short_bid - put_long_ask

            # Call spread: sell short call, buy long call
            call_short_bid = float(call_short_quote.get('bid', 0) or 0)
            call_long_ask = float(call_long_quote.get('ask', 0) or 0)
            call_credit = call_short_bid - call_long_ask

            # Validate credits are positive (we should receive credit for IC)
            if put_credit <= 0 or call_credit <= 0:
                logger.warning(f"ANCHOR: Invalid credits - put=${put_credit:.2f}, call=${call_credit:.2f}")
                # Try using mid prices as fallback
                put_short_mid = (put_short_bid + float(put_short_quote.get('ask', 0) or 0)) / 2
                put_long_mid = (float(put_long_quote.get('bid', 0) or 0) + put_long_ask) / 2
                call_short_mid = (call_short_bid + float(call_short_quote.get('ask', 0) or 0)) / 2
                call_long_mid = (float(call_long_quote.get('bid', 0) or 0) + call_long_ask) / 2

                put_credit = max(0, put_short_mid - put_long_mid)
                call_credit = max(0, call_short_mid - call_long_mid)

            total = put_credit + call_credit
            width = self.config.spread_width
            max_profit = total * 100
            max_loss = (width - total) * 100

            logger.info(f"ANCHOR: REAL QUOTES - Put spread ${put_credit:.2f}, Call spread ${call_credit:.2f}, Total ${total:.2f}")

            return {
                'put_credit': round(put_credit, 2),
                'call_credit': round(call_credit, 2),
                'total_credit': round(total, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2),
                'source': 'TRADIER_LIVE',
            }

        except Exception as e:
            logger.warning(f"ANCHOR: Failed to get real credits: {e}")
            return None

    def estimate_credits(self, spot: float, expected_move: float, put_short: float, call_short: float, vix: float) -> Dict[str, float]:
        """
        Estimate SPX IC credits (FALLBACK when Tradier unavailable).

        NOTE: This is a rough estimate. Real trading should use get_real_credits()
        which fetches actual bid/ask from Tradier API.
        """
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
            'source': 'ESTIMATED',
        }

    def generate_signal(self, prophet_data: Optional[Dict[str, Any]] = None) -> Optional[IronCondorSignal]:
        """Generate SPX Iron Condor signal with FULL Prophet/Chronicles context

        Args:
            prophet_data: Pre-fetched Prophet advice (optional). If provided, uses this
                        instead of making a new Prophet call for consistency.
        """
        market = self.get_market_data()
        if not market:
            return None

        vix = market['vix']

        # ============================================================
        # ML/PROPHET PREDICTIONS FIRST (SUPERSEDES VIX FILTER)
        #
        # CRITICAL: Prophet and ML already account for VIX in their predictions.
        # If ML/Prophet provides a good win probability, we TRADE regardless of VIX.
        # ============================================================

        # Get ML prediction first (PRIMARY SOURCE)
        ml_prediction = self.get_ml_prediction(market)
        ml_win_prob = ml_prediction.get('win_probability', 0) if ml_prediction else 0
        ml_confidence = ml_prediction.get('confidence', 0) if ml_prediction else 0

        # Get Prophet advice (BACKUP SOURCE)
        # Use pre-fetched prophet_data if provided to avoid double Prophet calls
        if prophet_data is not None:
            prophet = prophet_data
            logger.info(f"[ANCHOR] Using pre-fetched Prophet data: advice={prophet.get('advice', 'UNKNOWN')}")
        else:
            prophet = self.get_prophet_advice(market)
        oracle_win_prob = prophet.get('win_probability', 0) if prophet else 0
        oracle_confidence = prophet.get('confidence', 0.7) if prophet else 0.7

        # Determine which source to use
        use_ml_prediction = ml_prediction is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        confidence = ml_confidence if use_ml_prediction else oracle_confidence
        prediction_source = "ARES_ML_ADVISOR" if use_ml_prediction else "PROPHET"

        # Check if ML/Prophet gives us a tradeable signal
        min_win_prob = self.config.min_win_probability
        ml_oracle_says_trade = effective_win_prob >= min_win_prob

        # Log ML/Prophet decision
        if ml_oracle_says_trade:
            logger.info(f"[ANCHOR] ML/Prophet SUPERSEDES VIX filter: {prediction_source} = {effective_win_prob:.0%} (>={min_win_prob:.0%})")
            # Check what VIX would have done (for logging only)
            can_trade, vix_reason = self.check_vix_filter(vix)
            if not can_trade:
                logger.info(f"[ANCHOR] VIX would have blocked ({vix_reason}) but ML/Prophet supersedes")
        else:
            logger.info(f"[ANCHOR] ML/Prophet: {effective_win_prob:.0%} (threshold: {min_win_prob:.0%})")
            # Only apply VIX filter if ML/Prophet doesn't give tradeable signal
            can_trade, vix_reason = self.check_vix_filter(vix)
            if not can_trade:
                logger.info(f"[ANCHOR SKIP] VIX filter: {vix_reason}, ML/Prophet also insufficient")
                return None

            # REMOVED: Market conditions fallback baseline
            # If Prophet returns 0 win probability, trust that decision.
            # Don't manufacture a baseline - Prophet already analyzed VIX, GEX, etc.
            if effective_win_prob <= 0:
                logger.info(f"[ANCHOR BLOCKED] ML/Prophet returned 0 win probability - no trade signal")
                return None

        # Log ML analysis FIRST (PRIMARY source)
        if ml_prediction:
            logger.info(f"[ANCHOR ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
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
            logger.info(f"[ANCHOR] ML Advisor not available, falling back to Prophet")

        # Log Prophet analysis (BACKUP source)
        if prophet:
            logger.info(f"[ANCHOR PROPHET ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
            logger.info(f"  Win Probability: {oracle_win_prob:.1%}")
            logger.info(f"  Confidence: {oracle_confidence:.1%}")
            logger.info(f"  Advice: {prophet.get('advice', 'N/A')}")

            if prophet.get('top_factors'):
                logger.info(f"  Top Factors:")
                for i, factor in enumerate(prophet['top_factors'][:3], 1):
                    factor_name = factor.get('factor', 'unknown')
                    impact = factor.get('impact', 0)
                    direction = "+" if impact > 0 else ""
                    logger.info(f"    {i}. {factor_name}: {direction}{impact:.3f}")

                if not use_ml_prediction:
                    oracle_confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                        oracle_confidence, prophet['top_factors'], market
                    )
                    confidence = oracle_confidence

            if prophet.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[ANCHOR] Prophet advises SKIP_TODAY but ML override active")
                    logger.info(f"  ML Win Prob: {ml_win_prob:.1%} will be used instead")
                else:
                    logger.info(f"[ANCHOR PROPHET INFO] Prophet advises SKIP_TODAY (informational only)")
                    logger.info(f"  Bot will use its own threshold: {self.config.min_win_probability:.1%}")

        # Win probability threshold check - enforce minimum win probability
        min_win_prob = getattr(self.config, 'min_win_probability', 0.42)
        logger.info(f"[ANCHOR DECISION] Using {prediction_source} win probability: {effective_win_prob:.1%}")
        logger.info(f"[ANCHOR THRESHOLD] Minimum required: {min_win_prob:.1%}")

        if effective_win_prob < min_win_prob:
            logger.info(f"[ANCHOR BLOCKED] Win probability {effective_win_prob:.1%} < threshold {min_win_prob:.1%}")

            # Convert Prophet top_factors to list for blocked signal audit trail
            oracle_top_factors = prophet.get('top_factors', []) if prophet else []

            # Return an invalid signal with the reason - include Prophet fields for audit trail
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
                # BUG FIX: Include Prophet fields for audit trail
                oracle_win_probability=oracle_win_prob,
                oracle_advice=prophet.get('advice', '') if prophet else '',
                oracle_top_factors=oracle_top_factors,
                oracle_suggested_sd=prophet.get('suggested_sd_multiplier', 1.0) if prophet else 1.0,
                oracle_use_gex_walls=prophet.get('use_gex_walls', False) if prophet else False,
                oracle_probabilities=prophet.get('probabilities', {}) if prophet else {},
            )

        if effective_win_prob <= 0:
            effective_win_prob = 0.50  # Default to 50% if no prediction
        logger.info(f"[ANCHOR PASSED] {prediction_source} Win Prob {effective_win_prob:.1%} >= threshold {min_win_prob:.1%}")

        # Get Prophet suggested strikes if available
        oracle_put = prophet.get('suggested_put_strike') if prophet else None
        oracle_call = prophet.get('suggested_call_strike') if prophet else None
        strikes = self.calculate_strikes(
            market['spot_price'],
            market['expected_move'],
            market['call_wall'],
            market['put_wall'],
            oracle_put_strike=oracle_put,
            oracle_call_strike=oracle_call,
        )

        # Calculate expiration for SPXW weekly options (next Friday)
        # Need this early for real quote fetching
        now = datetime.now(CENTRAL_TZ)
        days_until_friday = (4 - now.weekday()) % 7  # Friday is weekday 4
        if days_until_friday == 0 and now.hour >= 15:
            # It's Friday after 3 PM, use next Friday
            days_until_friday = 7
        expiration_date = now + timedelta(days=days_until_friday)
        expiration = expiration_date.strftime("%Y-%m-%d")

        # Try to get REAL quotes from Tradier first
        pricing = self.get_real_credits(
            expiration=expiration,
            put_short=strikes['put_short'],
            put_long=strikes['put_long'],
            call_short=strikes['call_short'],
            call_long=strikes['call_long'],
        )

        # Fall back to estimation if real quotes unavailable
        if not pricing:
            logger.info("ANCHOR: Using estimated credits (Tradier unavailable)")
            pricing = self.estimate_credits(
                market['spot_price'],
                market['expected_move'],
                strikes['put_short'],
                strikes['call_short'],
                market['vix'],
            )

        if pricing['total_credit'] < self.config.min_credit:
            logger.warning(f"Credit ${pricing['total_credit']:.2f} < ${self.config.min_credit} ({pricing.get('source', 'UNKNOWN')})")

        # Build detailed reasoning (FULL audit trail)
        reasoning_parts = []
        reasoning_parts.append(f"SPX VIX={market['vix']:.1f}, EM=${market['expected_move']:.0f}")
        if strikes.get('using_oracle'):
            reasoning_parts.append(f"Prophet Strikes")
        elif strikes['using_gex']:
            reasoning_parts.append("GEX-Protected")
        else:
            reasoning_parts.append(f"{self.config.sd_multiplier} SD")

        # Prophet context for reasoning
        if prophet:
            reasoning_parts.append(f"Prophet: {prophet['advice']} ({prophet['confidence']:.0%})")
            if prophet['win_probability']:
                reasoning_parts.append(f"Win Prob: {prophet['win_probability']:.0%}")
            # Add top factor if available
            if prophet['top_factors']:
                top = prophet['top_factors'][0]
                reasoning_parts.append(f"Top Factor: {top['factor']}")

        reasoning = " | ".join(reasoning_parts)

        # Determine confidence (base 0.7, boost with Prophet)
        confidence = 0.7
        if prophet:
            if prophet['advice'] == 'ENTER' and prophet['confidence'] > 0.6:
                confidence = min(0.9, confidence + prophet['confidence'] * 0.2)
            elif prophet['advice'] == 'EXIT':
                confidence -= 0.2

        return IronCondorSignal(
            spot_price=market['spot_price'],
            vix=market['vix'],
            expected_move=market['expected_move'],
            call_wall=market['call_wall'],
            put_wall=market['put_wall'],
            gex_regime=market['gex_regime'],
            # Chronicles GEX context
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
            # Prophet context (CRITICAL for audit)
            oracle_win_probability=prophet['win_probability'] if prophet else 0,
            oracle_advice=prophet['advice'] if prophet else '',
            oracle_confidence=prophet['confidence'] if prophet else 0,
            oracle_top_factors=prophet['top_factors'] if prophet else [],
            oracle_suggested_sd=prophet['suggested_sd_multiplier'] if prophet else 1.0,
            oracle_use_gex_walls=prophet['use_gex_walls'] if prophet else False,
            oracle_probabilities=prophet['probabilities'] if prophet else {},
        )
