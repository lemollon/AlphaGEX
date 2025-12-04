"""
Implied Volatility Solver using Newton-Raphson Method

This module calculates implied volatility from option prices using
the Newton-Raphson iterative method. Critical for accurate backtesting.

Usage:
    from quant.iv_solver import calculate_iv_from_price, IVSolver

    iv = calculate_iv_from_price(
        option_price=5.50,
        spot=5800,
        strike=5750,
        dte=45,
        option_type='put'
    )
"""

import math
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from scipy.stats import norm
import numpy as np
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class IVResult:
    """Result of IV calculation"""
    iv: float                    # Implied volatility (decimal, e.g., 0.20 = 20%)
    converged: bool              # Whether Newton-Raphson converged
    iterations: int              # Number of iterations taken
    price_error: float           # Difference between target and calculated price
    method: str                  # 'newton_raphson', 'bisection', or 'fallback'
    confidence: str              # 'HIGH', 'MEDIUM', 'LOW'


class IVSolver:
    """
    Newton-Raphson Implied Volatility Solver

    Calculates the implied volatility that, when plugged into Black-Scholes,
    produces the observed market price.
    """

    def __init__(self, risk_free_rate: float = 0.05, max_iterations: int = 100,
                 tolerance: float = 1e-6):
        """
        Args:
            risk_free_rate: Annual risk-free rate (default 5%)
            max_iterations: Maximum Newton-Raphson iterations
            tolerance: Price tolerance for convergence
        """
        self.risk_free_rate = risk_free_rate
        self.max_iterations = max_iterations
        self.tolerance = tolerance

        # Stats tracking
        self.stats = {
            'newton_raphson_success': 0,
            'bisection_fallback': 0,
            'failed': 0,
            'total_calls': 0
        }

    def calculate_iv(
        self,
        option_price: float,
        spot: float,
        strike: float,
        time_to_expiry: float,
        option_type: str = 'put'
    ) -> IVResult:
        """
        Calculate implied volatility from option price.

        Args:
            option_price: Market option price
            spot: Current underlying price
            strike: Option strike price
            time_to_expiry: Time to expiry in YEARS (e.g., 45/365)
            option_type: 'call' or 'put'

        Returns:
            IVResult with IV and metadata
        """
        self.stats['total_calls'] += 1

        # Validate inputs
        if option_price <= 0:
            return IVResult(0.20, False, 0, 0, 'fallback', 'LOW')
        if time_to_expiry <= 0:
            return IVResult(0.20, False, 0, 0, 'fallback', 'LOW')
        if spot <= 0 or strike <= 0:
            return IVResult(0.20, False, 0, 0, 'fallback', 'LOW')

        # Calculate intrinsic value
        if option_type.lower() == 'call':
            intrinsic = max(0, spot - strike)
        else:
            intrinsic = max(0, strike - spot)

        # If price is less than intrinsic, something's wrong
        if option_price < intrinsic * 0.99:  # Allow small tolerance
            return IVResult(0.20, False, 0, 0, 'fallback', 'LOW')

        # Try Newton-Raphson first
        result = self._newton_raphson(option_price, spot, strike, time_to_expiry, option_type)

        if result.converged:
            self.stats['newton_raphson_success'] += 1
            return result

        # Fallback to bisection method
        result = self._bisection(option_price, spot, strike, time_to_expiry, option_type)

        if result.converged:
            self.stats['bisection_fallback'] += 1
            return result

        # Last resort: estimate from VIX-like proxy
        self.stats['failed'] += 1
        estimated_iv = self._estimate_iv_from_moneyness(spot, strike, time_to_expiry)
        return IVResult(estimated_iv, False, 0, 0, 'fallback', 'LOW')

    def _newton_raphson(
        self,
        target_price: float,
        spot: float,
        strike: float,
        T: float,
        option_type: str
    ) -> IVResult:
        """
        Newton-Raphson iteration to find IV.

        Uses the formula: iv_new = iv - (BS_price - target) / vega
        """
        # Initial guess based on ATM approximation
        iv = self._initial_iv_guess(target_price, spot, strike, T)

        for i in range(self.max_iterations):
            # Calculate Black-Scholes price and vega at current IV
            price = self._black_scholes_price(spot, strike, T, iv, option_type)
            vega = self._vega(spot, strike, T, iv)

            # Check convergence
            price_diff = price - target_price
            if abs(price_diff) < self.tolerance:
                confidence = 'HIGH' if i < 10 else 'MEDIUM'
                return IVResult(iv, True, i + 1, price_diff, 'newton_raphson', confidence)

            # Avoid division by zero
            if abs(vega) < 1e-10:
                break

            # Newton-Raphson update
            iv_new = iv - price_diff / vega

            # Clamp IV to reasonable bounds
            iv_new = max(0.01, min(iv_new, 5.0))  # 1% to 500%

            # Check for convergence of IV itself
            if abs(iv_new - iv) < 1e-8:
                price = self._black_scholes_price(spot, strike, T, iv_new, option_type)
                return IVResult(iv_new, True, i + 1, price - target_price, 'newton_raphson', 'MEDIUM')

            iv = iv_new

        # Did not converge
        return IVResult(iv, False, self.max_iterations, price - target_price, 'newton_raphson', 'LOW')

    def _bisection(
        self,
        target_price: float,
        spot: float,
        strike: float,
        T: float,
        option_type: str
    ) -> IVResult:
        """
        Bisection method as fallback when Newton-Raphson fails.

        More robust but slower.
        """
        iv_low, iv_high = 0.01, 3.0

        for i in range(self.max_iterations):
            iv_mid = (iv_low + iv_high) / 2
            price = self._black_scholes_price(spot, strike, T, iv_mid, option_type)

            price_diff = price - target_price

            if abs(price_diff) < self.tolerance:
                return IVResult(iv_mid, True, i + 1, price_diff, 'bisection', 'MEDIUM')

            if price_diff > 0:
                iv_high = iv_mid
            else:
                iv_low = iv_mid

            # Check if bounds have converged
            if iv_high - iv_low < 1e-8:
                return IVResult(iv_mid, True, i + 1, price_diff, 'bisection', 'MEDIUM')

        return IVResult((iv_low + iv_high) / 2, False, self.max_iterations, 0, 'bisection', 'LOW')

    def _black_scholes_price(
        self,
        spot: float,
        strike: float,
        T: float,
        iv: float,
        option_type: str
    ) -> float:
        """Calculate Black-Scholes option price."""
        if T <= 0:
            if option_type.lower() == 'call':
                return max(0, spot - strike)
            else:
                return max(0, strike - spot)

        d1 = (math.log(spot / strike) + (self.risk_free_rate + 0.5 * iv**2) * T) / (iv * math.sqrt(T))
        d2 = d1 - iv * math.sqrt(T)

        if option_type.lower() == 'call':
            price = spot * norm.cdf(d1) - strike * math.exp(-self.risk_free_rate * T) * norm.cdf(d2)
        else:
            price = strike * math.exp(-self.risk_free_rate * T) * norm.cdf(-d2) - spot * norm.cdf(-d1)

        return max(0, price)

    def _vega(self, spot: float, strike: float, T: float, iv: float) -> float:
        """
        Calculate option vega (sensitivity to volatility).

        Vega = S * sqrt(T) * N'(d1)
        """
        if T <= 0 or iv <= 0:
            return 0.0

        d1 = (math.log(spot / strike) + (self.risk_free_rate + 0.5 * iv**2) * T) / (iv * math.sqrt(T))

        # N'(d1) = standard normal PDF
        n_prime_d1 = math.exp(-0.5 * d1**2) / math.sqrt(2 * math.pi)

        vega = spot * math.sqrt(T) * n_prime_d1

        return vega

    def _initial_iv_guess(
        self,
        option_price: float,
        spot: float,
        strike: float,
        T: float
    ) -> float:
        """
        Generate intelligent initial guess for IV.

        Uses Brenner-Subrahmanyam approximation for ATM options.
        """
        # For ATM options: IV ≈ price / (0.4 * S * sqrt(T))
        if T > 0:
            atm_approx = option_price / (0.4 * spot * math.sqrt(T))
            # Adjust for moneyness
            moneyness = abs(spot - strike) / spot
            iv_guess = atm_approx * (1 + moneyness)
            return max(0.05, min(iv_guess, 2.0))

        return 0.20  # Default 20%

    def _estimate_iv_from_moneyness(
        self,
        spot: float,
        strike: float,
        T: float
    ) -> float:
        """
        Fallback IV estimation when solver fails.

        Uses empirical relationship between moneyness and IV.
        """
        moneyness = abs(spot - strike) / spot

        # Base IV around 15-20%, increase for OTM
        base_iv = 0.18
        skew_adjustment = moneyness * 0.5  # IV increases for OTM
        time_adjustment = 1 + (0.5 * (1 - T))  # Higher for shorter DTE

        iv = base_iv + skew_adjustment * time_adjustment

        return max(0.10, min(iv, 1.0))

    def get_stats(self) -> Dict:
        """Get solver statistics."""
        total = self.stats['total_calls']
        if total == 0:
            return self.stats

        return {
            **self.stats,
            'newton_raphson_pct': self.stats['newton_raphson_success'] / total * 100,
            'bisection_pct': self.stats['bisection_fallback'] / total * 100,
            'failed_pct': self.stats['failed'] / total * 100,
            'success_rate': (self.stats['newton_raphson_success'] + self.stats['bisection_fallback']) / total * 100
        }


# Global solver instance
_solver = None


def get_iv_solver() -> IVSolver:
    """Get or create global IV solver instance."""
    global _solver
    if _solver is None:
        _solver = IVSolver()
    return _solver


def calculate_iv_from_price(
    option_price: float,
    spot: float,
    strike: float,
    dte: int,
    option_type: str = 'put',
    risk_free_rate: float = 0.05
) -> float:
    """
    Convenience function to calculate IV from option price.

    Args:
        option_price: Market option price
        spot: Current underlying price
        strike: Option strike price
        dte: Days to expiration
        option_type: 'call' or 'put'
        risk_free_rate: Annual risk-free rate

    Returns:
        Implied volatility as decimal (e.g., 0.25 = 25%)
    """
    solver = get_iv_solver()
    solver.risk_free_rate = risk_free_rate

    time_to_expiry = max(dte, 1) / 365.0

    result = solver.calculate_iv(option_price, spot, strike, time_to_expiry, option_type)

    return result.iv


def calculate_iv_with_details(
    option_price: float,
    spot: float,
    strike: float,
    dte: int,
    option_type: str = 'put'
) -> IVResult:
    """
    Calculate IV with full result details.

    Returns IVResult with convergence info, confidence, etc.
    """
    solver = get_iv_solver()
    time_to_expiry = max(dte, 1) / 365.0

    return solver.calculate_iv(option_price, spot, strike, time_to_expiry, option_type)


def get_historical_iv(
    trade_date: str,
    strike: float,
    expiration: str,
    underlying_price: float,
    option_price: float = None
) -> Tuple[float, str]:
    """
    Get historical IV for a specific option.

    First tries to get IV from Polygon, then calculates from price if available.

    Args:
        trade_date: Date in YYYY-MM-DD format
        strike: Option strike
        expiration: Expiration in YYYY-MM-DD format
        underlying_price: Spot price on trade date
        option_price: Historical option price (if known)

    Returns:
        Tuple of (iv, source) where source is 'POLYGON', 'CALCULATED', or 'ESTIMATED'
    """
    from datetime import datetime

    # Calculate DTE
    trade_dt = datetime.strptime(trade_date, '%Y-%m-%d')
    exp_dt = datetime.strptime(expiration, '%Y-%m-%d')
    dte = (exp_dt - trade_dt).days

    # Try Polygon first
    try:
        from data.polygon_data_fetcher import get_option_quote_historical

        # Build option ticker
        exp_str = expiration.replace('-', '')[2:]  # YYMMDD
        strike_str = f"{int(strike * 1000):08d}"
        ticker = f"O:SPX{exp_str}P{strike_str}"

        quote = get_option_quote_historical(ticker, trade_date)
        if quote and quote.get('implied_volatility'):
            return (quote['implied_volatility'], 'POLYGON')
    except Exception:
        pass

    # Calculate from price if available
    if option_price and option_price > 0:
        result = calculate_iv_with_details(
            option_price=option_price,
            spot=underlying_price,
            strike=strike,
            dte=dte,
            option_type='put'
        )

        source = 'CALCULATED' if result.converged else 'ESTIMATED'
        return (result.iv, source)

    # Fallback: estimate from VIX
    try:
        from data.polygon_data_fetcher import get_vix_for_date

        vix = get_vix_for_date(trade_date)
        if vix and vix > 0:
            # Convert VIX to decimal
            iv = vix / 100.0
            return (iv, 'VIX_PROXY')
    except Exception:
        pass

    # Last resort
    return (0.18, 'ESTIMATED')


# Test function
def test_iv_solver():
    """Test the IV solver with known values."""
    print("Testing IV Solver...")
    print("=" * 60)

    # Test case: SPX put option
    # SPX at 5800, strike 5750, 45 DTE, put price ~$50
    test_cases = [
        {'spot': 5800, 'strike': 5750, 'dte': 45, 'price': 50, 'type': 'put', 'expected_iv': 0.15},
        {'spot': 5800, 'strike': 5700, 'dte': 45, 'price': 35, 'type': 'put', 'expected_iv': 0.14},
        {'spot': 5800, 'strike': 5800, 'dte': 45, 'price': 85, 'type': 'put', 'expected_iv': 0.18},
        {'spot': 600, 'strike': 590, 'dte': 7, 'price': 2.50, 'type': 'put', 'expected_iv': 0.20},  # SPY
    ]

    solver = IVSolver()

    for i, tc in enumerate(test_cases):
        result = solver.calculate_iv(
            option_price=tc['price'],
            spot=tc['spot'],
            strike=tc['strike'],
            time_to_expiry=tc['dte'] / 365.0,
            option_type=tc['type']
        )

        # Verify by pricing back
        verify_price = solver._black_scholes_price(
            tc['spot'], tc['strike'], tc['dte'] / 365.0, result.iv, tc['type']
        )

        print(f"\nTest {i+1}: {tc['type'].upper()} @ {tc['strike']}")
        print(f"  Input Price:  ${tc['price']:.2f}")
        print(f"  Calculated IV: {result.iv * 100:.2f}%")
        print(f"  Verify Price:  ${verify_price:.2f}")
        print(f"  Price Error:   ${abs(verify_price - tc['price']):.4f}")
        print(f"  Converged:     {result.converged} ({result.method})")
        print(f"  Iterations:    {result.iterations}")
        print(f"  Confidence:    {result.confidence}")

    print("\n" + "=" * 60)
    print("Solver Stats:", solver.get_stats())


if __name__ == '__main__':
    test_iv_solver()
