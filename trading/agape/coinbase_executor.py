"""
AGAPE Coinbase Executor - Executes spot ETH trades via Coinbase Advanced Trade API.

Enables 24/7 crypto trading (no CME Saturday/maintenance breaks).
Trades ETH-USD spot instead of /MET futures contracts.

Position sizing: Uses the same contract_size logic as the CME executor.
  - contract_size = 0.1 ETH (default)
  - 5 contracts = 0.5 ETH spot buy/sell
  - P&L = (exit - entry) * quantity * direction

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

from trading.agape.models import (
    AgapeConfig,
    AgapeSignal,
    AgapePosition,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
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
    logger.info("AGAPE CoinbaseExecutor: coinbase-advanced-py loaded")
except ImportError:
    logger.info(
        "AGAPE CoinbaseExecutor: coinbase-advanced-py not installed "
        "(pip install coinbase-advanced-py)"
    )

PRODUCT_ID = "ETH-USD"


class CoinbaseExecutor:
    """Executes spot ETH-USD trades via Coinbase Advanced Trade API.

    24/7 trading - no market hours restrictions.

    Modes:
      PAPER: Simulated fills at current market price (with slippage)
      LIVE:  Real orders via Coinbase Advanced Trade API
    """

    def __init__(self, config: AgapeConfig, db=None):
        self.config = config
        self.db = db
        self._client: Optional[object] = None

        if config.mode == TradingMode.LIVE and coinbase_available:
            self._init_coinbase()

    def _init_coinbase(self):
        """Initialize Coinbase Advanced Trade API client."""
        api_key = os.getenv("COINBASE_API_KEY")
        api_secret = os.getenv("COINBASE_API_SECRET")

        if not api_key or not api_secret:
            logger.error(
                "AGAPE CoinbaseExecutor: COINBASE_API_KEY and COINBASE_API_SECRET "
                "must be set. Get keys at https://portal.cdp.coinbase.com/access/api"
            )
            return

        try:
            self._client = RESTClient(api_key=api_key, api_secret=api_secret)
            # Verify connection by fetching product
            product = self._client.get_product(PRODUCT_ID)
            if product:
                price = float(product.get("price", 0))
                logger.info(
                    f"AGAPE CoinbaseExecutor: Connected to Coinbase. "
                    f"ETH-USD = ${price:,.2f}"
                )
            else:
                logger.warning("AGAPE CoinbaseExecutor: Connected but no product data")
        except Exception as e:
            logger.error(f"AGAPE CoinbaseExecutor: Init failed: {e}")
            self._client = None

    def execute_trade(self, signal: AgapeSignal) -> Optional[AgapePosition]:
        """Execute a trade from a signal."""
        if not signal.is_valid:
            logger.warning("AGAPE CoinbaseExecutor: Invalid signal, skipping")
            return None

        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeSignal) -> Optional[AgapePosition]:
        """Simulate a spot ETH trade with slippage."""
        try:
            slippage = signal.spot_price * 0.001  # 0.1% adverse
            if signal.side == "long":
                fill_price = signal.spot_price + slippage
            else:
                fill_price = signal.spot_price - slippage

            position_id = f"AGAPE-CB-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)

            # Quantity in ETH = contracts * contract_size
            eth_quantity = signal.contracts * self.config.contract_size

            position = AgapePosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                contracts=signal.contracts,
                entry_price=round(fill_price, 2),
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
                high_water_mark=fill_price,
            )

            logger.info(
                f"AGAPE CoinbaseExecutor: PAPER {signal.side.upper()} "
                f"{eth_quantity:.4f} ETH ({signal.contracts}x) @ ${fill_price:.2f} "
                f"(stop=${signal.stop_loss:.2f}, target=${signal.take_profit:.2f})"
            )
            return position

        except Exception as e:
            logger.error(f"AGAPE CoinbaseExecutor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeSignal) -> Optional[AgapePosition]:
        """Execute a real spot trade via Coinbase Advanced Trade API.

        For LONG: market buy ETH-USD
        For SHORT: market sell ETH-USD (requires existing ETH balance)
        """
        if not self._client:
            logger.error("AGAPE CoinbaseExecutor: No Coinbase client for live trading")
            return self._execute_paper(signal)

        try:
            eth_quantity = round(signal.contracts * self.config.contract_size, 8)
            client_order_id = f"agape-{uuid.uuid4().hex[:12]}"

            if signal.side == "long":
                # Market buy: specify base_size (ETH quantity to buy)
                order = self._client.market_order_buy(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
                )
            else:
                # Market sell: specify base_size (ETH quantity to sell)
                order = self._client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
                )

            if order and order.get("success"):
                order_id = order["success_response"]["order_id"]

                # Get fill price from order details
                fill_price = signal.spot_price  # Default
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
                    pass  # Use spot price as fallback

                position_id = f"AGAPE-CB-{order_id[:8]}"
                now = datetime.now(CENTRAL_TZ)

                position = AgapePosition(
                    position_id=position_id,
                    side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                    contracts=signal.contracts,
                    entry_price=round(fill_price, 2),
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
                    high_water_mark=round(fill_price, 2),
                )

                logger.info(
                    f"AGAPE CoinbaseExecutor: LIVE {signal.side.upper()} "
                    f"{eth_quantity:.4f} ETH @ ${fill_price:.2f} "
                    f"(order_id={order_id})"
                )
                return position

            else:
                error = order.get("error_response", {}) if order else "No response"
                logger.error(f"AGAPE CoinbaseExecutor: Order failed: {error}")
                return None

        except Exception as e:
            logger.error(f"AGAPE CoinbaseExecutor: Live execution failed: {e}")
            return None

    def close_position(
        self, position: AgapePosition, current_price: float, reason: str
    ) -> Tuple[bool, float, float]:
        """Close a position by placing the opposite trade."""
        if self.config.mode == TradingMode.LIVE and self._client:
            return self._close_live(position, current_price, reason)
        return self._close_paper(position, current_price, reason)

    def _close_paper(
        self, position: AgapePosition, current_price: float, reason: str
    ) -> Tuple[bool, float, float]:
        """Simulate closing a spot position."""
        slippage = current_price * 0.001
        if position.side == PositionSide.LONG:
            close_price = current_price - slippage
        else:
            close_price = current_price + slippage

        realized_pnl = position.calculate_pnl(close_price)

        logger.info(
            f"AGAPE CoinbaseExecutor: PAPER CLOSE {position.position_id} "
            f"@ ${close_price:.2f} P&L=${realized_pnl:.2f} reason={reason}"
        )
        return (True, round(close_price, 2), realized_pnl)

    def _close_live(
        self, position: AgapePosition, current_price: float, reason: str
    ) -> Tuple[bool, float, float]:
        """Close by executing opposite spot trade on Coinbase."""
        try:
            eth_quantity = round(
                position.contracts * self.config.contract_size, 8
            )
            client_order_id = f"agape-close-{uuid.uuid4().hex[:12]}"

            if position.side == PositionSide.LONG:
                # Close long = sell ETH
                order = self._client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
                )
            else:
                # Close short = buy ETH
                order = self._client.market_order_buy(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
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
                    f"AGAPE CoinbaseExecutor: LIVE CLOSE {position.position_id} "
                    f"@ ${close_price:.2f} P&L=${realized_pnl:.2f}"
                )
                return (True, round(close_price, 2), realized_pnl)

            error = order.get("error_response", {}) if order else "No response"
            logger.error(f"AGAPE CoinbaseExecutor: Close failed: {error}")
            return self._close_paper(position, current_price, reason)

        except Exception as e:
            logger.error(f"AGAPE CoinbaseExecutor: Live close failed: {e}")
            return self._close_paper(position, current_price, reason)

    def get_current_price(self) -> Optional[float]:
        """Get current ETH-USD spot price."""
        # Try Coinbase first (most accurate for our execution venue)
        if self._client:
            try:
                product = self._client.get_product(PRODUCT_ID)
                if product and product.get("price"):
                    return float(product["price"])
            except Exception as e:
                logger.debug(f"AGAPE CoinbaseExecutor: Coinbase quote failed: {e}")

        # Fallback to crypto data provider
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("ETH")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None

    def get_account_balance(self) -> Optional[Dict]:
        """Get Coinbase account balances."""
        if not self._client:
            return None
        try:
            accounts = self._client.get_accounts()
            if accounts and accounts.get("accounts"):
                usd_balance = 0.0
                eth_balance = 0.0
                for acct in accounts["accounts"]:
                    currency = acct.get("currency", "")
                    available = float(acct.get("available_balance", {}).get("value", 0))
                    if currency == "USD":
                        usd_balance = available
                    elif currency == "ETH":
                        eth_balance = available
                return {
                    "usd_balance": usd_balance,
                    "eth_balance": eth_balance,
                    "exchange": "coinbase",
                }
        except Exception as e:
            logger.error(f"AGAPE CoinbaseExecutor: Balance fetch failed: {e}")
        return None
