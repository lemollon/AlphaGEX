"""Risk Advisor Discord alerts — the playbook's alert plan, wired.

Five alerts, exactly as documented on the /risk page:

  1. MORNING VERDICT (08:05 CT, weekdays)
     RISK-OFF (backwardation or VIX1D flag from last close) -> @here push with
     the playbook actions. CALM FLOOR (double_floor) -> quiet note, no ping.
     NORMAL -> nothing at all: silence means normal.
  2. FLOW SPIKE (10:06 CT, weekdays)
     Captures/loads the 10:00 CT snapshot; put/total z > 2 -> @here push.
     The window enforcement in routes_risk guarantees the z is the validated
     10:00 figure, never a late-capture artifact.
  3/4. AFTERNOON RE-CHECKS (12:06 & 13:36 CT, weekdays)
     Same test re-run at 12:00 and 13:30 CT vs each clock's own trailing-63
     same-clock baseline. A fresh spike -> @here push, saying whether it's a
     new afternoon spike or the morning spike continuing. If the morning
     alert already fired and the clock's z has faded below 1 -> a quiet
     all-clear note, no ping — the anti-stale-signal update.
  5. Nothing else. Alert scarcity is the point — the channel must stay
     readable or the pushes train you to ignore them.

Safety rails:
  * webhook from env RISK_ADVISOR_DISCORD_WEBHOOK (falls back to
    DISCORD_WEBHOOK_URL). NEVER hardcoded.
  * every send is deduped through discord_post_log (INSERT..ON CONFLICT), so
    replicas/redeploys cannot double-ping.
  * jobs never raise — a data hiccup logs and skips.
  * ADVISORY ONLY: nothing here touches a bot.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
CT = ZoneInfo("America/Chicago")
SQRT252 = 15.874507866387544

RED = 0xF87171
GREEN = 0x34D399
AMBER = 0xFBBF24


def _webhook_url() -> str:
    return (os.getenv("RISK_ADVISOR_DISCORD_WEBHOOK", "")
            or os.getenv("DISCORD_WEBHOOK_URL", ""))


def _send(embed: dict, ping: bool = False) -> bool:
    import requests as req
    url = _webhook_url()
    if not url:
        logger.warning("[RiskAlerts] no webhook configured — skipping")
        return False
    payload: dict = {"embeds": [embed]}
    if ping:
        payload["content"] = "@here"
    try:
        r = req.post(url, json=payload, timeout=15)
        return r.status_code in (200, 204)
    except Exception as e:  # noqa: BLE001
        logger.warning("[RiskAlerts] send failed: %r", e)
        return False


def _already_posted(key: str, fire_date) -> bool:
    """Read-only check: has `key` already claimed a slot for `fire_date`?

    Unlike _claim_post_slot_db this never inserts — used to look up whether
    an EARLIER alert already fired today (e.g. did the morning verdict push
    before this afternoon re-check runs) without stealing that slot."""
    try:
        from .db import SessionLocal
        from .models import DiscordPostLog
    except Exception:
        return False
    if SessionLocal is None:
        return False
    db = SessionLocal()
    try:
        return db.get(DiscordPostLog, (key, fire_date)) is not None
    except Exception:
        return False
    finally:
        db.close()


def register_risk_alerts(scheduler, app) -> None:
    """Attach the two alert jobs to the existing APScheduler instance."""
    if scheduler is None:
        logger.warning("[RiskAlerts] no scheduler — alerts disabled")
        return
    from . import _claim_post_slot_db          # existing dedupe

    async def morning_verdict():
        try:
            if datetime.now(CT).weekday() >= 5:
                return
            from .routes_risk import _cboe, _latest
            client = app.state.http
            vix = await _cboe(client, "VIX")
            v3 = await _cboe(client, "VIX3M")
            v1 = await _cboe(client, "VIX1D")
            vvix = await _cboe(client, "VVIX")
            d, vix_c = _latest(vix)
            v3_c, v1_c, vv_c = v3.get(d), v1.get(d), vvix.get(d)

            backw = bool(v3_c and vix_c > v3_c)
            flag = bool(v1_c and v1_c / SQRT252 > 1.0)
            floor = bool(vv_c and vv_c < 85 and vix_c < 14)
            today = datetime.now(CT).date()

            if backw or flag:
                if not _claim_post_slot_db("risk_morning_riskoff", today):
                    return
                actions = []
                if backw:
                    actions.append("• **Backwardation (VIX > VIX3M)** — skip new "
                                   "premium-selling entries today (+0.09 ret/DD, 7y backtest)")
                if flag:
                    actions.append(f"• **VIX1D flag** — implied 1-day move "
                                   f"{v1_c / SQRT252:.2f}% > 1%: reduce size or skip "
                                   f"(42.8% of flagged days move ≥1%)")
                _send({
                    "title": "🛑 RISK-OFF — morning verdict",
                    "description": "\n".join(actions),
                    "color": RED,
                    "fields": [
                        {"name": "VIX", "value": f"{vix_c:.1f}", "inline": True},
                        {"name": "VIX3M", "value": f"{v3_c:.1f}" if v3_c else "—", "inline": True},
                        {"name": "VIX1D", "value": f"{v1_c:.1f}" if v1_c else "—", "inline": True},
                    ],
                    "footer": {"text": f"closes of {d} · advisory only · /risk for detail"},
                }, ping=True)
            elif floor:
                if not _claim_post_slot_db("risk_morning_calm", today):
                    return
                _send({
                    "title": "🟢 Calm floor",
                    "description": "VVIX < 85 and VIX < 14 — statistically the safest "
                                   "measured state to sell premium at normal size "
                                   "(0 next-day moves ≥1.5% across 56 such sessions).",
                    "color": GREEN,
                    "footer": {"text": f"closes of {d} · quiet note, not an alarm"},
                }, ping=False)
            # NORMAL -> deliberate silence
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] morning_verdict failed: %r", e)

    async def flow_spike_check():
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .routes_risk import (_capture_snapshot, _flow_history, _z)
            shim = SimpleNamespace(app=app)     # capture helpers expect request.app
            snap = await _capture_snapshot(shim)
            if snap is None:
                logger.info("[RiskAlerts] no valid 10:00 snapshot — no spike check")
                return
            hist = _flow_history()
            prior = [r for r in hist if r["d"] < now.date()]
            pz = _z(snap["putv"], [r["putv"] for r in prior])
            tz = _z(snap["totv"], [r["totv"] for r in prior])
            oz = _z(snap["otm_call_0dte"], [r["otm_call_0dte"] for r in prior])
            if (pz or 0) > 2 or (tz or 0) > 2:
                if not _claim_post_slot_db("risk_flow_spike", now.date()):
                    return
                # which side is driving it — plain-speech composition line
                if (pz or 0) > 2 and (oz or 0) <= 1:
                    driver = ("Driven by **PUT volume** — someone is paying up "
                              "for downside protection.")
                elif (oz or 0) > 1 and (pz or 0) <= 1:
                    driver = ("Driven by **CALL volume** on the upside — the "
                              "squeeze-tell shape we track in the watch tier "
                              "(accumulating evidence, NOT yet a tradeable "
                              "signal).")
                else:
                    driver = "Both sides are heavy — broad bracing, no lean."
                _send({
                    "title": "⚠️ Unusual option volume this morning — bigger "
                             "rest-of-day move than normal is ~2.4× more likely",
                    "description": (
                        f"In plain English: this morning's SPY option volume is a "
                        f"top-2% outlier vs the last 3 months at the same clock "
                        f"(put z {(pz or 0):.1f} · total z {(tz or 0):.1f} · "
                        f"0DTE call z {(oz or 0):.1f}).\n"
                        f"{driver}\n\n"
                        "**DO:** no new same-day (0DTE) premium selling today; "
                        "tighten exits on anything expiring today. Multi-day "
                        "positions: ignore this — gating them on it was tested "
                        "and made them worse.\n"
                        "**DON'T:** don't switch to buying options for the move "
                        "— backtested, it loses MORE on flagged days than "
                        "normal ones (−$19.63/trade, negative 4/4 years). And "
                        "there is NO direction call: up and down are ~equally "
                        "likely on these days (every direction test t < 1). "
                        "Flat beats clever.\n"
                        "**EBB note:** its validated spec already includes days "
                        "like this (skipping them was tested ≈ neutral) — the "
                        "bot needs no manual action."),
                    "color": AMBER,
                    "fields": [
                        {"name": "big-move odds", "value": "28.6% vs 12.1% base",
                         "inline": True},
                        {"name": "confidence", "value": "~4.8σ, 904 sessions",
                         "inline": True},
                        {"name": "fires on", "value": "~6% of days", "inline": True},
                    ],
                    "footer": {"text": "validated 10:00–10:35 CT snapshot · "
                                       "advisory only · /risk for the playbook"},
                }, ping=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] flow_spike_check failed: %r", e)

    # 12:00 -> 29.3% vs 17.0% base odds of |move to close| >= 0.5%
    # 13:30 -> 17.0% vs 8.4% base odds
    PM_BASE_RATES = {"12:00": (0.293, 0.170), "13:30": (0.170, 0.084)}

    async def pm_recheck(clock: str, spike_slot: str, fade_slot: str):
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .routes_risk import _capture_pm_snapshot, _pm_flow_history, _z
            shim = SimpleNamespace(app=app)     # capture helpers expect request.app
            snap = await _capture_pm_snapshot(shim, clock)
            if snap is None:
                logger.info("[RiskAlerts] no valid %s snapshot — no re-check", clock)
                return
            today = now.date()
            hist = _pm_flow_history(clock)
            prior = [r for r in hist if r["d"] < today]
            pz = _z(snap["putv"], [r["putv"] for r in prior])
            tz = _z(snap["totv"], [r["totv"] for r in prior])
            hi, lo = PM_BASE_RATES[clock]

            if (pz or 0) > 2 or (tz or 0) > 2:
                if not _claim_post_slot_db(spike_slot, today):
                    return
                # continuation vs fresh: did an earlier clock today already
                # alert on a spike? (morning 10:06 push, or the 12:00
                # re-check for the 13:30 job)
                continuation = _already_posted("risk_flow_spike", today) or (
                    clock == "13:30" and _already_posted("risk_pm_1200", today))
                lead = ("This looks like the morning spike **continuing** into "
                        "the afternoon." if continuation else
                        "This is a **fresh** afternoon spike — no earlier alert "
                        "fired today.")
                _send({
                    "title": f"⚠️ Afternoon re-check — unusual option volume "
                             f"at {clock} CT",
                    "description": (
                        f"{lead}\n\n"
                        f"In plain English: SPY option volume through {clock} "
                        f"CT is a top-2% outlier vs the last 3 months at this "
                        f"same clock (put z {(pz or 0):.1f} · total z "
                        f"{(tz or 0):.1f}) — historically {hi:.1%} vs {lo:.1%} "
                        "base odds of a move of at least 0.5% by the close.\n\n"
                        "**DO:** no new same-day (0DTE) premium selling for the "
                        "rest of today; tighten exits on anything expiring "
                        "today. Multi-day positions: ignore this — gating them "
                        "on it was tested and made them worse.\n"
                        "**DON'T:** don't switch to buying options for the "
                        "move — backtested, it loses MORE. And there is NO "
                        "direction call: every direction test comes back "
                        "t < 1. Flat beats clever."),
                    "color": AMBER,
                    "fields": [
                        {"name": "move odds", "value": f"{hi:.1%} vs {lo:.1%} base",
                         "inline": True},
                        {"name": "re-check clock", "value": f"{clock} CT",
                         "inline": True},
                    ],
                    "footer": {"text": f"validated {clock} CT re-check "
                                       "snapshot · advisory only · /risk for "
                                       "the playbook"},
                }, ping=True)
            elif _already_posted("risk_flow_spike", today) and \
                    (pz or 0) < 1 and (tz or 0) < 1:
                if not _claim_post_slot_db(fade_slot, today):
                    return
                z_now = max(pz or 0, tz or 0)
                _send({
                    "title": f"🟢 All-clear update — {clock} CT",
                    "description": (
                        f"All-clear update: the morning volume spike did not "
                        f"persist — {clock} CT z is back to {z_now:.1f}. "
                        "Signal considered faded; normal caution applies."),
                    "color": GREEN,
                    "footer": {"text": f"{clock} CT re-check · advisory only "
                                       "· /risk for the playbook"},
                }, ping=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] pm_recheck(%s) failed: %r", clock, e)

    scheduler.add_job(morning_verdict, "cron", hour=8, minute=5, second=30,
                      timezone=CT, id="risk_morning_verdict")
    scheduler.add_job(flow_spike_check, "cron", hour=10, minute=6,
                      timezone=CT, id="risk_flow_spike")
    scheduler.add_job(pm_recheck, "cron", hour=12, minute=6, timezone=CT,
                      id="pm_recheck_1200",
                      args=["12:00", "risk_pm_1200", "risk_pm_fade_1200"])
    scheduler.add_job(pm_recheck, "cron", hour=13, minute=36, timezone=CT,
                      id="pm_recheck_1330",
                      args=["13:30", "risk_pm_1330", "risk_pm_fade_1330"])
    logger.info("[RiskAlerts] registered: morning verdict 08:05:30 CT, "
                "flow spike 10:06 CT, PM re-checks 12:06 & 13:36 CT")
