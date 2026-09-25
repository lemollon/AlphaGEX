"""Research profit-lock repair on frozen entries.
Purpose: test whether the dominant failure mode is profitable excursion followed by reversal.
Entries remain frozen. EBB is unchanged. Research-only retrospective test.
"""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from decimal import Decimal as D
from http.server import HTTPServer
import flame_research_exit_repair as repair
import flame_two_entry_optimized as base
import flame_research_frozen28_exit_repair as devset
import flame_research_frozen57_exit_repair as extset

core=repair.core
U=core.U
core.SPEC.update({
 "id":"flame-research-profit-lock-repair-20260925",
 "scope":"frozen Research entries; 25pct target + 2x stop with preregistered profit-lock overlays",
 "no_saved_price_inputs":True,
 "no_previous_trade_inputs":False,
})
VARIANTS={
 "tp25_stop2x":{"arm_cents":None,"lock_cents":None},
 "be_after_10":{"arm_cents":1000,"lock_cents":0},
 "be_after_15":{"arm_cents":1500,"lock_cents":0},
 "lock5_after_15":{"arm_cents":1500,"lock_cents":500},
 "lock10_after_20":{"arm_cents":2000,"lock_cents":1000},
}

def replay_lock(df,k,arm_cents,lock_cents):
 t=721; end=core.SPEC["flat_et_minute"]
 short=df.leg(k,t); long=df.leg(k-2*U,t)
 def mk(m):
  s=short.get(m); l=long.get(m)
  if s is None or l is None:return None
  return (s[0]-l[1],s[1]-l[0],s[1]-s[0]+l[1]-l[0])
 p=mk(t)
 if p is None:return {"status":"skip","reason":"no_entry_quote"}
 credit=p[0]
 if not 2*U*core.SPEC["credit_min_pct_width"] <= 100*credit <= 2*U*core.SPEC["credit_max_pct_width"]:
  return {"status":"skip","reason":"entry_credit_changed"}
 if p[2]>core.SPEC["max_combined_quote_width_units"]:
  return {"status":"skip","reason":"entry_spread_widened"}
 fee=core.SPEC["fee_cents_roundtrip"]; risk=2*U-credit+fee
 rb={"short_units":k,"width":2,"credit_units":credit,"risk_cents":risk,"decision_minute_et":720,"entry_minute_et":t}
 armed=False; worst=0; best=0; within=0
 for m in range(t,end):
  q=mk(m)
  if q is None:return {**rb,"status":"unresolved","reason":"missing_open_position_quote","at_minute":m}
  debit=q[1]
  if debit<0:return {**rb,"status":"unresolved","reason":"negative_synthetic_debit"}
  mark=credit-debit-fee
  worst=min(worst,mark); best=max(best,mark); within=max(within,best-mark)
  if arm_cents is not None and mark>=arm_cents: armed=True
  hit_stop=debit>=2*credit
  hit_target=debit*100<=75*credit
  hit_lock=armed and lock_cents is not None and mark<=lock_cents
  reason="stop" if hit_stop else "target" if hit_target else "profit_lock" if hit_lock else "time" if m==end-1 else None
  if reason:
   x=mk(m+1)
   if x is None:return {**rb,"status":"unresolved","reason":"missing_exit_quote"}
   close=x[1]; pnl=credit-close-fee
   return {**rb,"status":"trade","reason":reason,"exit_minute_et":m+1,"debit_units":close,"net_cents":pnl,
    "worst_open_cents":min(worst,pnl),"best_open_cents":max(best,pnl),
    "within_trade_drawdown_cents":max(within,best-pnl),"lock_armed":armed}
 raise AssertionError("missing_exit")

def run_one(period,item):
 day,k,eff=item; last=None
 for attempt in range(1,5):
  feed=core.Feed()
  try:
   df=base.DayFeed(feed,day,{})
   variants={name:replay_lock(df,k,**cfg) for name,cfg in VARIANTS.items()}
   if attempt>1:core.emit("profit_lock_recovered",period=period,day=day,attempt=attempt)
   return {"period":period,"day":day,"eff":float(eff),"variants":variants},None
  except Exception as exc:
   last=exc
   if "transport_failed" not in str(exc) or attempt==4:break
   core.emit("profit_lock_retry",period=period,day=day,attempt=attempt,reason=str(exc)[:240])
   time.sleep(2*attempt)
 return None,{"period":period,"day":day,"kind":type(last).__name__,"reason":str(last)[:240]}

def summarize(rows,name):
 eq=200000;peak=eq;dd=0;profit=0;accepted=[];rej=Counter()
 for row in sorted(rows,key=lambda x:x["day"]):
  tr=row["variants"].get(name)
  if not tr or tr.get("status")!="trade":
   rej[(tr or {}).get("reason","not_trade")]+=1;continue
  if tr["risk_cents"]*100>eq*core.SPEC["position_risk_pct"]:
   rej["risk_budget"]+=1;continue
  accepted.append({"day":row["day"],**tr})
  dd=max(dd,peak-(eq+tr.get("worst_open_cents",0)))
  eq+=tr["net_cents"];profit+=tr["net_cents"];peak=max(peak,eq);dd=max(dd,peak-eq)
 wins=[x for x in accepted if x["net_cents"]>0]; losses=[x for x in accepted if x["net_cents"]<0]
 reasons=Counter(x["reason"] for x in accepted)
 months=defaultdict(int)
 for x in accepted:months[x["day"][:7]]+=x["net_cents"]
 money=lambda c:round(c/100,2)
 return {"variant":name,"trades":len(accepted),"wins":len(wins),"losses":len(losses),
  "win_rate":round(100*len(wins)/len(accepted),1) if accepted else 0,
  "trading_net":money(profit),"max_observed_drawdown":money(dd),
  "worst_trade":money(min((x["net_cents"] for x in accepted),default=0)),
  "avg_win":money(sum(x["net_cents"] for x in wins)/len(wins)) if wins else 0,
  "avg_loss":money(sum(x["net_cents"] for x in losses)/len(losses)) if losses else 0,
  "exit_reasons":dict(reasons),"rejections":dict(rej),
  "months":{k:money(v) for k,v in sorted(months.items())}}

def execute():
 core.STATE["stage"]="running"; rows=[];errors=[]
 jobs=[("dev",t) for t in devset.TRADES]+[("ext",t) for t in extset.TRADES]
 workers=max(1,min(int(os.getenv("FLAME_LOCK_WORKERS","3")),6))
 core.emit("profit_lock_spec",dev_entries=len(devset.TRADES),ext_entries=len(extset.TRADES),
  variants=VARIANTS,acceptance="dev nonnegative; ext positive; beats tp25_stop2x ext; ext drawdown and worst trade no worse",live_changed=False)
 with ThreadPoolExecutor(max_workers=workers) as ex:
  futs={ex.submit(run_one,p,t):(p,t[0]) for p,t in jobs};done=0
  for fut in as_completed(futs):
   row,err=fut.result();done+=1
   if row:rows.append(row)
   if err:errors.append(err);core.emit("profit_lock_day_error",**err)
   if done%10==0 or done==len(jobs):core.emit("profit_lock_progress",completed=done,total=len(jobs),errors=len(errors))
 if errors:
  core.STATE["stage"]="failed";core.emit("profit_lock_failed",errors=errors);return
 dev=[r for r in rows if r["period"]=="dev"];ext=[r for r in rows if r["period"]=="ext"]
 ds={n:summarize(dev,n) for n in VARIANTS}; es={n:summarize(ext,n) for n in VARIANTS}
 for n in VARIANTS:core.emit("profit_lock_result",period="dev",**ds[n]);core.emit("profit_lock_result",period="ext",**es[n])
 baseext=es["tp25_stop2x"];qualified=[]
 for n in VARIANTS:
  if n=="tp25_stop2x":continue
  checks={"development_nonnegative":ds[n]["trading_net"]>=0,"extension_positive":es[n]["trading_net"]>0,
   "extension_beats_tp25":es[n]["trading_net"]>baseext["trading_net"],
   "drawdown_not_worse":es[n]["max_observed_drawdown"]<=baseext["max_observed_drawdown"],
   "worst_trade_not_worse":es[n]["worst_trade"]>=baseext["worst_trade"]}
  core.emit("profit_lock_candidate_check",variant=n,checks=checks)
  if all(checks.values()):qualified.append(n)
 qualified.sort(key=lambda n:es[n]["trading_net"],reverse=True)
 core.STATE["stage"]="complete"
 core.emit("profit_lock_complete",qualified=qualified,best=qualified[0] if qualified else None,dev=ds,ext=es,errors=0)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="profit-lock-repair":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
