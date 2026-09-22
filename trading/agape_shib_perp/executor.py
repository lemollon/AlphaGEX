"""
AGAPE-SHIB-PERP Executor - Executes SHIB-PERP perpetual contract trades.

Same logic as AGAPE-DOGE executor for perpetual contracts.
No tastytrade/CME integration - perpetual contracts only.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from trading.agape_shib_perp.models import (
    AgapeShibPerpConfig, AgapeShibPerpSignal, AgapeShibPerpPosition,
    PositionSide, PositionStatus, SignalAction, TradingMode,
)

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class AgapeShibPerpExecutor:
    """Executes SHIB Perpetual contract trades.

    SHIB-PERP: Quantity-based perpetual contract, no expiration.
    Very low price (~$0.00001), very large quantities (millions).
    """

    def __init__(self, config: AgapeShibPerpConfig, db=None):
        self.config = config
        self.db = db

    def execute_trade(self, signal: AgapeShibPerpSignal) -> Optional[AgapeShibPerpPosition]:
        if not signal.is_valid:
            return None

        # Pre-trade margin check - strict only in LIVE mode.
        from trading.margin.pre_trade_check import check_margin_before_trade
        is_live = self.config.mode == TradingMode.LIVE
        approved, reason = check_margin_before_trade(
            bot_name="AGAPE_SHIB_PERP",
            symbol="SHIB-PERP",
            side=signal.side or "long",
            quantity=signal.quantity,
            entry_price=signal.entry_price or signal.spot_price,
            strict=is_live,
        )
        if not approved:
            logger.warning(f"AGAPE-SHIB-PERP: Trade BLOCKED by margin check: {reason}")
            return None

        if self.config.mode == TradingMode.LIVE:
            logger.error("AGAPE-SHIB-PERP Executor: LIVE execution is disabled until a real perpetual venue adapter is configured")
            return None
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeShibPerpSignal) -> Optional[AgapeShibPerpPosition]:
        try:
            from trading.shared.margin_config import PERPETUAL_MARGIN_SPECS
            from trading.shared.perp_realism import simulate_reference_fill

            spec = PERPETUAL_MARGIN_SPECS.get(self.config.instrument, {})
            fill, reference_market, venue_rules = simulate_reference_fill(
                self.config.instrument,
                signal.side,
                signal.quantity,
                signal.spot_price,
                default_leverage=float(spec.get("default_leverage", 5) or 5),
                max_leverage=float(spec.get("max_leverage", 20) or 20),
                fallback_maintenance_margin_rate=float(
                    spec.get("maintenance_margin_rate", 0.01) or 0.01
                ),
                funding_interval_hours=float(
                    spec.get("funding_interval_hours", 8) or 8
                ),
            )
            fill_price = fill.fill_price
            logger.info(
                "%s paper fill source=%s ref=%.8f fill=%.8f slippage=%.2fbps fee=$%.4f",
                self.config.instrument,
                reference_market.quote.source if reference_market else "fallback",
                fill.reference_price,
                fill.fill_price,
                fill.slippage_bps,
                fill.fee_usd,
            )
            position_id = f"AGAPE-SHIB-PERP-{uuid.uuid4().hex[:8].upper()}"
            return AgapeShibPerpPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                quantity=signal.quantity, entry_price=round(fill_price, 8),
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
            logger.error(f"AGAPE-SHIB-PERP Executor: Paper execution failed: {e}")
            return None

    def get_current_price(self) -> Optional[float]:
        """Get current SHIB price from CryptoDataProvider."""
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("SHIB")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None
