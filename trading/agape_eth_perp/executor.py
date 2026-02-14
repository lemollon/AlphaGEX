"""
AGAPE-ETH-PERP Executor - Executes ETH perpetual contract trades.

Key differences from AGAPE-XRP:
    - No tastytrade / CME integration (perpetual contracts on crypto exchanges)
    - No _get_active_contract() (perpetuals don't expire)
    - Position ID prefix: "AGAPE-ETH-PERP-"
    - Uses quantity (float ETH) instead of contracts (int)
    - get_current_price() uses CryptoDataProvider "ETH" only
    - Slippage: 0.001 (0.1%)
    - Live execution: placeholder that falls back to paper
"""

import logging
import uuid
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from trading.agape_eth_perp.models import (
    AgapeEthPerpConfig, AgapeEthPerpSignal, AgapeEthPerpPosition,
    PositionSide, PositionStatus, SignalAction, TradingMode,
)

logger = logging.getLogger(__name__)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class AgapeEthPerpExecutor:
    """Executes ETH perpetual contract trades.

    ETH-PERP: Perpetual contract, no expiration, quantity in ETH units.
    No tastytrade/CME integration - perpetual contracts trade on crypto exchanges.
    """

    def __init__(self, config: AgapeEthPerpConfig, db=None):
        self.config = config
        self.db = db
        self._crypto_provider = None
        self._init_crypto_provider()

    def _init_crypto_provider(self):
        """Initialize CryptoDataProvider for price feeds."""
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            self._crypto_provider = get_crypto_data_provider()
            logger.info("AGAPE-ETH-PERP Executor: CryptoDataProvider initialized")
        except ImportError:
            logger.warning("AGAPE-ETH-PERP Executor: CryptoDataProvider not available")
        except Exception as e:
            logger.warning(f"AGAPE-ETH-PERP Executor: CryptoDataProvider init failed: {e}")

    def execute_trade(self, signal: AgapeEthPerpSignal) -> Optional[AgapeEthPerpPosition]:
        """Execute a trade based on the signal.

        Live mode falls back to paper since perpetual contract exchange
        integration is not yet implemented.
        """
        if not signal.is_valid:
            return None
        if self.config.mode == TradingMode.LIVE:
            return self._execute_live(signal)
        return self._execute_paper(signal)

    def _execute_paper(self, signal: AgapeEthPerpSignal) -> Optional[AgapeEthPerpPosition]:
        """Execute a paper trade with simulated slippage."""
        try:
            slippage = signal.spot_price * 0.001
            fill_price = signal.spot_price + slippage if signal.side == "long" else signal.spot_price - slippage
            position_id = f"AGAPE-ETH-PERP-{uuid.uuid4().hex[:8].upper()}"
            return AgapeEthPerpPosition(
                position_id=position_id,
                side=PositionSide.LONG if signal.side == "long" else PositionSide.SHORT,
                quantity=signal.quantity, entry_price=round(fill_price, 2),
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
            logger.error(f"AGAPE-ETH-PERP Executor: Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: AgapeEthPerpSignal) -> Optional[AgapeEthPerpPosition]:
        """Execute a live trade on a crypto exchange.

        Perpetual contract exchange integration is not yet implemented.
        Falls back to paper execution with a warning.
        """
        logger.warning("AGAPE-ETH-PERP Executor: Live perpetual contract execution not yet implemented, falling back to paper")
        return self._execute_paper(signal)

    def get_current_price(self) -> Optional[float]:
        """Get current ETH price from CryptoDataProvider.

        No tastytrade/CME fallback - perpetual contracts use crypto exchange data only.
        """
        if self._crypto_provider:
            try:
                snapshot = self._crypto_provider.get_snapshot("ETH")
                if snapshot and snapshot.spot_price > 0:
                    return snapshot.spot_price
            except Exception as e:
                logger.warning(f"AGAPE-ETH-PERP Executor: CryptoDataProvider price fetch failed: {e}")

        # Fallback: try to re-initialize and fetch
        try:
            from data.crypto_data_provider import get_crypto_data_provider
            provider = get_crypto_data_provider()
            snapshot = provider.get_snapshot("ETH")
            return snapshot.spot_price if snapshot else None
        except Exception:
            return None
