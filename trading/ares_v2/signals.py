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
from typing import Optional, Dict, Any, Tuple
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


class SignalGenerator:
    """
    Generates Iron Condor signals using GEX data and market analysis.
    """

    def __init__(self, config: ARESConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        """Initialize signal generation components"""
        # GEX Calculator
        self.gex_calculator = None
        if KRONOS_AVAILABLE:
            try:
                self.gex_calculator = KronosGEXCalculator()
                logger.info("ARES SignalGenerator: Using Kronos GEX")
            except Exception as e:
                logger.warning(f"Kronos init failed: {e}")

        if not self.gex_calculator and TRADIER_GEX_AVAILABLE:
            try:
                self.gex_calculator = get_gex_calculator()
                logger.info("ARES SignalGenerator: Using Tradier GEX fallback")
            except Exception as e:
                logger.warning(f"Tradier GEX init failed: {e}")

        # Oracle Advisor
        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
                logger.info("ARES SignalGenerator: Oracle initialized")
            except Exception as e:
                logger.warning(f"Oracle init failed: {e}")

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

            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0) if gex_data else 0,
                'put_wall': gex_data.get('put_wall', 0) if gex_data else 0,
                'gex_regime': gex_data.get('regime', 'NEUTRAL') if gex_data else 'NEUTRAL',
                'net_gex': gex_data.get('net_gex', 0) if gex_data else 0,
                'flip_point': gex_data.get('flip_point', 0) if gex_data else 0,
                'timestamp': datetime.now(CENTRAL_TZ),
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

    def calculate_strikes(
        self,
        spot_price: float,
        expected_move: float,
        call_wall: float = 0,
        put_wall: float = 0
    ) -> Dict[str, float]:
        """
        Calculate Iron Condor strikes.

        Uses GEX walls if available (higher win rate),
        otherwise falls back to SD-based strikes.
        """
        sd = self.config.sd_multiplier
        width = self.config.spread_width

        # Round to $1 for SPY
        def round_strike(x):
            return round(x)

        # Determine short strikes
        use_gex = call_wall > 0 and put_wall > 0

        if use_gex:
            # GEX-Protected: Place shorts OUTSIDE the walls
            put_short = round_strike(put_wall)
            call_short = round_strike(call_wall)
            logger.info(f"Using GEX walls: Put short ${put_short}, Call short ${call_short}")
        else:
            # SD-based: Place shorts at expected move distance
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
            # Build context for Oracle
            from quant.oracle_advisor import MarketContext as OracleMarketContext, BotName

            context = OracleMarketContext(
                spot=market_data['spot_price'],
                vix=market_data['vix'],
                put_wall=market_data['put_wall'],
                call_wall=market_data['call_wall'],
                gex_regime=market_data['gex_regime'],
            )

            prediction = self.oracle.get_prediction(context, BotName.ARES)

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

        # Step 2: Check VIX filter
        can_trade, vix_reason = self.check_vix_filter(vix)
        if not can_trade:
            logger.info(f"VIX filter blocked: {vix_reason}")
            return None

        # Step 3: Get Oracle advice (FULL context)
        oracle = self.get_oracle_advice(market_data)
        confidence = oracle.get('confidence', 0.7) if oracle else 0.7
        win_probability = oracle.get('win_probability', 0) if oracle else 0

        # Step 4: Calculate strikes (use Oracle's suggestion if available)
        use_gex_walls = oracle.get('use_gex_walls', False) if oracle else False
        strikes = self.calculate_strikes(
            spot_price=spot,
            expected_move=expected_move,
            call_wall=market_data['call_wall'] if use_gex_walls else 0,
            put_wall=market_data['put_wall'] if use_gex_walls else 0,
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

        if strikes['using_gex']:
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
            source="GEX" if strikes['using_gex'] else "SD",

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
