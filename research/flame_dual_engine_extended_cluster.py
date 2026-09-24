"""Extended dual-engine Flame study with separate loss-cluster diagnostics.

Frozen engines:
- Research: 12:00 ET decision, efficiency >= 0.30, $2-wide SPY put credit spread,
  50% target, 2x stop, 15:45 ET final exit.
- EBB: 14:05 ET decision, prior-session VIX decay <= 0.80, short $1 below SPY,
  $2 wide, no stop/target, settle at official-session close.
- Shared portfolio governor: 10% total defined open risk on current account equity.

Study window: 2025-06-02 through 2026-08-31.
Only standard full sessions are included. Known half-days are excluded because EBB's
14:05 ET decision occurs after those sessions close and Research's normal 15:45 exit
would not exist.

Research only. No live trading imports or writes.
"""
from __future__ import annotations
import csv, json, os, threading
from collections import Counter
from http.server import HTTPServer
import flame_dual_engine_portfolio as old

core=old.core
base=old.base
U=old.U

EXCLUDED = [
 "2025-06-19",              # Juneteenth
 "2025-07-03","2025-07-04", # half-day + Independence Day
 "2025-09-01",              # Labor Day
 "2025-11-27","2025-11-28", # Thanksgiving + half-day
 "2025-12-24","2025-12-25", # half-day + Christmas
 "2026-01-01","2026-01-19",
 "2026-02-16","2026-04-03",
 "2026-05-25","2026-06-19","2026-07-03",
]
core.SPEC.update({
 "id":"flame-dual-engine-extended-cluster-20260924",
 "start":"2025-06-02",
 "end":"2026-08-31",
 "closures":EXCLUDED,
 "expected_sessions":311,
 "max_requests":1600,
 "deadline_seconds":7200,
 "scope":"frozen dual-engine extension with 10% governor and separate loss-cluster diagnostics",
 "no_saved_price_inputs":True,
 "no_previous_trade_inputs":True,
})

def money(x): return core.money(int(x))

def accepted_portfolio(days,daily,cap_pct=10):
 """Correct chronological accounting and admission decisions."""
 eq=core.SPEC["initial_equity_cents"]; peak=eq; maxdd=0; profit=0
 accepted=[]; blocked=Counter()
 for day in days:
  r=daily[day]["research"]; e=daily[day]["ebb"]
  active_r=False
  # Research admission at noon.
  if r and r.get("status")=="trade":
   if r["risk_cents"]*100 <= eq*cap_pct:
    active_r=True
   else:
    blocked["research_risk"]+=1
  # Research may close before EBB decision; realize it before EBB sizing.
  if active_r and r["exit_minute_et"] <= old.EBB_DECISION:
   accepted.append((day,"research",r["exit_minute_et"],r))
   eq += r["net_cents"]; profit += r["net_cents"]
   peak=max(peak,eq); maxdd=max(maxdd,peak-eq)
   active_r=False
  # EBB admission at 14:05 ET uses then-current equity and any still-open Research risk.
  accept_e=False
  if e and e.get("status")=="trade":
   openrisk=(r["risk_cents"] if active_r else 0)+e["risk_cents"]
   if openrisk*100 <= eq*cap_pct:
    accept_e=True
   else:
    blocked["ebb_portfolio_risk"]+=1
  # Close events must be processed chronologically.
  close_events=[]
  if active_r:
   close_events.append(("research",r["exit_minute_et"],r))
  if accept_e:
   close_events.append(("ebb",e["exit_minute_et"],e))
  close_events.sort(key=lambda x:x[1])
  for engine,minute,tr in close_events:
   accepted.append((day,engine,minute,tr))
   eq += tr["net_cents"]; profit += tr["net_cents"]
   peak=max(peak,eq); maxdd=max(maxdd,peak-eq)
 bills=core.SPEC["monthly_bill_cents"]*len(set(d[:7] for d in days))
 return {
  "accepted":accepted,"blocked":dict(blocked),"trading_net_cents":profit,
  "customer_net_cents":profit-bills,"subscription_cents":bills,
  "ending_equity_cents":eq,"max_closed_equity_drawdown_cents":maxdd
 }

def streaks(trades):
 # trades sorted chronologically by trade date for one engine
 out=[]; cur=None
 for x in trades:
  typ="W" if x["pnl_cents"]>0 else "L" if x["pnl_cents"]<0 else "F"
  if typ=="F": continue
  if not cur or cur["type"]!=typ:
   if cur: out.append(cur)
   cur={"type":typ,"count":1,"start":x["day"],"end":x["day"],"pnl_cents":x["pnl_cents"]}
  else:
   cur["count"]+=1;cur["end"]=x["day"];cur["pnl_cents"]+=x["pnl_cents"]
 if cur:out.append(cur)
 return out

def bin_eff(v):
 if v<0.40:return "0.30-0.40"
 if v<0.50:return "0.40-0.50"
 if v<0.60:return "0.50-0.60"
 return "0.60+"

def bin_vix(v):
 if v is None:return "unknown"
 if v<0.50:return "<0.50"
 if v<0.60:return "0.50-0.60"
 if v<0.70:return "0.60-0.70"
 return "0.70-0.80"

def bin_credit(cents):
 if cents<2500:return "<$0.25"
 if cents<4000:return "$0.25-$0.39"
 if cents<6000:return "$0.40-$0.59"
 return "$0.60+"

def summarize_bucket(rows,keyfn):
 d={}
 for x in rows:
  k=keyfn(x); z=d.setdefault(k,{"trades":0,"wins":0,"losses":0,"pnl_cents":0})
  z["trades"]+=1;z["pnl_cents"]+=x["pnl_cents"]
  if x["pnl_cents"]>0:z["wins"]+=1
  elif x["pnl_cents"]<0:z["losses"]+=1
 for z in d.values():
  z["pnl"]=money(z.pop("pnl_cents"))
  z["win_rate"]=round(100*z["wins"]/z["trades"],1) if z["trades"] else 0
 return d

def rolling_loss_cluster(rows,window=5):
 # Trade-sequence clusters, not calendar bars.
 best={"losses":0,"start":None,"end":None,"pnl_cents":0}
 for i in range(max(0,len(rows)-window+1)):
  w=rows[i:i+window]; n=sum(1 for x in w if x["pnl_cents"]<0); p=sum(x["pnl_cents"] for x in w)
  if n>best["losses"] or (n==best["losses"] and p<best["pnl_cents"]):
   best={"losses":n,"start":w[0]["day"],"end":w[-1]["day"],"pnl_cents":p}
 best["pnl"]=money(best.pop("pnl_cents"))
 return best

def engine_cluster(days,daily,key):
 rows=[]
 for day in days:
  t=daily[day][key]
  if not t or t.get("status")!="trade": continue
  meta=daily[day][key+"_meta"]
  row={"day":day,"pnl_cents":t["net_cents"],"reason":t["reason"],
       "credit_cents":t["credit_units"],"risk_cents":t["risk_cents"]}
  if key=="research":
   row["efficiency"]=float(meta["eff"])
   row["hold_minutes"]=t["exit_minute_et"]-t["entry_minute_et"]
   row["best_open_cents"]=t.get("best_open_cents",0)
   row["worst_open_cents"]=t.get("worst_open_cents",0)
  else:
   row["vix_ratio"]=meta.get("ratio")
   row["intrinsic_cents"]=t.get("intrinsic_units",0)
  rows.append(row)
 losses=[x for x in rows if x["pnl_cents"]<0]; wins=[x for x in rows if x["pnl_cents"]>0]
 ss=streaks(rows); ls=[x for x in ss if x["type"]=="L"]; ws=[x for x in ss if x["type"]=="W"]
 months=summarize_bucket(rows,lambda x:x["day"][:7])
 result={
  "engine":key,"trades":len(rows),"wins":len(wins),"losses":len(losses),
  "win_rate":round(100*len(wins)/len(rows),1) if rows else 0,
  "trading_net":money(sum(x["pnl_cents"] for x in rows)),
  "loss_total":money(sum(x["pnl_cents"] for x in losses)),
  "avg_win":money(sum(x["pnl_cents"] for x in wins)/len(wins)) if wins else 0,
  "avg_loss":money(sum(x["pnl_cents"] for x in losses)/len(losses)) if losses else 0,
  "longest_loss_streak":max(ls,key=lambda x:x["count"]) if ls else None,
  "longest_win_streak":max(ws,key=lambda x:x["count"]) if ws else None,
  "worst_5_trade_window":rolling_loss_cluster(rows,5),
  "by_month":months,
  "worst_losses":[{**x,"pnl":money(x["pnl_cents"])} for x in sorted(losses,key=lambda x:x["pnl_cents"])[:12]],
 }
 if key=="research":
  result["by_efficiency"]=summarize_bucket(rows,lambda x:bin_eff(x["efficiency"]))
  result["by_exit_reason"]=summarize_bucket(rows,lambda x:x["reason"])
  result["loss_best_excursion"]={
   "zero_or_less":sum(1 for x in losses if x.get("best_open_cents",0)<=0),
   "le_10_dollars":sum(1 for x in losses if x.get("best_open_cents",0)<=1000),
   "le_20_dollars":sum(1 for x in losses if x.get("best_open_cents",0)<=2000),
  }
 else:
  result["by_vix_ratio"]=summarize_bucket(rows,lambda x:bin_vix(x.get("vix_ratio")))
  result["by_credit"]=summarize_bucket(rows,lambda x:bin_credit(x["credit_cents"]))
 return result,rows

def overlap_cluster(days,daily):
 same_signal=[]; both_trade=[]; both_loss=[]
 for d in days:
  r=daily[d]["research"]; e=daily[d]["ebb"]
  rt=bool(r and r.get("status")=="trade"); et=bool(e and e.get("status")=="trade")
  if rt and et:
   both_trade.append(d)
   if r["net_cents"]<0 and e["net_cents"]<0: both_loss.append(d)
 return {"both_trade_days":len(both_trade),"both_loss_days":len(both_loss),
         "both_loss_dates":both_loss[:30]}

def execute():
 core.STATE["stage"]="running"; feed=core.Feed(); days=core.session_days(); daily={}
 try:
  if len(days)!=core.SPEC["expected_sessions"]:
   raise core.DataError("session_count:"+str(len(days)))
  vix,vix_sha=old.get_vix()
  core.emit("dual_ext_spec",configuration=core.SPEC,vix_source=old.VIX_URL,vix_sha256=vix_sha,
   research_rules={"decision_et":720,"efficiency_min":0.30,"target_pct":50,"stop_mult":2,"width":2},
   ebb_rules={"decision_et":845,"vix_decay_ceiling":0.80,"otm_dollars":1,"width":2,"exit":"close_settlement"},
   portfolio_cap_pct=10,live_changed=False)
  for i,day in enumerate(days,1):
   stock=old.get_stock(feed,day)
   df=base.DayFeed(feed,day,stock)
   r,rm=old.research_trade(df)
   vg=old.vix_gate(vix,day)
   e,em=old.ebb_trade(df,vg)
   daily[day]={"research":r,"research_meta":rm,"ebb":e,"ebb_meta":em}
   core.emit("dual_ext_day",day=day,index=i,research=r,research_meta=rm,ebb=e,ebb_meta=em)
  rc,rr=engine_cluster(days,daily,"research")
  ec,er=engine_cluster(days,daily,"ebb")
  core.emit("dual_ext_cluster",**rc)
  core.emit("dual_ext_cluster",**ec)
  port=accepted_portfolio(days,daily,10)
  core.emit("dual_ext_portfolio",
   sessions=len(days),trades=len(port["accepted"]),blocked=port["blocked"],
   trading_net=money(port["trading_net_cents"]),
   subscription=money(port["subscription_cents"]),
   customer_net=money(port["customer_net_cents"]),
   ending_equity=money(port["ending_equity_cents"]),
   max_closed_equity_drawdown=money(port["max_closed_equity_drawdown_cents"]),
   overlap=overlap_cluster(days,daily),qualification="RETROSPECTIVE_ONLY")
  core.STATE["stage"]="complete"
  core.emit("dual_ext_complete",days=len(days),provider_requests=feed.n,prior_inputs=0,vix_sha256=vix_sha)
 except Exception as e:
  core.STATE["stage"]="failed"
  core.emit("dual_ext_failed",kind=type(e).__name__,reason=str(e)[:600],completed_days=len(daily),provider_requests=feed.n)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-extended-cluster":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
