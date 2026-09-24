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

    # A real SHIB move of more than this fraction in a single scan cycle is
    # not physically plausible for a meme-coin perp - it means the upstream
    # quote is corrupt (stale JSON, truncated string, API hiccup), not that
    # the market crashed. Reject it and hold the last known-good price
    # instead of feeding a garbage tick into exits/stops/trailing logic.
    MAX_TICK_DEVIATION_PCT = 0.50

    def __init__(self, config: AgapeShibPerpConfig, db=None):
        self.config = config
        self.db = db
        # Last failure reason so the trader can surface WHY a trade was
        # rejected (margin/free-margin block or execution exception)
        # in scan activity instead of a bare EXECUTION_FAILED.
        self.last_failure_reason = None
        self._last_good_price: Optional[float] = None

    def execute_trade(self, signal: AgapeShibPerpSignal) -> Optional[AgapeShibPerpPosition]:
        self.last_failure_reason = None
        if not signal.is_valid:
            self.last_failure_reason = "invalid_signal"
            return None

        # Pre-trade margin check - strict only in LIVE mode.
        from trading.margin.pre_trade_check import check_margin_before_trade
        approved, reason = check_margin_before_trade(
            bot_name="AGAPE_SHIB_PERP",
            symbol="SHIB-PERP",
            side=signal.side or "long",
            quantity=signal.quantity,
            entry_price=signal.entry_price or signal.spot_price,
            # Paper accounts must behave like a real Hyperliquid account: fail
            # CLOSED (block the trade) on any margin-system error, not just in LIVE.
            strict=True,
        )
        if not approved:
            self.last_failure_reason = f"margin_rejected: {reason}"
            logger.warning(f"AGAPE-SHIB-PERP: Trade BLOCKED by margin check: {reason}")
            return None

        # Free-margin + leverage-cap check. Paper accounts must never be able
        # to open a position they couldn't actually afford on a real cross-margin
        # Hyperliquid account. Fails CLOSED on any computation error.
        from trading.margin.pre_trade_check import check_free_margin_for_perp
        margin_ok, margin_reason = check_free_margin_for_perp(
            db=self.db,
            config=self.config,
            signal_side=signal.side or "long",
            signal_quantity=signal.quantity,
            signal_entry_price=signal.entry_price or signal.spot_price,
            current_price=self.get_current_price(),
        )
        if not margin_ok:
            self.last_failure_reason = f"free_margin_rejected: {margin_reason}"
            logger.warning(
                f"AGAPE-SHIB-PERP: Trade BLOCKED by free-margin check: {margin_reason}"
            )
            return None

        if self.config.mode == TradingMode.LIVE:
            logger.error("AGAPE-SHIB-PERP Executor: LIVE execution is disabled until a real perpetual venue adapter is configured")
            return None
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeShibPerpSignal) -> Optional[AgapeShibPerpPosition]:
        try:
            from trading.shared.margin_config import PERPETUAL_MARGIN_SPECS
            from trading.shared.perp_realism import simulate_selective_reference_fill

            spec = PERPETUAL_MARGIN_SPECS.get(self.config.instrument, {})
            fill, reference_market, venue_rules = simulate_selective_reference_fill(
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
                prefer_maker=getattr(signal, "confidence", "") in ("HIGH", "VERY_HIGH"),
                seed_key=f"{self.config.instrument}|{getattr(signal, 'side', '')}|{getattr(signal, 'entry_price', 0)}|{getattr(signal, 'spot_price', 0)}|{getattr(signal, 'confidence', '')}",
            )
            fill_price = fill.fill_price
            logger.info(
                "%s paper fill source=%s style=%s fill_frac=%.2f ref=%.8f fill=%.8f slippage=%.2fbps fee=$%.4f",
                self.config.instrument,
                reference_market.quote.source if reference_market else "fallback",
                fill.execution_style,
                fill.fill_fraction,
                fill.reference_price,
                fill.fill_price,
                fill.slippage_bps,
                fill.fee_usd,
            )
            position_id = f"AGAPE-SHIB-PERP-{uuid.uuid4().hex[:8].upper()}"
            return AgapeShibPerpPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                quantity=signal.quantity * fill.fill_fraction, entry_price=round(fill_price, 8),
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
            self.last_failure_reason = f"paper_exception: {type(e).__name__}: {e}"
            logger.error(f"AGAPE-SHIB-PERP Executor: Paper execution failed: {e}")
            return None

    def get_current_price(self) -> Optional[float]:
        """Get current SHIB price from CryptoDataProvider.

        Root-cause guard for the near-zero exit bug (2026-09-24): a
        corrupt/stale upstream tick that is still numerically > 0 (e.g.
        0.00000001) used to pass straight through to trailing-stop and
        close logic, booking a fake ~5000% profit on a "price crash" that
        never happened. Reject any single-cycle move bigger than
        MAX_TICK_DEVIATION_PCT from the last known-good price and reuse
        the last good price instead - SHIB does not move 50%+ between two
        scan cycles on a real market event.
        """
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("SHIB")
            price = snapshot.spot_price if snapshot else None
        except Exception:
            price = None

        if price is None or price <= 0:
            return self._last_good_price

        if self._last_good_price:
            deviation = abs(price - self._last_good_price) / self._last_good_price
            if deviation > self.MAX_TICK_DEVIATION_PCT:
                logger.error(
                    "AGAPE-SHIB-PERP: rejecting corrupt price tick $%.10f "
                    "(%.0f%% away from last good $%.10f) - holding last good price",
                    price, deviation * 100, self._last_good_price,
                )
                return self._last_good_price

        self._last_good_price = price
        return price
