"""
JUBILEE Order Executor - Box Spread Execution

Handles order placement and position management for box spreads.
Includes comprehensive educational annotations for learning.

IMPORTANT - Production Quote Strategy:
======================================
SPX options REQUIRE Tradier PRODUCTION API - the sandbox does NOT provide
SPX option quotes. Even in paper trading mode, we use production API for
quotes to ensure realistic pricing. This is critical for:
1. Accurate implied rate calculations
2. Realistic equity curves
3. Proper mark-to-market valuations
"""

import logging
import os
import time
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, Tuple, List
import uuid

from .models import (
    BoxSpreadPosition,
    BoxSpreadSignal,
    CapitalDeployment,
    JubileeConfig,
    PositionStatus,
    TradingMode,
    # IC Trading Models
    JubileeICSignal,
    JubileeICPosition,
    JubileeICConfig,
    ICPositionStatus,
)
from .db import JubileeDatabase
from .tracing import get_tracer, trace_quote, trace_position

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

# Try to import Tradier
try:
    from data.tradier_data_fetcher import TradierDataFetcher
    tradier_available = True
except ImportError:
    tradier_available = False
    logger.warning("TradierDataFetcher not available - paper trading only")

# Quote cache for box spread pricing (TTL-based)
_quote_cache: Dict[str, Tuple[float, Dict]] = {}
CACHE_TTL_SECONDS = 30  # Cache quotes for 30 seconds


def _get_production_tradier_client(underlying: str = "SPX"):
    """
    Get Tradier client for SPX quotes - ALWAYS uses production API.

    EDUCATIONAL NOTE:
    =================
    The Tradier sandbox API does NOT provide SPX option quotes.
    For realistic paper trading, we MUST use the production API
    to get actual market prices. This ensures:
    - Accurate implied borrowing rates
    - Realistic bid-ask spreads
    - Proper mark-to-market calculations

    This follows the same pattern used by SAMSON/ANCHOR for SPX quotes.
    """
    if not tradier_available:
        logger.warning("TradierDataFetcher not available")
        return None

    try:
        # Check production keys - TRADIER_PROD_API_KEY takes priority
        prod_key = os.environ.get('TRADIER_PROD_API_KEY') or os.environ.get('TRADIER_API_KEY')

        if prod_key:
            logger.info(f"Using Tradier PRODUCTION API for {underlying} box spread quotes")
            return TradierDataFetcher(api_key=prod_key, sandbox=False)
        else:
            logger.error(
                f"SPX quotes require production Tradier API key "
                f"(TRADIER_PROD_API_KEY or TRADIER_API_KEY) - NEITHER is set. "
                f"Box spread quotes will NOT be available until API key is configured."
            )
            return None

    except Exception as e:
        logger.warning(f"Could not create production Tradier client: {e}")
        return None


def build_occ_symbol(
    underlying: str,
    expiration: str,
    strike: float,
    option_type: str
) -> str:
    """
    Build OCC-format option symbol.

    EDUCATIONAL NOTE:
    =================
    OCC (Options Clearing Corporation) symbols follow this format:
    ROOT + YYMMDD + C/P + STRIKE*1000

    Example: SPXW240315C05900000
    - SPXW = SPX weekly options root symbol
    - 240315 = March 15, 2024
    - C = Call (P = Put)
    - 05900000 = $5900.00 strike (8 digits)

    IMPORTANT: SPX uses "SPXW" as the root symbol for weeklies,
    which is what we typically trade for box spreads. The Tradier
    API requires this exact format for quote fetching.
    """
    # Parse expiration date
    exp_date = datetime.strptime(expiration, '%Y-%m-%d')
    date_str = exp_date.strftime('%y%m%d')

    # Option type
    opt_type = 'C' if option_type.lower() == 'call' else 'P'

    # Strike (multiply by 1000, pad to 8 digits)
    strike_int = int(strike * 1000)
    strike_str = f"{strike_int:08d}"

    # Handle SPX -> SPXW conversion for weeklies
    root = underlying.upper()
    if root == 'SPX':
        root = 'SPXW'

    return f"{root}{date_str}{opt_type}{strike_str}"


@trace_quote
def get_box_spread_quotes(
    ticker: str,
    expiration: str,
    lower_strike: float,
    upper_strike: float,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Fetch real-time quotes for all 4 legs of a box spread from Tradier PRODUCTION API.

    EDUCATIONAL NOTE:
    =================
    This function fetches actual market prices for the box spread components:
    - Long call at lower strike
    - Short call at upper strike
    - Long put at upper strike
    - Short put at lower strike

    We use the PRODUCTION Tradier API because SPX quotes are not available
    in the sandbox. The quotes are cached for 30 seconds to reduce API calls.

    Returns:
        Dict with quotes for each leg, plus calculated mid prices and spreads.
        If quotes unavailable, returns success=False with error details.
    """
    global _quote_cache

    result = {
        'success': False,
        'quotes': {},
        'mid_prices': {},
        'box_bid': None,
        'box_ask': None,
        'box_mid': None,
        'implied_rate': None,
        'quote_time': datetime.now(CENTRAL_TZ).isoformat(),
        'source': 'unknown',
        'error': None,
    }

    # Build OCC symbols for all 4 legs
    symbols = {
        'call_long': build_occ_symbol(ticker, expiration, lower_strike, 'call'),
        'call_short': build_occ_symbol(ticker, expiration, upper_strike, 'call'),
        'put_long': build_occ_symbol(ticker, expiration, upper_strike, 'put'),
        'put_short': build_occ_symbol(ticker, expiration, lower_strike, 'put'),
    }

    logger.info(f"Fetching box spread quotes for {ticker} {lower_strike}/{upper_strike} exp {expiration}")
    for leg, sym in symbols.items():
        logger.debug(f"  {leg}: {sym}")

    # Check cache first
    cached_quotes = {}
    symbols_to_fetch = []

    if use_cache:
        for leg, sym in symbols.items():
            if sym in _quote_cache:
                cache_time, cached_quote = _quote_cache[sym]
                if time.time() - cache_time < CACHE_TTL_SECONDS:
                    cached_quotes[leg] = cached_quote
                else:
                    symbols_to_fetch.append((leg, sym))
            else:
                symbols_to_fetch.append((leg, sym))
    else:
        symbols_to_fetch = [(leg, sym) for leg, sym in symbols.items()]

    # If we have all from cache, use them
    if len(cached_quotes) == 4:
        result['quotes'] = cached_quotes
        result['source'] = 'cache'
        logger.info("Using cached quotes for box spread")
    else:
        # Fetch from Tradier PRODUCTION API
        tradier = _get_production_tradier_client(ticker)

        if tradier:
            try:
                # Fetch all symbols at once
                all_symbols = [sym for _, sym in symbols_to_fetch]
                all_symbols.extend(symbols[leg] for leg in cached_quotes.keys())

                response = tradier._make_request(
                    'GET',
                    'markets/quotes',
                    params={'symbols': ','.join([symbols[leg] for leg in symbols.keys()])}
                )

                if response and 'quotes' in response:
                    quotes_data = response['quotes']
                    if 'quote' in quotes_data:
                        quote_list = quotes_data['quote']
                        if isinstance(quote_list, dict):
                            quote_list = [quote_list]

                        # Map quotes back to legs
                        fetched_quotes = {}
                        for quote in quote_list:
                            quote_symbol = quote.get('symbol', '')
                            for leg, sym in symbols.items():
                                if quote_symbol.upper() == sym.upper():
                                    fetched_quotes[leg] = quote
                                    _quote_cache[sym] = (time.time(), quote)

                        # Combine cached and fetched
                        result['quotes'] = {**cached_quotes, **fetched_quotes}
                        result['source'] = 'tradier_production'
                        logger.info(f"Fetched {len(fetched_quotes)} quotes from Tradier PRODUCTION API")
                else:
                    result['error'] = "Empty response from Tradier API"
                    logger.warning(f"Empty Tradier response for box spread quotes")

            except Exception as e:
                result['error'] = f"Tradier API error: {str(e)}"
                logger.error(f"Error fetching box spread quotes: {e}")
        else:
            result['error'] = "No production Tradier client available - SPX quotes require TRADIER_API_KEY"
            result['source'] = 'unavailable'

    # Check if we have all 4 legs
    if len(result['quotes']) == 4:
        try:
            # Calculate mid prices for each leg
            def get_mid(quote):
                bid = quote.get('bid', 0) or 0
                ask = quote.get('ask', 0) or 0
                if bid > 0 and ask > 0:
                    return (float(bid) + float(ask)) / 2
                return float(quote.get('last', 0) or 0)

            result['mid_prices'] = {leg: get_mid(quote) for leg, quote in result['quotes'].items()}

            # Calculate box spread value
            # Box value = (Call Long - Call Short) + (Put Long - Put Short)
            # For SELLING a box, we receive: box_mid
            # At expiration, we owe: strike_width
            call_spread_mid = result['mid_prices']['call_long'] - result['mid_prices']['call_short']
            put_spread_mid = result['mid_prices']['put_long'] - result['mid_prices']['put_short']
            box_mid = call_spread_mid + put_spread_mid

            # Also calculate using bid/ask for spread
            def get_bid(quote):
                return float(quote.get('bid', 0) or 0)

            def get_ask(quote):
                return float(quote.get('ask', 0) or 0)

            # Box bid (what we can sell for) - sell at bid for legs we're selling
            call_spread_bid = get_bid(result['quotes']['call_long']) - get_ask(result['quotes']['call_short'])
            put_spread_bid = get_bid(result['quotes']['put_long']) - get_ask(result['quotes']['put_short'])
            box_bid = call_spread_bid + put_spread_bid

            # Box ask (what we'd pay to close) - buy at ask for legs we're buying back
            call_spread_ask = get_ask(result['quotes']['call_long']) - get_bid(result['quotes']['call_short'])
            put_spread_ask = get_ask(result['quotes']['put_long']) - get_bid(result['quotes']['put_short'])
            box_ask = call_spread_ask + put_spread_ask

            result['box_bid'] = round(box_bid, 4)
            result['box_ask'] = round(box_ask, 4)
            result['box_mid'] = round(box_mid, 4)

            # Calculate implied rate
            strike_width = upper_strike - lower_strike
            exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
            dte = (exp_date - date.today()).days

            if dte > 0 and box_mid > 0:
                cash_received = box_mid * 100  # Per contract
                cash_owed = strike_width * 100
                borrowing_cost = cash_owed - cash_received
                time_fraction = dte / 365.0
                implied_rate = (borrowing_cost / cash_received) / time_fraction * 100
                result['implied_rate'] = round(implied_rate, 4)

            result['success'] = True
            implied_rate_log = f"{result['implied_rate']}%" if result['implied_rate'] else "N/A"
            logger.info(
                f"Box spread calculated: bid={result['box_bid']}, "
                f"mid={result['box_mid']}, ask={result['box_ask']}, "
                f"implied_rate={implied_rate_log}"
            )

        except Exception as e:
            result['error'] = f"Calculation error: {str(e)}"
            logger.error(f"Error calculating box spread values: {e}")
    else:
        missing = [leg for leg in symbols.keys() if leg not in result['quotes']]
        result['error'] = f"Missing quotes for legs: {missing}"
        logger.warning(f"Incomplete box spread quotes - missing: {missing}")

    return result


def calculate_box_spread_mark_to_market(
    ticker: str,
    expiration: str,
    lower_strike: float,
    upper_strike: float,
    contracts: int,
    entry_credit: float,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Calculate mark-to-market value for an open box spread position.

    EDUCATIONAL NOTE:
    =================
    For an open short box spread position:
    - We received a credit when we opened (entry_credit per contract)
    - Current value = what we'd pay to close = box_ask
    - Unrealized P&L = (entry_credit - current_close_cost) * 100 * contracts

    Uses MID prices by default for a fair representation of position value.
    The function fetches real quotes from Tradier PRODUCTION API.

    Args:
        ticker: SPX or other underlying
        expiration: Expiration date YYYY-MM-DD
        lower_strike: Lower strike price
        upper_strike: Upper strike price
        contracts: Number of contracts
        entry_credit: Credit received per contract when opened
        use_cache: Whether to use cached quotes

    Returns:
        Dict with:
        - success: bool
        - current_value: cost to close per contract (using mid)
        - unrealized_pnl: total unrealized P&L
        - quotes: individual leg quotes
        - timestamp: when this MTM was calculated
    """
    result = {
        'success': False,
        'current_value': None,
        'unrealized_pnl': None,
        'quotes': {},
        'leg_prices': {},
        'method': 'mark_to_market',
        'quote_source': 'unknown',
        'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
        'error': None,
    }

    # Get quotes
    quote_result = get_box_spread_quotes(
        ticker, expiration, lower_strike, upper_strike, use_cache
    )

    if not quote_result['success']:
        result['error'] = quote_result.get('error', 'Failed to get quotes')
        result['quote_source'] = quote_result.get('source', 'failed')
        return result

    result['quotes'] = quote_result['quotes']
    result['quote_source'] = quote_result['source']
    result['leg_prices'] = quote_result['mid_prices']

    try:
        # Current cost to close = box mid price (what we'd pay to buy back)
        current_value = quote_result['box_mid']

        # Unrealized P&L = (credit received - cost to close) * 100 * contracts
        # If we received 49.50 and it costs 49.60 to close, we're down
        unrealized_pnl = (entry_credit - current_value) * 100 * contracts

        result['success'] = True
        result['current_value'] = round(current_value, 4)
        result['unrealized_pnl'] = round(unrealized_pnl, 2)
        result['box_bid'] = quote_result['box_bid']
        result['box_ask'] = quote_result['box_ask']
        result['box_mid'] = quote_result['box_mid']
        result['current_implied_rate'] = quote_result['implied_rate']

        logger.info(
            f"Box MTM: entry=${entry_credit:.4f}, "
            f"current=${current_value:.4f}, "
            f"unrealized=${unrealized_pnl:.2f}"
        )

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Box MTM calculation error: {e}")

    return result


class BoxSpreadExecutor:
    """
    Executes box spread orders with full transparency.

    EDUCATIONAL NOTE - Order Execution:
    ====================================
    A box spread requires executing TWO spread orders:
    1. Bull Call Spread: Sell high call, buy low call
    2. Bear Put Spread: Sell low put, buy high put

    We typically execute as combo/spread orders rather than
    individual legs to reduce slippage and execution risk.

    Order types:
    - LIMIT: Best for defined risk, ensures minimum credit
    - MARKET: Faster fill but may get worse price
    - We always use LIMIT orders for box spreads

    PRODUCTION QUOTES:
    ==================
    Even in PAPER mode, we use PRODUCTION Tradier API for SPX quotes.
    This ensures realistic pricing for:
    - Accurate implied rate calculations
    - Real bid-ask spreads
    - Proper mark-to-market valuations
    """

    def __init__(
        self,
        config: JubileeConfig,
        db: JubileeDatabase
    ):
        self.config = config
        self.db = db
        # Use production client for SPX quotes (even in paper mode)
        self.tradier = _get_production_tradier_client(config.ticker)

    def execute_signal(
        self,
        signal: BoxSpreadSignal
    ) -> Optional[BoxSpreadPosition]:
        """
        Execute a box spread signal.

        This creates a position by:
        1. Building option symbols for all 4 legs
        2. Placing the call spread order
        3. Placing the put spread order
        4. Creating and saving the position record

        Returns the created position or None if execution fails.
        """
        # Trace the execution
        tracer.trace_position_opened(signal.signal_id, signal.cash_received or 0)

        now = datetime.now(CENTRAL_TZ)

        # Generate position ID
        position_id = f"PROM-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # Build OCC symbols for all 4 legs
        symbols = self._build_option_symbols(signal)

        logger.info(f"Executing box spread signal {signal.signal_id}")
        logger.info(f"  Lower strike: {signal.lower_strike}")
        logger.info(f"  Upper strike: {signal.upper_strike}")
        logger.info(f"  Expiration: {signal.expiration}")
        logger.info(f"  Contracts: {signal.recommended_contracts}")

        # Execute orders
        if self.config.mode == TradingMode.LIVE and self.tradier:
            call_order = self._execute_call_spread(signal, symbols)
            put_order = self._execute_put_spread(signal, symbols)

            if not call_order or not put_order:
                logger.error("Failed to execute one or both spread orders")
                return None

            call_order_id = call_order.get('id', 'LIVE-CALL')
            put_order_id = put_order.get('id', 'LIVE-PUT')
        else:
            # Paper trading - use REAL production quotes for realistic pricing
            call_order_id = f"PAPER-CALL-{uuid.uuid4().hex[:8]}"
            put_order_id = f"PAPER-PUT-{uuid.uuid4().hex[:8]}"

            # Get real quotes from production API for accurate paper trading
            real_quotes = get_box_spread_quotes(
                signal.ticker,
                signal.expiration,
                signal.lower_strike,
                signal.upper_strike,
                use_cache=False  # Fresh quotes for execution
            )

            if real_quotes['success']:
                # Use real mid price instead of theoretical
                signal.mid_price = real_quotes['box_mid']
                signal.market_bid = real_quotes['box_bid']
                signal.market_ask = real_quotes['box_ask']
                signal.implied_annual_rate = real_quotes['implied_rate'] or signal.implied_annual_rate

                # Recalculate cash values with real prices
                signal.cash_received = signal.mid_price * 100 * signal.recommended_contracts
                theoretical_value = signal.strike_width * 100 * signal.recommended_contracts
                signal.borrowing_cost = theoretical_value - signal.cash_received

                implied_rate_str = f"{real_quotes['implied_rate']:.2f}%" if real_quotes['implied_rate'] else "N/A"
                logger.info(
                    f"PAPER TRADING with REAL PRODUCTION quotes: "
                    f"mid=${real_quotes['box_mid']:.4f}, "
                    f"implied_rate={implied_rate_str}"
                )
            else:
                logger.error(
                    f"CRITICAL: Could not get production quotes ({real_quotes.get('error', 'unknown')}). "
                    f"Position will NOT have accurate pricing - ensure TRADIER_API_KEY is set."
                )

        # Calculate capital deployment
        deployment = self._calculate_deployment(signal, position_id)

        # Create position object
        position = BoxSpreadPosition(
            position_id=position_id,
            ticker=signal.ticker,
            lower_strike=signal.lower_strike,
            upper_strike=signal.upper_strike,
            strike_width=signal.strike_width,
            expiration=signal.expiration,
            dte_at_entry=signal.dte,
            current_dte=signal.dte,
            call_long_symbol=symbols['call_long'],
            call_short_symbol=symbols['call_short'],
            put_long_symbol=symbols['put_long'],
            put_short_symbol=symbols['put_short'],
            call_spread_order_id=call_order_id,
            put_spread_order_id=put_order_id,
            contracts=signal.recommended_contracts,
            entry_credit=signal.mid_price,
            total_credit_received=signal.cash_received,
            theoretical_value=signal.theoretical_value,
            total_owed_at_expiration=signal.cash_owed_at_expiration,
            borrowing_cost=signal.borrowing_cost,
            implied_annual_rate=signal.implied_annual_rate,
            daily_cost=signal.borrowing_cost / signal.dte if signal.dte > 0 else 0,
            cost_accrued_to_date=0.0,
            fed_funds_at_entry=signal.fed_funds_rate,
            margin_rate_at_entry=signal.margin_rate,
            savings_vs_margin=signal.cash_received * (signal.margin_rate - signal.implied_annual_rate) / 100,
            cash_deployed_to_ares=deployment.fortress_allocation,
            cash_deployed_to_titan=deployment.samson_allocation,
            cash_deployed_to_pegasus=deployment.anchor_allocation,
            cash_held_in_reserve=deployment.reserve_amount,
            total_cash_deployed=deployment.total_capital_available,
            returns_from_ares=0.0,
            returns_from_titan=0.0,
            returns_from_pegasus=0.0,
            total_ic_returns=0.0,
            net_profit=0.0,
            spot_at_entry=signal.spot_price,
            vix_at_entry=0.0,  # Would get from market data
            early_assignment_risk=signal.early_assignment_risk,
            current_margin_used=signal.margin_requirement,
            margin_cushion=self.config.capital * (self.config.max_margin_pct / 100) - signal.margin_requirement,
            status=PositionStatus.OPEN,
            open_time=now,
            position_explanation=self._generate_position_explanation(signal, deployment),
            daily_briefing="",
        )

        # Save position to database
        if self.db.save_position(position):
            logger.info(f"Position {position_id} saved successfully")

            # Save capital deployment
            self.db.save_deployment(deployment)

            # Log the action
            self.db.log_action(
                action="POSITION_OPENED",
                message=f"Opened box spread position {position_id}",
                level="INFO",
                details={
                    'signal_id': signal.signal_id,
                    'strikes': f"{signal.lower_strike}/{signal.upper_strike}",
                    'cash_received': signal.cash_received,
                    'implied_rate': signal.implied_annual_rate,
                },
                position_id=position_id,
                signal_id=signal.signal_id,
                log_type="BOX",
            )

            return position
        else:
            logger.error(f"Failed to save position {position_id}")
            return None

    def _build_option_symbols(
        self,
        signal: BoxSpreadSignal
    ) -> Dict[str, str]:
        """Build OCC symbols for all 4 legs of the box spread"""
        return {
            'call_long': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.lower_strike, 'call'
            ),
            'call_short': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.upper_strike, 'call'
            ),
            'put_long': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.upper_strike, 'put'
            ),
            'put_short': build_occ_symbol(
                signal.ticker, signal.expiration,
                signal.lower_strike, 'put'
            ),
        }

    def _execute_call_spread(
        self,
        signal: BoxSpreadSignal,
        symbols: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the call spread leg of the box.

        EDUCATIONAL NOTE:
        =================
        For SELLING the box, we sell the call vertical spread:
        - Sell upper strike call (receive premium)
        - Buy lower strike call (pay premium, but less)
        - Net: Receive credit on the call side
        """
        if not self.tradier:
            return {'id': 'PAPER-CALL', 'status': 'filled'}

        try:
            # Use Tradier's place_vertical_spread with correct indexed-key format
            # For the call spread: sell the short (upper) call, buy the long (lower) call
            result = self.tradier.place_vertical_spread(
                symbol=signal.ticker,
                expiration=signal.expiration,
                long_strike=signal.lower_strike,   # Buy lower call
                short_strike=signal.upper_strike,   # Sell upper call
                option_type="call",
                quantity=signal.recommended_contracts,
                limit_price=round(signal.mid_price / 2, 2),  # Half the total credit
            )
            return result

        except Exception as e:
            logger.error(f"Error executing call spread: {e}")
            return None

    def _execute_put_spread(
        self,
        signal: BoxSpreadSignal,
        symbols: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute the put spread leg of the box.

        EDUCATIONAL NOTE:
        =================
        For SELLING the box, we sell the put vertical spread:
        - Sell lower strike put (receive premium)
        - Buy upper strike put (pay premium, but less)
        - Net: Receive credit on the put side
        """
        if not self.tradier:
            return {'id': 'PAPER-PUT', 'status': 'filled'}

        try:
            # Use Tradier's place_vertical_spread with correct indexed-key format
            # For the put spread: sell the short (lower) put, buy the long (upper) put
            result = self.tradier.place_vertical_spread(
                symbol=signal.ticker,
                expiration=signal.expiration,
                long_strike=signal.upper_strike,    # Buy upper put
                short_strike=signal.lower_strike,    # Sell lower put
                option_type="put",
                quantity=signal.recommended_contracts,
                limit_price=round(signal.mid_price / 2, 2),  # Half the total credit
            )
            return result

        except Exception as e:
            logger.error(f"Error executing put spread: {e}")
            return None

    def _calculate_deployment(
        self,
        signal: BoxSpreadSignal,
        position_id: str
    ) -> CapitalDeployment:
        """
        Calculate how to deploy the borrowed capital to IC bots.

        EDUCATIONAL NOTE:
        =================
        Capital deployment strategy:
        1. FORTRESS (SPY 0DTE ICs) - aggressive, daily opportunities
        2. SAMSON (SPX Aggressive ICs) - aggressive SPX plays
        3. ANCHOR (SPX Weekly ICs) - more conservative
        4. RESERVE - buffer for margin and emergencies

        The allocation is based on:
        - Historical bot performance
        - Current market regime
        - Risk tolerance settings
        """
        total_cash = signal.cash_received
        now = datetime.now(CENTRAL_TZ)

        # Calculate allocations based on config percentages
        fortress_amount = total_cash * (self.config.fortress_allocation_pct / 100)
        samson_amount = total_cash * (self.config.samson_allocation_pct / 100)
        anchor_amount = total_cash * (self.config.anchor_allocation_pct / 100)
        reserve_amount = total_cash * (self.config.reserve_pct / 100)

        # Generate reasoning for each allocation
        ares_reasoning = f"""
FORTRESS receives {self.config.fortress_allocation_pct}% (${fortress_amount:,.2f}) because:
- FORTRESS trades SPY 0DTE Iron Condors with proven track record
- High trade frequency allows rapid capital deployment
- Recommended for active premium collection
""".strip()

        titan_reasoning = f"""
SAMSON receives {self.config.samson_allocation_pct}% (${samson_amount:,.2f}) because:
- SAMSON runs aggressive SPX Iron Condors
- Higher premium per trade than SPY strategies
- Complements FORTRESS with SPX exposure
""".strip()

        anchor_reasoning = f"""
ANCHOR receives {self.config.anchor_allocation_pct}% (${anchor_amount:,.2f}) because:
- ANCHOR trades weekly SPX Iron Condors
- More conservative risk profile
- Provides stability to overall returns
""".strip()

        reserve_reasoning = f"""
Reserve holds {self.config.reserve_pct}% (${reserve_amount:,.2f}) because:
- Maintains margin buffer for position adjustments
- Provides liquidity for rolling positions
- Emergency fund for unexpected market events
""".strip()

        methodology = f"""
ALLOCATION METHODOLOGY: Configured Percentages

The capital is allocated based on predefined percentages that balance:
1. Return potential (FORTRESS/SAMSON for aggressive returns)
2. Risk management (ANCHOR for stability)
3. Liquidity needs (Reserve for flexibility)

Total allocated: ${total_cash:,.2f}
- FORTRESS: {self.config.fortress_allocation_pct}% = ${fortress_amount:,.2f}
- SAMSON: {self.config.samson_allocation_pct}% = ${samson_amount:,.2f}
- ANCHOR: {self.config.anchor_allocation_pct}% = ${anchor_amount:,.2f}
- Reserve: {self.config.reserve_pct}% = ${reserve_amount:,.2f}

This allocation aims to maximize premium collection while maintaining
adequate reserves for risk management.
""".strip()

        return CapitalDeployment(
            deployment_id=f"DEP-{position_id}",
            deployment_time=now,
            source_box_position_id=position_id,
            total_capital_available=total_cash,
            fortress_allocation=fortress_amount,
            fortress_allocation_pct=self.config.fortress_allocation_pct,
            fortress_allocation_reasoning=ares_reasoning,
            samson_allocation=samson_amount,
            samson_allocation_pct=self.config.samson_allocation_pct,
            samson_allocation_reasoning=titan_reasoning,
            anchor_allocation=anchor_amount,
            anchor_allocation_pct=self.config.anchor_allocation_pct,
            anchor_allocation_reasoning=anchor_reasoning,
            reserve_amount=reserve_amount,
            reserve_pct=self.config.reserve_pct,
            reserve_reasoning=reserve_reasoning,
            allocation_method="CONFIGURED_PERCENTAGES",
            methodology_explanation=methodology,
            fortress_returns_to_date=0.0,
            samson_returns_to_date=0.0,
            anchor_returns_to_date=0.0,
            total_returns_to_date=0.0,
            is_active=True,
        )

    def _generate_position_explanation(
        self,
        signal: BoxSpreadSignal,
        deployment: CapitalDeployment
    ) -> str:
        """Generate comprehensive position explanation"""
        return f"""
╔══════════════════════════════════════════════════════════════════╗
║            YOUR BOX SPREAD POSITION EXPLAINED                    ║
╚══════════════════════════════════════════════════════════════════╝

POSITION SUMMARY:
═════════════════
You have SOLD a box spread on {signal.ticker}, which means:

1. TODAY: You received ${signal.cash_received:,.2f} in your account
2. AT EXPIRATION ({signal.expiration}): You will "owe" ${signal.cash_owed_at_expiration:,.2f}
3. NET COST: ${signal.borrowing_cost:,.2f} (this is your borrowing cost)

IMPLIED BORROWING RATE: {signal.implied_annual_rate:.2f}% annually
COMPARED TO MARGIN: {signal.margin_rate:.2f}% (you save {signal.margin_rate - signal.implied_annual_rate:.2f}%)

CAPITAL DEPLOYMENT:
═══════════════════
The ${signal.cash_received:,.2f} has been deployed to generate returns:

┌──────────────────────────────────────────────────────────────────┐
│ Bot      │ Allocation │ Amount         │ Target Return          │
├──────────┼────────────┼────────────────┼────────────────────────┤
│ FORTRESS     │ {deployment.fortress_allocation_pct:>5.1f}%    │ ${deployment.fortress_allocation:>12,.2f} │ 2-4% monthly           │
│ SAMSON    │ {deployment.samson_allocation_pct:>5.1f}%    │ ${deployment.samson_allocation:>12,.2f} │ 2-4% monthly           │
│ ANCHOR  │ {deployment.anchor_allocation_pct:>5.1f}%    │ ${deployment.anchor_allocation:>12,.2f} │ 1-3% monthly           │
│ Reserve  │ {deployment.reserve_pct:>5.1f}%    │ ${deployment.reserve_amount:>12,.2f} │ Held for flexibility   │
└──────────┴────────────┴────────────────┴────────────────────────┘

PROFIT EQUATION:
════════════════
Profit = IC Bot Returns - Borrowing Cost

If IC bots return 3% monthly on ${signal.cash_received:,.2f}:
  Monthly IC returns: ${signal.cash_received * 0.03:,.2f}
  Monthly box cost: ${signal.borrowing_cost / (signal.dte / 30):,.2f}
  Monthly profit: ${signal.cash_received * 0.03 - signal.borrowing_cost / (signal.dte / 30):,.2f}

Over {signal.dte} days until expiration:
  Total IC returns (estimated): ${signal.cash_received * 0.03 * (signal.dte / 30):,.2f}
  Total box cost: ${signal.borrowing_cost:,.2f}
  Estimated net profit: ${signal.cash_received * 0.03 * (signal.dte / 30) - signal.borrowing_cost:,.2f}

RISK FACTORS:
═════════════
1. Assignment Risk: {signal.early_assignment_risk}
   {signal.assignment_risk_explanation[:200]}...

2. Margin Requirement: ${signal.margin_requirement:,.2f}
   This is {signal.margin_pct_of_capital:.1f}% of your capital

3. IC Bot Performance Risk:
   If IC bots underperform, net profit could be negative.
   Break-even requires IC returns of {signal.implied_annual_rate / 12:.2f}% monthly.

MONITORING:
═══════════
Track this position through the JUBILEE dashboard:
- Daily cost accrual updates
- IC bot return tracking
- Net profit calculations
- Roll decision recommendations
""".strip()

    def close_position(
        self,
        position: BoxSpreadPosition,
        close_reason: str = "manual"
    ) -> bool:
        """
        Close a box spread position.

        EDUCATIONAL NOTE:
        =================
        Closing a box spread involves:
        1. Buying back the call spread (debit)
        2. Buying back the put spread (debit)
        3. The cost to close = current market value of the box

        You typically close early if:
        - IC returns have been strong and you want to lock in profit
        - Assignment risk has increased
        - Better opportunities exist
        - Position needs to be rolled
        """
        logger.info(f"Closing position {position.position_id}: {close_reason}")

        if self.config.mode == TradingMode.LIVE and self.tradier:
            # LIVE mode closing not yet implemented - log warning
            logger.warning(f"LIVE mode close_position not implemented for box spread {position.position_id}")

        # Update position in database
        success = self.db.close_position(
            position.position_id,
            close_reason,
            final_ic_returns=position.total_ic_returns
        )

        if success:
            self.db.log_action(
                action="POSITION_CLOSED",
                message=f"Closed box spread position {position.position_id}",
                level="INFO",
                details={
                    'close_reason': close_reason,
                    'total_ic_returns': position.total_ic_returns,
                    'borrowing_cost': position.borrowing_cost,
                    'net_profit': position.net_profit,
                },
                position_id=position.position_id,
                log_type="BOX",
            )

        return success

    def update_position_returns(
        self,
        position_id: str,
        fortress_returns: float = 0.0,
        samson_returns: float = 0.0,
        anchor_returns: float = 0.0
    ) -> bool:
        """
        Update the returns from IC bots for a position.

        This should be called periodically to track how the deployed
        capital is performing.
        """
        position = self.db.get_position(position_id)
        if not position:
            logger.warning(f"Position {position_id} not found")
            return False

        now = datetime.now(CENTRAL_TZ)

        # Update returns
        position.returns_from_ares = fortress_returns
        position.returns_from_titan = samson_returns
        position.returns_from_pegasus = anchor_returns
        position.total_ic_returns = fortress_returns + samson_returns + anchor_returns

        # Update cost accrual with timestamp tracking
        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
        days_held = (date.today() - position.open_time.date()).days
        position.cost_accrued_to_date = position.daily_cost * days_held
        position.current_dte = (exp_date - date.today()).days

        # Calculate net profit
        position.net_profit = position.total_ic_returns - position.cost_accrued_to_date

        # Update daily briefing
        position.daily_briefing = self._generate_daily_briefing(position)

        return self.db.save_position(position)

    def get_position_mark_to_market(
        self,
        position_id: str
    ) -> Dict[str, Any]:
        """
        Get real-time mark-to-market valuation for a position.

        EDUCATIONAL NOTE:
        =================
        Mark-to-market (MTM) shows the current value of your position
        based on actual market prices. This tells you:

        1. What you'd pay to close the position NOW
        2. Your unrealized P&L (how much you'd make/lose if you closed)
        3. Current implied rate vs when you opened

        We use PRODUCTION Tradier quotes for accurate MTM even in paper mode.
        """
        position = self.db.get_position(position_id)
        if not position:
            return {'success': False, 'error': 'Position not found'}

        # Calculate MTM using real production quotes
        mtm = calculate_box_spread_mark_to_market(
            ticker=position.ticker,
            expiration=position.expiration,
            lower_strike=position.lower_strike,
            upper_strike=position.upper_strike,
            contracts=position.contracts,
            entry_credit=position.entry_credit,
            use_cache=False  # Fresh quotes for accuracy
        )

        if mtm['success']:
            # Add position context
            mtm['position_id'] = position_id
            mtm['entry_credit'] = position.entry_credit
            mtm['days_held'] = (date.today() - position.open_time.date()).days
            mtm['dte_remaining'] = position.current_dte
            mtm['cost_accrued'] = position.cost_accrued_to_date
            mtm['ic_returns'] = position.total_ic_returns
            mtm['net_position_value'] = (
                mtm['unrealized_pnl'] +
                position.total_ic_returns -
                position.cost_accrued_to_date
            )
            mtm['entry_implied_rate'] = position.implied_annual_rate

            # Rate change since entry
            if mtm.get('current_implied_rate'):
                mtm['rate_change'] = mtm['current_implied_rate'] - position.implied_annual_rate

        return mtm

    def _generate_daily_briefing(self, position: BoxSpreadPosition) -> str:
        """Generate daily briefing for a position with full timestamp transparency"""
        now = datetime.now(CENTRAL_TZ)
        days_held = (date.today() - position.open_time.date()).days

        # Get real-time MTM if available
        mtm_section = ""
        try:
            mtm = calculate_box_spread_mark_to_market(
                ticker=position.ticker,
                expiration=position.expiration,
                lower_strike=position.lower_strike,
                upper_strike=position.upper_strike,
                contracts=position.contracts,
                entry_credit=position.entry_credit,
                use_cache=True  # Use cache for briefing
            )
            if mtm['success']:
                mtm_section = f"""
MARK-TO-MARKET (Real Production Quotes):
├─ Quote time: {mtm['timestamp']}
├─ Quote source: {mtm['quote_source']}
├─ Current box mid: ${mtm['box_mid']:.4f}
├─ Entry credit: ${position.entry_credit:.4f}
├─ Unrealized P&L: ${mtm['unrealized_pnl']:,.2f}
└─ Current implied rate: {mtm.get('current_implied_rate', 'N/A')}%
"""
            else:
                mtm_section = f"""
MARK-TO-MARKET: Unavailable ({mtm.get('error', 'unknown error')})
"""
        except Exception as e:
            mtm_section = f"""
MARK-TO-MARKET: Error fetching quotes ({str(e)})
"""

        # Calculate roll schedule
        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
        roll_threshold_date = exp_date - timedelta(days=self.config.min_dte_to_hold)
        days_until_roll = (roll_threshold_date - date.today()).days

        roll_section = f"""
ROLL SCHEDULE:
├─ Expiration: {position.expiration}
├─ DTE remaining: {position.current_dte}
├─ Roll threshold: {self.config.min_dte_to_hold} days
├─ Roll trigger date: {roll_threshold_date.strftime('%Y-%m-%d')}
├─ Days until roll: {max(0, days_until_roll)}
└─ Roll status: {'ROLL NOW' if days_until_roll <= 0 else 'HOLDING' if days_until_roll > 7 else 'APPROACHING ROLL'}
"""

        # Interest accrual schedule
        daily_accrual = position.daily_cost
        total_owed = position.strike_width * 100 * position.contracts
        accrual_section = f"""
INTEREST ACCRUAL SCHEDULE:
├─ Total owed at expiration: ${total_owed:,.2f}
├─ Total credit received: ${position.total_credit_received:,.2f}
├─ Total borrowing cost: ${position.borrowing_cost:,.2f}
├─ Daily accrual rate: ${daily_accrual:,.4f}
├─ Days accrued: {days_held}
├─ Cost accrued to date: ${position.cost_accrued_to_date:,.2f}
├─ Cost remaining: ${position.borrowing_cost - position.cost_accrued_to_date:,.2f}
├─ Next accrual: Tomorrow at market open
└─ Implied annual rate: {position.implied_annual_rate:.2f}%
"""

        return f"""
╔══════════════════════════════════════════════════════════════════╗
║           DAILY BRIEFING - {date.today().strftime('%Y-%m-%d')}                         ║
║           Generated: {now.strftime('%H:%M:%S CT')}                               ║
╚══════════════════════════════════════════════════════════════════╝

Position: {position.position_id}
Opened: {position.open_time.strftime('%Y-%m-%d %H:%M:%S CT')}
Days Held: {days_held} | Days Remaining: {position.current_dte}
{mtm_section}
IC BOT RETURNS TO DATE:
├─ FORTRESS: ${position.returns_from_ares:,.2f}
├─ SAMSON: ${position.returns_from_titan:,.2f}
├─ ANCHOR: ${position.returns_from_pegasus:,.2f}
└─ TOTAL: ${position.total_ic_returns:,.2f}
{accrual_section}
{roll_section}
═══════════════════════════════════════════════════════════════════
NET PROFIT: ${position.net_profit:,.2f}
STATUS: {"✅ PROFITABLE" if position.net_profit > 0 else "⏳ TRACKING" if position.net_profit > -position.cost_accrued_to_date / 2 else "⚠️ MONITOR CLOSELY"}
═══════════════════════════════════════════════════════════════════
""".strip()

    def check_roll_decision(
        self,
        position: BoxSpreadPosition
    ) -> Dict[str, Any]:
        """
        Check if a position should be rolled to a later expiration.

        EDUCATIONAL NOTE:
        =================
        Rolling involves closing the current box spread and opening
        a new one at a later expiration. Roll when:

        1. DTE is getting low (< min_dte_to_hold)
        2. Better rates available at longer expiration
        3. Want to extend the borrowing period

        Rolling has costs (bid-ask spread on close and open), so
        only roll if the benefits outweigh the costs.

        FULL TRANSPARENCY:
        ==================
        This function provides exact timestamps for:
        - When the position will reach roll threshold
        - When it should be rolled by
        - Current market conditions for rolling
        """
        now = datetime.now(CENTRAL_TZ)
        exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
        current_dte = (exp_date - date.today()).days

        # Calculate roll timing
        roll_threshold_date = exp_date - timedelta(days=self.config.min_dte_to_hold)
        days_until_roll = (roll_threshold_date - date.today()).days
        should_roll = current_dte <= self.config.min_dte_to_hold

        reasoning = []

        if should_roll:
            reasoning.append(
                f"DTE ({current_dte}) is at or below minimum threshold ({self.config.min_dte_to_hold})"
            )
            reasoning.append(
                f"Position should be rolled immediately to avoid gamma risk"
            )
        elif days_until_roll <= 7:
            reasoning.append(
                f"Position is {days_until_roll} days away from roll threshold"
            )
            reasoning.append(
                f"Consider analyzing roll opportunities now"
            )

        # Get current rate comparison if we were to roll today
        roll_rate_analysis = None
        try:
            # Import here to avoid circular imports
            from .signals import BoxSpreadSignalGenerator
            signal_gen = BoxSpreadSignalGenerator(self.config)
            rate_analysis = signal_gen.analyze_current_rates()
            roll_rate_analysis = {
                'current_market_rate': rate_analysis.box_implied_rate,
                'position_rate': position.implied_annual_rate,
                'rate_improvement': position.implied_annual_rate - rate_analysis.box_implied_rate,
                'is_favorable_to_roll': rate_analysis.is_favorable,
            }
        except Exception as e:
            logger.debug(f"Could not get roll rate analysis: {e}")

        # Estimate roll costs (bid-ask spread on close + open)
        estimated_roll_cost = position.strike_width * 0.02 * position.contracts * 100  # ~2% of width per side

        return {
            'position_id': position.position_id,
            'decision_time': now.isoformat(),
            'should_roll': should_roll,
            'urgency': 'HIGH' if should_roll else ('MEDIUM' if days_until_roll <= 7 else 'LOW'),

            # Timing transparency
            'current_dte': current_dte,
            'expiration_date': position.expiration,
            'min_dte_threshold': self.config.min_dte_to_hold,
            'roll_threshold_date': roll_threshold_date.strftime('%Y-%m-%d'),
            'days_until_roll_threshold': max(0, days_until_roll),

            # If roll needed, when to do it
            'recommended_roll_window': {
                'earliest': (date.today() - timedelta(days=1)).strftime('%Y-%m-%d') if should_roll else roll_threshold_date.strftime('%Y-%m-%d'),
                'latest': (exp_date - timedelta(days=3)).strftime('%Y-%m-%d'),  # Roll at least 3 days before expiry
                'optimal': roll_threshold_date.strftime('%Y-%m-%d'),
            },

            # Cost analysis
            'estimated_roll_cost': estimated_roll_cost,
            'cost_already_accrued': position.cost_accrued_to_date,
            'cost_remaining_in_current': position.borrowing_cost - position.cost_accrued_to_date,

            # Rate analysis
            'rate_analysis': roll_rate_analysis,

            'reasoning': reasoning,
            'recommendation': 'ROLL IMMEDIATELY' if should_roll else (
                'PREPARE TO ROLL' if days_until_roll <= 7 else 'HOLD POSITION'
            ),

            # Educational context
            'educational_note': """
ROLL DECISION EXPLAINED:
========================
Rolling a box spread involves:
1. CLOSING current position (buy back the box at current market price)
2. OPENING new position (sell new box at later expiration)

WHY ROLL BEFORE EXPIRATION:
- Gamma risk increases as expiration approaches
- Liquidity typically decreases near expiration
- Rolling early locks in new borrowing rate

COSTS OF ROLLING:
- Bid-ask spread on close (~0.5-1% of box value)
- Bid-ask spread on open (~0.5-1% of box value)
- Total ~1-2% of position value per roll

BENEFITS OF ROLLING:
- Extended borrowing period
- Continued IC capital deployment
- Avoid expiration settlement complexity
"""
        }


# ==============================================================================
# JUBILEE IC EXECUTOR
# ==============================================================================
# Handles order placement and position management for Iron Condor trades.
# This is the "execution engine" for the IC trading side of JUBILEE.
# ==============================================================================

def get_ic_quotes(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Fetch real-time quotes for all 4 legs of an Iron Condor from Tradier PRODUCTION API.

    Returns dict with quotes, mid prices, total credit, and implied metrics.
    """
    global _quote_cache

    result = {
        'success': False,
        'quotes': {},
        'mid_prices': {},
        'put_spread_credit': None,
        'call_spread_credit': None,
        'total_credit': None,
        'quote_time': datetime.now(CENTRAL_TZ).isoformat(),
        'source': 'unknown',
        'error': None,
    }

    # Build OCC symbols for all 4 legs
    symbols = {
        'put_short': build_occ_symbol(ticker, expiration, put_short, 'put'),
        'put_long': build_occ_symbol(ticker, expiration, put_long, 'put'),
        'call_short': build_occ_symbol(ticker, expiration, call_short, 'call'),
        'call_long': build_occ_symbol(ticker, expiration, call_long, 'call'),
    }

    logger.info(f"Fetching IC quotes for {ticker} P {put_long}/{put_short} C {call_short}/{call_long} exp {expiration}")

    # Check cache first
    cached_quotes = {}
    symbols_to_fetch = []

    if use_cache:
        for leg, sym in symbols.items():
            if sym in _quote_cache:
                cache_time, cached_quote = _quote_cache[sym]
                if time.time() - cache_time < CACHE_TTL_SECONDS:
                    cached_quotes[leg] = cached_quote
                else:
                    symbols_to_fetch.append((leg, sym))
            else:
                symbols_to_fetch.append((leg, sym))
    else:
        symbols_to_fetch = [(leg, sym) for leg, sym in symbols.items()]

    if len(cached_quotes) == 4:
        result['quotes'] = cached_quotes
        result['source'] = 'cache'
    else:
        # Fetch from Tradier PRODUCTION API
        tradier = _get_production_tradier_client(ticker)

        if tradier:
            try:
                response = tradier._make_request(
                    'GET',
                    'markets/quotes',
                    params={'symbols': ','.join([symbols[leg] for leg in symbols.keys()])}
                )

                if response and 'quotes' in response:
                    quotes_data = response['quotes']
                    if 'quote' in quotes_data:
                        quote_list = quotes_data['quote']
                        if isinstance(quote_list, dict):
                            quote_list = [quote_list]

                        fetched_quotes = {}
                        for quote in quote_list:
                            quote_symbol = quote.get('symbol', '')
                            for leg, sym in symbols.items():
                                if quote_symbol.upper() == sym.upper():
                                    fetched_quotes[leg] = quote
                                    _quote_cache[sym] = (time.time(), quote)

                        result['quotes'] = {**cached_quotes, **fetched_quotes}
                        result['source'] = 'tradier_production'
                else:
                    result['error'] = "Empty response from Tradier API"
            except Exception as e:
                result['error'] = f"Tradier API error: {str(e)}"
        else:
            result['error'] = "No production Tradier client available - SPX quotes require TRADIER_API_KEY"
            result['source'] = 'unavailable'

    # Check if we have all 4 legs
    if len(result['quotes']) == 4:
        try:
            def get_mid(quote):
                bid = quote.get('bid', 0) or 0
                ask = quote.get('ask', 0) or 0
                if bid > 0 and ask > 0:
                    return (float(bid) + float(ask)) / 2
                return float(quote.get('last', 0) or 0)

            result['mid_prices'] = {leg: get_mid(quote) for leg, quote in result['quotes'].items()}

            # Calculate IC credit
            # Put spread: sell put_short, buy put_long -> receive credit
            put_spread_credit = result['mid_prices']['put_short'] - result['mid_prices']['put_long']
            # Call spread: sell call_short, buy call_long -> receive credit
            call_spread_credit = result['mid_prices']['call_short'] - result['mid_prices']['call_long']

            result['put_spread_credit'] = round(max(0, put_spread_credit), 4)
            result['call_spread_credit'] = round(max(0, call_spread_credit), 4)
            result['total_credit'] = round(result['put_spread_credit'] + result['call_spread_credit'], 4)

            result['success'] = True
            logger.info(
                f"IC quotes: put_credit={result['put_spread_credit']}, "
                f"call_credit={result['call_spread_credit']}, "
                f"total={result['total_credit']}"
            )
        except Exception as e:
            result['error'] = f"Calculation error: {str(e)}"
    else:
        missing = [leg for leg in symbols.keys() if leg not in result['quotes']]
        result['error'] = f"Missing quotes for legs: {missing}"

    return result


def calculate_ic_mark_to_market(
    ticker: str,
    expiration: str,
    put_short: float,
    put_long: float,
    call_short: float,
    call_long: float,
    contracts: int,
    entry_credit: float,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Calculate mark-to-market value for an open IC position.

    For a short IC position:
    - We received a credit when we opened
    - Current value = what we'd pay to close = sum of mid prices
    - Unrealized P&L = (entry_credit - current_close_cost) * 100 * contracts
    """
    result = {
        'success': False,
        'current_value': None,
        'unrealized_pnl': None,
        'quotes': {},
        'method': 'mark_to_market',
        'quote_source': 'unknown',
        'timestamp': datetime.now(CENTRAL_TZ).isoformat(),
        'error': None,
    }

    quote_result = get_ic_quotes(
        ticker, expiration, put_short, put_long, call_short, call_long, use_cache
    )

    if not quote_result['success']:
        result['error'] = quote_result.get('error', 'Failed to get quotes')
        result['quote_source'] = quote_result.get('source', 'failed')
        return result

    result['quotes'] = quote_result['quotes']
    result['quote_source'] = quote_result['source']

    try:
        # Current cost to close = buy back spreads at mid
        current_value = quote_result['total_credit']

        # Unrealized P&L = (credit received - cost to close) * 100 * contracts
        unrealized_pnl = (entry_credit - current_value) * 100 * contracts

        result['success'] = True
        result['current_value'] = round(current_value, 4)
        result['unrealized_pnl'] = round(unrealized_pnl, 2)
        result['put_spread_value'] = quote_result['put_spread_credit']
        result['call_spread_value'] = quote_result['call_spread_credit']

        logger.info(
            f"IC MTM: entry=${entry_credit:.4f}, current=${current_value:.4f}, "
            f"unrealized=${unrealized_pnl:.2f}"
        )
    except Exception as e:
        result['error'] = str(e)

    return result


class JubileeICExecutor:
    """
    Executes Iron Condor orders for JUBILEE.

    This handles:
    - Order placement for IC trades
    - Position mark-to-market
    - Stop loss and profit target monitoring
    - Position closing
    """

    def __init__(
        self,
        config: JubileeICConfig,
        db: JubileeDatabase
    ):
        self.config = config
        self.db = db
        self.tradier = _get_production_tradier_client(config.ticker)

    def execute_signal(
        self,
        signal: JubileeICSignal
    ) -> Optional[JubileeICPosition]:
        """
        Execute an IC signal and create a position.

        Returns the created position or None if execution fails.
        """
        if not signal.is_valid:
            logger.warning(f"Cannot execute invalid signal: {signal.skip_reason}")
            return None

        now = datetime.now(CENTRAL_TZ)
        position_id = f"PROM-IC-{now.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

        # Build option symbols
        symbols = self._build_option_symbols(signal)

        logger.info(f"Executing IC signal {signal.signal_id}")
        logger.info(f"  Put spread: {signal.put_long_strike}/{signal.put_short_strike}")
        logger.info(f"  Call spread: {signal.call_short_strike}/{signal.call_long_strike}")
        logger.info(f"  Contracts: {signal.contracts}")

        # Execute orders
        if self.config.mode == TradingMode.LIVE and self.tradier:
            put_order = self._execute_put_spread(signal, symbols)
            call_order = self._execute_call_spread(signal, symbols)

            if not put_order or not call_order:
                logger.error("Failed to execute one or both spread orders")
                return None

            put_order_id = put_order.get('id', 'LIVE-PUT')
            call_order_id = call_order.get('id', 'LIVE-CALL')
        else:
            # Paper trading — same pattern as SAMSON executor:
            # Signal generator already fetched real Tradier quotes and set credits.
            # Try to refresh with latest quotes, but use signal's Tradier credits
            # if the executor's fetch fails (signal already has real pricing).
            put_order_id = f"PAPER-PUT-{uuid.uuid4().hex[:8]}"
            call_order_id = f"PAPER-CALL-{uuid.uuid4().hex[:8]}"

            real_quotes = get_ic_quotes(
                signal.ticker,
                signal.expiration,
                signal.put_short_strike,
                signal.put_long_strike,
                signal.call_short_strike,
                signal.call_long_strike,
                use_cache=False
            )

            if real_quotes['success']:
                signal.put_spread_credit = real_quotes['put_spread_credit']
                signal.call_spread_credit = real_quotes['call_spread_credit']
                signal.total_credit = real_quotes['total_credit']
                logger.info(
                    f"JUBILEE IC PAPER: Using FRESH Tradier quotes: credit=${real_quotes['total_credit']:.4f}"
                )
            else:
                # Executor refresh failed — use signal's Tradier credits from generator.
                # SAMSON executor does the same: uses signal credits directly without re-fetch.
                logger.warning(
                    f"JUBILEE IC PAPER: Executor quote refresh failed ({real_quotes.get('error')}). "
                    f"Using signal's Tradier credits: ${signal.total_credit:.4f} "
                    f"(put=${signal.put_spread_credit:.4f}, call=${signal.call_spread_credit:.4f})"
                )

        # Calculate totals
        total_credit_received = signal.total_credit * signal.contracts * 100
        max_loss = (signal.put_spread_width - signal.total_credit) * signal.contracts * 100

        # Create position object
        position = JubileeICPosition(
            position_id=position_id,
            source_box_position_id=signal.source_box_position_id,
            ticker=signal.ticker,
            put_short_strike=signal.put_short_strike,
            put_long_strike=signal.put_long_strike,
            call_short_strike=signal.call_short_strike,
            call_long_strike=signal.call_long_strike,
            spread_width=signal.put_spread_width,
            put_short_symbol=symbols['put_short'],
            put_long_symbol=symbols['put_long'],
            call_short_symbol=symbols['call_short'],
            call_long_symbol=symbols['call_long'],
            put_spread_order_id=put_order_id,
            call_spread_order_id=call_order_id,
            expiration=signal.expiration,
            dte_at_entry=signal.dte,
            current_dte=signal.dte,
            contracts=signal.contracts,
            entry_credit=signal.total_credit,
            total_credit_received=total_credit_received,
            max_loss=max_loss,
            current_value=signal.total_credit,
            unrealized_pnl=0.0,
            spot_at_entry=signal.spot_price,
            vix_at_entry=signal.vix_level,
            gamma_regime_at_entry=signal.gamma_regime,
            oracle_confidence_at_entry=signal.oracle_confidence,
            oracle_reasoning=signal.oracle_reasoning,
            status=ICPositionStatus.OPEN,
            open_time=now,
            stop_loss_pct=self.config.stop_loss_pct,
            profit_target_pct=self.config.profit_target_pct,
            time_stop_dte=self.config.time_stop_dte,
        )

        # Save position
        if self.db.save_ic_position(position):
            logger.info(f"IC Position {position_id} saved successfully")

            # Log the signal
            self.db.log_ic_signal(signal, was_executed=True, executed_position_id=position_id)

            # Log the action
            self.db.log_action(
                action="IC_POSITION_OPENED",
                message=f"Opened IC position {position_id}",
                level="INFO",
                details={
                    'signal_id': signal.signal_id,
                    'put_spread': f"{signal.put_long_strike}/{signal.put_short_strike}",
                    'call_spread': f"{signal.call_short_strike}/{signal.call_long_strike}",
                    'total_credit': signal.total_credit,
                    'contracts': signal.contracts,
                    'oracle_confidence': signal.oracle_confidence,
                },
                position_id=position_id,
                signal_id=signal.signal_id,
                log_type="IC",
            )

            return position
        else:
            logger.error(f"Failed to save IC position {position_id}")
            return None

    def _build_option_symbols(self, signal: JubileeICSignal) -> Dict[str, str]:
        """Build OCC symbols for all 4 IC legs"""
        return {
            'put_short': build_occ_symbol(signal.ticker, signal.expiration, signal.put_short_strike, 'put'),
            'put_long': build_occ_symbol(signal.ticker, signal.expiration, signal.put_long_strike, 'put'),
            'call_short': build_occ_symbol(signal.ticker, signal.expiration, signal.call_short_strike, 'call'),
            'call_long': build_occ_symbol(signal.ticker, signal.expiration, signal.call_long_strike, 'call'),
        }

    def _execute_put_spread(
        self,
        signal: JubileeICSignal,
        symbols: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Execute the put spread leg (sell put_short, buy put_long for credit)"""
        if not self.tradier:
            return {'id': 'PAPER-PUT', 'status': 'filled'}

        try:
            # Use Tradier's place_vertical_spread with correct indexed-key format
            result = self.tradier.place_vertical_spread(
                symbol=signal.ticker,
                expiration=signal.expiration,
                long_strike=signal.put_long_strike,    # Buy protection put
                short_strike=signal.put_short_strike,   # Sell short put
                option_type="put",
                quantity=signal.contracts,
                limit_price=round(signal.put_spread_credit, 2),
            )
            return result
        except Exception as e:
            logger.error(f"Error executing put spread: {e}")
            return None

    def _execute_call_spread(
        self,
        signal: JubileeICSignal,
        symbols: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Execute the call spread leg (sell call_short, buy call_long for credit)"""
        if not self.tradier:
            return {'id': 'PAPER-CALL', 'status': 'filled'}

        try:
            # Use Tradier's place_vertical_spread with correct indexed-key format
            result = self.tradier.place_vertical_spread(
                symbol=signal.ticker,
                expiration=signal.expiration,
                long_strike=signal.call_long_strike,    # Buy protection call
                short_strike=signal.call_short_strike,   # Sell short call
                option_type="call",
                quantity=signal.contracts,
                limit_price=round(signal.call_spread_credit, 2),
            )
            return result
        except Exception as e:
            logger.error(f"Error executing call spread: {e}")
            return None

    def update_position_mtm(self, position_id: str) -> Optional[JubileeICPosition]:
        """Update mark-to-market for a position"""
        position = self.db.get_ic_position(position_id)
        if not position:
            return None

        mtm = calculate_ic_mark_to_market(
            ticker=position.ticker,
            expiration=position.expiration,
            put_short=position.put_short_strike,
            put_long=position.put_long_strike,
            call_short=position.call_short_strike,
            call_long=position.call_long_strike,
            contracts=position.contracts,
            entry_credit=position.entry_credit,
            use_cache=False
        )

        if mtm['success']:
            position.current_value = mtm['current_value']
            position.unrealized_pnl = mtm['unrealized_pnl']

            # Update DTE
            exp_date = datetime.strptime(position.expiration, '%Y-%m-%d').date()
            position.current_dte = (exp_date - date.today()).days

            self.db.save_ic_position(position)

        return position

    def check_exit_conditions(
        self,
        position: JubileeICPosition
    ) -> Tuple[bool, str]:
        """
        Check if position should be closed based on exit conditions.

        Returns (should_close, reason)
        """
        # Update MTM first
        self.update_position_mtm(position.position_id)
        position = self.db.get_ic_position(position.position_id)

        if not position:
            return False, "Position not found"

        # Check profit target
        if position.unrealized_pnl >= position.total_credit_received * (position.profit_target_pct / 100):
            return True, f"Profit target reached ({position.profit_target_pct}%)"

        # Check stop loss
        max_loss_threshold = position.max_loss * (position.stop_loss_pct / 100)
        if position.unrealized_pnl <= -max_loss_threshold:
            return True, f"Stop loss triggered ({position.stop_loss_pct}% of max loss)"

        # Check time stop
        if position.current_dte <= position.time_stop_dte:
            return True, f"Time stop reached ({position.current_dte} DTE <= {position.time_stop_dte})"

        # Check expiration
        if position.current_dte <= 0:
            return True, "Position at expiration"

        return False, ""

    def close_position(
        self,
        position_id: str,
        close_reason: str = "manual"
    ) -> bool:
        """Close an IC position"""
        position = self.db.get_ic_position(position_id)
        if not position:
            logger.warning(f"IC position {position_id} not found")
            return False

        logger.info(f"Closing IC position {position_id}: {close_reason}")

        # Get current price for exit
        mtm = calculate_ic_mark_to_market(
            ticker=position.ticker,
            expiration=position.expiration,
            put_short=position.put_short_strike,
            put_long=position.put_long_strike,
            call_short=position.call_short_strike,
            call_long=position.call_long_strike,
            contracts=position.contracts,
            entry_credit=position.entry_credit,
            use_cache=False
        )

        exit_price = mtm.get('current_value', position.entry_credit) if mtm['success'] else position.entry_credit
        realized_pnl = (position.entry_credit - exit_price) * position.contracts * 100

        # Execute closing orders in live mode (matching SAMSON pattern)
        if self.config.mode == TradingMode.LIVE and self.tradier:
            try:
                # Close put spread: buy back short put, sell long put (debit)
                put_result = self.tradier.place_vertical_spread(
                    symbol=position.ticker,
                    expiration=position.expiration,
                    long_strike=position.put_short_strike,   # Buy back the short
                    short_strike=position.put_long_strike,    # Sell the long
                    option_type="put",
                    quantity=position.contracts,
                    limit_price=round(exit_price / 2, 2),
                )
                if not put_result or not put_result.get('id'):
                    logger.error(f"Failed to close IC put spread via Tradier: {put_result}")

                # Close call spread: buy back short call, sell long call (debit)
                call_result = self.tradier.place_vertical_spread(
                    symbol=position.ticker,
                    expiration=position.expiration,
                    long_strike=position.call_short_strike,   # Buy back the short
                    short_strike=position.call_long_strike,    # Sell the long
                    option_type="call",
                    quantity=position.contracts,
                    limit_price=round(exit_price / 2, 2),
                )
                if not call_result or not call_result.get('id'):
                    logger.error(f"Failed to close IC call spread via Tradier: {call_result}")

                logger.info(f"JUBILEE IC LIVE CLOSE: {position_id} via Tradier, exit=${exit_price:.4f}")
            except Exception as e:
                logger.error(f"Failed to close IC position via Tradier: {e}")

        # Close in database
        success = self.db.close_ic_position(position_id, exit_price, close_reason)

        # Log the close action for Activity Log
        if success:
            self.db.log_action(
                action="IC_POSITION_CLOSED",
                message=f"Closed IC position {position_id}: {close_reason}",
                level="INFO",
                details={
                    'entry_credit': position.entry_credit,
                    'exit_price': exit_price,
                    'realized_pnl': realized_pnl,
                    'contracts': position.contracts,
                    'close_reason': close_reason,
                    'put_spread': f"{position.put_long_strike}/{position.put_short_strike}",
                    'call_spread': f"{position.call_short_strike}/{position.call_long_strike}",
                },
                position_id=position_id,
                log_type="IC",
            )

        # Record outcome to auto-validation system (which also notifies Proverbs)
        if success:
            try:
                from quant.auto_validation_system import record_bot_outcome
                record_bot_outcome('JUBILEE', win=(realized_pnl > 0), pnl=realized_pnl)
                logger.info(f"[JUBILEE] Trade outcome recorded: ${realized_pnl:+,.2f}")
            except Exception as e:
                logger.debug(f"[JUBILEE] Could not record outcome: {e}")

        return success
