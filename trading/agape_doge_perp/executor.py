"""
AGAPE-DOGE-PERP Executor - Executes DOGE perpetual contract trades.

Perpetual contracts: No expiration, 24/7 trading, funding rate every 8h.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from trading.agape_doge_perp.models import (
    AgapeDogePerpConfig, AgapeDogePerpSignal, AgapeDogePerpPosition,
    PositionSide, PositionStatus, SignalAction, TradingMode,
)

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class AgapeDogePerpExecutor:
    """Executes DOGE perpetual contract trades.

    DOGE-PERP: Quantity-based sizing (DOGE units), no expiration.
    """

    def __init__(self, config: AgapeDogePerpConfig, db=None):
        self.config = config
        self.db = db

    def execute_trade(self, signal: AgapeDogePerpSignal) -> Optional[AgapeDogePerpPosition]:
        if not signal.is_valid:
            return None
        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeDogePerpSignal) -> Optional[AgapeDogePerpPosition]:
        try:
            slippage = signal.spot_price * 0.001
            fill_price = signal.spot_price + slippage if signal.side == "long" else signal.spot_price - slippage
            position_id = f"AGAPE-DOGE-PERP-{uuid.uuid4().hex[:8].upper()}"
            return AgapeDogePerpPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                quantity=signal.quantity, entry_price=round(fill_price, 6),
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
            logger.error(f"AGAPE-DOGE-PERP Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeDogePerpSignal) -> Optional[AgapeDogePerpPosition]:
        # Live perpetual contract execution placeholder - falls back to paper for now
        logger.warning("AGAPE-DOGE-PERP Executor: Live execution not yet implemented, falling back to paper")
        return self._execute_paper(signal)

    def get_current_price(self) -> Optional[float]:
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("DOGE")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None
