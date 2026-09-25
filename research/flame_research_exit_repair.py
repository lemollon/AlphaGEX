"""Research-only Flame Research exit repair study.

Entry is frozen:
- SPY 0DTE put credit spread
- 12:00 ET decision / 12:01 ET modeled entry
- efficiency >= 0.30
- $2 width
- same strike/credit/liquidity selection as the frozen Research engine

Only exit policy varies. No broker imports, no production DB writes, no EBB changes.
"""
from __future__ import annotations

import json
import os
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal as D
from http.server import HTTPServer

import flame_dual_engine_portfolio as old
import flame_two_entry_optimized as base

core = old.core
U = core.U

CLOSURES = [
    "2025-01-01","2025-01-09","2025-01-20","2025-02-17","2025-04-18","2025-05-26",
    "2025-06-19","2025-07-03","2025-07-04","2025-09-01","2025-11-27","2025-11-28",
    "2025-12-24","2025-12-25","2026-01-01","2026-01-19","2026-02-16","2026-04-03",
    "2026-05-25","2026-06-19","2026-07-03",
]
RUN_START = os.getenv("FLAME_REPAIR_START", "2025-01-01")
RUN_END = os.getenv("FLAME_REPAIR_END", "2026-08-31")

def _expected_sessions(start, end, closures):
    from datetime import date, timedelta
    d=date.fromisoformat(start); last=date.fromisoformat(end); n=0
    closed=set(closures)
    while d<=last:
        if d.weekday()<5 and d.isoformat() not in closed:
            n+=1
        d+=timedelta(days=1)
    return n

RUN_CLOSURES=[d for d in CLOSURES if RUN_START <= d <= RUN_END]
RUN_EXPECTED=_expected_sessions(RUN_START,RUN_END,RUN_CLOSURES)

core.SPEC.update({
    "id": "flame-research-exit-repair-v2-20260925",
    "start": RUN_START,
    "end": RUN_END,
    "closures": RUN_CLOSURES,
    "expected_sessions": RUN_EXPECTED,
    "flat_et_minute": 945,
    "max_requests": 1200,
    "deadline_seconds": 7200,
    "scope": "frozen Research entry; preregistered exit repair comparison; research only",
    "no_saved_price_inputs": True,
    "no_previous_trade_inputs": True,
})

VARIANTS = {
    "baseline_tp50_stop2x": {"target_capture_pct": 50, "stop_mult": D("2.0")},
    "tp25_stop2x": {"target_capture_pct": 25, "stop_mult": D("2.0")},
    "tp50_stop1_5x": {"target_capture_pct": 50, "stop_mult": D("1.5")},
    "tp25_stop1_5x": {"target_capture_pct": 25, "stop_mult": D("1.5")},
    "tp50_no_stop_diag": {"target_capture_pct": 50, "stop_mult": None},
}

DEV_END = "2025-05-30"
EXT_START = "2025-06-02"


def money(cents):
    return core.money(int(cents))


def replay_variant(df, k, w, decision, target_capture_pct, stop_mult):
    t = decision + 1
    end = core.SPEC["flat_et_minute"]
    short = df.leg(k, t)
    long = df.leg(k - w * U, t)

    def mk(m):
        s = short.get(m)
        l = long.get(m)
        if s is None or l is None:
            return None
        return (s[0] - l[1], s[1] - l[0], s[1] - s[0] + l[1] - l[0])

    p = mk(t)
    if p is None:
        return {"status": "skip", "reason": "no_entry_quote"}
    credit = p[0]
    if not w * U * core.SPEC["credit_min_pct_width"] <= 100 * credit <= w * U * core.SPEC["credit_max_pct_width"]:
        return {"status": "skip", "reason": "entry_credit_changed"}
    if p[2] > core.SPEC["max_combined_quote_width_units"]:
        return {"status": "skip", "reason": "entry_spread_widened"}

    fee = core.SPEC["fee_cents_roundtrip"]
    risk = w * U - credit + fee
    result_base = {
        "short_units": k,
        "width": w,
        "credit_units": credit,
        "risk_cents": risk,
        "decision_minute_et": decision,
        "entry_minute_et": t,
    }
    worst = 0
    best = 0
    within = 0

    for m in range(t, end):
        q = mk(m)
        if q is None:
            return {**result_base, "status": "unresolved", "reason": "missing_open_position_quote", "at_minute": m}
        debit = q[1]
        if debit < 0:
            return {**result_base, "status": "unresolved", "reason": "negative_synthetic_debit"}
        mark = credit - debit - fee
        worst = min(worst, mark)
        best = max(best, mark)
        within = max(within, best - mark)

        hit_stop = stop_mult is not None and D(debit) >= stop_mult * D(credit)
        target_debit_pct = 100 - target_capture_pct
        hit_target = debit * 100 <= target_debit_pct * credit
        reason = "stop" if hit_stop else "target" if hit_target else "time" if m == end - 1 else None
        if reason:
            x = mk(m + 1)
            if x is None:
                return {**result_base, "status": "unresolved", "reason": "missing_exit_quote"}
            close = x[1]
            pnl = credit - close - fee
            return {
                **result_base,
                "status": "trade",
                "reason": reason,
                "exit_minute_et": m + 1,
                "debit_units": close,
                "net_cents": pnl,
                "worst_open_cents": min(worst, pnl),
                "best_open_cents": max(best, pnl),
                "within_trade_drawdown_cents": max(within, best - pnl),
            }
    raise AssertionError("missing_exit")


def summarize(rows, name, start=None, end=None):
    filt = [r for r in rows if (start is None or r["day"] >= start) and (end is None or r["day"] <= end)]
    eq = core.SPEC["initial_equity_cents"]
    peak = eq
    maxdd = 0
    profit = 0
    accepted = []
    rejects = Counter()

    for row in filt:
        tr = row["variants"].get(name)
        if tr is None:
            rejects["no_candidate"] += 1
            continue
        if tr.get("status") != "trade":
            rejects[tr.get("reason", "not_trade")] += 1
            continue
        if tr["risk_cents"] * 100 > eq * core.SPEC["position_risk_pct"]:
            rejects["risk_budget"] += 1
            continue
        accepted.append({"day": row["day"], "eff": row["eff"], **tr})
        maxdd = max(maxdd, peak - (eq + tr.get("worst_open_cents", 0)))
        eq += tr["net_cents"]
        profit += tr["net_cents"]
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)

    wins = [x for x in accepted if x["net_cents"] > 0]
    losses = [x for x in accepted if x["net_cents"] < 0]
    reasons = Counter(x["reason"] for x in accepted)
    months = defaultdict(lambda: {"trades": 0, "pnl_cents": 0})
    for x in accepted:
        z = months[x["day"][:7]]
        z["trades"] += 1
        z["pnl_cents"] += x["net_cents"]

    return {
        "variant": name,
        "start": start or core.SPEC["start"],
        "end": end or core.SPEC["end"],
        "sessions": len(filt),
        "trades": len(accepted),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(100 * len(wins) / len(accepted), 1) if accepted else 0,
        "trading_net": money(profit),
        "avg_win": money(sum(x["net_cents"] for x in wins) / len(wins)) if wins else 0,
        "avg_loss": money(sum(x["net_cents"] for x in losses) / len(losses)) if losses else 0,
        "worst_trade": money(min((x["net_cents"] for x in accepted), default=0)),
        "max_observed_drawdown": money(maxdd),
        "ending_equity": money(eq),
        "exit_reasons": dict(reasons),
        "rejections": dict(rejects),
        "months": {k: {"trades": v["trades"], "pnl": money(v["pnl_cents"])} for k, v in sorted(months.items())},
    }


def verdict(dev, ext):
    baseline = ext["baseline_tp50_stop2x"]
    qualified = []
    for name in VARIANTS:
        if name == "baseline_tp50_stop2x" or name.endswith("_diag"):
            continue
        d = dev[name]
        e = ext[name]
        checks = {
            "development_nonnegative": d["trading_net"] >= 0,
            "extension_positive": e["trading_net"] > 0,
            "extension_beats_baseline": e["trading_net"] > baseline["trading_net"],
            "drawdown_not_worse": e["max_observed_drawdown"] <= baseline["max_observed_drawdown"],
            "worst_trade_not_worse": e["worst_trade"] >= baseline["worst_trade"],
        }
        if all(checks.values()):
            qualified.append((name, e["trading_net"], checks))
        core.emit("exit_repair_candidate_check", variant=name, checks=checks)
    qualified.sort(key=lambda x: x[1], reverse=True)
    return {
        "qualified": [x[0] for x in qualified],
        "best_by_extension_net_if_qualified": qualified[0][0] if qualified else None,
        "rule": "positive development and extension; beats extension baseline; no worse extension drawdown or worst trade",
    }


def execute():
    core.STATE["stage"] = "running"
    feed = core.Feed()
    days = core.session_days()
    rows = []
    try:
        core.emit(
            "exit_repair_spec",
            configuration=core.SPEC,
            variants={k: {"target_capture_pct": v["target_capture_pct"], "stop_mult": str(v["stop_mult"]) if v["stop_mult"] is not None else None} for k, v in VARIANTS.items()},
            entry_rules={"decision_et": 720, "efficiency_min": 0.30, "width": 2, "strike_selection": "frozen"},
            acceptance="positive development and extension; beats extension baseline; no worse extension drawdown or worst trade",
            ebb_changed=False,
            live_changed=False,
        )
        errors=[]
        workers=max(1,min(int(os.getenv("FLAME_REPAIR_WORKERS","6")),8))
        request_lock=threading.Lock()
        feeds=[]

        def run_day(day):
            local_feed=core.Feed()
            with request_lock:
                feeds.append(local_feed)
            try:
                stock=old.get_stock(local_feed,day)
                df=base.DayFeed(local_feed,day,stock)
                eff=old.research_eff(stock,720)
                row={"day":day,"eff":float(eff),"variants":{}}
                if eff>=D("0.30"):
                    q=df.snapshot(720)
                    k=base.choose_snapshot(q,old.spot(stock,720),2)
                    if k is not None:
                        for name,cfg in VARIANTS.items():
                            row["variants"][name]=replay_variant(df,k,2,720,**cfg)
                return row,None
            except Exception as day_exc:
                err={"day":day,"kind":type(day_exc).__name__,"reason":str(day_exc)[:240]}
                return {"day":day,"eff":None,"variants":{},"error":err},err

        done=0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_map={pool.submit(run_day,day):day for day in days}
            for fut in as_completed(future_map):
                row,err=fut.result()
                rows.append(row)
                if err:
                    errors.append(err)
                    core.emit("exit_repair_day_error",**err)
                done+=1
                if done%10==0 or done==len(days):
                    total_requests=sum(x.n for x in feeds)
                    core.emit("exit_repair_progress",completed=done,total=len(days),day=row["day"],provider_requests=total_requests,errors=len(errors),workers=workers)

        rows.sort(key=lambda x:x["day"])
        feed.n=sum(x.n for x in feeds)

        dev = {name: summarize(rows, name, core.SPEC["start"], DEV_END) for name in VARIANTS}
        ext = {name: summarize(rows, name, EXT_START, core.SPEC["end"]) for name in VARIANTS}
        full = {name: summarize(rows, name) for name in VARIANTS}
        for period, block in (("development", dev), ("extension", ext), ("full", full)):
            for result in block.values():
                core.emit("exit_repair_result", period=period, **result)
        v = verdict(dev, ext)
        core.STATE["stage"] = "complete"
        core.emit("exit_repair_verdict", **v)
        core.emit("exit_repair_complete", sessions=len(days), provider_requests=feed.n, errors=errors, prior_inputs=0, ebb_changed=False, live_changed=False)
    except Exception as exc:
        core.STATE["stage"] = "failed"
        core.emit("exit_repair_failed", kind=type(exc).__name__, reason=str(exc)[:500], completed=len(rows), provider_requests=feed.n)


if __name__ == "__main__":
    if os.getenv("FLAME_FRESH_MODE") == "research-exit-repair-v1":
        threading.Thread(target=execute, daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), core.Handler).serve_forever()
