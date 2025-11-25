"""
Realistic Option Pricing Module for AlphaGEX

This module provides realistic option pricing for backtesting, including:
- Strike selection based on delta/moneyness
- Intrinsic and time value calculations
- Greeks calculations (delta, gamma, theta, vega)
- Bid/ask spread modeling
- Realistic P&L calculations for spreads

Replaces the simplified directional pricing model with realistic option mechanics.
"""

import math
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from scipy.stats import norm
import numpy as np


class BlackScholesOption:
    """
    Black-Scholes option pricing model with Greeks calculations.

    This provides the foundation for realistic option pricing in backtests.
    """

    def __init__(self, spot_price: float, strike: float, time_to_expiry: float,
                 risk_free_rate: float, volatility: float, option_type: str = 'call'):
        """
        Args:
            spot_price: Current stock price
            strike: Option strike price
            time_to_expiry: Time to expiration in years (e.g., 30 days = 30/365)
            risk_free_rate: Risk-free interest rate (e.g., 0.05 for 5%)
            volatility: Implied volatility (e.g., 0.25 for 25% IV)
            option_type: 'call' or 'put'
        """
        self.S = spot_price
        self.K = strike
        self.T = time_to_expiry
        self.r = risk_free_rate
        self.sigma = volatility
        self.option_type = option_type.lower()

    def _d1(self) -> float:
        """Calculate d1 parameter for Black-Scholes"""
        if self.T <= 0:
            return 0
        return (math.log(self.S / self.K) + (self.r + 0.5 * self.sigma**2) * self.T) / (self.sigma * math.sqrt(self.T))

    def _d2(self) -> float:
        """Calculate d2 parameter for Black-Scholes"""
        if self.T <= 0:
            return 0
        return self._d1() - self.sigma * math.sqrt(self.T)

    def price(self) -> float:
        """Calculate option theoretical value"""
        if self.T <= 0:
            # At expiration, only intrinsic value remains
            if self.option_type == 'call':
                return max(0, self.S - self.K)
            else:
                return max(0, self.K - self.S)

        d1 = self._d1()
        d2 = self._d2()

        if self.option_type == 'call':
            return self.S * norm.cdf(d1) - self.K * math.exp(-self.r * self.T) * norm.cdf(d2)
        else:
            return self.K * math.exp(-self.r * self.T) * norm.cdf(-d2) - self.S * norm.cdf(-d1)

    def delta(self) -> float:
        """
        Calculate delta: rate of change of option price with respect to stock price
        Call delta: 0 to 1
        Put delta: -1 to 0
        """
        if self.T <= 0:
            if self.option_type == 'call':
                return 1.0 if self.S > self.K else 0.0
            else:
                return -1.0 if self.S < self.K else 0.0

        d1 = self._d1()
        if self.option_type == 'call':
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1

    def gamma(self) -> float:
        """
        Calculate gamma: rate of change of delta with respect to stock price
        Same for calls and puts
        """
        if self.T <= 0:
            return 0.0

        d1 = self._d1()
        return norm.pdf(d1) / (self.S * self.sigma * math.sqrt(self.T))

    def theta(self) -> float:
        """
        Calculate theta: rate of change of option price with respect to time
        Expressed as daily decay (divide by 365)
        """
        if self.T <= 0:
            return 0.0

        d1 = self._d1()
        d2 = self._d2()

        term1 = -(self.S * norm.pdf(d1) * self.sigma) / (2 * math.sqrt(self.T))

        if self.option_type == 'call':
            term2 = -self.r * self.K * math.exp(-self.r * self.T) * norm.cdf(d2)
            return (term1 + term2) / 365  # Daily theta
        else:
            term2 = self.r * self.K * math.exp(-self.r * self.T) * norm.cdf(-d2)
            return (term1 + term2) / 365  # Daily theta

    def vega(self) -> float:
        """
        Calculate vega: rate of change of option price with respect to volatility
        Same for calls and puts
        Expressed per 1% change in IV
        """
        if self.T <= 0:
            return 0.0

        d1 = self._d1()
        return self.S * norm.pdf(d1) * math.sqrt(self.T) / 100  # Per 1% IV change


class StrikeSelector:
    """
    Selects realistic strike prices for option strategies based on:
    - Delta targeting (e.g., 30-delta for credit spreads)
    - Moneyness (e.g., ATM, 5% OTM)
    - Available strikes (realistic strike intervals)
    """

    @staticmethod
    def get_available_strikes(spot_price: float, strike_interval: float = 5.0) -> list:
        """
        Generate realistic available strikes around current price.
        Most stocks have $5 or $2.50 strike intervals.

        Args:
            spot_price: Current stock price
            strike_interval: Strike spacing (5.0 for $5 intervals)

        Returns:
            List of available strikes from -20% to +20% of spot
        """
        base = round(spot_price / strike_interval) * strike_interval
        strikes = []

        # Generate strikes from -20% to +20%
        for i in range(-8, 9):
            strike = base + (i * strike_interval)
            if strike > 0:
                strikes.append(strike)

        return sorted(strikes)

    @staticmethod
    def select_strike_by_delta(spot_price: float, target_delta: float,
                               time_to_expiry: float, volatility: float,
                               option_type: str = 'call',
                               risk_free_rate: float = 0.05) -> float:
        """
        Select strike that achieves target delta.

        Args:
            spot_price: Current stock price
            target_delta: Desired delta (e.g., 0.30 for 30-delta call)
            time_to_expiry: Time to expiration in years
            volatility: Implied volatility
            option_type: 'call' or 'put'
            risk_free_rate: Risk-free rate

        Returns:
            Strike price closest to target delta
        """
        available_strikes = StrikeSelector.get_available_strikes(spot_price)

        best_strike = available_strikes[0]
        best_delta_diff = float('inf')

        for strike in available_strikes:
            option = BlackScholesOption(
                spot_price, strike, time_to_expiry,
                risk_free_rate, volatility, option_type
            )
            delta = abs(option.delta())  # Use absolute value for comparison
            delta_diff = abs(delta - abs(target_delta))

            if delta_diff < best_delta_diff:
                best_delta_diff = delta_diff
                best_strike = strike

        return best_strike

    @staticmethod
    def select_strike_by_moneyness(spot_price: float, percent_otm: float,
                                   option_type: str = 'call') -> float:
        """
        Select strike based on moneyness (% OTM/ITM).

        Args:
            spot_price: Current stock price
            percent_otm: Percentage out-of-the-money (e.g., 5.0 for 5% OTM)
            option_type: 'call' or 'put'

        Returns:
            Strike price at specified moneyness
        """
        if option_type == 'call':
            target_strike = spot_price * (1 + percent_otm / 100)
        else:
            target_strike = spot_price * (1 - percent_otm / 100)

        # Round to nearest $5 strike
        available_strikes = StrikeSelector.get_available_strikes(spot_price)
        return min(available_strikes, key=lambda x: abs(x - target_strike))


class SpreadPricer:
    """
    Prices option spreads with realistic mechanics:
    - Intrinsic and time value
    - Bid/ask spreads
    - Slippage
    - Greeks for the entire spread
    """

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Args:
            risk_free_rate: Risk-free interest rate (default 5%)
        """
        self.risk_free_rate = risk_free_rate

    def price_vertical_spread(self, spot_price: float, long_strike: float,
                             short_strike: float, time_to_expiry: float,
                             volatility: float, option_type: str = 'call',
                             include_slippage: bool = True) -> Dict:
        """
        Price a vertical spread (bull/bear call/put spread).

        Args:
            spot_price: Current stock price
            long_strike: Strike of long option
            short_strike: Strike of short option
            time_to_expiry: Time to expiration in years
            volatility: Implied volatility
            option_type: 'call' or 'put'
            include_slippage: Whether to include bid/ask spread and slippage

        Returns:
            Dictionary with spread details:
            - debit: Cost to enter spread
            - max_profit: Maximum profit potential
            - max_loss: Maximum loss potential
            - breakeven: Breakeven stock price
            - net_delta: Spread delta
            - net_theta: Spread theta (daily)
            - net_vega: Spread vega
        """
        # Price both legs
        long_option = BlackScholesOption(
            spot_price, long_strike, time_to_expiry,
            self.risk_free_rate, volatility, option_type
        )

        short_option = BlackScholesOption(
            spot_price, short_strike, time_to_expiry,
            self.risk_free_rate, volatility, option_type
        )

        # Theoretical mid prices
        long_price = long_option.price()
        short_price = short_option.price()

        # Apply bid/ask spread if requested (typically 3-5% of option price)
        if include_slippage:
            # Pay ask when buying, receive bid when selling
            bid_ask_pct = 0.04  # 4% bid/ask spread
            long_price_ask = long_price * (1 + bid_ask_pct)
            short_price_bid = short_price * (1 - bid_ask_pct)

            # Additional slippage for multi-leg orders (1-2%)
            slippage_pct = 0.015  # 1.5% additional slippage
            debit = (long_price_ask - short_price_bid) * (1 + slippage_pct)
        else:
            debit = long_price - short_price

        # Calculate spread parameters
        spread_width = abs(long_strike - short_strike)

        if option_type == 'call':
            if long_strike < short_strike:
                # Bull call spread
                max_profit = spread_width - debit
                max_loss = debit
                breakeven = long_strike + debit
            else:
                # Bear call spread (credit spread)
                max_profit = debit  # Would be negative (credit received)
                max_loss = spread_width - abs(debit)
                breakeven = short_strike + abs(debit)
        else:
            if long_strike > short_strike:
                # Bear put spread
                max_profit = spread_width - debit
                max_loss = debit
                breakeven = long_strike - debit
            else:
                # Bull put spread (credit spread)
                max_profit = debit  # Would be negative (credit received)
                max_loss = spread_width - abs(debit)
                breakeven = short_strike - abs(debit)

        # Calculate net Greeks (long - short)
        net_delta = long_option.delta() - short_option.delta()
        net_gamma = long_option.gamma() - short_option.gamma()
        net_theta = long_option.theta() - short_option.theta()
        net_vega = long_option.vega() - short_option.vega()

        return {
            'debit': debit,
            'long_price': long_price,
            'short_price': short_price,
            'max_profit': max_profit,
            'max_loss': max_loss,
            'breakeven': breakeven,
            'spread_width': spread_width,
            'net_delta': net_delta,
            'net_gamma': net_gamma,
            'net_theta': net_theta,
            'net_vega': net_vega,
            'long_strike': long_strike,
            'short_strike': short_strike
        }

    def calculate_spread_pnl(self, spread_details: Dict, current_price: float,
                            days_held: int, entry_volatility: float,
                            exit_volatility: Optional[float] = None) -> Dict:
        """
        Calculate realistic P&L for a spread position.

        Args:
            spread_details: Original spread details from price_vertical_spread()
            current_price: Current stock price
            days_held: Days since entry
            entry_volatility: IV at entry
            exit_volatility: IV at exit (if None, assume unchanged)

        Returns:
            Dictionary with P&L details:
            - current_value: Current spread value
            - pnl_dollars: P&L in dollars
            - pnl_percent: P&L as % of debit paid
            - intrinsic_value: Intrinsic value component
            - time_value: Time value component
            - iv_pnl: P&L from IV changes
        """
        if exit_volatility is None:
            exit_volatility = entry_volatility

        # Calculate remaining time to expiry
        original_dte = spread_details.get('original_dte', 30)  # Default 30 days
        remaining_dte = max(0, original_dte - days_held)
        time_to_expiry = remaining_dte / 365.0

        # Get spread parameters
        long_strike = spread_details['long_strike']
        short_strike = spread_details['short_strike']
        option_type = spread_details.get('option_type', 'call')

        # Calculate current value of both legs
        if time_to_expiry > 0:
            long_option = BlackScholesOption(
                current_price, long_strike, time_to_expiry,
                self.risk_free_rate, exit_volatility, option_type
            )
            short_option = BlackScholesOption(
                current_price, short_strike, time_to_expiry,
                self.risk_free_rate, exit_volatility, option_type
            )

            long_value = long_option.price()
            short_value = short_option.price()
        else:
            # At expiration, only intrinsic value
            if option_type == 'call':
                long_value = max(0, current_price - long_strike)
                short_value = max(0, current_price - short_strike)
            else:
                long_value = max(0, long_strike - current_price)
                short_value = max(0, short_strike - current_price)

        current_value = long_value - short_value

        # Calculate intrinsic and time value
        if option_type == 'call':
            long_intrinsic = max(0, current_price - long_strike)
            short_intrinsic = max(0, current_price - short_strike)
        else:
            long_intrinsic = max(0, long_strike - current_price)
            short_intrinsic = max(0, short_strike - current_price)

        intrinsic_value = long_intrinsic - short_intrinsic
        time_value = current_value - intrinsic_value

        # Calculate P&L
        entry_debit = spread_details['debit']
        pnl_dollars = current_value - entry_debit
        pnl_percent = (pnl_dollars / entry_debit) * 100 if entry_debit != 0 else 0

        # Estimate IV contribution (rough approximation)
        iv_change = exit_volatility - entry_volatility
        iv_pnl = spread_details['net_vega'] * (iv_change * 100)  # Vega per 1% IV

        return {
            'current_value': current_value,
            'pnl_dollars': pnl_dollars,
            'pnl_percent': pnl_percent,
            'intrinsic_value': intrinsic_value,
            'time_value': time_value,
            'iv_pnl': iv_pnl,
            'long_value': long_value,
            'short_value': short_value,
            'days_held': days_held,
            'remaining_dte': remaining_dte
        }


def create_bullish_call_spread(spot_price: float, volatility: float,
                                dte: int = 30, target_delta: float = 0.30,
                                spread_width_pct: float = 5.0) -> Dict:
    """
    Convenience function to create a realistic bullish call spread.

    Args:
        spot_price: Current stock price
        volatility: Implied volatility (e.g., 0.25 for 25%)
        dte: Days to expiration
        target_delta: Target delta for long call (e.g., 0.30 for 30-delta)
        spread_width_pct: Spread width as % of spot (e.g., 5.0 for 5% wide)

    Returns:
        Spread details dictionary
    """
    time_to_expiry = dte / 365.0
    selector = StrikeSelector()
    pricer = SpreadPricer()

    # Select long strike based on delta
    long_strike = selector.select_strike_by_delta(
        spot_price, target_delta, time_to_expiry, volatility, 'call'
    )

    # Short strike is spread_width higher
    short_strike = long_strike * (1 + spread_width_pct / 100)
    short_strike = selector.select_strike_by_moneyness(
        long_strike, spread_width_pct, 'call'
    )

    # Price the spread
    spread = pricer.price_vertical_spread(
        spot_price, long_strike, short_strike,
        time_to_expiry, volatility, 'call'
    )

    spread['option_type'] = 'call'
    spread['original_dte'] = dte

    return spread


def create_bearish_put_spread(spot_price: float, volatility: float,
                              dte: int = 30, target_delta: float = -0.30,
                              spread_width_pct: float = 5.0) -> Dict:
    """
    Convenience function to create a realistic bearish put spread.

    Args:
        spot_price: Current stock price
        volatility: Implied volatility
        dte: Days to expiration
        target_delta: Target delta for long put (e.g., -0.30 for 30-delta)
        spread_width_pct: Spread width as % of spot

    Returns:
        Spread details dictionary
    """
    time_to_expiry = dte / 365.0
    selector = StrikeSelector()
    pricer = SpreadPricer()

    # Select long strike based on delta
    long_strike = selector.select_strike_by_delta(
        spot_price, target_delta, time_to_expiry, volatility, 'put'
    )

    # Short strike is spread_width lower
    short_strike = long_strike * (1 - spread_width_pct / 100)
    short_strike = selector.select_strike_by_moneyness(
        long_strike, spread_width_pct, 'put'
    )

    # Price the spread
    spread = pricer.price_vertical_spread(
        spot_price, long_strike, short_strike,
        time_to_expiry, volatility, 'put'
    )

    spread['option_type'] = 'put'
    spread['original_dte'] = dte

    return spread


if __name__ == "__main__":
    # Example usage and testing
    print("=" * 60)
    print("Realistic Option Pricing Module - Example Usage")
    print("=" * 60)

    # Example 1: Price a single call option with Greeks
    print("\nExample 1: Single Call Option")
    print("-" * 60)
    spot = 400.0
    strike = 410.0
    dte = 30
    vol = 0.25

    call = BlackScholesOption(spot, strike, dte/365, 0.05, vol, 'call')
    print(f"Spot: ${spot:.2f}, Strike: ${strike:.2f}, DTE: {dte}, IV: {vol*100:.1f}%")
    print(f"Theoretical Value: ${call.price():.2f}")
    print(f"Delta: {call.delta():.3f}")
    print(f"Gamma: {call.gamma():.4f}")
    print(f"Theta: ${call.theta():.2f}/day")
    print(f"Vega: ${call.vega():.2f} per 1% IV")

    # Example 2: Create and price a bullish call spread
    print("\nExample 2: Bullish Call Spread")
    print("-" * 60)
    spread = create_bullish_call_spread(spot, vol, dte=30, target_delta=0.30)
    print(f"Long Strike: ${spread['long_strike']:.2f}")
    print(f"Short Strike: ${spread['short_strike']:.2f}")
    print(f"Debit Paid: ${spread['debit']:.2f}")
    print(f"Max Profit: ${spread['max_profit']:.2f}")
    print(f"Max Loss: ${spread['max_loss']:.2f}")
    print(f"Breakeven: ${spread['breakeven']:.2f}")
    print(f"Net Delta: {spread['net_delta']:.3f}")
    print(f"Net Theta: ${spread['net_theta']:.2f}/day")

    # Example 3: Calculate P&L after price move
    print("\nExample 3: P&L After 10 Days, +5% Move")
    print("-" * 60)
    pricer = SpreadPricer()
    new_spot = spot * 1.05  # +5% move
    pnl = pricer.calculate_spread_pnl(spread, new_spot, days_held=10, entry_volatility=vol)
    print(f"New Spot: ${new_spot:.2f}")
    print(f"Current Spread Value: ${pnl['current_value']:.2f}")
    print(f"P&L: ${pnl['pnl_dollars']:.2f} ({pnl['pnl_percent']:.1f}%)")
    print(f"Intrinsic Value: ${pnl['intrinsic_value']:.2f}")
    print(f"Time Value: ${pnl['time_value']:.2f}")
    print(f"Days Held: {pnl['days_held']}, Remaining DTE: {pnl['remaining_dte']}")

    print("\n" + "=" * 60)
    print("Module ready for integration with backtest_options_strategies.py")
    print("=" * 60)
