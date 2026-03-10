"""
Position Monitor: Fast Exit Guardian
======================================

Lightweight job that ONLY monitors open positions for exit conditions.
Runs every 15 seconds — much faster than the full scan cycle (1-5 min).

What it does:
  1. Query open positions across ALL bots (FLAME, SPARK, INFERNO)
  2. Fetch MTM quotes in batch (1 API call per bot, not 4 per position)
  3. Close positions that hit profit target, stop loss, or EOD cutoff
  4. Mirror closes to Tradier sandbox accounts

What it does NOT do:
  - No signal generation
  - No new trade entry
  - No option chain scanning
  - No PDT checks or buying power calculations

This ensures exits happen within 15 seconds of hitting targets,
even when the full scanner is slow or queued.
"""

import sys
import os
import time
import logging
from datetime import datetime
from typing import List, Tuple, Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("position_monitor")

MONITOR_INTERVAL = 15  # seconds


class PositionMonitor:
    """
    Fast position exit monitor for all IronForge bots.

    Checks open positions every 15 seconds for:
      - Sliding profit target hit
      - Stop loss hit
      - EOD safety cutoff (2:45 PM CT)
      - Stale/expired positions from prior days
    """

    def __init__(self):
        from trading.models import (
            flame_config, spark_config, inferno_config, CENTRAL_TZ, EASTERN_TZ,
        )
        from trading.db import TradingDatabase
        from trading.executor import PaperExecutor
        from trading.tradier_client import TradierClient, build_occ_symbol

        self.CENTRAL_TZ = CENTRAL_TZ
        self.EASTERN_TZ = EASTERN_TZ
        self.build_occ_symbol = build_occ_symbol

        # One shared Tradier client for all MTM quotes
        self.tradier = TradierClient()

        # Per-bot config, database, and executor
        self.bots = {}
        for config_fn in [flame_config, spark_config, inferno_config]:
            config = config_fn()
            db = TradingDatabase(bot_name=config.bot_name, dte_mode=config.dte_mode)
            executor = PaperExecutor(config, db)
            self.bots[config.bot_name] = {
                "config": config,
                "db": db,
                "executor": executor,
            }

        logger.info(
            f"PositionMonitor initialized for {list(self.bots.keys())} "
            f"— checking every {MONITOR_INTERVAL}s"
        )

    def run_once(self) -> Dict[str, int]:
        """Run one monitoring pass across all bots. Returns {bot: positions_closed}."""
        now = datetime.now(self.CENTRAL_TZ)
        results = {}

        for bot_name, bot in self.bots.items():
            try:
                closed = self._check_bot(bot_name, bot, now)
                results[bot_name] = closed
            except Exception as e:
                logger.error(f"{bot_name}: Monitor check failed: {e}")
                results[bot_name] = 0

        return results

    def _check_bot(self, bot_name: str, bot: dict, now: datetime) -> int:
        """Check all open positions for a single bot. Returns count of positions closed."""
        db = bot["db"]
        executor = bot["executor"]
        config = bot["config"]

        positions = db.get_open_positions()
        if not positions:
            return 0

        # Build all OCC symbols for batch quote
        all_symbols = []
        position_symbols = {}  # position_id → [ps, pl, cs, cl] OCC symbols

        for pos in positions:
            try:
                exp_date = datetime.strptime(pos.expiration, "%Y-%m-%d")
                exp_str = exp_date.strftime("%y%m%d")

                def _sym(strike: float, opt_type: str) -> str:
                    strike_str = f"{int(strike * 1000):08d}"
                    return f"SPY{exp_str}{opt_type}{strike_str}"

                syms = [
                    _sym(pos.put_short_strike, "P"),
                    _sym(pos.put_long_strike, "P"),
                    _sym(pos.call_short_strike, "C"),
                    _sym(pos.call_long_strike, "C"),
                ]
                position_symbols[pos.position_id] = syms
                all_symbols.extend(syms)
            except Exception as e:
                logger.warning(f"{bot_name}: Failed to build symbols for {pos.position_id}: {e}")

        if not all_symbols:
            return 0

        # Single batch API call for all option quotes
        quotes = self.tradier.get_option_quotes_batch(all_symbols)

        closed_count = 0
        today_str = now.strftime("%Y-%m-%d")

        for pos in positions:
            syms = position_symbols.get(pos.position_id)
            if not syms:
                continue

            # Check stale/expired first (no quotes needed)
            position_date = None
            if pos.open_time:
                position_date = (
                    pos.open_time.strftime("%Y-%m-%d")
                    if hasattr(pos.open_time, "strftime")
                    else str(pos.open_time)[:10]
                )

            is_stale = position_date and position_date < today_str
            is_expired = pos.expiration < today_str

            if is_stale or is_expired:
                reason = "expired_previous_day" if is_expired else "stale_overnight_position"
                close_price = self._calc_mtm_from_quotes(quotes, syms)
                if close_price is None:
                    close_price = pos.total_credit
                success, pnl = executor.close_paper_position(pos, close_price, reason)
                if success:
                    closed_count += 1
                    logger.info(
                        f"MONITOR {bot_name}: Closed {pos.position_id} [{reason}] "
                        f"P&L=${pnl:.2f}"
                    )
                continue

            # Calculate MTM from batch quotes
            close_price = self._calc_mtm_from_quotes(quotes, syms)
            if close_price is None:
                # EOD safety even without quotes
                if self._is_past_eod_cutoff(now, config):
                    close_price = pos.total_credit
                    success, pnl = executor.close_paper_position(
                        pos, close_price, "eod_safety_no_data"
                    )
                    if success:
                        closed_count += 1
                        logger.info(
                            f"MONITOR {bot_name}: EOD close {pos.position_id} "
                            f"(no data) P&L=${pnl:.2f}"
                        )
                continue

            entry_credit = pos.total_credit

            # Sliding profit target
            pt_pct, pt_tier = self._get_sliding_profit_target(now, config)
            profit_target_price = entry_credit * (1 - pt_pct)
            if close_price <= profit_target_price:
                reason = f"profit_target_{pt_tier.lower()}"
                success, pnl = executor.close_paper_position(pos, close_price, reason)
                if success:
                    closed_count += 1
                    logger.info(
                        f"MONITOR {bot_name}: PROFIT TARGET {pt_tier} ({pt_pct:.0%}) "
                        f"{pos.position_id} debit=${close_price:.4f} <= "
                        f"threshold=${profit_target_price:.4f} P&L=${pnl:.2f}"
                    )
                continue

            # Stop loss
            stop_loss_price = entry_credit * (1 + config.stop_loss_pct / 100)
            if close_price >= stop_loss_price:
                success, pnl = executor.close_paper_position(pos, close_price, "stop_loss")
                if success:
                    closed_count += 1
                    logger.info(
                        f"MONITOR {bot_name}: STOP LOSS {pos.position_id} "
                        f"debit=${close_price:.4f} >= stop=${stop_loss_price:.4f} "
                        f"P&L=${pnl:.2f}"
                    )
                continue

            # EOD safety close
            if self._is_past_eod_cutoff(now, config):
                success, pnl = executor.close_paper_position(pos, close_price, "eod_safety")
                if success:
                    closed_count += 1
                    logger.info(
                        f"MONITOR {bot_name}: EOD CLOSE {pos.position_id} "
                        f"P&L=${pnl:.2f}"
                    )
                continue

        return closed_count

    def _calc_mtm_from_quotes(
        self, quotes: Dict[str, Dict], syms: List[str]
    ) -> Optional[float]:
        """Calculate cost-to-close from pre-fetched batch quotes."""
        ps_q = quotes.get(syms[0])
        pl_q = quotes.get(syms[1])
        cs_q = quotes.get(syms[2])
        cl_q = quotes.get(syms[3])

        if not all([ps_q, pl_q, cs_q, cl_q]):
            return None

        # Cost to close: buy back shorts at ask, sell longs at bid
        cost = (
            float(ps_q.get("ask", 0) or 0)
            + float(cs_q.get("ask", 0) or 0)
            - float(pl_q.get("bid", 0) or 0)
            - float(cl_q.get("bid", 0) or 0)
        )
        return max(0, round(cost, 4))

    def _get_sliding_profit_target(
        self, ct_now: datetime, config
    ) -> Tuple[float, str]:
        """Return sliding profit target percentage and tier label."""
        time_minutes = ct_now.hour * 60 + ct_now.minute
        is_inferno = config.bot_name == "INFERNO"

        if time_minutes < 630:       # before 10:30 AM CT
            return (0.50 if is_inferno else 0.30), "MORNING"
        elif time_minutes < 780:     # before 1:00 PM CT
            return (0.30 if is_inferno else 0.20), "MIDDAY"
        else:
            return (0.10 if is_inferno else 0.15), "AFTERNOON"

    def _is_past_eod_cutoff(self, now: datetime, config) -> bool:
        """Check if past EOD cutoff (3:45 PM ET = 2:45 PM CT)."""
        now_et = now.astimezone(self.EASTERN_TZ)
        cutoff_parts = config.eod_cutoff_et.split(":")
        cutoff_hour = int(cutoff_parts[0])
        cutoff_minute = int(cutoff_parts[1])

        if now_et.hour > cutoff_hour:
            return True
        if now_et.hour == cutoff_hour and now_et.minute >= cutoff_minute:
            return True
        return False


def main():
    from config import Config

    valid, msg = Config.validate()
    if not valid:
        logger.error(f"Config invalid: {msg}")
        sys.exit(1)

    from setup_tables import setup_all_tables
    setup_all_tables()

    monitor = PositionMonitor()
    logger.info(f"Position monitor started — checking every {MONITOR_INTERVAL}s")

    cycle = 0
    while True:
        cycle += 1
        start = time.time()

        try:
            results = monitor.run_once()
            total_closed = sum(results.values())
            elapsed = time.time() - start

            # Only log details when there are open positions or closures
            has_activity = total_closed > 0

            if has_activity:
                logger.info(
                    f"Monitor #{cycle}: CLOSED {total_closed} position(s) "
                    f"in {elapsed:.1f}s — {results}"
                )
            elif cycle % 20 == 1:
                # Heartbeat log every ~5 minutes (20 cycles × 15s)
                logger.info(
                    f"Monitor #{cycle}: No open positions — heartbeat OK "
                    f"({elapsed:.1f}s)"
                )

        except Exception as e:
            logger.error(f"Monitor #{cycle} error: {e}", exc_info=True)

        time.sleep(MONITOR_INTERVAL)


if __name__ == "__main__":
    main()
