"""
VALOR - Order Executor
=========================

Handles order execution via Tastytrade API for MES futures.

Features:
- Market and limit order execution
- Position monitoring
- Stop loss management
- Real-time quote fetching via DXLinkStreamer (WebSocket)
"""

import os
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
from zoneinfo import ZoneInfo

from .models import (
    FuturesPosition, FuturesSignal, TradeDirection, PositionStatus,
    ValorConfig, TradingMode, MES_POINT_VALUE, CENTRAL_TZ
)

logger = logging.getLogger(__name__)

# Try to import tastytrade SDK for real-time streaming quotes
try:
    from tastytrade import Session, DXLinkStreamer
    from tastytrade.dxfeed import Quote
    TASTYTRADE_SDK_AVAILABLE = True
    logger.info("Tastytrade SDK loaded - real-time futures quotes available")
except ImportError:
    TASTYTRADE_SDK_AVAILABLE = False
    logger.warning("Tastytrade SDK not installed - falling back to Yahoo for quotes")

# Quote cache for reducing API calls
_quote_cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
QUOTE_CACHE_TTL_SECONDS = 5  # Cache quotes for 5 seconds

# Tastytrade API endpoints
TASTYTRADE_BASE_URL = "https://api.tastytrade.com"
TASTYTRADE_SANDBOX_URL = "https://api.cert.tastytrade.com"


class TastytradeExecutor:
    """
    Executes orders on Tastytrade for MES futures.

    Handles:
    - Authentication (OAuth preferred, username/password fallback)
    - Order placement (market/limit)
    - Position queries
    - Quote fetching via DXLinkStreamer
    - Account balances
    """

    def __init__(self, config: ValorConfig):
        self.config = config
        self.session_token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

        # OAuth credentials (PREFERRED - works with 2FA)
        self.client_secret = os.environ.get("TASTYTRADE_CLIENT_SECRET")
        self.refresh_token = os.environ.get("TASTYTRADE_REFRESH_TOKEN")

        # Legacy credentials (fallback - does NOT work with 2FA)
        self.username = os.environ.get("TASTYTRADE_USERNAME")
        self.password = os.environ.get("TASTYTRADE_PASSWORD")

        self.account_id = os.environ.get("TASTYTRADE_ACCOUNT_ID") or config.account_id

        # Determine auth method
        if self.client_secret and self.refresh_token:
            self.auth_method = "OAUTH"
            logger.info("Tastytrade: Using OAuth authentication (2FA compatible)")
        elif self.username and self.password:
            self.auth_method = "PASSWORD"
            logger.warning("Tastytrade: Using password auth (may fail with 2FA enabled)")
        else:
            self.auth_method = None
            logger.warning("Tastytrade: No credentials configured - will use Yahoo fallback")

        # Use sandbox for paper trading
        self.base_url = TASTYTRADE_BASE_URL
        if config.mode == TradingMode.PAPER:
            # Note: Tastytrade doesn't have a true sandbox for futures
            # Paper trading is simulated in our system
            logger.info("VALOR running in PAPER mode - orders will be simulated")

    def _ensure_session(self) -> bool:
        """Ensure we have a valid session token"""
        if self.session_token and self.token_expiry:
            if datetime.now(CENTRAL_TZ) < self.token_expiry:
                return True

        return self._authenticate()

    def _authenticate(self) -> bool:
        """Authenticate with Tastytrade API"""
        if not self.username or not self.password:
            logger.error("TASTYTRADE_USERNAME and TASTYTRADE_PASSWORD must be set")
            return False

        try:
            response = requests.post(
                f"{self.base_url}/sessions",
                json={
                    "login": self.username,
                    "password": self.password,
                    "remember-me": True
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )

            if response.status_code == 201:
                data = response.json()
                self.session_token = data.get("data", {}).get("session-token")
                # Token valid for 24 hours, refresh at 23 hours
                self.token_expiry = datetime.now(CENTRAL_TZ).replace(hour=23, minute=0)
                logger.info("Tastytrade authentication successful")
                return True
            else:
                logger.error(f"Tastytrade auth failed: {response.status_code} - {response.text[:200]}")
                return False

        except Exception as e:
            logger.error(f"Tastytrade auth error: {e}")
            return False

    def _get_headers(self) -> Dict[str, str]:
        """Get authenticated headers"""
        return {
            "Authorization": self.session_token,
            "Content-Type": "application/json"
        }

    # ========================================================================
    # Quote & Market Data
    # ========================================================================

    def get_mes_quote(self, symbol: str = None) -> Optional[Dict[str, Any]]:
        """
        Get current MES futures quote.

        Priority:
        1. Tastytrade DXLinkStreamer (real-time via WebSocket)
        2. Yahoo Finance MES=F (may have 15-min delay)
        3. SPY-derived price (last resort for paper trading)

        Returns:
            Dict with bid, ask, last, volume or None if failed
        """
        symbol = symbol or self.config.symbol

        # Check cache first
        cache_key = symbol
        if cache_key in _quote_cache:
            cached_quote, cache_time = _quote_cache[cache_key]
            if datetime.now(CENTRAL_TZ) - cache_time < timedelta(seconds=QUOTE_CACHE_TTL_SECONDS):
                logger.debug(f"Using cached quote for {symbol}")
                return cached_quote

        # Try Tastytrade DXLinkStreamer (real-time WebSocket streaming)
        if TASTYTRADE_SDK_AVAILABLE and self.auth_method:
            try:
                quote = self._get_tastytrade_streaming_quote(symbol)
                if quote:
                    _quote_cache[cache_key] = (quote, datetime.now(CENTRAL_TZ))
                    return quote
            except Exception as e:
                logger.warning(f"DXLinkStreamer quote failed: {e}")

        # Fallback: Get direct MES futures quote from Yahoo Finance
        # Yahoo provides free delayed MES=F quotes (typically 15-min delay)
        mes_quote = self._get_yahoo_mes_quote()
        if mes_quote:
            _quote_cache[cache_key] = (mes_quote, datetime.now(CENTRAL_TZ))
            return mes_quote

        # Last resort: Derive from SPY * 10 (not ideal but better than nothing)
        if self.config.mode == TradingMode.PAPER:
            spy_quote = self._get_spy_derived_quote(symbol)
            if spy_quote:
                _quote_cache[cache_key] = (spy_quote, datetime.now(CENTRAL_TZ))
            return spy_quote

        return None

    def _get_tastytrade_streaming_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time futures quote via Tastytrade DXLinkStreamer.

        This uses WebSocket streaming for real-time data.
        Note: Requires tastytrade SDK (pip install tastytrade)
        """
        if not TASTYTRADE_SDK_AVAILABLE:
            return None

        try:
            # Convert symbol to DXFeed format
            # Config uses /MESH6 (contract month) but DXFeed needs /MES:XCME (root + exchange)
            # /MESH6, /MESM6, /MESU6, /MESZ6 all map to /MES:XCME for real-time quotes
            if symbol.startswith('/MES'):
                streamer_symbol = '/MES:XCME'
            elif symbol.startswith('MES'):
                streamer_symbol = '/MES:XCME'
            else:
                # For other symbols, add / prefix if needed
                streamer_symbol = symbol if symbol.startswith('/') else f'/{symbol}'

            logger.debug(f"Converting {symbol} to DXFeed symbol: {streamer_symbol}")

            # Run async function synchronously
            return asyncio.run(self._async_get_streaming_quote(streamer_symbol))

        except Exception as e:
            logger.warning(f"Tastytrade streaming quote error: {e}")
            return None

    async def _async_get_streaming_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Async function to get a single quote from DXLinkStreamer.

        Opens a connection, subscribes to the symbol, gets one quote, and closes.
        Supports both OAuth (preferred) and password authentication.
        """
        try:
            # Create a session based on auth method
            if self.auth_method == "OAUTH":
                # OAuth: use client_secret and refresh_token (works with 2FA)
                session = Session(self.client_secret, self.refresh_token)
                logger.debug("Created Tastytrade session via OAuth")
            else:
                # Password auth (legacy, doesn't work with 2FA)
                session = Session(self.username, self.password)
                logger.debug("Created Tastytrade session via password")

            async with DXLinkStreamer(session) as streamer:
                # Subscribe to the futures symbol
                await streamer.subscribe(Quote, [symbol])

                # Get one quote with a timeout
                try:
                    quote = await asyncio.wait_for(
                        streamer.get_event(Quote),
                        timeout=5.0  # 5 second timeout
                    )

                    if quote and quote.bid_price and quote.ask_price:
                        return {
                            "symbol": symbol,
                            "bid": float(quote.bid_price),
                            "ask": float(quote.ask_price),
                            "last": float(quote.bid_price + quote.ask_price) / 2,  # Mid price if no last
                            "price": float(quote.bid_price + quote.ask_price) / 2,
                            "volume": 0,  # DXFeed Quote doesn't include volume
                            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
                            "source": "TASTYTRADE_DXLINK"
                        }
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for quote on {symbol}")

        except Exception as e:
            logger.warning(f"DXLinkStreamer error: {e}")

        return None

    def _get_yahoo_mes_quote(self) -> Optional[Dict[str, Any]]:
        """
        Get MES futures quote from Yahoo Finance.

        Yahoo Finance provides free MES=F quotes (Micro E-mini S&P 500 futures).
        Data may be delayed 15 minutes per exchange rules, but this is acceptable
        for paper trading and better than deriving from SPY.
        """
        try:
            # Yahoo Finance API for MES=F (Micro E-mini S&P 500)
            yahoo_url = "https://query1.finance.yahoo.com/v8/finance/chart/MES=F"
            params = {
                "interval": "1m",
                "range": "1d"
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }

            response = requests.get(yahoo_url, params=params, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()
                result = data.get("chart", {}).get("result", [])

                if result:
                    meta = result[0].get("meta", {})
                    price = meta.get("regularMarketPrice", 0)
                    prev_close = meta.get("previousClose", price)

                    if price > 0:
                        # MES typical spread is 0.25-0.50 points
                        spread = 0.25
                        return {
                            "symbol": "MES",
                            "bid": price - spread,
                            "ask": price + spread,
                            "last": price,
                            "price": price,  # Alias for convenience
                            "prev_close": prev_close,
                            "volume": meta.get("regularMarketVolume", 0),
                            "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
                            "source": "YAHOO_MES",
                            "exchange": meta.get("exchangeName", "CME")
                        }

            logger.warning(f"Yahoo MES quote failed: {response.status_code}")

        except Exception as e:
            logger.warning(f"Could not get MES quote from Yahoo: {e}")

        return None

    def _get_spy_derived_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get MES-equivalent quote by deriving from SPY price.
        SPY = S&P 500 / 10, so SPY * 10 ≈ ES/MES price.
        Used as LAST RESORT fallback when both Tastytrade and Yahoo fail.
        """
        try:
            from data.unified_data_provider import get_quote
            spy_quote = get_quote("SPY")

            if spy_quote and spy_quote.price > 0:
                # SPY * 10 gives approximate ES/MES level
                mes_price = spy_quote.price * 10
                # Approximate bid/ask spread for MES (typically 0.25-0.50 points)
                spread = 0.25
                return {
                    "symbol": symbol,
                    "bid": mes_price - spread,
                    "ask": mes_price + spread,
                    "last": mes_price,
                    "price": mes_price,
                    "volume": 100000,  # Placeholder for paper trading
                    "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
                    "source": "SPY_DERIVED"  # Flag this as derived data
                }
        except Exception as e:
            logger.warning(f"Could not derive MES quote from SPY: {e}")

        return None

    def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """Get account balance and buying power"""
        if not self._ensure_session():
            return None

        try:
            response = requests.get(
                f"{self.base_url}/accounts/{self.account_id}/balances",
                headers=self._get_headers(),
                timeout=30
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                return {
                    "net_liquidating_value": float(data.get("net-liquidating-value", 0)),
                    "cash_balance": float(data.get("cash-balance", 0)),
                    "buying_power": float(data.get("derivative-buying-power", 0)),
                    "futures_buying_power": float(data.get("futures-overnight-margin-requirement", 0)),
                    "pending_cash": float(data.get("pending-cash", 0)),
                }
            else:
                logger.error(f"Failed to get balance: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            return None

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions in the account"""
        if not self._ensure_session():
            return []

        try:
            response = requests.get(
                f"{self.base_url}/accounts/{self.account_id}/positions",
                headers=self._get_headers(),
                timeout=30
            )

            if response.status_code == 200:
                positions = response.json().get("data", {}).get("items", [])

                # Filter for futures positions
                futures_positions = [
                    p for p in positions
                    if p.get("instrument-type") == "Future"
                ]

                return futures_positions
            else:
                logger.error(f"Failed to get positions: {response.status_code}")
                return []

        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    # ========================================================================
    # Order Execution
    # ========================================================================

    def execute_signal(self, signal: FuturesSignal, position_id: str) -> Tuple[bool, str, Optional[str]]:
        """
        Execute a trading signal.

        Args:
            signal: The signal to execute
            position_id: Unique position identifier

        Returns:
            (success, message, order_id)
        """
        if self.config.mode == TradingMode.PAPER:
            return self._simulate_execution(signal, position_id)

        return self._live_execution(signal, position_id)

    def _simulate_execution(self, signal: FuturesSignal, position_id: str) -> Tuple[bool, str, Optional[str]]:
        """Simulate order execution for paper trading"""
        logger.info(
            f"[PAPER] Simulating {signal.direction.value} order: "
            f"{signal.contracts} contracts at {signal.entry_price:.2f}"
        )

        # Simulate execution with slight slippage
        slippage = 0.25  # 1 tick slippage
        if signal.direction == TradeDirection.LONG:
            fill_price = signal.entry_price + slippage
        else:
            fill_price = signal.entry_price - slippage

        order_id = f"PAPER-{position_id}"

        return True, f"Paper order filled at {fill_price:.2f}", order_id

    def _live_execution(self, signal: FuturesSignal, position_id: str) -> Tuple[bool, str, Optional[str]]:
        """Execute a live order via Tastytrade"""
        if not self._ensure_session():
            return False, "Authentication failed", None

        try:
            # Build order payload
            order_payload = {
                "time-in-force": "Day",
                "order-type": "Market",
                "legs": [
                    {
                        "instrument-type": "Future",
                        "symbol": self.config.symbol,
                        "quantity": signal.contracts,
                        "action": "Buy to Open" if signal.direction == TradeDirection.LONG else "Sell to Open"
                    }
                ]
            }

            response = requests.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                headers=self._get_headers(),
                json=order_payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                order_id = data.get("order", {}).get("id")
                status = data.get("order", {}).get("status")

                logger.info(f"Order placed: {order_id}, status: {status}")
                return True, f"Order {order_id} placed, status: {status}", order_id
            else:
                error_msg = response.json().get("error", {}).get("message", response.text[:200])
                logger.error(f"Order failed: {error_msg}")
                return False, f"Order failed: {error_msg}", None

        except Exception as e:
            logger.error(f"Error executing order: {e}")
            return False, str(e), None

    def close_position_order(
        self,
        position: FuturesPosition,
        close_reason: str,
        intended_close_price: float = 0.0
    ) -> Tuple[bool, str, float]:
        """
        Close an existing position.

        Args:
            position: The position to close
            close_reason: Reason for closing
            intended_close_price: For PAPER stop orders, this is the stop price we want to fill at.
                                  This simulates exchange-level stop orders that fill at the stop price,
                                  not the current market price (which could be much worse).

        Returns:
            (success, message, fill_price)
        """
        if self.config.mode == TradingMode.PAPER:
            return self._simulate_close(position, close_reason, intended_close_price)

        return self._live_close(position, close_reason)

    def _simulate_close(
        self,
        position: FuturesPosition,
        close_reason: str,
        intended_close_price: float = 0.0
    ) -> Tuple[bool, str, float]:
        """
        Simulate closing a position for paper trading.

        PAPER STOP ORDER FIX:
        If intended_close_price is provided (> 0), use that as the fill price.
        This simulates an exchange-level stop order that would fill at the stop price,
        not the current market price (which could gap past the stop).

        Without this fix, a stop at 6910 could "fill" at 6920 if that's where the
        market is when we detect the stop was hit (due to 15-second polling delay).
        """
        # If intended close price is provided (stop order simulation), use it
        if intended_close_price > 0:
            fill_price = intended_close_price
            logger.info(
                f"[PAPER STOP] Simulating stop fill for {position.position_id}: "
                f"{position.direction.value} {position.contracts} contracts at STOP PRICE {fill_price:.2f}"
            )
        else:
            # Market order simulation - use current quote
            quote = self.get_mes_quote(position.symbol)

            if quote:
                if position.direction == TradeDirection.LONG:
                    fill_price = quote.get("bid", position.current_stop)
                else:
                    fill_price = quote.get("ask", position.current_stop)
            else:
                # Use stop price as fill price if no quote
                fill_price = position.current_stop

            logger.info(
                f"[PAPER MARKET] Simulating close for {position.position_id}: "
                f"{position.direction.value} {position.contracts} contracts at {fill_price:.2f}"
            )

        return True, f"Paper close filled at {fill_price:.2f}", fill_price

    def _live_close(
        self,
        position: FuturesPosition,
        close_reason: str
    ) -> Tuple[bool, str, float]:
        """Close a live position via Tastytrade"""
        if not self._ensure_session():
            return False, "Authentication failed", 0.0

        try:
            # Determine closing action
            if position.direction == TradeDirection.LONG:
                action = "Sell to Close"
            else:
                action = "Buy to Close"

            order_payload = {
                "time-in-force": "Day",
                "order-type": "Market",
                "legs": [
                    {
                        "instrument-type": "Future",
                        "symbol": position.symbol,
                        "quantity": position.contracts,
                        "action": action
                    }
                ]
            }

            response = requests.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                headers=self._get_headers(),
                json=order_payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                order_id = data.get("order", {}).get("id")
                fill_price = float(data.get("order", {}).get("fill-price", 0))

                logger.info(f"Close order placed: {order_id}, fill: {fill_price}")
                return True, f"Close order {order_id} filled at {fill_price}", fill_price
            else:
                error_msg = response.json().get("error", {}).get("message", response.text[:200])
                logger.error(f"Close order failed: {error_msg}")
                return False, f"Close failed: {error_msg}", 0.0

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False, str(e), 0.0

    # ========================================================================
    # Stop Order Management
    # ========================================================================

    def place_stop_order(
        self,
        position: FuturesPosition,
        stop_price: float
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Place a stop loss order for a position.

        For paper trading, stops are managed internally by the trader.
        For live trading, we place a stop order with Tastytrade.
        """
        if self.config.mode == TradingMode.PAPER:
            logger.info(f"[PAPER] Stop order simulated at {stop_price:.2f}")
            return True, f"Paper stop at {stop_price:.2f}", f"STOP-{position.position_id}"

        if not self._ensure_session():
            return False, "Authentication failed", None

        try:
            # Determine stop action
            if position.direction == TradeDirection.LONG:
                action = "Sell to Close"
            else:
                action = "Buy to Close"

            order_payload = {
                "time-in-force": "GTC",  # Good Till Cancelled
                "order-type": "Stop",
                "stop-trigger": stop_price,
                "legs": [
                    {
                        "instrument-type": "Future",
                        "symbol": position.symbol,
                        "quantity": position.contracts,
                        "action": action
                    }
                ]
            }

            response = requests.post(
                f"{self.base_url}/accounts/{self.account_id}/orders",
                headers=self._get_headers(),
                json=order_payload,
                timeout=30
            )

            if response.status_code in [200, 201]:
                data = response.json().get("data", {})
                order_id = data.get("order", {}).get("id")
                logger.info(f"Stop order placed: {order_id} at {stop_price}")
                return True, f"Stop order {order_id} at {stop_price}", order_id
            else:
                error_msg = response.json().get("error", {}).get("message", response.text[:200])
                logger.error(f"Stop order failed: {error_msg}")
                return False, f"Stop order failed: {error_msg}", None

        except Exception as e:
            logger.error(f"Error placing stop order: {e}")
            return False, str(e), None

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order"""
        if self.config.mode == TradingMode.PAPER:
            logger.info(f"[PAPER] Order {order_id} cancelled")
            return True

        if not self._ensure_session():
            return False

        try:
            response = requests.delete(
                f"{self.base_url}/accounts/{self.account_id}/orders/{order_id}",
                headers=self._get_headers(),
                timeout=30
            )

            if response.status_code in [200, 204]:
                logger.info(f"Order {order_id} cancelled")
                return True
            else:
                logger.error(f"Failed to cancel order {order_id}: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}")
            return False

    # ========================================================================
    # Utility Methods
    # ========================================================================

    def is_market_open(self) -> bool:
        """
        Check if futures market is open.

        MES trades nearly 24 hours:
        - Sunday 5:00 PM CT to Friday 4:00 PM CT
        - Daily maintenance break: 4:00 PM - 5:00 PM CT
        """
        now = datetime.now(CENTRAL_TZ)
        day = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour
        minute = now.minute

        # Saturday - closed
        if day == 5:
            return False

        # Sunday - opens at 5 PM
        if day == 6:
            return hour >= 17

        # Friday - closes at 4 PM
        if day == 4 and hour >= 16:
            return False

        # Daily maintenance break 4-5 PM CT
        if hour == 16:
            return False

        return True

    def get_maintenance_break_seconds(self) -> int:
        """Get seconds until maintenance break ends (if during break)"""
        now = datetime.now(CENTRAL_TZ)

        if now.hour == 16:
            # In maintenance break, calculate seconds until 5 PM
            return (60 - now.minute) * 60 - now.second

        return 0

    def validate_order_params(
        self,
        signal: FuturesSignal,
        account_balance: float
    ) -> Tuple[bool, str]:
        """
        Validate order parameters before execution.

        Checks:
        - Sufficient buying power
        - Position size limits
        - Market hours
        """
        # Check market hours
        if not self.is_market_open():
            return False, "Market is closed"

        # Check position size
        if signal.contracts > self.config.max_contracts:
            return False, f"Contracts {signal.contracts} exceeds max {self.config.max_contracts}"

        # Check risk per trade
        risk_amount = signal.risk_dollars
        max_risk = account_balance * (self.config.risk_per_trade_pct / 100)

        if risk_amount > max_risk * 1.5:  # Allow 50% buffer
            return False, f"Risk ${risk_amount:.2f} exceeds max ${max_risk:.2f}"

        # Check minimum balance for MES margin (~$1,500 per contract)
        min_margin_per_contract = 1500
        required_margin = signal.contracts * min_margin_per_contract

        if account_balance < required_margin:
            return False, f"Insufficient margin: need ${required_margin:.2f}, have ${account_balance:.2f}"

        return True, "Validation passed"

    def get_execution_status(self) -> Dict[str, Any]:
        """
        Get current execution capability status.

        Returns dict with:
        - can_execute: Whether orders can be executed
        - auth_method: Authentication method being used
        - session_active: Whether session is authenticated
        - market_open: Whether futures market is open
        - init_error: Any initialization error message
        """
        return {
            "can_execute": self.session is not None,
            "auth_method": self.auth_method,
            "session_active": self.session is not None,
            "market_open": self.is_market_open(),
            "init_error": None if self.session else "No active session - check credentials"
        }
