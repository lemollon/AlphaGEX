"""Risk Advisor Discord alerts — the playbook's alert plan, wired.

Three alerts, exactly as documented on the /risk page:

  1. MORNING VERDICT (08:05 CT, weekdays)
     RISK-OFF (backwardation or VIX1D flag from last close) -> @here push with
     the playbook actions. CALM FLOOR (double_floor) -> quiet note, no ping.
     NORMAL -> nothing at all: silence means normal.
  2. FLOW SPIKE (10:06 CT, weekdays)
     Captures/loads the 10:00 CT snapshot; put/total z > 2 -> @here push.
     The window enforcement in routes_risk guarantees the z is the validated
     10:00 figure, never a late-capture artifact.
  3. Nothing else. Alert scarcity is the point — the channel must stay
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
            if (pz or 0) > 2 or (tz or 0) > 2:
                if not _claim_post_slot_db("risk_flow_spike", now.date()):
                    return
                _send({
                    "title": "⚠️ 10:00 CT option-flow spike",
                    "description": (
                        f"put-vol z **{(pz or 0):.1f}** · total z **{(tz or 0):.1f}** "
                        f"(threshold 2.0)\n"
                        "Big rest-of-day move odds jump to **28.6% vs 12.1%** base "
                        "(~4.8σ backtest).\n"
                        "**Action: avoid new 0DTE exposure; tighten same-day exits.** "
                        "Multi-day positions: this signal does not apply."),
                    "color": AMBER,
                    "footer": {"text": "validated 10:00–10:35 CT snapshot · advisory only"},
                }, ping=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] flow_spike_check failed: %r", e)

    scheduler.add_job(morning_verdict, "cron", hour=8, minute=5, second=30,
                      timezone=CT, id="risk_morning_verdict")
    scheduler.add_job(flow_spike_check, "cron", hour=10, minute=6,
                      timezone=CT, id="risk_flow_spike")
    logger.info("[RiskAlerts] registered: morning verdict 08:05:30 CT, "
                "flow spike 10:06 CT")
