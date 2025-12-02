"""
Tradier API Data Fetcher and Trading Execution

Provides real-time options data, Greeks, and trade execution via Tradier API.
This replaces paper trading with actual market execution when TRADIER_SANDBOX=false.

API Documentation: https://documentation.tradier.com/
"""

import os
import json
import asyncio
import aiohttp
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class OrderSide(Enum):
    BUY_TO_OPEN = "buy_to_open"
    BUY_TO_CLOSE = "buy_to_close"
    SELL_TO_OPEN = "sell_to_open"
    SELL_TO_CLOSE = "sell_to_close"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderDuration(Enum):
    DAY = "day"
    GTC = "gtc"  # Good till canceled
    PRE = "pre"  # Pre-market
    POST = "post"  # Post-market


@dataclass
class OptionContract:
    """Single option contract with Greeks"""
    symbol: str  # OCC symbol like SPXW240126C04800000
    underlying: str
    strike: float
    expiration: str  # YYYY-MM-DD
    option_type: str  # 'call' or 'put'

    # Pricing
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    mid: float = 0.0
    volume: int = 0
    open_interest: int = 0

    # Greeks
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    implied_volatility: float = 0.0

    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class OptionChain:
    """Full options chain for an underlying"""
    underlying: str
    underlying_price: float
    chains: Dict[str, List[OptionContract]] = field(default_factory=dict)  # expiration -> contracts
    last_updated: datetime = field(default_factory=datetime.now)

    @property
    def symbol(self) -> str:
        """Alias for underlying for backward compatibility"""
        return self.underlying


@dataclass
class AccountPosition:
    """Current position in account"""
    symbol: str
    quantity: int
    cost_basis: float
    current_price: float
    gain_loss: float
    gain_loss_pct: float


@dataclass
class Order:
    """Order information"""
    order_id: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    status: str
    filled_quantity: int = 0
    avg_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)


class TradierDataFetcher:
    """
    Tradier API client for options data and trading execution.

    Supports both sandbox (paper) and production (live) trading.
    """

    # API endpoints
    SANDBOX_BASE = "https://sandbox.tradier.com/v1"
    PRODUCTION_BASE = "https://api.tradier.com/v1"

    # Streaming endpoints
    SANDBOX_STREAM = "https://sandbox.tradier.com/v1/markets/events/session"
    PRODUCTION_STREAM = "https://api.tradier.com/v1/markets/events/session"

    def __init__(
        self,
        api_key: Optional[str] = None,
        account_id: Optional[str] = None,
        sandbox: Optional[bool] = None
    ):
        """
        Initialize Tradier client.

        Args:
            api_key: Tradier API key (falls back to env var)
            account_id: Tradier account ID (falls back to env var)
            sandbox: If True, use sandbox/paper trading. If False, live trading. None = read from env.
        """
        # Import from centralized config
        try:
            from unified_config import APIConfig
            self.api_key = api_key or APIConfig.TRADIER_API_KEY
            self.account_id = account_id or APIConfig.TRADIER_ACCOUNT_ID
            default_sandbox = APIConfig.TRADIER_SANDBOX
        except ImportError:
            self.api_key = api_key or os.getenv('TRADIER_API_KEY')
            self.account_id = account_id or os.getenv('TRADIER_ACCOUNT_ID')
            default_sandbox = os.getenv('TRADIER_SANDBOX', 'true').lower() == 'true'

        # Check sandbox setting from env if not explicitly set
        if sandbox is not None:
            self.sandbox = sandbox
        else:
            self.sandbox = default_sandbox

        if not self.api_key:
            raise ValueError("TRADIER_API_KEY is required. Set in .env or pass directly.")

        if not self.account_id:
            raise ValueError("TRADIER_ACCOUNT_ID is required. Set in .env or pass directly.")

        self.base_url = self.SANDBOX_BASE if self.sandbox else self.PRODUCTION_BASE
        self.stream_url = self.SANDBOX_STREAM if self.sandbox else self.PRODUCTION_STREAM

        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Accept': 'application/json'
        }

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

        logger.info(f"Tradier client initialized - Mode: {'SANDBOX' if self.sandbox else 'PRODUCTION'}")
        if not self.sandbox:
            logger.warning("⚠️ LIVE TRADING MODE - Real money at risk!")

    def _rate_limit(self):
        """Simple rate limiting"""
        import time
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        max_retries: int = 3
    ) -> Dict:
        """Make API request with retry logic and exponential backoff"""
        import time
        self._rate_limit()

        url = f"{self.base_url}/{endpoint}"
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=self.headers, params=params, timeout=30)
                elif method.upper() == 'POST':
                    response = requests.post(url, headers=self.headers, params=params, data=data, timeout=30)
                elif method.upper() == 'DELETE':
                    response = requests.delete(url, headers=self.headers, params=params, timeout=30)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                response.raise_for_status()
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON response from {endpoint}: {e}")
                    logger.debug(f"Response text: {response.text[:500]}")
                    raise ValueError(f"Tradier API returned invalid JSON: {e}")

            except requests.exceptions.HTTPError as e:
                # Don't retry client errors (4xx), only server errors (5xx)
                if e.response.status_code < 500:
                    logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
                    raise
                last_exception = e
                logger.warning(f"Server error (attempt {attempt + 1}/{max_retries + 1}): {e.response.status_code}")

            except (requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.ChunkedEncodingError) as e:
                last_exception = e
                logger.warning(f"Network error (attempt {attempt + 1}/{max_retries + 1}): {e}")

            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                raise

            # Exponential backoff: 1s, 2s, 4s
            if attempt < max_retries:
                backoff_time = 2 ** attempt
                logger.info(f"Retrying in {backoff_time}s...")
                time.sleep(backoff_time)

        # All retries exhausted
        logger.error(f"All {max_retries + 1} attempts failed for {endpoint}")
        if last_exception:
            raise last_exception
        raise requests.exceptions.RequestException(f"Request to {endpoint} failed after {max_retries + 1} attempts")

    # ==================== MARKET DATA ====================

    def get_quote(self, symbol: str) -> Dict:
        """
        Get real-time quote for a symbol.

        Args:
            symbol: Stock symbol (SPY, SPX) or option OCC symbol

        Returns:
            Quote data including bid, ask, last, volume
        """
        response = self._make_request('GET', 'markets/quotes', params={'symbols': symbol})
        quotes = response.get('quotes', {})

        if 'quote' in quotes:
            quote_data = quotes['quote']
            # Handle single quote (not list)
            if isinstance(quote_data, dict):
                return quote_data
            elif isinstance(quote_data, list):
                return quote_data[0] if quote_data else {}

        return {}

    def get_option_expirations(self, symbol: str) -> List[str]:
        """
        Get available option expiration dates for underlying.

        Args:
            symbol: Underlying symbol (SPY, SPX)

        Returns:
            List of expiration dates in YYYY-MM-DD format
        """
        response = self._make_request('GET', 'markets/options/expirations', params={'symbol': symbol})
        expirations = response.get('expirations', {})

        date_list = expirations.get('date', [])
        if isinstance(date_list, str):
            return [date_list]
        return date_list or []

    def get_option_chain(
        self,
        symbol: str,
        expiration: Optional[str] = None,
        greeks: bool = True
    ) -> OptionChain:
        """
        Get full options chain with Greeks.

        Args:
            symbol: Underlying symbol (SPY, SPX)
            expiration: Specific expiration (YYYY-MM-DD) or None for nearest
            greeks: Include Greeks in response

        Returns:
            OptionChain with all contracts
        """
        # Get underlying price first
        quote = self.get_quote(symbol)
        underlying_price = quote.get('last', 0) or quote.get('close', 0)

        # Get expiration if not specified
        if not expiration:
            expirations = self.get_option_expirations(symbol)
            if not expirations:
                logger.error(f"No expirations found for {symbol}")
                return OptionChain(underlying=symbol, underlying_price=underlying_price)
            expiration = expirations[0]

        params = {
            'symbol': symbol,
            'expiration': expiration,
            'greeks': 'true' if greeks else 'false'
        }

        response = self._make_request('GET', 'markets/options/chains', params=params)
        options_data = response.get('options', {})
        option_list = options_data.get('option', [])

        if isinstance(option_list, dict):
            option_list = [option_list]

        contracts = []
        for opt in option_list:
            greeks_data = opt.get('greeks', {}) or {}

            contract = OptionContract(
                symbol=opt.get('symbol', ''),
                underlying=symbol,
                strike=float(opt.get('strike', 0)),
                expiration=expiration,
                option_type=opt.get('option_type', 'call'),
                bid=float(opt.get('bid', 0) or 0),
                ask=float(opt.get('ask', 0) or 0),
                last=float(opt.get('last', 0) or 0),
                mid=(float(opt.get('bid', 0) or 0) + float(opt.get('ask', 0) or 0)) / 2,
                volume=int(opt.get('volume', 0) or 0),
                open_interest=int(opt.get('open_interest', 0) or 0),
                delta=float(greeks_data.get('delta', 0) or 0),
                gamma=float(greeks_data.get('gamma', 0) or 0),
                theta=float(greeks_data.get('theta', 0) or 0),
                vega=float(greeks_data.get('vega', 0) or 0),
                rho=float(greeks_data.get('rho', 0) or 0),
                implied_volatility=float(greeks_data.get('mid_iv', 0) or 0)
            )
            contracts.append(contract)

        chain = OptionChain(
            underlying=symbol,
            underlying_price=underlying_price,
            chains={expiration: contracts},
            last_updated=datetime.now()
        )

        logger.info(f"Fetched {len(contracts)} contracts for {symbol} exp {expiration}")
        return chain

    def get_multiple_chains(
        self,
        symbol: str,
        num_expirations: int = 4,
        greeks: bool = True
    ) -> OptionChain:
        """
        Get options chains for multiple expirations.

        Args:
            symbol: Underlying symbol
            num_expirations: Number of nearest expirations to fetch
            greeks: Include Greeks

        Returns:
            OptionChain with multiple expiration chains
        """
        expirations = self.get_option_expirations(symbol)[:num_expirations]

        quote = self.get_quote(symbol)
        underlying_price = quote.get('last', 0) or quote.get('close', 0)

        all_chains = {}
        for exp in expirations:
            chain = self.get_option_chain(symbol, exp, greeks)
            if exp in chain.chains:
                all_chains[exp] = chain.chains[exp]

        return OptionChain(
            underlying=symbol,
            underlying_price=underlying_price,
            chains=all_chains,
            last_updated=datetime.now()
        )

    def find_atm_options(
        self,
        symbol: str,
        expiration: Optional[str] = None,
        option_type: str = 'call'
    ) -> Optional[OptionContract]:
        """
        Find the at-the-money option for given parameters.

        Args:
            symbol: Underlying symbol
            expiration: Expiration date
            option_type: 'call' or 'put'

        Returns:
            ATM OptionContract or None
        """
        chain = self.get_option_chain(symbol, expiration)

        if not chain.chains:
            return None

        contracts = list(chain.chains.values())[0]
        underlying = chain.underlying_price

        # Filter by type and find closest strike
        typed_contracts = [c for c in contracts if c.option_type == option_type]
        if not typed_contracts:
            return None

        atm = min(typed_contracts, key=lambda c: abs(c.strike - underlying))
        return atm

    def find_delta_option(
        self,
        symbol: str,
        target_delta: float,
        expiration: Optional[str] = None,
        option_type: str = 'call'
    ) -> Optional[OptionContract]:
        """
        Find option closest to target delta.

        Args:
            symbol: Underlying symbol
            target_delta: Target delta (e.g., 0.30 for 30 delta)
            expiration: Expiration date
            option_type: 'call' or 'put'

        Returns:
            OptionContract closest to target delta
        """
        chain = self.get_option_chain(symbol, expiration, greeks=True)

        if not chain.chains:
            return None

        contracts = list(chain.chains.values())[0]

        # Filter by type
        typed_contracts = [c for c in contracts if c.option_type == option_type]
        if not typed_contracts:
            return None

        # For puts, delta is negative, so we compare absolute values
        if option_type == 'put':
            closest = min(typed_contracts, key=lambda c: abs(abs(c.delta) - target_delta))
        else:
            closest = min(typed_contracts, key=lambda c: abs(c.delta - target_delta))

        return closest

    # ==================== ACCOUNT & POSITIONS ====================

    def get_account_balance(self) -> Dict:
        """Get account balance and buying power"""
        response = self._make_request('GET', f'accounts/{self.account_id}/balances')
        return response.get('balances', {})

    def get_positions(self) -> List[AccountPosition]:
        """Get current positions"""
        response = self._make_request('GET', f'accounts/{self.account_id}/positions')
        positions_data = response.get('positions', {})

        if positions_data == 'null' or not positions_data:
            return []

        position_list = positions_data.get('position', [])
        if isinstance(position_list, dict):
            position_list = [position_list]

        positions = []
        for pos in position_list:
            positions.append(AccountPosition(
                symbol=pos.get('symbol', ''),
                quantity=int(pos.get('quantity', 0)),
                cost_basis=float(pos.get('cost_basis', 0)),
                current_price=float(pos.get('last', 0) or 0),
                gain_loss=float(pos.get('gain_loss', 0) or 0),
                gain_loss_pct=float(pos.get('gain_loss_percent', 0) or 0)
            ))

        return positions

    def get_orders(self, status: str = 'open') -> List[Order]:
        """
        Get orders for account.

        Args:
            status: 'open', 'pending', 'filled', 'all'
        """
        response = self._make_request('GET', f'accounts/{self.account_id}/orders')
        orders_data = response.get('orders', {})

        if orders_data == 'null' or not orders_data:
            return []

        order_list = orders_data.get('order', [])
        if isinstance(order_list, dict):
            order_list = [order_list]

        orders = []
        for ord in order_list:
            if status != 'all' and ord.get('status', '') != status:
                continue

            orders.append(Order(
                order_id=str(ord.get('id', '')),
                symbol=ord.get('symbol', ''),
                side=ord.get('side', ''),
                quantity=int(ord.get('quantity', 0)),
                order_type=ord.get('type', ''),
                status=ord.get('status', ''),
                filled_quantity=int(ord.get('exec_quantity', 0) or 0),
                avg_fill_price=float(ord.get('avg_fill_price', 0) or 0)
            ))

        return orders

    # ==================== ORDER EXECUTION ====================

    def place_option_order(
        self,
        option_symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType = OrderType.LIMIT,
        price: Optional[float] = None,
        duration: OrderDuration = OrderDuration.DAY,
        stop_price: Optional[float] = None
    ) -> Dict:
        """
        Place an options order.

        Args:
            option_symbol: OCC option symbol
            side: buy_to_open, sell_to_open, etc.
            quantity: Number of contracts
            order_type: market, limit, stop, stop_limit
            price: Limit price (required for limit orders)
            duration: day, gtc, pre, post
            stop_price: Stop trigger price (for stop orders)

        Returns:
            Order response with order ID
        """
        data = {
            'class': 'option',
            'symbol': option_symbol.split('_')[0] if '_' in option_symbol else option_symbol[:3],  # Underlying
            'option_symbol': option_symbol,
            'side': side.value,
            'quantity': str(quantity),
            'type': order_type.value,
            'duration': duration.value
        }

        if order_type in [OrderType.LIMIT, OrderType.STOP_LIMIT]:
            if price is None:
                raise ValueError("Limit price required for limit orders")
            data['price'] = str(price)

        if order_type in [OrderType.STOP, OrderType.STOP_LIMIT]:
            if stop_price is None:
                raise ValueError("Stop price required for stop orders")
            data['stop'] = str(stop_price)

        logger.info(f"Placing order: {side.value} {quantity}x {option_symbol} @ {price or 'MARKET'}")

        if not self.sandbox:
            logger.warning(f"⚠️ LIVE ORDER: {side.value} {quantity}x {option_symbol}")

        response = self._make_request('POST', f'accounts/{self.account_id}/orders', data=data)

        order_info = response.get('order', {})
        if order_info:
            logger.info(f"Order placed - ID: {order_info.get('id')}, Status: {order_info.get('status')}")

        return response

    def place_equity_order(
        self,
        symbol: str,
        side: str,  # 'buy' or 'sell'
        quantity: int,
        order_type: OrderType = OrderType.LIMIT,
        price: Optional[float] = None,
        duration: OrderDuration = OrderDuration.DAY
    ) -> Dict:
        """
        Place an equity (stock/ETF) order.

        Args:
            symbol: Stock symbol (SPY, QQQ, etc.)
            side: 'buy' or 'sell'
            quantity: Number of shares
            order_type: market, limit, etc.
            price: Limit price
            duration: day, gtc, etc.
        """
        data = {
            'class': 'equity',
            'symbol': symbol,
            'side': side,
            'quantity': str(quantity),
            'type': order_type.value,
            'duration': duration.value
        }

        if order_type == OrderType.LIMIT and price:
            data['price'] = str(price)

        return self._make_request('POST', f'accounts/{self.account_id}/orders', data=data)

    def cancel_order(self, order_id: str) -> Dict:
        """Cancel an open order"""
        return self._make_request('DELETE', f'accounts/{self.account_id}/orders/{order_id}')

    def modify_order(
        self,
        order_id: str,
        order_type: Optional[OrderType] = None,
        price: Optional[float] = None,
        duration: Optional[OrderDuration] = None
    ) -> Dict:
        """Modify an existing order"""
        data = {}
        if order_type:
            data['type'] = order_type.value
        if price:
            data['price'] = str(price)
        if duration:
            data['duration'] = duration.value

        return self._make_request('PUT', f'accounts/{self.account_id}/orders/{order_id}', data=data)

    # ==================== CONVENIENCE METHODS ====================

    def buy_call(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """
        Buy call options with simple parameters.

        Args:
            symbol: Underlying (SPY, SPX)
            expiration: YYYY-MM-DD
            strike: Strike price
            quantity: Number of contracts
            limit_price: Limit price (uses mid if None)
        """
        # Build OCC symbol
        option_symbol = self._build_occ_symbol(symbol, expiration, strike, 'C')

        # Get current pricing if no limit specified
        if limit_price is None:
            quote = self.get_quote(option_symbol)
            bid = float(quote.get('bid', 0) or 0)
            ask = float(quote.get('ask', 0) or 0)
            limit_price = round((bid + ask) / 2, 2)

        return self.place_option_order(
            option_symbol=option_symbol,
            side=OrderSide.BUY_TO_OPEN,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=limit_price
        )

    def buy_put(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Buy put options"""
        option_symbol = self._build_occ_symbol(symbol, expiration, strike, 'P')

        if limit_price is None:
            quote = self.get_quote(option_symbol)
            bid = float(quote.get('bid', 0) or 0)
            ask = float(quote.get('ask', 0) or 0)
            limit_price = round((bid + ask) / 2, 2)

        return self.place_option_order(
            option_symbol=option_symbol,
            side=OrderSide.BUY_TO_OPEN,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=limit_price
        )

    def sell_call(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Sell call options (short)"""
        option_symbol = self._build_occ_symbol(symbol, expiration, strike, 'C')

        if limit_price is None:
            quote = self.get_quote(option_symbol)
            bid = float(quote.get('bid', 0) or 0)
            ask = float(quote.get('ask', 0) or 0)
            limit_price = round((bid + ask) / 2, 2)

        return self.place_option_order(
            option_symbol=option_symbol,
            side=OrderSide.SELL_TO_OPEN,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=limit_price
        )

    def sell_put(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """Sell put options (short)"""
        option_symbol = self._build_occ_symbol(symbol, expiration, strike, 'P')

        if limit_price is None:
            quote = self.get_quote(option_symbol)
            bid = float(quote.get('bid', 0) or 0)
            ask = float(quote.get('ask', 0) or 0)
            limit_price = round((bid + ask) / 2, 2)

        return self.place_option_order(
            option_symbol=option_symbol,
            side=OrderSide.SELL_TO_OPEN,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=limit_price
        )

    def close_position(
        self,
        option_symbol: str,
        quantity: int,
        limit_price: Optional[float] = None
    ) -> Dict:
        """
        Close an existing position.

        Determines if long or short based on current positions.
        """
        positions = self.get_positions()
        position = next((p for p in positions if p.symbol == option_symbol), None)

        if not position:
            raise ValueError(f"No position found for {option_symbol}")

        if position.quantity > 0:
            # Long position, sell to close
            side = OrderSide.SELL_TO_CLOSE
        else:
            # Short position, buy to close
            side = OrderSide.BUY_TO_CLOSE
            quantity = abs(quantity)

        if limit_price is None:
            quote = self.get_quote(option_symbol)
            bid = float(quote.get('bid', 0) or 0)
            ask = float(quote.get('ask', 0) or 0)
            limit_price = round((bid + ask) / 2, 2)

        return self.place_option_order(
            option_symbol=option_symbol,
            side=side,
            quantity=quantity,
            order_type=OrderType.LIMIT,
            price=limit_price
        )

    def _build_occ_symbol(
        self,
        underlying: str,
        expiration: str,
        strike: float,
        option_type: str  # 'C' or 'P'
    ) -> str:
        """
        Build OCC option symbol.

        Format: ROOT + YYMMDD + C/P + Strike*1000 (8 digits)
        Example: SPY240126C00500000 for SPY $500 call exp 1/26/24
        """
        # Parse expiration
        exp_date = datetime.strptime(expiration, '%Y-%m-%d')
        exp_str = exp_date.strftime('%y%m%d')

        # Format strike (multiply by 1000, pad to 8 digits)
        strike_str = f"{int(strike * 1000):08d}"

        # Build symbol
        root = underlying.upper()
        if root == 'SPX':
            root = 'SPXW'  # Weekly SPX options

        return f"{root}{exp_str}{option_type}{strike_str}"

    # ==================== SPREAD ORDERS ====================

    def place_vertical_spread(
        self,
        symbol: str,
        expiration: str,
        long_strike: float,
        short_strike: float,
        option_type: str,  # 'call' or 'put'
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """
        Place a vertical spread (bull/bear call/put spread).

        Args:
            symbol: Underlying
            expiration: YYYY-MM-DD
            long_strike: Strike to buy
            short_strike: Strike to sell
            option_type: 'call' or 'put'
            quantity: Number of spreads
            limit_price: Net debit/credit limit
        """
        opt_char = 'C' if option_type == 'call' else 'P'
        long_symbol = self._build_occ_symbol(symbol, expiration, long_strike, opt_char)
        short_symbol = self._build_occ_symbol(symbol, expiration, short_strike, opt_char)

        data = {
            'class': 'multileg',
            'symbol': symbol,
            'type': 'limit' if limit_price else 'market',
            'duration': 'day',
            'side[0]': 'buy_to_open',
            'quantity[0]': str(quantity),
            'option_symbol[0]': long_symbol,
            'side[1]': 'sell_to_open',
            'quantity[1]': str(quantity),
            'option_symbol[1]': short_symbol
        }

        if limit_price:
            data['price'] = str(limit_price)

        return self._make_request('POST', f'accounts/{self.account_id}/orders', data=data)

    def place_iron_condor(
        self,
        symbol: str,
        expiration: str,
        put_long: float,
        put_short: float,
        call_short: float,
        call_long: float,
        quantity: int = 1,
        limit_price: Optional[float] = None
    ) -> Dict:
        """
        Place an iron condor.

        Args:
            symbol: Underlying
            expiration: YYYY-MM-DD
            put_long: Long put strike (lowest)
            put_short: Short put strike
            call_short: Short call strike
            call_long: Long call strike (highest)
            quantity: Number of condors
            limit_price: Net credit limit
        """
        put_long_sym = self._build_occ_symbol(symbol, expiration, put_long, 'P')
        put_short_sym = self._build_occ_symbol(symbol, expiration, put_short, 'P')
        call_short_sym = self._build_occ_symbol(symbol, expiration, call_short, 'C')
        call_long_sym = self._build_occ_symbol(symbol, expiration, call_long, 'C')

        data = {
            'class': 'multileg',
            'symbol': symbol,
            'type': 'limit' if limit_price else 'market',
            'duration': 'day',
            'side[0]': 'buy_to_open',
            'quantity[0]': str(quantity),
            'option_symbol[0]': put_long_sym,
            'side[1]': 'sell_to_open',
            'quantity[1]': str(quantity),
            'option_symbol[1]': put_short_sym,
            'side[2]': 'sell_to_open',
            'quantity[2]': str(quantity),
            'option_symbol[2]': call_short_sym,
            'side[3]': 'buy_to_open',
            'quantity[3]': str(quantity),
            'option_symbol[3]': call_long_sym
        }

        if limit_price:
            data['price'] = str(limit_price)

        return self._make_request('POST', f'accounts/{self.account_id}/orders', data=data)

    # ==================== STREAMING ====================

    async def get_stream_session(self) -> str:
        """Get streaming session token for WebSocket connection"""
        response = self._make_request('POST', 'markets/events/session')
        return response.get('stream', {}).get('sessionid', '')

    async def stream_quotes(
        self,
        symbols: List[str],
        callback
    ):
        """
        Stream real-time quotes via WebSocket.

        Args:
            symbols: List of symbols to stream
            callback: Async function called with each quote update
        """
        session_id = await self.get_stream_session()
        if not session_id:
            raise ValueError("Failed to get streaming session")

        stream_url = "wss://ws.tradier.com/v1/markets/events"

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(stream_url) as ws:
                # Subscribe to symbols
                await ws.send_json({
                    'symbols': symbols,
                    'sessionid': session_id,
                    'filter': ['quote', 'trade']
                })

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        await callback(data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
                        break


# ==================== Integration with Unified System ====================

class TradierExecutor:
    """
    High-level executor that integrates Tradier with the unified trading system.

    Takes MarketAction from MarketRegimeClassifier and executes appropriate trades.
    """

    def __init__(
        self,
        symbol: str = 'SPY',
        max_position_size: int = 10,  # Max contracts
        default_dte: int = 7,  # Default days to expiration
        delta_target: float = 0.30  # Target delta for options
    ):
        self.symbol = symbol
        self.max_position_size = max_position_size
        self.default_dte = default_dte
        self.delta_target = delta_target

        self.tradier = TradierDataFetcher()

        logger.info(f"TradierExecutor initialized for {symbol}")

    def execute_regime_action(
        self,
        action: str,  # 'BUY_CALLS', 'BUY_PUTS', 'SELL_PREMIUM', 'CLOSE_POSITIONS', 'STAY_FLAT'
        position_size: int = 1,
        stop_loss_pct: float = 0.50,  # 50% stop
        take_profit_pct: float = 1.00  # 100% profit target
    ) -> Optional[Dict]:
        """
        Execute trade based on regime classifier output.

        Args:
            action: MarketAction value
            position_size: Number of contracts
            stop_loss_pct: Stop loss as % of premium
            take_profit_pct: Take profit as % of premium

        Returns:
            Order response or None
        """
        # Check current positions
        positions = self.tradier.get_positions()
        current_symbol_positions = [p for p in positions if self.symbol in p.symbol]

        if action == 'CLOSE_POSITIONS':
            # Close all positions for this symbol
            results = []
            for pos in current_symbol_positions:
                try:
                    result = self.tradier.close_position(pos.symbol, abs(pos.quantity))
                    results.append(result)
                except Exception as e:
                    logger.error(f"Failed to close {pos.symbol}: {e}")
            return {'closed': len(results)}

        if action == 'STAY_FLAT':
            logger.info("STAY_FLAT - No action taken")
            return None

        # Find appropriate expiration
        expirations = self.tradier.get_option_expirations(self.symbol)
        target_exp = self._find_target_expiration(expirations, self.default_dte)

        if not target_exp:
            logger.error("No suitable expiration found")
            return None

        # Limit position size
        position_size = min(position_size, self.max_position_size)

        if action == 'BUY_CALLS':
            # Find delta call
            contract = self.tradier.find_delta_option(
                self.symbol, self.delta_target, target_exp, 'call'
            )
            if contract:
                return self.tradier.place_option_order(
                    option_symbol=contract.symbol,
                    side=OrderSide.BUY_TO_OPEN,
                    quantity=position_size,
                    order_type=OrderType.LIMIT,
                    price=contract.mid
                )

        elif action == 'BUY_PUTS':
            # Find delta put
            contract = self.tradier.find_delta_option(
                self.symbol, self.delta_target, target_exp, 'put'
            )
            if contract:
                return self.tradier.place_option_order(
                    option_symbol=contract.symbol,
                    side=OrderSide.BUY_TO_OPEN,
                    quantity=position_size,
                    order_type=OrderType.LIMIT,
                    price=contract.mid
                )

        elif action == 'SELL_PREMIUM':
            # Sell iron condor for neutral premium collection
            quote = self.tradier.get_quote(self.symbol)
            price = quote.get('last', 0)

            # Set wings at 1 standard deviation (roughly)
            wing_width = price * 0.03  # 3% wings

            return self.tradier.place_iron_condor(
                symbol=self.symbol,
                expiration=target_exp,
                put_long=round(price - wing_width * 2, 0),
                put_short=round(price - wing_width, 0),
                call_short=round(price + wing_width, 0),
                call_long=round(price + wing_width * 2, 0),
                quantity=position_size
            )

        return None

    def _find_target_expiration(
        self,
        expirations: List[str],
        target_dte: int
    ) -> Optional[str]:
        """Find expiration closest to target DTE"""
        today = datetime.now().date()

        best_exp = None
        best_diff = float('inf')

        for exp in expirations:
            exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
            dte = (exp_date - today).days

            if dte > 0 and abs(dte - target_dte) < best_diff:
                best_diff = abs(dte - target_dte)
                best_exp = exp

        return best_exp

    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio state"""
        balance = self.tradier.get_account_balance()
        positions = self.tradier.get_positions()
        orders = self.tradier.get_orders('open')

        return {
            'account_value': balance.get('total_equity', 0),
            'buying_power': balance.get('option_buying_power', 0),
            'cash': balance.get('total_cash', 0),
            'positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'cost_basis': p.cost_basis,
                    'current_value': p.current_price * abs(p.quantity) * 100,
                    'gain_loss': p.gain_loss,
                    'gain_loss_pct': p.gain_loss_pct
                }
                for p in positions
            ],
            'open_orders': len(orders),
            'mode': 'SANDBOX' if self.tradier.sandbox else 'LIVE'
        }


# ==================== CLI Testing ====================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Tradier API Test')
    parser.add_argument('--symbol', default='SPY', help='Symbol to test')
    parser.add_argument('--action', choices=['quote', 'chain', 'balance', 'positions'],
                       default='quote', help='Action to perform')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    try:
        tradier = TradierDataFetcher()

        if args.action == 'quote':
            quote = tradier.get_quote(args.symbol)
            print(f"\n{args.symbol} Quote:")
            print(f"  Last: ${quote.get('last', 'N/A')}")
            print(f"  Bid: ${quote.get('bid', 'N/A')}")
            print(f"  Ask: ${quote.get('ask', 'N/A')}")
            print(f"  Volume: {quote.get('volume', 'N/A'):,}")

        elif args.action == 'chain':
            chain = tradier.get_option_chain(args.symbol)
            print(f"\n{args.symbol} Options Chain:")
            print(f"  Underlying: ${chain.underlying_price:.2f}")
            for exp, contracts in chain.chains.items():
                print(f"\n  Expiration: {exp}")
                calls = [c for c in contracts if c.option_type == 'call'][:5]
                for c in calls:
                    print(f"    {c.strike:>8.0f}C | Bid: {c.bid:>6.2f} Ask: {c.ask:>6.2f} | Δ: {c.delta:>5.2f}")

        elif args.action == 'balance':
            balance = tradier.get_account_balance()
            print(f"\nAccount Balance:")
            print(f"  Total Equity: ${balance.get('total_equity', 0):,.2f}")
            print(f"  Option BP: ${balance.get('option_buying_power', 0):,.2f}")
            print(f"  Cash: ${balance.get('total_cash', 0):,.2f}")

        elif args.action == 'positions':
            positions = tradier.get_positions()
            print(f"\nPositions ({len(positions)}):")
            for p in positions:
                print(f"  {p.symbol}: {p.quantity} @ ${p.cost_basis:.2f} | P&L: ${p.gain_loss:.2f} ({p.gain_loss_pct:.1f}%)")

    except Exception as e:
        print(f"Error: {e}")
