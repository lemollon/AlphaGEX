"""
Render Worker: FLAME (2DTE Iron Condor)
========================================

Entry point for the FLAME trading bot as a Render worker.

Runs a proper loop with adaptive sleep: fast (60s) during active trading,
longer when done for the day or before market open.
"""

import sys
import os
import time
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("flame_job")


def main():
    from config import Config

    valid, msg = Config.validate()
    if not valid:
        logger.error(f"Config invalid: {msg}")
        sys.exit(1)

    # Ensure tables exist (once at startup)
    from setup_tables import setup_all_tables
    setup_all_tables()

    from trading.trader import create_flame_trader

    trader = create_flame_trader()
    logger.info("FLAME trader initialized, starting adaptive loop...")

    scan_num = 0
    while True:
        scan_num += 1
        sleep_secs = 60  # default fallback
        try:
            logger.info(f"FLAME scan #{scan_num} started")
            result = trader.run_cycle()
            action = result.get("action", "unknown")
            md = result.get("market_data", {})
            details = result.get("details", {})
            reason = details.get("reason", "") if isinstance(details, dict) else str(details)
            sleep_secs = result.get("sleep_hint", 60)

            spy_str = f" SPY=${md['spy']}" if md.get("spy") else ""
            vix_str = f" VIX={md['vix']}" if md.get("vix") else ""

            next_time = time.strftime(
                "%H:%M CT", time.localtime(time.time() + sleep_secs)
            )
            logger.info(
                f"FLAME scan #{scan_num}: {action}{spy_str}{vix_str}"
                f" | traded={result['traded']}"
                f" | {reason}"
                f" | next={next_time} (sleep {sleep_secs}s)"
            )
        except Exception as e:
            logger.error(f"FLAME cycle #{scan_num} error: {e}", exc_info=True)

        time.sleep(sleep_secs)


if __name__ == "__main__":
    main()
