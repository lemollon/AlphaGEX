"""
Render Worker: FLAME (2DTE Iron Condor)
========================================

Entry point for the FLAME trading bot as a Render worker.

Runs a proper loop: one cycle every 5 minutes during market hours.
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

CYCLE_INTERVAL = 300  # 5 minutes


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
    logger.info("FLAME trader initialized, starting 5-min loop...")

    while True:
        try:
            result = trader.run_cycle()
            logger.info(
                f"FLAME cycle: action={result['action']}, traded={result['traded']}"
            )
            if result.get("details"):
                logger.info(f"  Details: {result['details']}")
        except Exception as e:
            logger.error(f"FLAME cycle error: {e}", exc_info=True)

        time.sleep(CYCLE_INTERVAL)


if __name__ == "__main__":
    main()
