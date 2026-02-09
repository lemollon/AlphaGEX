"""
FORTRESS V2 - Signal Generation
=============================

Clean signal generation for Iron Condor trades.
Uses GEX data, Prophet ML, and expected move calculations.

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
    IronCondorSignal, FortressConfig, StrategyPreset,
    STRATEGY_PRESETS, CENTRAL_TZ
)

logger = logging.getLogger(__name__)

# Prophet is the god of all trade decisions
# No config flag needed - Prophet always decides, GEX + VIX is fallback

# Optional imports with fallbacks
try:
    from quant.prophet_advisor import ProphetAdvisor, ProphetPrediction
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None

try:
    from quant.fortress_ml_advisor import FortressMLAdvisor, MLPrediction
    FORTRESS_ML_AVAILABLE = True
except ImportError:
    FORTRESS_ML_AVAILABLE = False
    FortressMLAdvisor = None
    MLPrediction = None

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
    get_gex_calculator = None

try:
    from data.unified_data_provider import get_price, get_vix
    DATA_PROVIDER_AVAILABLE = True
except ImportError:
    DATA_PROVIDER_AVAILABLE = False

# REMOVED: Ensemble Strategy and ML Regime Classifier
# Prophet is the god of all trade decisions. GEX + VIX is the fallback.
# These systems were dead code that only blocked trades unnecessarily.

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
    Generates Iron Condor signals using GEX data and market analysis.
    """

    def __init__(self, config: FortressConfig):
        self.config = config
        self._init_components()
        self._init_tradier()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator - Use Tradier for LIVE trading data
        # Chronicles uses ORAT database (EOD) - only for backtesting, NOT live trading
        self.gex_calculator = None

        if TRADIER_GEX_AVAILABLE:
            try:
                tradier_calc = get_gex_calculator()
                # Verify Tradier works with live data
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"FORTRESS: Using Tradier GEX for LIVE trading (spot={test_result.get('spot_price')})")
                else:
                    logger.error("FORTRESS: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"FORTRESS: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("FORTRESS: NO GEX CALCULATOR AVAILABLE - Tradier required for live trading")

        # FORTRESS ML Advisor (PRIMARY - trained on CHRONICLES backtests with ~70% win rate)
        self.fortress_ml = None
        if FORTRESS_ML_AVAILABLE:
            try:
                self.fortress_ml = FortressMLAdvisor()
                if self.fortress_ml.is_trained:
                    logger.info(f"FORTRESS SignalGenerator: ML Advisor v{self.fortress_ml.model_version} loaded (PRIMARY)")
                else:
                    logger.info("FORTRESS SignalGenerator: ML Advisor initialized (not yet trained)")
            except Exception as e:
                logger.warning(f"FORTRESS ML Advisor init failed: {e}")

        # Prophet Advisor (BACKUP - used when ML not available)
        self.prophet = None
        if PROPHET_AVAILABLE:
            try:
                self.prophet = ProphetAdvisor()
                logger.info("FORTRESS SignalGenerator: Prophet initialized (BACKUP)")
            except Exception as e:
                logger.warning(f"Prophet init failed: {e}")

        # REMOVED: Ensemble Strategy, GEX Directional ML, ML Regime Classifier
        # All redundant - Prophet is the god of all trade decisions

    def _init_tradier(self) -> None:
        """Initialize Tradier for real option quotes.

        FORTRESS uses SPY options which are available on sandbox and production.
        This enables real bid/ask quotes for accurate credit estimation.
        """
        self.tradier = None
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            # SPY works on both sandbox and production
            self.tradier = TradierDataFetcher(sandbox=False)  # Use production for consistency
            # Test connectivity
            test_quote = self.tradier.get_quote("SPY")
            if test_quote and test_quote.get('last', 0) > 0:
                logger.info(f"FORTRESS: Tradier API connected (SPY=${test_quote.get('last', 0):.2f})")
            else:
                logger.warning("FORTRESS: Tradier connected but SPY quote unavailable")
        except Exception as e:
            logger.warning(f"FORTRESS: Tradier init failed, using estimated credits: {e}")
            self.tradier = None


    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Get current market data including price, VIX, and GEX"""
        try:
            # Get GEX data FIRST - it includes spot price from production API
            gex_data = self._get_gex_data()

            # Get spot price - try multiple sources for reliability
            spot = None

            # Source 1: GEX calculator (uses production Tradier API)
            if gex_data and gex_data.get('spot_price', 0) > 0:
                spot = gex_data.get('spot_price')
                logger.debug(f"Using spot price from GEX calculator: ${spot:.2f}")

            # Source 2: Data provider (fallback)
            if not spot and DATA_PROVIDER_AVAILABLE:
                spot = get_price(self.config.ticker)
                if spot and spot > 0:
                    logger.debug(f"Using spot price from data provider: ${spot:.2f}")

            if not spot or spot <= 0:
                logger.warning("Could not get spot price from any source (GEX calc or data provider)")
                return None

            # Get VIX with minimum floor
            vix = 20.0
            if DATA_PROVIDER_AVAILABLE:
                try:
                    fetched_vix = get_vix()
                    # VIX should be at least 10 (historically never below ~9)
                    # If we get 0 or very low, use default
                    if fetched_vix and fetched_vix >= 10:
                        vix = fetched_vix
                    elif fetched_vix:
                        logger.warning(f"VIX unusually low ({fetched_vix:.1f}), using default 20.0")
                except Exception as e:
                    logger.debug(f"VIX fetch failed: {e}, using default 20.0")

            # Calculate expected move (1 SD)
            expected_move = self._calculate_expected_move(spot, vix)

            # Sanity check - expected move should be reasonable (0.5% to 5% of spot)
            min_em = spot * 0.005
            max_em = spot * 0.05
            if expected_move < min_em:
                logger.warning(f"Expected move ${expected_move:.2f} too low, using minimum ${min_em:.2f}")
                expected_move = min_em
            elif expected_move > max_em:
                logger.warning(f"Expected move ${expected_move:.2f} unusually high (VIX={vix:.1f})")

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
        """Get GEX data from calculator (includes spot_price for fallback)"""
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
                    # CRITICAL: Include spot_price for fallback when data provider fails
                    'spot_price': gex.get('spot_price', gex.get('underlying_price', 0)),
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
        # VIX filter - only block in extreme conditions (VIX > 50)
        # Normal trading should happen every day regardless of VIX
        # High VIX actually means higher premiums which can offset risk
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
        Calculate Iron Condor strikes using SD-based math only.

        FIX (Feb 2026): Removed Prophet/GEX wall strike tiers.
        Prophet was suggesting strikes at 0.6-0.9 SD (based on GEX walls + tiny buffer)
        that bypassed validation, causing $9,500+ in losses (Jan 29 - Feb 6).
        Prophet still decides WHETHER to trade - strikes are now pure math.

        Strikes = spot +/- (SD_multiplier * expected_move), rounded away from spot.
        """
        # FIX (Feb 2026): Minimum 1.5 SD from spot.
        # 1.2 SD was too tight - FORTRESS lost $5,850 on Feb 6 with wings at 1.21 SD.
        MIN_SD_FLOOR = 1.5
        sd = max(self.config.sd_multiplier, MIN_SD_FLOOR)
        width = self.config.spread_width

        # Round strikes AWAY from spot for safety
        def round_put_strike(x):
            return math.floor(x)  # Round down = further from spot for puts

        def round_call_strike(x):
            return math.ceil(x)   # Round up = further from spot for calls

        # Ensure minimum expected move (0.5% of spot) to prevent calculation issues
        min_expected_move = spot_price * 0.005
        effective_em = max(expected_move, min_expected_move)

        if expected_move < min_expected_move:
            logger.warning(f"Expected move ${expected_move:.2f} too small, using minimum ${effective_em:.2f}")

        # Calculate strikes: spot +/- (SD * expected_move)
        put_short = round_put_strike(spot_price - sd * effective_em)
        call_short = round_call_strike(spot_price + sd * effective_em)

        # Log actual SD distances
        put_sd = (spot_price - put_short) / effective_em if effective_em > 0 else 0
        call_sd = (call_short - spot_price) / effective_em if effective_em > 0 else 0
        logger.info(f"[FORTRESS STRIKES] SD-based ({sd:.1f} SD): "
                   f"Put ${put_short} ({put_sd:.1f} SD), Call ${call_short} ({call_sd:.1f} SD)")

        # Safety net: verify strikes are at least MIN_SD_FLOOR from spot
        if put_sd < MIN_SD_FLOOR or call_sd < MIN_SD_FLOOR:
            logger.error(
                f"[FORTRESS SAFETY NET] Strikes below {MIN_SD_FLOOR} SD! "
                f"Put {put_sd:.2f} SD, Call {call_sd:.2f} SD. This should not happen."
            )

        # Long strikes are spread_width away from shorts
        put_long = put_short - width
        call_long = call_short + width

        # Ensure strikes don't overlap
        if call_short <= put_short:
            logger.error(f"[FORTRESS STRIKES] Overlap detected! Put ${put_short} >= Call ${call_short}")
            put_short = round_put_strike(spot_price - spot_price * 0.02)
            call_short = round_call_strike(spot_price + spot_price * 0.02)
            put_long = put_short - width
            call_long = call_short + width
            logger.warning(f"[FORTRESS STRIKES] Emergency fallback: Put ${put_short}, Call ${call_short}")

        return {
            'put_short': put_short,
            'put_long': put_long,
            'call_short': call_short,
            'call_long': call_long,
            'using_gex': False,
            'using_oracle': False,
            'source': f'SD_{sd:.1f}',
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
        Get REAL option credits from Tradier API.

        This fetches actual bid/ask quotes for SPY options to get accurate
        credit values instead of using formula estimation.

        Returns:
            Dict with put_credit, call_credit, total_credit, etc. or None if unavailable
        """
        if not self.tradier:
            logger.debug("FORTRESS: Tradier not available, cannot get real credits")
            return None

        try:
            # Build OCC symbols for each leg
            # SPY uses format: SPY + YYMMDD + C/P + Strike*1000 (8 digits)
            from datetime import datetime as dt
            exp_date = dt.strptime(expiration, '%Y-%m-%d')
            exp_str = exp_date.strftime('%y%m%d')

            def build_symbol(strike: float, opt_type: str) -> str:
                strike_str = f"{int(strike * 1000):08d}"
                return f"SPY{exp_str}{opt_type}{strike_str}"

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
                logger.warning(f"FORTRESS: Missing option quotes for {expiration}")
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
                logger.warning(f"FORTRESS: Invalid credits - put=${put_credit:.2f}, call=${call_credit:.2f}")
                # Try using mid prices as fallback
                put_short_mid = (put_short_bid + float(put_short_quote.get('ask', 0) or 0)) / 2
                put_long_mid = (float(put_long_quote.get('bid', 0) or 0) + put_long_ask) / 2
                call_short_mid = (call_short_bid + float(call_short_quote.get('ask', 0) or 0)) / 2
                call_long_mid = (float(call_long_quote.get('bid', 0) or 0) + call_long_ask) / 2

                put_credit = max(0, put_short_mid - put_long_mid)
                call_credit = max(0, call_short_mid - call_long_mid)

            total = put_credit + call_credit
            spread_width = put_short - put_long
            max_profit = total * 100
            max_loss = (spread_width - total) * 100

            logger.info(f"FORTRESS: REAL QUOTES - Put spread ${put_credit:.2f}, Call spread ${call_credit:.2f}, Total ${total:.2f}")

            return {
                'put_credit': round(put_credit, 2),
                'call_credit': round(call_credit, 2),
                'total_credit': round(total, 2),
                'max_profit': round(max_profit, 2),
                'max_loss': round(max_loss, 2),
                'source': 'TRADIER_LIVE',
            }

        except Exception as e:
            logger.warning(f"FORTRESS: Failed to get real credits: {e}")
            return None

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
        Estimate credits for the Iron Condor (FALLBACK when Tradier unavailable).

        NOTE: This is a rough estimate. Real trading should use get_real_credits()
        which fetches actual bid/ask from Tradier API.
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
            'source': 'ESTIMATED',
        }

    def get_ml_prediction(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get prediction from FORTRESS ML Advisor (PRIMARY prediction source).

        This model was trained on CHRONICLES backtests with ~70% win rate.
        It takes precedence over Prophet for trading decisions.

        Returns dict with:
        - win_probability: Calibrated probability of winning (key metric)
        - confidence: Model confidence score
        - advice: TRADE_FULL, TRADE_REDUCED, or SKIP_TODAY
        - suggested_risk_pct: Position size recommendation
        - suggested_sd_multiplier: Strike width recommendation
        - top_factors: Feature importances explaining the decision
        """
        if not self.fortress_ml:
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
            prediction = self.fortress_ml.predict(
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
            logger.warning(f"FORTRESS ML prediction error: {e}")
            import traceback
            traceback.print_exc()

        return None

    def get_prophet_advice(self, market_data: Dict) -> Optional[Dict[str, Any]]:
        """
        Get Prophet ML advice if available.

        Returns FULL prediction context for audit trail including:
        - win_probability: The key metric!
        - confidence: Model confidence
        - top_factors: WHY Prophet made this decision
        - suggested_sd_multiplier: Risk adjustment
        - use_gex_walls: Whether to use GEX wall strikes
        - probabilities: Raw probability dict
        """
        if not self.prophet:
            return None

        # Validate required market data before calling Prophet
        spot_price = market_data.get('spot_price', 0)
        if not spot_price or spot_price <= 0:
            logger.debug("Prophet skipped: No valid spot price available")
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'NO_DATA',
                'reasoning': 'No valid spot price available for Prophet analysis',
                'top_factors': [],
                'probabilities': {},
                'suggested_sd_multiplier': 1.0,
                'use_gex_walls': False,
                'suggested_put_strike': None,
                'suggested_call_strike': None,
                'suggested_risk_pct': 0,
            }

        try:
            # Build context for Prophet using correct field names
            from quant.prophet_advisor import MarketContext as ProphetMarketContext, GEXRegime

            # Convert gex_regime string to GEXRegime enum
            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL').upper()
            try:
                gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = ProphetMarketContext(
                spot_price=market_data['spot_price'],
                vix=market_data['vix'],
                gex_put_wall=market_data['put_wall'],
                gex_call_wall=market_data['call_wall'],
                gex_regime=gex_regime,
                gex_net=market_data.get('net_gex', 0),
                gex_flip_point=market_data.get('flip_point', 0),
                expected_move_pct=(market_data.get('expected_move', 0) / market_data.get('spot_price', 1) * 100) if market_data.get('spot_price') else 0,
            )

            # Call correct method: get_fortress_advice instead of get_prediction
            # Pass all VIX filtering parameters for proper skip logic
            # NOTE: VIX skips are disabled to allow daily trading (only extreme VIX > 50 blocked in check_vix_filter)
            prediction = self.prophet.get_fortress_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=True,  # Enable Claude for transparency logging
                vix_hard_skip=0.0,  # Disabled - main VIX filter only blocks VIX > 50
                vix_monday_friday_skip=0.0,  # Disabled - trade every day
                vix_streak_skip=0.0,  # Disabled - allow trading after losses
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
                    # wall_filter removed - not applicable to FORTRESS Iron Condors
                }
        except Exception as e:
            logger.warning(f"Prophet advice error: {e}")
            import traceback
            traceback.print_exc()
            # Return fallback values instead of None so scan activity shows meaningful data
            # This helps debugging - we can see Prophet was attempted but failed
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'ERROR',
                'reasoning': f"Prophet error: {str(e)[:100]}",
                'top_factors': [{'factor': 'error', 'impact': 0}],
                'probabilities': {},
                'suggested_sd_multiplier': 1.0,
                'use_gex_walls': False,
                'suggested_put_strike': None,
                'suggested_call_strike': None,
                'suggested_risk_pct': 0,
            }

        return None

    def generate_signal(self, prophet_data: Optional[Dict[str, Any]] = None) -> Optional[IronCondorSignal]:
        """
        Generate an Iron Condor signal.

        This is the MAIN entry point for signal generation.

        Args:
            prophet_data: Pre-fetched Prophet advice (optional). If provided, uses this
                        instead of making a new Prophet call. This ensures consistency
                        between what's displayed in scan logs and what's used for trading.

        Returns signal with FULL context for audit trail:
        - Market data (spot, VIX, expected move)
        - Chronicles GEX data (walls, regime, flip point, net GEX)
        - Prophet prediction (win probability, top factors, advice)
        - Strike selection rationale
        - Credit/risk calculations
        """
        # Step 1: Get market data (includes Chronicles GEX)
        market_data = self.get_market_data()
        if not market_data:
            logger.info("No market data available - returning blocked signal for diagnostics")
            return IronCondorSignal(
                spot_price=0,
                vix=0,
                expected_move=0,
                call_wall=0,
                put_wall=0,
                gex_regime="UNKNOWN",
                confidence=0,
                reasoning="NO_MARKET_DATA: GEX data not available",
                source="BLOCKED_NO_DATA",
            )

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
                    logger.info("No fresh market data available - returning blocked signal")
                    return IronCondorSignal(
                        spot_price=spot,
                        vix=vix,
                        expected_move=expected_move,
                        call_wall=0,
                        put_wall=0,
                        gex_regime="UNKNOWN",
                        confidence=0,
                        reasoning=f"STALE_DATA: Market data is {data_age:.0f}s old",
                        source="BLOCKED_STALE_DATA",
                    )
                spot = market_data['spot_price']
                vix = market_data['vix']
                expected_move = market_data['expected_move']

        # ============================================================
        # Step 2: GET PROPHET PREDICTION (PROPHET IS THE GOD OF ALL DECISIONS)
        #
        # CRITICAL: When Prophet says TRADE, we TRADE. Period.
        # Prophet already analyzed VIX, GEX, walls, regime, day of week.
        # Bot's min_win_probability threshold does NOT override Prophet.
        # ============================================================

        # Step 2a: Try ML prediction first (PRIMARY SOURCE)
        ml_prediction = self.get_ml_prediction(market_data)
        ml_win_prob = ml_prediction.get('win_probability', 0) if ml_prediction else 0
        ml_confidence = ml_prediction.get('confidence', 0) if ml_prediction else 0

        # Step 2b: Get Prophet advice (BACKUP SOURCE)
        # Use pre-fetched prophet_data if provided to avoid double Prophet calls
        # This ensures consistency between scan logs display and trade decision
        if prophet_data is not None:
            prophet = prophet_data
            logger.info(f"[FORTRESS] Using pre-fetched Prophet data: advice={prophet.get('advice', 'UNKNOWN')}")
        else:
            prophet = self.get_prophet_advice(market_data)
        oracle_win_prob = prophet.get('win_probability', 0) if prophet else 0
        oracle_confidence = prophet.get('confidence', 0.7) if prophet else 0.7
        oracle_advice = prophet.get('advice', 'SKIP_TODAY') if prophet else 'SKIP_TODAY'

        # Determine which source to use
        use_ml_prediction = ml_prediction is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        confidence = ml_confidence if use_ml_prediction else oracle_confidence
        # FIX (Feb 2026): Clamp confidence to 0-1 scale.
        # ML advisor may return 0-100 scale, causing "Conf: 10000%" display bug.
        if confidence > 1.0:
            confidence = confidence / 100.0
        confidence = max(0.0, min(1.0, confidence))
        prediction_source = "ARES_ML_ADVISOR" if use_ml_prediction else "PROPHET"

        # ============================================================
        # PROPHET IS THE GOD: If Prophet says TRADE, we TRADE
        # No min_win_probability threshold check - Prophet's word is final
        # ============================================================
        oracle_says_trade = oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')
        ml_oracle_says_trade = oracle_says_trade

        # Log Prophet decision
        if ml_oracle_says_trade:
            logger.info(f"[FORTRESS] PROPHET SAYS TRADE: {oracle_advice} - {prediction_source} = {effective_win_prob:.0%} win prob")
        else:
            logger.info(f"[FORTRESS] Prophet advice: {oracle_advice}, win prob: {effective_win_prob:.0%}")

        # ============================================================
        # Step 3: PROPHET SAYS NO TRADE - RESPECT PROPHET'S DECISION
        # ============================================================
        if not ml_oracle_says_trade:
            logger.info(f"[FORTRESS SKIP] Prophet says {oracle_advice} - respecting Prophet's decision")
            return IronCondorSignal(
                spot_price=spot,
                vix=vix,
                expected_move=expected_move,
                call_wall=market_data.get('call_wall', 0),
                put_wall=market_data.get('put_wall', 0),
                gex_regime=market_data.get('gex_regime', 'UNKNOWN'),
                confidence=0,
                reasoning=f"BLOCKED: Prophet advice={oracle_advice}, win_prob={effective_win_prob:.0%}",
                source="BLOCKED_ORACLE_NO_TRADE",
                oracle_win_probability=oracle_win_prob,
                oracle_advice=oracle_advice,
            )
        else:
            # Prophet says trade - log that we're bypassing VIX filter if needed
            can_trade, vix_reason = self.check_vix_filter(vix)
            if not can_trade:
                logger.info(f"[FORTRESS] VIX would have blocked ({vix_reason}) but PROPHET SAYS TRADE - proceeding")

        # Log ML analysis FIRST (PRIMARY source)
        if ml_prediction:
            logger.info(f"[FORTRESS ML ANALYSIS] *** PRIMARY PREDICTION SOURCE ***")
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
            logger.info(f"[FORTRESS] ML Advisor not available, falling back to Prophet")

        # Log Prophet analysis (BACKUP source)
        if prophet:
            logger.info(f"[FORTRESS PROPHET ANALYSIS] {'(BACKUP)' if not use_ml_prediction else '(informational)'}")
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

                # APPLY top_factors to adjust confidence based on current conditions
                if not use_ml_prediction:
                    confidence, factor_adjustments = self.adjust_confidence_from_top_factors(
                        confidence, prophet['top_factors'], market_data
                    )

            # Prophet SKIP_TODAY is informational only when ML is available
            if prophet.get('advice') == 'SKIP_TODAY':
                if use_ml_prediction:
                    logger.info(f"[FORTRESS] Prophet advises SKIP_TODAY but ML override active")
                    logger.info(f"  ML Win Prob: {ml_win_prob:.1%} will be used instead")
                else:
                    logger.info(f"[FORTRESS PROPHET INFO] Prophet advises SKIP_TODAY (informational only)")
                    logger.info(f"  Bot will use its own threshold: {self.config.min_win_probability:.1%}")

        # ============================================================
        # PROPHET IS THE GOD - No threshold check needed
        # If we reached here, Prophet said TRADE. We proceed.
        # ============================================================
        logger.info(f"[FORTRESS DECISION] Prophet says {oracle_advice} - proceeding with trade")
        logger.info(f"[FORTRESS] Using {prediction_source} win probability: {effective_win_prob:.1%}")

        # Use ML's suggested SD multiplier if available
        win_probability = effective_win_prob if effective_win_prob > 0 else 0.50  # Default to 50% if no prediction
        if use_ml_prediction and ml_prediction.get('suggested_sd_multiplier'):
            self._ml_suggested_sd = ml_prediction.get('suggested_sd_multiplier', 1.0)

        logger.info(f"[FORTRESS PASSED] {prediction_source} Win Prob {win_probability:.1%} >= threshold {self.config.min_win_probability:.1%}")

        # Step 4: Calculate strikes (SD-based only)
        # FIX (Feb 2026): Prophet/GEX wall strike tiers removed.
        # Prophet suggested GEX-wall-based strikes at 0.6-0.9 SD causing $9,500+ losses.
        # Strikes are now pure math: spot +/- (1.5 SD * expected_move).
        # Prophet still decides WHETHER to trade, not WHERE to place strikes.
        strikes = self.calculate_strikes(
            spot_price=spot,
            expected_move=expected_move,
        )

        # Step 5: Get expiration (0DTE) - needed for real quotes
        now = datetime.now(CENTRAL_TZ)
        expiration = now.strftime("%Y-%m-%d")

        # Step 6: Try to get REAL quotes from Tradier first
        pricing = self.get_real_credits(
            expiration=expiration,
            put_short=strikes['put_short'],
            put_long=strikes['put_long'],
            call_short=strikes['call_short'],
            call_long=strikes['call_long'],
        )

        # Fall back to estimation if real quotes unavailable
        if not pricing:
            logger.info("FORTRESS: Using estimated credits (Tradier unavailable)")
            pricing = self.estimate_credits(
                spot_price=spot,
                expected_move=expected_move,
                put_short=strikes['put_short'],
                put_long=strikes['put_long'],
                call_short=strikes['call_short'],
                call_long=strikes['call_long'],
                vix=vix,
            )

        # Step 7: Log credit info (no blocking - Prophet decides)
        if pricing['total_credit'] < self.config.min_credit:
            logger.warning(f"Credit ${pricing['total_credit']:.2f} below minimum ${self.config.min_credit} ({pricing.get('source', 'UNKNOWN')})")

        # Step 8: Build detailed reasoning (FULL audit trail)
        reasoning_parts = []
        reasoning_parts.append(f"VIX={vix:.1f}, Expected Move=${expected_move:.2f}")
        reasoning_parts.append(f"GEX Regime={market_data['gex_regime']}")

        reasoning_parts.append(f"{strikes['source']} strikes: Put ${strikes['put_short']}, Call ${strikes['call_short']}")

        if prophet:
            reasoning_parts.append(f"Prophet: {prophet.get('advice', 'N/A')} (Win Prob: {win_probability:.0%}, Conf: {confidence:.0%})")
            if prophet.get('top_factors'):
                top_factors_str = ", ".join([f"{f['factor']}: {f['impact']:.2f}" for f in prophet['top_factors'][:3]])
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

            # Chronicles context
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

            # Prophet context (FULL for audit)
            # BUG FIX: Use the oracle_advice variable from line 714 for consistency
            oracle_win_probability=win_probability,
            oracle_advice=oracle_advice,  # Use local var, not re-fetch with different default
            oracle_confidence=prophet.get('confidence', 0) if prophet else 0,
            oracle_top_factors=prophet.get('top_factors', []) if prophet else [],
            oracle_suggested_sd=prophet.get('suggested_sd_multiplier', 1.0) if prophet else 1.0,
            oracle_use_gex_walls=prophet.get('use_gex_walls', False) if prophet else False,
            oracle_probabilities=prophet.get('probabilities', {}) if prophet else {},
        )

        logger.info(f"Signal: IC {strikes['put_long']}/{strikes['put_short']}-{strikes['call_short']}/{strikes['call_long']} @ ${pricing['total_credit']:.2f}")
        logger.info(f"Prophet: Win Prob={win_probability:.0%}, Advice={oracle_advice}")
        return signal
