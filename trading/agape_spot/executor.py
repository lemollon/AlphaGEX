"""
AGAPE-SPOT Executor - Multi-ticker, long-only spot trades via Coinbase Advanced Trade API.

24/7 Coinbase spot trading. No CME futures, no market hours restrictions.
LONG-ONLY: Coinbase spot doesn't support shorting for US retail.

Supported tickers: ETH-USD, XRP-USD, SHIB-USD, DOGE-USD
Position sizing: Uses quantity directly (per-coin units).
  - P&L = (exit - entry) * quantity (always long)

Requires:
  pip install coinbase-advanced-py

Environment variables:
  COINBASE_API_KEY      = "organizations/{org_id}/apiKeys/{key_id}"
  COINBASE_API_SECRET   = "-----BEGIN EC PRIVATE KEY-----\\n...\\n-----END EC PRIVATE KEY-----\\n"
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple
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
    """

    def __init__(self, config: AgapeSpotConfig, db=None):
        self.config = config
        self.db = db
        self._client: Optional[object] = None

        # Always init Coinbase client (needed for price data even in paper mode)
        if coinbase_available:
            self._init_coinbase()

    def _init_coinbase(self):
        api_key = os.getenv("COINBASE_API_KEY")
        api_secret = os.getenv("COINBASE_API_SECRET")

        if not api_key or not api_secret:
            logger.error(
                "AGAPE-SPOT Executor: COINBASE_API_KEY and COINBASE_API_SECRET "
                "must be set."
            )
            return

        try:
            self._client = RESTClient(api_key=api_key, api_secret=api_secret)
            # Verify connectivity with the first configured ticker
            verify_ticker = self.config.tickers[0] if self.config.tickers else "ETH-USD"
            product = self._client.get_product(verify_ticker)
            if product:
                price = float(product.get("price", 0))
                logger.info(
                    f"AGAPE-SPOT Executor: Connected. {verify_ticker} = ${price:,.2f}"
                )
            else:
                logger.warning("AGAPE-SPOT Executor: Connected but no product data")
        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Init failed: {e}")
            self._client = None

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _price_decimals(ticker: str) -> int:
        """Get the number of decimal places for a ticker's price."""
        return SPOT_TICKERS.get(ticker, {}).get("price_decimals", 2)

    # =========================================================================
    # Trade execution
    # =========================================================================

    def execute_trade(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        """Execute a long-only spot trade for signal.ticker."""
        if not signal.is_valid:
            logger.warning(
                f"AGAPE-SPOT Executor: Invalid signal for {signal.ticker}, skipping"
            )
            return None

        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        """Simulate a long-only spot buy with slippage."""
        try:
            slippage = signal.spot_price * 0.001  # 0.1%
            fill_price = signal.spot_price + slippage  # Buying = pay more

            ticker_symbol = SPOT_TICKERS.get(signal.ticker, {}).get("symbol", signal.ticker.split("-")[0])
            position_id = f"SPOT-{ticker_symbol}-{uuid.uuid4().hex[:8].upper()}"
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
            )

            notional = signal.quantity * fill_price
            logger.info(
                f"AGAPE-SPOT: PAPER BUY {signal.ticker} "
                f"{signal.quantity:.4f} (${notional:.2f}) @ ${fill_price:.{pd}f}"
            )
            return position

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        """Execute a real long-only spot buy via Coinbase."""
        if not self._client:
            logger.error("AGAPE-SPOT Executor: No Coinbase client")
            return self._execute_paper(signal)

        try:
            ticker_config = SPOT_TICKERS.get(signal.ticker, {})
            qty_decimals = ticker_config.get("quantity_decimals", 8)
            quantity = round(signal.quantity, qty_decimals)
            client_order_id = f"spot-{uuid.uuid4().hex[:12]}"

            # LONG-ONLY: Always buy to open
            order = self._client.market_order_buy(
                client_order_id=client_order_id,
                product_id=signal.ticker,
                base_size=str(quantity),
            )

            if order and order.get("success"):
                order_id = order["success_response"]["order_id"]
                fill_price = signal.spot_price
                try:
                    fills = self._client.get_fills(order_id=order_id)
                    if fills and fills.get("fills"):
                        total_value = sum(
                            float(f["price"]) * float(f["size"])
                            for f in fills["fills"]
                        )
                        total_size = sum(
                            float(f["size"]) for f in fills["fills"]
                        )
                        if total_size > 0:
                            fill_price = total_value / total_size
                except Exception:
                    pass

                ticker_symbol = ticker_config.get("symbol", signal.ticker.split("-")[0])
                position_id = f"SPOT-{ticker_symbol}-{order_id[:8]}"
                now = datetime.now(CENTRAL_TZ)

                pd = self._price_decimals(signal.ticker)

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
                )

                logger.info(
                    f"AGAPE-SPOT: LIVE BUY {signal.ticker} "
                    f"{quantity:.4f} @ ${fill_price:.2f} (order={order_id})"
                )
                return position

            error = order.get("error_response", {}) if order else "No response"
            logger.error(f"AGAPE-SPOT Executor: Order failed: {error}")
            return None

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Live execution failed: {e}")
            return None

    # =========================================================================
    # Position closing
    # =========================================================================

    def close_position(
        self,
        position: AgapeSpotPosition,
        current_price: float,
        reason: str,
    ) -> Tuple[bool, float, float]:
        """Close a long position (always sells)."""
        if self.config.mode == TradingMode.LIVE and self._client:
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
        try:
            ticker_config = SPOT_TICKERS.get(position.ticker, {})
            qty_decimals = ticker_config.get("quantity_decimals", 8)
            quantity = round(position.quantity, qty_decimals)
            client_order_id = f"spot-close-{uuid.uuid4().hex[:12]}"

            # LONG-ONLY: Always sell to close
            order = self._client.market_order_sell(
                client_order_id=client_order_id,
                product_id=position.ticker,
                base_size=str(quantity),
            )

            if order and order.get("success"):
                order_id = order["success_response"]["order_id"]
                close_price = current_price
                try:
                    fills = self._client.get_fills(order_id=order_id)
                    if fills and fills.get("fills"):
                        total_value = sum(
                            float(f["price"]) * float(f["size"])
                            for f in fills["fills"]
                        )
                        total_size = sum(
                            float(f["size"]) for f in fills["fills"]
                        )
                        if total_size > 0:
                            close_price = total_value / total_size
                except Exception:
                    pass

                realized_pnl = position.calculate_pnl(close_price)
                logger.info(
                    f"AGAPE-SPOT: LIVE SELL {position.ticker} {position.position_id} "
                    f"@ ${close_price:.2f} P&L=${realized_pnl:.2f}"
                )
                pd = self._price_decimals(position.ticker)
                return (True, round(close_price, pd), realized_pnl)

            error = order.get("error_response", {}) if order else "No response"
            logger.error(f"AGAPE-SPOT Executor: Close failed: {error}")
            return self._close_paper(position, current_price, reason)

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Live close failed: {e}")
            return self._close_paper(position, current_price, reason)

    # =========================================================================
    # Market data
    # =========================================================================

    def get_current_price(self, ticker: str) -> Optional[float]:
        """Get current spot price for any supported ticker from Coinbase."""
        if self._client:
            try:
                product = self._client.get_product(ticker)
                if product and product.get("price"):
                    return float(product["price"])
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

    def get_account_balance(self) -> Optional[Dict]:
        """Get account balances for USD and all supported crypto currencies."""
        if not self._client:
            return None
        try:
            accounts = self._client.get_accounts()
            if accounts and accounts.get("accounts"):
                balances: Dict[str, float] = {}
                # Collect all currencies we care about
                tracked_currencies = {"USD"}
                for ticker_key in self.config.tickers:
                    symbol = SPOT_TICKERS.get(ticker_key, {}).get("symbol")
                    if symbol:
                        tracked_currencies.add(symbol)

                for acct in accounts["accounts"]:
                    currency = acct.get("currency", "")
                    if currency in tracked_currencies:
                        available = float(
                            acct.get("available_balance", {}).get("value", 0)
                        )
                        balances[currency.lower() + "_balance"] = available

                balances["exchange"] = "coinbase"
                return balances
        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Balance fetch failed: {e}")
        return None
