"""
AGAPE-SPOT Executor - Executes spot ETH trades via Coinbase Advanced Trade API.

24/7 Coinbase spot trading. No CME futures, no market hours restrictions.

Position sizing: Uses eth_quantity directly (not contracts).
  - eth_quantity = 0.1 ETH default
  - P&L = (exit - entry) * eth_quantity * direction

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
    logger.info("AGAPE-SPOT Executor: coinbase-advanced-py loaded")
except ImportError:
    logger.info("AGAPE-SPOT Executor: coinbase-advanced-py not installed")

PRODUCT_ID = "ETH-USD"


class AgapeSpotExecutor:
    """Executes spot ETH-USD trades via Coinbase Advanced Trade API.

    24/7 trading - no market hours restrictions.
    """

    def __init__(self, config: AgapeSpotConfig, db=None):
        self.config = config
        self.db = db
        self._client: Optional[object] = None

        if config.mode == TradingMode.LIVE and coinbase_available:
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
            product = self._client.get_product(PRODUCT_ID)
            if product:
                price = float(product.get("price", 0))
                logger.info(f"AGAPE-SPOT Executor: Connected. ETH-USD = ${price:,.2f}")
            else:
                logger.warning("AGAPE-SPOT Executor: Connected but no product data")
        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Init failed: {e}")
            self._client = None

    def execute_trade(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        if not signal.is_valid:
            logger.warning("AGAPE-SPOT Executor: Invalid signal, skipping")
            return None

        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        """Simulate a spot ETH trade with slippage."""
        try:
            slippage = signal.spot_price * 0.001  # 0.1%
            if signal.side == "long":
                fill_price = signal.spot_price + slippage
            else:
                fill_price = signal.spot_price - slippage

            position_id = f"SPOT-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)

            position = AgapeSpotPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                eth_quantity=signal.eth_quantity,
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

            notional = signal.eth_quantity * fill_price
            logger.info(
                f"AGAPE-SPOT: PAPER {signal.side.upper()} "
                f"{signal.eth_quantity:.4f} ETH (${notional:.2f}) @ ${fill_price:.2f}"
            )
            return position

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeSpotSignal) -> Optional[AgapeSpotPosition]:
        """Execute a real spot trade via Coinbase."""
        if not self._client:
            logger.error("AGAPE-SPOT Executor: No Coinbase client")
            return self._execute_paper(signal)

        try:
            eth_quantity = round(signal.eth_quantity, 8)
            client_order_id = f"spot-{uuid.uuid4().hex[:12]}"

            if signal.side == "long":
                order = self._client.market_order_buy(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
                )
            else:
                order = self._client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
                )

            if order and order.get("success"):
                order_id = order["success_response"]["order_id"]
                fill_price = signal.spot_price
                try:
                    fills = self._client.get_fills(order_id=order_id)
                    if fills and fills.get("fills"):
                        total_value = sum(float(f["price"]) * float(f["size"]) for f in fills["fills"])
                        total_size = sum(float(f["size"]) for f in fills["fills"])
                        if total_size > 0:
                            fill_price = total_value / total_size
                except Exception:
                    pass

                position_id = f"SPOT-{order_id[:8]}"
                now = datetime.now(CENTRAL_TZ)

                position = AgapeSpotPosition(
                    position_id=position_id,
                    side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                    eth_quantity=eth_quantity,
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
                    f"AGAPE-SPOT: LIVE {signal.side.upper()} "
                    f"{eth_quantity:.4f} ETH @ ${fill_price:.2f} (order={order_id})"
                )
                return position

            error = order.get("error_response", {}) if order else "No response"
            logger.error(f"AGAPE-SPOT Executor: Order failed: {error}")
            return None

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Live execution failed: {e}")
            return None

    def close_position(self, position: AgapeSpotPosition, current_price: float, reason: str) -> Tuple[bool, float, float]:
        if self.config.mode == TradingMode.LIVE and self._client:
            return self._close_live(position, current_price, reason)
        return self._close_paper(position, current_price, reason)

    def _close_paper(self, position: AgapeSpotPosition, current_price: float, reason: str) -> Tuple[bool, float, float]:
        slippage = current_price * 0.001
        if position.side == PositionSide.LONG:
            close_price = current_price - slippage
        else:
            close_price = current_price + slippage

        realized_pnl = position.calculate_pnl(close_price)

        logger.info(
            f"AGAPE-SPOT: PAPER CLOSE {position.position_id} "
            f"@ ${close_price:.2f} P&L=${realized_pnl:.2f} ({reason})"
        )
        return (True, round(close_price, 2), realized_pnl)

    def _close_live(self, position: AgapeSpotPosition, current_price: float, reason: str) -> Tuple[bool, float, float]:
        try:
            eth_quantity = round(position.eth_quantity, 8)
            client_order_id = f"spot-close-{uuid.uuid4().hex[:12]}"

            if position.side == PositionSide.LONG:
                order = self._client.market_order_sell(
                    client_order_id=client_order_id,
                    product_id=PRODUCT_ID,
                    base_size=str(eth_quantity),
                )
            else:
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
                        total_value = sum(float(f["price"]) * float(f["size"]) for f in fills["fills"])
                        total_size = sum(float(f["size"]) for f in fills["fills"])
                        if total_size > 0:
                            close_price = total_value / total_size
                except Exception:
                    pass

                realized_pnl = position.calculate_pnl(close_price)
                logger.info(
                    f"AGAPE-SPOT: LIVE CLOSE {position.position_id} "
                    f"@ ${close_price:.2f} P&L=${realized_pnl:.2f}"
                )
                return (True, round(close_price, 2), realized_pnl)

            error = order.get("error_response", {}) if order else "No response"
            logger.error(f"AGAPE-SPOT Executor: Close failed: {error}")
            return self._close_paper(position, current_price, reason)

        except Exception as e:
            logger.error(f"AGAPE-SPOT Executor: Live close failed: {e}")
            return self._close_paper(position, current_price, reason)

    def get_current_price(self) -> Optional[float]:
        """Get current ETH-USD spot price from Coinbase."""
        if self._client:
            try:
                product = self._client.get_product(PRODUCT_ID)
                if product and product.get("price"):
                    return float(product["price"])
            except Exception as e:
                logger.debug(f"AGAPE-SPOT Executor: Coinbase quote failed: {e}")

        # Fallback to crypto data provider
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("ETH")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None

    def get_account_balance(self) -> Optional[Dict]:
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
            logger.error(f"AGAPE-SPOT Executor: Balance fetch failed: {e}")
        return None
