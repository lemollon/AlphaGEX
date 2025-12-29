"""
PEGASUS - Signal Generation
=============================

Signal generation for SPX Iron Condors.
Uses $5 strike increments and larger expected moves.
"""

import math
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from .models import IronCondorSignal, PEGASUSConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Optional imports
try:
    from quant.oracle_advisor import OracleAdvisor
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

try:
    from data.unified_data_provider import get_price, get_vix
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class SignalGenerator:
    """Generates SPX Iron Condor signals"""

    def __init__(self, config: PEGASUSConfig):
        self.config = config
        self._init_components()

    def _init_components(self) -> None:
        self.gex_calculator = None
        if KRONOS_AVAILABLE:
            try:
                self.gex_calculator = KronosGEXCalculator()
                logger.info("PEGASUS: Kronos GEX initialized")
            except Exception:
                pass

        if not self.gex_calculator and TRADIER_GEX_AVAILABLE:
            try:
                from data.gex_calculator import get_gex_calculator
                self.gex_calculator = get_gex_calculator()
            except Exception:
                pass

        self.oracle = None
        if ORACLE_AVAILABLE:
            try:
                self.oracle = OracleAdvisor()
            except Exception:
                pass

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
                except Exception:
                    pass

            # GEX data (scale from SPY if needed)
            gex_data = self._get_gex_data()

            expected_move = self._calculate_expected_move(spot, vix)

            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0) * 10 if gex_data else 0,  # Scale to SPX
                'put_wall': gex_data.get('put_wall', 0) * 10 if gex_data else 0,
                'gex_regime': gex_data.get('regime', 'NEUTRAL') if gex_data else 'NEUTRAL',
                'timestamp': datetime.now(CENTRAL_TZ),
            }
        except Exception as e:
            logger.error(f"Market data error: {e}")
            return None

    def _get_gex_data(self) -> Optional[Dict]:
        if not self.gex_calculator:
            return None
        try:
            # Try SPX first, fallback to SPY
            gex = self.gex_calculator.calculate_gex("SPX")
            if not gex:
                gex = self.gex_calculator.calculate_gex("SPY")
            if gex:
                return {
                    'call_wall': gex.get('call_wall', gex.get('major_call_wall', 0)),
                    'put_wall': gex.get('put_wall', gex.get('major_put_wall', 0)),
                    'regime': gex.get('regime', 'NEUTRAL'),
                }
        except Exception:
            pass
        return None

    def _calculate_expected_move(self, spot: float, vix: float) -> float:
        """Calculate 1 SD expected move for SPX"""
        annual_factor = math.sqrt(252)
        daily_vol = (vix / 100) / annual_factor
        return round(spot * daily_vol, 2)

    def check_vix_filter(self, vix: float) -> Tuple[bool, str]:
        if self.config.vix_skip and vix > self.config.vix_skip:
            return False, f"VIX {vix:.1f} > {self.config.vix_skip}"
        return True, "OK"

    def calculate_strikes(self, spot: float, expected_move: float, call_wall: float = 0, put_wall: float = 0) -> Dict[str, float]:
        """Calculate SPX strikes with $5 rounding"""
        sd = self.config.sd_multiplier
        width = self.config.spread_width

        def round_to_5(x):
            return round(x / 5) * 5

        use_gex = call_wall > 0 and put_wall > 0

        if use_gex:
            put_short = round_to_5(put_wall)
            call_short = round_to_5(call_wall)
        else:
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
        """Generate SPX Iron Condor signal"""
        market = self.get_market_data()
        if not market:
            return None

        can_trade, reason = self.check_vix_filter(market['vix'])
        if not can_trade:
            logger.info(f"VIX filter: {reason}")
            return None

        strikes = self.calculate_strikes(
            market['spot_price'],
            market['expected_move'],
            market['call_wall'],
            market['put_wall'],
        )

        pricing = self.estimate_credits(
            market['spot_price'],
            market['expected_move'],
            strikes['put_short'],
            strikes['call_short'],
            market['vix'],
        )

        if pricing['total_credit'] < self.config.min_credit:
            logger.info(f"Credit ${pricing['total_credit']:.2f} < ${self.config.min_credit}")
            return None

        expiration = datetime.now(CENTRAL_TZ).strftime("%Y-%m-%d")

        reasoning = f"SPX VIX={market['vix']:.1f}, EM=${market['expected_move']:.0f}. "
        reasoning += "GEX-Protected. " if strikes['using_gex'] else f"{self.config.sd_multiplier} SD. "

        return IronCondorSignal(
            spot_price=market['spot_price'],
            vix=market['vix'],
            expected_move=market['expected_move'],
            call_wall=market['call_wall'],
            put_wall=market['put_wall'],
            gex_regime=market['gex_regime'],
            put_short=strikes['put_short'],
            put_long=strikes['put_long'],
            call_short=strikes['call_short'],
            call_long=strikes['call_long'],
            expiration=expiration,
            estimated_put_credit=pricing['put_credit'],
            estimated_call_credit=pricing['call_credit'],
            total_credit=pricing['total_credit'],
            max_loss=pricing['max_loss'],
            max_profit=pricing['max_profit'],
            confidence=0.7,
            reasoning=reasoning,
            source="GEX" if strikes['using_gex'] else "SD",
        )
