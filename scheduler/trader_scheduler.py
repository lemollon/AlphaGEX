"""AlphaGEX trading scheduler.

Active systems only:
- VALOR (micro futures)
- AGAPE crypto perpetuals: BTC, ETH, SOL, AVAX, XRP, DOGE, SHIB (paper only)

SpreadWorks and IronForge are separate protected projects and are intentionally
not imported or scheduled here.
"""

import logging
import signal
import time
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from trading.valor import ValorConfig, ValorTrader, TradingMode as ValorTradingMode
from trading.agape_btc_perp.trader import create_agape_btc_perp_trader
from trading.agape_eth_perp.trader import create_agape_eth_perp_trader
from trading.agape_sol_perp.trader import create_agape_sol_perp_trader
from trading.agape_avax_perp.trader import create_agape_avax_perp_trader
from trading.agape_xrp_perp.trader import create_agape_xrp_perp_trader
from trading.agape_doge_perp.trader import create_agape_doge_perp_trader
from trading.agape_shib_perp.trader import create_agape_shib_perp_trader

CENTRAL_TZ = ZoneInfo("America/Chicago")
logger = logging.getLogger("alphagex.scheduler")

PERP_FACTORIES = {
    "AGAPE-BTC-PERP": create_agape_btc_perp_trader,
    "AGAPE-ETH-PERP": create_agape_eth_perp_trader,
    "AGAPE-SOL-PERP": create_agape_sol_perp_trader,
    "AGAPE-AVAX-PERP": create_agape_avax_perp_trader,
    "AGAPE-XRP-PERP": create_agape_xrp_perp_trader,
    "AGAPE-DOGE-PERP": create_agape_doge_perp_trader,
    "AGAPE-SHIB-PERP": create_agape_shib_perp_trader,
}


class AutonomousTraderScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone=CENTRAL_TZ)
        self.is_running = False
        self.last_error = None
        self.last_valor_check = None
        self.valor_execution_count = 0

        self.valor_trader = None
        self.perp_traders = {}

        self._initialize_traders()

    def _initialize_traders(self):
        try:
            config = ValorConfig(mode=ValorTradingMode.PAPER)
            self.valor_trader = ValorTrader(config=config)
            logger.info("VALOR initialized")
        except Exception as exc:
            logger.exception("VALOR initialization failed: %s", exc)

        for name, factory in PERP_FACTORIES.items():
            try:
                self.perp_traders[name] = factory()
                logger.info("%s initialized", name)
            except Exception as exc:
                logger.exception("%s initialization failed: %s", name, exc)

    def scheduled_valor_logic(self):
        self.last_valor_check = datetime.now(CENTRAL_TZ)
        self.valor_execution_count += 1

        if self.valor_trader is None:
            try:
                config = ValorConfig(mode=ValorTradingMode.PAPER)
                self.valor_trader = ValorTrader(config=config)
            except Exception as exc:
                self.last_error = f"VALOR init: {exc}"
                return

        try:
            result = self.valor_trader.run_scan()
            if result.get("trades_executed", 0):
                logger.info("VALOR executed %s trade(s)", result["trades_executed"])
            if result.get("errors"):
                logger.warning("VALOR scan errors: %s", result["errors"])
        except Exception as exc:
            self.last_error = f"VALOR scan: {exc}"
            logger.error("VALOR scan failed: %s", exc)
            logger.debug(traceback.format_exc())

    def scheduled_valor_position_monitor(self):
        if self.valor_trader is None:
            return
        try:
            result = self.valor_trader.monitor_positions()
            closed = result.get("positions_closed", 0)
            if closed:
                logger.info("VALOR monitor closed %s position(s)", closed)
        except Exception as exc:
            self.last_error = f"VALOR monitor: {exc}"
            logger.warning("VALOR position monitor failed: %s", exc)

    def scheduled_valor_eod_logic(self):
        if self.valor_trader is None:
            return
        try:
            result = self.valor_trader.process_expired_positions()
            if result.get("processed_count", 0):
                logger.info(
                    "VALOR maintenance processed %s position(s), P&L=%s",
                    result["processed_count"],
                    result.get("total_pnl"),
                )
        except Exception as exc:
            self.last_error = f"VALOR maintenance: {exc}"
            logger.exception("VALOR maintenance failed")

    def _run_perp(self, name, close_only=False):
        trader = self.perp_traders.get(name)
        if trader is None:
            factory = PERP_FACTORIES[name]
            try:
                trader = factory()
                self.perp_traders[name] = trader
            except Exception as exc:
                self.last_error = f"{name} init: {exc}"
                logger.exception("%s reinitialization failed", name)
                return

        try:
            result = trader.run_cycle(close_only=close_only)
            if result.get("new_trade"):
                logger.info("%s opened a new trade", name)
            if result.get("positions_closed", 0):
                logger.info("%s closed %s position(s)", name, result["positions_closed"])
        except Exception as exc:
            self.last_error = f"{name}: {exc}"
            logger.error("%s cycle failed: %s", name, exc)
            logger.debug(traceback.format_exc())

    def _schedule_perp_jobs(self):
        for name in PERP_FACTORIES:
            slug = name.lower().replace("-", "_")
            self.scheduler.add_job(
                self._run_perp,
                trigger=IntervalTrigger(minutes=5, timezone=CENTRAL_TZ),
                kwargs={"name": name, "close_only": False},
                id=f"{slug}_cycle",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

            # Preserve the existing daily accounting/close-only safety cycle.
            self.scheduler.add_job(
                self._run_perp,
                trigger=CronTrigger(hour=15, minute=45, timezone=CENTRAL_TZ),
                kwargs={"name": name, "close_only": True},
                id=f"{slug}_daily_close_only",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

    def start(self):
        if self.is_running:
            return

        self.scheduler.add_job(
            self.scheduled_valor_logic,
            trigger=IntervalTrigger(minutes=1, timezone=CENTRAL_TZ),
            id="valor_scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self.scheduled_valor_position_monitor,
            trigger=IntervalTrigger(seconds=15, timezone=CENTRAL_TZ),
            id="valor_position_monitor",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self.scheduler.add_job(
            self.scheduled_valor_eod_logic,
            trigger=CronTrigger(hour=16, minute=0, day_of_week="mon-fri", timezone=CENTRAL_TZ),
            id="valor_daily_maintenance",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        self._schedule_perp_jobs()
        self.scheduler.start()
        self.is_running = True

        logger.info(
            "AlphaGEX scheduler started: VALOR + %s perpetual bots",
            len(PERP_FACTORIES),
        )

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        self.is_running = False

    def is_scheduler_healthy(self):
        return bool(self.is_running and self.scheduler.running)

    def get_status(self):
        return {
            "is_running": self.is_running,
            "scheduler_healthy": self.is_scheduler_healthy(),
            "scope": ["VALOR", "crypto_perpetuals"],
            "valor": {
                "initialized": self.valor_trader is not None,
                "last_check": self.last_valor_check.isoformat() if self.last_valor_check else None,
                "execution_count": self.valor_execution_count,
            },
            "perpetuals": {
                name: {"initialized": self.perp_traders.get(name) is not None}
                for name in PERP_FACTORIES
            },
            "jobs": [
                {
                    "id": job.id,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                }
                for job in self.scheduler.get_jobs()
            ] if self.scheduler.running else [],
            "last_error": self.last_error,
        }


_scheduler_instance = None


def get_scheduler():
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = AutonomousTraderScheduler()
    return _scheduler_instance


def run_standalone():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    scheduler = get_scheduler()
    shutdown = False

    def handle_signal(signum, _frame):
        nonlocal shutdown
        logger.info("Received signal %s; shutting down", signum)
        shutdown = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    scheduler.start()

    try:
        while not shutdown:
            time.sleep(30)
            if not scheduler.is_scheduler_healthy():
                raise RuntimeError("scheduler health check failed")
    finally:
        scheduler.stop()


if __name__ == "__main__":
    run_standalone()
