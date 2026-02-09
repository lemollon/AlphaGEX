"""
JUBILEE Signal Generation - Box Spread Analysis

Generates box spread signals with comprehensive educational explanations.
This module analyzes market conditions to find optimal box spread opportunities.
"""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
import math
import uuid

from .models import (
    BoxSpreadSignal,
    BorrowingCostAnalysis,
    JubileeConfig,
    # IC Trading Models
    JubileeICSignal,
    JubileeICConfig,
)
from .tracing import get_tracer, trace_signal, trace_rate

logger = logging.getLogger(__name__)

# Get global tracer instance
tracer = get_tracer()

# Central timezone
try:
    from zoneinfo import ZoneInfo
    CENTRAL_TZ = ZoneInfo("America/Chicago")
except ImportError:
    import pytz
    CENTRAL_TZ = pytz.timezone("America/Chicago")

# Try to import data providers
try:
    from data.unified_data_provider import UnifiedDataProvider
    data_provider = UnifiedDataProvider()
except ImportError:
    data_provider = None
    logger.warning("UnifiedDataProvider not available")

import os

# Tradier client - MUST use production for SPX quotes
# Sandbox API does NOT provide SPX option data
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TradierDataFetcher = None
    TRADIER_AVAILABLE = False
    logger.warning("TradierDataFetcher not available")


# Lazy-loaded Tradier client (initialized on first use, not at module import)
# This ensures environment variables are available before client creation
_tradier_client = None


def _get_tradier():
    """
    Get Tradier client for SPX quotes - LAZY LOADED, ALWAYS uses production API.

    CRITICAL: The Tradier sandbox API does NOT provide SPX option quotes.
    For accurate box spread pricing, we MUST use the production API.
    This follows the same pattern used by ANCHOR/TradierGEXCalculator.

    LAZY LOADING: Client is created on first use, not at module import time.
    This ensures environment variables are available when the client is created.
    """
    global _tradier_client

    if _tradier_client is not None:
        return _tradier_client

    if not TRADIER_AVAILABLE:
        logger.error("TradierDataFetcher module not available")
        return None

    try:
        # Check production keys - TRADIER_PROD_API_KEY takes priority
        prod_key = os.environ.get('TRADIER_PROD_API_KEY') or os.environ.get('TRADIER_API_KEY')

        if prod_key:
            _tradier_client = TradierDataFetcher(api_key=prod_key, sandbox=False)
            logger.info("JUBILEE: Tradier PRODUCTION client initialized for SPX quotes")
            return _tradier_client
        else:
            logger.error(
                "JUBILEE: SPX quotes require production Tradier API key "
                "(TRADIER_PROD_API_KEY or TRADIER_API_KEY) - NOT SET!"
            )
            return None

    except Exception as e:
        logger.error(f"JUBILEE: Could not create production Tradier client: {e}")
        return None

import time  # For retry delays


def _tradier_call_with_retry(func, *args, max_retries: int = 3, **kwargs):
    """
    Execute a Tradier API call with exponential backoff retry.

    This ensures resilience against transient network/API failures.
    Pattern borrowed from ANCHOR executor.py.

    Args:
        func: The function to call (e.g., _get_tradier().get_quote)
        *args: Positional arguments to pass to the function
        max_retries: Number of retry attempts (default 3)
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function call, or None if all retries fail
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result
            # Empty result is not necessarily an error - might just be no data
            logger.warning(f"Tradier returned empty result on attempt {attempt + 1}")
            return None
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                delay = 1.0 * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"Tradier API error (attempt {attempt + 1}/{max_retries}): {e}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
            else:
                logger.error(f"Tradier API failed after {max_retries} attempts: {e}")

    return None


# Dynamic rate fetching
try:
    from .rate_fetcher import get_current_rates, InterestRates
    RATE_FETCHER_AVAILABLE = True
except ImportError:
    RATE_FETCHER_AVAILABLE = False
    logger.warning("RateFetcher not available, using static rates")


class BoxSpreadSignalGenerator:
    """
    Generates box spread signals with full educational context.

    EDUCATIONAL NOTE - How Box Spread Signals Work:
    ===============================================
    1. Find liquid options expirations (6-12 months out)
    2. Select strikes around current price (for liquidity)
    3. Price the four legs of the box spread
    4. Calculate implied borrowing rate
    5. Compare to alternatives (margin, Fed Funds)
    6. Generate signal if rate is favorable

    The signal includes full explanations of WHY each decision
    was made, helping you learn the strategy.
    """

    def __init__(self, config: JubileeConfig = None):
        self.config = config or JubileeConfig()
        # Initialize rates - will be updated dynamically
        self._rates_cache: Optional[InterestRates] = None
        self._refresh_rates()

    def _refresh_rates(self) -> None:
        """Refresh interest rates from live sources."""
        if RATE_FETCHER_AVAILABLE:
            try:
                self._rates_cache = get_current_rates()
                self._fed_funds_rate = self._rates_cache.fed_funds_rate
                self._margin_rate = self._rates_cache.margin_rate
                logger.info(f"Rates updated: Fed Funds={self._fed_funds_rate:.2f}%, Margin={self._margin_rate:.2f}% (source: {self._rates_cache.source})")
            except Exception as e:
                logger.warning(f"Failed to fetch rates: {e}, using FOMC target midpoint")
                # FOMC target range: 4.25-4.50% (as of Jan 2025)
                self._fed_funds_rate = 4.38  # FOMC midpoint
                self._margin_rate = 8.38     # Fed Funds + 4% spread
        else:
            # Static fallback - use FOMC target midpoint
            # IMPORTANT: Update these when Fed changes rates!
            self._fed_funds_rate = 4.38  # FOMC midpoint (4.25-4.50%)
            self._margin_rate = 8.38     # Fed Funds + 4% spread
            logger.warning("Rate fetcher not available - using FOMC target midpoint 4.38%")

    @property
    def rates_source(self) -> str:
        """Get the source of current rates (live/cached/fallback)."""
        if self._rates_cache:
            return self._rates_cache.source
        return "static"

    def generate_signal(self) -> Optional[BoxSpreadSignal]:
        """
        Generate a box spread signal with full educational context.

        Returns None if no favorable opportunity exists.
        """
        logger.info("Generating box spread signal...")
        now = datetime.now(CENTRAL_TZ)

        # Get market data
        market_data = self._get_market_data()
        if not market_data:
            logger.warning("Could not get market data for signal generation")
            return None

        spot_price = market_data['spot_price']
        vix = market_data.get('vix', 15.0)

        # Find optimal expiration
        expiration, dte, why_expiration = self._select_expiration(market_data)
        if not expiration:
            logger.info("No suitable expiration found")
            return None

        # Select strikes
        lower_strike, upper_strike, why_strikes = self._select_strikes(
            spot_price, market_data
        )
        strike_width = upper_strike - lower_strike

        # Price the box spread
        pricing = self._price_box_spread(
            lower_strike, upper_strike, expiration, market_data
        )
        if not pricing:
            logger.info("Could not price box spread")
            return None

        # Calculate borrowing metrics
        theoretical_value = strike_width  # Per share, guaranteed at expiration
        mid_price = pricing['mid_price']

        # Cash flows (per contract = 100 shares)
        contracts = self._calculate_position_size(mid_price, strike_width)
        cash_received = mid_price * contracts * 100
        cash_owed = theoretical_value * contracts * 100
        borrowing_cost = cash_owed - cash_received

        # Implied annual rate calculation
        implied_rate = self._calculate_implied_rate(
            mid_price, theoretical_value, dte
        )

        # Rate comparisons
        rate_advantage = (self._margin_rate - implied_rate) * 100  # In basis points

        # Assignment risk assessment
        assignment_risk, risk_explanation = self._assess_assignment_risk(
            self.config.ticker, dte
        )

        # Margin requirement estimate
        margin_req = self._estimate_margin_requirement(
            strike_width, contracts
        )

        # Generate strategy explanation
        strategy_explanation = self._generate_strategy_explanation(
            spot_price, lower_strike, upper_strike, expiration, dte,
            mid_price, implied_rate, cash_received, cash_owed
        )

        # Check if signal is valid
        is_valid, skip_reason = self._validate_signal(
            implied_rate, rate_advantage, margin_req
        )

        signal = BoxSpreadSignal(
            signal_id=f"PROM-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            signal_time=now,
            ticker=self.config.ticker,
            spot_price=spot_price,
            lower_strike=lower_strike,
            upper_strike=upper_strike,
            strike_width=strike_width,
            expiration=expiration,
            dte=dte,
            theoretical_value=theoretical_value,
            market_bid=pricing['bid'],
            market_ask=pricing['ask'],
            mid_price=mid_price,
            cash_received=cash_received,
            cash_owed_at_expiration=cash_owed,
            borrowing_cost=borrowing_cost,
            implied_annual_rate=implied_rate,
            fed_funds_rate=self._fed_funds_rate,
            margin_rate=self._margin_rate,
            rate_advantage=rate_advantage,
            early_assignment_risk=assignment_risk,
            assignment_risk_explanation=risk_explanation,
            margin_requirement=margin_req,
            margin_pct_of_capital=margin_req / self.config.capital * 100,
            recommended_contracts=contracts,
            total_cash_generated=cash_received,
            strategy_explanation=strategy_explanation,
            why_this_expiration=why_expiration,
            why_these_strikes=why_strikes,
            is_valid=is_valid,
            skip_reason=skip_reason,
        )

        return signal

    def _get_market_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current market data for the underlying from PRODUCTION Tradier.

        CRITICAL: SPX quotes require production Tradier API.
        This function does NOT fall back to simulated data.
        If live data is unavailable, returns None and signal generation is skipped.

        Uses retry logic with exponential backoff for API resilience.
        """
        tradier = _get_tradier()
        if not tradier:
            logger.error(
                "Tradier client not available - cannot get SPX quotes. "
                "Ensure TRADIER_API_KEY or TRADIER_PROD_API_KEY is set."
            )
            return None

        # Get SPX/SPXW quote from PRODUCTION Tradier with retry
        quote = _tradier_call_with_retry(tradier.get_quote, self.config.ticker)
        if not quote:
            logger.error(f"No quote returned for {self.config.ticker} after retries - check Tradier API")
            return None

        spot = quote.get('last') or quote.get('bid') or quote.get('close')
        if not spot or spot <= 0:
            logger.error(f"Invalid spot price for {self.config.ticker}: {quote}")
            return None

        return {
            'spot_price': float(spot),
            'bid': float(quote.get('bid', 0) or 0),
            'ask': float(quote.get('ask', 0) or 0),
            'vix': self._get_vix(),
            'source': 'tradier_production',
        }

    def _get_vix(self) -> float:
        """Get current VIX level with retry logic"""
        tradier = _get_tradier()
        if tradier:
            quote = _tradier_call_with_retry(tradier.get_quote, 'VIX', max_retries=2)
            if quote:
                vix = quote.get('last', 15.0)
                if vix and vix > 0:
                    return float(vix)
        # VIX is supplementary - use conservative default if unavailable
        logger.debug("VIX quote unavailable, using default 15.0")
        return 15.0

    def _select_expiration(
        self, market_data: Dict[str, Any]
    ) -> Tuple[Optional[str], int, str]:
        """
        Select optimal expiration for box spread.

        EDUCATIONAL NOTE:
        =================
        Longer expirations generally have better (lower) implied rates
        because the time value of money is more efficiently priced.
        However, capital is tied up longer.

        We prefer quarterly expirations (March, June, Sept, Dec) because:
        1. Higher liquidity
        2. Tighter bid-ask spreads
        3. More predictable pricing

        Returns: (expiration_date, dte, explanation)
        """
        try:
            # Get available expirations with retry
            tradier = _get_tradier()
            if tradier:
                expirations = _tradier_call_with_retry(
                    tradier.get_expirations, self.config.ticker, max_retries=2
                )
            else:
                expirations = None

            if not expirations:
                return None, 0, "No expirations available"

            today = date.today()
            candidates = []

            for exp_str in expirations:
                try:
                    exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
                    dte = (exp_date - today).days

                    # Filter by DTE range
                    if dte < self.config.target_dte_min:
                        continue
                    if dte > self.config.target_dte_max:
                        continue

                    # Prefer quarterly expirations
                    is_quarterly = exp_date.month in [3, 6, 9, 12]
                    score = 100 if is_quarterly else 50

                    # Prefer longer DTE (better rates)
                    score += dte / 10

                    candidates.append({
                        'expiration': exp_str,
                        'dte': dte,
                        'is_quarterly': is_quarterly,
                        'score': score,
                    })

                except ValueError:
                    continue

            if not candidates:
                return None, 0, "No expirations in target DTE range"

            # Sort by score, pick best
            candidates.sort(key=lambda x: x['score'], reverse=True)
            best = candidates[0]

            explanation = f"""
EXPIRATION SELECTION: {best['expiration']} ({best['dte']} DTE)

Why this expiration:
1. DTE of {best['dte']} days is within target range ({self.config.target_dte_min}-{self.config.target_dte_max})
2. {'Quarterly expiration = higher liquidity and tighter spreads' if best['is_quarterly'] else 'Non-quarterly but acceptable liquidity expected'}
3. Longer DTE generally provides better (lower) implied borrowing rates
4. Time horizon allows IC bots to generate returns before box expires

Alternative expirations considered: {len(candidates)} options
""".strip()

            return best['expiration'], best['dte'], explanation

        except Exception as e:
            logger.error(f"Error selecting expiration: {e}")
            return None, 0, f"Error: {str(e)}"

    def _select_strikes(
        self, spot_price: float, market_data: Dict[str, Any]
    ) -> Tuple[float, float, str]:
        """
        Select optimal strikes for box spread.

        EDUCATIONAL NOTE:
        =================
        Strike selection balances two factors:
        1. ATM strikes have best liquidity (tightest spreads)
        2. Round number strikes are more liquid
        3. Wider strike width = more cash generated but more margin

        We typically select strikes slightly below and above current price
        at round numbers for maximum liquidity.

        Returns: (lower_strike, upper_strike, explanation)
        """
        width = self.config.strike_width

        if self.config.prefer_round_strikes:
            # Round to nearest strike width multiple
            if 'SPX' in self.config.ticker:
                # SPX strikes in $5 or $10 increments
                base = round(spot_price / 10) * 10
                lower = base - width / 2
                upper = base + width / 2
            else:
                # SPY strikes in $1 increments
                base = round(spot_price)
                lower = base - width / 2
                upper = base + width / 2
        else:
            # Use distance from spot
            distance = spot_price * (self.config.strike_distance_pct / 100)
            lower = round(spot_price - distance)
            upper = lower + width

        explanation = f"""
STRIKE SELECTION: {lower}/{upper} (${width} width)

Why these strikes:
1. Current {self.config.ticker} price: ${spot_price:.2f}
2. Lower strike ({lower}) is {'a round number' if lower % 10 == 0 else 'near'} below spot
3. Upper strike ({upper}) is {'a round number' if upper % 10 == 0 else 'near'} above spot
4. Strike width of ${width} generates approximately ${width * 100:,.0f} per contract
5. ATM strikes ensure maximum liquidity for better fills

Strike width tradeoff:
- Wider width = More cash per contract, but higher margin requirement
- Current width of ${width} is {'conservative' if width <= 30 else 'moderate' if width <= 50 else 'aggressive'}
""".strip()

        return lower, upper, explanation

    def _price_box_spread(
        self,
        lower_strike: float,
        upper_strike: float,
        expiration: str,
        market_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Price the four legs of a box spread.

        EDUCATIONAL NOTE:
        =================
        A box spread has 4 legs:
        1. Buy Call at lower strike (long leg of bull call spread)
        2. Sell Call at upper strike (short leg of bull call spread)
        3. Buy Put at upper strike (long leg of bear put spread)
        4. Sell Put at lower strike (short leg of bear put spread)

        When you SELL a box:
        - You sell the bull call spread
        - You sell the bear put spread
        - You receive a credit today
        - You owe the strike width at expiration

        Returns: {bid, ask, mid_price, legs: {...}} or None if live data unavailable

        CRITICAL: No longer falls back to simulated pricing.
        If live option chain is unavailable, returns None.
        """
        try:
            tradier = _get_tradier()
            if not tradier:
                logger.error("Tradier client not available - cannot price box spread")
                return None

            # Get option chain from PRODUCTION Tradier with retry
            chain = _tradier_call_with_retry(
                tradier.get_option_chain, self.config.ticker, expiration, max_retries=3
            )
            if not chain:
                logger.error(f"Empty option chain for {self.config.ticker} exp {expiration} after retries")
                return None

            # OptionChain has chains dict: {expiration -> List[OptionContract]}
            # OptionContract is a dataclass with strike, option_type, bid, ask, etc.
            options_list = chain.chains.get(expiration, [])
            if not options_list:
                logger.error(f"No options found for expiration {expiration} in chain")
                return None

            # Find our strikes
            legs = {}
            for option in options_list:
                # OptionContract is a dataclass - access attributes directly
                strike = option.strike
                opt_type = option.option_type  # 'call' or 'put'

                if strike == lower_strike:
                    if opt_type == 'call':
                        legs['call_long'] = option
                    elif opt_type == 'put':
                        legs['put_short'] = option
                elif strike == upper_strike:
                    if opt_type == 'call':
                        legs['call_short'] = option
                    elif opt_type == 'put':
                        legs['put_long'] = option

            if len(legs) < 4:
                logger.warning(
                    f"Could not find all 4 legs for {lower_strike}/{upper_strike}, "
                    f"found: {list(legs.keys())} - check strikes exist in chain"
                )
                return None

            # Calculate box spread price
            # Selling the box = receiving call spread credit + put spread credit
            # Bull call spread: Sell high call, buy low call
            # Bear put spread: Sell low put, buy high put

            # For selling the box, we want the BID prices for what we sell
            # and ASK prices for what we buy
            # OptionContract is a dataclass - access attributes directly

            call_spread_credit = (
                legs['call_short'].bid -  # Sell upper call
                legs['call_long'].ask     # Buy lower call
            )
            put_spread_credit = (
                legs['put_short'].bid -   # Sell lower put
                legs['put_long'].ask      # Buy upper put
            )

            box_bid = call_spread_credit + put_spread_credit

            # For the ask side (if we were buying)
            call_spread_debit = (
                legs['call_short'].ask -
                legs['call_long'].bid
            )
            put_spread_debit = (
                legs['put_short'].ask -
                legs['put_long'].bid
            )

            box_ask = call_spread_debit + put_spread_debit
            mid_price = (box_bid + box_ask) / 2

            # Convert OptionContract dataclasses to dicts for serialization
            from dataclasses import asdict
            legs_dict = {k: asdict(v) for k, v in legs.items()}

            return {
                'bid': box_bid,
                'ask': box_ask,
                'mid_price': mid_price,
                'legs': legs_dict,
                'source': 'tradier_production',
            }

        except Exception as e:
            logger.error(f"Error pricing box spread from Tradier: {e}")
            return None

    def _calculate_implied_rate(
        self,
        current_price: float,
        future_value: float,
        dte: int
    ) -> float:
        """
        Calculate the implied annual borrowing rate.

        EDUCATIONAL NOTE:
        =================
        The implied rate is derived from present value formula:

        PV = FV / (1 + r * t)

        Rearranging:
        r = (FV / PV - 1) / t

        Where:
        - PV = current box price (what you receive)
        - FV = strike width (what you owe at expiration)
        - t = time in years (DTE / 365)
        - r = implied annual rate

        Lower rate = cheaper borrowing = better for us
        """
        if current_price <= 0 or dte <= 0:
            return 0.0

        time_years = dte / 365
        implied_rate = ((future_value / current_price) - 1) / time_years

        return implied_rate * 100  # Return as percentage

    def _calculate_rate_trend(
        self,
        current_rate: float
    ) -> tuple:
        """
        Calculate rate trend from historical data.

        Returns:
            (avg_30d, avg_90d, trend)
        """
        try:
            from .db import JubileeDatabase
            db = JubileeDatabase()

            # Get historical rates
            history = db.get_rate_history(days=90)

            if not history or len(history) < 2:
                return current_rate, current_rate, "STABLE"

            # Calculate averages
            rates = [float(h.get('box_implied_rate', current_rate)) for h in history if h.get('box_implied_rate')]

            if not rates:
                return current_rate, current_rate, "STABLE"

            # 30-day average (last 30 entries or all if less)
            rates_30d = rates[:30] if len(rates) >= 30 else rates
            avg_30d = sum(rates_30d) / len(rates_30d) if rates_30d else current_rate

            # 90-day average
            avg_90d = sum(rates) / len(rates) if rates else current_rate

            # Determine trend
            if len(rates) >= 7:
                recent_avg = sum(rates[:7]) / 7
                older_avg = sum(rates[7:14]) / 7 if len(rates) >= 14 else avg_30d

                diff = recent_avg - older_avg
                if diff > 0.10:
                    trend = "RISING"
                elif diff < -0.10:
                    trend = "FALLING"
                else:
                    trend = "STABLE"
            else:
                trend = "STABLE"

            return avg_30d, avg_90d, trend

        except Exception as e:
            logger.warning(f"Failed to calculate rate trend: {e}")
            return current_rate, current_rate, "STABLE"

    def _calculate_position_size(
        self,
        mid_price: float,
        strike_width: float
    ) -> int:
        """
        Calculate optimal position size based on config constraints.

        EDUCATIONAL NOTE:
        =================
        Position sizing considers:
        1. Max position size limit
        2. Max contracts limit
        3. Margin requirements
        4. Reserve buffer
        """
        # Cash generated per contract
        cash_per_contract = mid_price * 100

        # Max contracts by cash limit
        max_by_cash = int(self.config.max_position_size / cash_per_contract)

        # Apply config max
        max_contracts = min(max_by_cash, self.config.max_contracts_per_position)

        # Ensure at least 1 contract
        return max(1, max_contracts)

    def _assess_assignment_risk(
        self, ticker: str, dte: int
    ) -> Tuple[str, str]:
        """
        Assess early assignment risk.

        EDUCATIONAL NOTE:
        =================
        Early assignment risk varies by option style:

        SPX (European-style):
        - Can ONLY be exercised at expiration
        - Assignment risk = ZERO until expiration
        - This is why we prefer SPX for box spreads

        SPY (American-style):
        - Can be exercised ANY time
        - Higher risk near ex-dividend dates
        - Risk increases as ITM amount grows
        - Can disrupt the box spread strategy

        XSP (Mini SPX, European-style):
        - Same benefits as SPX
        - Smaller notional for smaller accounts
        """
        if 'SPX' in ticker.upper() or 'XSP' in ticker.upper():
            return "LOW", f"""
ASSIGNMENT RISK: LOW (European-Style Options)

{ticker} options are European-style, meaning:
1. They can ONLY be exercised at expiration
2. No early assignment risk whatsoever
3. Your box spread will stay intact until expiration
4. This is the ideal underlying for box spreads

Recommendation: Proceed with confidence. European-style options
eliminate the biggest risk of box spread strategies.
""".strip()

        else:
            risk_level = "MEDIUM" if dte > 30 else "HIGH"
            return risk_level, f"""
ASSIGNMENT RISK: {risk_level} (American-Style Options)

{ticker} options are American-style, meaning:
1. They can be exercised at ANY time before expiration
2. Risk is {'elevated' if risk_level == 'HIGH' else 'moderate'} with {dte} DTE
3. Deep ITM options may be assigned early
4. Ex-dividend dates increase assignment probability

Mitigation strategies:
- Monitor positions daily for deep ITM legs
- Be prepared to unwind if assignment occurs
- Consider using SPX/XSP instead for zero assignment risk

Recommendation: {'Consider SPX instead for safety' if risk_level == 'HIGH' else 'Proceed with monitoring'}.
""".strip()

    def _estimate_margin_requirement(
        self,
        strike_width: float,
        contracts: int
    ) -> float:
        """
        Estimate margin requirement for box spread.

        EDUCATIONAL NOTE:
        =================
        Box spread margin varies by broker:

        1. Some brokers recognize the risk-free nature and require minimal margin
        2. Others require full spread margin (strike width × 100 × contracts)
        3. The actual requirement depends on your broker's rules

        We estimate conservatively using full spread margin.
        Check with your broker for actual requirements.
        """
        # Conservative estimate: full spread width as margin
        # Some brokers give credit for the offsetting positions
        margin = strike_width * 100 * contracts

        # Assume broker gives 50% credit for box spread structure
        adjusted_margin = margin * 0.5

        return adjusted_margin

    def _validate_signal(
        self,
        implied_rate: float,
        rate_advantage: float,
        margin_req: float
    ) -> Tuple[bool, str]:
        """Validate if the signal meets our criteria"""
        reasons = []

        # Check max implied rate
        if implied_rate > self.config.max_implied_rate:
            reasons.append(
                f"Implied rate {implied_rate:.2f}% exceeds max {self.config.max_implied_rate}%"
            )

        # Check rate advantage
        if rate_advantage < self.config.min_rate_advantage:
            reasons.append(
                f"Rate advantage {rate_advantage:.0f}bps below min {self.config.min_rate_advantage}bps"
            )

        # Check margin
        max_margin = self.config.capital * (self.config.max_margin_pct / 100)
        if margin_req > max_margin:
            reasons.append(
                f"Margin requirement ${margin_req:,.0f} exceeds max ${max_margin:,.0f}"
            )

        if reasons:
            return False, "; ".join(reasons)

        return True, ""

    def _generate_strategy_explanation(
        self,
        spot_price: float,
        lower_strike: float,
        upper_strike: float,
        expiration: str,
        dte: int,
        mid_price: float,
        implied_rate: float,
        cash_received: float,
        cash_owed: float
    ) -> str:
        """Generate comprehensive strategy explanation"""
        strike_width = upper_strike - lower_strike

        return f"""
╔══════════════════════════════════════════════════════════════════╗
║           BOX SPREAD SYNTHETIC BORROWING EXPLAINED               ║
╚══════════════════════════════════════════════════════════════════╝

WHAT IS A BOX SPREAD?
═══════════════════
A box spread combines two vertical spreads to create a position with
a GUARANTEED payoff at expiration, regardless of where the underlying
price ends up. This makes it risk-free in terms of directional exposure.

YOUR SPECIFIC BOX SPREAD:
═══════════════════════
┌─────────────────────────────────────────────────────────────────┐
│ Underlying: {self.config.ticker} (currently at ${spot_price:.2f})
│ Expiration: {expiration} ({dte} days)
│ Strikes: ${lower_strike:.0f} / ${upper_strike:.0f} (${strike_width:.0f} width)
└─────────────────────────────────────────────────────────────────┘

THE 4 LEGS OF YOUR BOX:
═══════════════════════
┌─────────────────────────────────────────────────────────────────┐
│ BULL CALL SPREAD (you receive credit):                          │
│   • Sell ${upper_strike:.0f} Call (receive premium)
│   • Buy ${lower_strike:.0f} Call (pay premium)
│                                                                 │
│ BEAR PUT SPREAD (you receive credit):                           │
│   • Sell ${lower_strike:.0f} Put (receive premium)
│   • Buy ${upper_strike:.0f} Put (pay premium)
└─────────────────────────────────────────────────────────────────┘

THE MAGIC - WHY THIS IS SYNTHETIC BORROWING:
════════════════════════════════════════════
TODAY: You SELL the box spread
       → You RECEIVE ${cash_received:,.2f} cash

AT EXPIRATION: The box ALWAYS equals ${strike_width:.0f} × 100 × contracts
              → You "OWE" ${cash_owed:,.2f}

This is identical to taking out a loan:
  • Loan principal: ${cash_received:,.2f}
  • Repayment: ${cash_owed:,.2f}
  • Interest cost: ${cash_owed - cash_received:,.2f}
  • Implied annual rate: {implied_rate:.2f}%

COMPARISON TO ALTERNATIVES:
═══════════════════════════
┌──────────────────────┬────────────┬───────────────────────────┐
│ Borrowing Method     │ Rate       │ Notes                     │
├──────────────────────┼────────────┼───────────────────────────┤
│ Box Spread           │ {implied_rate:.2f}%     │ ← Your rate               │
│ Fed Funds Rate       │ {self._fed_funds_rate:.2f}%     │ Risk-free benchmark       │
│ Broker Margin        │ {self._margin_rate:.2f}%     │ What broker charges       │
└──────────────────────┴────────────┴───────────────────────────┘

YOUR SAVINGS: {self._margin_rate - implied_rate:.2f}% lower than margin
             = ${(self._margin_rate - implied_rate) / 100 * cash_received:,.2f} saved annually

HOW THIS FUNDS IC BOTS:
═══════════════════════
1. Cash received (${cash_received:,.2f}) is deployed to FORTRESS, SAMSON, ANCHOR
2. These bots trade Iron Condors, generating premium income
3. Target IC returns: 2-4% monthly
4. Box spread costs: ~{implied_rate / 12:.2f}% monthly
5. Net profit: IC returns minus box cost

Example math (monthly):
  • IC returns (3%): ${cash_received * 0.03:,.2f}
  • Box cost ({implied_rate / 12:.2f}%): ${(cash_owed - cash_received) / (dte / 30):,.2f}
  • Net profit: ${cash_received * 0.03 - (cash_owed - cash_received) / (dte / 30):,.2f}
""".strip()

    def analyze_current_rates(self) -> BorrowingCostAnalysis:
        """
        Analyze current box spread rates vs alternatives.

        This provides a comprehensive view of whether now is a good
        time to open box spread positions.
        """
        now = datetime.now(CENTRAL_TZ)

        # Get current market data
        market_data = self._get_market_data()
        if not market_data:
            spot_price = 5950.0 if 'SPX' in self.config.ticker else 595.0
        else:
            spot_price = market_data['spot_price']

        # Price a sample box spread for rate calculation
        lower = round(spot_price / 10) * 10 - 25
        upper = lower + 50
        exp_date = date.today() + timedelta(days=180)
        expiration = exp_date.strftime('%Y-%m-%d')

        pricing = self._price_box_spread(lower, upper, expiration, market_data or {})
        if pricing:
            implied_rate = self._calculate_implied_rate(
                pricing['mid_price'], 50, 180
            )
        else:
            implied_rate = 4.5  # Fallback estimate

        # Get comparison rates (now dynamic!)
        self._refresh_rates()  # Ensure we have latest rates
        fed_funds = self._fed_funds_rate
        margin = self._margin_rate
        # Use cached SOFR if available, otherwise estimate
        if self._rates_cache:
            sofr = self._rates_cache.sofr_rate
        else:
            sofr = fed_funds - 0.05  # SOFR typically slightly below Fed Funds

        # Cost projections
        cost_monthly = (implied_rate / 12) * 1000  # Per $100K
        cost_annual = implied_rate * 1000

        # Break-even analysis
        required_ic_return = implied_rate / 12
        estimated_ic_return = 2.5  # Conservative estimate
        projected_profit = (estimated_ic_return - required_ic_return) * 1000

        # Rate trend from historical data
        avg_30d, avg_90d, trend = self._calculate_rate_trend(implied_rate)

        # Recommendation
        spread_to_margin = implied_rate - margin
        is_favorable = spread_to_margin < -1.0  # At least 100bps cheaper

        if is_favorable:
            recommendation = "FAVORABLE - Box spread borrowing is attractive"
            reasoning = f"""
Current box spread implied rate of {implied_rate:.2f}% is {abs(spread_to_margin):.2f}%
below typical margin rates. This represents meaningful savings.

With estimated IC returns of {estimated_ic_return:.2f}% monthly and box cost of
{required_ic_return:.2f}% monthly, the projected profit is {projected_profit:.2f}
per $100K borrowed.

Recommendation: Consider opening new box spread positions.
""".strip()
        else:
            recommendation = "NEUTRAL - Rates are not compelling"
            reasoning = f"""
Current box spread implied rate of {implied_rate:.2f}% offers only
{abs(spread_to_margin):.2f}% advantage over margin. The spread may not
justify the complexity of box spreads.

Consider waiting for more favorable rate conditions or using
margin for smaller positions.
""".strip()

        # Get rate source info
        rates_source = self._rates_cache.source if self._rates_cache else "fallback"
        rates_last_updated = self._rates_cache.last_updated if self._rates_cache else now

        return BorrowingCostAnalysis(
            analysis_time=now,
            box_implied_rate=implied_rate,
            fed_funds_rate=fed_funds,
            sofr_rate=sofr,
            broker_margin_rate=margin,
            spread_to_fed_funds=implied_rate - fed_funds,
            spread_to_margin=spread_to_margin,
            cost_per_100k_monthly=cost_monthly,
            cost_per_100k_annual=cost_annual,
            required_ic_return_monthly=required_ic_return,
            current_ic_return_estimate=estimated_ic_return,
            projected_profit_per_100k=projected_profit,
            avg_box_rate_30d=avg_30d,
            avg_box_rate_90d=avg_90d,
            rate_trend=trend,
            is_favorable=is_favorable,
            recommendation=recommendation,
            reasoning=reasoning,
            rates_source=rates_source,
            rates_last_updated=rates_last_updated,
        )


# ==============================================================================
# JUBILEE IC SIGNAL GENERATOR
# ==============================================================================
# Generates Iron Condor signals using borrowed capital from box spreads.
# This is the "returns side" of the JUBILEE system - IC trading generates
# the returns that (should) exceed the box spread borrowing costs.
# ==============================================================================

# Prophet import for IC trading decisions
try:
    from quant.prophet_advisor import ProphetAdvisor, MarketContext, GEXRegime
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    ProphetAdvisor = None
    MarketContext = None
    GEXRegime = None

# GEX calculator for gamma regime
try:
    from data.gex_calculator import TradierGEXCalculator
    GEX_AVAILABLE = True
except ImportError:
    GEX_AVAILABLE = False
    TradierGEXCalculator = None


class JubileeICSignalGenerator:
    """
    Generates Iron Condor signals for JUBILEE trading.

    EDUCATIONAL NOTE - IC Signal Generation:
    ========================================
    Iron Condors profit when the underlying stays within a range.
    Signal generation involves:

    1. Check market conditions (VIX, gamma regime)
    2. Get Prophet approval for IC trading
    3. Select strikes based on delta targeting (~10 delta)
    4. Calculate position size based on available capital
    5. Generate signal with full audit trail

    The goal: Generate consistent premium income that exceeds
    the borrowing cost from box spreads.
    """

    def __init__(self, config: JubileeICConfig = None):
        self.config = config or JubileeICConfig()
        self._init_components()

    def _init_components(self) -> None:
        """Initialize Prophet and GEX components"""
        # Prophet for IC trade approval
        self.prophet = None
        if PROPHET_AVAILABLE:
            try:
                self.prophet = ProphetAdvisor()
                logger.info("JUBILEE IC: Prophet initialized")
            except Exception as e:
                logger.warning(f"JUBILEE IC: Prophet init failed: {e}")

        # GEX calculator for gamma regime
        self.gex_calculator = None
        if GEX_AVAILABLE:
            try:
                self.gex_calculator = TradierGEXCalculator(sandbox=False)
                logger.info("JUBILEE IC: GEX Calculator initialized")
            except Exception as e:
                logger.warning(f"JUBILEE IC: GEX init failed: {e}")

    def get_market_data(self) -> Optional[Dict[str, Any]]:
        """
        Get current market data for IC signal generation.

        Uses PRODUCTION Tradier with retry logic for SPX quotes.
        No fallback to simulated data - returns None if unavailable.
        """
        try:
            # Get spot price
            spot = None
            vix = None
            gex_data = {}

            tradier = _get_tradier()
            if not tradier:
                logger.error("JUBILEE IC: Tradier not available - cannot get SPX quotes")
                return None

            # Get SPX quote with retry
            quote = _tradier_call_with_retry(tradier.get_quote, self.config.ticker)
            if quote:
                spot = quote.get('last', quote.get('bid', 0))

            # Get VIX with retry
            vix_quote = _tradier_call_with_retry(tradier.get_quote, 'VIX', max_retries=2)
            if vix_quote:
                vix = vix_quote.get('last', 20.0)

            if not spot:
                logger.error("JUBILEE IC: No spot price available from Tradier")
                return None

            vix = vix or 20.0

            # Get GEX data for gamma regime
            if self.gex_calculator:
                gex_data = self.gex_calculator.calculate_gex(self.config.ticker) or {}

            # Calculate expected move
            expected_move = self._calculate_expected_move(spot, vix)

            return {
                'spot_price': spot,
                'vix': vix,
                'expected_move': expected_move,
                'call_wall': gex_data.get('call_wall', 0),
                'put_wall': gex_data.get('put_wall', 0),
                'gex_regime': gex_data.get('regime', 'NEUTRAL'),
                'flip_point': gex_data.get('flip_point', 0),
                'net_gex': gex_data.get('net_gex', 0),
                'timestamp': datetime.now(CENTRAL_TZ),
            }

        except Exception as e:
            logger.error(f"JUBILEE IC: Market data error: {e}")
            return None

    def _calculate_expected_move(self, spot: float, vix: float) -> float:
        """Calculate 1 SD expected move"""
        annual_factor = math.sqrt(252)
        daily_vol = (vix / 100) / annual_factor
        return round(spot * daily_vol, 2)

    def get_prophet_advice(self, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get Prophet advice for IC trading.

        JUBILEE requires Prophet approval before opening IC positions.
        This ensures we only trade when conditions are favorable.
        """
        if not self.prophet or not PROPHET_AVAILABLE:
            logger.warning("JUBILEE IC: Prophet not available")
            return None

        try:
            # Build MarketContext
            gex_regime_str = market_data.get('gex_regime', 'NEUTRAL').upper()
            try:
                gex_regime = GEXRegime[gex_regime_str] if gex_regime_str in GEXRegime.__members__ else GEXRegime.NEUTRAL
            except (KeyError, AttributeError):
                gex_regime = GEXRegime.NEUTRAL

            spot = market_data['spot_price']
            context = MarketContext(
                spot_price=spot,
                vix=market_data['vix'],
                gex_call_wall=market_data.get('call_wall', 0),
                gex_put_wall=market_data.get('put_wall', 0),
                gex_regime=gex_regime,
                gex_flip_point=market_data.get('flip_point', 0),
                gex_net=market_data.get('net_gex', 0),
                expected_move_pct=(market_data.get('expected_move', 0) / spot * 100) if spot else 0,
            )

            # Get IC advice from Prophet (using ANCHOR method since we're trading SPX ICs)
            prediction = self.prophet.get_anchor_advice(
                context=context,
                use_gex_walls=True,
                use_claude_validation=False,  # Skip Claude for speed
                spread_width=self.config.spread_width,
            )

            if not prediction:
                return None

            # Extract top_factors as list of dicts
            top_factors = []
            if hasattr(prediction, 'top_factors') and prediction.top_factors:
                for factor_name, impact in prediction.top_factors:
                    top_factors.append({'factor': factor_name, 'impact': impact})

            return {
                'confidence': prediction.confidence,
                'win_probability': prediction.win_probability,
                'advice': prediction.advice.value if prediction.advice else 'HOLD',
                'top_factors': top_factors,
                'suggested_sd_multiplier': prediction.suggested_sd_multiplier,
                'suggested_put_strike': getattr(prediction, 'suggested_put_strike', None),
                'suggested_call_strike': getattr(prediction, 'suggested_call_strike', None),
                'reasoning': prediction.reasoning or '',
                'ic_suitability': getattr(prediction, 'ic_suitability', 0),
            }

        except Exception as e:
            logger.error(f"JUBILEE IC: Prophet error: {e}")
            return None

    def check_vix_filter(self, vix: float) -> Tuple[bool, str]:
        """Check if VIX is within acceptable range for IC trading"""
        if vix < self.config.min_vix:
            return False, f"VIX {vix:.1f} below minimum {self.config.min_vix} (premiums too thin)"
        if vix > self.config.max_vix:
            return False, f"VIX {vix:.1f} above maximum {self.config.max_vix} (too risky)"
        return True, f"VIX {vix:.1f} within acceptable range"

    def calculate_strikes(
        self,
        spot: float,
        expected_move: float,
        call_wall: float = 0,
        put_wall: float = 0,
        oracle_put_strike: Optional[float] = None,
        oracle_call_strike: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Calculate IC strikes with SPX $5 rounding.

        Priority:
        1. Prophet suggested strikes (if valid)
        2. GEX walls (if available)
        3. Delta-based strikes (fallback)
        """
        width = self.config.spread_width  # $25 for JUBILEE

        def round_to_5(x):
            return round(x / 5) * 5

        use_oracle = False
        use_gex = False

        # Priority 1: Prophet suggested strikes
        if oracle_put_strike and oracle_call_strike:
            put_dist = (spot - oracle_put_strike) / spot
            call_dist = (oracle_call_strike - spot) / spot
            if 0.003 <= put_dist <= 0.05 and 0.003 <= call_dist <= 0.05:
                put_short = round_to_5(oracle_put_strike)
                call_short = round_to_5(oracle_call_strike)
                use_oracle = True

        # Priority 2: GEX walls
        if not use_oracle and call_wall > 0 and put_wall > 0:
            put_short = round_to_5(put_wall)
            call_short = round_to_5(call_wall)
            use_gex = True

        # Priority 3: Delta-based fallback (~10 delta = ~1.0-1.2 SD)
        if not use_oracle and not use_gex:
            # ~10 delta is approximately 1.0-1.2 standard deviations
            sd_multiplier = 1.0
            min_expected_move = spot * 0.005
            effective_em = max(expected_move, min_expected_move)
            put_short = round_to_5(spot - sd_multiplier * effective_em)
            call_short = round_to_5(spot + sd_multiplier * effective_em)

        put_long = put_short - width
        call_long = call_short + width

        return {
            'put_short': put_short,
            'put_long': put_long,
            'call_short': call_short,
            'call_long': call_long,
            'using_gex': use_gex,
            'using_oracle': use_oracle,
            'source': 'PROPHET' if use_oracle else ('GEX' if use_gex else 'DELTA'),
        }

    def estimate_credits(
        self,
        spot: float,
        expected_move: float,
        put_short: float,
        call_short: float,
        vix: float
    ) -> Dict[str, float]:
        """Estimate IC credits for SPX"""
        width = self.config.spread_width

        put_dist = (spot - put_short) / expected_move if expected_move > 0 else 1
        call_dist = (call_short - spot) / expected_move if expected_move > 0 else 1
        vol_factor = vix / 20.0

        # SPX typically has good premiums
        put_credit = width * 0.025 * vol_factor / max(put_dist, 0.5)
        call_credit = width * 0.025 * vol_factor / max(call_dist, 0.5)

        put_credit = max(0.30, min(put_credit, width * 0.35))
        call_credit = max(0.30, min(call_credit, width * 0.35))

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

    def calculate_position_size(
        self,
        available_capital: float,
        max_loss_per_contract: float
    ) -> int:
        """
        Calculate position size based on available capital and risk limits.

        JUBILEE/JUBILEE uses AGGRESSIVE sizing with borrowed capital.
        Position size is determined by:
        1. Available capital × max_capital_per_trade_pct = max risk
        2. max risk ÷ max loss per contract = calculated contracts
        3. Apply configurable max_contracts limit (safety ceiling)
        """
        # Guard against invalid inputs
        if available_capital <= 0:
            logger.warning("JUBILEE IC: No available capital for position sizing")
            return 1
        if max_loss_per_contract <= 0:
            logger.warning("JUBILEE IC: Invalid max_loss_per_contract (<=0)")
            return 1

        # Max capital at risk per trade
        max_risk = available_capital * (self.config.max_capital_per_trade_pct / 100)

        # Contracts based on max loss
        calculated_contracts = int(max_risk / max_loss_per_contract)

        # Apply configurable max (safety ceiling to prevent data-error blowups)
        final_contracts = max(1, min(calculated_contracts, self.config.max_contracts))

        # Log position sizing math for transparency
        logger.info(
            f"JUBILEE IC Position Sizing: "
            f"available_capital=${available_capital:,.0f}, "
            f"max_risk_pct={self.config.max_capital_per_trade_pct}%, "
            f"max_risk=${max_risk:,.0f}, "
            f"max_loss_per_contract=${max_loss_per_contract:,.0f}, "
            f"calculated_contracts={calculated_contracts}, "
            f"max_contracts_config={self.config.max_contracts}, "
            f"final_contracts={final_contracts}"
        )

        return final_contracts

    def generate_signal(
        self,
        source_box_position_id: str,
        available_capital: float,
    ) -> Optional[JubileeICSignal]:
        """
        Generate an Iron Condor signal for JUBILEE.

        Args:
            source_box_position_id: ID of the box spread funding this trade
            available_capital: Capital available for this trade

        Returns:
            JubileeICSignal if conditions are favorable, None otherwise
        """
        now = datetime.now(CENTRAL_TZ)

        # Get market data
        market = self.get_market_data()
        if not market:
            logger.warning("JUBILEE IC: No market data available")
            return None

        spot = market['spot_price']
        vix = market['vix']

        # VIX filter
        can_trade, vix_reason = self.check_vix_filter(vix)
        if not can_trade:
            logger.info(f"JUBILEE IC: {vix_reason}")
            return self._create_skip_signal(
                now, source_box_position_id, market, vix_reason
            )

        # Get Prophet advice
        prophet = self.get_prophet_advice(market)
        if not prophet:
            logger.warning("JUBILEE IC: No Prophet advice available")
            return self._create_skip_signal(
                now, source_box_position_id, market, "Prophet not available"
            )

        oracle_advice = prophet.get('advice', 'HOLD')
        oracle_confidence = prophet.get('confidence', 0)
        oracle_win_prob = prophet.get('win_probability', 0)

        # Log Prophet advice (informational - ANCHOR style)
        logger.info(f"JUBILEE IC Prophet: advice={oracle_advice}, confidence={oracle_confidence:.0%}, win_prob={oracle_win_prob:.0%}")

        # Check Prophet thresholds if required
        # NOTE: Like ANCHOR, we only check win_probability threshold, NOT the advice string
        # Prophet advice string (TRADE_FULL/SKIP_TODAY) is informational only
        oracle_approved = True  # Will be set to False only if we fail the threshold check
        if self.config.require_oracle_approval:
            # Only check win probability - this is how ANCHOR works
            if oracle_win_prob < self.config.min_win_probability:
                skip_reason = f"Win probability {oracle_win_prob:.0%} below min {self.config.min_win_probability:.0%}"
                logger.info(f"JUBILEE IC: {skip_reason}")
                return self._create_skip_signal(
                    now, source_box_position_id, market, skip_reason, prophet
                )
            # If we pass the threshold, Prophet approved
            logger.info(f"JUBILEE IC: Prophet APPROVED (win_prob {oracle_win_prob:.0%} >= {self.config.min_win_probability:.0%})")

        # Calculate strikes
        strikes = self.calculate_strikes(
            spot,
            market['expected_move'],
            market.get('call_wall', 0),
            market.get('put_wall', 0),
            prophet.get('suggested_put_strike'),
            prophet.get('suggested_call_strike'),
        )

        # Estimate credits
        pricing = self.estimate_credits(
            spot,
            market['expected_move'],
            strikes['put_short'],
            strikes['call_short'],
            vix,
        )

        # Calculate position size
        contracts = self.calculate_position_size(
            available_capital,
            pricing['max_loss']
        )

        total_credit = pricing['total_credit']
        max_loss = pricing['max_loss'] * contracts
        margin_required = self.config.spread_width * 100 * contracts

        # Calculate expiration (0DTE or next available)
        if self.config.prefer_0dte:
            # Today's expiration for 0DTE
            expiration = now.strftime('%Y-%m-%d')
            dte = 0
        else:
            # Next Friday
            days_until_friday = (4 - now.weekday()) % 7
            if days_until_friday == 0 and now.hour >= 15:
                days_until_friday = 7
            exp_date = now + timedelta(days=days_until_friday)
            expiration = exp_date.strftime('%Y-%m-%d')
            dte = days_until_friday

        # Calculate probability of profit (approximate from delta)
        # ~10 delta short strikes = ~80% PoP for IC
        put_dist_pct = abs(spot - strikes['put_short']) / spot * 100
        call_dist_pct = abs(strikes['call_short'] - spot) / spot * 100
        avg_dist = (put_dist_pct + call_dist_pct) / 2
        pop = min(0.85, 0.5 + avg_dist * 5)  # Rough approximation

        # Build reasoning
        reasoning_parts = [
            f"Prophet: {oracle_advice} ({oracle_confidence:.0%})",
            f"Win Prob: {oracle_win_prob:.0%}",
            f"VIX: {vix:.1f}",
            f"Strikes via {strikes['source']}",
        ]
        if prophet.get('top_factors'):
            top_factor = prophet['top_factors'][0]
            reasoning_parts.append(f"Top: {top_factor['factor']}")

        logger.info(
            f"JUBILEE IC: Signal generated - "
            f"{strikes['put_short']}/{strikes['put_long']} PUT, "
            f"{strikes['call_short']}/{strikes['call_long']} CALL, "
            f"credit=${total_credit:.2f}, contracts={contracts}"
        )

        return JubileeICSignal(
            signal_id=f"PROM-IC-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            signal_time=now,
            source_box_position_id=source_box_position_id,
            ticker=self.config.ticker,
            spot_price=spot,
            # Put spread
            put_short_strike=strikes['put_short'],
            put_long_strike=strikes['put_long'],
            put_spread_width=self.config.spread_width,
            # Call spread
            call_short_strike=strikes['call_short'],
            call_long_strike=strikes['call_long'],
            call_spread_width=self.config.spread_width,
            # Expiration
            expiration=expiration,
            dte=dte,
            # Pricing
            put_spread_credit=pricing['put_credit'],
            call_spread_credit=pricing['call_credit'],
            total_credit=total_credit,
            max_loss=pricing['max_loss'],
            # Risk metrics
            probability_of_profit=pop,
            delta_of_short_put=-self.config.short_put_delta,
            delta_of_short_call=self.config.short_call_delta,
            # Sizing
            contracts=contracts,
            margin_required=margin_required,
            capital_at_risk=max_loss,
            # Prophet
            oracle_approved=oracle_approved,
            oracle_confidence=oracle_confidence,
            oracle_reasoning=" | ".join(reasoning_parts),
            # Market context
            vix_level=vix,
            gamma_regime=market.get('gex_regime', 'NEUTRAL'),
            gex_regime=market.get('gex_regime', 'NEUTRAL'),
            # Validity
            is_valid=True,
            skip_reason="",
        )

    def _create_skip_signal(
        self,
        signal_time: datetime,
        source_box_position_id: str,
        market: Dict[str, Any],
        skip_reason: str,
        prophet: Dict[str, Any] = None,
    ) -> JubileeICSignal:
        """Create a signal that was skipped (for audit trail)"""
        return JubileeICSignal(
            signal_id=f"PROM-IC-SKIP-{signal_time.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}",
            signal_time=signal_time,
            source_box_position_id=source_box_position_id,
            ticker=self.config.ticker,
            spot_price=market.get('spot_price', 0),
            # Empty strikes
            put_short_strike=0,
            put_long_strike=0,
            put_spread_width=0,
            call_short_strike=0,
            call_long_strike=0,
            call_spread_width=0,
            expiration="",
            dte=0,
            # Empty pricing
            put_spread_credit=0,
            call_spread_credit=0,
            total_credit=0,
            max_loss=0,
            probability_of_profit=0,
            delta_of_short_put=0,
            delta_of_short_call=0,
            contracts=0,
            margin_required=0,
            capital_at_risk=0,
            # Prophet context
            oracle_approved=False,
            oracle_confidence=prophet.get('confidence', 0) if prophet else 0,
            oracle_reasoning=prophet.get('reasoning', '') if prophet else '',
            # Market context
            vix_level=market.get('vix', 0),
            gamma_regime=market.get('gex_regime', 'NEUTRAL'),
            gex_regime=market.get('gex_regime', 'NEUTRAL'),
            # Skipped
            is_valid=False,
            skip_reason=skip_reason,
        )
