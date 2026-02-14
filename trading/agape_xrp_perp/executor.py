"""
AGAPE-XRP-PERP Executor - Executes XRP perpetual contract trades.

Key differences from AGAPE-XRP (Futures) executor:
- No tastytrade / CME integration
- Paper position ID prefix: "AGAPE-XRP-PERP-"
- Uses `quantity` (float XRP) instead of `contracts` (int)
- get_current_price via CryptoDataProvider "XRP" only (no broker fallback)
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from trading.agape_xrp_perp.models import (
    AgapeXrpPerpConfig, AgapeXrpPerpSignal, AgapeXrpPerpPosition,
    PositionSide, PositionStatus, SignalAction, TradingMode,
)

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class AgapeXrpPerpExecutor:
    """Executes XRP Perpetual Contract trades.

    Perpetual contracts: no expiration, no CME, no tastytrade.
    P&L = (current_price - entry_price) * quantity * direction
    """

    def __init__(self, config: AgapeXrpPerpConfig, db=None):
        self.config = config
        self.db = db

    def execute_trade(self, signal: AgapeXrpPerpSignal) -> Optional[AgapeXrpPerpPosition]:
        if not signal.is_valid:
            return None
        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeXrpPerpSignal) -> Optional[AgapeXrpPerpPosition]:
        try:
            slippage = signal.spot_price * 0.001
            fill_price = signal.spot_price + slippage if signal.side == "long" else signal.spot_price - slippage
            position_id = f"AGAPE-XRP-PERP-{uuid.uuid4().hex[:8].upper()}"
            return AgapeXrpPerpPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                quantity=signal.quantity, entry_price=round(fill_price, 4),
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
        except Exception as e:
            logger.error(f"AGAPE-XRP-PERP Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeXrpPerpSignal) -> Optional[AgapeXrpPerpPosition]:
        """Live execution placeholder for perpetual contracts.

        Perpetual contracts are exchange-agnostic. Live execution would
        integrate with a specific perpetual exchange API (e.g., Binance,
        Bybit, dYdX). For now, falls back to paper execution.
        """
        logger.warning("AGAPE-XRP-PERP Executor: Live perpetual execution not yet integrated, using paper mode")
        return self._execute_paper(signal)

    def get_current_price(self) -> Optional[float]:
        """Get current XRP price via CryptoDataProvider.

        No broker/tastytrade fallback for perpetual contracts.
        """
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("XRP")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None
