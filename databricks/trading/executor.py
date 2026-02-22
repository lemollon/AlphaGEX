"""
Paper Trade Executor
=====================

Executes paper trades using real Tradier market data.
No order execution — only simulated fills using real bid/ask prices.

Fill rules:
- Sells fill at bid (conservative)
- Buys fill at ask (conservative)
- Net credit = (short_put_bid + short_call_bid) - (long_put_ask + long_call_ask)
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Optional, Tuple

from .models import (
    IronCondorPosition,
    IronCondorSignal,
    BotConfig,
    PositionStatus,
    CENTRAL_TZ,
)
from .db import TradingDatabase

logger = logging.getLogger(__name__)


class PaperExecutor:
    """
    Paper trade executor for SPARK and FLAME bots.

    Uses real Tradier bid/ask for fill simulation.
    Tracks paper account balance, collateral, and P&L.
    """

    def __init__(self, config: BotConfig, db: TradingDatabase):
        self.config = config
        self.db = db

    def calculate_collateral(self, spread_width: float, net_credit: float) -> float:
        """
        Calculate collateral required per contract.

        collateral = (wing_width * 100) - (net_credit * 100)
        """
        if spread_width <= 0:
            logger.error(f"{self.config.bot_name}: Invalid spread width")
            return 0
        collateral = (spread_width * 100) - (net_credit * 100)
        return max(0, collateral)

    def calculate_max_contracts(
        self, buying_power: float, collateral_per_contract: float
    ) -> int:
        """Calculate maximum contracts based on buying power (85% usage)."""
        if collateral_per_contract <= 0:
            return 0
        usable_bp = buying_power * self.config.buying_power_usage_pct
        max_contracts = int(usable_bp / collateral_per_contract)
        return min(max_contracts, self.config.max_contracts)

    def open_paper_position(
        self, signal: IronCondorSignal, contracts: int
    ) -> Optional[IronCondorPosition]:
        """
        Open a paper Iron Condor position.

        Uses real Tradier bid/ask from the signal for conservative fill pricing.
        Deducts collateral from paper account.
        """
        if contracts < 1:
            logger.error(f"{self.config.bot_name}: Cannot open with 0 contracts")
            return None

        try:
            now = datetime.now(CENTRAL_TZ)
            position_id = (
                f"{self.config.bot_name}-{now.strftime('%Y%m%d')}-"
                f"{uuid.uuid4().hex[:6].upper()}"
            )

            spread_width = signal.put_short - signal.put_long
            collateral_per = self.calculate_collateral(spread_width, signal.total_credit)
            total_collateral = collateral_per * contracts
            max_profit = signal.total_credit * 100 * contracts
            max_loss = collateral_per * contracts

            oracle_factors_json = (
                json.dumps(signal.oracle_top_factors)
                if signal.oracle_top_factors
                else ""
            )

            position = IronCondorPosition(
                position_id=position_id,
                ticker=self.config.ticker,
                expiration=signal.expiration,
                put_short_strike=signal.put_short,
                put_long_strike=signal.put_long,
                put_credit=signal.estimated_put_credit,
                call_short_strike=signal.call_short,
                call_long_strike=signal.call_long,
                call_credit=signal.estimated_call_credit,
                contracts=contracts,
                spread_width=spread_width,
                total_credit=signal.total_credit,
                max_profit=max_profit,
                max_loss=max_loss,
                underlying_at_entry=signal.spot_price,
                vix_at_entry=signal.vix,
                expected_move=signal.expected_move,
                call_wall=signal.call_wall,
                put_wall=signal.put_wall,
                gex_regime=signal.gex_regime,
                flip_point=signal.flip_point,
                net_gex=signal.net_gex,
                oracle_confidence=signal.oracle_confidence,
                oracle_win_probability=signal.oracle_win_probability,
                oracle_advice=signal.oracle_advice,
                oracle_reasoning=signal.reasoning,
                oracle_top_factors=oracle_factors_json,
                oracle_use_gex_walls=signal.oracle_use_gex_walls,
                wings_adjusted=signal.wings_adjusted,
                original_put_width=signal.original_put_width,
                original_call_width=signal.original_call_width,
                put_order_id="PAPER",
                call_order_id="PAPER",
                status=PositionStatus.OPEN,
                open_time=now,
                collateral_required=total_collateral,
            )

            if not self.db.save_position(position):
                logger.error(f"{self.config.bot_name}: Failed to save {position_id}")
                return None

            self.db.update_paper_balance(collateral_change=total_collateral)

            self.db.log_pdt_entry(
                position_id=position_id,
                symbol=self.config.ticker,
                opened_at=now,
                contracts=contracts,
                entry_credit=signal.total_credit,
            )

            account = self.db.get_paper_account()
            self.db.save_equity_snapshot(
                balance=account.balance,
                open_positions=self.db.get_position_count(),
                note=f"Opened {position_id}",
            )

            logger.info(
                f"{self.config.bot_name} PAPER OPEN: "
                f"{signal.put_long}/{signal.put_short}P-"
                f"{signal.call_short}/{signal.call_long}C "
                f"x{contracts} @ ${signal.total_credit:.2f} "
                f"(collateral: ${total_collateral:.2f})"
            )

            self.db.log(
                "TRADE_OPEN",
                f"Opened {position_id}: "
                f"{signal.put_long}/{signal.put_short}P-"
                f"{signal.call_short}/{signal.call_long}C "
                f"x{contracts} @ ${signal.total_credit:.2f}",
                {
                    "position_id": position_id,
                    "contracts": contracts,
                    "credit": signal.total_credit,
                    "collateral": total_collateral,
                    "wings_adjusted": signal.wings_adjusted,
                },
            )

            return position

        except Exception as e:
            logger.error(f"{self.config.bot_name}: Paper open failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def close_paper_position(
        self,
        position: IronCondorPosition,
        close_price: float,
        reason: str,
    ) -> Tuple[bool, float]:
        """
        Close a paper position and update P&L.

        P&L = (credit received - debit to close) * 100 * contracts
        """
        try:
            pnl_per_contract = (position.total_credit - close_price) * 100
            realized_pnl = round(pnl_per_contract * position.contracts, 2)

            if not self.db.close_position(
                position_id=position.position_id,
                close_price=close_price,
                realized_pnl=realized_pnl,
                close_reason=reason,
            ):
                logger.error(
                    f"{self.config.bot_name}: Failed to close "
                    f"{position.position_id} in DB"
                )
                return False, 0

            self.db.update_paper_balance(
                realized_pnl=realized_pnl,
                collateral_change=-position.collateral_required,
            )

            now = datetime.now(CENTRAL_TZ)
            self.db.update_pdt_close(
                position_id=position.position_id,
                closed_at=now,
                exit_cost=close_price,
                pnl=realized_pnl,
                close_reason=reason,
            )

            account = self.db.get_paper_account()
            self.db.save_equity_snapshot(
                balance=account.balance,
                realized_pnl=realized_pnl,
                open_positions=self.db.get_position_count(),
                note=f"Closed {position.position_id}: {reason}",
            )

            logger.info(
                f"{self.config.bot_name} PAPER CLOSE: "
                f"{position.position_id} @ ${close_price:.4f} "
                f"P&L=${realized_pnl:.2f} [{reason}]"
            )

            self.db.log(
                "TRADE_CLOSE",
                f"Closed {position.position_id}: ${realized_pnl:.2f} [{reason}]",
                {
                    "position_id": position.position_id,
                    "close_price": close_price,
                    "realized_pnl": realized_pnl,
                    "close_reason": reason,
                    "entry_credit": position.total_credit,
                },
            )

            return True, realized_pnl

        except Exception as e:
            logger.error(f"{self.config.bot_name}: Paper close failed: {e}")
            import traceback
            traceback.print_exc()
            return False, 0
