"""
Enhanced Probability Calculator with Better Price Estimates
Uses more sophisticated Black-Scholes calculations for realistic option pricing
"""

import math
from scipy.stats import norm
from typing import Dict, Tuple, Optional
from datetime import datetime
import numpy as np

class EnhancedProbabilityCalculator:
    """
    Calculates more accurate option prices using:
    - Black-Scholes-Merton model
    - Volatility smile adjustments
    - Bid/ask spread estimation
    - Market conditions (VIX-based IV adjustments)
    """

    def __init__(self):
        # VIX to ATM IV conversion (rough approximation)
        self.vix_to_iv_multiplier = 0.8  # VIX 20 ≈ 16% ATM IV for SPY

    def estimate_atm_iv(self, vix: float, days_to_expiry: int) -> float:
        """
        Estimate ATM implied volatility from VIX

        VIX represents 30-day IV, adjust for DTE
        """
        # Base IV from VIX
        base_iv = (vix / 100) * self.vix_to_iv_multiplier

        # Term structure adjustment (shorter term = higher IV usually)
        if days_to_expiry <= 5:
            term_adj = 1.15  # 0DTE/weekly tend to have higher IV
        elif days_to_expiry <= 14:
            term_adj = 1.05
        else:
            term_adj = 1.0

        return base_iv * term_adj

    def calculate_option_price(self,
                              spot_price: float,
                              strike: float,
                              days_to_expiry: int,
                              implied_vol: float,
                              option_type: str = 'call',
                              risk_free_rate: float = 0.045) -> Dict:
        """
        Calculate option price using Black-Scholes with realistic adjustments

        Returns:
            {
                'theoretical_price': float,
                'bid': float (theoretical - spread/2),
                'ask': float (theoretical + spread/2),
                'mid': float (theoretical),
                'delta': float,
                'gamma': float,
                'theta': float,
                'vega': float,
                'estimated_spread': float
            }
        """
        T = days_to_expiry / 365.0
        if T <= 0:
            T = 1/365  # Minimum 1 day

        sigma = implied_vol
        r = risk_free_rate
        S = spot_price
        K = strike

        # Black-Scholes calculation
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type.lower() == 'call':
            theoretical_price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
        else:  # put
            theoretical_price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            delta = -norm.cdf(-d1)

        # Greeks
        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T) / 100  # Per 1% change in IV
        theta_call = (-(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
                     - r * K * math.exp(-r * T) * norm.cdf(d2))
        theta_put = (-(S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
                    + r * K * math.exp(-r * T) * norm.cdf(-d2))
        theta = (theta_call if option_type.lower() == 'call' else theta_put) / 365

        # Estimate bid/ask spread based on liquidity factors
        # SPY has tight spreads, smaller names wider
        # Further OTM = wider spreads
        moneyness = abs(S - K) / S

        if moneyness < 0.01:  # ATM
            spread_pct = 0.015  # 1.5% spread (e.g., $0.05 on $3.00 option)
        elif moneyness < 0.02:  # Slightly OTM/ITM
            spread_pct = 0.02  # 2%
        elif moneyness < 0.05:  # More OTM/ITM
            spread_pct = 0.03  # 3%
        else:  # Deep OTM/ITM
            spread_pct = 0.05  # 5%

        # Minimum spread of $0.05
        estimated_spread = max(0.05, theoretical_price * spread_pct)

        # Adjust for very low priced options
        if theoretical_price < 0.50:
            estimated_spread = 0.05  # Penny increment minimum
        elif theoretical_price < 2.00:
            estimated_spread = 0.10  # Nickel-wide for cheap options

        bid = max(0.01, theoretical_price - estimated_spread / 2)
        ask = theoretical_price + estimated_spread / 2
        mid = theoretical_price

        return {
            'theoretical_price': round(theoretical_price, 2),
            'bid': round(bid, 2),
            'ask': round(ask, 2),
            'mid': round(mid, 2),
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'theta': round(theta, 4),
            'vega': round(vega, 4),
            'estimated_spread': round(estimated_spread, 2),
            'estimated_spread_pct': round(spread_pct * 100, 1),
            'iv_used': round(implied_vol * 100, 1),
            'dte': days_to_expiry
        }

    def calculate_option_for_setup(self,
                                   spot_price: float,
                                   strike_distance_pct: float,
                                   days_to_expiry: int,
                                   vix: float,
                                   option_type: str = 'call') -> Dict:
        """
        Calculate option price for a specific trade setup

        Args:
            spot_price: Current stock price
            strike_distance_pct: Distance from spot (0 = ATM, 0.01 = 1% OTM)
            days_to_expiry: Days to expiration
            vix: VIX level for IV estimation
            option_type: 'call' or 'put'
        """
        # Calculate strike
        if option_type.lower() == 'call':
            strike = spot_price * (1 + strike_distance_pct)
        else:
            strike = spot_price * (1 - strike_distance_pct)

        strike = round(strike)  # Round to nearest dollar

        # Estimate IV from VIX
        atm_iv = self.estimate_atm_iv(vix, days_to_expiry)

        # Volatility smile/skew adjustment
        # OTM options typically have higher IV (especially puts)
        moneyness = abs(strike - spot_price) / spot_price

        if option_type.lower() == 'put' and strike < spot_price:
            # OTM puts have skew (higher IV)
            iv_adjustment = 1.0 + (moneyness * 2.0)  # Add up to 2x IV for deep OTM puts
        elif option_type.lower() == 'call' and strike > spot_price:
            # OTM calls have some skew but less
            iv_adjustment = 1.0 + (moneyness * 0.5)
        else:
            # ITM options have lower IV
            iv_adjustment = 1.0 - (moneyness * 0.3)

        implied_vol = atm_iv * iv_adjustment

        # Calculate option price and Greeks
        result = self.calculate_option_price(
            spot_price=spot_price,
            strike=strike,
            days_to_expiry=days_to_expiry,
            implied_vol=implied_vol,
            option_type=option_type
        )

        result['strike'] = strike
        result['strike_distance_pct'] = round(strike_distance_pct * 100, 2)

        return result

    def calculate_profit_targets(self, entry_price: float, win_rate: float,
                               avg_win: float, avg_loss: float) -> Dict:
        """
        Calculate realistic profit targets and stop losses

        Returns:
            {
                'entry_bid': float,  # Conservative entry
                'entry_ask': float,  # Aggressive entry
                'profit_target': float,
                'stop_loss': float,
                'risk_reward_ratio': float,
                'expected_value': float
            }
        """
        # Conservative entry at bid (better fill, lower entry)
        entry_bid = entry_price * 0.97  # Assume can get filled near bid

        # Aggressive entry at ask (immediate fill, higher entry)
        entry_ask = entry_price * 1.03

        # Use mid as base
        entry_mid = entry_price

        # Profit target based on avg win
        profit_target = entry_mid * (1 + avg_win)

        # Stop loss based on avg loss
        stop_loss = entry_mid * (1 + avg_loss)  # avg_loss is negative

        # Risk/Reward
        risk = entry_mid - stop_loss
        reward = profit_target - entry_mid
        rr_ratio = reward / risk if risk > 0 else 0

        # Expected Value
        ev = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)

        return {
            'entry_bid': round(entry_bid, 2),
            'entry_ask': round(entry_ask, 2),
            'entry_mid': round(entry_mid, 2),
            'profit_target': round(profit_target, 2),
            'stop_loss': round(stop_loss, 2),
            'risk_reward_ratio': round(rr_ratio, 2),
            'expected_value_pct': round(ev * 100, 1),
            'max_risk_per_contract': round((entry_mid - stop_loss) * 100, 2),  # In dollars
            'max_profit_per_contract': round((profit_target - entry_mid) * 100, 2)
        }


# Quick test
if __name__ == "__main__":
    calc = EnhancedProbabilityCalculator()

    print("=== ENHANCED PROBABILITY CALCULATOR TEST ===\n")

    # Test 1: SPY ATM call with VIX = 18
    print("1. SPY ATM Call (VIX 18, 3 DTE):")
    result = calc.calculate_option_for_setup(
        spot_price=585.0,
        strike_distance_pct=0.0,  # ATM
        days_to_expiry=3,
        vix=18,
        option_type='call'
    )
    print(f"   Strike: ${result['strike']}")
    print(f"   Theoretical: ${result['theoretical_price']}")
    print(f"   Bid/Ask: ${result['bid']} / ${result['ask']}")
    print(f"   Spread: ${result['estimated_spread']} ({result['estimated_spread_pct']}%)")
    print(f"   Delta: {result['delta']:.3f}")
    print(f"   IV Used: {result['iv_used']:.1f}%")

    # Test 2: Slightly OTM call (0.4 delta target)
    print("\n2. SPY 0.4 Delta Call (1% OTM, VIX 20, 3 DTE):")
    result2 = calc.calculate_option_for_setup(
        spot_price=585.0,
        strike_distance_pct=0.01,  # 1% OTM
        days_to_expiry=3,
        vix=20,
        option_type='call'
    )
    print(f"   Strike: ${result2['strike']}")
    print(f"   Bid/Ask: ${result2['bid']} / ${result2['ask']}")
    print(f"   Delta: {result2['delta']:.3f}")

    # Test 3: Profit targets for PANICKING state (90% win rate, 60% avg win)
    print("\n3. Profit Targets for PANICKING State:")
    targets = calc.calculate_profit_targets(
        entry_price=3.20,
        win_rate=0.90,
        avg_win=0.60,
        avg_loss=-0.30
    )
    print(f"   Entry Range: ${targets['entry_bid']} - ${targets['entry_ask']}")
    print(f"   Profit Target: ${targets['profit_target']}")
    print(f"   Stop Loss: ${targets['stop_loss']}")
    print(f"   Risk/Reward: {targets['risk_reward_ratio']:.2f}:1")
    print(f"   Expected Value: {targets['expected_value_pct']}%")
    print(f"   Max Risk: ${targets['max_risk_per_contract']}")
    print(f"   Max Profit: ${targets['max_profit_per_contract']}")
