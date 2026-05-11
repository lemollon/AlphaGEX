"""JOSHUA position monitor — polls Tradier every poll_seconds, closes on PT/SL/TIME_STOP.

Mirrors the SPARK monitor pattern but scoped to one bot, one position.
Runs forever in the alphagex-trader worker. Each cycle:
  1. Get the (single) open HELIOS position from DB
  2. Pull both legs' bid/ask from Tradier in one batch quote call
  3. Compute mark_to_close = bid(long) - ask(short)
  4. Call decide_exit(...) — pure function, no I/O
  5. If exit triggered → close via executor.close_paper()
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Optional

from trading.helios.db import HeliosDatabase
from trading.helios.executor import close_paper
from trading.helios.models import JoshuaConfig
from trading.helios.strategy import decide_exit

logger = logging.getLogger(__name__)

CT_OFFSET = dt.timedelta(hours=-5)  # CDT/CST approximation; only HH:MM matters for TIME_STOP.


class HeliosMonitor:
    def __init__(self, db: HeliosDatabase, tradier, config: JoshuaConfig):
        self.db = db
        self.tradier = tradier
        self.config = config
        self._streak: int = 0

    def run_one_cycle(self) -> Optional[float]:
        """Returns realized PnL if a position was closed, else None."""
        pos = self.db.get_open_position()
        if pos is None:
            self._streak = 0
            return None

        long_sym = pos["long_symbol"]
        short_sym = pos["short_symbol"]
        try:
            quotes = self.tradier.get_option_quotes_batch([long_sym, short_sym])
        except Exception as e:
            logger.warning("HELIOS monitor: quote fetch failed: %s", e)
            self._streak += 1
            return None

        long_q = quotes.get(long_sym)
        short_q = quotes.get(short_sym)
        if long_q is None or short_q is None:
            logger.warning("HELIOS monitor: QUOTE_UNAVAILABLE long=%s short=%s",
                           bool(long_q), bool(short_q))
            self._streak += 1
            return None

        try:
            long_bid = float(long_q["bid"])
            short_ask = float(short_q["ask"])
        except (KeyError, TypeError, ValueError):
            logger.warning("HELIOS monitor: bid/ask parse failed long=%r short=%r",
                           long_q, short_q)
            self._streak += 1
            return None

        self._streak = 0
        mark_to_close = long_bid - short_ask
        now_utc = dt.datetime.now(dt.timezone.utc)
        now_ct = now_utc + CT_OFFSET

        decision = decide_exit(
            debit=float(pos["debit"]),
            mark_to_close=mark_to_close,
            now_ct=now_ct,
            quotes_unavail_streak=self._streak,
            config=self.config,
        )

        if not decision.should_exit:
            return None

        realized_pnl = close_paper(
            db=self.db,
            position_id=pos["id"],
            mark_to_close=mark_to_close,
            exit_reason=decision.reason.value,
        )
        logger.info(
            "HELIOS exit: id=%s reason=%s mtc=%.4f debit=%.4f pnl=%.2f",
            pos["id"], decision.reason.value, mark_to_close, float(pos["debit"]), realized_pnl,
        )
        self.db.log("INFO", "exit", {
            "position_id": pos["id"],
            "reason": decision.reason.value,
            "mark_to_close": mark_to_close,
            "realized_pnl": realized_pnl,
        })
        return realized_pnl

    def run_forever(self) -> None:
        logger.info("HELIOS monitor starting; poll=%ds", self.config.poll_seconds)
        while True:
            try:
                self.run_one_cycle()
            except Exception:
                logger.exception("HELIOS monitor: cycle error")
            time.sleep(self.config.poll_seconds)
