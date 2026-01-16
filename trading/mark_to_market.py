"""
Mark-to-Market Option Pricing Utility

Provides real-time option price fetching from Tradier to calculate
accurate unrealized P&L for open positions.

This replaces estimation-based calculations with actual market quotes.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from functools import lru_cache
import time

logger = logging.getLogger(__name__)

# Cache for option quotes (TTL-based)
_quote_cache: Dict[str, Tuple[float, Dict]] = {}  # symbol -> (timestamp, quote)
CACHE_TTL_SECONDS = 30  # Cache quotes for 30 seconds


def _get_tradier_client():
    """Get Tradier client instance."""
    try:
        from data.tradier_data_fetcher import TradierDataFetcher
        api_key = os.environ.get('TRADIER_API_KEY') or os.environ.get('TRADIER_SANDBOX_API_KEY')
        if api_key:
            sandbox = 'SANDBOX' in str(os.environ.get('TRADIER_SANDBOX_API_KEY', ''))
            return TradierDataFetcher(api_key=api_key, sandbox=sandbox)
    except Exception as e:
        logger.debug(f"Could not create Tradier client: {e}")
    return None


def build_occ_symbol(
    underlying: str,
    expiration: str,
    strike: float,
    option_type: str  # 'C' or 'P'
) -> str:
    """
    Build OCC option symbol.

    Format: ROOT + YYMMDD + C/P + Strike*1000 (8 digits)
    Example: SPY240126C00500000 for SPY $500 call exp 1/26/24
    Example: SPXW240126P05900000 for SPX $5900 put exp 1/26/24

    Args:
        underlying: Underlying symbol (SPY, SPX)
        expiration: Expiration date as YYYY-MM-DD string
        strike: Strike price
        option_type: 'C' for call, 'P' for put

    Returns:
        OCC formatted option symbol
    """
    # Parse expiration
    if isinstance(expiration, str):
        exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    else:
        exp_date = expiration
    exp_str = exp_date.strftime('%y%m%d')

    # Format strike (multiply by 1000, pad to 8 digits)
    strike_num = float(strike) if isinstance(strike, str) else strike
    strike_str = f"{int(strike_num * 1000):08d}"

    # Build symbol - SPX uses SPXW for weeklies
    root = underlying.upper()
    if root == 'SPX':
        root = 'SPXW'

    return f"{root}{exp_str}{option_type.upper()}{strike_str}"


def get_option_quote(symbol: str, use_cache: bool = True) -> Optional[Dict]:
    """
    Get option quote from Tradier with caching.

    Args:
        symbol: OCC option symbol
        use_cache: Whether to use cached quotes (default True)

    Returns:
        Quote dict with bid, ask, last, etc. or None if unavailable
    """
    global _quote_cache

    # Check cache
    if use_cache and symbol in _quote_cache:
        cache_time, cached_quote = _quote_cache[symbol]
        if time.time() - cache_time < CACHE_TTL_SECONDS:
            return cached_quote

    # Fetch from Tradier
    tradier = _get_tradier_client()
    if not tradier:
        return None

    try:
        quote = tradier.get_quote(symbol)
        if quote:
            # Cache the result
            _quote_cache[symbol] = (time.time(), quote)
            return quote
    except Exception as e:
        logger.debug(f"Failed to fetch quote for {symbol}: {e}")

    return None


def get_option_quotes_batch(symbols: List[str], use_cache: bool = True) -> Dict[str, Dict]:
    """
    Get multiple option quotes efficiently.

    Args:
        symbols: List of OCC option symbols
        use_cache: Whether to use cached quotes

    Returns:
        Dict mapping symbol to quote data
    """
    global _quote_cache
    results = {}
    symbols_to_fetch = []

    # Check cache first
    if use_cache:
        for symbol in symbols:
            if symbol in _quote_cache:
                cache_time, cached_quote = _quote_cache[symbol]
                if time.time() - cache_time < CACHE_TTL_SECONDS:
                    results[symbol] = cached_quote
                else:
                    symbols_to_fetch.append(symbol)
            else:
                symbols_to_fetch.append(symbol)
    else:
        symbols_to_fetch = symbols

    # Fetch remaining from Tradier
    if symbols_to_fetch:
        tradier = _get_tradier_client()
        if tradier:
            try:
                # Tradier supports comma-separated symbols
                response = tradier._make_request(
                    'GET',
                    'markets/quotes',
                    params={'symbols': ','.join(symbols_to_fetch)}
                )
                quotes = response.get('quotes', {})

                if 'quote' in quotes:
                    quote_data = quotes['quote']
                    # Handle single quote vs list
                    if isinstance(quote_data, dict):
                        quote_data = [quote_data]

                    for quote in quote_data:
                        symbol = quote.get('symbol', '')
                        if symbol:
                            _quote_cache[symbol] = (time.time(), quote)
                            results[symbol] = quote
            except Exception as e:
                logger.debug(f"Failed to fetch batch quotes: {e}")

    return results


def calculate_ic_mark_to_market(
    underlying: str,
    expiration: str,
    put_short_strike: float,
    put_long_strike: float,
    call_short_strike: float,
    call_long_strike: float,
    contracts: int,
    entry_credit: float,
    use_cache: bool = True
) -> Dict:
    """
    Calculate mark-to-market value for an Iron Condor position.

    For an Iron Condor we hold:
    - Short put at put_short_strike (sold)
    - Long put at put_long_strike (bought)
    - Short call at call_short_strike (sold)
    - Long call at call_long_strike (bought)

    To close: Buy back shorts, sell longs
    Cost to close = (short_put_ask - long_put_bid) + (short_call_ask - long_call_bid)

    Args:
        underlying: SPX or SPY
        expiration: Expiration date YYYY-MM-DD
        put_short_strike, put_long_strike: Put spread strikes
        call_short_strike, call_long_strike: Call spread strikes
        contracts: Number of contracts
        entry_credit: Credit received when opening
        use_cache: Whether to use cached quotes

    Returns:
        Dict with:
        - success: bool
        - current_value: cost to close per contract
        - unrealized_pnl: total unrealized P&L
        - quotes: individual leg quotes
        - error: error message if failed
    """
    result = {
        'success': False,
        'current_value': None,
        'unrealized_pnl': None,
        'quotes': {},
        'method': 'mark_to_market',
        'error': None
    }

    # Build option symbols for all 4 legs
    exp_str = expiration if isinstance(expiration, str) else expiration.strftime('%Y-%m-%d')

    symbols = {
        'put_short': build_occ_symbol(underlying, exp_str, put_short_strike, 'P'),
        'put_long': build_occ_symbol(underlying, exp_str, put_long_strike, 'P'),
        'call_short': build_occ_symbol(underlying, exp_str, call_short_strike, 'C'),
        'call_long': build_occ_symbol(underlying, exp_str, call_long_strike, 'C'),
    }

    # Fetch all quotes in batch
    all_symbols = list(symbols.values())
    quotes = get_option_quotes_batch(all_symbols, use_cache=use_cache)

    # Store quotes in result
    result['quotes'] = {leg: quotes.get(sym) for leg, sym in symbols.items()}

    # Check if we got all quotes
    missing = [leg for leg, sym in symbols.items() if sym not in quotes or not quotes[sym]]
    if missing:
        result['error'] = f"Missing quotes for: {missing}"
        logger.debug(f"IC MTM failed - missing quotes: {missing}")
        return result

    try:
        # Get bid/ask for each leg
        # To close shorts: use ask (we buy back)
        # To close longs: use bid (we sell)
        put_short_quote = quotes[symbols['put_short']]
        put_long_quote = quotes[symbols['put_long']]
        call_short_quote = quotes[symbols['call_short']]
        call_long_quote = quotes[symbols['call_long']]

        # Use mid price if bid/ask not available, fall back to last
        def get_price(quote, side):
            """Get price from quote - ask for shorts, bid for longs"""
            if side == 'ask':
                return quote.get('ask') or quote.get('last') or 0
            else:
                return quote.get('bid') or quote.get('last') or 0

        put_short_ask = float(get_price(put_short_quote, 'ask'))
        put_long_bid = float(get_price(put_long_quote, 'bid'))
        call_short_ask = float(get_price(call_short_quote, 'ask'))
        call_long_bid = float(get_price(call_long_quote, 'bid'))

        # Cost to close the IC (per contract)
        # Buy back shorts (pay ask), sell longs (receive bid)
        put_spread_close = put_short_ask - put_long_bid  # Debit to close put spread
        call_spread_close = call_short_ask - call_long_bid  # Debit to close call spread

        current_value = put_spread_close + call_spread_close

        # Unrealized P&L = (credit received - cost to close) * 100 * contracts
        unrealized_pnl = (entry_credit - current_value) * 100 * contracts

        result['success'] = True
        result['current_value'] = round(current_value, 4)
        result['unrealized_pnl'] = round(unrealized_pnl, 2)
        result['leg_prices'] = {
            'put_short_ask': put_short_ask,
            'put_long_bid': put_long_bid,
            'call_short_ask': call_short_ask,
            'call_long_bid': call_long_bid,
            'put_spread_close': round(put_spread_close, 4),
            'call_spread_close': round(call_spread_close, 4),
        }

        logger.debug(
            f"IC MTM: {underlying} entry=${entry_credit:.4f}, "
            f"close=${current_value:.4f}, unrealized=${unrealized_pnl:.2f}"
        )

    except Exception as e:
        result['error'] = str(e)
        logger.debug(f"IC MTM calculation failed: {e}")

    return result


def calculate_spread_mark_to_market(
    underlying: str,
    expiration: str,
    long_strike: float,
    short_strike: float,
    spread_type: str,  # 'BULL_CALL', 'BEAR_PUT', etc.
    contracts: int,
    entry_debit: float,
    use_cache: bool = True
) -> Dict:
    """
    Calculate mark-to-market value for a vertical spread position.

    For a debit spread (bull call or bear put) we hold:
    - Long option at long_strike (bought)
    - Short option at short_strike (sold)

    To close: Sell the long, buy back the short
    Value = long_bid - short_ask

    Args:
        underlying: SPY or SPX
        expiration: Expiration date YYYY-MM-DD
        long_strike: Long option strike
        short_strike: Short option strike
        spread_type: Type of spread (BULL_CALL, BEAR_PUT, etc.)
        contracts: Number of contracts
        entry_debit: Debit paid when opening
        use_cache: Whether to use cached quotes

    Returns:
        Dict with success, current_value, unrealized_pnl, quotes, error
    """
    result = {
        'success': False,
        'current_value': None,
        'unrealized_pnl': None,
        'quotes': {},
        'method': 'mark_to_market',
        'error': None
    }

    # Determine option type from spread type
    spread_upper = spread_type.upper()
    if 'CALL' in spread_upper or 'BULL' in spread_upper:
        option_type = 'C'
    else:
        option_type = 'P'

    # Build option symbols
    exp_str = expiration if isinstance(expiration, str) else expiration.strftime('%Y-%m-%d')

    symbols = {
        'long': build_occ_symbol(underlying, exp_str, long_strike, option_type),
        'short': build_occ_symbol(underlying, exp_str, short_strike, option_type),
    }

    # Fetch quotes
    all_symbols = list(symbols.values())
    quotes = get_option_quotes_batch(all_symbols, use_cache=use_cache)

    result['quotes'] = {leg: quotes.get(sym) for leg, sym in symbols.items()}

    # Check if we got all quotes
    missing = [leg for leg, sym in symbols.items() if sym not in quotes or not quotes[sym]]
    if missing:
        result['error'] = f"Missing quotes for: {missing}"
        return result

    try:
        long_quote = quotes[symbols['long']]
        short_quote = quotes[symbols['short']]

        def get_price(quote, side):
            if side == 'ask':
                return quote.get('ask') or quote.get('last') or 0
            else:
                return quote.get('bid') or quote.get('last') or 0

        long_bid = float(get_price(long_quote, 'bid'))
        short_ask = float(get_price(short_quote, 'ask'))

        # Value of the spread = what we'd receive closing
        # Sell long (get bid), buy back short (pay ask)
        current_value = long_bid - short_ask

        # Unrealized P&L = (current_value - entry_debit) * 100 * contracts
        unrealized_pnl = (current_value - entry_debit) * 100 * contracts

        result['success'] = True
        result['current_value'] = round(current_value, 4)
        result['unrealized_pnl'] = round(unrealized_pnl, 2)
        result['leg_prices'] = {
            'long_bid': long_bid,
            'short_ask': short_ask,
        }

        logger.debug(
            f"Spread MTM: {underlying} {spread_type} entry=${entry_debit:.4f}, "
            f"value=${current_value:.4f}, unrealized=${unrealized_pnl:.2f}"
        )

    except Exception as e:
        result['error'] = str(e)
        logger.debug(f"Spread MTM calculation failed: {e}")

    return result


def clear_quote_cache():
    """Clear the quote cache."""
    global _quote_cache
    _quote_cache = {}


def get_cache_stats() -> Dict:
    """Get cache statistics."""
    global _quote_cache
    now = time.time()
    valid_count = sum(1 for ts, _ in _quote_cache.values() if now - ts < CACHE_TTL_SECONDS)
    return {
        'total_entries': len(_quote_cache),
        'valid_entries': valid_count,
        'ttl_seconds': CACHE_TTL_SECONDS,
    }
