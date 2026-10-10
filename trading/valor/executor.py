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
import threading
from datetime import datetime, timedelta
from .reconciliation import summarize_order
from typing import Optional, Dict, Any, Tuple, List
from zoneinfo import ZoneInfo

from .models import (
    FuturesPosition, FuturesSignal, TradeDirection, PositionStatus,
    ValorConfig, TradingMode, MES_POINT_VALUE, CENTRAL_TZ,
    FUTURES_TICKERS, get_ticker_point_value, SignalSource
)

logger = logging.getLogger(__name__)

# Try to import tastytrade SDK for real-time streaming quotes
try:
    from tastytrade import Session, DXLinkStreamer
    from tastytrade.dxfeed import Quote
    from tastytrade.instruments import Future
    TASTYTRADE_SDK_AVAILABLE = True
    logger.info("Tastytrade SDK loaded - real-time futures quotes available")
except ImportError:
    TASTYTRADE_SDK_AVAILABLE = False
    logger.warning("Tastytrade SDK not installed - executable contract quotes unavailable")

# Cache must distinguish expiry as well as ticker and execution mode.
_quote_cache: Dict[Tuple[str, str, str], Tuple[Dict[str, Any], datetime]] = {}
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
            self.auth_method = None
            logger.error("Tastytrade password authentication retired; configure OAuth")
        else:
            self.auth_method = None
            logger.warning("Tastytrade: No credentials configured - executable contract quotes unavailable")

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
        """Exchange the personal OAuth grant; never fall back to retired sessions."""
        self.session_token = None
        self.token_expiry = None
        if not self.client_secret or not self.refresh_token:
            logger.error("Tastytrade OAuth client secret and refresh token are required")
            return False
        try:
            response = requests.post(
                f"{self.base_url}/oauth/token",
                json={"grant_type": "refresh_token", "client_secret": self.client_secret,
                      "refresh_token": self.refresh_token},
                headers={"Content-Type": "application/json", "User-Agent": "AlphaGEX-Valor/1.0"},
                timeout=30,
            )
            if response.status_code != 200:
                logger.error("Tastytrade OAuth failed: HTTP %s", response.status_code)
                return False
            data = response.json()
            token = data.get("access_token")
            expires = int(data.get("expires_in", 900))
            if not token or expires <= 60:
                return False
            self.session_token = token
            self.token_expiry = datetime.now(CENTRAL_TZ) + timedelta(seconds=expires - 60)
            return True
        except Exception:
            logger.error("Tastytrade OAuth exchange failed")
            return False

    def _get_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.session_token}",
                "Content-Type": "application/json", "User-Agent": "AlphaGEX-Valor/1.0"}

    # ========================================================================
    # Quote & Market Data
    # ========================================================================

    @staticmethod
    def _quote_is_usable(quote: Dict[str, Any]) -> bool:
        """Reject non-finite, crossed, missing-time and stale market data."""
        from math import isfinite
        try:
            bid, ask, last = (float(quote[k]) for k in ("bid", "ask", "last"))
            timestamp = datetime.fromisoformat(quote["timestamp"])
            age = (datetime.now(CENTRAL_TZ) - timestamp).total_seconds()
            return all(isfinite(v) and v > 0 for v in (bid, ask, last)) and bid <= ask and 0 <= age <= 10
        except (KeyError, TypeError, ValueError):
            return False

    def get_entry_symbol(self, ticker):
        if ticker in {"MES", "MNQ", "RTY"}:
            return self.config.get_ticker_symbol(ticker)
        if not TASTYTRADE_SDK_AVAILABLE or self.auth_method != "OAUTH":
            return None
        cache = getattr(self, '_entry_contract_cache', {})
        cached = cache.get(ticker)
        now = datetime.now(CENTRAL_TZ)
        if cached and (now-cached[1]).total_seconds() < 60:
            return cached[0]
        async def resolve():
            session = Session(self.client_secret,self.refresh_token)
            code = FUTURES_TICKERS[ticker]['contract_prefix'].lstrip('/')
            futures = await asyncio.wait_for(Future.get(session,product_codes=[code]),10)
            return self._choose_active_contract(futures,code,now)
        try:
            symbol = self._run_async_sync(resolve)
            if symbol:
                cache[ticker] = (symbol,now)
                self._entry_contract_cache = cache
            return symbol
        except Exception:
            logger.warning("No verified active contract for %s",ticker)
            return None

    @staticmethod
    def _choose_active_contract(futures, code, now):
        eligible = [f for f in futures if f.product_code == code and f.active_month
                    and f.is_tradeable and not f.is_closing_only and f.stops_trading_at > now
                    and f.streamer_symbol and f.symbol.startswith('/'+code)]
        return eligible[0].symbol if len(eligible) == 1 else None

    def get_mes_quote(self, symbol: str = None, ticker: str = None) -> Optional[Dict[str, Any]]:
        """
        Get current futures quote for any supported instrument.

        Priority:
        1. Tastytrade DXLinkStreamer (real-time via WebSocket)
        Contract metadata must resolve to an exact broker streamer symbol.
        Continuous Yahoo quotes cannot identify the contract being executed.

        Args:
            symbol: Contract symbol (e.g. /MESH6, /MNQH6)
            ticker: Instrument key (MNQ, CL, NG, RTY, MES) - used to look up Yahoo/DXFeed symbols

        Returns:
            Dict with bid, ask, last, volume or None if failed
        """
        ticker = ticker or "MES"
        symbol = symbol or self.get_entry_symbol(ticker)
        ticker_cfg = FUTURES_TICKERS.get(ticker, {})
        prefix = ticker_cfg.get("contract_prefix")
        if not symbol or not prefix or not symbol.startswith(prefix) or len(symbol) != len(prefix) + 2:
            return None

        # Check cache first
        cache_key = (ticker, symbol, self.config.mode.value)
        if cache_key in _quote_cache:
            cached_quote, cache_time = _quote_cache[cache_key]
            if datetime.now(CENTRAL_TZ) - cache_time < timedelta(seconds=QUOTE_CACHE_TTL_SECONDS) and self._quote_is_usable(cached_quote):
                logger.debug(f"Using cached quote for {ticker}")
                return cached_quote

        # Try Tastytrade DXLinkStreamer (real-time WebSocket streaming)
        if TASTYTRADE_SDK_AVAILABLE and self.auth_method:
            try:
                quote = self._get_tastytrade_streaming_quote(symbol)
                if quote and quote.get("contract_symbol") == symbol and self._quote_is_usable(quote):
                    quote["ticker"] = ticker
                    _quote_cache[cache_key] = (quote, datetime.now(CENTRAL_TZ))
                    return quote
            except Exception as e:
                logger.warning(f"DXLinkStreamer quote failed for {ticker}: {e}")

        return None

    def _run_async_sync(self, coro_factory):
        """Run a coroutine from sync code even when the caller already owns an event loop."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro_factory())

        result = {}
        error = {}

        def runner():
            try:
                result["value"] = asyncio.run(coro_factory())
            except Exception as exc:
                error["exc"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=15)
        if thread.is_alive():
            raise TimeoutError("Timed out waiting for async Tastytrade operation")
        if "exc" in error:
            raise error["exc"]
        return result.get("value")

    def _get_tastytrade_streaming_quote(self, dxfeed_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time futures quote via Tastytrade DXLinkStreamer.

        Args:
            dxfeed_symbol: Exact broker contract (e.g., /MESZ6); resolved below.
        """
        if not TASTYTRADE_SDK_AVAILABLE:
            return None

        try:
            # Ensure proper format - dxfeed_symbol should already be correct
            # from FUTURES_TICKERS config
            streamer_symbol = dxfeed_symbol if dxfeed_symbol.startswith('/') else f'/{dxfeed_symbol}'
            logger.debug(f"DXLinkStreamer quote for: {streamer_symbol}")

            # Run async quote retrieval safely from both scheduler threads and
            # FastAPI request handlers that already have an event loop.
            return self._run_async_sync(
                lambda: self._async_get_streaming_quote(streamer_symbol)
            )

        except Exception as e:
            logger.warning(f"Tastytrade streaming quote error for {dxfeed_symbol}: {e}")
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

            contract_symbol = symbol
            future = await asyncio.wait_for(Future.get(session, contract_symbol), timeout=10)
            if future.symbol != contract_symbol or not future.streamer_symbol:
                return None
            if future.stops_trading_at <= datetime.now(CENTRAL_TZ):
                logger.error("Expired contract %s requires reconciliation", contract_symbol)
                return None
            symbol = future.streamer_symbol

            async with DXLinkStreamer(session) as streamer:
                # Subscribe to the futures symbol
                await streamer.subscribe(Quote, [symbol])

                # Get one quote with a timeout
                try:
                    deadline = asyncio.get_running_loop().time() + 5.0
                    previous = None
                    while True:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            return None
                        quote = await asyncio.wait_for(streamer.get_event(Quote), timeout=remaining)
                        normalized = self._normalize_contract_quote(quote, symbol, contract_symbol)
                        if normalized:
                            return normalized
                        signature = (quote.event_symbol, quote.bid_price, quote.ask_price,
                                     quote.bid_size, quote.ask_size)
                        # Missing times occur on this feed. Only paper may use a
                        # changed post-snapshot event; never relabel stale times.
                        if (self.config.mode == TradingMode.PAPER and previous is not None
                                and signature != previous and quote.event_symbol == symbol
                                and quote.bid_time == 0 and quote.ask_time == 0):
                            return self._normalize_contract_quote(
                                quote, symbol, contract_symbol,
                                observed_update=datetime.now(CENTRAL_TZ))
                        previous = signature
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for quote on {symbol}")

        except Exception as e:
            logger.warning(f"DXLinkStreamer error: {e}")

        return None

    @staticmethod
    def _normalize_contract_quote(quote, streamer_symbol: str, contract_symbol: str, observed_update=None):
        """Reception time must not make a stale snapshot look executable."""
        try:
            if quote.event_symbol != streamer_symbol:
                return None
            # dxFeed bid/ask change times are Unix milliseconds. Require both
            # sides to be recent, using the older side as the quote timestamp.
            missing_times = quote.bid_time == 0 and quote.ask_time == 0
            if missing_times:
                if observed_update is None:
                    return None
                observed = observed_update
            else:
                observed = datetime.fromtimestamp(min(quote.bid_time, quote.ask_time) / 1000, CENTRAL_TZ)
            result = {
                "symbol": streamer_symbol, "contract_symbol": contract_symbol,
                "bid": float(quote.bid_price), "ask": float(quote.ask_price),
                "last": float(quote.bid_price + quote.ask_price) / 2,
                "price": float(quote.bid_price + quote.ask_price) / 2,
                "volume": 0, "timestamp": observed.isoformat(), "source": "TASTYTRADE_DXLINK",
                "bid_size": float(quote.bid_size), "ask_size": float(quote.ask_size),
                "timestamp_basis": "observed_stream_change" if missing_times else "broker_bid_ask",
                "exchange_timestamp_verified": not missing_times,
                "broker_bid_time": quote.bid_time, "broker_ask_time": quote.ask_time,
            }
            return result if TastytradeExecutor._quote_is_usable(result) else None
        except (AttributeError, TypeError, ValueError, OverflowError, OSError):
            return None

    def _get_yahoo_mes_quote(self) -> Optional[Dict[str, Any]]:
        """Legacy method - calls _get_yahoo_futures_quote for MES."""
        return self._get_yahoo_futures_quote("MES=F", "MES")

    def _get_yahoo_futures_quote(self, yahoo_symbol: str, ticker: str = "MES") -> Optional[Dict[str, Any]]:
        """
        Get futures quote from Yahoo Finance for any supported instrument.

        Args:
            yahoo_symbol: Yahoo symbol (e.g., MES=F, MNQ=F, CL=F, NG=F, RTY=F)
            ticker: Instrument key for metadata
        """
        try:
            yahoo_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol}"
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

                    if price > 0 and 0 <= datetime.now(CENTRAL_TZ).timestamp() - meta.get("regularMarketTime", 0) <= 120:
                        # Estimate spread based on instrument
                        ticker_cfg = FUTURES_TICKERS.get(ticker, {})
                        spread = ticker_cfg.get("tick_size", 0.25)
                        return {
                            "symbol": yahoo_symbol.replace("=F", ""),
                            "ticker": ticker,
                            "bid": price - spread,
                            "ask": price + spread,
                            "last": price,
                            "price": price,
                            "prev_close": prev_close,
                            "volume": meta.get("regularMarketVolume", 0),
                            "timestamp": datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=CENTRAL_TZ).isoformat(),
                            "source": f"YAHOO_{ticker}",
                            "exchange": meta.get("exchangeName", "CME")
                        }

            logger.warning(f"Yahoo {yahoo_symbol} quote failed: {response.status_code}")

        except Exception as e:
            logger.warning(f"Could not get {yahoo_symbol} quote from Yahoo: {e}")

        return None

    def _get_spy_derived_quote(self, symbol: str, multiplier: float = 10.0) -> Optional[Dict[str, Any]]:
        """
        Get futures-equivalent quote by deriving from SPY price.
        SPY * multiplier ≈ futures price (e.g., SPY * 10 ≈ MES).
        Used as LAST RESORT fallback when both Tastytrade and Yahoo fail.
        Only works for equity-index futures (MES, RTY).
        """
        try:
            from data.unified_data_provider import get_quote
            spy_quote = get_quote("SPY")

            if spy_quote and spy_quote.price > 0:
                futures_price = spy_quote.price * multiplier
                spread = 0.25
                return {
                    "symbol": symbol,
                    "bid": futures_price - spread,
                    "ask": futures_price + spread,
                    "last": futures_price,
                    "price": futures_price,
                    "volume": 100000,
                    "timestamp": datetime.now(CENTRAL_TZ).isoformat(),
                    "source": "SPY_DERIVED"
                }
        except Exception as e:
            logger.warning(f"Could not derive futures quote from SPY: {e}")

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
        if signal.source == SignalSource.MNQ_BREAKOUT_30M:
            from .mnq_breakout import paper_order_valid
            if not paper_order_valid(signal, self.config.mode, datetime.now(CENTRAL_TZ)):
                return False, "MNQ breakout is paper-only or its decision expired", None
        # Pre-trade margin check (LIVE only). VALOR is multi-instrument but the
        # shared margin engine looks up specs by bot_name, and BOT_INSTRUMENT_MAP
        # pins VALOR → MES, so MNQ's $27k entry × 4 ctr × MES multiplier 5.0 is
        # treated as $558k notional (true MNQ multiplier is 2.0 → real notional
        # ~$223k). The 2.5x inflated notional pushes effective leverage past the
        # bot config limit and silently blocks every MNQ trade. VALOR already has
        # its own per-ticker controls (GATE 4.5 max_open_positions + ValorMarginManager
        # with VALOR_MARGIN_REQUIREMENTS), so the global check is redundant in paper.
        # Skip it in paper mode; live mode keeps the (still-buggy) check until
        # the shared engine learns to take per-trade instrument overrides.
        ticker = getattr(signal, 'ticker', None) or "MES"
        if self.config.mode != TradingMode.PAPER:
            from trading.margin.pre_trade_check import check_margin_before_trade
            approved, reason = check_margin_before_trade(
                bot_name="VALOR",
                symbol=ticker,
                side=signal.direction.value if hasattr(signal.direction, 'value') else str(signal.direction),
                quantity=float(signal.contracts),
                entry_price=signal.entry_price,
                strict=True,
            )
            if not approved:
                logger.warning(f"VALOR: Trade BLOCKED by margin check: {reason}")
                return False, f"Margin check failed: {reason}", None

        if self.config.mode == TradingMode.PAPER:
            return self._simulate_execution(signal, position_id)

        return self._live_execution(signal, position_id)

    def _simulate_execution(self, signal: FuturesSignal, position_id: str) -> Tuple[bool, str, Optional[str]]:
        """Simulate order execution for paper trading"""
        logger.info(
            f"[PAPER] Simulating {signal.direction.value} order: "
            f"{signal.contracts} contracts at {signal.entry_price:.2f}"
        )

        from math import isfinite
        quote = self.get_mes_quote(symbol=getattr(signal,"contract_symbol",None) or None,ticker=signal.ticker)
        if not quote:
            return False, "No executable futures quote", None
        side = "ask" if signal.direction == TradeDirection.LONG else "bid"
        requested_contracts = int(signal.contracts)
        available_contracts = int(float(quote.get(side + "_size", 0) or 0))
        if available_contracts < 1:
            return False, "No executable top-of-book liquidity", None

        # Realistic paper partial fill: never invent liquidity. If top-of-book
        # size is smaller than the requested order, fill only the observable
        # quantity and persist that smaller position size.
        if available_contracts < requested_contracts:
            logger.info(
                "[PAPER] %s partial fill: requested=%s available=%s",
                signal.ticker, requested_contracts, available_contracts,
            )
            signal.contracts = available_contracts

        fill_price = self._paper_fill(quote, side, signal.contracts, signal.ticker)
        if fill_price is None:
            return False, "No sufficiently sized, fresh contract quote", None
        signal.entry_price = fill_price

        order_id = f"PAPER-{position_id}"

        return True, f"Paper order filled at {fill_price:.2f}", order_id

    def find_order(self, intent_id: str, order_id=None) -> Optional[Dict[str, Any]]:
        """Read-only recovery; absence is never permission to resubmit."""
        if not self._ensure_session():
            return None
        url = f"{self.base_url}/accounts/{self.account_id}/orders"
        if order_id:
            response = requests.get(f"{url}/{order_id}", headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            order = response.json().get('data', {})
            if order.get('external-identifier') != intent_id:
                raise ValueError('Broker order identifier mismatch')
            return order
        for page in range(10):
            response = requests.get(url, params={'per-page':100, 'page-offset':page},
                                    headers=self._get_headers(), timeout=15)
            response.raise_for_status()
            payload = response.json()
            items = payload.get('data', {}).get('items', [])
            matches = [o for o in items if o.get('external-identifier') == intent_id]
            if len(matches) > 1:
                raise ValueError('Multiple broker orders match one intent')
            if matches:
                return matches[0]
            if len(items) < 100:
                break
        return None

    def _submit_market_order(self, symbol, quantity, action, intent_id):
        """Single submission; persist/reconcile ambiguous outcomes instead of retrying."""
        self.last_broker_order_id = None
        if not self._ensure_session():
            return None
        payload = {'time-in-force':'Day', 'order-type':'Market',
                   'external-identifier':intent_id,
                   'legs':[{'instrument-type':'Future','symbol':symbol,'quantity':quantity,'action':action}]}
        response = requests.post(f"{self.base_url}/accounts/{self.account_id}/orders",
                                 headers=self._get_headers(),json=payload,timeout=30)
        response.raise_for_status()
        order = response.json().get('data',{}).get('order',{})
        self.last_broker_order_id = order.get('id')
        return summarize_order(order,symbol,quantity,action)

    def _live_execution(self, signal: FuturesSignal, position_id: str) -> Tuple[bool, str, Optional[str]]:
        if signal.source == SignalSource.MNQ_BREAKOUT_30M:
            return False, "MNQ breakout live execution prohibited", None
        try:
            action = 'Buy to Open' if signal.direction == TradeDirection.LONG else 'Sell to Open'
            result = self._submit_market_order(signal.contract_symbol or self.get_entry_symbol(signal.ticker),signal.contracts,action,position_id)
            if result and result['terminal'] and result['quantity'] == signal.contracts:
                signal.entry_price = result['price']
                return True,'Broker fill confirmed',result['order_id']
            return False,'Broker order pending reconciliation',self.last_broker_order_id
        except Exception:
            logger.exception('VALOR entry requires reconciliation')
            return False,'Broker order pending reconciliation',getattr(self,'last_broker_order_id',None)

    def close_position_order(
        self,
        position: FuturesPosition,
        close_reason: str,
        intended_close_price: float = 0.0,
        intent_id: Optional[str] = None,
    ) -> Tuple[bool, str, float]:
        """
        Close an existing position.

        Args:
            position: The position to close
            close_reason: Reason for closing
            intended_close_price: Trigger price for context only; paper fills use current bid/ask.

        Returns:
            (success, message, fill_price)
        """
        if position.signal_source == SignalSource.MNQ_BREAKOUT_30M and self.config.mode != TradingMode.PAPER:
            return False, "Paper MNQ position cannot be closed through a live broker", 0.0
        if self.config.mode == TradingMode.PAPER:
            return self._simulate_close(position, close_reason, intended_close_price)

        return self._live_close(position, close_reason, intent_id)

    def _simulate_close(
        self,
        position: FuturesPosition,
        close_reason: str,
        intended_close_price: float = 0.0
    ) -> Tuple[bool, str, float]:
        """Use observable bid/ask, including gaps; never invent a stop fill."""
        from math import isfinite
        quote = self.get_mes_quote(symbol=position.symbol, ticker=position.ticker)
        if not quote:
            return False, "No executable futures quote", 0.0
        side = "bid" if position.direction == TradeDirection.LONG else "ask"
        fill_price = self._paper_fill(quote, side, position.contracts, position.ticker)
        if fill_price is None:
            return False, "No sufficiently sized, fresh contract quote", 0.0
        return True, f"Paper close filled at {fill_price:.2f}", fill_price

    def _paper_fill(self, quote, side, quantity, ticker):
        from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
        from math import isfinite
        self.last_paper_fill = None
        try:
            if not self.is_market_open() or not self._quote_is_usable(quote) or quantity < 1:
                return None
            size = float(quote.get(side + "_size", 0))
            if not isfinite(size) or size < quantity:
                return None  # No invented liquidity or unmodeled partial fills.
            ticks = self.config.paper_slippage_ticks
            if isinstance(ticks, bool) or int(ticks) != ticks or ticks < 0:
                return None
            tick = Decimal(str(FUTURES_TICKERS[ticker]["tick_size"]))
            raw = Decimal(str(quote[side])) + (1 if side == "ask" else -1) * int(ticks) * tick
            price = float((raw/tick).to_integral_value(rounding=ROUND_CEILING if side == "ask" else ROUND_FLOOR)*tick)
            if price <= 0:
                return None
            self.last_paper_fill = dict(quote, fill_price=price, side=side, quantity=quantity,
                                       slippage_ticks=ticks, observed_at=datetime.now(CENTRAL_TZ).isoformat())
            return price
        except (KeyError, TypeError, ValueError, ArithmeticError):
            return None

    def _live_close(self, position: FuturesPosition, close_reason: str, intent_id: Optional[str] = None) -> Tuple[bool, str, float]:
        if position.signal_source == SignalSource.MNQ_BREAKOUT_30M:
            return False, "Paper MNQ position cannot be closed through a live broker", 0.0
        try:
            action = 'Sell to Close' if position.direction == TradeDirection.LONG else 'Buy to Close'
            result = self._submit_market_order(position.symbol,position.contracts,action,intent_id or f'close:{position.position_id}')
            if result and result['terminal'] and result['quantity'] == position.contracts:
                return True,'Broker close confirmed',result['price']
            return False,'Broker close pending reconciliation',0.0
        except Exception:
            logger.exception('VALOR close requires reconciliation')
            return False,'Broker close pending reconciliation',0.0

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

        # Time-only MNQ is a one-contract PAPER experiment, never zero-risk live trading.
        if signal.source == SignalSource.MNQ_BREAKOUT_30M:
            from .mnq_breakout import paper_order_valid
            if not paper_order_valid(signal, self.config.mode, datetime.now(CENTRAL_TZ)):
                return False, "MNQ breakout requires a current one-contract paper decision"
        else:
            risk_amount = signal.risk_dollars
            max_risk = account_balance * (self.config.risk_per_trade_pct / 100)
            if risk_amount is None or risk_amount > max_risk * 1.5:
                return False, "Stop-defined risk is absent or exceeds the configured maximum"

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
            "can_execute": self.session_token is not None,
            "auth_method": self.auth_method,
            "session_active": self.session_token is not None,
            "market_open": self.is_market_open(),
            "init_error": None if self.session_token else "No active session - check credentials"
        }
