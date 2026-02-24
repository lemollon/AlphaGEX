"""
Databricks Job: SPARK (1DTE Iron Condor)
=========================================

Entry point for the SPARK trading bot as a Databricks Job.

Scheduling options:
  - Databricks Workflow: Run every 5 minutes during market hours (8:30-14:45 CT)
  - Cron expression: */5 14-20 * * 1-5 (UTC, Mon-Fri 14:30-20:45 UTC = 8:30-14:45 CT)

Usage:
  As a Databricks notebook or Python script task in a Workflow.
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("spark_job")


def main():
    from config import DatabricksConfig

    valid, msg = DatabricksConfig.validate()
    if not valid:
        logger.error(f"Config invalid: {msg}")
        sys.exit(1)

    from trading.trader import create_spark_trader

    trader = create_spark_trader()
    logger.info("SPARK trader initialized, running cycle...")

    result = trader.run_cycle()

    logger.info(f"SPARK cycle complete: action={result['action']}, traded={result['traded']}")
    if result.get("details"):
        logger.info(f"  Details: {result['details']}")

    return result


if __name__ == "__main__":
    main()
