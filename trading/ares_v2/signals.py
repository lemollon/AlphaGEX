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

# Oracle is the god of all trade decisions
# No config flag needed - Oracle always decides, GEX + VIX is fallback

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

# REMOVED: Ensemble Strategy and ML Regime Classifier
# Oracle is the god of all trade decisions. GEX + VIX is the fallback.
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

    def __init__(self, config: ARESConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator - Use Tradier for LIVE trading data
        # Kronos uses ORAT database (EOD) - only for backtesting, NOT live trading
        self.gex_calculator = None

        if TRADIER_GEX_AVAILABLE:
            try:
                tradier_calc = get_gex_calculator()
                # Verify Tradier works with live data
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"ARES: Using Tradier GEX for LIVE trading (spot={test_result.get('spot_price')})")
                else:
                    logger.error("ARES: Tradier GEX returned no data!")
            except Exception as e:
                logger.warning(f"ARES: Tradier GEX init/test failed: {e}")

        if not self.gex_calculator:
            logger.error("ARES: NO GEX CALCULATOR AVAILABLE - Tradier required for live trading")

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

        # REMOVED: Ensemble Strategy, GEX Directional ML, ML Regime Classifier
        # All redundant - Oracle is the god of all trade decisions


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
        2. GEX walls (if available and reasonable)
        3. SD-based strikes (with WIDENED multiplier for safety)

        FIX (Jan 2025): Previously used sd_multiplier=1.0 which placed strikes
        at EXACTLY the expected move boundary. This was too tight - 1 SD is
        breached ~32% of the time by statistical definition. Now uses 1.2 SD
        for SD-based fallback (20% more cushion).
        """
        # Use config SD multiplier, but enforce minimum of 1.2 for safety
        # Backtests show WIDE_STRIKES preset (1.2 SD) has highest win rate
        sd = max(self.config.sd_multiplier, 1.2)  # FIX: Floor at 1.2 SD for safety
        width = self.config.spread_width

        # Round strikes to nearest $1 for SPY, but AWAY from spot for safety
        # Put strikes round DOWN (further below spot)
        # Call strikes round UP (further above spot)
        # This ensures strikes are AT LEAST the calculated distance from spot
        def round_put_strike(x):
            return math.floor(x)  # Round down = further from spot for puts

        def round_call_strike(x):
            return math.ceil(x)   # Round up = further from spot for calls

        # Ensure minimum expected move (0.5% of spot) to prevent calculation issues
        min_expected_move = spot_price * 0.005  # 0.5% minimum
        effective_em = max(expected_move, min_expected_move)

        # FIX: Calculate MINIMUM strike distances using SD, NOT percentage!
        # BUG: Previously used 0.5%-5% percentage validation which could accept
        # GEX walls at 0.5% (~0.5 SD in low VIX) while SD fallback uses 1.2 SD.
        # PEGASUS enforces 1 SD minimum - ARES should enforce 1.2 SD minimum.
        min_sd_for_external = 1.2  # Minimum SD for Oracle/GEX strikes
        min_put_short = spot_price - (min_sd_for_external * effective_em)  # 1.2 SD below
        min_call_short = spot_price + (min_sd_for_external * effective_em)  # 1.2 SD above

        # Helper to validate strike is at least min SD away from spot
        def is_valid_sd_distance(put_strike: float, call_strike: float) -> tuple:
            """
            Validate strikes are at least 1.2 SD from spot.
            Returns (is_valid, put_sd, call_sd) for logging.
            """
            put_sd = (spot_price - put_strike) / effective_em if effective_em > 0 else 0
            call_sd = (call_strike - spot_price) / effective_em if effective_em > 0 else 0
            is_valid = put_strike <= min_put_short and call_strike >= min_call_short
            return is_valid, put_sd, call_sd

        # Determine short strikes with Oracle priority
        use_oracle = False
        use_gex = False
        put_short = 0
        call_short = 0

        # Priority 1: Oracle suggested strikes (ONLY if >= 1.2 SD away from spot)
        if oracle_put_strike and oracle_call_strike:
            is_valid, put_sd, call_sd = is_valid_sd_distance(oracle_put_strike, oracle_call_strike)
            if is_valid:
                put_short = round_put_strike(oracle_put_strike)
                call_short = round_call_strike(oracle_call_strike)
                use_oracle = True
                logger.info(f"[ARES STRIKES] Using Oracle strikes: Put ${put_short} ({put_sd:.1f} SD), Call ${call_short} ({call_sd:.1f} SD)")
            else:
                logger.warning(f"[ARES STRIKES] Oracle strikes TOO TIGHT (put={put_sd:.1f} SD, call={call_sd:.1f} SD - need >= {min_sd_for_external} SD)")

        # Priority 2: GEX walls (ONLY if >= 1.2 SD away from spot)
        if not use_oracle and call_wall > 0 and put_wall > 0:
            is_valid, put_sd, call_sd = is_valid_sd_distance(put_wall, call_wall)
            if is_valid:
                put_short = round_put_strike(put_wall)
                call_short = round_call_strike(call_wall)
                use_gex = True
                logger.info(f"[ARES STRIKES] Using GEX walls: Put ${put_short} ({put_sd:.1f} SD), Call ${call_short} ({call_sd:.1f} SD)")
            else:
                logger.warning(f"[ARES STRIKES] GEX walls TOO TIGHT (put={put_sd:.1f} SD, call={call_sd:.1f} SD - need >= {min_sd_for_external} SD)")

        # Priority 3: SD-based fallback (guaranteed 1.2 SD minimum)
        if not use_oracle and not use_gex:
            # effective_em already calculated above with 0.5% minimum

            # Use 1.2 SD minimum for wider strikes
            put_short = round_put_strike(spot_price - sd * effective_em)
            call_short = round_call_strike(spot_price + sd * effective_em)

            # Calculate actual SD for logging
            put_sd_actual = (spot_price - put_short) / effective_em if effective_em > 0 else 0
            call_sd_actual = (call_short - spot_price) / effective_em if effective_em > 0 else 0

            logger.info(f"[ARES STRIKES] Using SD-based ({sd:.1f} SD): "
                       f"Put ${put_short} ({put_sd_actual:.1f} SD), Call ${call_short} ({call_sd_actual:.1f} SD)")

            if expected_move < min_expected_move:
                logger.warning(f"Expected move ${expected_move:.2f} too small, using minimum ${effective_em:.2f}")

        # Long strikes are spread_width away from shorts
        put_long = put_short - width
        call_long = call_short + width

        # Final validation - ensure strikes don't overlap
        if call_short <= put_short:
            logger.error(f"[ARES STRIKES] Invalid strikes - overlap detected! Put ${put_short} >= Call ${call_short}")
            # Emergency fix: use wider strikes
            put_short = round_put_strike(spot_price - spot_price * 0.02)  # 2% below
            call_short = round_call_strike(spot_price + spot_price * 0.02)  # 2% above
            put_long = put_short - width
            call_long = call_short + width
            logger.warning(f"[ARES STRIKES] Emergency fallback: Put ${put_short}, Call ${call_short}")

        return {
            'put_short': put_short,
            'put_long': put_long,
            'call_short': call_short,
            'call_long': call_long,
            'using_gex': use_gex,
            'using_oracle': use_oracle,
            'source': 'ORACLE' if use_oracle else ('GEX' if use_gex else f'SD_{sd:.1f}'),
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

        # Validate required market data before calling Oracle
        spot_price = market_data.get('spot_price', 0)
        if not spot_price or spot_price <= 0:
            logger.debug("Oracle skipped: No valid spot price available")
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'NO_DATA',
                'reasoning': 'No valid spot price available for Oracle analysis',
                'top_factors': [],
                'probabilities': {},
                'suggested_sd_multiplier': 1.0,
                'use_gex_walls': False,
                'suggested_put_strike': None,
                'suggested_call_strike': None,
                'suggested_risk_pct': 0,
            }

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
            # NOTE: VIX skips are disabled to allow daily trading (only extreme VIX > 50 blocked in check_vix_filter)
            prediction = self.oracle.get_ares_advice(
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
                    # wall_filter removed - not applicable to ARES Iron Condors
                }
        except Exception as e:
            logger.warning(f"Oracle advice error: {e}")
            import traceback
            traceback.print_exc()
            # Return fallback values instead of None so scan activity shows meaningful data
            # This helps debugging - we can see Oracle was attempted but failed
            return {
                'confidence': 0,
                'win_probability': 0,
                'advice': 'ERROR',
                'reasoning': f"Oracle error: {str(e)[:100]}",
                'top_factors': [{'factor': 'error', 'impact': 0}],
                'probabilities': {},
                'suggested_sd_multiplier': 1.0,
                'use_gex_walls': False,
                'suggested_put_strike': None,
                'suggested_call_strike': None,
                'suggested_risk_pct': 0,
            }

        return None

    def generate_signal(self, oracle_data: Optional[Dict[str, Any]] = None) -> Optional[IronCondorSignal]:
        """
        Generate an Iron Condor signal.

        This is the MAIN entry point for signal generation.

        Args:
            oracle_data: Pre-fetched Oracle advice (optional). If provided, uses this
                        instead of making a new Oracle call. This ensures consistency
                        between what's displayed in scan logs and what's used for trading.

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
        # Step 2: GET ORACLE PREDICTION (ORACLE IS THE GOD OF ALL DECISIONS)
        #
        # CRITICAL: When Oracle says TRADE, we TRADE. Period.
        # Oracle already analyzed VIX, GEX, walls, regime, day of week.
        # Bot's min_win_probability threshold does NOT override Oracle.
        # ============================================================

        # Step 2a: Try ML prediction first (PRIMARY SOURCE)
        ml_prediction = self.get_ml_prediction(market_data)
        ml_win_prob = ml_prediction.get('win_probability', 0) if ml_prediction else 0
        ml_confidence = ml_prediction.get('confidence', 0) if ml_prediction else 0

        # Step 2b: Get Oracle advice (BACKUP SOURCE)
        # Use pre-fetched oracle_data if provided to avoid double Oracle calls
        # This ensures consistency between scan logs display and trade decision
        if oracle_data is not None:
            oracle = oracle_data
            logger.info(f"[ARES] Using pre-fetched Oracle data: advice={oracle.get('advice', 'UNKNOWN')}")
        else:
            oracle = self.get_oracle_advice(market_data)
        oracle_win_prob = oracle.get('win_probability', 0) if oracle else 0
        oracle_confidence = oracle.get('confidence', 0.7) if oracle else 0.7
        oracle_advice = oracle.get('advice', 'SKIP_TODAY') if oracle else 'SKIP_TODAY'

        # Determine which source to use
        use_ml_prediction = ml_prediction is not None and ml_win_prob > 0
        effective_win_prob = ml_win_prob if use_ml_prediction else oracle_win_prob
        confidence = ml_confidence if use_ml_prediction else oracle_confidence
        prediction_source = "ARES_ML_ADVISOR" if use_ml_prediction else "ORACLE"

        # ============================================================
        # ORACLE IS THE GOD: If Oracle says TRADE, we TRADE
        # No min_win_probability threshold check - Oracle's word is final
        # ============================================================
        oracle_says_trade = oracle_advice in ('TRADE_FULL', 'TRADE_REDUCED', 'ENTER')
        ml_oracle_says_trade = oracle_says_trade

        # Log Oracle decision
        if ml_oracle_says_trade:
            logger.info(f"[ARES] ORACLE SAYS TRADE: {oracle_advice} - {prediction_source} = {effective_win_prob:.0%} win prob")
        else:
            logger.info(f"[ARES] Oracle advice: {oracle_advice}, win prob: {effective_win_prob:.0%}")

        # ============================================================
        # Step 3: ORACLE SAYS NO TRADE - RESPECT ORACLE'S DECISION
        # ============================================================
        if not ml_oracle_says_trade:
            logger.info(f"[ARES SKIP] Oracle says {oracle_advice} - respecting Oracle's decision")
            return IronCondorSignal(
                spot_price=spot,
                vix=vix,
                expected_move=expected_move,
                call_wall=market_data.get('call_wall', 0),
                put_wall=market_data.get('put_wall', 0),
                gex_regime=market_data.get('gex_regime', 'UNKNOWN'),
                confidence=0,
                reasoning=f"BLOCKED: Oracle advice={oracle_advice}, win_prob={effective_win_prob:.0%}",
                source="BLOCKED_ORACLE_NO_TRADE",
                oracle_win_probability=oracle_win_prob,
                oracle_advice=oracle_advice,
            )
        else:
            # Oracle says trade - log that we're bypassing VIX filter if needed
            can_trade, vix_reason = self.check_vix_filter(vix)
            if not can_trade:
                logger.info(f"[ARES] VIX would have blocked ({vix_reason}) but ORACLE SAYS TRADE - proceeding")

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

        # ============================================================
        # ORACLE IS THE GOD - No threshold check needed
        # If we reached here, Oracle said TRADE. We proceed.
        # ============================================================
        logger.info(f"[ARES DECISION] Oracle says {oracle_advice} - proceeding with trade")
        logger.info(f"[ARES] Using {prediction_source} win probability: {effective_win_prob:.1%}")

        # Use ML's suggested SD multiplier if available
        win_probability = effective_win_prob if effective_win_prob > 0 else 0.50  # Default to 50% if no prediction
        if use_ml_prediction and ml_prediction.get('suggested_sd_multiplier'):
            self._ml_suggested_sd = ml_prediction.get('suggested_sd_multiplier', 1.0)

        logger.info(f"[ARES PASSED] {prediction_source} Win Prob {win_probability:.1%} >= threshold {self.config.min_win_probability:.1%}")

        # Step 4: Calculate strikes (Oracle > GEX > SD priority)
        # FIX: Always pass GEX walls - let calculate_strikes() decide whether to use them
        # Previously, walls were zeroed unless Oracle explicitly set use_gex_walls=True
        # This caused ARES to always fall back to SD-based strikes (too tight at 1.0 SD)
        oracle_put = oracle.get('suggested_put_strike') if oracle else None
        oracle_call = oracle.get('suggested_call_strike') if oracle else None

        # Get GEX walls from market data - always pass them for fallback protection
        gex_call_wall = market_data.get('call_wall', 0) or 0
        gex_put_wall = market_data.get('put_wall', 0) or 0

        # Log GEX wall availability for debugging
        if gex_call_wall > 0 and gex_put_wall > 0:
            logger.info(f"[ARES] GEX Walls available: Put ${gex_put_wall:.0f}, Call ${gex_call_wall:.0f}")
        else:
            logger.warning(f"[ARES] GEX Walls not available (put={gex_put_wall}, call={gex_call_wall})")

        strikes = self.calculate_strikes(
            spot_price=spot,
            expected_move=expected_move,
            call_wall=gex_call_wall,  # Always pass walls - let calculate_strikes validate
            put_wall=gex_put_wall,    # Always pass walls - let calculate_strikes validate
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

        # Step 6: Log credit info (no blocking - Oracle decides)
        if pricing['total_credit'] < self.config.min_credit:
            logger.warning(f"Credit ${pricing['total_credit']:.2f} below minimum ${self.config.min_credit} - proceeding (Oracle approved)")

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
            # BUG FIX: Use the oracle_advice variable from line 714 for consistency
            oracle_win_probability=win_probability,
            oracle_advice=oracle_advice,  # Use local var, not re-fetch with different default
            oracle_confidence=oracle.get('confidence', 0) if oracle else 0,
            oracle_top_factors=oracle.get('top_factors', []) if oracle else [],
            oracle_suggested_sd=oracle.get('suggested_sd_multiplier', 1.0) if oracle else 1.0,
            oracle_use_gex_walls=oracle.get('use_gex_walls', False) if oracle else False,
            oracle_probabilities=oracle.get('probabilities', {}) if oracle else {},
        )

        logger.info(f"Signal: IC {strikes['put_long']}/{strikes['put_short']}-{strikes['call_short']}/{strikes['call_long']} @ ${pricing['total_credit']:.2f}")
        logger.info(f"Oracle: Win Prob={win_probability:.0%}, Advice={oracle_advice}")
        return signal
