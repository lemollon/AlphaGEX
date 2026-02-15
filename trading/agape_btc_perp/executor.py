"""
AGAPE-BTC-PERP Executor - Executes BTC perpetual contract trades.

Key differences from AGAPE-BTC (CME futures):
  - No tastytrade SDK integration
  - No CME /MBT contract lookup
  - Paper prefix: "AGAPE-BTC-PERP-"
  - Uses quantity (float BTC) not contracts (int)
  - get_current_price via CryptoDataProvider "BTC" only
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple
from zoneinfo import ZoneInfo

from trading.agape_btc_perp.models import (
    AgapeBtcPerpConfig,
    AgapeBtcPerpSignal,
    AgapeBtcPerpPosition,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
)

logger = logging.getLogger(__name__)

CENTRAL_TZ = ZoneInfo("America/Chicago")


class AgapeBtcPerpExecutor:
    """Executes BTC Perpetual Contract trades.

    BTC-PERP:
      - No expiration, trades 24/7/365
      - Position sized in BTC quantity (float)
      - P&L = (current - entry) * quantity * direction
      - No tastytrade/CME integration
    """

    def __init__(self, config: AgapeBtcPerpConfig, db=None):
        self.config = config
        self.db = db
        self._crypto_provider = None

        # Initialize crypto data provider for price quotes
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            self._crypto_provider = get_crypto_data_provider()
            logger.info("AGAPE-BTC-PERP Executor: CryptoDataProvider loaded")
        except ImportError:
            logger.warning("AGAPE-BTC-PERP Executor: CryptoDataProvider not available")
        except Exception as e:
            logger.warning(f"AGAPE-BTC-PERP Executor: CryptoDataProvider init failed: {e}")

    def execute_trade(self, signal: AgapeBtcPerpSignal) -> Optional[AgapeBtcPerpPosition]:
        if not signal.is_valid:
            return None

        # Pre-trade margin check (non-blocking on failure)
        try:
            from trading.margin.pre_trade_check import check_margin_before_trade
            approved, reason = check_margin_before_trade(
                bot_name="AGAPE_BTC_PERP",
                symbol="BTC-PERP",
                side=signal.side or "long",
                quantity=signal.quantity,
                entry_price=signal.entry_price or signal.spot_price,
            )
            if not approved:
                logger.warning(f"AGAPE-BTC-PERP: Trade rejected by margin check: {reason}")
                return None
        except Exception as e:
            logger.debug(f"AGAPE-BTC-PERP: Margin check skipped: {e}")

        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeBtcPerpSignal) -> Optional[AgapeBtcPerpPosition]:
        try:
            slippage = signal.spot_price * 0.001
            if signal.side == "long":
                fill_price = signal.spot_price + slippage
            else:
                fill_price = signal.spot_price - slippage

            position_id = f"AGAPE-BTC-PERP-{uuid.uuid4().hex[:8].upper()}"
            now = datetime.now(CENTRAL_TZ)

            position = AgapeBtcPerpPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                quantity=signal.quantity,
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
                f"AGAPE-BTC-PERP Executor: PAPER {signal.side.upper()} "
                f"{signal.quantity:.5f} BTC-PERP @ ${fill_price:.2f}"
            )
            return position
        except Exception as e:
            logger.error(f"AGAPE-BTC-PERP Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeBtcPerpSignal) -> Optional[AgapeBtcPerpPosition]:
        """Live execution placeholder for perpetual contract exchange integration.

        Currently falls back to paper execution. When a perpetual exchange API
        is integrated (e.g., Binance, Bybit, dYdX), this method will place
        real orders via that exchange's SDK.
        """
        logger.warning("AGAPE-BTC-PERP Executor: Live execution not yet integrated, using paper mode")
        return self._execute_paper(signal)

    def get_current_price(self) -> Optional[float]:
        """Get current BTC price via CryptoDataProvider.

        No tastytrade/CME fallback - perpetual contracts use crypto-native pricing only.
        """
        if self._crypto_provider:
            try:
                snapshot = self._crypto_provider.get_snapshot("BTC")
                if snapshot and snapshot.spot_price > 0:
                    return snapshot.spot_price
            except Exception as e:
                logger.warning(f"AGAPE-BTC-PERP Executor: Price fetch failed: {e}")

        # Fallback: try to import fresh provider
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("BTC")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None
