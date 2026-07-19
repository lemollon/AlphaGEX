"""
ZEPHYR Executor - turn signals into orders (paper or live), compute fills/fees.

Maker-first: a maker scalp posts a resting limit one tick inside the spread.
Taker scalps cross with a fill-or-kill marketable limit. In PAPER mode fills
are simulated optimistically at the signal limit; in LIVE mode orders go to
Kalshi via KalshiClient. Live is gated by BOTH live_enabled and the fee gate
having already passed in signals.evaluate().
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from .models import (
    CENTRAL_TZ,
    DEFAULT_MAKER_FEE_COEFF,
    DEFAULT_TAKER_FEE_COEFF,
    ExitReason,
    ScalpPosition,
    ScalpSignal,
    SignalAction,
    Side,
    PositionStatus,
    kalshi_fee,
    market_config,
)

logger = logging.getLogger(__name__)


class ZephyrExecutor:
    def __init__(self, kalshi_client=None, live_enabled: bool = False):
        self.kalshi = kalshi_client
        self.live_enabled = live_enabled

    @property
    def is_live(self) -> bool:
        return bool(self.live_enabled and self.kalshi is not None and self.kalshi.can_trade)

    # ------------------------------------------------------------- open
    def open_scalp(self, sig: ScalpSignal) -> Optional[ScalpPosition]:
        if not sig.is_trade or sig.side is None or sig.limit_cents is None:
            return None
        is_maker = sig.action in (SignalAction.BUY_YES_MAKER, SignalAction.BUY_NO_MAKER)
        cfg = market_config(sig.sport)
        coeff = (cfg["fees"]["maker_coeff"] if is_maker else cfg["fees"]["taker_coeff"])
        entry_fee = kalshi_fee(sig.limit_cents, sig.contracts, coeff)

        pos = ScalpPosition(
            position_id=f"zephyr-{uuid.uuid4().hex[:12]}",
            market_id=sig.market_id, sport=sig.sport, side=sig.side,
            contracts=sig.contracts, entry_cents=sig.limit_cents,
            fair_at_entry_cents=sig.fair_cents, is_maker=is_maker,
            open_time=datetime.now(CENTRAL_TZ), entry_fee=entry_fee,
            is_paper=not self.is_live, status=PositionStatus.OPEN,
        )

        if self.is_live:
            try:
                resp = self.kalshi.place_order(
                    ticker=sig.market_id,
                    side="yes" if sig.side == Side.YES else "no",
                    action="buy", count=sig.contracts,
                    order_type="limit", price_cents=int(round(sig.limit_cents)),
                    time_in_force="fill_or_kill" if not is_maker else "good_till_cancelled",
                    client_order_id=pos.position_id,
                )
                pos.kalshi_order_id = (resp.get("order") or {}).get("order_id")
                # A maker post may rest unfilled; mark pending until confirmed.
                pos.status = PositionStatus.PENDING if is_maker else PositionStatus.OPEN
            except Exception as e:
                logger.error("zephyr live open failed (%s): %s", sig.market_id, e)
                return None
        return pos

    # ------------------------------------------------------------- close
    def close_scalp(self, pos: ScalpPosition, exit_cents: float,
                    reason: ExitReason) -> ScalpPosition:
        cfg = market_config(pos.sport)
        # Exits cross the book -> taker fee.
        exit_fee = kalshi_fee(exit_cents, pos.contracts, cfg["fees"]["taker_coeff"])
        gross = pos.gross_pnl(exit_cents)
        net = gross - pos.entry_fee - exit_fee

        if self.is_live and not pos.is_paper:
            try:
                self.kalshi.place_order(
                    ticker=pos.market_id,
                    side="yes" if pos.side == Side.YES else "no",
                    action="sell", count=pos.contracts,
                    order_type="limit", price_cents=int(round(exit_cents)),
                    time_in_force="fill_or_kill",
                    client_order_id=f"{pos.position_id}-exit",
                )
            except Exception as e:
                logger.error("zephyr live close failed (%s): %s", pos.market_id, e)
                # fall through: still record intent; reconciliation will fix.

        pos.status = PositionStatus.CLOSED
        pos.close_time = datetime.now(CENTRAL_TZ)
        pos.exit_cents = exit_cents
        pos.exit_reason = reason
        pos.exit_fee = exit_fee
        pos.realized_pnl = round(net, 4)
        return pos
