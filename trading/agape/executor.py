"""
AGAPE Executor - Executes /MET trades via tastytrade API.

Handles both PAPER mode (simulated fills) and LIVE mode (real tastytrade orders).
Mirrors FORTRESS V2 executor pattern.
"""

import logging
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

# Graceful tastytrade SDK import
tastytrade_available = False
TastytradeSession = None
try:
    from tastytrade import Session as TastytradeSession
    from tastytrade import Account as TastytradeAccount
    tastytrade_available = True
    logger.info("AGAPE Executor: tastytrade SDK loaded")
except ImportError:
    logger.info("AGAPE Executor: tastytrade SDK not installed (pip install tastytrade)")


class AgapeExecutor:
    """Executes /MET Micro Ether Futures trades.

    Modes:
      PAPER: Simulated fills at current market price
      LIVE:  Real orders via tastytrade API

    /MET Contract:
      - 0.1 ETH per contract
      - $0.05 per tick ($0.50 point)
      - Cash settled
      - ~$125-225 margin per contract
    """

    MET_CONTRACT_SIZE = 0.1      # 0.1 ETH per /MET contract
    MET_TICK_SIZE = 0.50         # Minimum price increment
    MET_TICK_VALUE = 0.05        # Dollar value per tick
    MET_SYMBOL = "/MET"          # tastytrade futures symbol

    def __init__(self, config: AgapeConfig, db=None):
        self.config = config
        self.db = db
        self._session = None
        self._account = None

        if config.mode == TradingMode.LIVE and tastytrade_available:
            self._init_tastytrade()

    def _init_tastytrade(self):
        """Initialize tastytrade API session."""
        import os
        username = os.getenv("TASTYTRADE_USERNAME")
        password = os.getenv("TASTYTRADE_PASSWORD")
        account_id = os.getenv("TASTYTRADE_ACCOUNT_ID")

        if not all([username, password]):
            logger.error("AGAPE Executor: TASTYTRADE_USERNAME/PASSWORD not set")
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
                    logger.info(f"AGAPE Executor: Connected to tastytrade account {account_id}")
                else:
                    logger.error("AGAPE Executor: Account not found")
        except Exception as e:
            logger.error(f"AGAPE Executor: tastytrade init failed: {e}")

    def execute_trade(self, signal: AgapeSignal) -> Optional[AgapePosition]:
        """Execute a trade from a signal.

        Returns AgapePosition if successful, None otherwise.
        """
        if not signal.is_valid:
            logger.warning("AGAPE Executor: Invalid signal, skipping execution")
            return None

        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeSignal) -> Optional[AgapePosition]:
        """Execute a simulated paper trade.

        Uses the current spot price as the fill price with a small
        slippage assumption.
        """
        try:
            # Simulate slippage: 0.1% adverse
            slippage = signal.spot_price * 0.001
            if signal.side == "long":
                fill_price = signal.spot_price + slippage
            else:
                fill_price = signal.spot_price - slippage

            position_id = f"AGAPE-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)

            position = AgapePosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                contracts=signal.contracts,
                entry_price=round(fill_price, 2),
                stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                max_risk_usd=signal.max_risk_usd,
                # Market context
                underlying_at_entry=signal.spot_price,
                funding_rate_at_entry=signal.funding_rate,
                funding_regime_at_entry=signal.funding_regime,
                ls_ratio_at_entry=signal.ls_ratio,
                squeeze_risk_at_entry=signal.squeeze_risk,
                max_pain_at_entry=signal.max_pain,
                crypto_gex_at_entry=signal.crypto_gex,
                crypto_gex_regime_at_entry=signal.crypto_gex_regime,
                # Prophet context
                oracle_advice=signal.oracle_advice,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_confidence=signal.oracle_confidence,
                oracle_top_factors=signal.oracle_top_factors,
                # Signal context
                signal_action=signal.action.value,
                signal_confidence=signal.confidence,
                signal_reasoning=signal.reasoning,
                # Status
                status=PositionStatus.OPEN,
                open_time=now,
                high_water_mark=fill_price,
            )

            logger.info(
                f"AGAPE Executor: PAPER {signal.side.upper()} "
                f"{signal.contracts}x /MET @ ${fill_price:.2f} "
                f"(stop=${signal.stop_loss:.2f}, target=${signal.take_profit:.2f})"
            )

            return position

        except Exception as e:
            logger.error(f"AGAPE Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeSignal) -> Optional[AgapePosition]:
        """Execute a real trade via tastytrade API."""
        if not self._session or not self._account:
            logger.error("AGAPE Executor: No tastytrade session for live trading")
            return self._execute_paper(signal)  # Fallback to paper

        try:
            from tastytrade.instruments import Future
            from tastytrade.order import NewOrder, OrderAction, OrderType, OrderTimeInForce

            # Find the active /MET contract
            met_future = self._get_active_met_contract()
            if not met_future:
                logger.error("AGAPE Executor: Could not find active /MET contract")
                return None

            # Build order
            action = OrderAction.BUY_TO_OPEN if signal.side == "long" else OrderAction.SELL_TO_OPEN

            order = NewOrder(
                time_in_force=OrderTimeInForce.DAY,
                order_type=OrderType.MARKET,
                legs=[{
                    "instrument_type": "Future",
                    "symbol": met_future.symbol,
                    "action": action,
                    "quantity": signal.contracts,
                }],
            )

            response = self._account.place_order(self._session, order)
            if response and response.order:
                fill_price = float(response.order.avg_fill_price or signal.spot_price)
                position_id = f"AGAPE-{response.order.id}"

                position = AgapePosition(
                    position_id=position_id,
                    side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                    contracts=signal.contracts,
                    entry_price=fill_price,
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
                    open_time=datetime.now(CENTRAL_TZ),
                    high_water_mark=fill_price,
                )

                logger.info(
                    f"AGAPE Executor: LIVE {signal.side.upper()} "
                    f"{signal.contracts}x /MET @ ${fill_price:.2f}"
                )
                return position

            logger.error("AGAPE Executor: Order response was empty")
            return None

        except Exception as e:
            logger.error(f"AGAPE Executor: Live execution failed: {e}")
            return None

    def close_position(
        self, position: AgapePosition, current_price: float, reason: str
    ) -> Tuple[bool, float, float]:
        """Close an open position.

        Returns (success, close_price, realized_pnl).
        """
        if self.config.mode == TradingMode.LIVE and self._session and self._account:
            return self._close_live(position, current_price, reason)
        return self._close_paper(position, current_price, reason)

    def _close_paper(
        self, position: AgapePosition, current_price: float, reason: str
    ) -> Tuple[bool, float, float]:
        """Simulate closing a position."""
        # Slippage: 0.1% adverse
        slippage = current_price * 0.001
        if position.side == PositionSide.LONG:
            close_price = current_price - slippage
        else:
            close_price = current_price + slippage

        realized_pnl = position.calculate_pnl(close_price)

        logger.info(
            f"AGAPE Executor: PAPER CLOSE {position.position_id} "
            f"@ ${close_price:.2f} P&L=${realized_pnl:.2f} reason={reason}"
        )

        return (True, round(close_price, 2), realized_pnl)

    def _close_live(
        self, position: AgapePosition, current_price: float, reason: str
    ) -> Tuple[bool, float, float]:
        """Close position via tastytrade API."""
        try:
            from tastytrade.order import NewOrder, OrderAction, OrderType, OrderTimeInForce

            met_future = self._get_active_met_contract()
            if not met_future:
                logger.error("AGAPE Executor: Could not find /MET for close")
                return self._close_paper(position, current_price, reason)

            # Opposite action to close
            if position.side == PositionSide.LONG:
                action = OrderAction.SELL_TO_CLOSE
            else:
                action = OrderAction.BUY_TO_CLOSE

            order = NewOrder(
                time_in_force=OrderTimeInForce.DAY,
                order_type=OrderType.MARKET,
                legs=[{
                    "instrument_type": "Future",
                    "symbol": met_future.symbol,
                    "action": action,
                    "quantity": position.contracts,
                }],
            )

            response = self._account.place_order(self._session, order)
            if response and response.order:
                close_price = float(response.order.avg_fill_price or current_price)
                realized_pnl = position.calculate_pnl(close_price)

                logger.info(
                    f"AGAPE Executor: LIVE CLOSE {position.position_id} "
                    f"@ ${close_price:.2f} P&L=${realized_pnl:.2f}"
                )
                return (True, close_price, realized_pnl)

            return (False, 0, 0)

        except Exception as e:
            logger.error(f"AGAPE Executor: Live close failed: {e}")
            return self._close_paper(position, current_price, reason)

    def get_current_price(self) -> Optional[float]:
        """Get current /MET price for position monitoring."""
        if self._session:
            try:
                met = self._get_active_met_contract()
                if met:
                    # Get quote via streamer or API
                    quote = self._account.get_quote(self._session, met.symbol)
                    if quote:
                        mid = (float(quote.bid_price) + float(quote.ask_price)) / 2
                        return mid
            except Exception as e:
                logger.debug(f"AGAPE Executor: tastytrade quote failed: {e}")

        # Fallback: use crypto data provider
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("ETH")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None

    def _get_active_met_contract(self):
        """Find the nearest active /MET futures contract."""
        if not self._session:
            return None
        try:
            from tastytrade.instruments import Future
            futures = Future.get_futures(self._session, product_codes=["MET"])
            if futures:
                # Sort by expiration, get nearest active
                active = [f for f in futures if f.is_tradeable]
                if active:
                    return sorted(active, key=lambda f: f.expiration_date)[0]
        except Exception as e:
            logger.error(f"AGAPE Executor: Failed to find /MET contract: {e}")
        return None

    def get_account_balance(self) -> Optional[Dict]:
        """Get tastytrade account balance."""
        if not self._session or not self._account:
            return None
        try:
            balances = self._account.get_balances(self._session)
            return {
                "net_liquidating_value": float(balances.net_liquidating_value),
                "cash_balance": float(balances.cash_balance),
                "buying_power": float(getattr(balances, "derivative_buying_power", 0)),
            }
        except Exception as e:
            logger.error(f"AGAPE Executor: Balance fetch failed: {e}")
            return None
