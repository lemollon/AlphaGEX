"""
AGAPE-SPOT Executor - Multi-ticker, long-only spot trades via Coinbase Advanced Trade API.

24/7 Coinbase spot trading. No CME futures, no market hours restrictions.
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.

Supported tickers: ETH-USD, BTC-USD, XRP-USD, SHIB-USD, DOGE-USD
Position sizing: Uses quantity directly (per-coin units).
  - P&L = (exit - entry) * quantity (always long)

Requires:
  pip install coinbase-advanced-py

Environment variables (default account, shared by all tickers):
  COINBASE_API_KEY      = "organizations/{org_id}/apiKeys/{key_id}"
  COINBASE_API_SECRET   = "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----\\n"

Shared dedicated account (used for ALL live tickers without their own key):
  COINBASE_DEDICATED_API_KEY    = "organizations/{org_id}/apiKeys/{key_id}"
  COINBASE_DEDICATED_API_SECRET = "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----\\n"

Per-ticker overrides (optional, overrides dedicated for a specific coin):
  COINBASE_DOGE_API_KEY     = "organizations/{org_id}/apiKeys/{key_id}"
  COINBASE_DOGE_API_SECRET  = "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----\\n"
  COINBASE_XRP_API_KEY      = ...
  COINBASE_SHIB_API_KEY     = ...
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional, Dict, Tuple
from zoneinfo import ZoneInfo

from trading.agape_spot.models import (
    AgapeSpotConfig,
    AgapeSpotSignal,
    AgapeSpotPosition,
    CapitalAllocator,
    PositionStatus,
    SignalAction,
    TradingMode,
    SPOT_TICKERS,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

# Graceful Coinbase SDK import
coinbase_available = False
RESTClient = None
try:
    from coinbase.rest import RESTClient as _RESTClient
    RESTClient = _RESTClient
    coinbase_available = True
    logger.info("AGAPE-SPOT Executor: coinbase-advanced-py loaded")
except ImportError:
    logger.info("AGAPE-SPOT Executor: coinbase-advanced-py not installed")


class AgapeSpotExecutor:
    """Executes multi-ticker, long-only spot trades via Coinbase Advanced Trade API.

    24/7 trading - no market hours restrictions.
    LONG-ONLY: Opening = market_order_buy, Closing = market_order_sell.

    Supports per-ticker Coinbase accounts via env var overrides:
      COINBASE_{SYMBOL}_API_KEY / COINBASE_{SYMBOL}_API_SECRET
    Falls back to the default COINBASE_API_KEY / COINBASE_API_SECRET.
    """

    def __init__(self, config: AgapeSpotConfig, db=None):
        self.config = config
        self.db = db

        # Account 1: Default client (COINBASE_API_KEY)
        self._client: Optional[object] = None

        # Account 2: Dedicated client (COINBASE_DEDICATED_API_KEY)
        # Both accounts trade ALL live tickers independently.
        self._dedicated_client: Optional[object] = None

        # Per-ticker override clients (COINBASE_{SYMBOL}_API_KEY)
        # Only used if a specific coin needs a different key than the two main accounts.
        self._ticker_clients: Dict[str, object] = {}

        # Coinbase product limits fetched at init (real minimums from API)
        # {ticker: {"base_min_size": float, "quote_min_size": float, "base_increment": float}}
        self._product_limits: Dict[str, Dict[str, float]] = {}

        # Performance-based capital allocator (set by trader.py, refreshed each cycle)
        self.capital_allocator: Optional[CapitalAllocator] = None

        # Always init Coinbase clients (needed for price data even in paper mode)
        if coinbase_available:
            self._init_coinbase()

    def _init_coinbase(self):
        """Initialize Coinbase clients.

        Two main accounts, both trade ALL live tickers:
          1. Default:   COINBASE_API_KEY / SECRET
          2. Dedicated: COINBASE_DEDICATED_API_KEY / SECRET

        Optional per-ticker override:
          COINBASE_{SYMBOL}_API_KEY / SECRET  (replaces default for one coin)
        """
        # --- Account 1: Default client (your account) ---
        api_key = os.getenv("COINBASE_API_KEY")
        api_secret = os.getenv("COINBASE_API_SECRET")

        if api_key and api_secret:
            try:
                self._client = RESTClient(api_key=api_key, api_secret=api_secret)
                verify_ticker = self.config.tickers[0] if self.config.tickers else "ETH-USD"
                product = self._client.get_product(verify_ticker)
                if product:
                    price = float(self._resp(product, "price", 0))
                    self._store_product_limits(verify_ticker, product)
                    logger.info(
                        f"AGAPE-SPOT Executor: Account 1 (default) connected. "
                        f"{verify_ticker} = ${price:,.2f}"
                    )
                else:
                    logger.warning("AGAPE-SPOT Executor: Account 1 connected but no product data")
            except Exception as e:
                logger.error(f"AGAPE-SPOT Executor: Account 1 init failed: {e}")
                self._client = None
        else:
            logger.warning(
                "AGAPE-SPOT Executor: No COINBASE_API_KEY/SECRET set (Account 1)."
            )

        # --- Account 2: Dedicated client (friend's account) ---
        # Trades ALL live tickers, not just specific ones.
        ded_key = os.getenv("COINBASE_DEDICATED_API_KEY")
        ded_secret = os.getenv("COINBASE_DEDICATED_API_SECRET")
        if ded_key and ded_secret:
            try:
                self._dedicated_client = RESTClient(api_key=ded_key, api_secret=ded_secret)
                verify_ticker = self.config.live_tickers[0] if self.config.live_tickers else "DOGE-USD"
                product = self._dedicated_client.get_product(verify_ticker)
                if product:
                    price = float(self._resp(product, "price", 0))
                    self._store_product_limits(verify_ticker, product)
                    logger.info(
                        f"AGAPE-SPOT Executor: Account 2 (dedicated) connected. "
                        f"{verify_ticker} = ${price:,.2f}"
                    )
            except Exception as e:
                logger.error(f"AGAPE-SPOT Executor: Account 2 init failed: {e}")
                self._dedicated_client = None

        # --- Optional per-ticker overrides ---
        for ticker in self.config.tickers:
            symbol = SPOT_TICKERS.get(ticker, {}).get("symbol", ticker.split("-")[0])
            env_key = f"COINBASE_{symbol.upper()}_API_KEY"
            env_secret = f"COINBASE_{symbol.upper()}_API_SECRET"
            tk_api_key = os.getenv(env_key)
            tk_api_secret = os.getenv(env_secret)

            if tk_api_key and tk_api_secret:
                try:
                    client = RESTClient(api_key=tk_api_key, api_secret=tk_api_secret)
                    product = client.get_product(ticker)
                    if product:
                        price = float(self._resp(product, "price", 0))
                        self._store_product_limits(ticker, product)
                        logger.info(
                            f"AGAPE-SPOT Executor: {symbol} per-ticker override connected. "
                            f"{ticker} = ${price:,.2f}"
                        )
                    self._ticker_clients[ticker] = client
                except Exception as e:
                    logger.error(
                        f"AGAPE-SPOT Executor: {symbol} per-ticker override failed: {e}"
                    )

        if not self._client and not self._dedicated_client:
            logger.error(
                "AGAPE-SPOT Executor: No Coinbase clients initialized. "
                "Set COINBASE_API_KEY/SECRET and/or COINBASE_DEDICATED_API_KEY/SECRET."
            )

        # --- Startup balance check: log each account's USD so we can
        #     verify in production that both keys point to different accounts ---
        if self._client:
            bal = self._get_usd_balance_from_client(self._client, account_label="default")
            logger.info(f"AGAPE-SPOT INIT: default account cash = ${bal or 0:.2f}")
        if self._dedicated_client:
            bal = self._get_usd_balance_from_client(self._dedicated_client, account_label="dedicated")
            logger.info(f"AGAPE-SPOT INIT: dedicated account cash = ${bal or 0:.2f}")

    def _get_client(self, ticker: str) -> Optional[object]:
        """Get any available Coinbase client for a ticker.

        Priority: per-ticker override → default → dedicated.
        Used for price lookups and other non-account-specific operations.
        """
        return (self._ticker_clients.get(ticker)
                or self._client
                or self._dedicated_client)

    def _get_client_for_account(self, ticker: str, account_label: str) -> Optional[object]:
        """Get the Coinbase client for a specific account label.

        'default'   → Account 1 (COINBASE_API_KEY)
        'dedicated' → Account 2 (COINBASE_DEDICATED_API_KEY)
        'paper'     → None

        Also handles legacy labels (e.g. 'DOGE', 'XRP') from old positions
        by routing them to the dedicated client.
        """
        if account_label == "paper":
            return None
        if account_label == "default":
            return self._client
        if account_label == "dedicated":
            return self._dedicated_client
        # Legacy: old positions have symbol-based labels (e.g. "DOGE", "XRP")
        # Route them to per-ticker override if exists, else dedicated client
        if ticker in self._ticker_clients:
            return self._ticker_clients[ticker]
        return self._dedicated_client

    def get_all_accounts(self, ticker: str) -> list:
        """Return all (account_label, is_live) pairs available for a ticker.

        Both accounts trade ALL live tickers:
          ("default", True)    -- Account 1 (COINBASE_API_KEY)
          ("dedicated", True)  -- Account 2 (COINBASE_DEDICATED_API_KEY)
          ("paper", False)     -- paper tracking

        Each signal opens independent positions on EVERY returned account.
        """
        accounts = []

        if self.config.is_live(ticker):
            if self._client is not None:
                accounts.append(("default", True))
            if self._dedicated_client is not None:
                accounts.append(("dedicated", True))
            accounts.append(("paper", False))
        else:
            accounts.append(("paper", False))

        return accounts

    @property
    def has_any_client(self) -> bool:
        """True if at least one Coinbase client is connected."""
        return (self._client is not None
                or self._dedicated_client is not None
                or bool(self._ticker_clients))

    # =========================================================================
    # Volatility: ATR + Chop Detection (from Coinbase candles)
    # =========================================================================

    def get_atr(
        self, ticker: str, periods: int = 14, granularity: str = "FIVE_MINUTE",
    ) -> Optional[float]:
        """Calculate Average True Range from Coinbase candles.

        ATR measures actual price volatility — how much a coin moves per
        candle. Used to size stops to real market conditions instead of
        fixed percentages that get whipsawed in choppy markets.

        Args:
            ticker: e.g. "ETH-USD"
            periods: ATR lookback (default 14 candles)
            granularity: Candle size. FIVE_MINUTE for scalping, ONE_HOUR for swing.

        Returns:
            ATR as a dollar value, or None if candles unavailable.
        """
        client = self._get_client(ticker)
        if not client:
            return None

        try:
            # Fetch enough candles for ATR calculation (periods + 1 for TR)
            import time
            now_ts = str(int(time.time()))
            # granularity seconds: FIVE_MINUTE=300, FIFTEEN_MINUTE=900, ONE_HOUR=3600
            gran_secs = {"ONE_MINUTE": 60, "FIVE_MINUTE": 300, "FIFTEEN_MINUTE": 900, "ONE_HOUR": 3600}
            secs = gran_secs.get(granularity, 300)
            start_ts = str(int(time.time()) - secs * (periods + 5))

            candles_resp = client.get_candles(
                product_id=ticker,
                start=start_ts,
                end=now_ts,
                granularity=granularity,
            )
            candles = self._resp(candles_resp, "candles", [])
            if not candles or len(candles) < periods:
                logger.debug(
                    f"AGAPE-SPOT ATR: Not enough candles for {ticker} "
                    f"({len(candles) if candles else 0}/{periods})"
                )
                return None

            # Candles: [{start, low, high, open, close, volume}, ...]
            # Sort by timestamp ascending (Coinbase returns newest first)
            candles = sorted(candles, key=lambda c: int(self._resp(c, "start", "0")))

            # Calculate True Range for each candle
            true_ranges = []
            for i in range(1, len(candles)):
                high = float(self._resp(candles[i], "high", 0))
                low = float(self._resp(candles[i], "low", 0))
                prev_close = float(self._resp(candles[i - 1], "close", 0))

                if high <= 0 or low <= 0 or prev_close <= 0:
                    continue

                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close),
                )
                true_ranges.append(tr)

            if len(true_ranges) < periods:
                return None

            # Simple moving average of last N true ranges
            atr = sum(true_ranges[-periods:]) / periods
            return atr

        except Exception as e:
            logger.debug(f"AGAPE-SPOT ATR: Failed for {ticker}: {e}")
            return None

    def get_volatility_context(
        self, ticker: str, periods: int = 14,
    ) -> Dict[str, Any]:
        """Get ATR + chop index + RSI for a ticker.

        Returns:
            {
                "atr": float,           # Average True Range ($)
                "atr_pct": float,       # ATR as % of current price
                "chop_index": float,    # 0-1, high = choppy
                "is_choppy": bool,      # True if chop_index > 0.65
                "regime": str,          # TRENDING / CHOPPY / UNKNOWN
                "rsi": float,           # RSI(14) on 5-min candles, 0-100
                "spot_price": float,    # Current price (latest close)
            }
        """
        result: Dict[str, Any] = {
            "atr": None,
            "atr_pct": None,
            "chop_index": None,
            "is_choppy": False,
            "regime": "UNKNOWN",
            "rsi": None,
            "spot_price": None,
        }

        client = self._get_client(ticker)
        if not client:
            return result

        try:
            import time
            now_ts = str(int(time.time()))
            # Use 5-min candles, 20 periods for chop calculation
            lookback = max(periods + 5, 25)
            start_ts = str(int(time.time()) - 300 * lookback)

            candles_resp = client.get_candles(
                product_id=ticker,
                start=start_ts,
                end=now_ts,
                granularity="FIVE_MINUTE",
            )
            candles = self._resp(candles_resp, "candles", [])
            if not candles or len(candles) < periods + 1:
                return result

            candles = sorted(candles, key=lambda c: int(self._resp(c, "start", "0")))

            # Extract close prices and calculate TR
            closes = []
            true_ranges = []
            for i, c in enumerate(candles):
                close = float(self._resp(c, "close", 0))
                high = float(self._resp(c, "high", 0))
                low = float(self._resp(c, "low", 0))
                if close <= 0:
                    continue
                closes.append(close)
                if i > 0:
                    prev_close = float(self._resp(candles[i - 1], "close", 0))
                    if prev_close > 0 and high > 0 and low > 0:
                        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                        true_ranges.append(tr)

            if len(true_ranges) < periods or len(closes) < periods + 1:
                return result

            # ATR = average of last N true ranges
            atr = sum(true_ranges[-periods:]) / periods
            current_price = closes[-1]
            atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

            result["atr"] = atr
            result["atr_pct"] = round(atr_pct, 4)

            # Kaufman Efficiency Ratio (chop detection)
            # ER = abs(net_move) / sum(abs(individual_moves))
            # ER near 1 = trending, ER near 0 = choppy
            recent_closes = closes[-(periods + 1):]
            net_move = abs(recent_closes[-1] - recent_closes[0])
            path_length = sum(
                abs(recent_closes[i] - recent_closes[i - 1])
                for i in range(1, len(recent_closes))
            )

            if path_length > 0:
                efficiency_ratio = net_move / path_length  # 0 = pure chop, 1 = pure trend
                chop_index = 1.0 - efficiency_ratio  # Invert: 1 = pure chop, 0 = pure trend
            else:
                chop_index = 1.0  # No movement = max chop

            result["chop_index"] = round(chop_index, 4)
            result["is_choppy"] = chop_index > 0.65
            result["regime"] = "CHOPPY" if chop_index > 0.65 else "TRENDING"
            result["spot_price"] = current_price

            # RSI(14) on 1-MINUTE candles for fast scalping entries/exits.
            # Separate API call from the 5-min ATR/chop candles because
            # 1-min RSI is more responsive for mean-reversion timing.
            result["rsi"] = self.get_rsi(ticker, periods=periods)

            return result

        except Exception as e:
            logger.debug(f"AGAPE-SPOT volatility context: Failed for {ticker}: {e}")
            return result

    def get_rsi(
        self, ticker: str, periods: int = 14,
    ) -> Optional[float]:
        """Calculate RSI on 1-MINUTE candles (Wilder smoothing).

        Uses 1-min granularity for fast mean-reversion timing:
        - RSI < 30 = oversold → biggest buying opportunity in range-bound markets
        - RSI > 70 = overbought → take profit exit signal

        Separate from the 5-min candles used for ATR/chop because 1-min RSI
        is more responsive to short-term price swings in crypto scalping.

        Returns:
            RSI value (0-100), or None if candles unavailable.
        """
        client = self._get_client(ticker)
        if not client:
            return None

        try:
            import time
            now_ts = str(int(time.time()))
            # 1-min candles: need periods + 5 buffer candles
            lookback = periods + 10
            start_ts = str(int(time.time()) - 60 * lookback)

            candles_resp = client.get_candles(
                product_id=ticker,
                start=start_ts,
                end=now_ts,
                granularity="ONE_MINUTE",
            )
            candles = self._resp(candles_resp, "candles", [])
            if not candles or len(candles) < periods + 1:
                return None

            candles = sorted(candles, key=lambda c: int(self._resp(c, "start", "0")))

            closes = []
            for c in candles:
                close = float(self._resp(c, "close", 0))
                if close > 0:
                    closes.append(close)

            if len(closes) < periods + 1:
                return None

            # Wilder smoothed RSI: SMA seed then EMA
            gains = []
            losses = []
            for i in range(1, len(closes)):
                delta = closes[i] - closes[i - 1]
                gains.append(max(delta, 0))
                losses.append(max(-delta, 0))

            if len(gains) < periods:
                return None

            avg_gain = sum(gains[:periods]) / periods
            avg_loss = sum(losses[:periods]) / periods
            for j in range(periods, len(gains)):
                avg_gain = (avg_gain * (periods - 1) + gains[j]) / periods
                avg_loss = (avg_loss * (periods - 1) + losses[j]) / periods

            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))
            else:
                rsi = 100.0

            return round(rsi, 2)

        except Exception as e:
            logger.debug(f"AGAPE-SPOT RSI: Failed for {ticker}: {e}")
            return None

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _price_decimals(ticker: str) -> int:
        """Get the number of decimal places for a ticker's price."""
        return SPOT_TICKERS.get(ticker, {}).get("price_decimals", 2)

    @staticmethod
    def _resp(obj, key, default=None):
        """Safely get a value from a Coinbase SDK response or dict.

        The coinbase-advanced-py SDK returns typed response objects (not dicts).
        They support attribute access (obj.key) and bracket access (obj[key])
        via __getitem__, but NOT .get().
        """
        # Attribute access (SDK response objects)
        if hasattr(obj, key):
            val = getattr(obj, key)
            return val if val is not None else default
        # Dict access
        if isinstance(obj, dict):
            return obj.get(key, default)
        return default

    # =========================================================================
    # Fee extraction (robust, with fallbacks)
    # =========================================================================

    # Coinbase Advanced Trade fee rates.
    # Observed from live trades (Feb 2026): 1.2-1.4% per side on small orders.
    # Coinbase charges higher rates on sub-$10K monthly volume.
    # Taker: ~1.2% (market orders), Maker: ~0.6% (limit orders)
    COINBASE_TAKER_FEE_RATE = 0.012  # 1.20% — observed from live fills
    COINBASE_MAKER_FEE_RATE = 0.006  # 0.60% — estimated maker tier

    def _extract_fee_from_fills(
        self, fills_list: list, side: str, ticker: str,
    ) -> Optional[float]:
        """Extract total fee from Coinbase fill objects.

        Tries multiple field names because the Coinbase SDK has changed
        field names across versions:
          - "commission" (documented in REST API)
          - "trade_commission" (some SDK versions)
          - "fee" (older SDK versions)

        Also tries to derive fee from size_in_quote when commission
        fields are unavailable: fee = size_in_quote - (price * size).

        Args:
            fills_list: List of fill objects from client.get_fills()
            side: "buy" or "sell" — for logging context
            ticker: Ticker symbol for logging

        Returns:
            Total fee in USD, or None if extraction failed entirely.
        """
        if not fills_list:
            return None

        total_fee = 0.0
        extraction_method = None

        # --- Attempt 1: Direct commission field ---
        # Try multiple field names that Coinbase SDK has used
        for fee_field in ("commission", "trade_commission", "fee"):
            try:
                field_fee = 0.0
                field_found = False
                for f in fills_list:
                    raw_val = self._resp(f, fee_field)
                    if raw_val is not None and raw_val != "" and raw_val != "0":
                        field_found = True
                        parsed = float(raw_val)
                        if parsed > 0:
                            field_fee += parsed
                if field_found and field_fee > 0:
                    total_fee = field_fee
                    extraction_method = fee_field
                    break
            except (ValueError, TypeError):
                continue

        # --- Attempt 2: Derive from size_in_quote ---
        # size_in_quote = total USD value INCLUDING fee for a buy,
        # or total USD received MINUS fee for a sell.
        # fee = |size_in_quote - (price * size)|
        if total_fee == 0:
            try:
                derived_fee = 0.0
                for f in fills_list:
                    siq = self._resp(f, "size_in_quote")
                    price = self._resp(f, "price")
                    size = self._resp(f, "size")
                    if siq is not None and price is not None and size is not None:
                        siq_f = float(siq)
                        price_f = float(price)
                        size_f = float(size)
                        if siq_f > 0 and price_f > 0 and size_f > 0:
                            raw_value = price_f * size_f
                            fill_fee = abs(siq_f - raw_value)
                            # Sanity: fee should be < 5% of trade value
                            if fill_fee < raw_value * 0.05:
                                derived_fee += fill_fee
                if derived_fee > 0:
                    total_fee = derived_fee
                    extraction_method = "size_in_quote_derived"
            except (ValueError, TypeError):
                pass

        if total_fee > 0:
            total_fee = round(total_fee, 6)
            logger.info(
                f"AGAPE-SPOT FEE: {side} {ticker} fee=${total_fee:.6f} "
                f"(method={extraction_method}, fills={len(fills_list)})"
            )
            return total_fee

        # Log what we actually got for debugging
        if fills_list:
            try:
                sample = fills_list[0]
                debug_fields = {}
                for field_name in ("commission", "trade_commission", "fee", "size_in_quote", "price", "size"):
                    val = self._resp(sample, field_name)
                    debug_fields[field_name] = repr(val)
                logger.warning(
                    f"AGAPE-SPOT FEE: {side} {ticker} — could not extract fee "
                    f"from {len(fills_list)} fills. Sample fill fields: {debug_fields}"
                )
            except Exception:
                logger.warning(
                    f"AGAPE-SPOT FEE: {side} {ticker} — could not extract fee "
                    f"from {len(fills_list)} fills (debug logging also failed)"
                )

        return None

    def _get_fee_from_order(
        self, client, order_id: str, side: str, ticker: str,
    ) -> Optional[float]:
        """Fetch fee from the order object itself via get_order().

        Coinbase order objects contain 'total_fees' which is the
        authoritative fee for the entire order. This is more reliable
        than summing fill-level commissions.

        Args:
            client: Coinbase REST client
            order_id: The Coinbase order ID
            side: "buy" or "sell" — for logging
            ticker: Ticker symbol for logging

        Returns:
            Fee in USD, or None if unavailable.
        """
        try:
            order_resp = client.get_order(order_id=str(order_id))
            if order_resp:
                # Try 'total_fees' (primary)
                total_fees = self._resp(order_resp, "total_fees")
                if total_fees is not None and total_fees != "" and total_fees != "0":
                    fee = float(total_fees)
                    if fee > 0:
                        logger.info(
                            f"AGAPE-SPOT FEE: {side} {ticker} fee=${fee:.6f} "
                            f"(method=get_order.total_fees)"
                        )
                        return round(fee, 6)

                # Try nested order_configuration.total_fees or similar
                order_config = self._resp(order_resp, "order_configuration")
                if order_config:
                    tf = self._resp(order_config, "total_fees")
                    if tf is not None and tf != "" and tf != "0":
                        fee = float(tf)
                        if fee > 0:
                            logger.info(
                                f"AGAPE-SPOT FEE: {side} {ticker} fee=${fee:.6f} "
                                f"(method=get_order.order_config.total_fees)"
                            )
                            return round(fee, 6)
        except Exception as e:
            logger.debug(
                f"AGAPE-SPOT FEE: get_order fee lookup failed for {ticker} "
                f"order={order_id}: {e}"
            )
        return None

    def _estimate_fee(
        self, fill_price: float, quantity: float, ticker: str, side: str,
        order_type: str = "market",
    ) -> float:
        """Estimate fee using Coinbase fee rate when extraction fails.

        Uses maker rate for limit orders, taker rate for market orders.
        This is a last resort. The estimated fee is tagged as estimated
        in logs so you can distinguish real vs estimated fees in analysis.

        Returns:
            Estimated fee in USD (always > 0).
        """
        notional = fill_price * quantity
        rate = self.COINBASE_MAKER_FEE_RATE if order_type == "limit" else self.COINBASE_TAKER_FEE_RATE
        estimated_fee = round(notional * rate, 6)
        logger.info(
            f"AGAPE-SPOT FEE: {side} {ticker} fee=${estimated_fee:.6f} "
            f"(method=ESTIMATED, rate={rate:.3%}, "
            f"order_type={order_type}, notional=${notional:.2f})"
        )
        return estimated_fee

    def _resolve_fee(
        self,
        client,
        fills_list: list,
        order_id: str,
        fill_price: float,
        quantity: float,
        ticker: str,
        side: str,
        order_type: str = "market",
    ) -> float:
        """Resolve the fee for a trade using all available methods.

        Priority:
          1. Extract from fill objects (commission / size_in_quote)
          2. Fetch from order object (get_order → total_fees)
          3. Estimate from notional × fee rate (maker for limit, taker for market)

        Always returns a fee > 0. Never returns None.
        """
        # 1. Try fills
        fee = self._extract_fee_from_fills(fills_list, side, ticker)
        if fee is not None and fee > 0:
            return fee

        # 2. Try order-level fee
        if client and order_id:
            fee = self._get_fee_from_order(client, order_id, side, ticker)
            if fee is not None and fee > 0:
                return fee

        # 3. Estimate (uses maker rate for limit orders, taker for market)
        return self._estimate_fee(fill_price, quantity, ticker, side, order_type)

    def _get_usd_balance_from_client(self, client, account_label: str = "unknown") -> Optional[float]:
        """Get available USD + USDC cash balance from a Coinbase client.

        Returns the CASH available to trade (not crypto holdings).

        Compounding works naturally:
          1. Start with $100 USD
          2. Buy 0.037 ETH ($100) → USD drops to ~$0
          3. ETH goes up 3%, sell → $103 USD back
          4. Next trade: $103 × 90% = $92.70 position (compounded!)

        The key is that after a profitable sell, USD increases. Each new
        trade is sized from the current USD balance, which includes all
        prior profits. No artificial capital tracking needed.

        Logs at INFO level so we can see actual balance in production.
        """
        if not client:
            return None
        try:
            usd_balance = None
            usdc_balance = None
            cursor = None
            total_scanned = 0
            top_holdings = []

            for page in range(20):
                kwargs = {"limit": 250}
                if cursor:
                    kwargs["cursor"] = cursor

                accounts = client.get_accounts(**kwargs)
                acct_list = self._resp(accounts, "accounts", [])
                if not acct_list:
                    break

                for acct in acct_list:
                    currency = self._resp(acct, "currency", "")
                    avail_bal = self._resp(acct, "available_balance", {})
                    val = float(self._resp(avail_bal, "value", 0))
                    total_scanned += 1

                    if currency == "USD":
                        usd_balance = val
                    elif currency == "USDC":
                        usdc_balance = val

                    # Track top holdings for visibility
                    if val > 0:
                        top_holdings.append(f"{currency}={val}")

                # Don't return early — scan ALL pages to find USD + USDC
                next_cursor = self._resp(accounts, "cursor", None)
                if not next_cursor or next_cursor == cursor:
                    break
                cursor = next_cursor

            # Combine USD + USDC (both are dollar-denominated cash)
            cash = (usd_balance or 0) + (usdc_balance or 0)

            # Always log at INFO — we need to see this in production
            logger.info(
                f"AGAPE-SPOT BALANCE [{account_label}]: USD=${usd_balance or 0:.2f}, "
                f"USDC=${usdc_balance or 0:.2f}, "
                f"TOTAL CASH=${cash:.2f} "
                f"({total_scanned} accounts scanned). "
                f"Top holdings: {top_holdings[:10]}"
            )

            if cash > 0:
                return cash

            # $0 cash — all money is deployed in crypto positions
            # This is normal when a position is open (max_positions=1)
            if top_holdings:
                logger.info(
                    f"AGAPE-SPOT BALANCE [{account_label}]: $0 cash but have crypto holdings. "
                    f"This is normal when a position is open."
                )
            else:
                logger.warning(
                    f"AGAPE-SPOT BALANCE [{account_label}]: $0 total across {total_scanned} "
                    f"accounts — account may be empty"
                )
            return None
        except Exception as e:
            logger.warning(f"AGAPE-SPOT BALANCE [{account_label}]: Lookup failed: {e}")
        return None

    def _store_product_limits(self, ticker: str, product) -> None:
        """Extract and store base_min_size/quote_min_size from a Coinbase product response."""
        try:
            base_min = float(self._resp(product, "base_min_size", 0))
            quote_min = float(self._resp(product, "quote_min_size", 0))
            base_inc = float(self._resp(product, "base_increment", 0))
            self._product_limits[ticker] = {
                "base_min_size": base_min,
                "quote_min_size": quote_min,
                "base_increment": base_inc,
            }
            logger.info(
                f"AGAPE-SPOT Executor: {ticker} limits — "
                f"base_min={base_min}, quote_min=${quote_min}, "
                f"base_increment={base_inc}"
            )
        except Exception as e:
            logger.warning(f"AGAPE-SPOT Executor: Could not parse product limits for {ticker}: {e}")

    def get_min_notional(self, ticker: str) -> float:
        """Get the minimum notional (USD) for a ticker.

        Priority: Coinbase API quote_min_size (fetched at init) > config min_notional_usd > $2 default.
        Adds a 10% buffer above the Coinbase minimum to avoid edge-case rejects from price slippage.
        """
        # Use real Coinbase limit if fetched
        limits = self._product_limits.get(ticker)
        if limits and limits.get("quote_min_size", 0) > 0:
            return limits["quote_min_size"] * 1.1  # 10% buffer

        # Fall back to config
        return SPOT_TICKERS.get(ticker, {}).get("min_notional_usd", 2.0)

    def get_min_base_size(self, ticker: str) -> float:
        """Get the minimum base quantity for a ticker from Coinbase product data."""
        limits = self._product_limits.get(ticker)
        if limits and limits.get("base_min_size", 0) > 0:
            return limits["base_min_size"]
        return SPOT_TICKERS.get(ticker, {}).get("min_order", 0.001)

    # =========================================================================
    # Limit order support — reduces fees from 0.6% taker to 0.4% maker
    # =========================================================================

    def get_best_bid_ask(self, ticker: str, client=None) -> Tuple[Optional[float], Optional[float]]:
        """Get best bid/ask from Coinbase product book.

        Returns (best_bid, best_ask) or (None, None) on failure.
        Uses the product ticker endpoint which includes bid/ask.
        """
        if client is None:
            client = self._get_client(ticker)
        if not client:
            return (None, None)
        try:
            product = client.get_product(ticker)
            if product:
                bid = self._resp(product, "bid")
                ask = self._resp(product, "ask")
                if bid is not None and ask is not None:
                    return (float(bid), float(ask))
                # Fallback: use price as mid
                price = self._resp(product, "price")
                if price:
                    p = float(price)
                    # Estimate spread as 0.02% for majors, 0.05% for alts
                    spread_pct = 0.0002 if ticker in ("ETH-USD", "BTC-USD") else 0.0005
                    return (p * (1 - spread_pct), p * (1 + spread_pct))
        except Exception as e:
            logger.debug(f"AGAPE-SPOT Executor: Bid/ask lookup failed for {ticker}: {e}")
        return (None, None)

    def _place_limit_buy(
        self, client, ticker: str, quantity: float, limit_price: float,
        client_order_id: str,
    ) -> Tuple[bool, Optional[object], str]:
        """Place a limit GTC buy and wait for fill, falling back to market order.

        Returns (success, order_response, order_type) where order_type is
        'limit' or 'market'.
        """
        timeout = self.config.limit_order_timeout_seconds
        pd_val = SPOT_TICKERS.get(ticker, {}).get("price_decimals", 2)

        try:
            logger.info(
                f"AGAPE-SPOT: PLACING LIMIT BUY {ticker} "
                f"qty={quantity} limit=${limit_price:.{pd_val}f} "
                f"timeout={timeout}s"
            )
            order = client.limit_order_gtc_buy(
                client_order_id=client_order_id,
                product_id=ticker,
                base_size=str(quantity),
                limit_price=str(round(limit_price, pd_val)),
            )

            success = self._resp(order, "success", False)
            if not success:
                # Limit rejected — fall back to market
                logger.warning(
                    f"AGAPE-SPOT: Limit buy rejected for {ticker}, "
                    f"falling back to market order"
                )
                return self._place_market_buy_fallback(
                    client, ticker, quantity,
                )

            # Wait for fill
            success_resp = self._resp(order, "success_response")
            order_id = self._resp(success_resp, "order_id", "")

            import time
            fill_wait = 0
            poll_interval = 2  # seconds
            while fill_wait < timeout:
                time.sleep(poll_interval)
                fill_wait += poll_interval
                try:
                    order_status = client.get_order(order_id=str(order_id))
                    status = self._resp(order_status, "status", "")
                    if status in ("FILLED", "COMPLETED"):
                        logger.info(
                            f"AGAPE-SPOT: Limit buy FILLED {ticker} "
                            f"in {fill_wait}s (maker fee)"
                        )
                        return (True, order, "limit")
                    if status in ("CANCELLED", "EXPIRED", "FAILED"):
                        logger.info(
                            f"AGAPE-SPOT: Limit buy {status} {ticker}, "
                            f"falling back to market"
                        )
                        return self._place_market_buy_fallback(
                            client, ticker, quantity,
                        )
                except Exception:
                    pass

            # Timeout — cancel and fall back to market
            try:
                client.cancel_orders(order_ids=[str(order_id)])
                logger.info(
                    f"AGAPE-SPOT: Limit buy TIMED OUT {ticker} "
                    f"after {timeout}s, cancelled → market fallback"
                )
            except Exception as ce:
                logger.debug(f"AGAPE-SPOT: Cancel failed: {ce}")

            return self._place_market_buy_fallback(
                client, ticker, quantity,
            )

        except Exception as e:
            logger.warning(
                f"AGAPE-SPOT: Limit buy exception for {ticker}: {e}, "
                f"falling back to market"
            )
            return self._place_market_buy_fallback(
                client, ticker, quantity,
            )

    def _place_market_buy_fallback(
        self, client, ticker: str, quantity: float,
    ) -> Tuple[bool, Optional[object], str]:
        """Market order fallback when limit order fails."""
        fallback_id = str(uuid.uuid4())
        try:
            order = client.market_order_buy(
                client_order_id=fallback_id,
                product_id=ticker,
                base_size=str(quantity),
            )
            success = self._resp(order, "success", False)
            return (success, order, "market")
        except Exception as e:
            logger.error(f"AGAPE-SPOT: Market buy fallback also failed: {e}")
            return (False, None, "market")

    def _place_limit_sell(
        self, client, ticker: str, quantity: float, limit_price: float,
        client_order_id: str,
    ) -> Tuple[bool, Optional[object], str]:
        """Place a limit GTC sell and wait for fill, falling back to market order.

        Returns (success, order_response, order_type).
        """
        timeout = self.config.limit_order_timeout_seconds
        pd_val = SPOT_TICKERS.get(ticker, {}).get("price_decimals", 2)

        try:
            logger.info(
                f"AGAPE-SPOT: PLACING LIMIT SELL {ticker} "
                f"qty={quantity} limit=${limit_price:.{pd_val}f} "
                f"timeout={timeout}s"
            )
            order = client.limit_order_gtc_sell(
                client_order_id=client_order_id,
                product_id=ticker,
                base_size=str(quantity),
                limit_price=str(round(limit_price, pd_val)),
            )

            success = self._resp(order, "success", False)
            if not success:
                logger.warning(
                    f"AGAPE-SPOT: Limit sell rejected for {ticker}, "
                    f"falling back to market"
                )
                return self._place_market_sell_fallback(
                    client, ticker, quantity,
                )

            success_resp = self._resp(order, "success_response")
            order_id = self._resp(success_resp, "order_id", "")

            import time
            fill_wait = 0
            poll_interval = 2
            while fill_wait < timeout:
                time.sleep(poll_interval)
                fill_wait += poll_interval
                try:
                    order_status = client.get_order(order_id=str(order_id))
                    status = self._resp(order_status, "status", "")
                    if status in ("FILLED", "COMPLETED"):
                        logger.info(
                            f"AGAPE-SPOT: Limit sell FILLED {ticker} "
                            f"in {fill_wait}s (maker fee)"
                        )
                        return (True, order, "limit")
                    if status in ("CANCELLED", "EXPIRED", "FAILED"):
                        logger.info(
                            f"AGAPE-SPOT: Limit sell {status} {ticker}, "
                            f"falling back to market"
                        )
                        return self._place_market_sell_fallback(
                            client, ticker, quantity,
                        )
                except Exception:
                    pass

            try:
                client.cancel_orders(order_ids=[str(order_id)])
                logger.info(
                    f"AGAPE-SPOT: Limit sell TIMED OUT {ticker} "
                    f"after {timeout}s, cancelled → market fallback"
                )
            except Exception as ce:
                logger.debug(f"AGAPE-SPOT: Cancel failed: {ce}")

            return self._place_market_sell_fallback(
                client, ticker, quantity,
            )

        except Exception as e:
            logger.warning(
                f"AGAPE-SPOT: Limit sell exception for {ticker}: {e}, "
                f"falling back to market"
            )
            return self._place_market_sell_fallback(
                client, ticker, quantity,
            )

    def _place_market_sell_fallback(
        self, client, ticker: str, quantity: float,
    ) -> Tuple[bool, Optional[object], str]:
        """Market order fallback when limit sell fails."""
        fallback_id = str(uuid.uuid4())
        try:
            order = client.market_order_sell(
                client_order_id=fallback_id,
                product_id=ticker,
                base_size=str(quantity),
            )
            success = self._resp(order, "success", False)
            return (success, order, "market")
        except Exception as e:
            logger.error(f"AGAPE-SPOT: Market sell fallback also failed: {e}")
            return (False, None, "market")

    # =========================================================================
    # Trade execution
    # =========================================================================

    def execute_trade(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        """Execute a long-only spot trade for signal.ticker (single-account legacy path)."""
        if not signal.is_valid:
            logger.warning(
                f"AGAPE-SPOT Executor: Invalid signal for {signal.ticker}, skipping"
            )
            return None

        if self.config.is_live(signal.ticker):
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def execute_trade_on_account(
        self,
        signal: AgapeSpotSignal,
        account_label: str,
        is_live: bool,
    ) -> Optional[AgapeSpotPosition]:
        """Execute a trade on a specific account.

        account_label: 'default', '{SYMBOL}', or 'paper'
        is_live: True → Coinbase order, False → simulated
        """
        if not signal.is_valid:
            return None

        if is_live:
            client = self._get_client_for_account(signal.ticker, account_label)
            if not client:
                logger.warning(
                    f"AGAPE-SPOT: No client for {signal.ticker} account={account_label}, "
                    f"skipping live execution"
                )
                return None
            position = self._execute_live(signal, client=client, account_label=account_label)
        else:
            position = self._execute_paper(signal, account_label=account_label)

        return position

    def _execute_paper(self, signal: AgapeSpotSignal, account_label: str = "paper") -> Optional[AgapeSpotPosition]:
        """Simulate a long-only spot buy with slippage.

        Only used for paper-only tickers (no live accounts).
        When live accounts exist, use execute_paper_mirror() instead
        so paper tracks the exact same fill price and quantity.
        """
        try:
            slippage = signal.spot_price * 0.001  # 0.1%
            fill_price = signal.spot_price + slippage  # Buying = pay more

            ticker_symbol = SPOT_TICKERS.get(signal.ticker, {}).get("symbol", signal.ticker.split("-")[0])
            acct_tag = account_label.upper()[:3] if account_label != "paper" else "PPR"
            position_id = f"SPOT-{ticker_symbol}-{acct_tag}-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)

            pd = self._price_decimals(signal.ticker)

            position = AgapeSpotPosition(
                position_id=position_id,
                ticker=signal.ticker,
                quantity=signal.quantity,
                entry_price=round(fill_price, pd),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                max_risk_usd=signal.max_risk_usd,
                underlying_at_entry=signal.spot_price,
                funding_rate_at_entry=signal.funding_rate,
                funding_regime_at_entry=signal.funding_regime,
                ls_ratio_at_entry=signal.ls_ratio,
                squeeze_risk_at_entry=signal.squeeze_risk,
                max_pain_at_entry=signal.max_pain,
                crypto_gex_at_entry=signal.crypto_gex,
                crypto_gex_regime_at_entry=signal.crypto_gex_regime,
                oracle_advice=signal.oracle_advice,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_confidence=signal.oracle_confidence,
                oracle_top_factors=signal.oracle_top_factors,
                signal_action=signal.action.value,
                signal_confidence=signal.confidence,
                signal_reasoning=signal.reasoning,
                atr_at_entry=signal.atr,
                atr_pct_at_entry=signal.atr_pct,
                chop_index_at_entry=signal.chop_index,
                status=PositionStatus.OPEN,
                open_time=now,
                high_water_mark=round(fill_price, pd),
                account_label=account_label,
                # Estimate entry fee: Coinbase taker fee ~0.6% for market orders
                entry_fee_usd=round(signal.quantity * fill_price * 0.006, 4),
            )

            notional = signal.quantity * fill_price
            logger.info(
                f"AGAPE-SPOT: PAPER BUY [{account_label}] {signal.ticker} "
                f"{signal.quantity:.4f} (${notional:.2f}) @ ${fill_price:.{pd}f} "
                f"(est fee ${position.entry_fee_usd:.4f})"
            )
            return position

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Paper execution failed: {e}")
            return None

    def execute_paper_mirror(
        self,
        signal: AgapeSpotSignal,
        live_fill_price: float,
        live_quantity: float,
        account_label: str = "paper",
    ) -> Optional[AgapeSpotPosition]:
        """Create a paper position that mirrors a live fill exactly.

        Uses the SAME fill price and quantity as the live order so paper
        tracks identical performance to live — one trading agent, one result.
        """
        try:
            ticker_symbol = SPOT_TICKERS.get(signal.ticker, {}).get(
                "symbol", signal.ticker.split("-")[0],
            )
            position_id = f"SPOT-{ticker_symbol}-PPR-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)
            pd = self._price_decimals(signal.ticker)

            position = AgapeSpotPosition(
                position_id=position_id,
                ticker=signal.ticker,
                quantity=live_quantity,
                entry_price=round(live_fill_price, pd),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                max_risk_usd=signal.max_risk_usd,
                underlying_at_entry=signal.spot_price,
                funding_rate_at_entry=signal.funding_rate,
                funding_regime_at_entry=signal.funding_regime,
                ls_ratio_at_entry=signal.ls_ratio,
                squeeze_risk_at_entry=signal.squeeze_risk,
                max_pain_at_entry=signal.max_pain,
                crypto_gex_at_entry=signal.crypto_gex,
                crypto_gex_regime_at_entry=signal.crypto_gex_regime,
                oracle_advice=signal.oracle_advice,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_confidence=signal.oracle_confidence,
                oracle_top_factors=signal.oracle_top_factors,
                signal_action=signal.action.value,
                signal_confidence=signal.confidence,
                signal_reasoning=signal.reasoning,
                atr_at_entry=signal.atr,
                atr_pct_at_entry=signal.atr_pct,
                chop_index_at_entry=signal.chop_index,
                status=PositionStatus.OPEN,
                open_time=now,
                high_water_mark=round(live_fill_price, pd),
                account_label=account_label,
                # Estimate entry fee: Coinbase taker fee ~0.6% for market orders
                entry_fee_usd=round(live_quantity * live_fill_price * 0.006, 4),
            )

            notional = live_quantity * live_fill_price
            logger.info(
                f"AGAPE-SPOT: PAPER MIRROR [{account_label}] {signal.ticker} "
                f"{live_quantity:.4f} (${notional:.2f}) @ ${live_fill_price:.{pd}f} "
                f"(paper sizing, live price, est fee ${position.entry_fee_usd:.4f})"
            )
            return position

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Paper mirror failed: {e}")
            return None

    def _execute_live(
        self,
        signal: AgapeSpotSignal,
        client: Optional[object] = None,
        account_label: Optional[str] = None,
    ) -> Optional[AgapeSpotPosition]:
        """Execute a real long-only spot buy via Coinbase."""
        if client is None:
            client = self._get_client(signal.ticker)
        if account_label is None:
            account_label = "default"
        if not client:
            symbol = SPOT_TICKERS.get(signal.ticker, {}).get("symbol", signal.ticker.split("-")[0])
            logger.error(
                f"AGAPE-SPOT Executor: No Coinbase client for {signal.ticker} - "
                f"SKIPPING LIVE trade. Set COINBASE_API_KEY/SECRET "
                f"or COINBASE_{symbol}_API_KEY/SECRET."
            )
            # Log to DB so it shows up in the error dashboard
            if self.db:
                self.db.log(
                    "ERROR", "NO_COINBASE_CLIENT",
                    f"No Coinbase client for {signal.ticker}. "
                    f"Cannot execute live order.",
                    ticker=signal.ticker,
                )
            return None

        try:
            ticker_config = SPOT_TICKERS.get(signal.ticker, {})
            qty_decimals = ticker_config.get("quantity_decimals", 8)
            quantity = round(signal.quantity, qty_decimals)
            client_order_id = str(uuid.uuid4())

            # --- Balance-aware sizing with performance-based allocation ---
            #
            # Live accounts ALWAYS size from the REAL Coinbase USD balance.
            # No hardcoded fallbacks. If we can't read the balance, don't trade.
            # The allocator ranks tickers by performance and assigns each a %
            # of the available balance.
            usd_available = self._get_usd_balance_from_client(client, account_label=account_label)

            if usd_available is None:
                logger.error(
                    f"AGAPE-SPOT: CANNOT READ USD BALANCE [{account_label}] "
                    f"{signal.ticker} — skipping order. Check API key "
                    f"permissions and Coinbase account."
                )
                if self.db:
                    self.db.log(
                        "ERROR", "BALANCE_LOOKUP_FAILED",
                        f"[{account_label}] {signal.ticker}: "
                        f"Could not read USD balance from Coinbase. "
                        f"Cannot size order without real balance.",
                        ticker=signal.ticker,
                    )
                return None

            if usd_available <= 0:
                logger.warning(
                    f"AGAPE-SPOT: $0 USD [{account_label}] {signal.ticker} "
                    f"— skipping order"
                )
                if self.db:
                    self.db.log(
                        "WARNING", "NO_USD_BALANCE",
                        f"[{account_label}] {signal.ticker}: $0 available",
                        ticker=signal.ticker,
                    )
                return None

            # Size from real balance — use FULL available balance per trade.
            #
            # With max_positions=1 per ticker, the old allocator split the
            # balance 5 ways (one per ticker) even though only 1 trade opens
            # at a time.  Result: $50 balance → $9.50 per trade → $4.75 per
            # account → trades too small to overcome fees.
            #
            # New approach: use 90% of available USD for each trade.  The
            # Coinbase balance already reflects capital tied up in other open
            # positions (it's the AVAILABLE balance, not total balance).
            # Reserve 10% for fees + slippage headroom.
            usable_usd = usd_available * 0.90

            affordable_qty = usable_usd / signal.spot_price
            affordable_qty = round(affordable_qty, qty_decimals)

            logger.info(
                f"AGAPE-SPOT: SIZING [{account_label}] {signal.ticker} "
                f"balance=${usd_available:.2f}, usable=${usable_usd:.2f} "
                f"(90% of balance), qty={affordable_qty}"
            )
            if self.db:
                self.db.log(
                    "INFO", "FULL_BALANCE_SIZED",
                    f"[{account_label}] {signal.ticker}: "
                    f"balance=${usd_available:.2f}, "
                    f"usable=${usable_usd:.2f} (90%), "
                    f"qty={affordable_qty}",
                    ticker=signal.ticker,
                )
            quantity = affordable_qty

            notional_est = quantity * signal.spot_price
            min_notional = self.get_min_notional(signal.ticker)
            min_base = self.get_min_base_size(signal.ticker)
            if quantity < min_base or notional_est < min_notional:
                logger.warning(
                    f"AGAPE-SPOT: BUY SKIPPED {signal.ticker} — "
                    f"notional ${notional_est:.2f} (min ${min_notional:.2f}) "
                    f"or qty {quantity} (min {min_base})"
                )
                if self.db:
                    self.db.log(
                        "WARNING", "BELOW_MIN_NOTIONAL",
                        f"Buy skipped for {signal.ticker}: notional "
                        f"${notional_est:.2f} (min ${min_notional:.2f}), "
                        f"qty={quantity} (min {min_base}), "
                        f"price=${signal.spot_price:.4f}",
                        ticker=signal.ticker,
                    )
                return None

            logger.info(
                f"AGAPE-SPOT: PLACING LIVE BUY {signal.ticker} [{account_label}] "
                f"qty={quantity} base_size='{quantity}' "
                f"(~${notional_est:.2f}) client_order_id={client_order_id}"
            )

            # LONG-ONLY: Buy to open — use limit orders when enabled (lower fees)
            order_type = "market"
            if self.config.use_limit_orders:
                bid, ask = self.get_best_bid_ask(signal.ticker, client)
                if bid and ask:
                    # Place limit at ask - offset (aggressive, likely fills quickly)
                    offset = self.config.limit_order_offset_pct / 100
                    limit_price = ask * (1 - offset)
                    success, order, order_type = self._place_limit_buy(
                        client, signal.ticker, quantity, limit_price,
                        client_order_id,
                    )
                    if not success:
                        return None
                else:
                    # Can't get bid/ask — fall back to market order
                    logger.info(
                        f"AGAPE-SPOT: No bid/ask for {signal.ticker}, "
                        f"using market order"
                    )
                    order = client.market_order_buy(
                        client_order_id=client_order_id,
                        product_id=signal.ticker,
                        base_size=str(quantity),
                    )
            else:
                order = client.market_order_buy(
                    client_order_id=client_order_id,
                    product_id=signal.ticker,
                    base_size=str(quantity),
                )

            # Log the raw response for debugging
            try:
                if hasattr(order, "to_dict"):
                    logger.info(f"AGAPE-SPOT: Order response ({order_type}): {order.to_dict()}")
                else:
                    logger.info(f"AGAPE-SPOT: Order response ({order_type}): {order}")
            except Exception:
                logger.info(f"AGAPE-SPOT: Order response type={type(order).__name__}")

            # Check success -- SDK returns typed object, not dict
            success = self._resp(order, "success", False)

            if success:
                # Get order_id from success_response
                success_resp = self._resp(order, "success_response")
                order_id = self._resp(success_resp, "order_id", client_order_id[:8])

                fill_price = signal.spot_price
                fills_list = []
                try:
                    fills = client.get_fills(order_id=str(order_id))
                    fills_list = self._resp(fills, "fills", [])
                    if fills_list:
                        total_value = sum(
                            float(self._resp(f, "price", 0))
                            * float(self._resp(f, "size", 0))
                            for f in fills_list
                        )
                        total_size = sum(
                            float(self._resp(f, "size", 0))
                            for f in fills_list
                        )
                        if total_size > 0:
                            fill_price = total_value / total_size
                except Exception as fe:
                    logger.debug(f"AGAPE-SPOT: Fill lookup skipped: {fe}")

                ticker_symbol = ticker_config.get("symbol", signal.ticker.split("-")[0])
                position_id = f"SPOT-{ticker_symbol}-{str(order_id)[:8]}"
                now = datetime.now(CENTRAL_TZ)

                pd = self._price_decimals(signal.ticker)

                # Calculate entry slippage (fill vs signal price)
                entry_slippage = (
                    round((fill_price - signal.spot_price) / signal.spot_price * 100, 4)
                    if signal.spot_price > 0 else None
                )

                # Extract fee using robust multi-method resolution
                entry_fee = self._resolve_fee(
                    client, fills_list, order_id,
                    fill_price, quantity,
                    signal.ticker, "buy",
                    order_type=order_type,
                )

                position = AgapeSpotPosition(
                    position_id=position_id,
                    ticker=signal.ticker,
                    quantity=quantity,
                    entry_price=round(fill_price, pd),
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    max_risk_usd=signal.max_risk_usd,
                    underlying_at_entry=signal.spot_price,
                    funding_rate_at_entry=signal.funding_rate,
                    funding_regime_at_entry=signal.funding_regime,
                    ls_ratio_at_entry=signal.ls_ratio,
                    squeeze_risk_at_entry=signal.squeeze_risk,
                    max_pain_at_entry=signal.max_pain,
                    crypto_gex_at_entry=signal.crypto_gex,
                    crypto_gex_regime_at_entry=signal.crypto_gex_regime,
                    oracle_advice=signal.oracle_advice,
                    oracle_win_probability=signal.oracle_win_probability,
                    oracle_confidence=signal.oracle_confidence,
                    oracle_top_factors=signal.oracle_top_factors,
                    signal_action=signal.action.value,
                    signal_confidence=signal.confidence,
                    signal_reasoning=signal.reasoning,
                    atr_at_entry=signal.atr,
                    atr_pct_at_entry=signal.atr_pct,
                    chop_index_at_entry=signal.chop_index,
                    status=PositionStatus.OPEN,
                    open_time=now,
                    high_water_mark=round(fill_price, pd),
                    account_label=account_label,
                    coinbase_order_id=str(order_id),
                    entry_slippage_pct=entry_slippage,
                    entry_fee_usd=entry_fee,
                )

                logger.info(
                    f"AGAPE-SPOT: LIVE BUY SUCCESS [{account_label}] {signal.ticker} "
                    f"{quantity} @ ${fill_price:.{pd}f} (order={order_id}, "
                    f"slippage={entry_slippage}%)"
                )
                return position

            # Order was rejected
            error_resp = self._resp(order, "error_response", "unknown")
            failure = self._resp(order, "failure_reason", "unknown")
            logger.error(
                f"AGAPE-SPOT Executor: LIVE ORDER REJECTED {signal.ticker}: "
                f"failure_reason={failure}, error_response={error_resp}"
            )
            if self.db:
                self.db.log(
                    "ERROR", "ORDER_REJECTED",
                    f"Coinbase rejected {signal.ticker} BUY: "
                    f"reason={failure}, qty={signal.quantity}, "
                    f"price=${signal.spot_price:.2f}, error={error_resp}",
                    ticker=signal.ticker,
                )
            return None

        except Exception as e:
            logger.error(
                f"AGAPE-SPOT Executor: LIVE EXECUTION EXCEPTION {signal.ticker}: {e}",
                exc_info=True,
            )
            if self.db:
                self.db.log(
                    "ERROR", "EXEC_EXCEPTION",
                    f"Coinbase exception for {signal.ticker} BUY: {e}",
                    ticker=signal.ticker,
                )
            return None

    # =========================================================================
    # Spot sell (used by trader._close_position for live exits)
    # =========================================================================

    def sell_spot(
        self,
        ticker: str,
        quantity: float,
        position_id: str,
        reason: str,
        account_label: str = "default",
    ) -> Tuple[bool, Optional[float], Optional[dict]]:
        """Execute a live market sell on Coinbase for a position being closed.

        Returns (success, fill_price, exec_details).
        exec_details is a dict with coinbase_sell_order_id, exit_slippage_pct,
        exit_fee_usd -- or None on failure.
        fill_price is None when the sell succeeded but fill lookup failed
        (caller should fall back to current_price).
        Returns (False, None, None) when no client or order rejected/exception.

        account_label routes to the correct Coinbase client that owns this position.
        """
        if account_label == "paper" or account_label.endswith("_fallback"):
            # Paper and fallback positions were never placed on Coinbase
            return (False, None, None)

        client = self._get_client_for_account(ticker, account_label)
        if not client:
            # Fall back to legacy routing
            client = self._get_client(ticker)
        if not client:
            logger.error(
                f"AGAPE-SPOT: No Coinbase client for {ticker}, cannot sell "
                f"{position_id}"
            )
            return (False, None, None)

        try:
            ticker_config = SPOT_TICKERS.get(ticker, {})
            qty_decimals = ticker_config.get("quantity_decimals", 8)
            sell_qty = round(quantity, qty_decimals)

            # Check minimum notional — if below, this is a dust position
            # that Coinbase will reject. Let caller close the DB position
            # without a Coinbase sell (dust value is negligible).
            current_price = self.get_current_price(ticker)
            notional_est = sell_qty * (current_price or 0)
            min_notional = self.get_min_notional(ticker)
            min_base = self.get_min_base_size(ticker)
            if sell_qty < min_base or notional_est < min_notional:
                logger.info(
                    f"AGAPE-SPOT: SELL SKIPPED (dust) {ticker} {position_id} — "
                    f"notional ${notional_est:.2f} below "
                    f"minimum ${min_notional:.2f}. "
                    f"Coins remain in account as dust."
                )
                if self.db:
                    self.db.log(
                        "INFO", "DUST_SKIP",
                        f"Sell skipped for {ticker} {position_id}: "
                        f"notional ${notional_est:.2f} < ${min_notional:.2f}. "
                        f"qty={sell_qty} is dust.",
                        ticker=ticker,
                    )
                # Return True so caller closes DB position (dust is negligible)
                return (True, current_price, {"dust_skip": True})

            client_order_id = str(uuid.uuid4())

            acct_label = account_label.upper()
            logger.info(
                f"AGAPE-SPOT: PLACING LIVE SELL {ticker} [{acct_label}] "
                f"{position_id} qty={sell_qty} (~${notional_est:.2f}) ({reason})"
            )

            # Use limit orders when enabled (lower fees)
            sell_order_type = "market"
            if self.config.use_limit_orders:
                bid, ask = self.get_best_bid_ask(ticker, client)
                if bid and ask:
                    # Place limit at bid + offset (aggressive, likely fills quickly)
                    offset = self.config.limit_order_offset_pct / 100
                    limit_price = bid * (1 + offset)
                    success, order, sell_order_type = self._place_limit_sell(
                        client, ticker, sell_qty, limit_price,
                        client_order_id,
                    )
                    if not success:
                        return (False, None, None)
                else:
                    order = client.market_order_sell(
                        client_order_id=client_order_id,
                        product_id=ticker,
                        base_size=str(sell_qty),
                    )
            else:
                order = client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=ticker,
                    base_size=str(sell_qty),
                )

            # Log raw response
            try:
                if hasattr(order, "to_dict"):
                    logger.info(f"AGAPE-SPOT: Sell response ({sell_order_type}): {order.to_dict()}")
                else:
                    logger.info(f"AGAPE-SPOT: Sell response ({sell_order_type}): {order}")
            except Exception:
                pass

            success = self._resp(order, "success", False)

            if success:
                success_resp = self._resp(order, "success_response")
                order_id = self._resp(success_resp, "order_id", "")
                fill_price = None
                fills_list = []

                try:
                    fills = client.get_fills(order_id=str(order_id))
                    fills_list = self._resp(fills, "fills", [])
                    if fills_list:
                        total_value = sum(
                            float(self._resp(f, "price", 0))
                            * float(self._resp(f, "size", 0))
                            for f in fills_list
                        )
                        total_size = sum(
                            float(self._resp(f, "size", 0))
                            for f in fills_list
                        )
                        if total_size > 0:
                            fill_price = total_value / total_size
                except Exception as fe:
                    logger.debug(f"AGAPE-SPOT: Sell fill lookup skipped: {fe}")

                pd = self._price_decimals(ticker)
                if fill_price is not None:
                    fill_price = round(fill_price, pd)

                # Calculate exit slippage (fill vs current market)
                exit_slippage = None
                if fill_price and current_price and current_price > 0:
                    exit_slippage = round(
                        (fill_price - current_price) / current_price * 100, 4
                    )

                # Extract fee using robust multi-method resolution
                exit_fee = self._resolve_fee(
                    client, fills_list, order_id,
                    fill_price or current_price, sell_qty,
                    ticker, "sell",
                    order_type=sell_order_type,
                )

                exec_details = {
                    "coinbase_sell_order_id": str(order_id),
                    "exit_slippage_pct": exit_slippage,
                    "exit_fee_usd": exit_fee,
                    "order_type": sell_order_type,
                }

                logger.info(
                    f"AGAPE-SPOT: LIVE SELL SUCCESS {ticker} "
                    f"{position_id} qty={sell_qty} "
                    f"fill=${fill_price if fill_price else 'N/A'} "
                    f"(order={order_id}, slippage={exit_slippage}%, reason={reason})"
                )
                return (True, fill_price, exec_details)

            # Order rejected
            error_resp = self._resp(order, "error_response", "unknown")
            failure = self._resp(order, "failure_reason", "unknown")
            logger.error(
                f"AGAPE-SPOT: LIVE SELL REJECTED {ticker} {position_id}: "
                f"failure_reason={failure}, error_response={error_resp}"
            )
            if self.db:
                self.db.log(
                    "ERROR", "SELL_REJECTED",
                    f"Coinbase rejected {ticker} SELL: reason={failure}, "
                    f"qty={sell_qty}, position={position_id}, "
                    f"error={error_resp}",
                    ticker=ticker,
                )
            return (False, None, None)

        except Exception as e:
            logger.error(
                f"AGAPE-SPOT: LIVE SELL EXCEPTION {ticker} {position_id}: {e}",
                exc_info=True,
            )
            if self.db:
                self.db.log(
                    "ERROR", "SELL_EXCEPTION",
                    f"Coinbase sell exception for {ticker} {position_id}: {e}",
                    ticker=ticker,
                )
            return (False, None, None)

    # =========================================================================
    # Position closing (legacy interface used by executor.close_position)
    # =========================================================================

    def close_position(
        self,
        position: AgapeSpotPosition,
        current_price: float,
        reason: str,
    ) -> Tuple[bool, float, float]:
        """Close a long position (always sells).

        Routes to the correct Coinbase account using position.account_label.
        Fallback positions (account_label ending with '_fallback') are always
        closed as paper — they were never placed on Coinbase.
        """
        acct = getattr(position, "account_label", "default")
        if acct == "paper" or acct.endswith("_fallback"):
            return self._close_paper(position, current_price, reason)
        client = self._get_client_for_account(position.ticker, acct)
        if not client:
            client = self._get_client(position.ticker)
        if self.config.is_live(position.ticker) and client:
            return self._close_live(position, current_price, reason)
        return self._close_paper(position, current_price, reason)

    def _close_paper(
        self,
        position: AgapeSpotPosition,
        current_price: float,
        reason: str,
    ) -> Tuple[bool, float, float]:
        """Simulate closing a long position with slippage."""
        slippage = current_price * 0.001  # 0.1%
        close_price = current_price - slippage  # Selling = get less

        realized_pnl = position.calculate_pnl(close_price)

        logger.info(
            f"AGAPE-SPOT: PAPER SELL {position.ticker} {position.position_id} "
            f"@ ${close_price:.2f} P&L=${realized_pnl:.2f} ({reason})"
        )
        pd = self._price_decimals(position.ticker)
        return (True, round(close_price, pd), realized_pnl)

    def _close_live(
        self,
        position: AgapeSpotPosition,
        current_price: float,
        reason: str,
    ) -> Tuple[bool, float, float]:
        """Execute a real sell to close a long position via Coinbase."""
        acct = getattr(position, "account_label", "default")
        client = self._get_client_for_account(position.ticker, acct)
        if not client:
            client = self._get_client(position.ticker)
        if not client:
            return self._close_paper(position, current_price, reason)

        try:
            ticker_config = SPOT_TICKERS.get(position.ticker, {})
            qty_decimals = ticker_config.get("quantity_decimals", 8)
            quantity = round(position.quantity, qty_decimals)

            # Check minimum notional/base — dust positions can't be sold
            notional_est = quantity * current_price
            min_notional = self.get_min_notional(position.ticker)
            min_base = self.get_min_base_size(position.ticker)
            if quantity < min_base or notional_est < min_notional:
                realized_pnl = position.calculate_pnl(current_price)
                logger.info(
                    f"AGAPE-SPOT: LEGACY SELL SKIPPED (dust) {position.ticker} "
                    f"{position.position_id} — notional ${notional_est:.2f} "
                    f"(min ${min_notional:.2f}), qty {quantity} (min {min_base})"
                )
                return (True, current_price, realized_pnl)

            client_order_id = str(uuid.uuid4())

            acct_label = position.account_label.upper()
            logger.info(
                f"AGAPE-SPOT: PLACING LIVE SELL {position.ticker} [{acct_label}] "
                f"{position.position_id} qty={quantity} (~${notional_est:.2f}) ({reason})"
            )

            # LONG-ONLY: Always sell to close
            order = client.market_order_sell(
                client_order_id=client_order_id,
                product_id=position.ticker,
                base_size=str(quantity),
            )

            # Log the raw response
            try:
                if hasattr(order, "to_dict"):
                    logger.info(f"AGAPE-SPOT: Sell response: {order.to_dict()}")
                else:
                    logger.info(f"AGAPE-SPOT: Sell response: {order}")
            except Exception:
                pass

            success = self._resp(order, "success", False)

            if success:
                success_resp = self._resp(order, "success_response")
                order_id = self._resp(success_resp, "order_id", "")
                close_price = current_price
                try:
                    fills = client.get_fills(order_id=str(order_id))
                    fills_list = self._resp(fills, "fills", [])
                    if fills_list:
                        total_value = sum(
                            float(self._resp(f, "price", 0))
                            * float(self._resp(f, "size", 0))
                            for f in fills_list
                        )
                        total_size = sum(
                            float(self._resp(f, "size", 0))
                            for f in fills_list
                        )
                        if total_size > 0:
                            close_price = total_value / total_size
                except Exception as fe:
                    logger.debug(f"AGAPE-SPOT: Sell fill lookup skipped: {fe}")

                realized_pnl = position.calculate_pnl(close_price)
                pd = self._price_decimals(position.ticker)
                logger.info(
                    f"AGAPE-SPOT: LIVE SELL SUCCESS {position.ticker} "
                    f"{position.position_id} @ ${close_price:.{pd}f} "
                    f"P&L=${realized_pnl:.2f} (order={order_id})"
                )
                return (True, round(close_price, pd), realized_pnl)

            error_resp = self._resp(order, "error_response", "unknown")
            failure = self._resp(order, "failure_reason", "unknown")
            logger.error(
                f"AGAPE-SPOT Executor: LIVE SELL REJECTED {position.ticker}: "
                f"failure_reason={failure}, error_response={error_resp}"
            )
            return self._close_paper(position, current_price, reason)

        except Exception as e:
            logger.error(
                f"AGAPE-SPOT Executor: LIVE SELL EXCEPTION {position.ticker}: {e}",
                exc_info=True,
            )
            return self._close_paper(position, current_price, reason)

    # =========================================================================
    # Market data
    # =========================================================================

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current spot price for any supported ticker from Coinbase."""
        client = self._get_client(ticker)
        if client:
            try:
                product = client.get_product(ticker)
                if product:
                    price = self._resp(product, "price")
                    if price:
                        return float(price)
            except Exception as e:
                logger.debug(f"AGAPE-SPOT Executor: Coinbase quote failed for {ticker}: {e}")

        # Fallback: Public Coinbase API (no auth required, works for all coins)
        try:
            import urllib.request
            import json as _json
            url = f"https://api.coinbase.com/v2/prices/{ticker}/spot"
            req = urllib.request.Request(url, headers={"User-Agent": "AlphaGEX/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read())
                price = float(data["data"]["amount"])
                if price > 0:
                    return price
        except Exception as e:
            logger.debug(f"AGAPE-SPOT Executor: Public Coinbase API failed for {ticker}: {e}")

        # Last resort: crypto data provider (Deribit - only supports ETH/BTC)
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            symbol = SPOT_TICKERS.get(ticker, {}).get("symbol", ticker.split("-")[0])
            snapshot = provider.get_snapshot(symbol)
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None

    def get_account_balance(self, ticker: str = None) -> Optional[Dict]:
        """Get account balances for USD, USDC, and all supported crypto currencies.

        If *ticker* is specified, uses that ticker's client (dedicated or default).
        If None, uses the default client.
        """
        client = self._get_client(ticker) if ticker else self._client
        if not client:
            return None
        try:
            accounts = client.get_accounts()
            acct_list = self._resp(accounts, "accounts", [])
            if acct_list:
                balances: Dict[str, float] = {}
                # Collect all currencies we care about (USD + USDC + all traded coins)
                tracked_currencies = {"USD", "USDC"}
                for ticker_key in self.config.tickers:
                    symbol = SPOT_TICKERS.get(ticker_key, {}).get("symbol")
                    if symbol:
                        tracked_currencies.add(symbol)

                for acct in acct_list:
                    currency = self._resp(acct, "currency", "")
                    if currency in tracked_currencies:
                        avail_bal = self._resp(acct, "available_balance", {})
                        available = float(self._resp(avail_bal, "value", 0))
                        balances[currency.lower() + "_balance"] = available

                balances["exchange"] = "coinbase"
                # Determine account type from which client was used
                if ticker and self._dedicated_client and client is self._dedicated_client:
                    balances["account_type"] = "dedicated"
                else:
                    balances["account_type"] = "default"
                return balances
        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Balance fetch failed: {e}")
        return None

    def get_all_account_balances(self) -> Dict[str, Any]:
        """Get balances from ALL Coinbase accounts (default + dedicated).

        Returns a dict keyed by account_label with balance details.
        """
        results: Dict[str, Any] = {}

        # Account 1: Default
        if self._client:
            bal = self.get_account_balance()
            if bal:
                results["default"] = bal

        # Account 2: Dedicated
        if self._dedicated_client:
            try:
                usd_bal = self._get_usd_balance_from_client(self._dedicated_client, account_label="dedicated")
                balances: Dict[str, Any] = {
                    "exchange": "coinbase",
                    "account_type": "dedicated",
                    "tickers": list(self.config.live_tickers),
                }
                if usd_bal is not None:
                    balances["usd_balance"] = usd_bal
                results["dedicated"] = balances
            except Exception as e:
                logger.error(f"AGAPE-SPOT Executor: Dedicated balance fetch failed: {e}")
                results["dedicated"] = {"error": str(e)}

        return results
