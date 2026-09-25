"""Portfolio safety repair: Research hard-stop -> EBB session stand-down.
Uses the already-qualified Research exit (TP25, 2x stop, +$10 breakeven arm)
and unchanged EBB rules. The circuit breaker is causal: it only fires when
Research has already exited by hard stop before EBB's 14:05 ET decision.
Research/EBB entry logic is otherwise unchanged. 10% governor remains frozen.
"""
import os, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from http.server import HTTPServer
import flame_repaired_research_ebb_shared as shared

core=shared.core
core.SPEC.update({
 "id":"flame-research-stop-ebb-standdown-20260925",
 "scope":"qualified Research + unchanged EBB; test causal same-day stop circuit breaker",
 "kelly":False,
})

def max_losing_streak(seq):
 best=cur=0
 for p in seq:
  if p<0:cur+=1;best=max(best,cur)
  else:cur=0
 return best

def simulate(research, standdown=False, start=None, end=None):
 ebb={d:{"net_cents":p,"risk_cents":r,"entry_minute_et":en,"exit_minute_et":ex}
      for d,p,r,en,ex in shared.EBB
      if (start is None or d>=start) and (end is None or d<=end)}
 rr={d:r for d,r in research.items() if (start is None or d>=start) and (end is None or d<=end)}
 days=sorted(set(ebb)|set(rr))
 eq=200000;peak=eq;dd=0
 accepted=[];blocked=Counter();standdowns=[];both_loss=[]
 epnl=Counter();en=Counter()
 for day in days:
  r=rr.get(day);e=ebb.get(day);r_active=False;research_stopped_pre_ebb=False
  if r and r.get("status")=="trade":
   if r["risk_cents"]*100<=eq*10:r_active=True
   else:blocked["research_risk"]+=1
  if r_active and r["exit_minute_et"]<=845:
   eq+=r["net_cents"];epnl["research"]+=r["net_cents"];en["research"]+=1
   accepted.append((day,"research",r["net_cents"]))
   peak=max(peak,eq);dd=max(dd,peak-eq)
   research_stopped_pre_ebb=(r.get("reason")=="stop")
   r_active=False
  e_active=False
  if e:
   if standdown and research_stopped_pre_ebb:
    blocked["ebb_after_research_stop"]+=1;standdowns.append({"day":day,"ebb_net_cents":e["net_cents"]})
   else:
    openrisk=(r["risk_cents"] if r_active else 0)+e["risk_cents"]
    if openrisk*100<=eq*10:e_active=True
    else:blocked["ebb_portfolio_risk" if r_active else "ebb_risk"]+=1
  if r_active:
   eq+=r["net_cents"];epnl["research"]+=r["net_cents"];en["research"]+=1
   accepted.append((day,"research",r["net_cents"]))
   peak=max(peak,eq);dd=max(dd,peak-eq)
  if e_active:
   eq+=e["net_cents"];epnl["ebb"]+=e["net_cents"];en["ebb"]+=1
   accepted.append((day,"ebb",e["net_cents"]))
   peak=max(peak,eq);dd=max(dd,peak-eq)
  vals=[p for d,eng,p in accepted if d==day]
  if len(vals)>=2 and all(p<0 for p in vals):both_loss.append(day)
 rs=[p for d,eng,p in accepted if eng=="research"];es=[p for d,eng,p in accepted if eng=="ebb"];alls=[p for d,eng,p in accepted]
 return {
  "mode":"research_stop_standdown" if standdown else "standard_10pct",
  "start":start,"end":end,"trade_active_dates":len(days),
  "trading_net":round((eq-200000)/100,2),"ending_equity":round(eq/100,2),
  "max_closed_equity_drawdown":round(dd/100,2),
  "research_trades":en["research"],"research_pnl":round(epnl["research"]/100,2),
  "ebb_trades":en["ebb"],"ebb_pnl":round(epnl["ebb"]/100,2),
  "blocked":dict(blocked),"standdowns":[{"day":x["day"],"ebb_pnl":round(x["ebb_net_cents"]/100,2)} for x in standdowns],
  "both_loss_days":both_loss,
  "research_max_losing_streak":max_losing_streak(rs),
  "ebb_max_losing_streak":max_losing_streak(es),
  "portfolio_max_losing_trade_streak":max_losing_streak(alls),
 }

def execute():
 core.STATE["stage"]="running";out={};errors=[]
 workers=max(1,min(int(os.getenv("FLAME_STANDDOWN_WORKERS","3")),6))
 core.emit("standdown_spec",research_entries=len(shared.RESEARCH),ebb_trades=len(shared.EBB),workers=workers,
  rule="If qualified Research exits via hard stop at or before 14:05 ET, EBB does not enter that session.",
  governor_pct=10,kelly=False,live_changed=False)
 with ThreadPoolExecutor(max_workers=workers) as ex:
  futs={ex.submit(shared.replay_one,p,t):(p,t[0]) for p,t in shared.RESEARCH};done=0
  for fut in as_completed(futs):
   day,tr,err=fut.result();done+=1
   if tr:out[day]=tr
   if err:errors.append(err);core.emit("standdown_day_error",**err)
   if done%10==0 or done==len(shared.RESEARCH):core.emit("standdown_progress",completed=done,total=len(shared.RESEARCH),errors=len(errors))
 if errors:
  core.STATE["stage"]="failed";core.emit("standdown_failed",errors=errors);return
 periods={
  "dev":("2025-01-01","2025-05-30"),
  "ext":("2025-06-02","2026-08-31"),
  "full":(None,None),
 }
 results={}
 for period,(start,end) in periods.items():
  results[period]={}
  for mode in [False,True]:
   z=simulate(out,standdown=mode,start=start,end=end)
   results[period][z["mode"]]=z
   core.emit("standdown_result",period=period,**z)
 checks={
  "development_net_not_worse":results["dev"]["research_stop_standdown"]["trading_net"]>=results["dev"]["standard_10pct"]["trading_net"],
  "extension_net_not_worse":results["ext"]["research_stop_standdown"]["trading_net"]>=results["ext"]["standard_10pct"]["trading_net"],
  "full_net_improves":results["full"]["research_stop_standdown"]["trading_net"]>results["full"]["standard_10pct"]["trading_net"],
  "full_drawdown_not_worse":results["full"]["research_stop_standdown"]["max_closed_equity_drawdown"]<=results["full"]["standard_10pct"]["max_closed_equity_drawdown"],
  "double_loss_days_not_more":len(results["full"]["research_stop_standdown"]["both_loss_days"])<=len(results["full"]["standard_10pct"]["both_loss_days"]),
 }
 qualified=all(checks.values())
 core.STATE["stage"]="complete"
 core.emit("standdown_complete",qualified=qualified,checks=checks,results=results,errors=0)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="research-stop-ebb-standdown":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
