"""
Combined Runner: FLAME + SPARK + INFERNO
==========================================

Runs all three bots in a single process using threads.
Designed for Databricks where each job costs money — one job instead of three.

Each bot uses adaptive sleep: fast during active trading, long sleeps when
done for the day or before market open.
"""

import sys
import os
import time
import signal
import logging
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("ironforge_combined")


def run_bot(bot_name: str, create_fn):
    """Run a single bot in an infinite loop with adaptive sleep."""
    bot_logger = logging.getLogger(bot_name.lower())
    try:
        trader = create_fn()
        bot_logger.info(f"{bot_name} initialized")
    except Exception as e:
        bot_logger.error(f"{bot_name} init failed: {e}", exc_info=True)
        return

    scan_num = 0
    while True:
        scan_num += 1
        sleep_secs = 60
        try:
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
            bot_logger.info(
                f"#{scan_num}: {action}{spy_str}{vix_str}"
                f" | traded={result['traded']}"
                f" | {reason}"
                f" | next={next_time} (sleep {sleep_secs}s)"
            )
        except Exception as e:
            bot_logger.error(f"#{scan_num} error: {e}", exc_info=True)

        time.sleep(sleep_secs)


def main():
    from config import Config

    valid, msg = Config.validate()
    if not valid:
        logger.error(f"Config invalid: {msg}")
        sys.exit(1)

    from setup_tables import setup_all_tables
    setup_all_tables()

    from trading.trader import create_flame_trader, create_spark_trader, create_inferno_trader

    bots = [
        ("FLAME", create_flame_trader),
        ("SPARK", create_spark_trader),
        ("INFERNO", create_inferno_trader),
    ]

    threads = []
    for bot_name, create_fn in bots:
        t = threading.Thread(target=run_bot, args=(bot_name, create_fn), daemon=True)
        t.start()
        threads.append(t)
        logger.info(f"Started {bot_name} thread")

    logger.info(f"All {len(bots)} bots running. Press Ctrl+C to stop.")

    # Graceful shutdown on SIGTERM (Render sends this before killing the process)
    shutdown = threading.Event()

    def handle_sigterm(signum: int, frame: object) -> None:
        logger.info("SIGTERM received — shutting down gracefully...")
        shutdown.set()

    signal.signal(signal.SIGTERM, handle_sigterm)

    # Keep main thread alive until shutdown or KeyboardInterrupt
    try:
        shutdown.wait()
    except KeyboardInterrupt:
        pass

    logger.info("Shutdown complete.")


if __name__ == "__main__":
    main()
