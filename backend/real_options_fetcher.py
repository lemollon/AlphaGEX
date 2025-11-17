"""
Real Options Chain Data Fetcher
Fetches ACTUAL bid/ask spreads, Greeks, and IV from Yahoo Finance API
This replaces ESTIMATED prices with REAL market data
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import numpy as np
from scipy.stats import norm
import math

class RealOptionsChainFetcher:
    """
    Fetches real options chain data from Yahoo Finance API
    Returns actual bid/ask, volume, open interest, IV, and Greeks
    """

    def __init__(self):
        self.base_url = "https://query2.finance.yahoo.com/v7/finance/options"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://finance.yahoo.com/',
            'Origin': 'https://finance.yahoo.com'
        })
        # Add a cookie to appear more legitimate
        self.session.cookies.set('A1', 'valid', domain='.yahoo.com')
        self.session.cookies.set('A3', 'valid', domain='.yahoo.com')

    def get_options_chain(self, symbol: str, days_to_expiry: int = 7) -> Dict:
        """
        Fetch real options chain from Yahoo Finance

        Returns:
            {
                'calls': [...],
                'puts': [...],
                'spot_price': float,
                'expiration_date': str
            }
        """
        try:
            # Get available expiration dates
            url = f"{self.base_url}/{symbol}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if 'optionChain' not in data or 'result' not in data['optionChain']:
                return None

            result = data['optionChain']['result'][0]
            spot_price = result['quote']['regularMarketPrice']

            # Find expiration closest to target days
            expirations = result.get('expirationDates', [])
            if not expirations:
                return None

            target_date = int((datetime.now() + timedelta(days=days_to_expiry)).timestamp())
            closest_exp = min(expirations, key=lambda x: abs(x - target_date))

            # Fetch options for that expiration
            exp_url = f"{self.base_url}/{symbol}?date={closest_exp}"
            exp_response = self.session.get(exp_url, timeout=10)
            exp_response.raise_for_status()
            exp_data = exp_response.json()

            exp_result = exp_data['optionChain']['result'][0]
            options = exp_result.get('options', [{}])[0]

            calls = options.get('calls', [])
            puts = options.get('puts', [])

            expiration_date = datetime.fromtimestamp(closest_exp).strftime('%Y-%m-%d')

            return {
                'calls': calls,
                'puts': puts,
                'spot_price': spot_price,
                'expiration_date': expiration_date,
                'days_to_expiry': (datetime.fromtimestamp(closest_exp) - datetime.now()).days
            }

        except Exception as e:
            print(f"Error fetching options chain: {e}")
            return None

    def get_atm_option(self, symbol: str, option_type: str = 'call', days_to_expiry: int = 3) -> Optional[Dict]:
        """
        Get the ATM (at-the-money) option with REAL market data

        Returns:
            {
                'strike': float,
                'bid': float,
                'ask': float,
                'last': float,
                'mid': float,
                'volume': int,
                'open_interest': int,
                'implied_volatility': float,
                'delta': float,
                'gamma': float,
                'theta': float,
                'vega': float,
                'spot_price': float
            }
        """
        chain = self.get_options_chain(symbol, days_to_expiry)
        if not chain:
            return None

        spot_price = chain['spot_price']
        options = chain['calls'] if option_type == 'call' else chain['puts']

        if not options:
            return None

        # Find ATM option (closest to spot)
        atm_option = min(options, key=lambda x: abs(x['strike'] - spot_price))

        bid = atm_option.get('bid', 0)
        ask = atm_option.get('ask', 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else atm_option.get('lastPrice', 0)

        return {
            'strike': atm_option['strike'],
            'bid': bid,
            'ask': ask,
            'last': atm_option.get('lastPrice', 0),
            'mid': mid,
            'volume': atm_option.get('volume', 0),
            'open_interest': atm_option.get('openInterest', 0),
            'implied_volatility': atm_option.get('impliedVolatility', 0),
            'delta': atm_option.get('delta'),
            'gamma': atm_option.get('gamma'),
            'theta': atm_option.get('theta'),
            'vega': atm_option.get('vega'),
            'spot_price': spot_price,
            'days_to_expiry': chain['days_to_expiry'],
            'expiration_date': chain['expiration_date']
        }

    def get_option_by_strike(self, symbol: str, strike: float, option_type: str = 'call',
                            days_to_expiry: int = 3) -> Optional[Dict]:
        """
        Get specific option by strike with REAL market data
        """
        chain = self.get_options_chain(symbol, days_to_expiry)
        if not chain:
            return None

        options = chain['calls'] if option_type == 'call' else chain['puts']

        # Find option closest to requested strike
        option = min(options, key=lambda x: abs(x['strike'] - strike))

        bid = option.get('bid', 0)
        ask = option.get('ask', 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else option.get('lastPrice', 0)

        return {
            'strike': option['strike'],
            'bid': bid,
            'ask': ask,
            'last': option.get('lastPrice', 0),
            'mid': mid,
            'volume': option.get('volume', 0),
            'open_interest': option.get('openInterest', 0),
            'implied_volatility': option.get('impliedVolatility', 0),
            'delta': option.get('delta'),
            'gamma': option.get('gamma'),
            'theta': option.get('theta'),
            'vega': option.get('vega'),
            'spot_price': chain['spot_price'],
            'days_to_expiry': chain['days_to_expiry'],
            'expiration_date': chain['expiration_date']
        }

    def get_options_by_delta(self, symbol: str, target_delta: float, option_type: str = 'call',
                            days_to_expiry: int = 3) -> Optional[Dict]:
        """
        Find option closest to target delta (e.g., 0.40 for slightly OTM calls)
        """
        chain = self.get_options_chain(symbol, days_to_expiry)
        if not chain:
            return None

        options = chain['calls'] if option_type == 'call' else chain['puts']

        # Filter options with delta data
        options_with_delta = [opt for opt in options if opt.get('delta') is not None]

        if not options_with_delta:
            # Fallback: estimate delta and find closest
            spot_price = chain['spot_price']
            target_strike = self._estimate_strike_from_delta(spot_price, target_delta, option_type)
            return self.get_option_by_strike(symbol, target_strike, option_type, days_to_expiry)

        # Find option closest to target delta
        option = min(options_with_delta, key=lambda x: abs(abs(x['delta']) - abs(target_delta)))

        bid = option.get('bid', 0)
        ask = option.get('ask', 0)
        mid = (bid + ask) / 2 if bid > 0 and ask > 0 else option.get('lastPrice', 0)

        return {
            'strike': option['strike'],
            'bid': bid,
            'ask': ask,
            'last': option.get('lastPrice', 0),
            'mid': mid,
            'volume': option.get('volume', 0),
            'open_interest': option.get('openInterest', 0),
            'implied_volatility': option.get('impliedVolatility', 0),
            'delta': option.get('delta'),
            'gamma': option.get('gamma'),
            'theta': option.get('theta'),
            'vega': option.get('vega'),
            'spot_price': chain['spot_price'],
            'days_to_expiry': chain['days_to_expiry'],
            'expiration_date': chain['expiration_date']
        }

    def _estimate_strike_from_delta(self, spot_price: float, delta: float, option_type: str) -> float:
        """
        Estimate strike price from delta (simplified)
        For calls: ATM delta ≈ 0.50, decreases as strike increases
        """
        if option_type == 'call':
            # Rough approximation: delta 0.40 ≈ 1-2% OTM
            if delta >= 0.50:
                return spot_price * (1 - (0.50 - delta) * 0.05)
            else:
                return spot_price * (1 + (0.50 - delta) * 0.05)
        else:  # put
            if abs(delta) >= 0.50:
                return spot_price * (1 + (0.50 - abs(delta)) * 0.05)
            else:
                return spot_price * (1 - (0.50 - abs(delta)) * 0.05)

    def calculate_greeks(self, S: float, K: float, T: float, r: float, sigma: float,
                        option_type: str = 'call') -> Dict[str, float]:
        """
        Calculate Black-Scholes Greeks if not provided by API

        S: spot price
        K: strike price
        T: time to expiry (years)
        r: risk-free rate (e.g., 0.05 for 5%)
        sigma: implied volatility (e.g., 0.20 for 20%)
        """
        if T <= 0:
            T = 0.001

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == 'call':
            delta = norm.cdf(d1)
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:  # put
            delta = -norm.cdf(-d1)
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T) / 100  # Per 1% change in IV
        theta = (- (S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * norm.cdf(d2 if option_type == 'call' else -d2)) / 365

        return {
            'price': price,
            'delta': delta,
            'gamma': gamma,
            'theta': theta,
            'vega': vega
        }


# Singleton instance
_real_options_fetcher = None

def get_real_options_fetcher() -> RealOptionsChainFetcher:
    """Get or create singleton instance"""
    global _real_options_fetcher
    if _real_options_fetcher is None:
        _real_options_fetcher = RealOptionsChainFetcher()
    return _real_options_fetcher


# Quick test
if __name__ == "__main__":
    fetcher = RealOptionsChainFetcher()

    print("Testing Real Options Chain Fetcher...")
    print("\n1. Fetching SPY ATM call option (3 DTE):")
    atm_call = fetcher.get_atm_option('SPY', 'call', 3)
    if atm_call:
        print(f"   Strike: ${atm_call['strike']}")
        print(f"   Bid/Ask: ${atm_call['bid']} / ${atm_call['ask']}")
        print(f"   Mid: ${atm_call['mid']}")
        print(f"   IV: {atm_call['implied_volatility']*100:.1f}%")
        print(f"   Delta: {atm_call['delta']:.3f}")
        print(f"   Volume: {atm_call['volume']:,}")
        print(f"   OI: {atm_call['open_interest']:,}")
    else:
        print("   Failed to fetch")

    print("\n2. Fetching 0.40 delta call (for TRAPPED state):")
    delta_call = fetcher.get_options_by_delta('SPY', 0.40, 'call', 3)
    if delta_call:
        print(f"   Strike: ${delta_call['strike']}")
        print(f"   Bid/Ask: ${delta_call['bid']} / ${delta_call['ask']}")
        print(f"   Delta: {delta_call['delta']:.3f}")
    else:
        print("   Failed to fetch")
