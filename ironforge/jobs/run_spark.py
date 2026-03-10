"""
Render Worker: SPARK (1DTE Iron Condor)
========================================

Entry point for the SPARK trading bot as a Render worker.

Runs a proper loop: one cycle every 1 minute during market hours.
"""

import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("spark_job")

CYCLE_INTERVAL = 60  # 1 minute


def main():
    from config import Config

    valid, msg = Config.validate()
    if not valid:
        logger.error(f"Config invalid: {msg}")
        sys.exit(1)

    # Ensure tables exist (once at startup)
    from setup_tables import setup_all_tables
    setup_all_tables()

    from trading.trader import create_spark_trader

    trader = create_spark_trader()
    logger.info("SPARK trader initialized, starting 1-min loop...")

    scan_num = 0
    while True:
        scan_num += 1
        try:
            logger.info(f"SPARK scan #{scan_num} started")
            result = trader.run_cycle()
            action = result.get("action", "unknown")
            md = result.get("market_data", {})
            details = result.get("details", {})
            reason = details.get("reason", "") if isinstance(details, dict) else str(details)

            spy_str = f" SPY=${md['spy']}" if md.get("spy") else ""
            vix_str = f" VIX={md['vix']}" if md.get("vix") else ""

            next_time = time.strftime(
                "%H:%M CT", time.localtime(time.time() + CYCLE_INTERVAL)
            )
            logger.info(
                f"SPARK scan #{scan_num}: {action}{spy_str}{vix_str}"
                f" | traded={result['traded']}"
                f" | {reason}"
                f" | next={next_time}"
            )
        except Exception as e:
            logger.error(f"SPARK cycle #{scan_num} error: {e}", exc_info=True)

        time.sleep(CYCLE_INTERVAL)


if __name__ == "__main__":
    main()
