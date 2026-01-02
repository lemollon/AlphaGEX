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
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Texas Central Time - standard timezone for all AlphaGEX operations
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Default implied volatility for strike range filtering (20%)
DEFAULT_IV_FOR_FILTERING = 0.20


# =============================================================================
# OPTIONS DATA VALIDATION
# =============================================================================

def validate_options_data(
    options_data: List[Dict],
    spot_price: float,
    symbol: str = "UNKNOWN"
) -> Dict[str, Any]:
    """
    Validate options data quality and freshness.

    Returns:
        Dict with 'valid' bool and 'issues' list
    """
    result = {
        'valid': True,
        'issues': [],
        'warnings': [],
        'stats': {}
    }

    if not options_data:
        result['valid'] = False
        result['issues'].append("No options data provided")
        return result

    if spot_price <= 0:
        result['valid'] = False
        result['issues'].append(f"Invalid spot price: {spot_price}")
        return result

    # Count contracts with valid data
    valid_contracts = 0
    contracts_with_gamma = 0
    contracts_with_oi = 0
    total_oi = 0
    strike_range = []

    for contract in options_data:
        strike = float(contract.get('strike', 0))
        gamma = float(contract.get('gamma', 0) or 0)
        oi = int(contract.get('open_interest', 0) or 0)

        if strike > 0:
            valid_contracts += 1
            strike_range.append(strike)

        if gamma > 0:
            contracts_with_gamma += 1

        if oi > 0:
            contracts_with_oi += 1
            total_oi += oi

    result['stats'] = {
        'total_contracts': len(options_data),
        'valid_contracts': valid_contracts,
        'contracts_with_gamma': contracts_with_gamma,
        'contracts_with_oi': contracts_with_oi,
        'total_open_interest': total_oi,
        'strike_range': (min(strike_range), max(strike_range)) if strike_range else (0, 0)
    }

    # Validation checks
    if valid_contracts < 10:
        result['valid'] = False
        result['issues'].append(f"Too few valid contracts: {valid_contracts} (need at least 10)")

    if contracts_with_gamma < 5:
        result['valid'] = False
        result['issues'].append(f"Too few contracts with gamma data: {contracts_with_gamma}")

    if contracts_with_oi < 5:
        result['valid'] = False
        result['issues'].append(f"Too few contracts with open interest: {contracts_with_oi}")

    if total_oi < 1000:
        result['warnings'].append(f"Low total open interest: {total_oi} (may indicate stale data)")

    # Check if strikes span around spot price
    if strike_range:
        min_strike, max_strike = min(strike_range), max(strike_range)
        if spot_price < min_strike or spot_price > max_strike:
            result['warnings'].append(
                f"Spot price {spot_price} is outside strike range [{min_strike}, {max_strike}]"
            )

        # Check for reasonable strike distribution
        strikes_below_spot = sum(1 for s in strike_range if s < spot_price)
        strikes_above_spot = sum(1 for s in strike_range if s > spot_price)

        if strikes_below_spot < 3 or strikes_above_spot < 3:
            result['warnings'].append(
                f"Unbalanced strike distribution: {strikes_below_spot} below, {strikes_above_spot} above spot"
            )

    if result['issues']:
        logger.warning(f"Options data validation failed for {symbol}: {result['issues']}")
    elif result['warnings']:
        logger.info(f"Options data warnings for {symbol}: {result['warnings']}")
    else:
        logger.debug(f"Options data validated for {symbol}: {result['stats']}")

    return result


def filter_strikes_to_7day_range(
    gamma_array: List[Dict],
    spot_price: float,
    implied_vol: float = None
) -> Tuple[List[Dict], float, float, float, float]:
    """
    Filter gamma_array to +/- 7-day expected move range.

    This matches TradingVolatility API's filtering behavior where strikes
    are limited to those within one standard deviation of the 7-day expected move.

    Args:
        gamma_array: List of strike data with 'strike', 'call_gamma', 'put_gamma', 'total_gamma'
        spot_price: Current spot price
        implied_vol: Implied volatility (defaults to 0.20 if not provided)

    Returns:
        Tuple of (filtered_array, call_wall, put_wall, min_strike, max_strike)
    """
    if implied_vol is None or implied_vol <= 0:
        implied_vol = DEFAULT_IV_FOR_FILTERING

    # 7-day expected move: spot * IV * sqrt(7/252)
    seven_day_std = spot_price * implied_vol * math.sqrt(7 / 252)
    min_strike = spot_price - seven_day_std
    max_strike = spot_price + seven_day_std

    # Filter strikes to +/- 7 day std range
    filtered_array = [
        s for s in gamma_array
        if min_strike <= s.get('strike', 0) <= max_strike
    ]

    # Recalculate call_wall and put_wall from filtered strikes
    # Call wall = strike with highest call gamma
    # Put wall = strike with highest put gamma (absolute value)
    call_wall = spot_price  # Default fallback
    put_wall = spot_price   # Default fallback
    max_call_gamma = 0
    max_put_gamma = 0

    for strike_data in filtered_array:
        call_g = abs(strike_data.get('call_gamma', 0))
        put_g = abs(strike_data.get('put_gamma', 0))

        if call_g > max_call_gamma:
            max_call_gamma = call_g
            call_wall = strike_data['strike']

        if put_g > max_put_gamma:
            max_put_gamma = put_g
            put_wall = strike_data['strike']

    logger.debug(f"Strike filtering: {len(gamma_array)} -> {len(filtered_array)} "
                 f"(range: ${min_strike:.2f} to ${max_strike:.2f})")

    return filtered_array, call_wall, put_wall, min_strike, max_strike


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
            timestamp=datetime.now(CENTRAL_TZ)
        )

    # Group by strike
    strikes_gex = {}
    total_call_gex = 0
    total_put_gex = 0

    # For wall calculation - track max gamma ABOVE and BELOW spot
    max_call_gex_above_spot = 0  # Call wall should be at/above spot (resistance)
    max_put_gex_below_spot = 0   # Put wall should be at/below spot (support)
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

            # Call Wall = max call gamma AT or ABOVE spot price (resistance level)
            if strike >= spot_price and gex_value > max_call_gex_above_spot:
                max_call_gex_above_spot = gex_value
                call_wall_strike = strike

        elif option_type == 'put':
            # Short puts = Short gamma for MM when hedging (negative GEX)
            strikes_gex[strike]['put_gex'] -= gex_value  # Negative for puts
            total_put_gex += gex_value  # Store absolute value
            put_oi_by_strike[strike] = put_oi_by_strike.get(strike, 0) + open_interest

            # Put Wall = max put gamma AT or BELOW spot price (support level)
            if strike <= spot_price and gex_value > max_put_gex_below_spot:
                max_put_gex_below_spot = gex_value
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

    def get_0dte_gex_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get 0DTE (same-day expiration) GEX profile with per-strike NET gamma.

        This is specifically for comparing with TradingVolatility API's 0DTE data.

        Returns:
        {
            'symbol': str,
            'spot_price': float,
            'flip_point': float,
            'call_wall': float,
            'put_wall': float,
            'net_gex': float,
            'gamma_array': List[{strike, call_gamma, put_gamma, total_gamma}],
            'expiration': str (the 0DTE date),
            'data_source': 'tradier_0dte_calculated',
            'timestamp': str
        }
        """
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
                return {'error': f'No options chain for {symbol}'}

            # Find 0DTE expiration (today's date)
            today = datetime.now().strftime('%Y-%m-%d')

            # Also check for next trading day if today has no options
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')

            zero_dte_expiration = None
            zero_dte_contracts = []

            # First, try to find exact 0DTE (today)
            for expiration, contracts in chain.chains.items():
                if expiration == today:
                    zero_dte_expiration = expiration
                    zero_dte_contracts = contracts
                    break

            # If no 0DTE today, find the nearest expiration (could be tomorrow for after-hours)
            if not zero_dte_contracts:
                sorted_expirations = sorted(chain.chains.keys())
                if sorted_expirations:
                    # Get the nearest expiration
                    zero_dte_expiration = sorted_expirations[0]
                    zero_dte_contracts = chain.chains[zero_dte_expiration]

                    # Calculate DTE for this expiration
                    try:
                        exp_date = datetime.strptime(zero_dte_expiration, '%Y-%m-%d')
                        dte = (exp_date.date() - datetime.now().date()).days
                        if dte > 1:
                            # More than 1 day out, not really 0DTE - warn but continue
                            logger.warning(f"Nearest expiration for {symbol} is {dte} days out: {zero_dte_expiration}")
                    except:
                        pass

            if not zero_dte_contracts:
                return {'error': f'No 0DTE options found for {symbol}'}

            # Convert contracts to format for GEX calculation
            # Also calculate P/C ratio from open interest
            options_data = []
            total_call_oi = 0
            total_put_oi = 0

            for contract in zero_dte_contracts:
                options_data.append({
                    'strike': contract.strike,
                    'gamma': contract.gamma,
                    'open_interest': contract.open_interest,
                    'option_type': contract.option_type
                })
                # Track OI for P/C ratio
                oi = contract.open_interest or 0
                if contract.option_type == 'call':
                    total_call_oi += oi
                elif contract.option_type == 'put':
                    total_put_oi += oi

            # Calculate P/C ratio
            put_call_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            # Calculate GEX for 0DTE only
            result = calculate_gex_from_chain(symbol, spot_price, options_data)

            # Format gamma_array to match TradingVolatility API format
            gamma_array = []
            for strike_data in (result.strikes_data or []):
                gamma_array.append({
                    'strike': strike_data['strike'],
                    'call_gamma': abs(strike_data.get('call_gex', 0)),  # Absolute value
                    'put_gamma': abs(strike_data.get('put_gex', 0)),   # Absolute value
                    'total_gamma': strike_data.get('net_gex', 0),      # Net (can be negative)
                    'net_gex': strike_data.get('net_gex', 0)           # Alias
                })

            # Apply 7-day expected move filtering to match TradingVolatility API behavior
            # This ensures Tradier shows the same number of strikes as TradingVol API
            total_strikes_before = len(gamma_array)
            gamma_array_filtered, call_wall_filtered, put_wall_filtered, min_strike, max_strike = \
                filter_strikes_to_7day_range(gamma_array, spot_price)

            logger.info(f"0DTE strike filtering for {symbol}: "
                       f"{total_strikes_before} -> {len(gamma_array_filtered)} strikes "
                       f"(range: ${min_strike:.2f} - ${max_strike:.2f})")

            # Recalculate flip point within filtered range
            flip_point_filtered = result.gamma_flip
            for i in range(len(gamma_array_filtered) - 1):
                net_current = gamma_array_filtered[i].get('net_gex', 0)
                net_next = gamma_array_filtered[i + 1].get('net_gex', 0)

                # Check for sign change (zero crossing)
                if net_current * net_next < 0:
                    strike_current = gamma_array_filtered[i]['strike']
                    strike_next = gamma_array_filtered[i + 1]['strike']
                    # Linear interpolation
                    flip_point_filtered = strike_current + (strike_next - strike_current) * (
                        -net_current / (net_next - net_current)
                    )
                    break

            return {
                'symbol': symbol,
                'spot_price': spot_price,
                'flip_point': flip_point_filtered,
                'call_wall': call_wall_filtered,
                'put_wall': put_wall_filtered,
                'max_pain': result.max_pain,
                'net_gex': result.net_gex,
                'put_call_ratio': round(put_call_ratio, 3),
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'gamma_array': gamma_array_filtered,
                'expiration': zero_dte_expiration,
                'contracts_count': len(gamma_array_filtered),
                'total_contracts_before_filter': total_strikes_before,
                'data_source': 'tradier_0dte_calculated',
                'timestamp': datetime.now(CENTRAL_TZ).isoformat()
            }

        except Exception as e:
            logger.error(f"0DTE GEX calculation failed for {symbol}: {e}")
            return {'error': f'0DTE GEX calculation failed: {str(e)}'}

    def get_all_expirations_gex_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get ALL expirations GEX profile with per-strike NET gamma.

        This combines all available expirations to match TradingVolatility API's
        gammaOI endpoint which returns all expirations.

        Returns:
        {
            'symbol': str,
            'spot_price': float,
            'flip_point': float,
            'call_wall': float,
            'put_wall': float,
            'net_gex': float,
            'gamma_array': List[{strike, call_gamma, put_gamma, total_gamma}],
            'expiration': 'all_expirations',
            'data_source': 'tradier_all_expirations_calculated',
            'timestamp': str
        }
        """
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

            # Get options chain with Greeks - use get_multiple_chains to get ALL expirations
            # get_option_chain without expiration only returns the NEAREST expiration
            # For "all expirations" comparison, we need multiple expirations
            chain = tradier.get_multiple_chains(symbol, num_expirations=8, greeks=True)
            if not chain or not chain.chains:
                return {'error': f'No options chain for {symbol}'}

            logger.info(f"Fetched {len(chain.chains)} expirations for {symbol}: {list(chain.chains.keys())}")

            # Combine ALL expirations
            all_contracts = []
            total_call_oi = 0
            total_put_oi = 0
            expirations_included = []

            for expiration, contracts in chain.chains.items():
                expirations_included.append(expiration)
                for contract in contracts:
                    all_contracts.append({
                        'strike': contract.strike,
                        'gamma': contract.gamma,
                        'open_interest': contract.open_interest,
                        'option_type': contract.option_type
                    })
                    # Track OI for P/C ratio
                    oi = contract.open_interest or 0
                    if contract.option_type == 'call':
                        total_call_oi += oi
                    elif contract.option_type == 'put':
                        total_put_oi += oi

            if not all_contracts:
                return {'error': f'No options contracts found for {symbol}'}

            # Calculate P/C ratio
            put_call_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0

            # Calculate GEX for ALL expirations
            result = calculate_gex_from_chain(symbol, spot_price, all_contracts)

            # Format gamma_array to match TradingVolatility API format
            gamma_array = []
            for strike_data in (result.strikes_data or []):
                gamma_array.append({
                    'strike': strike_data['strike'],
                    'call_gamma': abs(strike_data.get('call_gex', 0)),  # Absolute value
                    'put_gamma': abs(strike_data.get('put_gex', 0)),   # Absolute value
                    'total_gamma': strike_data.get('net_gex', 0),      # Net (can be negative)
                    'net_gex': strike_data.get('net_gex', 0)           # Alias
                })

            # Apply 7-day expected move filtering to match TradingVolatility API behavior
            # This ensures Tradier shows the same number of strikes as TradingVol API
            total_strikes_before = len(gamma_array)
            gamma_array_filtered, call_wall_filtered, put_wall_filtered, min_strike, max_strike = \
                filter_strikes_to_7day_range(gamma_array, spot_price)

            logger.info(f"All expirations strike filtering for {symbol}: "
                       f"{total_strikes_before} -> {len(gamma_array_filtered)} strikes "
                       f"(range: ${min_strike:.2f} - ${max_strike:.2f})")

            # Recalculate flip point within filtered range
            flip_point_filtered = result.gamma_flip
            for i in range(len(gamma_array_filtered) - 1):
                net_current = gamma_array_filtered[i].get('net_gex', 0)
                net_next = gamma_array_filtered[i + 1].get('net_gex', 0)

                # Check for sign change (zero crossing)
                if net_current * net_next < 0:
                    strike_current = gamma_array_filtered[i]['strike']
                    strike_next = gamma_array_filtered[i + 1]['strike']
                    # Linear interpolation
                    flip_point_filtered = strike_current + (strike_next - strike_current) * (
                        -net_current / (net_next - net_current)
                    )
                    break

            return {
                'symbol': symbol,
                'spot_price': spot_price,
                'flip_point': flip_point_filtered,
                'call_wall': call_wall_filtered,
                'put_wall': put_wall_filtered,
                'max_pain': result.max_pain,
                'net_gex': result.net_gex,
                'put_call_ratio': round(put_call_ratio, 3),
                'total_call_oi': total_call_oi,
                'total_put_oi': total_put_oi,
                'gamma_array': gamma_array_filtered,
                'expiration': 'All expirations',
                'expirations_included': sorted(expirations_included),
                'contracts_count': len(gamma_array_filtered),
                'total_contracts_before_filter': total_strikes_before,
                'data_source': 'tradier_all_expirations_calculated',
                'timestamp': datetime.now(CENTRAL_TZ).isoformat()
            }

        except Exception as e:
            logger.error(f"All expirations GEX calculation failed for {symbol}: {e}")
            return {'error': f'All expirations GEX calculation failed: {str(e)}'}


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


def get_0dte_gex_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get 0DTE GEX profile for comparison"""
    return get_gex_calculator().get_0dte_gex_profile(symbol)


def get_all_expirations_gex_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """Convenience function to get all-expirations GEX profile for comparison"""
    return get_gex_calculator().get_all_expirations_gex_profile(symbol)
