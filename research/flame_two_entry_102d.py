"""Fresh-source 102-session SPY two-entry sequential test; research only.

Compares:
  A. one_entry: one qualifying 2-wide spread/day at 12:00 ET decision.
  B. two_entry_recheck: after trade 1 is fully closed, wait for next completed
     5-minute bar and take one second spread if rolling efficiency >= 0.30.
  C. two_entry_rearm: after trade 1 closes, require efficiency to print below
     0.30 at least once, then recover to >= 0.30 before a second entry.

No overlap, one contract per position, same quote-side execution, target, stop,
fees, strike/credit rules, and $2,000 account constraints.
"""
from __future__ import annotations
import csv, json, os, threading, hashlib
from collections import Counter
from datetime import datetime, timezone, date
from decimal import Decimal as D
from http.server import HTTPServer
import flame_reset_stock as patched

core = patched.core
U = core.U

core.SPEC.update({
    "id": "flame-two-entry-102d-20260923",
    "start": "2025-01-01",
    "end": "2025-05-30",
    "closures": ["2025-01-01","2025-01-09","2025-01-20","2025-02-17","2025-04-18","2025-05-26"],
    "expected_sessions": 102,
    "widths_dollars": [2],
    "profiles_units": {"natural": 0},
    "decision_et_minute": 720,
    "flat_et_minute": 945,
    "max_requests": 230,
    "deadline_seconds": 3600,
    "scope": "retrospective sequential-entry comparison, not unseen validation",
    "no_saved_price_inputs": True,
    "no_previous_trade_inputs": True,
})
MIN_EFF = D("0.30")
LATEST_SECOND_DECISION = 900   # 15:00 ET, leaves 45 min to final exit.
RECHECK_STEP = 5
COOLDOWN_MINUTES = 5


def full_stock_rows(rows, day):
    out = {}
    for r in rows:
        m = core.minute(r["timestamp"], day)
        if m == core.SPEC["flat_et_minute"]:
            continue  # endpoint is inclusive; terminal timestamp is not a completed minute bar we use
        if not 570 <= m < core.SPEC["flat_et_minute"]:
            raise core.DataError("stock_outside_rth:" + day + ":" + str(m))
        if r.get("symbol", "SPY") != "SPY" or m in out:
            raise core.DataError("stock_identity_or_duplicate")
        try:
            v = {k: core.units(r[k]) for k in ["open","high","low","close"]}
            vol = D(r["volume"])
        except Exception as e:
            raise core.DataError("stock_numeric:" + day + ":" + str(m)) from e
        if min(v.values()) <= 0 or not vol.is_finite() or vol < 0:
            raise core.DataError("bad_stock_bar")
        if v["low"] > min(v["open"],v["close"]) or v["high"] < max(v["open"],v["close"]):
            raise core.DataError("bad_stock_ohlc")
        out[m] = v
    expected = list(range(570, core.SPEC["flat_et_minute"]))
    if sorted(out) != expected:
        missing = sorted(set(expected) - set(out))
        raise core.DataError("missing_stock_minutes:" + day + ":" + repr(missing[:10]))
    return out


def completed_5m(stock, decision):
    # Build 5m bars ending strictly before decision. Stock timestamps are interval-start.
    bars = []
    for m in range(570, decision, 5):
        if m + 5 > decision:
            break
        xs = [stock[j] for j in range(m, m+5)]
        bars.append({
            "open": xs[0]["open"], "close": xs[-1]["close"],
            "high": max(x["high"] for x in xs), "low": min(x["low"] for x in xs),
        })
    return bars


def efficiency_at(stock, decision):
    b = completed_5m(stock, decision)
    if len(b) < 13:
        return D(0)
    c = [x["close"] for x in b]
    diff = c[-1] - c[-13]
    travel = sum(abs(y-x) for x,y in zip(c[-13:-1], c[-12:]))
    return (D(abs(diff)) / D(travel)) if travel else D(0)


def spot_at(stock, decision):
    # Last completed minute before decision.
    return stock[decision-1]["close"]


def parse_all_options(rows, day):
    data = {}
    seen = set()
    counts = Counter()
    for r in rows:
        counts["received"] += 1
        if r.get("symbol") != "SPY" or r.get("right","").lower() not in ("p","put"):
            raise core.DataError("wrong_option_identity")
        if r.get("expiration","")[:10].replace("-","") != day.replace("-",""):
            raise core.DataError("wrong_expiration")
        k = core.units(r["strike"])
        m = core.minute(r["timestamp"], day)
        if not core.SPEC["decision_et_minute"] <= m <= core.SPEC["flat_et_minute"]:
            raise core.DataError("option_outside_window")
        if (k,m) in seen:
            raise core.DataError("duplicate_option_observation")
        seen.add((k,m)); counts["rows"] += 1
        try:
            bid, ask = core.units(r["bid"]), core.units(r["ask"])
            bs, az = D(r["bid_size"]), D(r["ask_size"])
            if not bs.is_finite() or not az.is_finite() or bid < 0 or ask <= 0 or bid > ask or bs < 1 or az < 1:
                raise core.DataError("invalid_quote")
        except Exception:
            counts["unusable"] += 1
            continue
        data.setdefault(k,{})[m] = (bid,ask,int(bs),int(az))
    return data, dict(counts)


def market(data,k,w,m):
    s=data.get(k,{}).get(m); l=data.get(k-w*U,{}).get(m)
    if s is None or l is None: return None
    return (s[0]-l[1], s[1]-l[0], s[1]-s[0]+l[1]-l[0], s, l)


def choose_at(data, spot, w, decision):
    choices=[]
    lower=spot-core.SPEC["short_strike_search_dollars_below"]*U
    for k in data:
        if not lower <= k < spot: continue
        p=market(data,k,w,decision)
        if p is None: continue
        credit,_,spread=p[:3]
        if w*U*core.SPEC["credit_min_pct_width"] <= 100*credit <= w*U*core.SPEC["credit_max_pct_width"] and spread <= core.SPEC["max_combined_quote_width_units"]:
            choices.append((abs(100*credit-w*U*core.SPEC["credit_target_pct_width"]), spread, k))
    return min(choices)[2] if choices else None


def replay_at(data,k,w,decision):
    slip=0
    t=decision+core.SPEC["fill_delay_minutes"]; end=core.SPEC["flat_et_minute"]
    p=market(data,k,w,t)
    if p is None:return {"status":"skip","reason":"no_entry_quote"}
    credit=p[0]-slip
    if not w*U*core.SPEC["credit_min_pct_width"] <= 100*credit <= w*U*core.SPEC["credit_max_pct_width"]:
        return {"status":"skip","reason":"entry_credit_changed"}
    if p[2] > core.SPEC["max_combined_quote_width_units"]:
        return {"status":"skip","reason":"entry_spread_widened"}
    fee=core.SPEC["fee_cents_roundtrip"]
    risk=w*U-credit+fee
    base={"short_units":k,"width":w,"credit_units":credit,"risk_cents":risk,
          "decision_minute_et":decision,"entry_minute_et":t,
          "entry_leg_units":[p[3][0],p[4][1]],"slip_units":0}
    worst=0;best=0;within_dd=0
    for m in range(t,end):
        q=market(data,k,w,m)
        if q is None:return {**base,"status":"unresolved","reason":"missing_open_position_quote","at_minute":m}
        debit=q[1]
        if debit<0:return {**base,"status":"unresolved","reason":"negative_synthetic_debit"}
        mark=credit-debit-fee;worst=min(worst,mark);best=max(best,mark);within_dd=max(within_dd,best-mark)
        reason="stop" if debit>=core.SPEC["stop_debit_multiple"]*credit else "target" if debit*100 <= (100-core.SPEC["profit_capture_pct"])*credit else "time" if m==end-1 else None
        if reason:
            x=market(data,k,w,m+1)
            if x is None:return {**base,"status":"unresolved","reason":"missing_exit_quote"}
            close=x[1]; pnl=credit-close-fee
            return {**base,"status":"trade","reason":reason,"exit_minute_et":m+1,
                    "debit_units":close,"net_cents":pnl,
                    "worst_open_cents":min(worst,pnl),"best_open_cents":max(best,pnl),
                    "within_trade_drawdown_cents":max(within_dd,best-pnl)}
    raise AssertionError("missing_exit")


def reference_at(data,k,w,decision):
    # Independent Decimal arithmetic for the selected path.
    t=decision+1; end=core.SPEC["flat_et_minute"]; fee=D(core.SPEC["fee_cents_roundtrip"])/100
    def legs(m):
        a=data.get(k,{}).get(m); b=data.get(k-w*U,{}).get(m)
        if a is None or b is None:return None
        return tuple(D(x)/U for x in [a[0],a[1],b[0],b[1]])
    e=legs(t)
    if e is None:return ("skip","no_entry_quote")
    credit=e[0]-e[3]
    if not D(w)*D(".25") <= credit <= D(w)*D(".40"):return ("skip","entry_credit_changed")
    if e[1]-e[0]+e[3]-e[2] > D(".10"):return ("skip","entry_spread_widened")
    for m in range(t,end):
        z=legs(m)
        if z is None:return ("unresolved","missing_open_position_quote")
        debit=z[1]-z[2]
        lab="stop" if debit>=2*credit else "target" if debit<=credit/2 else "time" if m==end-1 else None
        if lab:
            f=legs(m+1)
            if f is None:return ("unresolved","missing_exit_quote")
            close=f[1]-f[2]; pnl=(credit-close)*100-fee
            return ("trade",lab,m+1,int(pnl*100))
    raise AssertionError("oracle_missing_exit")


def agree(rec, oracle):
    got=(rec["status"],rec["reason"])
    if rec["status"]=="trade": got+=(rec["exit_minute_et"],rec["net_cents"])
    if got != oracle: raise AssertionError(("independent_disagreement",got,oracle))


def first_trade(stock,data):
    d=core.SPEC["decision_et_minute"]
    eff=efficiency_at(stock,d)
    if eff < MIN_EFF:return None,{"reason":"efficiency","eff":str(eff)}
    k=choose_at(data,spot_at(stock,d),2,d)
    if k is None:return None,{"reason":"no_candidate","eff":str(eff)}
    rec=replay_at(data,k,2,d);agree(rec,reference_at(data,k,2,d))
    return rec,{"eff":str(eff),"decision":d}


def second_trade(stock,data,first,mode):
    if not first or first.get("status")!="trade" or first["reason"]=="time":return None,{"reason":"first_not_rearmed"}
    start=((first["exit_minute_et"]+COOLDOWN_MINUTES+4)//5)*5
    seen_below=False
    for d in range(start, LATEST_SECOND_DECISION+1, RECHECK_STEP):
        eff=efficiency_at(stock,d)
        if eff < MIN_EFF:
            seen_below=True
            continue
        if mode=="rearm" and not seen_below:
            continue
        k=choose_at(data,spot_at(stock,d),2,d)
        if k is None:continue
        rec=replay_at(data,k,2,d);agree(rec,reference_at(data,k,2,d))
        if rec["status"]=="skip":continue
        return rec,{"eff":str(eff),"decision":d,"seen_below":seen_below}
    return None,{"reason":"no_fresh_second_setup","seen_below":seen_below}


def summarize(days, daily, mode):
    eq=core.SPEC["initial_equity_cents"];peak=eq;dd=0;profit=0;n=0;w=0;l=0;stops=0;second=0;second_w=0;second_l=0;worst=0;months=set();reject=Counter()
    for day in days:
        months.add(day[:7])
        recs=daily[day][mode]
        for idx,tr in enumerate(recs):
            if tr is None:continue
            if tr["status"]!="trade":reject[tr["reason"]]+=1;continue
            # Same 10% risk-budget gate, evaluated before each sequential position.
            if tr["risk_cents"]*100 > eq*core.SPEC["position_risk_pct"]:
                reject["risk_budget"]+=1;continue
            n+=1
            if idx==1:second+=1
            pnl=tr["net_cents"];profit+=pnl;worst=min(worst,pnl)
            if pnl>0:w+=1
            elif pnl<0:l+=1
            if idx==1 and pnl>0:second_w+=1
            elif idx==1 and pnl<0:second_l+=1
            if tr["reason"]=="stop":stops+=1
            # intratrade economic drawdown
            dd=max(dd, peak-(eq+tr["worst_open_cents"]))
            eq+=pnl;peak=max(peak,eq);dd=max(dd,peak-eq)
    bills=len(months)*core.SPEC["monthly_bill_cents"]
    return {"mode":mode,"sessions":len(days),"trades":n,"wins":w,"losses":l,
            "win_rate":round(100*w/n,1) if n else 0,
            "second_entries":second,"second_wins":second_w,"second_losses":second_l,
            "stops":stops,"trading_net":core.money(profit),"subscription":core.money(bills),
            "customer_net":core.money(profit-bills),"ending_equity":core.money(eq),
            "max_drawdown":core.money(dd),"worst_trade":core.money(worst),
            "rejections":dict(reject),"qualification":"RETROSPECTIVE_ONLY"}


def execute():
    core.STATE["stage"]="running";feed=core.Feed();days=core.session_days();daily={};checked=0
    spec_extra={"min_efficiency":str(MIN_EFF),"latest_second_decision_et_minute":LATEST_SECOND_DECISION,
                "cooldown_minutes":COOLDOWN_MINUTES,"second_modes":["recheck","rearm"],"entries_per_day_max":2}
    core.emit("two_entry_spec",configuration=core.SPEC,extra=spec_extra,
              sha256=hashlib.sha256(json.dumps({"spec":core.SPEC,"extra":spec_extra},sort_keys=True).encode()).hexdigest())
    try:
        for day in days:
            p={"symbol":"SPY","date":day,"interval":"1m","start_time":"09:30:00","end_time":"15:45:00","venue":"utp_cta"}
            fp=feed.get("/v3/stock/history/ohlc",p)
            with fp.open() as f: stock=full_stock_rows(csv.DictReader(f),day)
            p={"symbol":"SPY","date":day,"expiration":day,"right":"put","strike":"*","interval":"1m","start_time":"12:00:00","end_time":"15:45:00"}
            fp=feed.get("/v3/option/history/quote",p)
            with fp.open() as f: data,cov=parse_all_options(csv.DictReader(f),day)
            first,meta1=first_trade(stock,data)
            if first is not None:checked+=1
            second_recheck,meta2=second_trade(stock,data,first,"recheck")
            if second_recheck is not None:checked+=1
            second_rearm,meta3=second_trade(stock,data,first,"rearm")
            if second_rearm is not None:checked+=1
            daily[day]={
                "one_entry":[first],
                "two_recheck":[first,second_recheck],
                "two_rearm":[first,second_rearm],
            }
            core.emit("two_entry_day",day=day,coverage=cov,
                      first=first,first_meta=meta1,
                      second_recheck=second_recheck,second_recheck_meta=meta2,
                      second_rearm=second_rearm,second_rearm_meta=meta3)
        totals=[summarize(days,daily,m) for m in ["one_entry","two_recheck","two_rearm"]]
        for x in totals:core.emit("two_entry_summary",**x)
        core.STATE["stage"]="complete"
        core.emit("two_entry_complete",days=len(days),provider_requests=feed.n,
                  oracle_comparisons=checked,prior_inputs=0,raw_exported=False)
    except Exception as e:
        core.STATE["stage"]="failed";core.emit("two_entry_failed",kind=type(e).__name__,
            reason=str(e)[:400],completed_days=len(daily),provider_requests=feed.n)


if __name__=="__main__":
    if os.getenv("FLAME_FRESH_MODE")=="two-entry-102d":
        threading.Thread(target=execute,daemon=True).start()
    HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
