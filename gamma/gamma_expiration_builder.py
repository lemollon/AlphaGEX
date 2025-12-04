"""
Gamma Expiration Builder - Constructs gamma data with expiration breakdown

This module builds the complete gamma_data structure needed for psychology trap detection,
including strike-by-strike gamma exposure separated by expiration date.

Usage:
    from gamma_expiration_builder import build_gamma_with_expirations

    gamma_data = build_gamma_with_expirations('SPY')
    # Returns gamma_data with 'expirations' key containing DTE-specific breakdown

Author: AlphaGEX Team
Date: 2025-11-14
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from scipy import stats

# Try to import yfinance (optional - Polygon.io is primary source)
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    print("ℹ️  yfinance not available - using Polygon.io for options data")

# Try to import Polygon fetcher as backup
try:
    from data.polygon_data_fetcher import polygon_fetcher
    POLYGON_AVAILABLE = True
except ImportError:
    POLYGON_AVAILABLE = False

# Import TradingVolatilityAPI for net GEX
try:
    from core_classes_and_engines import TradingVolatilityAPI
    TV_API_AVAILABLE = True
except ImportError:
    TV_API_AVAILABLE = False


class GammaExpirationBuilder:
    """Builds gamma data with expiration breakdown from options chains"""

    def __init__(self, symbol: str):
        self.symbol = symbol
        if YFINANCE_AVAILABLE:
            self.ticker = yf.Ticker(symbol)
        else:
            self.ticker = None  # Will use Polygon.io instead

    def calculate_gamma(self, spot: float, strike: float, iv: float, dte: int,
                       option_type: str = 'call', rf_rate: float = 0.045) -> float:
        """
        Calculate gamma using simplified Black-Scholes

        Args:
            spot: Current stock price
            strike: Strike price
            iv: Implied volatility (as decimal, e.g., 0.20 for 20%)
            dte: Days to expiration
            option_type: 'call' or 'put'
            rf_rate: Risk-free rate (default 4.5%)

        Returns:
            Gamma value (rate of delta change per $1 move)
        """
        try:
            if dte <= 0 or iv <= 0:
                return 0.0

            # Convert DTE to years
            T = dte / 365.0

            # Calculate d1
            d1 = (np.log(spot / strike) + (rf_rate + 0.5 * iv**2) * T) / (iv * np.sqrt(T))

            # Gamma (same for calls and puts)
            gamma = stats.norm.pdf(d1) / (spot * iv * np.sqrt(T))

            return gamma

        except Exception as e:
            print(f"   ⚠️  Error calculating gamma: {e}")
            return 0.0

    def fetch_options_chain(self, expiration: str) -> Dict:
        """
        Fetch options chain for a specific expiration

        Returns:
            {
                'calls': DataFrame,
                'puts': DataFrame
            }
        """
        if not YFINANCE_AVAILABLE or self.ticker is None:
            # yfinance not available - Polygon.io paid tier needed for options chains
            print(f"   ℹ️  yfinance unavailable - options chains require Polygon.io paid tier")
            return {'calls': None, 'puts': None}

        try:
            chain = self.ticker.option_chain(expiration)
            return {'calls': chain.calls, 'puts': chain.puts}
        except Exception as e:
            print(f"   ⚠️  Error fetching chain for {expiration}: {e}")
            return {'calls': None, 'puts': None}

    def build_expiration_data(self, current_price: float, max_dte: int = 60) -> List[Dict]:
        """
        Build gamma data for each expiration

        Args:
            current_price: Current stock price
            max_dte: Maximum days to expiration to include (default 60)

        Returns:
            List of expiration dictionaries with strike-level gamma
        """
        print(f"\n🔨 Building gamma expiration data for {self.symbol}")
        print(f"   Current price: ${current_price:.2f}")
        print(f"   Max DTE: {max_dte} days")

        if not YFINANCE_AVAILABLE or self.ticker is None:
            print(f"   ℹ️  yfinance unavailable - returning empty expiration data")
            print(f"   ℹ️  Psychology detector will use basic GEX analysis instead")
            return []

        try:
            # Get all available expirations
            expirations = self.ticker.options
            if not expirations:
                print(f"   ⚠️  No options data available")
                return []

            print(f"   Found {len(expirations)} expirations")

            # Filter to next max_dte days
            cutoff_date = (datetime.now() + timedelta(days=max_dte)).date()
            relevant_expirations = [
                exp for exp in expirations
                if datetime.strptime(exp, '%Y-%m-%d').date() <= cutoff_date
            ]

            print(f"   Processing {len(relevant_expirations)} near-term expirations")

            expiration_data = []

            for expiration in relevant_expirations:
                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                dte = (exp_date - datetime.now().date()).days

                if dte < 0:
                    continue

                print(f"   • {expiration} ({dte} DTE)...", end='')

                # Fetch chain
                chain = self.fetch_options_chain(expiration)
                if chain['calls'] is None or chain['puts'] is None:
                    print(" ❌ No data")
                    continue

                calls = chain['calls']
                puts = chain['puts']

                # Determine expiration type
                if dte == 0:
                    exp_type = '0dte'
                elif exp_date.day > 24:  # Monthly OPEX (usually 3rd Friday = days 15-21, but can be later)
                    exp_type = 'monthly'
                else:
                    exp_type = 'weekly'

                # Build strike-level data
                strikes = []

                # Process calls
                call_strikes = {}
                for _, row in calls.iterrows():
                    strike = float(row['strike'])
                    oi = int(row.get('openInterest', 0))
                    iv = float(row.get('impliedVolatility', 0.20))
                    volume = int(row.get('volume', 0))

                    if oi > 0:  # Only include strikes with OI
                        gamma = self.calculate_gamma(current_price, strike, iv, dte, 'call')
                        gamma_exposure = gamma * oi * 100 * current_price  # Gamma exposure in $

                        call_strikes[strike] = {
                            'strike': strike,
                            'call_gamma': gamma_exposure,
                            'call_oi': oi,
                            'call_volume': volume,
                            'call_iv': iv,
                            'put_gamma': 0,
                            'put_oi': 0,
                            'put_volume': 0,
                            'put_iv': 0,
                            'distance_pct': (strike - current_price) / current_price * 100
                        }

                # Process puts and merge
                for _, row in puts.iterrows():
                    strike = float(row['strike'])
                    oi = int(row.get('openInterest', 0))
                    iv = float(row.get('impliedVolatility', 0.20))
                    volume = int(row.get('volume', 0))

                    if oi > 0:
                        gamma = self.calculate_gamma(current_price, strike, iv, dte, 'put')
                        gamma_exposure = gamma * oi * 100 * current_price

                        if strike in call_strikes:
                            # Update existing strike
                            call_strikes[strike]['put_gamma'] = gamma_exposure
                            call_strikes[strike]['put_oi'] = oi
                            call_strikes[strike]['put_volume'] = volume
                            call_strikes[strike]['put_iv'] = iv
                        else:
                            # New strike (put only)
                            call_strikes[strike] = {
                                'strike': strike,
                                'call_gamma': 0,
                                'call_oi': 0,
                                'call_volume': 0,
                                'call_iv': 0,
                                'put_gamma': gamma_exposure,
                                'put_oi': oi,
                                'put_volume': volume,
                                'put_iv': iv,
                                'distance_pct': (strike - current_price) / current_price * 100
                            }

                # Convert to list and calculate totals
                strikes = list(call_strikes.values())
                total_call_gamma = sum(s['call_gamma'] for s in strikes)
                total_put_gamma = sum(s['put_gamma'] for s in strikes)
                net_gamma_this_exp = total_call_gamma - total_put_gamma

                print(f" ✅ {len(strikes)} strikes, Net Γ: ${net_gamma_this_exp/1e9:.2f}B")

                expiration_data.append({
                    'expiration_date': exp_date,
                    'dte': dte,
                    'expiration_type': exp_type,
                    'call_strikes': [
                        {
                            'strike': s['strike'],
                            'gamma_exposure': s['call_gamma'],
                            'open_interest': s['call_oi'],
                            'volume': s['call_volume'],
                            'implied_volatility': s['call_iv']
                        }
                        for s in strikes if s['call_oi'] > 0
                    ],
                    'put_strikes': [
                        {
                            'strike': s['strike'],
                            'gamma_exposure': s['put_gamma'],
                            'open_interest': s['put_oi'],
                            'volume': s['put_volume'],
                            'implied_volatility': s['put_iv']
                        }
                        for s in strikes if s['put_oi'] > 0
                    ],
                    'total_call_gamma': total_call_gamma,
                    'total_put_gamma': total_put_gamma,
                    'net_gamma': net_gamma_this_exp
                })

            print(f"\n   ✅ Built expiration data for {len(expiration_data)} expirations")
            return expiration_data

        except Exception as e:
            print(f"\n   ❌ Error building expiration data: {e}")
            import traceback
            traceback.print_exc()
            return []


def build_gamma_with_expirations(symbol: str, use_tv_api: bool = True) -> Dict:
    """
    Build complete gamma_data structure with expiration breakdown

    Args:
        symbol: Stock symbol (e.g., 'SPY')
        use_tv_api: Use Trading Volatility API for net GEX (default True)

    Returns:
        {
            'symbol': str,
            'spot_price': float,
            'net_gex': float,
            'flip_point': float,
            'call_wall': float,
            'put_wall': float,
            'expirations': List[Dict],  # <-- The key addition
            'net_gamma_by_expiration': Dict[str, float]
        }
    """
    print(f"\n{'='*80}")
    print(f"Building Complete Gamma Data for {symbol}")
    print(f"{'='*80}")

    result = {
        'symbol': symbol,
        'spot_price': 0,
        'net_gex': 0,
        'flip_point': 0,
        'call_wall': None,
        'put_wall': None,
        'expirations': [],
        'net_gamma_by_expiration': {}
    }

    try:
        # Step 1: Get aggregated GEX from Trading Volatility API (if available)
        if use_tv_api and TV_API_AVAILABLE:
            print("\n1️⃣ Fetching aggregated GEX from Trading Volatility API...")
            tv_api = TradingVolatilityAPI()
            tv_data = tv_api.get_net_gamma(symbol)

            if 'error' not in tv_data:
                result['net_gex'] = tv_data.get('net_gex', 0)
                result['flip_point'] = tv_data.get('flip_point', 0)
                result['spot_price'] = tv_data.get('spot_price', 0)
                result['call_wall'] = tv_data.get('call_wall')
                result['put_wall'] = tv_data.get('put_wall')
                print(f"   ✅ Net GEX: ${result['net_gex']/1e9:.2f}B")
                print(f"   ✅ Flip Point: ${result['flip_point']:.2f}")
            else:
                print(f"   ⚠️  TV API error: {tv_data['error']}")
                use_tv_api = False

        # Step 2: Get current price (if not from TV API)
        if result['spot_price'] == 0:
            print("\n2️⃣ Fetching current price...")
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1d')
            if not hist.empty:
                result['spot_price'] = float(hist['Close'].iloc[-1])
                print(f"   ✅ Current price: ${result['spot_price']:.2f}")

        # Step 3: Build expiration breakdown
        print("\n3️⃣ Building expiration breakdown from options chains...")
        builder = GammaExpirationBuilder(symbol)
        expiration_data = builder.build_expiration_data(result['spot_price'])

        result['expirations'] = expiration_data

        # Calculate net gamma by expiration
        for exp in expiration_data:
            exp_date_str = exp['expiration_date'].isoformat()
            result['net_gamma_by_expiration'][exp_date_str] = exp['net_gamma']

        # Summary
        total_expirations = len(expiration_data)
        total_net_gamma_from_chains = sum(exp['net_gamma'] for exp in expiration_data)

        print(f"\n{'='*80}")
        print(f"✅ COMPLETE")
        print(f"{'='*80}")
        print(f"   Symbol: {symbol}")
        print(f"   Spot Price: ${result['spot_price']:.2f}")
        print(f"   Net GEX (TV API): ${result['net_gex']/1e9:.2f}B")
        print(f"   Net Gamma (Chains): ${total_net_gamma_from_chains/1e9:.2f}B")
        print(f"   Flip Point: ${result['flip_point']:.2f}")
        print(f"   Expirations: {total_expirations}")
        print(f"{'='*80}\n")

        return result

    except Exception as e:
        print(f"\n❌ Error building gamma data: {e}")
        import traceback
        traceback.print_exc()
        return result


# Convenience function for testing
if __name__ == "__main__":
    import sys

    symbol = sys.argv[1] if len(sys.argv) > 1 else 'SPY'

    print(f"\nTesting Gamma Expiration Builder for {symbol}\n")

    gamma_data = build_gamma_with_expirations(symbol)

    print("\nExpiration Summary:")
    print(f"{'Date':<12} {'DTE':>4} {'Type':<10} {'Net Gamma':>15}")
    print("-" * 50)
    for exp in gamma_data['expirations'][:10]:
        print(f"{exp['expiration_date']} {exp['dte']:>4} {exp['expiration_type']:<10} ${exp['net_gamma']/1e9:>12.2f}B")

    print(f"\nTotal expirations: {len(gamma_data['expirations'])}")
    print(f"Net GEX: ${gamma_data['net_gex']/1e9:.2f}B")
