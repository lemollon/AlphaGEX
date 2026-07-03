"""TSUNAMI job scheduler hook.

TSUNAMI co-hosts on spreadworks-backend (moved from AlphaGEX's
alphagex-trader on 2026-07-03). This module is the integration point --
backend/__init__.py calls add_tsunami_jobs(scheduler) once during
service startup, and these two jobs handle all TSUNAMI operation:

  Entry cycle      Mon-Fri 10:30 AM CT (per 2026-05-07 schedule change;
                   was Monday 10:30 ET per original spec section 1.7)
  Management cycle Every 15 min during market hours, Mon-Fri

Both jobs invoke the Phase 6 Runner with the Phase-α Tradier
snapshot fetcher and paper broker executor wired in. Discord alerts
fire from monitoring; equity snapshots and audit log persist
automatically.

Module-level state: keeps a single Runner instance across cycles so
in-memory open_positions persist between management ticks (until the
process restarts; v0.3 V03-RECOVER will reload from
tsunami_paper_positions on startup).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level Runner; created on first add_tsunami_jobs() call.
_runner = None


def _get_runner():
    """Lazily build the Runner with paper-trading defaults wired."""
    global _runner
    if _runner is not None:
        return _runner

    try:
        from backend.bots.tsunami.broker.paper_executor import paper_broker_executor
        from backend.bots.tsunami.data.tradier_snapshot import build_market_snapshot
        from backend.bots.tsunami.engine import TsunamiEngine, PlatformContext
        from backend.bots.tsunami.main import Runner
    except ImportError as exc:
        logger.error("[tsunami_scheduler] import failed: %r", exc)
        return None

    def _platform_fetcher(instances) -> "PlatformContext":
        # Sum open positions + dollars-at-risk across all instances.
        from backend.bots.tsunami.engine import PlatformContext as PC
        total_count = sum(inst.open_count for inst in instances.values())
        total_dollars = sum(inst.open_dollars_at_risk() for inst in instances.values())
        return PC(open_position_count=total_count, open_dollars_at_risk=total_dollars)

    _runner = Runner(
        engine=TsunamiEngine(),
        snapshot_fetcher=build_market_snapshot,
        platform_fetcher=_platform_fetcher,
        broker_executor=paper_broker_executor,
        dry_run=False,
    )
    logger.info("[tsunami_scheduler] Runner initialized (paper-trading mode)")
    return _runner


def _is_market_hours_et() -> bool:
    """Return True when US equity market is open (Mon-Fri, 9:30 AM - 4:00 PM ET).

    APScheduler's CronTrigger handles day-of-week + time bounds, but we add
    an extra check inside the management job in case the scheduler fires
    just outside the window (DST transitions, etc).
    """
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        return True  # fail-open; CronTrigger constraints still bound it

    if now.weekday() > 4:  # Sat=5, Sun=6
        return False
    minutes = now.hour * 60 + now.minute
    return 570 <= minutes <= 960  # 9:30 AM (570) to 4:00 PM (960)


def tsunami_entry_job() -> None:
    """Mon-Fri 10:30 AM CT entry cycle (2026-05-07 schedule change)."""
    try:
        runner = _get_runner()
        if runner is None:
            logger.warning("[tsunami_scheduler] entry job skipped -- Runner unavailable")
            return
        result = runner.run_entry_cycle()
        logger.info(
            "[tsunami_scheduler] entry cycle: evaluated=%d approved=%d filled=%d skips=%d",
            result.instances_evaluated, result.entries_approved,
            result.entries_filled, len(result.skips),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami_scheduler] entry job failed: %r", exc)


def tsunami_management_job() -> None:
    """Every-15-min management cycle during market hours."""
    if not _is_market_hours_et():
        return
    try:
        runner = _get_runner()
        if runner is None:
            return
        result = runner.run_management_cycle()
        if result.triggers_fired:
            logger.info(
                "[tsunami_scheduler] management cycle: evaluated=%d triggers=%d",
                result.instances_evaluated, result.triggers_fired,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami_scheduler] management job failed: %r", exc)


def add_tsunami_jobs(scheduler) -> bool:
    """Register TSUNAMI entry + management jobs with an APScheduler instance.

    Args:
        scheduler: an apscheduler.schedulers.background.BackgroundScheduler
                   or similar already-started scheduler.

    Returns True on success, False on import failure / scheduling error.
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError as exc:
        logger.error("[tsunami_scheduler] APScheduler unavailable: %r", exc)
        return False

    # Ensure the six tsunami_* tables exist (SpreadWorks has no migration
    # framework; ensure-at-startup is the platform convention). Best-effort:
    # stores are individually resilient to a missing DB.
    try:
        from backend.bots.tsunami.init_db import ensure_tables
        ensure_tables()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[tsunami_scheduler] ensure_tables failed: %r", exc)

    # TSUNAMI-TREND (2026-07-03): the options engine is retired — backtests
    # proved the 3-leg structure can never fill on these LETFs (zero-bid
    # wall-mapped puts; tracking band narrower than the strike grid). The
    # bot now runs the backtest-validated LETF trend engine: one daily
    # rebalance near the close. Options Runner/gates/triggers stay importable
    # for the audit trail and tests but get no jobs.
    try:
        from backend.bots.tsunami.trend_engine import ensure_trend_tables, run_rebalance
        ensure_trend_tables()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami_scheduler] trend engine unavailable: %r", exc)
        return False

    def tsunami_trend_job() -> None:
        try:
            s = run_rebalance()
            logger.info("[tsunami_scheduler] trend rebalance: equity=%s fills=%s skipped=%s",
                        s.get("equity"), s.get("fills"), s.get("skipped"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[tsunami_scheduler] trend job failed: %r", exc)

    try:
        scheduler.add_job(
            tsunami_trend_job,
            trigger=CronTrigger(
                day_of_week="mon-fri",
                hour=14,
                minute=45,
                timezone="America/Chicago",
            ),
            id="tsunami_trend",
            name="TSUNAMI-TREND - daily 14:45 CT LETF rebalance",
            replace_existing=True,
        )
        logger.info("✅ TSUNAMI-TREND job scheduled (daily rebalance Mon-Fri 14:45 CT)")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("[tsunami_scheduler] add_job failed: %r", exc)
        return False
