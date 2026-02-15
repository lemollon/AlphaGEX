"""
AGAPE-BTC Executor - Executes /MBT trades via tastytrade API.

Same logic as AGAPE (ETH) executor but for Micro Bitcoin Futures.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple
from zoneinfo import ZoneInfo

from trading.agape_btc.models import (
    AgapeBtcConfig,
    AgapeBtcSignal,
    AgapeBtcPosition,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")

tastytrade_available = False
TastytradeSession = None
try:
    from tastytrade import Session as TastytradeSession
    from tastytrade import Account as TastytradeAccount
    tastytrade_available = True
    logger.info("AGAPE-BTC Executor: tastytrade SDK loaded")
except ImportError:
    logger.info("AGAPE-BTC Executor: tastytrade SDK not installed")


class AgapeBtcExecutor:
    """Executes /MBT Micro Bitcoin Futures trades.

    /MBT Contract:
      - 0.1 BTC per contract
      - $0.50 per tick ($5.00 point)
      - Cash settled
    """

    MBT_CONTRACT_SIZE = 0.1
    MBT_TICK_SIZE = 5.00
    MBT_TICK_VALUE = 0.50
    MBT_SYMBOL = "/MBT"

    def __init__(self, config: AgapeBtcConfig, db=None):
        self.config = config
        self.db = db
        self._session = None
        self._account = None
        if config.mode == TradingMode.LIVE and tastytrade_available:
            self._init_tastytrade()

    def _init_tastytrade(self):
        import os
        username = os.getenv("TASTYTRADE_USERNAME")
        password = os.getenv("TASTYTRADE_PASSWORD")
        account_id = os.getenv("TASTYTRADE_ACCOUNT_ID")
        if not all([username, password]):
            logger.error("AGAPE-BTC Executor: TASTYTRADE_USERNAME/PASSWORD not set")
            return
        try:
            self._session = TastytradeSession(username, password)
            if account_id:
                accounts = TastytradeAccount.get_accounts(self._session)
                self._account = next(
                    (a for a in accounts if a.account_number == account_id),
                    accounts[0] if accounts else None,
                )
                if self._account:
                    logger.info(f"AGAPE-BTC Executor: Connected to tastytrade account {account_id}")
        except Exception as e:
            logger.error(f"AGAPE-BTC Executor: tastytrade init failed: {e}")

    def execute_trade(self, signal: AgapeBtcSignal) -> Optional[AgapeBtcPosition]:
        if not signal.is_valid:
            return None

        # Pre-trade margin check (non-blocking on failure)
        try:
            from trading.margin.pre_trade_check import check_margin_before_trade
            approved, reason = check_margin_before_trade(
                bot_name="AGAPE_BTC",
                symbol="/MBT",
                side=signal.side or "long",
                quantity=float(signal.contracts) if hasattr(signal, 'contracts') else signal.quantity,
                entry_price=signal.entry_price or signal.spot_price,
            )
            if not approved:
                logger.warning(f"AGAPE-BTC: Trade rejected by margin check: {reason}")
                return None
        except Exception as e:
            logger.debug(f"AGAPE-BTC: Margin check skipped: {e}")

        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeBtcSignal) -> Optional[AgapeBtcPosition]:
        try:
            slippage = signal.spot_price * 0.001
            if signal.side == "long":
                fill_price = signal.spot_price + slippage
            else:
                fill_price = signal.spot_price - slippage

            position_id = f"AGAPE-BTC-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)

            position = AgapeBtcPosition(
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
                margin_required=signal.margin_required,
                liquidation_price=signal.liquidation_price,
                leverage_at_entry=signal.leverage_at_entry,
            )

            logger.info(
                f"AGAPE-BTC Executor: PAPER {signal.side.upper()} "
                f"{signal.contracts}x /MBT @ ${fill_price:.2f}"
            )
            return position
        except Exception as e:
            logger.error(f"AGAPE-BTC Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeBtcSignal) -> Optional[AgapeBtcPosition]:
        if not self._session or not self._account:
            return self._execute_paper(signal)
        try:
            from tastytrade.instruments import Future
            from tastytrade.order import NewOrder, OrderAction, OrderType, OrderTimeInForce

            mbt_future = self._get_active_mbt_contract()
            if not mbt_future:
                return None

            action = OrderAction.BUY_TO_OPEN if signal.side == "long" else OrderAction.SELL_TO_OPEN
            order = NewOrder(
                time_in_force=OrderTimeInForce.DAY,
                order_type=OrderType.MARKET,
                legs=[{"instrument_type": "Future", "symbol": mbt_future.symbol,
                       "action": action, "quantity": signal.contracts}],
            )
            response = self._account.place_order(self._session, order)
            if response and response.order:
                fill_price = float(response.order.avg_fill_price or signal.spot_price)
                position_id = f"AGAPE-BTC-{response.order.id}"
                position = AgapeBtcPosition(
                    position_id=position_id,
                    side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                    contracts=signal.contracts, entry_price=fill_price,
                    stop_loss=signal.stop_loss, take_profit=signal.take_profit,
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
                    open_time=datetime.now(CENTRAL_TZ),
                    high_water_mark=fill_price,
                )
                return position
            return None
        except Exception as e:
            logger.error(f"AGAPE-BTC Executor: Live execution failed: {e}")
            return None

    def get_current_price(self) -> Optional[float]:
        if self._session:
            try:
                mbt = self._get_active_mbt_contract()
                if mbt:
                    quote = self._account.get_quote(self._session, mbt.symbol)
                    if quote:
                        return (float(quote.bid_price) + float(quote.ask_price)) / 2
            except Exception:
                pass
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("BTC")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None

    def _get_active_mbt_contract(self):
        if not self._session:
            return None
        try:
            from tastytrade.instruments import Future
            futures = Future.get_futures(self._session, product_codes=["MBT"])
            if futures:
                active = [f for f in futures if f.is_tradeable]
                if active:
                    return sorted(active, key=lambda f: f.expiration_date)[0]
        except Exception as e:
            logger.error(f"AGAPE-BTC Executor: Failed to find /MBT contract: {e}")
        return None
