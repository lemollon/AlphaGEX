"""
GEX (Gamma Exposure) Calculator from Options Chain Data

Calculates Gamma Exposure metrics when TradingVolatilityAPI is unavailable.
Uses Tradier options chain data with Greeks to compute:
- Net GEX (billions)
- Call Wall (highest call gamma strike)
- Put Wall (highest put gamma strike)
- Gamma Flip Point (where net gamma crosses zero)
- Call/Put GEX breakdown

GEX Formula:
    GEX_strike = gamma * open_interest * 100 * spot^2 / 1e9

For Market Makers (assuming they're short options):
    - Short Calls = Long Gamma (positive GEX)
    - Short Puts = Short Gamma (negative GEX when delta-hedging)
    Net GEX = Call GEX - |Put GEX|
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GEXResult:
    """GEX calculation result"""
    symbol: str
    spot_price: float
    net_gex: float  # In dollars (not billions)
    call_gex: float
    put_gex: float
    call_wall: float  # Strike with highest call gamma
    put_wall: float   # Strike with highest put gamma
    gamma_flip: float  # Zero-crossing point
    flip_point: float  # Alias for gamma_flip
    max_pain: float   # Strike with max OI
    data_source: str
    timestamp: datetime
    strikes_data: List[Dict] = None  # Detailed per-strike data


def calculate_gex_from_chain(
    symbol: str,
    spot_price: float,
    options_data: List[Dict],
    contract_multiplier: int = 100
) -> GEXResult:
    """
    Calculate GEX from options chain data.

    Args:
        symbol: Underlying symbol
        spot_price: Current spot price
        options_data: List of option contracts with gamma, open_interest, strike, option_type
        contract_multiplier: Usually 100 for equity options

    Returns:
        GEXResult with all GEX metrics
    """
    if not options_data or spot_price <= 0:
        return GEXResult(
            symbol=symbol,
            spot_price=spot_price,
            net_gex=0,
            call_gex=0,
            put_gex=0,
            call_wall=spot_price,
            put_wall=spot_price,
            gamma_flip=spot_price,
            flip_point=spot_price,
            max_pain=spot_price,
            data_source='empty',
            timestamp=datetime.now()
        )

    # Group by strike
    strikes_gex = {}
    total_call_gex = 0
    total_put_gex = 0
    max_call_gex = 0
    max_put_gex = 0
    call_wall_strike = spot_price
    put_wall_strike = spot_price

    # For max pain calculation
    call_oi_by_strike = {}
    put_oi_by_strike = {}

    for contract in options_data:
        strike = float(contract.get('strike', 0))
        gamma = float(contract.get('gamma', 0) or 0)
        open_interest = int(contract.get('open_interest', 0) or 0)
        option_type = contract.get('option_type', '').lower()

        if strike <= 0 or gamma <= 0 or open_interest <= 0:
            continue

        # GEX = gamma * OI * 100 * spot^2
        # Note: gamma from APIs is usually per-share, so multiply by 100 for per-contract
        gex_value = gamma * open_interest * contract_multiplier * (spot_price ** 2)

        if strike not in strikes_gex:
            strikes_gex[strike] = {'call_gex': 0, 'put_gex': 0, 'net_gex': 0}

        if option_type == 'call':
            # Short calls = Long gamma for MM (positive GEX)
            strikes_gex[strike]['call_gex'] += gex_value
            total_call_gex += gex_value
            call_oi_by_strike[strike] = call_oi_by_strike.get(strike, 0) + open_interest

            if gex_value > max_call_gex:
                max_call_gex = gex_value
                call_wall_strike = strike

        elif option_type == 'put':
            # Short puts = Short gamma for MM when hedging (negative GEX)
            strikes_gex[strike]['put_gex'] -= gex_value  # Negative for puts
            total_put_gex += gex_value  # Store absolute value
            put_oi_by_strike[strike] = put_oi_by_strike.get(strike, 0) + open_interest

            if gex_value > max_put_gex:
                max_put_gex = gex_value
                put_wall_strike = strike

    # Calculate net GEX per strike and find flip point
    for strike in strikes_gex:
        strikes_gex[strike]['net_gex'] = strikes_gex[strike]['call_gex'] + strikes_gex[strike]['put_gex']

    # Find gamma flip (zero-crossing point)
    gamma_flip = find_gamma_flip(strikes_gex, spot_price)

    # Calculate max pain
    max_pain = calculate_max_pain(call_oi_by_strike, put_oi_by_strike, spot_price)

    # Net GEX is call GEX minus absolute put GEX
    net_gex = total_call_gex - total_put_gex

    # Prepare strikes data for detailed view
    strikes_data = []
    for strike in sorted(strikes_gex.keys()):
        strikes_data.append({
            'strike': strike,
            'call_gex': strikes_gex[strike]['call_gex'],
            'put_gex': strikes_gex[strike]['put_gex'],
            'net_gex': strikes_gex[strike]['net_gex']
        })

    return GEXResult(
        symbol=symbol,
        spot_price=spot_price,
        net_gex=net_gex,
        call_gex=total_call_gex,
        put_gex=-total_put_gex,  # Return as negative
        call_wall=call_wall_strike,
        put_wall=put_wall_strike,
        gamma_flip=gamma_flip,
        flip_point=gamma_flip,
        max_pain=max_pain,
        data_source='tradier_calculated',
        timestamp=datetime.now(),
        strikes_data=strikes_data
    )


def find_gamma_flip(strikes_gex: Dict, spot_price: float) -> float:
    """
    Find the strike where net gamma crosses from negative to positive.
    This is where market maker hedging behavior changes.
    """
    if not strikes_gex:
        return spot_price

    sorted_strikes = sorted(strikes_gex.keys())

    # Find zero-crossing point
    prev_strike = None
    prev_net = None

    for strike in sorted_strikes:
        net = strikes_gex[strike]['net_gex']

        if prev_net is not None:
            # Check for sign change (crossing zero)
            if prev_net < 0 and net >= 0:
                # Linear interpolation to find exact crossing point
                if net != prev_net:
                    ratio = abs(prev_net) / (abs(prev_net) + abs(net))
                    flip_point = prev_strike + ratio * (strike - prev_strike)
                    return flip_point
                return strike
            elif prev_net >= 0 and net < 0:
                # Going from positive to negative
                if net != prev_net:
                    ratio = abs(prev_net) / (abs(prev_net) + abs(net))
                    flip_point = prev_strike + ratio * (strike - prev_strike)
                    return flip_point
                return strike

        prev_strike = strike
        prev_net = net

    # If no zero-crossing found, return strike closest to spot with lowest absolute net GEX
    closest_strike = min(sorted_strikes, key=lambda s: abs(s - spot_price))
    return closest_strike


def calculate_max_pain(
    call_oi: Dict[float, int],
    put_oi: Dict[float, int],
    spot_price: float
) -> float:
    """
    Calculate max pain - the strike where total dollar loss is minimized for option holders.
    This is often a "magnet" price at expiration.
    """
    if not call_oi and not put_oi:
        return spot_price

    all_strikes = set(call_oi.keys()) | set(put_oi.keys())
    if not all_strikes:
        return spot_price

    min_pain = float('inf')
    max_pain_strike = spot_price

    for test_strike in all_strikes:
        total_pain = 0

        # Pain for call holders (lose money if price below strike)
        for strike, oi in call_oi.items():
            if test_strike < strike:
                # Calls expire worthless
                pass
            else:
                # Calls have intrinsic value
                total_pain += (test_strike - strike) * oi * 100

        # Pain for put holders (lose money if price above strike)
        for strike, oi in put_oi.items():
            if test_strike > strike:
                # Puts expire worthless
                pass
            else:
                # Puts have intrinsic value
                total_pain += (strike - test_strike) * oi * 100

        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike

    return max_pain_strike


class TradierGEXCalculator:
    """
    GEX Calculator using Tradier options data.

    This is the fallback when TradingVolatilityAPI is unavailable.
    """

    def __init__(self):
        self._tradier = None
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

    def _get_tradier(self):
        """Lazy load Tradier client"""
        if self._tradier is None:
            try:
                from data.tradier_data_fetcher import TradierDataFetcher
                self._tradier = TradierDataFetcher()
            except ImportError as e:
                logger.error(f"Tradier not available: {e}")
                return None
        return self._tradier

    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cached data is still valid"""
        if symbol not in self._cache:
            return False
        cached_time = self._cache[symbol].get('timestamp', datetime.min)
        return (datetime.now() - cached_time).total_seconds() < self._cache_ttl

    def get_gex(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get GEX data for a symbol.

        Returns dict compatible with TradingVolatilityAPI format:
        {
            'symbol': str,
            'spot_price': float,
            'net_gex': float,
            'call_gex': float,
            'put_gex': float,
            'call_wall': float,
            'put_wall': float,
            'gamma_flip': float,
            'flip_point': float,
            'max_pain': float,
            'data_source': str,
            'collection_date': str
        }
        """
        # Check cache first
        if self._is_cache_valid(symbol):
            return self._cache[symbol]['data']

        tradier = self._get_tradier()
        if not tradier:
            return {'error': 'Tradier client not available'}

        try:
            # Get spot price
            quote = tradier.get_quote(symbol)
            if not quote:
                return {'error': f'Could not get quote for {symbol}'}

            spot_price = float(quote.get('last', 0) or quote.get('close', 0) or 0)
            if spot_price <= 0:
                return {'error': f'Invalid spot price for {symbol}'}

            # Get options chain with Greeks
            chain = tradier.get_option_chain(symbol, greeks=True)
            if not chain or not chain.chains:
                return {'error': f'Could not get options chain for {symbol}'}

            # Flatten all contracts into a list
            all_contracts = []
            for expiration, contracts in chain.chains.items():
                for contract in contracts:
                    all_contracts.append({
                        'strike': contract.strike,
                        'gamma': contract.gamma,
                        'delta': contract.delta,
                        'open_interest': contract.open_interest,
                        'option_type': contract.option_type,
                        'expiration': expiration
                    })

            if not all_contracts:
                return {'error': f'No options data for {symbol}'}

            # Calculate GEX
            result = calculate_gex_from_chain(symbol, spot_price, all_contracts)

            # Format response like TradingVolatilityAPI
            gex_data = {
                'symbol': result.symbol,
                'spot_price': result.spot_price,
                'net_gex': result.net_gex,
                'call_gex': result.call_gex,
                'put_gex': result.put_gex,
                'call_wall': result.call_wall,
                'put_wall': result.put_wall,
                'gamma_flip': result.gamma_flip,
                'flip_point': result.flip_point,
                'max_pain': result.max_pain,
                'data_source': 'tradier_calculated',
                'collection_date': result.timestamp.strftime('%Y-%m-%d'),
                'is_calculated': True
            }

            # Cache the result
            self._cache[symbol] = {
                'data': gex_data,
                'timestamp': datetime.now()
            }

            return gex_data

        except Exception as e:
            logger.error(f"GEX calculation failed for {symbol}: {e}")
            return {'error': f'GEX calculation failed: {str(e)}'}

    def get_gex_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed GEX profile with per-strike data.

        Returns:
        {
            'symbol': str,
            'spot_price': float,
            'flip_point': float,
            'call_wall': float,
            'put_wall': float,
            'strikes': List[{strike, call_gex, put_gex, net_gex}],
            'expirations': List[{date, gamma, dte}]
        }
        """
        tradier = self._get_tradier()
        if not tradier:
            return {'error': 'Tradier client not available'}

        try:
            quote = tradier.get_quote(symbol)
            spot_price = float(quote.get('last', 0) or quote.get('close', 0) or 0)

            chain = tradier.get_option_chain(symbol, greeks=True)
            if not chain or not chain.chains:
                return {'error': f'No options chain for {symbol}'}

            # Calculate GEX by expiration
            expirations_data = []
            all_contracts = []

            for expiration, contracts in chain.chains.items():
                exp_gamma = sum(c.gamma * c.open_interest for c in contracts if c.gamma)

                # Calculate DTE
                try:
                    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
                    dte = (exp_date - datetime.now()).days
                except:
                    dte = 0

                expirations_data.append({
                    'date': expiration,
                    'gamma': exp_gamma,
                    'dte': max(0, dte),
                    'call_gamma': sum(c.gamma * c.open_interest for c in contracts if c.option_type == 'call' and c.gamma),
                    'put_gamma': sum(c.gamma * c.open_interest for c in contracts if c.option_type == 'put' and c.gamma)
                })

                for contract in contracts:
                    all_contracts.append({
                        'strike': contract.strike,
                        'gamma': contract.gamma,
                        'open_interest': contract.open_interest,
                        'option_type': contract.option_type
                    })

            # Calculate overall GEX
            result = calculate_gex_from_chain(symbol, spot_price, all_contracts)

            return {
                'symbol': symbol,
                'spot_price': spot_price,
                'flip_point': result.gamma_flip,
                'call_wall': result.call_wall,
                'put_wall': result.put_wall,
                'max_pain': result.max_pain,
                'net_gex': result.net_gex,
                'strikes': result.strikes_data or [],
                'expirations': sorted(expirations_data, key=lambda x: x['date']),
                'data_source': 'tradier_calculated'
            }

        except Exception as e:
            logger.error(f"GEX profile calculation failed for {symbol}: {e}")
            return {'error': f'GEX profile calculation failed: {str(e)}'}


# Global instance for easy import
_gex_calculator = None

def get_gex_calculator() -> TradierGEXCalculator:
    """Get singleton GEX calculator instance"""
    global _gex_calculator
    if _gex_calculator is None:
        _gex_calculator = TradierGEXCalculator()
    return _gex_calculator


def get_calculated_gex(symbol: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get GEX data"""
    return get_gex_calculator().get_gex(symbol)


def get_calculated_gex_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get GEX profile"""
    return get_gex_calculator().get_gex_profile(symbol)
