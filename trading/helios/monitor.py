"""HELIOS position monitor — polls Tradier every 15s, closes on PT/SL/EOD.

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
from trading.helios.models import HeliosConfig
from trading.helios.strategy import decide_exit

logger = logging.getLogger(__name__)

CT_OFFSET = dt.timedelta(hours=-5)  # CDT (DST). For CST use -6.
                                     # Acceptable approximation since EOD check
                                     # only cares about HH:MM in CT.


class HeliosMonitor:
    def __init__(self, db: HeliosDatabase, tradier, config: HeliosConfig):
        self.db = db
        self.tradier = tradier  # injectable for tests; live wiring uses TradierClient
        self.config = config

    def run_one_cycle(self) -> Optional[float]:
        """Returns realized PnL if a position was closed, else None."""
        pos = self.db.get_open_position()
        if pos is None:
            return None

        long_sym = pos["long_symbol"]
        short_sym = pos["short_symbol"]
        try:
            quotes = self.tradier.get_option_quotes_batch([long_sym, short_sym])
        except Exception as e:
            logger.warning("HELIOS monitor: quote fetch failed: %s", e)
            return None

        long_q = quotes.get(long_sym)
        short_q = quotes.get(short_sym)
        if long_q is None or short_q is None:
            logger.warning("HELIOS monitor: QUOTE_UNAVAILABLE long=%s short=%s",
                           bool(long_q), bool(short_q))
            return None

        try:
            long_bid = float(long_q["bid"])
            short_ask = float(short_q["ask"])
        except (KeyError, TypeError, ValueError):
            logger.warning("HELIOS monitor: bid/ask parse failed long=%r short=%r",
                           long_q, short_q)
            return None

        mark_to_close = long_bid - short_ask

        open_time = pos["open_time"]
        if open_time.tzinfo is None:
            open_time = open_time.replace(tzinfo=dt.timezone.utc)
        now_utc = dt.datetime.now(dt.timezone.utc)
        minutes_in = max(0, int((now_utc - open_time).total_seconds() // 60))

        # Convert to "now in CT" purely for the EOD check
        now_ct = now_utc + CT_OFFSET

        decision = decide_exit(
            debit=float(pos["debit"]),
            mark_to_close=mark_to_close,
            minutes_since_entry=minutes_in,
            now_ct=now_ct,
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
            "HELIOS exit: id=%s reason=%s mtc=%.4f debit=%.4f minutes=%d pnl=%.2f",
            pos["id"], decision.reason.value, mark_to_close, float(pos["debit"]),
            minutes_in, realized_pnl,
        )
        self.db.log("INFO", "exit", {
            "position_id": pos["id"],
            "reason": decision.reason.value,
            "mark_to_close": mark_to_close,
            "minutes_since_entry": minutes_in,
            "realized_pnl": realized_pnl,
        })
        return realized_pnl

    def run_forever(self) -> None:
        logger.info("HELIOS monitor starting; poll=%ds", self.config.monitor_poll_seconds)
        while True:
            try:
                self.run_one_cycle()
            except Exception:
                logger.exception("HELIOS monitor: cycle error")
            time.sleep(self.config.monitor_poll_seconds)
