"""Gamma-regime plumbing — daily capture + morning squeeze alert.

The signal logic lives entirely in backend/bots/gamma_regime.py (untouched
here). This module is the wiring: pull the chain once a day, store it, and
tell someone what it means before the open.

  1. CAPTURE (15:05 CT weekdays) — pulls SPY's full option chain via
     gamma_regime.fetch_net_gex and stores it under TODAY's date. Storing
     under today is the whole point of the lag: tomorrow's gamma_state()
     reads this row as "the prior session's close", never as same-day data.
  2. MORNING ALERT (08:05 CT weekdays) — reads squeeze_signal() off the
     reading last night's capture wrote and posts a Discord embed to the
     risk channel. Silent on NEUTRAL (the common case); loud on UNKNOWN — a
     missing signal must not read as "nothing to worry about".

Safety rails, matching risk_alerts.py:
  * webhook from env RISK_ADVISOR_DISCORD_WEBHOOK (falls back to
    DISCORD_WEBHOOK_URL). NEVER hardcoded.
  * both jobs deduped via backend._dedup_ok, so replicas/redeploys cannot
    double-capture or double-post.
  * jobs never raise — a data hiccup logs and skips.
  * ADVISORY ONLY: nothing here touches a bot. Not wired into scanner.py or
    any bot gate — it writes its table, serves its endpoint, renders its
    page, and posts to Discord. Nothing else.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")

RED = 0xF87171
GREEN = 0x34D399
AMBER = 0xFBBF24
GREY = 0x9CA3AF

COLORS = {
    "SQUEEZE_WATCH": AMBER,
    "NO_SELL": RED,
    "SELL_PREMIUM": GREEN,
    "UNKNOWN": GREY,
}
WHAT_TO_DO = {
    "SQUEEZE_WATCH": "stand down from selling; long-convexity setup "
                     "(0.25Δ call, 5–9 DTE)",
    "NO_SELL": "skip the put spread today",
    "SELL_PREMIUM": "gamma overbought — historically the safest state "
                    "to sell into",
    "UNKNOWN": "signal unavailable — treat as BLOCK, do not trade the rule",
}


def _webhook_url() -> str:
    return (os.getenv("RISK_ADVISOR_DISCORD_WEBHOOK", "")
            or os.getenv("DISCORD_WEBHOOK_URL", ""))


GAMMA_BASELINE_CSV = Path(__file__).resolve().parent / "data" / "gamma_baseline.csv"


def _auto_seed_from_csv(engine) -> None:
    """Bulk-load the committed CSV baseline into sw_gamma_daily on startup.

    The research warehouse `seed_gamma_history.py` can read locally does not
    exist on Render, so without this a fresh deploy sits at 0 rows and the
    60-session percentile (gamma_percentile / squeeze_signal) returns
    UNKNOWN for three months while the daily capture job accumulates history
    one session at a time. ON CONFLICT DO NOTHING: never overwrites a row
    the capture job already wrote, and a no-op once the table has data.

    NO EMPTINESS GUARD, DELIBERATELY. An earlier version ran this only when
    the table was empty, which is redundant — the ON CONFLICT clause already
    makes it idempotent — and actively harmful: proved against Postgres 16.2,
    a SINGLE stray row made the table non-empty and skipped the whole 1,660-row
    backfill, leaving the percentile permanently short of its 60-session
    minimum and the page reading UNKNOWN with nothing logged as wrong. Running
    unconditionally costs ~1,660 no-op inserts once per boot and self-heals a
    partial or botched seed.
    """
    from sqlalchemy import text as sa_text
    from .bots.gamma_regime import ensure_gamma_table, GAMMA_DAILY_TABLE

    ensure_gamma_table(engine)
    if not GAMMA_BASELINE_CSV.exists():
        logger.warning("[GammaAlerts] gamma_baseline.csv not found at %s — "
                       "cannot auto-seed, squeeze signal will read UNKNOWN "
                       "until the capture job accumulates 60 sessions",
                       GAMMA_BASELINE_CSV)
        return

    rows = []
    with open(GAMMA_BASELINE_CSV, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"d": date.fromisoformat(r["d"]), "g": float(r["net_gex"]),
                        "s": float(r["spot"]) if r.get("spot") not in (None, "") else None})
    if not rows:
        return

    with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            sql = sa_text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, n_contracts, updated_at) "
                "VALUES (:d, :g, :s, NULL, CURRENT_TIMESTAMP) "
                "ON CONFLICT(trade_date) DO NOTHING"
            )
        else:
            sql = sa_text(
                f"INSERT INTO {GAMMA_DAILY_TABLE} "
                "(trade_date, net_gex, spot, n_contracts, updated_at) "
                "VALUES (:d, :g, :s, NULL, NOW()) "
                "ON CONFLICT (trade_date) DO NOTHING"
            )
        for r in rows:
            conn.execute(sql, r)
    logger.info("[GammaAlerts] auto-seeded sw_gamma_daily from CSV baseline: "
               "%d row(s), %s..%s", len(rows), rows[0]["d"], rows[-1]["d"])


def register_gamma_alerts(scheduler, app) -> None:
    """Auto-seed sw_gamma_daily from the CSV baseline, then attach the
    capture + morning-alert jobs to the existing APScheduler."""
    from .db import engine
    from . import _dedup_ok, _send_webhook_sync

    try:
        _auto_seed_from_csv(engine)
    except Exception as e:  # noqa: BLE001
        logger.warning("[GammaAlerts] CSV auto-seed failed: %r", e)

    if scheduler is None:
        logger.warning("[GammaAlerts] no scheduler — gamma jobs disabled")
        return

    async def capture_gamma():
        """15:05 CT weekdays: pull SPY's chain, reduce to net_gex, store it
        under TODAY's date — the reading tomorrow's gamma_state() will read
        as the prior session's close."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            if not _dedup_ok("gamma_capture", fire_date=now.date()):
                return
            from .bots.gamma_regime import (ensure_gamma_table, fetch_net_gex,
                                            record_gamma)
            from .bots.routes_helpers import build_live_chain_provider

            def _run() -> dict:
                ensure_gamma_table(engine)
                client = build_live_chain_provider()
                out = fetch_net_gex(client, "SPY", today=now.date())
                if out.get("net_gex") is not None:
                    record_gamma(engine, now.date(), out["net_gex"],
                                 out.get("spot"), out.get("n_contracts"))
                return out

            out = await asyncio.to_thread(_run)
            if out.get("net_gex") is None:
                logger.warning("[GammaAlerts] capture_gamma: no reading for "
                               "%s (%s)", now.date(), out.get("reason"))
            else:
                logger.info("[GammaAlerts] captured %s: net_gex=$%.2fB "
                           "spot=%s n_contracts=%s", now.date(),
                           out["net_gex"] / 1e9, out.get("spot"),
                           out.get("n_contracts"))
        except Exception as e:  # noqa: BLE001
            logger.warning("[GammaAlerts] capture_gamma failed: %r", e)

    async def fire_squeeze_alert():
        """08:05 CT weekdays: post today's squeeze verdict. Silent on
        NEUTRAL; posts (loudly) on SQUEEZE_WATCH / NO_SELL / SELL_PREMIUM /
        UNKNOWN — a missing signal must be loud, not silent."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .bots.gamma_regime import squeeze_signal
            try:
                sig = squeeze_signal(engine, now.date())
            except Exception as e:  # noqa: BLE001
                # A DB hiccup (e.g. sw_vix_daily not created yet on a brand
                # new deploy) is exactly the kind of missing signal that
                # must be loud, not silently swallowed by the outer except.
                logger.warning("[GammaAlerts] squeeze_signal raised: %r", e)
                sig = {"verdict": "UNKNOWN", "gamma_pct": None, "net_gex_b": None,
                      "vix_ratio": None, "prior_date": None,
                      "reason": f"squeeze_signal error: {e}"}
            verdict = sig.get("verdict", "UNKNOWN")
            if verdict == "NEUTRAL":
                return
            if not _dedup_ok("squeeze_signal", fire_date=now.date()):
                return

            pct, b, ratio = (sig.get("gamma_pct"), sig.get("net_gex_b"),
                             sig.get("vix_ratio"))
            prior = sig.get("prior_date")
            description = WHAT_TO_DO.get(verdict, "")
            if sig.get("reason"):
                description += f"\n\n_{sig['reason']}_"

            embed = {
                "title": verdict,
                "description": description,
                "color": COLORS.get(verdict, GREY),
                "fields": [
                    {"name": "Gamma percentile",
                     "value": f"{pct * 100:.1f}%" if pct is not None else "—",
                     "inline": True},
                    {"name": "Net gamma",
                     "value": f"${b:.2f}B" if b is not None else "—",
                     "inline": True},
                    {"name": "VIX ratio",
                     "value": f"{ratio:.2f}" if ratio is not None else "—",
                     "inline": True},
                    {"name": "Prior session",
                     "value": str(prior) if prior else "—",
                     "inline": True},
                ],
                "footer": {"text": "gamma_regime squeeze signal · "
                                   "advisory only — no bot reads this"},
            }
            await asyncio.to_thread(_send_webhook_sync, embed, _webhook_url())
        except Exception as e:  # noqa: BLE001
            logger.warning("[GammaAlerts] fire_squeeze_alert failed: %r", e)

    scheduler.add_job(capture_gamma, "cron", hour=15, minute=5, timezone=CT,
                      id="gamma_capture", coalesce=True, max_instances=1,
                      replace_existing=True)
    scheduler.add_job(fire_squeeze_alert, "cron", hour=8, minute=5, timezone=CT,
                      id="gamma_squeeze_alert", coalesce=True, max_instances=1,
                      replace_existing=True)
    logger.info("[GammaAlerts] registered: capture 15:05 CT, "
               "squeeze alert 08:05 CT")
