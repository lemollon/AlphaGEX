"""
FAITH - Signal Generation
=========================

Generates 2DTE Iron Condor signals using real Tradier market data.
Cloned from FORTRESS with symmetric wing enforcement and 2DTE targeting.

Key differences from FORTRESS:
- Targets 2DTE expiration (more premium than 0DTE)
- Enforces symmetric wings (both sides same width)
- Uses real Tradier bid/ask for conservative paper fill pricing
"""

import math
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo

from .models import IronCondorSignal, FaithConfig, CENTRAL_TZ

logger = logging.getLogger(__name__)

# Optional imports with fallbacks
try:
    from quant.prophet_advisor import ProphetAdvisor, ProphetPrediction
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None

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

# Market Calendar for holiday-aware expiration calculation
MARKET_CALENDAR_AVAILABLE = False
try:
    from trading.market_calendar import MarketCalendar
    _MARKET_CALENDAR = MarketCalendar()
    MARKET_CALENDAR_AVAILABLE = True
except ImportError:
    _MARKET_CALENDAR = None


class FaithSignalGenerator:
    """
    Generates Iron Condor signals for FAITH using real Tradier data.

    Uses the same market data sources as FORTRESS (GEX calculator, Tradier API)
    but targets 2DTE expirations and enforces symmetric wings.
    """

    def __init__(self, config: FaithConfig):
        """Initialize signal generator with real data sources."""
        self.config = config
        self._init_tradier()
        self._init_gex()

    def _init_gex(self) -> None:
        """Initialize GEX calculator for market data."""
        self.gex_calculator = None
        if TRADIER_GEX_AVAILABLE:
            try:
                tradier_calc = get_gex_calculator()
                test_result = tradier_calc.calculate_gex(self.config.ticker)
                if test_result and test_result.get('spot_price', 0) > 0:
                    self.gex_calculator = tradier_calc
                    logger.info(f"FAITH: Using Tradier GEX (spot={test_result.get('spot_price')})")
                else:
                    logger.warning("FAITH: Tradier GEX returned no data")
            except Exception as e:
                logger.warning(f"FAITH: Tradier GEX init failed: {e}")

    def _init_tradier(self) -> None:
        """Initialize Tradier for real option quotes."""
        self.tradier = None
        try:
            from data.tradier_data_fetcher import TradierDataFetcher
            self.tradier = TradierDataFetcher(sandbox=False)
            test_quote = self.tradier.get_quote("SPY")
            if test_quote and test_quote.get('last', 0) > 0:
                logger.info(f"FAITH: Tradier API connected (SPY=${test_quote.get('last', 0):.2f})")
            else:
                logger.warning("FAITH: Tradier connected but SPY quote unavailable")
        except Exception as e:
            logger.warning(f"FAITH: Tradier init failed: {e}")
            self.tradier = None

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """Get current market data including price, VIX, and GEX."""
        try:
            gex_data = self.get_gex_data()

            spot = None
            if gex_data and gex_data.get('spot_price', 0) > 0:
                spot = gex_data.get('spot_price')

            if not spot and DATA_PROVIDER_AVAILABLE:
                spot = get_price(self.config.ticker)

            if not spot or spot <= 0:
                logger.warning("FAITH: Could not get spot price from any source")
                return None

            vix = 20.0
            if DATA_PROVIDER_AVAILABLE:
                try:
                    fetched_vix = get_vix()
                    if fetched_vix and fetched_vix >= 10:
                        vix = fetched_vix
                except Exception:
                    pass

            # Get expected move from GEX data or estimate
            expected_move = 0
            if gex_data:
                expected_move = gex_data.get('expected_move', 0)

            if not expected_move or expected_move <= 0:
                # Estimate: SPY daily move ~ VIX / sqrt(252) * spot
                expected_move = (vix / 100 / (252 ** 0.5)) * spot
                logger.debug(f"FAITH: Estimated expected move: ${expected_move:.2f}")

            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0) if gex_data else 0,
                'put_wall': gex_data.get('put_wall', 0) if gex_data else 0,
                'gex_regime': gex_data.get('gex_regime', 'UNKNOWN') if gex_data else 'UNKNOWN',
                'flip_point': gex_data.get('flip_point', 0) if gex_data else 0,
                'net_gex': gex_data.get('net_gex', 0) if gex_data else 0,
            }
        except Exception as e:
            logger.error(f"FAITH: Failed to get market data: {e}")
            return None

    def get_gex_data(self) -> Optional[Dict[str, Any]]:
        """Get GEX data from calculator."""
        if not self.gex_calculator:
            return None
        try:
            return self.gex_calculator.calculate_gex(self.config.ticker)
        except Exception as e:
            logger.warning(f"FAITH: GEX calculation failed: {e}")
            return None

    def get_prophet_advice(self, market_data: Dict) -> Optional[Dict]:
        """Get Prophet ML advice for trading decision."""
        if not PROPHET_AVAILABLE or not ProphetAdvisor:
            return None

        try:
            from quant.prophet_advisor import (
                ProphetAdvisor as PA, MarketContext, GEXRegime, BotName
            )
            prophet = PA()

            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL')
            if isinstance(gex_regime_str, str):
                gex_regime_str = gex_regime_str.upper()
            try:
                gex_regime = GEXRegime[gex_regime_str]
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            context = MarketContext(
                spot_price=market_data.get('spot_price', 0),
                vix=market_data.get('vix', 20),
                gex_regime=gex_regime,
                gex_call_wall=market_data.get('call_wall', 0),
                gex_put_wall=market_data.get('put_wall', 0),
                gex_flip_point=market_data.get('flip_point', 0),
                gex_net=market_data.get('net_gex', 0),
                day_of_week=datetime.now(CENTRAL_TZ).weekday(),
                expected_move_pct=(
                    market_data.get('expected_move', 0) / market_data.get('spot_price', 1) * 100
                ) if market_data.get('spot_price', 0) > 0 else 0,
            )

            # Use FORTRESS bot name since FAITH uses the same strategy
            prediction = prophet.get_prediction(BotName.FORTRESS, context)
            if prediction:
                return {
                    'advice': prediction.advice.value if hasattr(prediction.advice, 'value') else str(prediction.advice),
                    'win_probability': prediction.win_probability,
                    'confidence': prediction.confidence,
                    'reasoning': prediction.reasoning,
                    'top_factors': [
                        {'factor': f[0], 'impact': f[1]} for f in (prediction.top_factors or [])
                    ],
                    'suggested_sd_multiplier': prediction.suggested_sd_multiplier,
                    'use_gex_walls': prediction.use_gex_walls,
                }
        except Exception as e:
            logger.warning(f"FAITH: Prophet advice failed: {e}")
        return None

    def _get_target_expiration(self, now: datetime) -> str:
        """
        Get target expiration date that is exactly 2 trading days out.

        SPY has daily expirations Mon-Fri, so we advance by trading days
        (skipping weekends and market holidays).

        Examples with min_dte=2:
          Monday    -> Wednesday
          Tuesday   -> Thursday
          Wednesday -> Friday
          Thursday  -> next Monday (skip weekend)
          Friday    -> next Tuesday (skip weekend)
        """
        min_dte = self.config.min_dte
        if min_dte <= 0:
            return now.strftime("%Y-%m-%d")

        target = now
        trading_days_counted = 0

        while trading_days_counted < min_dte:
            target = target + timedelta(days=1)
            if MARKET_CALENDAR_AVAILABLE and _MARKET_CALENDAR:
                if _MARKET_CALENDAR.is_trading_day(target):
                    trading_days_counted += 1
            else:
                if target.weekday() < 5:
                    trading_days_counted += 1

        expiration = target.strftime("%Y-%m-%d")
        logger.info(f"FAITH: Target expiration {expiration} ({min_dte} trading days out)")
        return expiration

    def calculate_strikes(
        self,
        spot_price: float,
        expected_move: float,
    ) -> Dict[str, float]:
        """
        Calculate Iron Condor strikes using SD-based math.

        Same logic as FORTRESS: strikes = spot +/- (SD_multiplier * expected_move),
        rounded away from spot for safety.
        """
        MIN_SD_FLOOR = 1.2
        sd = max(self.config.sd_multiplier, MIN_SD_FLOOR)
        width = self.config.spread_width

        min_expected_move = spot_price * 0.005
        effective_em = max(expected_move, min_expected_move)

        if expected_move < min_expected_move:
            logger.warning(f"FAITH: Expected move ${expected_move:.2f} too small, using ${effective_em:.2f}")

        # Calculate short strikes
        put_short = math.floor(spot_price - sd * effective_em)
        call_short = math.ceil(spot_price + sd * effective_em)

        # Long strikes are spread_width away from shorts
        put_long = put_short - width
        call_long = call_short + width

        # Ensure strikes don't overlap
        if call_short <= put_short:
            logger.error(f"FAITH: Overlap detected! Put ${put_short} >= Call ${call_short}")
            put_short = math.floor(spot_price - spot_price * 0.02)
            call_short = math.ceil(spot_price + spot_price * 0.02)
            put_long = put_short - width
            call_long = call_short + width

        put_sd = (spot_price - put_short) / effective_em if effective_em > 0 else 0
        call_sd = (call_short - spot_price) / effective_em if effective_em > 0 else 0
        logger.info(
            f"FAITH STRIKES: SD-based ({sd:.1f} SD): "
            f"Put ${put_short} ({put_sd:.1f} SD), Call ${call_short} ({call_sd:.1f} SD)"
        )

        return {
            'put_short': put_short,
            'put_long': put_long,
            'call_short': call_short,
            'call_long': call_long,
            'source': f'SD_{sd:.1f}',
        }

    def enforce_symmetric_wings(
        self,
        short_put: float,
        long_put: float,
        short_call: float,
        long_call: float,
        available_strikes: Optional[set] = None,
    ) -> Dict[str, Any]:
        """
        Ensure put spread width == call spread width.

        If they differ, adjust the LONG (protective) strikes to match.
        Always adjust outward (wider), never inward - never reduce protection.

        Args:
            short_put: Short put strike
            long_put: Long put strike
            short_call: Short call strike
            long_call: Long call strike
            available_strikes: Set of available strikes from options chain (for validation)

        Returns:
            Dict with adjusted strikes and metadata about any adjustment made.
        """
        put_width = short_put - long_put
        call_width = long_call - short_call
        adjusted = False
        original_put_width = put_width
        original_call_width = call_width

        if abs(put_width - call_width) < 0.01:
            # Already symmetric (within floating point tolerance)
            return {
                'short_put': short_put,
                'long_put': long_put,
                'short_call': short_call,
                'long_call': long_call,
                'adjusted': False,
                'original_put_width': put_width,
                'original_call_width': call_width,
            }

        # Use the WIDER of the two as the target width
        target_width = max(put_width, call_width)

        # Adjust the narrower side's long strike outward
        if put_width < target_width:
            long_put = short_put - target_width
            logger.info(
                f"FAITH: Wings adjusted: put side widened from "
                f"${original_put_width:.0f} to ${target_width:.0f} to match call side"
            )
            adjusted = True
        elif call_width < target_width:
            long_call = short_call + target_width
            logger.info(
                f"FAITH: Wings adjusted: call side widened from "
                f"${original_call_width:.0f} to ${target_width:.0f} to match put side"
            )
            adjusted = True

        # Validate symmetry
        final_put_width = short_put - long_put
        final_call_width = long_call - short_call
        if abs(final_put_width - final_call_width) > 0.01:
            logger.error(
                f"FAITH: Wings still asymmetric after adjustment: "
                f"put=${final_put_width}, call=${final_call_width}"
            )

        # If available_strikes provided, validate the adjusted strike exists
        if available_strikes and adjusted:
            if long_put not in available_strikes:
                # Find nearest valid strike that keeps width >= target_width
                valid_puts = sorted([s for s in available_strikes if s <= short_put - target_width])
                if valid_puts:
                    long_put = valid_puts[-1]  # Closest strike that's far enough out
                    logger.info(f"FAITH: Adjusted long put to nearest valid strike: ${long_put}")

            if long_call not in available_strikes:
                valid_calls = sorted([s for s in available_strikes if s >= short_call + target_width])
                if valid_calls:
                    long_call = valid_calls[0]  # Closest strike that's far enough out
                    logger.info(f"FAITH: Adjusted long call to nearest valid strike: ${long_call}")

        return {
            'short_put': short_put,
            'long_put': long_put,
            'short_call': short_call,
            'long_call': long_call,
            'adjusted': adjusted,
            'original_put_width': original_put_width,
            'original_call_width': original_call_width,
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
        Get real option credits from Tradier API using bid/ask.

        For paper trading fills:
        - Sells fill at bid price (conservative)
        - Buys fill at ask price (conservative)
        """
        if not self.tradier:
            logger.debug("FAITH: Tradier not available for real credits")
            return None

        try:
            from datetime import datetime as dt
            exp_date = dt.strptime(expiration, '%Y-%m-%d')
            exp_str = exp_date.strftime('%y%m%d')

            def build_symbol(strike: float, opt_type: str) -> str:
                """Build OCC option symbol."""
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

            if not all([put_short_quote, put_long_quote, call_short_quote, call_long_quote]):
                logger.warning(f"FAITH: Missing option quotes for {expiration}")
                return None

            # Conservative paper fills: sell at bid, buy at ask
            put_short_bid = float(put_short_quote.get('bid', 0) or 0)
            put_long_ask = float(put_long_quote.get('ask', 0) or 0)
            put_credit = put_short_bid - put_long_ask

            call_short_bid = float(call_short_quote.get('bid', 0) or 0)
            call_long_ask = float(call_long_quote.get('ask', 0) or 0)
            call_credit = call_short_bid - call_long_ask

            # If bid/ask produces negative credit, try mid-price fallback
            if put_credit <= 0 or call_credit <= 0:
                logger.warning(f"FAITH: Negative credit from bid/ask: put=${put_credit:.2f}, call=${call_credit:.2f}")
                put_short_mid = (put_short_bid + float(put_short_quote.get('ask', 0) or 0)) / 2
                put_long_mid = (float(put_long_quote.get('bid', 0) or 0) + put_long_ask) / 2
                call_short_mid = (call_short_bid + float(call_short_quote.get('ask', 0) or 0)) / 2
                call_long_mid = (float(call_long_quote.get('bid', 0) or 0) + call_long_ask) / 2
                put_credit = max(0, put_short_mid - put_long_mid)
                call_credit = max(0, call_short_mid - call_long_mid)

            total = put_credit + call_credit
            spread_width = put_short - put_long

            logger.info(
                f"FAITH: REAL QUOTES - Put ${put_credit:.2f}, "
                f"Call ${call_credit:.2f}, Total ${total:.2f}"
            )

            return {
                'put_credit': round(put_credit, 4),
                'call_credit': round(call_credit, 4),
                'total_credit': round(total, 4),
                'max_profit': round(total * 100, 2),
                'max_loss': round((spread_width - total) * 100, 2),
                'source': 'TRADIER_LIVE',
            }
        except Exception as e:
            logger.warning(f"FAITH: Failed to get real credits: {e}")
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
        Estimate credits when Tradier is unavailable (fallback only).

        Uses the same formula as FORTRESS for consistency.
        """
        spread_width = put_short - put_long
        vol_factor = max(0.8, min(2.0, vix / 20.0))

        put_distance = (spot_price - put_short) / spot_price
        call_distance = (call_short - spot_price) / spot_price

        put_credit = min(
            spread_width * 0.015 * vol_factor / max(put_distance, 0.005),
            spread_width * 0.40
        )
        call_credit = min(
            spread_width * 0.015 * vol_factor / max(call_distance, 0.005),
            spread_width * 0.40
        )

        put_credit = max(0.02, round(put_credit, 2))
        call_credit = max(0.02, round(call_credit, 2))
        total = put_credit + call_credit

        return {
            'put_credit': put_credit,
            'call_credit': call_credit,
            'total_credit': total,
            'max_profit': round(total * 100, 2),
            'max_loss': round((spread_width - total) * 100, 2),
            'source': 'ESTIMATED',
        }

    def generate_signal(self, prophet_data: Optional[Dict] = None) -> Optional[IronCondorSignal]:
        """
        Generate a 2DTE Iron Condor signal using real market data.

        Process:
        1. Fetch market data (spot, VIX, expected move, GEX)
        2. Check Prophet ML advice (if available)
        3. Calculate strikes with SD-based math
        4. Enforce symmetric wings
        5. Get real Tradier credits (bid/ask)
        6. Return fully populated signal

        Args:
            prophet_data: Pre-fetched Prophet advice (to avoid double fetch)

        Returns:
            IronCondorSignal or None if no valid signal
        """
        now = datetime.now(CENTRAL_TZ)

        # Step 1: Get market data
        market_data = self.get_market_data()
        if not market_data:
            logger.warning("FAITH: No market data available")
            return None

        spot = market_data['spot_price']
        vix = market_data['vix']
        expected_move = market_data['expected_move']

        # Step 2: VIX filter
        if vix > self.config.vix_skip:
            logger.info(f"FAITH: VIX {vix:.1f} > skip threshold {self.config.vix_skip}")
            return IronCondorSignal(
                spot_price=spot, vix=vix, expected_move=expected_move,
                is_valid=False, reasoning=f"VIX {vix:.1f} too high (>{self.config.vix_skip})"
            )

        # Step 3: Get Prophet advice
        if prophet_data is None:
            prophet_data = self.get_prophet_advice(market_data)

        oracle_advice = ""
        oracle_win_prob = 0
        oracle_confidence = 0
        oracle_reasoning = ""
        oracle_top_factors = None

        if prophet_data:
            oracle_advice = prophet_data.get('advice', '')
            oracle_win_prob = prophet_data.get('win_probability', 0)
            oracle_confidence = prophet_data.get('confidence', 0)
            oracle_reasoning = prophet_data.get('reasoning', '')
            oracle_top_factors = prophet_data.get('top_factors', [])

            # Check if Prophet says to skip
            if oracle_advice in ('SKIP_TODAY', 'SKIP'):
                logger.info(f"FAITH: Prophet says SKIP: {oracle_reasoning}")
                return IronCondorSignal(
                    spot_price=spot, vix=vix, expected_move=expected_move,
                    oracle_advice=oracle_advice,
                    oracle_win_probability=oracle_win_prob,
                    oracle_confidence=oracle_confidence,
                    is_valid=False,
                    reasoning=f"Prophet SKIP: {oracle_reasoning}"
                )

            # Check minimum win probability
            if oracle_win_prob > 0 and oracle_win_prob < self.config.min_win_probability:
                logger.info(
                    f"FAITH: Prophet win prob {oracle_win_prob:.0%} < "
                    f"minimum {self.config.min_win_probability:.0%}"
                )
                return IronCondorSignal(
                    spot_price=spot, vix=vix, expected_move=expected_move,
                    oracle_advice=oracle_advice,
                    oracle_win_probability=oracle_win_prob,
                    is_valid=False,
                    reasoning=f"Win probability {oracle_win_prob:.0%} below threshold"
                )

        # Step 4: Get target expiration (2DTE)
        expiration = self._get_target_expiration(now)

        # Step 5: Calculate strikes
        strikes = self.calculate_strikes(spot, expected_move)

        # Step 6: Enforce symmetric wings (pass real chain strikes if available)
        available_strikes = None
        if self.tradier:
            try:
                chain = self.tradier.get_option_chain(self.config.ticker, expiration)
                if chain and hasattr(chain, 'chains') and chain.chains:
                    for contracts in chain.chains.values():
                        available_strikes = {c.strike for c in contracts if hasattr(c, 'strike')}
                        break
            except Exception as e:
                logger.debug(f"FAITH: Could not fetch chain for strike validation: {e}")

        symmetric = self.enforce_symmetric_wings(
            strikes['put_short'], strikes['put_long'],
            strikes['call_short'], strikes['call_long'],
            available_strikes=available_strikes,
        )

        put_short = symmetric['short_put']
        put_long = symmetric['long_put']
        call_short = symmetric['short_call']
        call_long = symmetric['long_call']
        wings_adjusted = symmetric['adjusted']

        # Step 7: Get real credits from Tradier
        credits = self.get_real_credits(expiration, put_short, put_long, call_short, call_long)

        if not credits:
            # Fallback to estimated credits
            credits = self.estimate_credits(
                spot, expected_move, put_short, put_long, call_short, call_long, vix
            )
            logger.info(f"FAITH: Using estimated credits (Tradier unavailable): ${credits['total_credit']:.2f}")

        total_credit = credits['total_credit']

        # Minimum credit check
        if total_credit < self.config.min_credit:
            logger.info(f"FAITH: Credit ${total_credit:.2f} < minimum ${self.config.min_credit}")
            return IronCondorSignal(
                spot_price=spot, vix=vix, expected_move=expected_move,
                put_short=put_short, put_long=put_long,
                call_short=call_short, call_long=call_long,
                expiration=expiration, total_credit=total_credit,
                is_valid=False,
                reasoning=f"Credit ${total_credit:.2f} below minimum ${self.config.min_credit}"
            )

        spread_width = put_short - put_long

        # Build the signal
        import json
        oracle_factors_json = json.dumps(oracle_top_factors) if oracle_top_factors else ""

        signal = IronCondorSignal(
            spot_price=spot,
            vix=vix,
            expected_move=expected_move,
            call_wall=market_data.get('call_wall', 0),
            put_wall=market_data.get('put_wall', 0),
            gex_regime=market_data.get('gex_regime', ''),
            flip_point=market_data.get('flip_point', 0),
            net_gex=market_data.get('net_gex', 0),
            put_short=put_short,
            put_long=put_long,
            call_short=call_short,
            call_long=call_long,
            expiration=expiration,
            estimated_put_credit=credits['put_credit'],
            estimated_call_credit=credits['call_credit'],
            total_credit=total_credit,
            max_loss=credits['max_loss'],
            max_profit=credits['max_profit'],
            confidence=oracle_confidence if oracle_confidence > 0 else 0.5,
            oracle_win_probability=oracle_win_prob,
            oracle_confidence=oracle_confidence,
            oracle_advice=oracle_advice,
            oracle_top_factors=oracle_top_factors,
            oracle_use_gex_walls=False,
            is_valid=True,
            reasoning=f"2DTE IC: {put_long}P/{put_short}P-{call_short}C/{call_long}C @ ${total_credit:.2f} ({credits.get('source', 'UNKNOWN')})",
            source=credits.get('source', 'UNKNOWN'),
            wings_adjusted=wings_adjusted,
            original_put_width=symmetric['original_put_width'],
            original_call_width=symmetric['original_call_width'],
        )

        logger.info(
            f"FAITH SIGNAL: {put_long}P/{put_short}P-{call_short}C/{call_long}C "
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
        """
        Get current cost to close an Iron Condor position using real Tradier data.

        For closing: we BUY back the shorts and SELL the longs.
        Cost to close = (short_put_ask + short_call_ask) - (long_put_bid + long_call_bid)

        Returns:
            Current cost to close (debit), or None if unavailable
        """
        if not self.tradier:
            return None

        try:
            from datetime import datetime as dt
            exp_date = dt.strptime(expiration, '%Y-%m-%d')
            exp_str = exp_date.strftime('%y%m%d')

            def build_symbol(strike: float, opt_type: str) -> str:
                strike_str = f"{int(strike * 1000):08d}"
                return f"SPY{exp_str}{opt_type}{strike_str}"

            ps_quote = self.tradier.get_option_quote(build_symbol(put_short, 'P'))
            pl_quote = self.tradier.get_option_quote(build_symbol(put_long, 'P'))
            cs_quote = self.tradier.get_option_quote(build_symbol(call_short, 'C'))
            cl_quote = self.tradier.get_option_quote(build_symbol(call_long, 'C'))

            if not all([ps_quote, pl_quote, cs_quote, cl_quote]):
                return None

            # Cost to close: buy back shorts at ask, sell longs at bid
            cost = (
                float(ps_quote.get('ask', 0) or 0) +
                float(cs_quote.get('ask', 0) or 0) -
                float(pl_quote.get('bid', 0) or 0) -
                float(cl_quote.get('bid', 0) or 0)
            )

            return max(0, round(cost, 4))

        except Exception as e:
            logger.warning(f"FAITH: MTM calculation failed: {e}")
            return None
