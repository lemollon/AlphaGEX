"""
PEGASUS - Order Executor
=========================

SPX Iron Condor execution via Tradier.
Uses SPXW symbols for weekly options.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Tuple

from .models import (
    IronCondorPosition, PositionStatus,
    IronCondorSignal, PEGASUSConfig, TradingMode, CENTRAL_TZ
)

logger = logging.getLogger(__name__)

try:
    from data.tradier_data_fetcher import TradierDataFetcher
    TRADIER_AVAILABLE = True
except ImportError:
    TRADIER_AVAILABLE = False
    TradierDataFetcher = None

try:
    from data.unified_data_provider import get_price
    DATA_AVAILABLE = True
except ImportError:
    DATA_AVAILABLE = False


class OrderExecutor:
    """Executes SPX Iron Condors"""

    def __init__(self, config: PEGASUSConfig):
        self.config = config
        self.tradier = None

        if TRADIER_AVAILABLE and config.mode == TradingMode.LIVE:
            try:
                self.tradier = TradierDataFetcher()
                logger.info("PEGASUS: Tradier initialized")
            except Exception as e:
                logger.error(f"Tradier init failed: {e}")

    def execute_iron_condor(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Execute SPX Iron Condor"""
        if self.config.mode == TradingMode.PAPER:
            return self._execute_paper(signal)
        else:
            return self._execute_live(signal)

    def _execute_paper(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Paper trade execution with FULL Oracle/Kronos context"""
        try:
            import json
            now = datetime.now(CENTRAL_TZ)
            position_id = f"PEGASUS-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

            contracts = self._calculate_position_size(signal.max_loss)
            max_profit = signal.total_credit * 100 * contracts
            max_loss = (self.config.spread_width - signal.total_credit) * 100 * contracts

            # Convert Oracle top_factors to JSON string for DB storage
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=position_id,
                ticker="SPX",
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=self.config.spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Kronos GEX context (FULL audit trail)
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context (FULL audit trail)
                oracle_confidence=signal.confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                put_order_id="PAPER",
                call_order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(
                f"PAPER SPX IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} "
                f"x{contracts} @ ${signal.total_credit:.2f}"
            )
            logger.info(f"Context: Oracle={signal.oracle_advice} ({signal.oracle_win_probability:.0%}), GEX Regime={signal.gex_regime}")

            return position
        except Exception as e:
            logger.error(f"Paper execution failed: {e}")
            return None

    def _execute_live(self, signal: IronCondorSignal) -> Optional[IronCondorPosition]:
        """Live SPX execution with FULL Oracle/Kronos context - uses SPXW symbols"""
        if not self.tradier:
            logger.error("Tradier not available")
            return None

        try:
            import json
            now = datetime.now(CENTRAL_TZ)
            contracts = self._calculate_position_size(signal.max_loss)

            # Execute put spread
            put_result = self.tradier.place_vertical_spread(
                symbol="SPXW",  # Weekly SPX options
                expiration=signal.expiration,
                long_strike=signal.put_long,
                short_strike=signal.put_short,
                option_type="put",
                quantity=contracts,
                limit_price=round(signal.estimated_put_credit, 2),
                is_credit=True,
            )

            if not put_result or not put_result.get('order'):
                logger.error(f"Put spread failed: {put_result}")
                return None

            put_order_id = str(put_result['order'].get('id', 'UNKNOWN'))

            # Execute call spread
            call_result = self.tradier.place_vertical_spread(
                symbol="SPXW",
                expiration=signal.expiration,
                long_strike=signal.call_long,
                short_strike=signal.call_short,
                option_type="call",
                quantity=contracts,
                limit_price=round(signal.estimated_call_credit, 2),
                is_credit=True,
            )

            if not call_result or not call_result.get('order'):
                logger.error(f"Call spread failed: {call_result}")
                return None

            call_order_id = str(call_result['order'].get('id', 'UNKNOWN'))

            max_profit = signal.total_credit * 100 * contracts
            max_loss = (self.config.spread_width - signal.total_credit) * 100 * contracts

            # Convert Oracle top_factors to JSON string for DB storage
            oracle_factors_json = json.dumps(signal.oracle_top_factors) if signal.oracle_top_factors else ""

            position = IronCondorPosition(
                position_id=f"PEGASUS-LIVE-{put_order_id}",
                ticker="SPX",
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=self.config.spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                # Kronos GEX context (FULL audit trail)
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                # Oracle context (FULL audit trail)
                oracle_confidence=signal.confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                put_order_id=put_order_id,
                call_order_id=call_order_id,
                status=PositionStatus.OPEN,
                open_time=now,
            )

            logger.info(f"LIVE SPX IC: {signal.put_long}/{signal.put_short}-{signal.call_short}/{signal.call_long} x{contracts}")
            logger.info(f"Context: Oracle={signal.oracle_advice} ({signal.oracle_win_probability:.0%}), GEX Regime={signal.gex_regime}")
            return position
        except Exception as e:
            logger.error(f"Live execution failed: {e}")
            return None

    def close_position(self, position: IronCondorPosition, reason: str) -> Tuple[bool, float, float]:
        """Close SPX IC position"""
        if self.config.mode == TradingMode.PAPER:
            return self._close_paper(position, reason)
        else:
            return self._close_live(position, reason)

    def _close_paper(self, position: IronCondorPosition, reason: str) -> Tuple[bool, float, float]:
        try:
            current_price = self._get_current_spx_price()
            if not current_price:
                current_price = position.underlying_at_entry

            close_value = self._estimate_ic_value(position, current_price)
            pnl = (position.total_credit - close_value) * 100 * position.contracts

            logger.info(f"PAPER CLOSE: {position.position_id} @ ${close_value:.2f}, P&L=${pnl:.2f}")
            return True, close_value, pnl
        except Exception as e:
            logger.error(f"Close failed: {e}")
            return False, 0, 0

    def _close_live(self, position: IronCondorPosition, reason: str) -> Tuple[bool, float, float]:
        if not self.tradier:
            return False, 0, 0

        try:
            # Close both spreads
            put_result = self.tradier.place_vertical_spread(
                symbol="SPXW",
                expiration=position.expiration,
                long_strike=position.put_long_strike,
                short_strike=position.put_short_strike,
                option_type="put",
                quantity=position.contracts,
                is_closing=True,
            )

            call_result = self.tradier.place_vertical_spread(
                symbol="SPXW",
                expiration=position.expiration,
                long_strike=position.call_long_strike,
                short_strike=position.call_short_strike,
                option_type="call",
                quantity=position.contracts,
                is_closing=True,
            )

            if not put_result or not call_result:
                return False, 0, 0

            # Estimate P&L
            close_value = position.total_credit * 0.3  # Assume 70% profit on close
            pnl = (position.total_credit - close_value) * 100 * position.contracts

            return True, close_value, pnl
        except Exception as e:
            logger.error(f"Live close failed: {e}")
            return False, 0, 0

    def _calculate_position_size(self, max_loss_per_contract: float) -> int:
        max_risk = 100_000 * (self.config.risk_per_trade_pct / 100)
        if max_loss_per_contract <= 0:
            return 1
        contracts = int(max_risk / max_loss_per_contract)
        return max(1, min(contracts, self.config.max_contracts))

    def _get_current_spx_price(self) -> Optional[float]:
        if DATA_AVAILABLE:
            try:
                spx = get_price("SPX")
                if spx:
                    return spx
                spy = get_price("SPY")
                if spy:
                    return spy * 10
            except Exception:
                pass
        return None

    def _estimate_ic_value(self, position: IronCondorPosition, current_price: float) -> float:
        """Estimate current IC value"""
        if position.put_short_strike < current_price < position.call_short_strike:
            put_dist = (current_price - position.put_short_strike) / position.spread_width
            call_dist = (position.call_short_strike - current_price) / position.spread_width
            factor = min(put_dist, call_dist) / 2
            return position.total_credit * max(0.1, 0.5 - factor * 0.3)
        elif current_price <= position.put_short_strike:
            intrinsic = position.put_short_strike - current_price
            return min(position.spread_width, intrinsic + position.total_credit * 0.2)
        else:
            intrinsic = current_price - position.call_short_strike
            return min(position.spread_width, intrinsic + position.total_credit * 0.2)

    def get_position_current_value(self, position: IronCondorPosition) -> Optional[float]:
        current_price = self._get_current_spx_price()
        if current_price:
            return self._estimate_ic_value(position, current_price)
        return None
