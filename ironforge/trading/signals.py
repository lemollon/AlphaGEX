"""
Signal Generator
=================

Unified signal generator for FLAME (2DTE) and SPARK (1DTE) Iron Condor bots.
Self-contained — uses the standalone TradierClient instead of AlphaGEX imports.
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from .models import IronCondorSignal, BotConfig, CENTRAL_TZ
from .tradier_client import TradierClient

logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    Generates Iron Condor signals using real Tradier market data.

    Works for both FLAME (2DTE) and SPARK (1DTE) — the only difference
    is config.min_dte which controls expiration targeting.
    """

    def __init__(self, config: BotConfig):
        self.config = config
        self.tradier = None
        self._init_tradier()

    def _init_tradier(self) -> None:
        """Initialize Tradier API client."""
        try:
            client = TradierClient()
            test_quote = client.get_quote("SPY")
            if test_quote and test_quote.get("last", 0) > 0:
                self.tradier = client
                logger.info(
                    f"{self.config.bot_name}: Tradier API connected "
                    f"(SPY=${test_quote.get('last', 0):.2f})"
                )
            else:
                logger.warning(f"{self.config.bot_name}: Tradier connected but SPY quote unavailable")
        except Exception as e:
            logger.warning(f"{self.config.bot_name}: Tradier init failed: {e}")

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Get current market data including price and VIX."""
        try:
            if not self.tradier:
                return None

            quote = self.tradier.get_quote(self.config.ticker)
            if not quote or not quote.get("last"):
                logger.warning(f"{self.config.bot_name}: Could not get spot price")
                return None

            spot = float(quote["last"])

            vix = 20.0
            fetched_vix = self.tradier.get_vix()
            if fetched_vix and fetched_vix >= 10:
                vix = fetched_vix

            # Estimate expected move: SPY daily move ~ VIX / sqrt(252) * spot
            expected_move = (vix / 100 / (252 ** 0.5)) * spot

            return {
                "spot_price": spot,
                "vix": vix,
                "expected_move": expected_move,
                "call_wall": 0,
                "put_wall": 0,
                "gex_regime": "UNKNOWN",
                "flip_point": 0,
                "net_gex": 0,
            }
        except Exception as e:
            logger.error(f"{self.config.bot_name}: Failed to get market data: {e}")
            return None

    def _get_target_expiration(self, now: datetime) -> str:
        """
        Get target expiration that is min_dte trading days out.

        Skips weekends (no holiday calendar in standalone mode).
        """
        min_dte = self.config.min_dte
        if min_dte <= 0:
            return now.strftime("%Y-%m-%d")

        target = now
        trading_days_counted = 0
        while trading_days_counted < min_dte:
            target += timedelta(days=1)
            if target.weekday() < 5:  # Mon-Fri
                trading_days_counted += 1

        expiration = target.strftime("%Y-%m-%d")
        logger.info(
            f"{self.config.bot_name}: Target expiration {expiration} "
            f"({min_dte} trading days out)"
        )
        return expiration

    def _validate_expiration(self, target_expiration: str) -> Optional[str]:
        """Validate the target expiration has listed options."""
        if not self.tradier:
            return target_expiration

        try:
            expirations = self.tradier.get_option_expirations(self.config.ticker)
            if not expirations:
                return target_expiration

            if target_expiration in expirations:
                return target_expiration

            # Find nearest valid expiration
            logger.warning(
                f"{self.config.bot_name}: Target {target_expiration} not available, "
                "searching for nearest"
            )
            target_date = datetime.strptime(target_expiration, "%Y-%m-%d")
            nearest = None
            min_diff = float("inf")
            for exp_str in expirations:
                try:
                    exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
                    diff = abs((exp_date - target_date).days)
                    if diff < min_diff and exp_date >= datetime.now():
                        min_diff = diff
                        nearest = exp_str
                except (ValueError, TypeError):
                    continue

            if nearest:
                logger.info(
                    f"{self.config.bot_name}: Using nearest expiration "
                    f"{nearest} (target was {target_expiration})"
                )
                return nearest

            return None
        except Exception as e:
            logger.warning(
                f"{self.config.bot_name}: Expiration validation failed: {e}"
            )
            return target_expiration

    def calculate_strikes(
        self, spot_price: float, expected_move: float
    ) -> Dict[str, float]:
        """Calculate Iron Condor strikes using SD-based math."""
        MIN_SD_FLOOR = 1.2
        sd = max(self.config.sd_multiplier, MIN_SD_FLOOR)
        width = self.config.spread_width

        min_expected_move = spot_price * 0.005
        effective_em = max(expected_move, min_expected_move)

        put_short = math.floor(spot_price - sd * effective_em)
        call_short = math.ceil(spot_price + sd * effective_em)
        put_long = put_short - width
        call_long = call_short + width

        if call_short <= put_short:
            put_short = math.floor(spot_price - spot_price * 0.02)
            call_short = math.ceil(spot_price + spot_price * 0.02)
            put_long = put_short - width
            call_long = call_short + width

        return {
            "put_short": put_short,
            "put_long": put_long,
            "call_short": call_short,
            "call_long": call_long,
            "source": f"SD_{sd:.1f}",
        }

    def enforce_symmetric_wings(
        self,
        short_put: float,
        long_put: float,
        short_call: float,
        long_call: float,
        available_strikes: Optional[set] = None,
    ) -> Optional[Dict[str, Any]]:
        """Ensure put spread width == call spread width."""
        put_width = short_put - long_put
        call_width = long_call - short_call
        original_put_width = put_width
        original_call_width = call_width
        adjusted = False

        if abs(put_width - call_width) < 0.01:
            return {
                "short_put": short_put,
                "long_put": long_put,
                "short_call": short_call,
                "long_call": long_call,
                "adjusted": False,
                "original_put_width": put_width,
                "original_call_width": call_width,
            }

        target_width = max(put_width, call_width)

        if put_width < target_width:
            long_put = short_put - target_width
            adjusted = True
        elif call_width < target_width:
            long_call = short_call + target_width
            adjusted = True

        # Validate against available strikes if provided
        if available_strikes and adjusted:
            if long_put not in available_strikes:
                valid_puts = sorted(
                    [s for s in available_strikes if s <= short_put - target_width]
                )
                if valid_puts:
                    long_put = valid_puts[-1]
                else:
                    return None

            if long_call not in available_strikes:
                valid_calls = sorted(
                    [s for s in available_strikes if s >= short_call + target_width]
                )
                if valid_calls:
                    long_call = valid_calls[0]
                else:
                    return None

        return {
            "short_put": short_put,
            "long_put": long_put,
            "short_call": short_call,
            "long_call": long_call,
            "adjusted": adjusted,
            "original_put_width": original_put_width,
            "original_call_width": original_call_width,
        }

    def get_real_credits(
        self,
        expiration: str,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
    ) -> Optional[Dict[str, float]]:
        """Get real option credits from Tradier using bid/ask."""
        if not self.tradier:
            return None

        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d")
            exp_str = exp_date.strftime("%y%m%d")

            def build_symbol(strike: float, opt_type: str) -> str:
                strike_str = f"{int(strike * 1000):08d}"
                return f"SPY{exp_str}{opt_type}{strike_str}"

            ps_q = self.tradier.get_option_quote(build_symbol(put_short, "P"))
            pl_q = self.tradier.get_option_quote(build_symbol(put_long, "P"))
            cs_q = self.tradier.get_option_quote(build_symbol(call_short, "C"))
            cl_q = self.tradier.get_option_quote(build_symbol(call_long, "C"))

            if not all([ps_q, pl_q, cs_q, cl_q]):
                return None

            # Conservative paper fills: sell at bid, buy at ask
            put_credit = float(ps_q.get("bid", 0) or 0) - float(
                pl_q.get("ask", 0) or 0
            )
            call_credit = float(cs_q.get("bid", 0) or 0) - float(
                cl_q.get("ask", 0) or 0
            )

            # Mid-price fallback if negative
            if put_credit <= 0 or call_credit <= 0:
                ps_mid = (float(ps_q.get("bid", 0) or 0) + float(ps_q.get("ask", 0) or 0)) / 2
                pl_mid = (float(pl_q.get("bid", 0) or 0) + float(pl_q.get("ask", 0) or 0)) / 2
                cs_mid = (float(cs_q.get("bid", 0) or 0) + float(cs_q.get("ask", 0) or 0)) / 2
                cl_mid = (float(cl_q.get("bid", 0) or 0) + float(cl_q.get("ask", 0) or 0)) / 2
                put_credit = max(0, ps_mid - pl_mid)
                call_credit = max(0, cs_mid - cl_mid)

            total = put_credit + call_credit
            spread_width = put_short - put_long

            return {
                "put_credit": round(put_credit, 4),
                "call_credit": round(call_credit, 4),
                "total_credit": round(total, 4),
                "max_profit": round(total * 100, 2),
                "max_loss": round((spread_width - total) * 100, 2),
                "source": "TRADIER_LIVE",
            }
        except Exception as e:
            logger.warning(f"{self.config.bot_name}: Failed to get real credits: {e}")
            return None

    def estimate_credits(
        self,
        spot_price: float,
        expected_move: float,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
        vix: float,
    ) -> Dict[str, float]:
        """Estimate credits when Tradier is unavailable (fallback)."""
        spread_width = put_short - put_long
        vol_factor = max(0.8, min(2.0, vix / 20.0))

        put_distance = (spot_price - put_short) / spot_price
        call_distance = (call_short - spot_price) / spot_price

        put_credit = min(
            spread_width * 0.015 * vol_factor / max(put_distance, 0.005),
            spread_width * 0.40,
        )
        call_credit = min(
            spread_width * 0.015 * vol_factor / max(call_distance, 0.005),
            spread_width * 0.40,
        )

        put_credit = max(0.02, round(put_credit, 2))
        call_credit = max(0.02, round(call_credit, 2))
        total = put_credit + call_credit

        return {
            "put_credit": put_credit,
            "call_credit": call_credit,
            "total_credit": total,
            "max_profit": round(total * 100, 2),
            "max_loss": round((spread_width - total) * 100, 2),
            "source": "ESTIMATED",
        }

    def generate_signal(self) -> Optional[IronCondorSignal]:
        """
        Generate an Iron Condor signal using real market data.

        Process:
        1. Fetch market data (spot, VIX, expected move)
        2. Check VIX threshold
        3. Calculate strikes with SD-based math
        4. Enforce symmetric wings
        5. Get real Tradier credits (bid/ask)
        6. Return fully populated signal
        """
        now = datetime.now(CENTRAL_TZ)
        dte_label = self.config.dte_mode

        market_data = self.get_market_data()
        if not market_data:
            logger.warning(f"{self.config.bot_name}: No market data available")
            return None

        spot = market_data["spot_price"]
        vix = market_data["vix"]
        expected_move = market_data["expected_move"]

        # VIX filter
        if vix > self.config.vix_skip:
            return IronCondorSignal(
                spot_price=spot,
                vix=vix,
                expected_move=expected_move,
                is_valid=False,
                reasoning=f"VIX {vix:.1f} too high (>{self.config.vix_skip})",
            )

        # Get target expiration
        expiration = self._get_target_expiration(now)
        expiration = self._validate_expiration(expiration)
        if not expiration:
            return IronCondorSignal(
                spot_price=spot,
                vix=vix,
                expected_move=expected_move,
                is_valid=False,
                reasoning="No valid expiration with options available",
            )

        # Calculate strikes
        strikes = self.calculate_strikes(spot, expected_move)

        # Get available strikes from chain for validation
        available_strikes = None
        if self.tradier:
            try:
                chain = self.tradier.get_option_chain(self.config.ticker, expiration)
                if chain:
                    available_strikes = {float(c["strike"]) for c in chain if "strike" in c}
            except Exception:
                pass

        # Enforce symmetric wings
        symmetric = self.enforce_symmetric_wings(
            strikes["put_short"],
            strikes["put_long"],
            strikes["call_short"],
            strikes["call_long"],
            available_strikes=available_strikes,
        )

        if symmetric is None:
            return IronCondorSignal(
                spot_price=spot,
                vix=vix,
                expected_move=expected_move,
                is_valid=False,
                reasoning="No valid strikes available for symmetric wings",
            )

        put_short = symmetric["short_put"]
        put_long = symmetric["long_put"]
        call_short = symmetric["short_call"]
        call_long = symmetric["long_call"]
        wings_adjusted = symmetric["adjusted"]

        # Get real credits
        credits = self.get_real_credits(
            expiration, put_short, put_long, call_short, call_long
        )
        if not credits:
            credits = self.estimate_credits(
                spot, expected_move, put_short, put_long, call_short, call_long, vix
            )

        total_credit = credits["total_credit"]

        # Minimum credit check
        if total_credit < self.config.min_credit:
            return IronCondorSignal(
                spot_price=spot,
                vix=vix,
                expected_move=expected_move,
                put_short=put_short,
                put_long=put_long,
                call_short=call_short,
                call_long=call_long,
                expiration=expiration,
                total_credit=total_credit,
                is_valid=False,
                reasoning=f"Credit ${total_credit:.2f} below minimum ${self.config.min_credit}",
            )

        signal = IronCondorSignal(
            spot_price=spot,
            vix=vix,
            expected_move=expected_move,
            put_short=put_short,
            put_long=put_long,
            call_short=call_short,
            call_long=call_long,
            expiration=expiration,
            estimated_put_credit=credits["put_credit"],
            estimated_call_credit=credits["call_credit"],
            total_credit=total_credit,
            max_loss=credits["max_loss"],
            max_profit=credits["max_profit"],
            confidence=0.5,
            is_valid=True,
            reasoning=(
                f"{dte_label} IC: {put_long}P/{put_short}P-{call_short}C/{call_long}C "
                f"@ ${total_credit:.2f} ({credits.get('source', 'UNKNOWN')})"
            ),
            source=credits.get("source", "UNKNOWN"),
            wings_adjusted=wings_adjusted,
            original_put_width=symmetric["original_put_width"],
            original_call_width=symmetric["original_call_width"],
        )

        logger.info(
            f"{self.config.bot_name} SIGNAL: "
            f"{put_long}P/{put_short}P-{call_short}C/{call_long}C "
            f"exp={expiration} credit=${total_credit:.2f} "
            f"{'(wings adjusted)' if wings_adjusted else '(symmetric)'}"
        )

        return signal

    def get_ic_mark_to_market(
        self,
        put_short: float,
        put_long: float,
        call_short: float,
        call_long: float,
        expiration: str,
    ) -> Optional[float]:
        """Get current cost to close an Iron Condor position."""
        if not self.tradier:
            return None

        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d")
            exp_str = exp_date.strftime("%y%m%d")

            def build_symbol(strike: float, opt_type: str) -> str:
                strike_str = f"{int(strike * 1000):08d}"
                return f"SPY{exp_str}{opt_type}{strike_str}"

            ps_q = self.tradier.get_option_quote(build_symbol(put_short, "P"))
            pl_q = self.tradier.get_option_quote(build_symbol(put_long, "P"))
            cs_q = self.tradier.get_option_quote(build_symbol(call_short, "C"))
            cl_q = self.tradier.get_option_quote(build_symbol(call_long, "C"))

            if not all([ps_q, pl_q, cs_q, cl_q]):
                return None

            # Cost to close: buy back shorts at ask, sell longs at bid
            cost = (
                float(ps_q.get("ask", 0) or 0)
                + float(cs_q.get("ask", 0) or 0)
                - float(pl_q.get("bid", 0) or 0)
                - float(cl_q.get("bid", 0) or 0)
            )

            return max(0, round(cost, 4))
        except Exception as e:
            logger.warning(f"{self.config.bot_name}: MTM calculation failed: {e}")
            return None
