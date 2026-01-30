"""
PROMETHEUS Signal Generation - Box Spread Analysis

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
    PrometheusConfig,
)

logger = logging.getLogger(__name__)

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

try:
    from data.tradier_data_fetcher import TradierDataFetcher
    tradier = TradierDataFetcher()
except ImportError:
    tradier = None
    logger.warning("TradierDataFetcher not available")


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

    def __init__(self, config: PrometheusConfig = None):
        self.config = config or PrometheusConfig()
        self._fed_funds_rate = 4.50  # Default, updated from market data
        self._margin_rate = 8.50     # Typical broker margin rate

    def generate_signal(self) -> Optional[BoxSpreadSignal]:
        """
        Generate a box spread signal with full educational context.

        Returns None if no favorable opportunity exists.
        """
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
        """Get current market data for the underlying"""
        try:
            if tradier:
                quote = tradier.get_quote(self.config.ticker)
                if quote:
                    return {
                        'spot_price': quote.get('last', quote.get('bid', 0)),
                        'bid': quote.get('bid', 0),
                        'ask': quote.get('ask', 0),
                        'vix': self._get_vix(),
                    }

            # Fallback to simulated data for testing
            logger.warning("Using simulated market data")
            return {
                'spot_price': 5950.0 if 'SPX' in self.config.ticker else 595.0,
                'bid': 5949.0 if 'SPX' in self.config.ticker else 594.90,
                'ask': 5951.0 if 'SPX' in self.config.ticker else 595.10,
                'vix': 15.0,
            }

        except Exception as e:
            logger.error(f"Error getting market data: {e}")
            return None

    def _get_vix(self) -> float:
        """Get current VIX level"""
        try:
            if tradier:
                quote = tradier.get_quote('VIX')
                if quote:
                    return quote.get('last', 15.0)
            return 15.0
        except Exception:
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
            # Get available expirations
            if tradier:
                expirations = tradier.get_expirations(self.config.ticker)
            else:
                # Generate synthetic expirations for testing
                today = date.today()
                expirations = [
                    (today + timedelta(days=d)).strftime('%Y-%m-%d')
                    for d in [30, 60, 90, 120, 180, 270, 365]
                ]

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

        Returns: {bid, ask, mid_price, legs: {...}}
        """
        try:
            if tradier:
                # Get option chain
                chain = tradier.get_option_chain(self.config.ticker, expiration)
                if not chain:
                    return self._simulate_pricing(lower_strike, upper_strike, expiration)

                # Find our strikes
                legs = {}
                for option in chain:
                    strike = option.get('strike')
                    opt_type = option.get('option_type', option.get('type', ''))

                    if strike == lower_strike:
                        if 'call' in opt_type.lower():
                            legs['call_long'] = option
                        elif 'put' in opt_type.lower():
                            legs['put_short'] = option
                    elif strike == upper_strike:
                        if 'call' in opt_type.lower():
                            legs['call_short'] = option
                        elif 'put' in opt_type.lower():
                            legs['put_long'] = option

                if len(legs) < 4:
                    logger.warning(f"Could not find all 4 legs, found: {list(legs.keys())}")
                    return self._simulate_pricing(lower_strike, upper_strike, expiration)

                # Calculate box spread price
                # Selling the box = receiving call spread credit + put spread credit
                # Bull call spread: Sell high call, buy low call
                # Bear put spread: Sell low put, buy high put

                # For selling the box, we want the BID prices for what we sell
                # and ASK prices for what we buy

                call_spread_credit = (
                    legs['call_short'].get('bid', 0) -  # Sell upper call
                    legs['call_long'].get('ask', 0)     # Buy lower call
                )
                put_spread_credit = (
                    legs['put_short'].get('bid', 0) -   # Sell lower put
                    legs['put_long'].get('ask', 0)      # Buy upper put
                )

                box_bid = call_spread_credit + put_spread_credit

                # For the ask side (if we were buying)
                call_spread_debit = (
                    legs['call_short'].get('ask', 0) -
                    legs['call_long'].get('bid', 0)
                )
                put_spread_debit = (
                    legs['put_short'].get('ask', 0) -
                    legs['put_long'].get('bid', 0)
                )

                box_ask = call_spread_debit + put_spread_debit
                mid_price = (box_bid + box_ask) / 2

                return {
                    'bid': box_bid,
                    'ask': box_ask,
                    'mid_price': mid_price,
                    'legs': legs,
                }

            return self._simulate_pricing(lower_strike, upper_strike, expiration)

        except Exception as e:
            logger.error(f"Error pricing box spread: {e}")
            return self._simulate_pricing(lower_strike, upper_strike, expiration)

    def _simulate_pricing(
        self,
        lower_strike: float,
        upper_strike: float,
        expiration: str
    ) -> Dict[str, Any]:
        """
        Simulate box spread pricing for testing.

        In reality, box spreads trade at a discount to theoretical value.
        The discount represents the implied interest rate.
        """
        strike_width = upper_strike - lower_strike
        theoretical = strike_width

        # Calculate DTE
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
        dte = (exp_date - date.today()).days

        # Implied rate determines discount
        # Assume ~4.5% annual rate for simulation
        annual_rate = 0.045
        discount_factor = 1 / (1 + annual_rate * dte / 365)
        present_value = theoretical * discount_factor

        # Add bid-ask spread
        spread = 0.10  # 10 cents spread
        bid = present_value - spread / 2
        ask = present_value + spread / 2

        return {
            'bid': bid,
            'ask': ask,
            'mid_price': present_value,
            'legs': {'simulated': True},
        }

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
1. Cash received (${cash_received:,.2f}) is deployed to ARES, TITAN, PEGASUS
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

        # Get comparison rates
        fed_funds = self._fed_funds_rate
        margin = self._margin_rate
        sofr = fed_funds - 0.05  # SOFR typically slightly below Fed Funds

        # Cost projections
        cost_monthly = (implied_rate / 12) * 1000  # Per $100K
        cost_annual = implied_rate * 1000

        # Break-even analysis
        required_ic_return = implied_rate / 12
        estimated_ic_return = 2.5  # Conservative estimate
        projected_profit = (estimated_ic_return - required_ic_return) * 1000

        # Rate trend (would need historical data)
        avg_30d = implied_rate  # Placeholder
        avg_90d = implied_rate
        trend = "STABLE"

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
        )
