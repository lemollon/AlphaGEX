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

        # Default client (shared across tickers without their own credentials)
        self._client: Optional[object] = None

        # Per-ticker clients keyed by ticker (e.g. "DOGE-USD" -> RESTClient)
        self._ticker_clients: Dict[str, object] = {}

        # Coinbase product limits fetched at init (real minimums from API)
        # {ticker: {"base_min_size": float, "quote_min_size": float, "base_increment": float}}
        self._product_limits: Dict[str, Dict[str, float]] = {}

        # Always init Coinbase clients (needed for price data even in paper mode)
        if coinbase_available:
            self._init_coinbase()

    def _init_coinbase(self):
        """Initialize Coinbase clients.

        Priority order for each ticker:
        1. Per-ticker key: COINBASE_{SYMBOL}_API_KEY / SECRET
        2. Shared dedicated key: COINBASE_DEDICATED_API_KEY / SECRET
        3. Default key: COINBASE_API_KEY / SECRET (fallback)
        """
        # --- Default client ---
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
                        f"AGAPE-SPOT Executor: Default client connected. "
                        f"{verify_ticker} = ${price:,.2f}"
                    )
                else:
                    logger.warning("AGAPE-SPOT Executor: Default client connected but no product data")
            except Exception as e:
                logger.error(f"AGAPE-SPOT Executor: Default client init failed: {e}")
                self._client = None
        else:
            logger.warning(
                "AGAPE-SPOT Executor: No default COINBASE_API_KEY/SECRET set."
            )

        # --- Shared dedicated client (one Coinbase account for all live tickers) ---
        shared_dedicated_client = None
        ded_key = os.getenv("COINBASE_DEDICATED_API_KEY")
        ded_secret = os.getenv("COINBASE_DEDICATED_API_SECRET")
        if ded_key and ded_secret:
            try:
                shared_dedicated_client = RESTClient(api_key=ded_key, api_secret=ded_secret)
                verify_ticker = self.config.live_tickers[0] if self.config.live_tickers else "DOGE-USD"
                product = shared_dedicated_client.get_product(verify_ticker)
                if product:
                    price = float(self._resp(product, "price", 0))
                    self._store_product_limits(verify_ticker, product)
                    logger.info(
                        f"AGAPE-SPOT Executor: Shared dedicated client connected. "
                        f"{verify_ticker} = ${price:,.2f}"
                    )
            except Exception as e:
                logger.error(f"AGAPE-SPOT Executor: Shared dedicated client init failed: {e}")
                shared_dedicated_client = None

        # --- Per-ticker clients ---
        for ticker in self.config.tickers:
            symbol = SPOT_TICKERS.get(ticker, {}).get("symbol", ticker.split("-")[0])
            env_key = f"COINBASE_{symbol.upper()}_API_KEY"
            env_secret = f"COINBASE_{symbol.upper()}_API_SECRET"
            tk_api_key = os.getenv(env_key)
            tk_api_secret = os.getenv(env_secret)

            if tk_api_key and tk_api_secret:
                # Per-ticker key found -- use it
                try:
                    client = RESTClient(api_key=tk_api_key, api_secret=tk_api_secret)
                    product = client.get_product(ticker)
                    if product:
                        price = float(self._resp(product, "price", 0))
                        self._store_product_limits(ticker, product)
                        logger.info(
                            f"AGAPE-SPOT Executor: {symbol} dedicated client connected. "
                            f"{ticker} = ${price:,.2f}"
                        )
                    self._ticker_clients[ticker] = client
                except Exception as e:
                    logger.error(
                        f"AGAPE-SPOT Executor: {symbol} dedicated client init failed: {e}"
                    )
            elif shared_dedicated_client and ticker in self.config.live_tickers:
                # No per-ticker key, but shared dedicated account covers all live tickers
                self._ticker_clients[ticker] = shared_dedicated_client
                logger.info(
                    f"AGAPE-SPOT Executor: {symbol} using shared dedicated client"
                )

        if not self._client and not self._ticker_clients:
            logger.error(
                "AGAPE-SPOT Executor: No Coinbase clients initialized. "
                "Set COINBASE_API_KEY/SECRET, COINBASE_DEDICATED_API_KEY/SECRET, "
                "or per-ticker COINBASE_{SYMBOL}_API_KEY/SECRET."
            )

    def _get_client(self, ticker: str) -> Optional[object]:
        """Get the Coinbase client for a specific ticker.

        Returns the per-ticker client if configured, otherwise the default client.
        """
        return self._ticker_clients.get(ticker, self._client)

    def _get_client_for_account(self, ticker: str, account_label: str) -> Optional[object]:
        """Get the Coinbase client for a specific account label.

        'default' → self._client, '{SYMBOL}' → self._ticker_clients[ticker].
        'paper' → None (no Coinbase client needed).
        """
        if account_label == "paper":
            return None
        if account_label == "default":
            return self._client
        # Dedicated account (label matches the ticker's symbol)
        return self._ticker_clients.get(ticker)

    def get_all_accounts(self, ticker: str) -> list:
        """Return all (account_label, is_live) pairs available for a ticker.

        For live tickers returns up to 3 entries:
          ("default", True)  -- your Coinbase account
          (symbol, True)     -- dedicated/shared-dedicated Coinbase account
          ("paper", False)   -- paper tracking

        Each signal opens independent positions on EVERY returned account.
        """
        accounts = []
        symbol = SPOT_TICKERS.get(ticker, {}).get("symbol", ticker.split("-")[0])

        if self.config.is_live(ticker):
            # Default Coinbase account (your account)
            if self._client is not None:
                accounts.append(("default", True))
            # Dedicated / shared-dedicated Coinbase account (friend's account)
            if ticker in self._ticker_clients:
                accounts.append((symbol, True))
            # Paper account for parallel tracking
            accounts.append(("paper", False))
        else:
            accounts.append(("paper", False))

        return accounts

    @property
    def has_any_client(self) -> bool:
        """True if at least one Coinbase client is connected."""
        return self._client is not None or bool(self._ticker_clients)

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
        """Simulate a long-only spot buy with slippage."""
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
                status=PositionStatus.OPEN,
                open_time=now,
                high_water_mark=round(fill_price, pd),
                account_label=account_label,
            )

            notional = signal.quantity * fill_price
            logger.info(
                f"AGAPE-SPOT: PAPER BUY [{account_label}] {signal.ticker} "
                f"{signal.quantity:.4f} (${notional:.2f}) @ ${fill_price:.{pd}f}"
            )
            return position

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Paper execution failed: {e}")
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
            # Legacy path: determine from client
            account_label = (
                SPOT_TICKERS.get(signal.ticker, {}).get("symbol", "default")
                if signal.ticker in self._ticker_clients
                else "default"
            )
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

            # LONG-ONLY: Always buy to open
            order = client.market_order_buy(
                client_order_id=client_order_id,
                product_id=signal.ticker,
                base_size=str(quantity),
            )

            # Log the raw response for debugging
            try:
                if hasattr(order, "to_dict"):
                    logger.info(f"AGAPE-SPOT: Order response: {order.to_dict()}")
                else:
                    logger.info(f"AGAPE-SPOT: Order response: {order}")
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

                # Extract fee from fills if available
                entry_fee = None
                try:
                    if fills_list:
                        entry_fee = sum(
                            float(self._resp(f, "commission", 0))
                            for f in fills_list
                        )
                        if entry_fee == 0:
                            entry_fee = None
                except Exception:
                    pass

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
        if account_label == "paper":
            # Paper positions don't need a Coinbase sell
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

            is_dedicated = ticker in self._ticker_clients
            acct_label = "DEDICATED" if is_dedicated else "DEFAULT"
            logger.info(
                f"AGAPE-SPOT: PLACING LIVE SELL {ticker} [{acct_label}] "
                f"{position_id} qty={sell_qty} (~${notional_est:.2f}) ({reason})"
            )

            order = client.market_order_sell(
                client_order_id=client_order_id,
                product_id=ticker,
                base_size=str(sell_qty),
            )

            # Log raw response
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
                fill_price = None

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

                # Extract fee
                exit_fee = None
                try:
                    if fills_list:
                        exit_fee = sum(
                            float(self._resp(f, "commission", 0))
                            for f in fills_list
                        )
                        if exit_fee == 0:
                            exit_fee = None
                except Exception:
                    pass

                exec_details = {
                    "coinbase_sell_order_id": str(order_id),
                    "exit_slippage_pct": exit_slippage,
                    "exit_fee_usd": exit_fee,
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
        """
        acct = getattr(position, "account_label", "default")
        if acct == "paper":
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

            is_dedicated = position.ticker in self._ticker_clients
            acct_label = "DEDICATED" if is_dedicated else "DEFAULT"
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
                is_dedicated = ticker and ticker in self._ticker_clients
                balances["account_type"] = "dedicated" if is_dedicated else "default"
                return balances
        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Balance fetch failed: {e}")
        return None

    def get_all_account_balances(self) -> Dict[str, Any]:
        """Get balances from ALL Coinbase accounts (default + dedicated).

        Returns a dict keyed by account_label with balance details.
        Deduplicates shared dedicated clients (one API call, all balances).
        """
        results: Dict[str, Any] = {}

        # Default account
        if self._client:
            bal = self.get_account_balance()
            if bal:
                results["default"] = bal

        # Dedicated / shared-dedicated accounts (deduplicate by client identity)
        seen_clients: set = set()
        all_dedicated_symbols: set = set()

        for ticker in self._ticker_clients:
            symbol = SPOT_TICKERS.get(ticker, {}).get("symbol", ticker.split("-")[0])
            all_dedicated_symbols.add(symbol)

        for ticker, client in self._ticker_clients.items():
            client_id = id(client)
            if client_id in seen_clients:
                continue
            seen_clients.add(client_id)

            try:
                accounts = client.get_accounts()
                acct_list = self._resp(accounts, "accounts", [])
                balances: Dict[str, float] = {}
                # Track all currencies this shared client trades + USD + USDC
                tracked = {"USD", "USDC"} | all_dedicated_symbols
                for acct in acct_list:
                    currency = self._resp(acct, "currency", "")
                    if currency in tracked:
                        avail_bal = self._resp(acct, "available_balance", {})
                        available = float(self._resp(avail_bal, "value", 0))
                        balances[currency.lower() + "_balance"] = available
                balances["exchange"] = "coinbase"
                balances["account_type"] = "dedicated"
                tickers_on_client = [
                    t for t, c in self._ticker_clients.items() if id(c) == client_id
                ]
                balances["tickers"] = tickers_on_client
                results["dedicated"] = balances
            except Exception as e:
                logger.error(f"AGAPE-SPOT Executor: Balance fetch failed: {e}")
                results["dedicated"] = {"error": str(e)}

        return results
