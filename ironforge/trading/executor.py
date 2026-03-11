"""
Paper Trade Executor
=====================

Executes paper trades using real Tradier market data.
Paper fills use real bid/ask prices, then mirrors the same trade
to all three Tradier sandbox accounts for simulated execution.

Fill rules:
- Sells fill at bid (conservative)
- Buys fill at ask (conservative)
- Net credit = (short_put_bid + short_call_bid) - (long_put_ask + long_call_ask)
"""

import uuid
import json
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Dict

from .models import (
    IronCondorPosition,
    IronCondorSignal,
    BotConfig,
    PositionStatus,
    DailySummary,
    CENTRAL_TZ,
)
from .db import TradingDatabase
from .tradier_client import TradierClient

logger = logging.getLogger(__name__)


class PaperExecutor:
    """
    Paper trade executor for SPARK and FLAME bots.

    Uses real Tradier bid/ask for fill simulation.
    Tracks paper account balance, collateral, and P&L.
    FLAME trades are mirrored to all 3 Tradier sandbox accounts;
    SPARK is paper-only.
    """

    def __init__(self, config: BotConfig, db: TradingDatabase):
        self.config = config
        self.db = db
        self._tradier: Optional[TradierClient] = None
        self._sandbox_clients: Optional[List[Dict]] = None

    @property
    def tradier(self) -> TradierClient:
        """Lazy-init Tradier client for market data."""
        if self._tradier is None:
            self._tradier = TradierClient()
        return self._tradier

    @property
    def sandbox_clients(self) -> List[Dict]:
        """Lazy-init list of sandbox TradierClient instances (one per account)."""
        if self._sandbox_clients is None:
            from config import Config
            accounts = Config.get_sandbox_accounts()
            sandbox_url = Config.TRADIER_SANDBOX_URL
            self._sandbox_clients = []
            for acct in accounts:
                client = TradierClient(
                    api_key=acct["api_key"],
                    base_url=sandbox_url,
                    account_id=acct["account_id"],
                )
                self._sandbox_clients.append({
                    "name": acct["name"],
                    "client": client,
                })
            if self._sandbox_clients:
                logger.info(
                    f"{self.config.bot_name}: Loaded {len(self._sandbox_clients)} "
                    f"sandbox accounts: {[c['name'] for c in self._sandbox_clients]}"
                )
            else:
                logger.warning(
                    f"{self.config.bot_name}: No sandbox accounts configured"
                )
        return self._sandbox_clients

    def _mirror_open_to_all_sandboxes(
        self, position: IronCondorPosition
    ) -> Dict[str, Dict]:
        """
        Mirror a paper open to all 3 Tradier sandbox accounts.

        Returns dict of {account_name: {order_id, fill_price}} for successful mirrors.
        Reads back actual fill prices from each account so P&L can match Tradier.
        Non-fatal: failures are logged but don't block paper trading.
        """
        results = {}
        for sandbox in self.sandbox_clients:
            name = sandbox["name"]
            client: TradierClient = sandbox["client"]
            try:
                result = client.place_ic_order(
                    ticker=position.ticker,
                    expiration=position.expiration,
                    put_short=position.put_short_strike,
                    put_long=position.put_long_strike,
                    call_short=position.call_short_strike,
                    call_long=position.call_long_strike,
                    contracts=position.contracts,
                    total_credit=position.total_credit,
                    tag=position.position_id,
                )
                if result and result.get("order_id"):
                    order_id = str(result["order_id"])
                    info = {"order_id": order_id, "fill_price": None}
                    # Read back actual fill price
                    try:
                        fill = client.get_order_fill_price(int(order_id))
                        if fill is not None and fill > 0:
                            info["fill_price"] = fill
                    except Exception as fe:
                        logger.warning(
                            f"{self.config.bot_name}: Fill readback failed [{name}]: {fe}"
                        )
                    results[name] = info
                    logger.info(
                        f"{self.config.bot_name} SANDBOX MIRROR [{name}]: "
                        f"{position.position_id} → order {order_id} "
                        f"fill=${info['fill_price']}"
                    )
                else:
                    logger.warning(
                        f"{self.config.bot_name} SANDBOX MIRROR FAILED [{name}]: "
                        f"{position.position_id} — no order ID returned"
                    )
            except Exception as e:
                logger.warning(
                    f"{self.config.bot_name} SANDBOX MIRROR ERROR [{name}]: "
                    f"{position.position_id} — {e}"
                )
        return results

    def _get_user_fill_price(self, sandbox_info: Dict[str, Dict]) -> Optional[float]:
        """Extract the User account's fill price from sandbox info dict.

        Returns the fill price (positive) or None if unavailable.
        """
        user_info = sandbox_info.get("User")
        if user_info and user_info.get("fill_price") is not None:
            return user_info["fill_price"]
        # Fallback: try any account
        for name, info in sandbox_info.items():
            if info.get("fill_price") is not None and info["fill_price"] > 0:
                logger.info(
                    f"{self.config.bot_name}: Using [{name}] fill as fallback "
                    f"(User fill unavailable)"
                )
                return info["fill_price"]
        return None

    def _mirror_close_to_all_sandboxes(
        self, position: IronCondorPosition, close_price: float
    ) -> Dict[str, Dict]:
        """
        Mirror a paper close to all 3 Tradier sandbox accounts.

        Returns dict of {account_name: {order_id, fill_price}} for successful closes.
        Reads back actual fill prices from each account so P&L can match Tradier.
        Non-fatal: failures are logged but don't block paper trading.
        """
        results = {}
        for sandbox in self.sandbox_clients:
            name = sandbox["name"]
            client: TradierClient = sandbox["client"]
            try:
                result = client.close_ic_order(
                    ticker=position.ticker,
                    expiration=position.expiration,
                    put_short=position.put_short_strike,
                    put_long=position.put_long_strike,
                    call_short=position.call_short_strike,
                    call_long=position.call_long_strike,
                    contracts=position.contracts,
                    close_price=close_price,
                    tag=f"CLOSE-{position.position_id}",
                )
                if result and result.get("order_id"):
                    order_id = str(result["order_id"])
                    info = {"order_id": order_id, "fill_price": None}
                    # Read back actual fill price
                    try:
                        fill = client.get_order_fill_price(int(order_id))
                        if fill is not None and fill > 0:
                            info["fill_price"] = fill
                    except Exception as fe:
                        logger.warning(
                            f"{self.config.bot_name}: Close fill readback failed [{name}]: {fe}"
                        )
                    results[name] = info
                    logger.info(
                        f"{self.config.bot_name} SANDBOX CLOSE [{name}]: "
                        f"{position.position_id} → order {order_id} "
                        f"fill=${info['fill_price']}"
                    )
                else:
                    logger.warning(
                        f"{self.config.bot_name} SANDBOX CLOSE FAILED [{name}]: "
                        f"{position.position_id} — no order ID returned"
                    )
            except Exception as e:
                logger.warning(
                    f"{self.config.bot_name} SANDBOX CLOSE ERROR [{name}]: "
                    f"{position.position_id} — {e}"
                )
        return results

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
                realized_pnl=account.cumulative_pnl,
                unrealized_pnl=0.0,
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

            # FLAME: Tradier sandbox is SOURCE OF TRUTH (1:1 sync).
            # Mirror to sandbox FIRST, wait for User fill, use that price.
            # If User doesn't fill → abort (position already saved, will be cleaned up).
            # SPARK/INFERNO: no sandbox mirroring.
            sandbox_info = {}
            actual_fill_credit = None
            is_flame = self.config.bot_name == "FLAME"

            if is_flame and self.sandbox_clients:
                sandbox_info = self._mirror_open_to_all_sandboxes(position)
                if sandbox_info:
                    self.db.update_sandbox_order_id(
                        position_id, json.dumps(sandbox_info)
                    )
                    actual_fill_credit = self._get_user_fill_price(sandbox_info)

                if actual_fill_credit is None or actual_fill_credit <= 0:
                    # FLAME: User sandbox didn't fill — abort trade
                    logger.error(
                        f"{self.config.bot_name}: Tradier User sandbox did not fill. "
                        f"Removing paper position {position_id}."
                    )
                    self.db.close_position(
                        position_id=position_id,
                        close_price=signal.total_credit,
                        realized_pnl=0.0,
                        close_reason="sandbox_not_filled_abort",
                    )
                    self.db.update_paper_balance(
                        collateral_change=-total_collateral,
                    )
                    self.db.log(
                        "ERROR",
                        f"FLAME 1:1 ABORT: {position_id} — User sandbox not filled",
                    )
                    return None

            # If we got an actual fill, update the position so the frontend
            # and P&L math use the real Tradier fill, not our bid/ask estimate.
            credit_used = signal.total_credit
            if actual_fill_credit is not None and actual_fill_credit > 0:
                logger.info(
                    f"{self.config.bot_name}: Actual sandbox fill=${actual_fill_credit:.4f} "
                    f"(estimated=${signal.total_credit:.4f}, "
                    f"diff={actual_fill_credit - signal.total_credit:+.4f})"
                )
                self.db.update_position_fill(
                    position_id=position_id,
                    actual_credit=actual_fill_credit,
                )
                credit_used = actual_fill_credit

            sandbox_summary = (
                f" [sandbox:{sandbox_info}]" if sandbox_info else ""
            )
            fill_note = (
                f" (actual fill=${actual_fill_credit:.4f})"
                if actual_fill_credit and actual_fill_credit != signal.total_credit
                else ""
            )
            self.db.log(
                "TRADE_OPEN",
                f"Opened {position_id}: "
                f"{signal.put_long}/{signal.put_short}P-"
                f"{signal.call_short}/{signal.call_long}C "
                f"x{contracts} @ ${credit_used:.4f}{fill_note}"
                f"{sandbox_summary}",
                {
                    "position_id": position_id,
                    "contracts": contracts,
                    "credit_estimated": signal.total_credit,
                    "credit_actual": actual_fill_credit,
                    "credit": credit_used,
                    "collateral": total_collateral,
                    "wings_adjusted": signal.wings_adjusted,
                    "sandbox_order_ids": sandbox_info,
                },
            )

            # Update daily performance
            self.db.update_daily_performance(DailySummary(
                date=now.strftime("%Y-%m-%d"),
                trades_executed=1,
                positions_closed=0,
                realized_pnl=0,
            ))

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

        Mirrors the close to Tradier sandbox accounts first, then reads back
        the actual fill price so the paper P&L matches Tradier exactly.

        P&L = (credit received - debit to close) * 100 * contracts
        """
        try:
            # FLAME: Tradier sandbox is SOURCE OF TRUTH (1:1 sync).
            #   - Close User sandbox first, WAIT for fill
            #   - Use User fill price for paper P&L (overrides calculated MTM)
            #   - Matt/Logan are best-effort
            # SPARK/INFERNO: paper-only, no sandbox mirroring.
            sandbox_close_info = {}
            actual_close_price = None
            is_flame = self.config.bot_name == "FLAME"
            price_source = "calculated"

            if is_flame and self.sandbox_clients:
                sandbox_close_info = self._mirror_close_to_all_sandboxes(
                    position, close_price
                )
                if sandbox_close_info:
                    actual_close_price = self._get_user_fill_price(
                        sandbox_close_info
                    )

            # FLAME 1:1: Use sandbox fill as paper close price.
            # SPARK/INFERNO: Use calculated MTM.
            effective_close = close_price
            if actual_close_price is not None and actual_close_price >= 0:
                logger.info(
                    f"{self.config.bot_name}: FLAME 1:1 close: using sandbox fill "
                    f"${actual_close_price:.4f} "
                    f"(MTM was ${close_price:.4f}, "
                    f"diff={actual_close_price - close_price:+.4f})"
                )
                effective_close = actual_close_price
                price_source = "sandbox_fill"
            elif is_flame:
                logger.warning(
                    f"{self.config.bot_name}: FLAME close: User fill not available, "
                    f"falling back to calculated MTM ${close_price:.4f}"
                )

            pnl_per_contract = (position.total_credit - effective_close) * 100
            realized_pnl = round(pnl_per_contract * position.contracts, 2)

            if not self.db.close_position(
                position_id=position.position_id,
                close_price=effective_close,
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
                exit_cost=effective_close,
                pnl=realized_pnl,
                close_reason=reason,
            )

            account = self.db.get_paper_account()
            self.db.save_equity_snapshot(
                balance=account.balance,
                realized_pnl=account.cumulative_pnl,
                open_positions=self.db.get_position_count(),
                note=f"Closed {position.position_id}: {reason}",
            )

            if sandbox_close_info:
                self.db.update_sandbox_close_order_id(
                    position.position_id, json.dumps(sandbox_close_info)
                )

            sandbox_summary = (
                f" [sandbox:{sandbox_close_info}]"
                if sandbox_close_info
                else ""
            )
            fill_note = (
                f" (actual fill=${actual_close_price:.4f})"
                if actual_close_price and actual_close_price != close_price
                else ""
            )
            logger.info(
                f"{self.config.bot_name} PAPER CLOSE: "
                f"{position.position_id} @ ${effective_close:.4f} "
                f"P&L=${realized_pnl:.2f} [{reason}]{fill_note}"
                f"{sandbox_summary}"
            )

            fill_delta_pct = (
                round(abs(actual_close_price - close_price) / close_price * 100, 1)
                if actual_close_price is not None and close_price > 0
                else None
            )
            self.db.log(
                "TRADE_CLOSE",
                f"Closed {position.position_id}: ${realized_pnl:.2f} [{reason}]"
                f"{fill_note}{sandbox_summary}",
                {
                    "position_id": position.position_id,
                    "close_price_estimated": close_price,
                    "close_price_actual": actual_close_price,
                    "close_price": effective_close,
                    "price_source": price_source,
                    "fill_delta_pct": fill_delta_pct,
                    "realized_pnl": realized_pnl,
                    "close_reason": reason,
                    "entry_credit": position.total_credit,
                    "sandbox_close_order_ids": sandbox_close_info,
                },
            )

            # Update daily performance
            self.db.update_daily_performance(DailySummary(
                date=now.strftime("%Y-%m-%d"),
                trades_executed=0,
                positions_closed=1,
                realized_pnl=realized_pnl,
            ))

            return True, realized_pnl

        except Exception as e:
            logger.error(f"{self.config.bot_name}: Paper close failed: {e}")
            import traceback
            traceback.print_exc()
            return False, 0
