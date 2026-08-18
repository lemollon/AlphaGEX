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
  5. ROLLING FLOW WATCHER (every 10 min, 10:36-14:00 CT, weekdays)
     Registry #39 (validated 2026-08-13): put/total z > 2 vs a per-minute
     trailing-63 baseline -> @here push, once per day, the FIRST time it
     crosses. Exists to catch a spike the fixed 10:00/12:00/13:30 clocks
     miss between their checks — it posts NOTHING if one of those clocks
     already alerted a spike today (they own their windows; this is the
     gap-filler, not a fourth copy of the same alert).
  6. THE TICKET (AM and PM entry windows, weekdays)
     The only alert here that hands over an ORDER rather than reporting
     market state: the strike pair and the expiration for today's SPY 0DTE
     put spread, pushed at the moment each validated window opens so it can
     be placed without opening the page to read it off a card. Clocks come
     from the ebb/ebb_pm registry, never a hardcoded copy. If the ticket
     cannot be priced the window still gets a quiet note — silence at an
     open window would read as "no trade today", which is a different and
     wrong message.
  7. Nothing else. Alert scarcity is the point — the channel must stay
     readable or the pushes train you to ignore them. The ticket earns its
     two daily pings by being the one actionable, time-boxed thing here.

     The two ticket pings are a DELIBERATE, CONFIRMED exception to the
     scarcity rule above, not an oversight — Leron was offered the quiet
     unpinged variant on 2026-08-14 and chose to keep @here. Do not "tidy"
     them down to a silent note: the whole reason this alert exists is that
     the strike and expiration were previously invisible unless you went and
     opened the page. Changing it back needs him to say so.

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
from datetime import date, datetime, timedelta
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


def _push_phone(title: str, body: str) -> None:
    """Second channel for the alerts that are time-critical — i.e. the ones
    where reading it an hour later is worth nothing.

    Two independent sinks, both optional, both env-driven, neither fatal:
      * RISK_PHONE_WEBHOOK — a Discord webhook pointed at a personal channel.
        This is the one that actually reaches Leron's phone.
      * RISK_NTFY_TOPIC    — ntfy.sh topic.

    🚨 ntfy is the SECONDARY here on purpose. Per the 2026-07-30 finding, ntfy
    iOS notifications do not surface in his Notification Center (app-side; the
    settings were verified) — he had to open the app to see them, which defeats
    the point. Discord iOS pushes work. So ntfy is kept as a redundant sink,
    not relied on as "the phone channel".
    """
    import os
    import requests as req
    hook = os.getenv("RISK_PHONE_WEBHOOK", "")
    if hook:
        try:
            # `content` is what renders in the phone notification itself —
            # an embed alone shows as an empty message on mobile.
            req.post(hook, json={"content": f"**{title}**\n{body}"}, timeout=15)
        except Exception as e:      # noqa: BLE001
            logger.warning("[RiskAlerts] phone webhook failed: %r", e)
    topic = os.getenv("RISK_NTFY_TOPIC", "")
    if topic:
        try:
            req.post(f"https://ntfy.sh/{topic}",
                     data=body.encode("utf-8"),
                     headers={"Title": title, "Priority": "high"}, timeout=15)
        except Exception as e:      # noqa: BLE001
            logger.warning("[RiskAlerts] ntfy failed: %r", e)


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

            try:
                from .econ_calendar import macro_today
                macro = macro_today(today)
            except Exception:
                macro = None
            if backw or flag:
                if not _claim_post_slot_db("risk_morning_riskoff", today):
                    return
                actions = []
                if macro:
                    actions.append(f"• 📅 **{macro} today** — announcement days "
                                   "run hotter; context, not a new signal")
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
            from .routes_risk import (_capture_snapshot, _flow_history, _z,
                                      _pc_z)
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
            # 🚨 THE MIX LEG (added 2026-08-18). On 2026-08-17 both level legs
            # were correctly quiet (put +0.58, total -0.45) and this one was at
            # +2.72 — the highest of the trailing 63 — 90 minutes before SPY
            # slid 775.50 -> 772.51. Without it this alert stays silent on
            # exactly the mornings where the composition, not the size, of the
            # flow is the outlier. See routes_risk._pc_z for the evidence.
            cz = _pc_z(snap, prior)
            if (pz or 0) > 2 or (tz or 0) > 2 or (cz or 0) > 2:
                if not _claim_post_slot_db("risk_flow_spike", now.date()):
                    return
                # which side is driving it — plain-speech composition line
                if (cz or 0) > 2 and (pz or 0) <= 2 and (tz or 0) <= 2:
                    driver = (
                        f"Driven by the **MIX, not the size** — total volume is "
                        f"ordinary (z {(tz or 0):.1f}) but the put/call ratio is "
                        f"{(cz or 0):.1f}σ, the highest in ~3 months. In plain "
                        f"English: puts are normal and **call buying has gone "
                        f"missing**. This is the shape that was present on the "
                        f"morning of 2026-08-17 and that this alert used to miss "
                        f"entirely.")
                elif (pz or 0) > 2 and (oz or 0) <= 1:
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
                        f"put/call MIX z {(cz or 0):.1f} · 0DTE call z "
                        f"{(oz or 0):.1f}).\n"
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

    async def confirm_check():
        """STAGE 2. Every 10 min, 10:10-14:00 CT weekdays.

        The 10:00 snapshot can tell you a big move is coming but NOT which way
        — measured, P(down) 45.8% vs a 45.4% base. So this job does not
        predict direction. It waits for the market to commit, and only then
        speaks. Validated 2026-08-18 over 904 sessions:

            price break alone, unflagged day   n=916   49.8% continue
            FLAGGED day, then the same break   n= 95   63.2% continue  z=+2.61

        Neither leg works alone. Robust across 0.10-0.30% break thresholds,
        positive 4/4 years, and symmetric on up and down breaks (disjoint
        samples, same effect) — which is the reason to believe it over the
        book's long-standing "intraday continuation is dead" prior: that prior
        is confirmed here, and only broken when the flow flag is present.

        🚨 Replayed on 2026-08-17 this confirms DOWN at 11:55 CT / 774.68 with
        $2.00 of the $3.00 slide still to come. That session is the reason the
        job exists: the 10:00 alert alone had nothing to say, and every page
        went on quoting a put sale while SPY walked down.

        Advisory. No bot reads it — EBB is warn-only by decision, because the
        breach lift that would justify a veto is not significant (n=37).
        """
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .routes_risk import (CONFIRM_WINDOW_CT, CONFIRM_MOVE_PCT,
                                      CONFIRM_ARM_Z, _rolling_flow_now,
                                      _flow_history, _pc_z, _latest_snapshot,
                                      confirm_step, session_log_write)
            start, end = CONFIRM_WINDOW_CT
            t = (now.hour, now.minute)
            if t < start or t > end:
                return
            today = now.date()
            # stage 1 — is today flagged? Read the stored 10:00 snapshot; do
            # NOT capture here, or this job would race the validated window.
            snap = _latest_snapshot(today)
            pcz = None
            if snap is not None:
                prior = [r for r in _flow_history() if r["d"] < today]
                pcz = _pc_z(snap, prior)
            armed = bool((pcz or 0) > CONFIRM_ARM_Z)

            shim = SimpleNamespace(app=app)
            live = await _rolling_flow_now(shim)
            if live is None or not live.get("spot"):
                return
            # tape first, so the price point survives even if the step below
            # throws — a gap in the tape is what made the 08-17 post-mortem
            # hard, and this poll is the only place spot is sampled.
            session_log_write(today, now, spot=float(live["spot"]))
            hit = confirm_step(today, now, float(live["spot"]), armed, pcz)
            if hit is None:
                return
            if not _claim_post_slot_db("risk_confirm", today):
                return

            d = hit["dir"]
            arrow = "🔻" if d == "DOWN" else "🔺"
            title = (f"{arrow} {d} CONFIRMED — SPY {hit['spot']:.2f} · "
                     "this one has legs more often than not")
            plain = (
                f"This morning's option MIX was a {hit['putcall_z']:.1f}σ outlier "
                f"(put/call ratio, top of the last 63 sessions). That said a big "
                f"move was coming but not which way.\n\n"
                f"SPY has now broken **{d}** through {hit['move_pct']:+.2f}% off "
                f"the 10:00 level ({hit['ref']:.2f} → {hit['spot']:.2f}) and is at "
                f"a session {'low' if d == 'DOWN' else 'high'}. **On flagged days "
                f"that break keeps going 63% of the time** vs a 50% coin flip on "
                f"normal days. Median further run: {'-' if d == 'DOWN' else '+'}0.19%.\n\n"
                f"**In plain English:** the market has picked a side and it tends "
                f"to stay picked today. If you are short {'put' if d == 'DOWN' else 'call'} "
                f"premium into this, you are on the wrong side of it — that is the "
                f"position to reduce or close. Do not add.")
            _send({
                "title": title,
                "description": plain,
                "color": RED if d == "DOWN" else GREEN,
                "fields": [
                    {"name": "continues", "value": "63.2% vs 49.8% base",
                     "inline": True},
                    {"name": "evidence", "value": "n=95, z=+2.6, 4/4 yrs",
                     "inline": True},
                    {"name": "fires on", "value": "~2.5% of days", "inline": True},
                ],
                "footer": {"text": "two-stage flow+confirmation · advisory only, "
                                   "no bot acts on this · /risk"},
            }, ping=True)
            _push_phone(
                f"{arrow} SPY {d} confirmed {hit['spot']:.2f}",
                f"{hit['move_pct']:+.2f}% off the 10:00 level on a flagged day. "
                f"Keeps going 63% of the time (vs 50% normal). Reduce short "
                f"{'put' if d == 'DOWN' else 'call'} premium; don't add.")
        except Exception as e:      # noqa: BLE001
            logger.warning("[RiskAlerts] confirm_check failed: %r", e)

    async def confirm_close():
        """15:05 CT — staple the session close onto today's watcher row so
        every live firing carries its own outcome. The backtest is n=95; this
        is how that number grows into live evidence instead of a claim that
        has to be re-argued from a log that overwrote itself."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .routes_risk import _rolling_flow_now, confirm_record_close
            shim = SimpleNamespace(app=app)
            live = await _rolling_flow_now(shim)
            if live and live.get("spot"):
                confirm_record_close(now.date(), float(live["spot"]))
        except Exception as e:      # noqa: BLE001
            logger.warning("[RiskAlerts] confirm_close failed: %r", e)

    async def calibration_score():
        """15:40 CT — append today's completed session to the evaluation
        record. Runs after settlement so the close is real. This is what keeps
        the decay monitor from going stale: the sample grows every session,
        not only when the signal fires."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .signal_calibration import score_session
            score_session(now.date())
        except Exception as e:      # noqa: BLE001
            logger.warning("[RiskAlerts] calibration_score failed: %r", e)

    async def calibration_report():
        """First Monday, 08:15 CT — post the scorecard against the
        pre-registered lines, and DISARM the pivot if it has breached.

        Posts on every verdict INCLUDING PASS. A monitor that only speaks when
        something is wrong cannot be distinguished from a monitor that has
        stopped running — the failure this whole body of work exists to catch.
        """
        try:
            now = datetime.now(CT)
            from .signal_calibration import report, enforce
            rep = report(now.date())
            if not _claim_post_slot_db("risk_calibration", now.date()):
                return
            disarmed = enforce(rep)
            v = rep.get("verdict")
            colour = {"PASS": GREEN, "WARN": AMBER, "DISARM": RED,
                      "UNDERPOWERED": AMBER}.get(v, AMBER)
            cont = rep.get("continuation")
            base = rep.get("base_continuation")
            lcb = rep.get("continuation_lcb")
            body = [
                f"**{v}** — {rep.get('n_armed_fired', 0)} flagged firings in the "
                f"trailing {rep.get('window_months')} months "
                f"({rep.get('live_sessions', 0)} live sessions so far).",
            ]
            if cont is not None and base is not None:
                body.append(
                    f"\nWhen the flag fires and price then breaks, it keeps going "
                    f"**{cont:.1%}** of the time (worst-case {lcb:.1%}) against "
                    f"**{base:.1%}** on unflagged days. The gap is the edge; if it "
                    f"closes, the pivot stops earning its keep.")
            for r in rep.get("reasons", []):
                body.append(f"\n• {r}")
            if disarmed:
                body.append(f"\n\n🚨 **PIVOT DISARMED on {', '.join(disarmed)}.** "
                            "EBB is back to holding every trade to settlement. "
                            "Re-arming is a manual decision, on purpose.")
            elif v == "PASS":
                body.append("\n\nNothing to do — the pivot stays armed.")
            _send({
                "title": f"📐 Signal calibration — {v}",
                "description": "".join(body),
                "color": colour,
                "footer": {"text": "thresholds pre-registered 2026-08-18, before "
                                   "any live firing · /api/spreadworks/"
                                   "risk-advisor/calibration"},
            }, ping=(v == "DISARM"))
        except Exception as e:      # noqa: BLE001
            logger.warning("[RiskAlerts] calibration_report failed: %r", e)

    async def rolling_flow_check():
        """Every 10 min, 10:36-14:00 CT weekdays: catch a flow spike the
        fixed 10:00/12:00/13:30 clocks miss (registry #39, validated
        2026-08-13: P(|move to close| >= 0.5%) 34.2% on alert days vs 22.4%
        minute-matched base, 1.53x lift, 4/4 years, ~23 alerts/yr).

        The fixed clocks own their windows — this job posts NOTHING if one
        of them already fired a spike alert today (suppression below)."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .routes_risk import (ROLLING_WINDOW_CT, _rolling_flow_now,
                                      _rolling_baseline_at, _rolling_z,
                                      _save_rolling_state, session_log_write)
            start, end = ROLLING_WINDOW_CT
            t = (now.hour, now.minute)
            if t < start or t > end:
                return
            shim = SimpleNamespace(app=app)     # capture helper expects request.app
            snap = await _rolling_flow_now(shim)
            if snap is None:
                logger.info("[RiskAlerts] rolling flow fetch failed — skip poll")
                return
            baseline = _rolling_baseline_at(now)
            if baseline is None:
                logger.info("[RiskAlerts] no rolling baseline for this minute — skip poll")
                return
            pz = _rolling_z(snap["putv"], baseline["put_mean"], baseline["put_sd"])
            tz = _rolling_z(snap["totv"], baseline["tot_mean"], baseline["tot_sd"])
            today = now.date()
            # refresh the live reading on EVERY successful poll — whether or
            # not it crosses the alert threshold — so /state's flow_rolling
            # block always shows the current z, not just the fired moment.
            _save_rolling_state(today, now.replace(tzinfo=None), pz, tz)
            # …and APPEND it, because the line above overwrites. That single
            # overwritten row is the reason the 2026-08-17 slide has no
            # surviving intraday z history at all.
            session_log_write(today, now, spot=snap.get("spot"),
                              roll_putv_z=pz, roll_totv_z=tz)

            if (pz or 0) <= 2 and (tz or 0) <= 2:
                return
            # the fixed clocks own their windows — a spike they already
            # alerted on today is not this job's to duplicate
            if (_already_posted("risk_flow_spike", today)
                    or _already_posted("risk_pm_1200", today)
                    or _already_posted("risk_pm_1330", today)):
                return
            if not _claim_post_slot_db("risk_flow_rolling", today):
                return
            _send({
                "title": "⚠️ Rolling flow check — unusual option volume "
                         "just crossed the line",
                "description": (
                    f"Rolling flow check: unusually heavy option flow just "
                    f"crossed the line (put z {(pz or 0):.1f} / total z "
                    f"{(tz or 0):.1f} at {now.strftime('%H:%M')} CT). On "
                    "days like this the market moved another ≥ 0.5% by "
                    "the close 34% of the time vs 22% on normal days "
                    "(backtest 2023-26, registry #39).\n\n"
                    "Same playbook: no new same-day (0DTE) trades, tighten "
                    "exits on anything expiring today. Multi-day positions: "
                    "ignore this one."),
                "color": AMBER,
                "fields": [
                    {"name": "move odds", "value": "34.2% vs 22.4% base",
                     "inline": True},
                    {"name": "lift", "value": "1.53x, 4/4 years",
                     "inline": True},
                    {"name": "checked at", "value": f"{now.strftime('%H:%M')} CT",
                     "inline": True},
                ],
                "footer": {"text": "polled every 10 min, 10:36-14:00 CT · "
                                   "registry #39 · advisory only · /risk "
                                   "for the playbook"},
            }, ping=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] rolling_flow_check failed: %r", e)

    async def expected_move_note():
        """Daily 08:06 CT quiet note: today's SPY expected move in % AND price.

        Informational, never pings — the number every same-day decision keys
        off (the intraday chart's band, EBB's regime, the breach alert)."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .routes_risk import _cboe, _latest, _live_quote
            v1 = await _cboe(app.state.http, "VIX1D")
            d, v1_c = _latest(v1)
            em = v1_c / SQRT252
            # claim the once-per-day slot only AFTER the data fetch succeeded —
            # claiming first burned the slot on a transient fetch failure and
            # silently killed that day's note
            if not _claim_post_slot_db("risk_em_note", now.date()):
                return
            shim = SimpleNamespace(app=app)
            q = await _live_quote(shim)
            prev = (q or {}).get("prev_close")
            band = ""
            if prev:
                lo, hi = prev * (1 - em / 100), prev * (1 + em / 100)
                band = f"\nPrice band: **${lo:,.2f} — ${hi:,.2f}** (prev close ${prev:,.2f})"
            _send({
                "title": f"📏 Today's SPY expected move: ±{em:.2f}%",
                "description": (
                    f"The options market has priced a ±{em:.2f}% day "
                    f"(VIX1D {v1_c:.1f} at yesterday's close).{band}\n"
                    "Inside the band = a normal day for premium selling. "
                    "A breach alert posts if price trades outside it."),
                "color": 0x60A5FA,
                "footer": {"text": f"closes of {d} · quiet daily note · /risk "
                                   "shows the live budget bar"},
            }, ping=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] expected_move_note failed: %r", e)

    async def em_breach_check():
        """Every 10 min in-session: @here once per day if SPY trades OUTSIDE
        the day's expected-move band — the day is officially bigger than
        options priced."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            if not ((now.hour, now.minute) >= (8, 35) and now.hour < 15):
                return
            from .routes_risk import _cboe, _latest, _live_quote
            shim = SimpleNamespace(app=app)
            q = await _live_quote(shim)
            if not q or not q.get("prev_close"):
                return
            v1 = await _cboe(app.state.http, "VIX1D")
            _, v1_c = _latest(v1)
            em = v1_c / SQRT252
            chg = q.get("chg_pct")
            if chg is None or abs(chg) < em:
                return
            if not _claim_post_slot_db("risk_em_breach", now.date()):
                return
            side = "ABOVE" if chg > 0 else "BELOW"
            _send({
                "title": f"🚨 SPY is outside today's expected move "
                         f"({chg:+.2f}% vs ±{em:.2f}% priced)",
                "description": (
                    f"Price **${q['last']:,.2f}** has broken {side} the band "
                    f"the options market paid for today — the day is already "
                    f"bigger than priced.\n\n"
                    "**DO:** no new same-day premium selling; tighten or close "
                    "anything expiring today (its breakeven math is broken). "
                    "Multi-day positions: reassess size, don't panic-exit.\n"
                    "**DON'T:** don't chase direction — breach days were "
                    "tested for follow-through direction and none exists "
                    "(all t < 1). The information is the SIZE of the day, "
                    "not its sign."),
                "color": RED,
                "footer": {"text": "checked every 10 min in-session · fires "
                                   "once per day · advisory only"},
            }, ping=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] em_breach_check failed: %r", e)

    async def health_flip_check():
        """15:50 CT weekdays: detect a scorecard signal's health status
        FLIPPING (sharp <-> DEGRADED) and push. A signal's first sighting
        only seeds RiskHealthState — there is no prior status to compare
        against, so nothing is announced that day."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            from .db import SessionLocal
            from .routes_risk import scorecard, RiskHealthState
            if SessionLocal is None:
                return
            try:
                shim = SimpleNamespace(app=app)
                result = await scorecard(shim)
            except Exception as e:
                logger.warning("[RiskAlerts] health_flip_check scorecard failed: %r", e)
                return
            health = (result or {}).get("health") or {}
            today = now.date()
            for signal, info in health.items():
                status = (info or {}).get("status")
                if status not in ("sharp", "DEGRADED"):
                    continue          # warming_up / static — nothing to flip
                if not _claim_post_slot_db(f"risk_health_{signal}", today):
                    continue
                db = SessionLocal()
                try:
                    row = db.get(RiskHealthState, signal)
                    prev_status = row.status if row else None
                    if row is None:
                        db.add(RiskHealthState(signal=signal, status=status,
                                               updated_at=now))
                        db.commit()
                        continue      # first sighting — seed only, no post
                    if prev_status == status:
                        row.updated_at = now
                        db.commit()
                        continue      # unchanged — nothing to announce
                    row.status = status
                    row.updated_at = now
                    db.commit()
                finally:
                    db.close()
                if status == "DEGRADED":
                    why = info.get("why", "no detail available")
                    _send({
                        "title": f"⚠️ Signal health: {signal} is now DEGRADED",
                        "description": (
                            f"{why}. Treat it as unreliable until re-validated; "
                            "the page has downgraded it."),
                        "color": RED,
                        "footer": {"text": "/risk scorecard · advisory only"},
                    }, ping=True)
                else:
                    _send({
                        "title": f"Signal health: {signal} recovered to SHARP.",
                        "color": GREEN,
                        "footer": {"text": "/risk scorecard · advisory only"},
                    }, ping=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] health_flip_check failed: %r", e)

    async def friday_digest():
        """Friday 15:55 CT: quiet weekly recap — scorecard grades over the
        last 5 sessions, EBB's week, this week's breach/spike alert counts,
        and squeeze-tell promotion progress. No ping — a recap, not an
        alert."""
        try:
            now = datetime.now(CT)
            if now.weekday() != 4:      # belt-and-braces; cron already gates fri
                return
            today = now.date()
            if not _claim_post_slot_db("risk_friday_digest", today):
                return

            from .routes_risk import scorecard
            try:
                shim = SimpleNamespace(app=app)
                result = await scorecard(shim)
            except Exception as e:
                logger.warning("[RiskAlerts] friday_digest scorecard failed: %r", e)
                result = {}
            recent = (result or {}).get("recent") or []
            last5 = recent[-5:]
            grades = {"hit": 0, "false_alarm": 0, "missed": 0, "clear": 0}
            for r in last5:
                g = r.get("grade")
                if g in grades:
                    grades[g] += 1
            scorecard_line = (f"hit {grades['hit']} · false alarm "
                              f"{grades['false_alarm']} · missed "
                              f"{grades['missed']} · clear {grades['clear']}")

            # EBB week — read-only, never raise (a query hiccup just falls
            # back to "no trades yet").
            ebb_line = "no trades yet"
            try:
                from .db import SessionLocal as _SL
                from sqlalchemy import text as sa_text
                if _SL is not None:
                    cutoff = today - timedelta(days=7)
                    db = _SL()
                    try:
                        row = db.execute(sa_text(
                            "SELECT COUNT(*) AS n, COALESCE(SUM(realized_pnl), 0) AS s "
                            "FROM ebb_closed_trades WHERE close_time >= :c"
                        ), {"c": cutoff}).mappings().first()
                    finally:
                        db.close()
                    n = int(row["n"] or 0)
                    s = float(row["s"] or 0)
                    if n > 0:
                        sign = "+" if s >= 0 else ""
                        ebb_line = f"{n} trades · {sign}${s:,.2f}"
            except Exception as e:
                logger.warning("[RiskAlerts] friday_digest EBB query failed: %r", e)

            # Breach/spike counts this week — read-only, skip counts (not
            # the whole line) on any hiccup.
            breach_line = "see channel history"
            try:
                from .db import SessionLocal as _SL
                from sqlalchemy import text as sa_text
                if _SL is not None:
                    week_start = today - timedelta(days=today.weekday())
                    db = _SL()
                    try:
                        rows = db.execute(sa_text(
                            "SELECT message_key, COUNT(*) AS n FROM discord_post_log "
                            "WHERE message_key IN "
                            "('risk_em_breach','risk_flow_spike','risk_pm_1200',"
                            "'risk_pm_1330') AND fire_date >= :w "
                            "GROUP BY message_key"
                        ), {"w": week_start}).mappings().all()
                    finally:
                        db.close()
                    counts = {r["message_key"]: r["n"] for r in rows}
                    breach_line = (
                        f"EM breach {counts.get('risk_em_breach', 0)} · "
                        f"flow spike {counts.get('risk_flow_spike', 0)} · "
                        f"12:00 re-check {counts.get('risk_pm_1200', 0)} · "
                        f"13:30 re-check {counts.get('risk_pm_1330', 0)}")
            except Exception as e:
                logger.warning("[RiskAlerts] friday_digest breach count failed: %r", e)

            promo = ((result or {}).get("promotion") or {}).get("squeeze_tell") or {}
            have = promo.get("quiet_sessions_have", "?")
            needed = promo.get("quiet_sessions_needed", "?")

            _send({
                "title": "\U0001f4d2 Week in review — Risk Advisor & EBB",
                "fields": [
                    {"name": "Scorecard (last 5 sessions)",
                     "value": scorecard_line, "inline": False},
                    {"name": "EBB this week", "value": ebb_line, "inline": False},
                    {"name": "Breaches / spikes this week",
                     "value": breach_line, "inline": False},
                    {"name": "Squeeze-tell promotion progress",
                     "value": f"{have} / {needed} quiet sessions", "inline": False},
                ],
                "color": 0x60A5FA,
                "footer": {"text": "advisory only · /risk for detail"},
            }, ping=False)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] friday_digest failed: %r", e)

    async def promotion_announce():
        """16:05 CT weekdays: one-time announcement when the quiet-day
        squeeze tell clears its pre-registered promotion gate.

        SQUEEZE_TELL_PROMOTED is the promotion switch — flipped only by a
        deploy/ops action AFTER the research harness confirms the gate
        (>=100 quiet sessions AND t>=2, see routes_risk.PROMOTION_QUIET_NEEDED
        and the /risk-advisor/scorecard "promotion" block). This job never
        flips it itself; it only checks and announces."""
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            if os.getenv("SQUEEZE_TELL_PROMOTED", "").strip().lower() != "true":
                return
            sentinel = date(2000, 1, 1)   # claim once, EVER — not per-day
            if not _claim_post_slot_db("risk_promotion_squeeze", sentinel):
                return
            _send({
                "title": "\U0001f393 New validated signal: the quiet-day squeeze tell",
                "description": (
                    "cleared its pre-registered promotion gate (≥100 quiet "
                    "sessions AND t ≥ 2) and is now on the playbook. "
                    "Details on /risk."),
                "color": GREEN,
                "footer": {"text": "advisory only · one-time announcement"},
            }, ping=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] promotion_announce failed: %r", e)

    async def recipe_ticket(session: str, slot_key: str):
        """Post today's actual tradeable ticket at the top of an entry window.

        Every other alert here reports market STATE. This one is the only
        alert that hands over an order: the strike pair and the expiration,
        at the moment the validated window opens, so the ticket can be placed
        without going to the page to read it off a card.
        """
        try:
            now = datetime.now(CT)
            if now.weekday() >= 5:
                return
            try:
                from . import is_market_holiday          # noqa: F401
            except Exception:
                pass
            try:
                from .economic_events import is_market_holiday as _hol
                if _hol(now.date()):
                    return
            except Exception:
                pass                                     # no calendar — still post

            from .routes_risk import recipe as _recipe
            shim = SimpleNamespace(app=app)              # /recipe expects request.app
            r = await _recipe(shim)

            today = now.date()
            if not isinstance(r, dict) or r.get("status") != "ok":
                # The window is open and we cannot price the ticket. Say so
                # quietly rather than staying silent — silence here reads as
                # "no trade today", which is a different and wrong message.
                if not _claim_post_slot_db(f"{slot_key}_unavailable", today):
                    return
                _send({
                    "title": f"⚠️ {session} window open — ticket unavailable",
                    "description": (
                        f"Could not price today's SPY 0DTE put spread "
                        f"(`{r.get('status') if isinstance(r, dict) else 'error'}`). "
                        "Check /risk before assuming there is no trade."),
                    "color": AMBER,
                    "footer": {"text": "advisory only · no bot reads this"},
                }, ping=False)
                return

            if not _claim_post_slot_db(slot_key, today):
                return

            short_k, long_k = r["short_strike"], r["long_strike"]
            credit, floor_ok = r.get("credit_now"), r.get("meets_floor")
            if credit is None:
                credit_line = ("credit: no live quote right now — check the "
                               "book before sending")
                colour = AMBER
            elif floor_ok:
                credit_line = (f"credit ≈ **${credit:.2f}** — above the "
                               f"${r.get('floor', 0.10):.2f} validated floor")
                colour = GREEN
            else:
                credit_line = (f"credit ≈ **${credit:.2f}** — **BELOW** the "
                               f"${r.get('floor', 0.10):.2f} validated floor. "
                               "**SKIP** if it is still below when you send it.")
                colour = RED

            _send({
                "title": f"\U0001f4c4 {session} ticket — SPY 0DTE put spread",
                "description": (
                    f"**SELL SPY {short_k}P / BUY SPY {long_k}P**\n"
                    f"**expires TODAY ({r['expiration']})**\n\n"
                    f"spot ${r['spot']:.2f} · {credit_line}\n\n"
                    "• Size 1 contract per $2,500–3,000 allocated. "
                    "Worst observed day −$484/lot.\n"
                    "• **NO stop-loss and NO profit-target** — every exit "
                    "tested collapses the edge to ~$0. Settling at the close "
                    "IS the trade.\n"
                    "• **Do NOT skip flagged days on this ticket** — its "
                    "backtest includes them; the calm-day gate cut it from "
                    "$12.19 to $6.00/trade. The morning verdict governs your "
                    "OTHER trading, not this."),
                "color": colour,
                "footer": {"text": "registry #23b/#41 · advisory only · "
                                   "no bot reads this"},
            }, ping=True)   # @here confirmed 2026-08-14 — see module docstring §7
        except Exception as e:  # noqa: BLE001
            logger.warning("[RiskAlerts] recipe_ticket(%s) failed: %r", session, e)

    # Cron the ticket off the REGISTRY windows, not a hardcoded clock — the
    # same single-source-of-truth rule /recipe itself follows. A registry edit
    # to ebb/ebb_pm entry_start_ct moves the alert with it instead of leaving
    # a silently-drifted copy behind.
    try:
        from .routes_risk import _recipe_windows
        (_am_h, _am_m), _, (_pm_h, _pm_m), _ = _recipe_windows()
    except Exception as _rw_exc:  # noqa: BLE001
        _am_h, _am_m, _pm_h, _pm_m = 10, 5, 13, 5
        logger.warning("[RiskAlerts] registry windows unreadable (%r) — "
                       "ticket alerts fall back to 10:05/13:05 CT", _rw_exc)
    scheduler.add_job(recipe_ticket, "cron", hour=_am_h, minute=_am_m,
                      timezone=CT, id="risk_recipe_am",
                      args=["AM", "risk_recipe_am"])
    scheduler.add_job(recipe_ticket, "cron", hour=_pm_h, minute=_pm_m,
                      timezone=CT, id="risk_recipe_pm",
                      args=["PM", "risk_recipe_pm"])

    scheduler.add_job(morning_verdict, "cron", hour=8, minute=5, second=30,
                      timezone=CT, id="risk_morning_verdict")
    scheduler.add_job(expected_move_note, "cron", hour=8, minute=6, second=30,
                      timezone=CT, id="risk_em_note")
    scheduler.add_job(flow_spike_check, "cron", hour=10, minute=6,
                      timezone=CT, id="risk_flow_spike")
    scheduler.add_job(pm_recheck, "cron", hour=12, minute=6, timezone=CT,
                      id="pm_recheck_1200",
                      args=["12:00", "risk_pm_1200", "risk_pm_fade_1200"])
    scheduler.add_job(pm_recheck, "cron", hour=13, minute=36, timezone=CT,
                      id="pm_recheck_1330",
                      args=["13:30", "risk_pm_1330", "risk_pm_fade_1330"])
    scheduler.add_job(rolling_flow_check, "cron", minute="*/10", timezone=CT,
                      id="risk_flow_rolling")
    scheduler.add_job(confirm_check, "cron", minute="*/10", timezone=CT,
                      id="risk_confirm")
    scheduler.add_job(confirm_close, "cron", hour=15, minute=5, timezone=CT,
                      id="risk_confirm_close")
    scheduler.add_job(calibration_score, "cron", hour=15, minute=40,
                      day_of_week="mon-fri", timezone=CT, id="risk_calib_score")
    scheduler.add_job(calibration_report, "cron", day="1-7", day_of_week="mon",
                      hour=8, minute=15, timezone=CT, id="risk_calib_report")
    scheduler.add_job(em_breach_check, "cron", minute="*/10", timezone=CT,
                      id="risk_em_breach")
    scheduler.add_job(health_flip_check, "cron", hour=15, minute=50,
                      timezone=CT, id="risk_health_flip")
    scheduler.add_job(friday_digest, "cron", day_of_week="fri", hour=15,
                      minute=55, timezone=CT, id="risk_friday_digest")
    scheduler.add_job(promotion_announce, "cron", hour=16, minute=5,
                      timezone=CT, id="risk_promotion_announce")
    logger.info("[RiskAlerts] registered: morning verdict 08:05:30, EM note "
                "08:06:30, ticket %02d:%02d & %02d:%02d, flow spike 10:06, "
                "PM re-checks 12:06 & 13:36, rolling flow watcher */10 "
                "10:36-14:00, CONFIRMATION watcher */10 10:10-14:00 + close "
                "record 15:05, EM-breach watch */10 in-session, health flip "
                "15:50, Friday digest 15:55, promotion announce 16:05 "
                "(all CT)", _am_h, _am_m, _pm_h, _pm_m)
