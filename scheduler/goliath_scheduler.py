"""GOLIATH job scheduler hook.

Per Q4 + paper-trading direction (2026-05-01): GOLIATH co-hosts on
alphagex-trader. This module is the integration point -- scheduler/
trader_scheduler.py calls add_goliath_jobs(scheduler) once during
service startup, and these two jobs handle all GOLIATH operation:

  Entry cycle      Monday 10:30 AM ET (per spec section 1.7)
  Management cycle Every 15 min during market hours, Mon-Fri

Both jobs invoke the Phase 6 Runner with the Phase-α Tradier
snapshot fetcher and paper broker executor wired in. Discord alerts
fire from monitoring; equity snapshots and audit log persist
automatically.

Module-level state: keeps a single Runner instance across cycles so
in-memory open_positions persist between management ticks (until the
process restarts; v0.3 V03-RECOVER will reload from
goliath_paper_positions on startup).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level Runner; created on first add_goliath_jobs() call.
_runner = None


def _get_runner():
    """Lazily build the Runner with paper-trading defaults wired."""
    global _runner
    if _runner is not None:
        return _runner

    try:
        from trading.goliath.broker.paper_executor import paper_broker_executor
        from trading.goliath.data.tradier_snapshot import build_market_snapshot
        from trading.goliath.engine import GoliathEngine, PlatformContext
        from trading.goliath.main import Runner
    except ImportError as exc:
        logger.error("[goliath_scheduler] import failed: %r", exc)
        return None

    def _platform_fetcher(instances) -> "PlatformContext":
        # Sum open positions + dollars-at-risk across all instances.
        from trading.goliath.engine import PlatformContext as PC
        total_count = sum(inst.open_count for inst in instances.values())
        total_dollars = sum(inst.open_dollars_at_risk() for inst in instances.values())
        return PC(open_position_count=total_count, open_dollars_at_risk=total_dollars)

    _runner = Runner(
        engine=GoliathEngine(),
        snapshot_fetcher=build_market_snapshot,
        platform_fetcher=_platform_fetcher,
        broker_executor=paper_broker_executor,
        dry_run=False,
    )
    logger.info("[goliath_scheduler] Runner initialized (paper-trading mode)")
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


def goliath_entry_job() -> None:
    """Monday 10:30 AM ET entry cycle. Per spec section 1.7."""
    try:
        runner = _get_runner()
        if runner is None:
            logger.warning("[goliath_scheduler] entry job skipped -- Runner unavailable")
            return
        result = runner.run_entry_cycle()
        logger.info(
            "[goliath_scheduler] entry cycle: evaluated=%d approved=%d filled=%d skips=%d",
            result.instances_evaluated, result.entries_approved,
            result.entries_filled, len(result.skips),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[goliath_scheduler] entry job failed: %r", exc)


def goliath_management_job() -> None:
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
                "[goliath_scheduler] management cycle: evaluated=%d triggers=%d",
                result.instances_evaluated, result.triggers_fired,
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[goliath_scheduler] management job failed: %r", exc)


def add_goliath_jobs(scheduler) -> bool:
    """Register GOLIATH entry + management jobs with an APScheduler instance.

    Args:
        scheduler: an apscheduler.schedulers.background.BackgroundScheduler
                   or similar already-started scheduler.

    Returns True on success, False on import failure / scheduling error.
    """
    try:
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError as exc:
        logger.error("[goliath_scheduler] APScheduler unavailable: %r", exc)
        return False

    # Pre-warm Runner so init failures surface during scheduler startup.
    if _get_runner() is None:
        logger.error("[goliath_scheduler] Runner init failed; jobs not registered")
        return False

    try:
        # Entry: Monday 10:30 AM ET.
        scheduler.add_job(
            goliath_entry_job,
            trigger=CronTrigger(
                day_of_week="mon",
                hour=10,
                minute=30,
                timezone="America/New_York",
            ),
            id="goliath_entry",
            name="GOLIATH - Monday 10:30 ET entry cycle",
            replace_existing=True,
        )
        # Management: every 15 min during market hours, Mon-Fri.
        scheduler.add_job(
            goliath_management_job,
            trigger=IntervalTrigger(minutes=15),
            id="goliath_management",
            name="GOLIATH - 15-min management cycle (market hours only)",
            replace_existing=True,
        )
        logger.info("✅ GOLIATH jobs scheduled (entry: Mon 10:30 ET, management: 15-min)")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.exception("[goliath_scheduler] add_job failed: %r", exc)
        return False
