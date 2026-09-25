"""Shared-account validation: repaired Research + unchanged EBB.
Research = frozen entries, 25% target, 2x stop, breakeven lock armed at +$10.
EBB = exact validated cleanroom ledger, unchanged.
Shared account starts $2,000; 10% open-risk governor; chronological accounting.
Research only changes are the qualified exit repair. No Kelly. No live changes.
"""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from http.server import HTTPServer
import flame_research_profit_lock_repair as lock
import flame_research_frozen28_exit_repair as devset
import flame_research_frozen57_exit_repair as extset
import flame_two_entry_optimized as base

core=lock.core
core.SPEC.update({
 "id":"flame-repaired-research-ebb-shared-account-20260925",
 "scope":"qualified be_after_10 Research + unchanged EBB on one $2k account",
 "initial_equity_cents":200000,
 "position_risk_pct":10,
 "no_saved_price_inputs":True,
 "no_previous_trade_inputs":False,
 "kelly":False,
})
EBB=[["2025-01-02",5940,14060,846,960],["2025-01-03",2740,17260,846,960],["2025-01-06",1740,18260,846,960],["2025-01-07",-10160,17360,846,960],["2025-01-08",3140,16860,846,960],["2025-01-10",-10560,15660,846,960],["2025-01-13",3140,16860,846,960],["2025-01-14",3040,16960,846,960],["2025-01-15",2840,17160,846,960],["2025-01-16",3140,16860,846,960],["2025-01-17",-1160,16860,846,960],["2025-01-21",2640,17360,846,960],["2025-01-22",840,19160,846,960],["2025-01-23",1840,18160,846,960],["2025-01-24",1340,18660,846,960],["2025-01-27",3040,16960,846,960],["2025-02-07",2440,17560,846,960],["2025-03-17",2340,17660,846,960],["2025-03-18",4340,15660,846,960],["2025-03-19",6140,13860,846,960],["2025-03-20",3240,16760,846,960],["2025-03-21",4240,15760,846,960],["2025-03-24",1640,18360,846,960],["2025-03-25",2140,17860,846,960],["2025-03-26",4140,15860,846,960],["2025-03-27",2640,17360,846,960],["2025-03-28",3640,16360,846,960],["2025-03-31",5640,14360,846,960],["2025-04-01",3440,16560,846,960],["2025-04-02",6340,13660,846,960],["2025-04-03",-13360,13360,846,960],["2025-04-10",-5460,12460,846,960],["2025-04-11",7540,12260,846,960],["2025-04-14",5140,14860,846,960],["2025-04-15",5540,14460,846,960],["2025-04-16",5040,14960,846,960],["2025-04-17",-15560,15560,846,960],["2025-04-21",5540,14460,846,960],["2025-04-22",3640,16360,846,960],["2025-04-23",-10460,14560,846,960],["2025-04-24",5340,14660,846,960],["2025-04-25",5540,14460,846,960],["2025-04-28",4440,15560,846,960],["2025-04-29",3440,16560,846,960],["2025-04-30",4840,15160,846,960],["2025-05-01",-10760,15360,846,960],["2025-05-02",-860,17060,846,960],["2025-05-05",-12660,17960,846,960],["2025-05-06",3340,16660,846,960],["2025-05-07",7440,12560,846,960],["2025-05-08",-15860,15860,846,960],["2025-05-09",3640,16360,846,960],["2025-05-12",3340,16660,846,960],["2025-05-13",40,18060,846,960],["2025-05-14",1340,18660,846,960],["2025-05-15",3740,16260,846,960],["2025-05-16",2340,17660,846,960],["2025-05-19",1240,18760,846,960],["2025-05-20",1840,18160,846,960],["2025-05-21",-5860,15460,846,960],["2025-05-22",-6760,17060,846,960],["2025-05-23",-5959,17560,846,960],["2025-05-28",-8560,15660,846,960],["2025-05-29",3140,16860,846,960],["2025-05-30",5540,14460,846,960],["2025-06-02",1840,18160,846,960],["2025-06-03",2940,17060,846,960],["2025-06-04",-8760,17760,846,960],["2025-06-05",-6460,16560,846,960],["2025-06-09",-2159,17760,846,960],["2025-06-10",2740,17260,846,960],["2025-06-11",3240,16760,846,960],["2025-06-12",1540,18460,846,960],["2025-06-25",1340,18660,846,960],["2025-06-27",1540,18460,846,960],["2025-06-30",2340,17660,846,960],["2025-07-01",1040,18960,846,960],["2025-07-07",1740,18260,846,960],["2025-07-09",1440,18560,846,960],["2025-07-10",140,18260,846,960],["2025-07-11",940,19060,846,960],["2025-07-14",840,19160,846,960],["2025-07-15",-16560,17760,846,960],["2025-07-16",940,19060,846,960],["2025-08-11",1240,17060,846,960],["2025-08-13",1840,18160,846,960],["2025-08-14",2440,17560,846,960],["2025-08-15",1040,18960,846,960],["2025-08-18",1640,18360,846,960],["2025-08-19",1440,18560,846,960],["2025-08-20",3240,16760,846,960],["2025-08-21",2540,17460,846,960],["2025-08-26",840,19160,846,960],["2025-08-27",4840,15160,846,960],["2025-08-29",1840,18160,846,960],["2025-10-21",840,19160,846,960],["2025-10-22",3040,16960,846,960],["2025-10-23",840,19160,846,960],["2025-10-24",940,19060,846,960],["2025-10-28",1340,18460,846,960],["2025-10-29",6140,13860,846,960],["2025-10-30",-15760,15760,846,960],["2025-10-31",4240,15760,846,960],["2025-11-03",1440,18560,846,960],["2025-11-04",-1360,14860,846,960],["2025-11-05",-13660,18760,846,960],["2025-11-06",-4760,17460,846,960],["2025-11-07",4240,15760,846,960],["2025-11-10",1040,18960,846,960],["2025-11-11",1740,18260,846,960],["2025-11-12",3740,16260,846,960],["2025-11-13",4540,15460,846,960],["2025-11-14",4440,15060,846,960],["2025-11-25",1440,18560,846,960],["2025-11-26",1040,18960,846,960],["2025-12-01",-5560,18260,846,960],["2025-12-02",2340,17660,846,960],["2025-12-03",1040,18960,846,960],["2025-12-04",1340,18660,846,960],["2025-12-05",1740,18260,846,960],["2025-12-08",2040,17960,846,960],["2025-12-09",1140,18860,846,960],["2025-12-10",5240,14760,846,960],["2025-12-11",2540,17460,846,960],["2025-12-12",2140,17860,846,960],["2025-12-15",1440,18560,846,960],["2025-12-16",3740,16260,846,960],["2025-12-17",2640,17360,846,960],["2025-12-18",3840,16160,846,960],["2025-12-19",1940,18060,846,960],["2026-01-23",1040,18960,846,960],["2026-02-10",1640,18360,846,960],["2026-03-17",-360,17660,846,960],["2026-03-18",-14160,14160,846,960],["2026-04-02",3340,16660,846,960],["2026-04-06",1940,18060,846,960],["2026-04-07",5140,14860,846,960],["2026-04-09",1640,18360,846,960],["2026-04-10",2040,17960,846,960],["2026-04-13",940,19060,846,960],["2026-04-14",2140,17860,846,960],["2026-04-15",1740,18260,846,960],["2026-04-16",3040,16960,846,960],["2026-04-17",2640,17360,846,960],["2026-04-20",1440,18560,846,960],["2026-04-21",-5760,17260,846,960],["2026-04-22",1740,18260,846,960],["2026-04-23",4340,15660,846,960],["2026-04-24",3540,16460,846,960],["2026-04-27",1940,18060,846,960],["2026-04-28",2140,17860,846,960],["2026-04-29",5440,14560,846,960],["2026-04-30",4540,15460,846,960],["2026-05-01",-2260,18960,846,960],["2026-05-04",1840,18160,846,960],["2026-05-05",840,19160,846,960],["2026-06-15",2140,17860,846,960],["2026-06-16",-4160,18060,846,960],["2026-06-17",-11260,11260,846,960],["2026-06-22",3240,16760,846,960],["2026-06-23",-9760,16460,846,960],["2026-06-30",3940,16060,846,960],["2026-07-01",-9960,16860,846,960],["2026-07-02",3040,16960,846,960],["2026-07-06",2140,17860,846,960],["2026-07-07",-1460,18360,846,960],["2026-07-08",3440,16560,846,960],["2026-07-09",1740,18260,846,960],["2026-07-13",2440,17560,846,960],["2026-08-03",1940,18060,846,960],["2026-08-04",2740,17260,846,960],["2026-08-05",-9760,17360,846,960],["2026-08-06",2340,17660,846,960],["2026-08-07",1540,18460,846,960],["2026-08-10",1540,18460,846,960],["2026-08-11",1340,18660,846,960],["2026-08-12",1140,18860,846,960],["2026-08-13",1040,18960,846,960],["2026-08-14",940,19060,846,960],["2026-08-18",2240,17760,846,960],["2026-08-19",2540,17460,846,960],["2026-08-20",-760,17260,846,960],["2026-08-21",2240,17760,846,960],["2026-08-24",1740,18260,846,960],["2026-08-25",1040,18960,846,960],["2026-08-26",5440,14560,846,960],["2026-08-27",2740,17260,846,960]]
RESEARCH=[("dev",x) for x in devset.TRADES]+[("ext",x) for x in extset.TRADES]

def replay_one(period,item):
 day,k,eff=item; last=None
 for attempt in range(1,5):
  feed=core.Feed()
  try:
   df=base.DayFeed(feed,day,{})
   tr=lock.replay_lock(df,k,1000,0)
   if attempt>1:core.emit("shared_research_recovered",day=day,attempt=attempt)
   return day,{"period":period,"eff":float(eff),**tr},None
  except Exception as exc:
   last=exc
   if "transport_failed" not in str(exc) or attempt==4:break
   core.emit("shared_research_retry",day=day,attempt=attempt,reason=str(exc)[:240])
   time.sleep(2*attempt)
 return day,None,{"day":day,"kind":type(last).__name__,"reason":str(last)[:240]}

def max_losing_streak(seq):
 best=cur=0
 for p in seq:
  if p<0:cur+=1;best=max(best,cur)
  else:cur=0
 return best

def run_portfolio(research):
 ebb={d:{"net_cents":p,"risk_cents":r,"entry_minute_et":en,"exit_minute_et":ex} for d,p,r,en,ex in EBB}
 days=sorted(set(ebb)|set(research))
 eq=200000; peak=eq; dd=0
 accepted=[]; blocked=Counter(); overlap_days=[]; both_loss_days=[]
 engine_pnl=Counter(); engine_n=Counter()
 for day in days:
  r=research.get(day); e=ebb.get(day)
  r_active=False
  # Research admission at 12:01.
  if r and r.get("status")=="trade":
   if r["risk_cents"]*100 <= eq*10:
    r_active=True
   else:
    blocked["research_risk"]+=1
  # If repaired Research closes before EBB decision, realize first.
  if r_active and r["exit_minute_et"]<=845:
   eq+=r["net_cents"];engine_pnl["research"]+=r["net_cents"];engine_n["research"]+=1
   accepted.append((day,"research",r["net_cents"]))
   peak=max(peak,eq);dd=max(dd,peak-eq);r_active=False
  # EBB admission at 14:05.
  e_active=False
  if e:
   openrisk=(r["risk_cents"] if r_active else 0)+e["risk_cents"]
   if openrisk*100 <= eq*10:
    e_active=True
   else:
    blocked["ebb_portfolio_risk" if r_active else "ebb_risk"]+=1
  if r and e: overlap_days.append(day)
  # Remaining Research exits by 15:45, before EBB 16:00 settlement.
  if r_active:
   eq+=r["net_cents"];engine_pnl["research"]+=r["net_cents"];engine_n["research"]+=1
   accepted.append((day,"research",r["net_cents"]))
   peak=max(peak,eq);dd=max(dd,peak-eq)
  if e_active:
   eq+=e["net_cents"];engine_pnl["ebb"]+=e["net_cents"];engine_n["ebb"]+=1
   accepted.append((day,"ebb",e["net_cents"]))
   peak=max(peak,eq);dd=max(dd,peak-eq)
  dayvals=[p for d,en,p in accepted if d==day]
  if len(dayvals)>=2 and all(p<0 for p in dayvals): both_loss_days.append(day)
 # Engine sequences in chronological accepted order.
 rs=[p for d,en,p in accepted if en=="research"]
 es=[p for d,en,p in accepted if en=="ebb"]
 alls=[p for d,en,p in accepted]
 return {
  "sessions":len(days),"starting_equity":2000.0,"ending_equity":round(eq/100,2),
  "trading_net":round((eq-200000)/100,2),"max_closed_equity_drawdown":round(dd/100,2),
  "research_trades":engine_n["research"],"research_pnl":round(engine_pnl["research"]/100,2),
  "ebb_trades":engine_n["ebb"],"ebb_pnl":round(engine_pnl["ebb"]/100,2),
  "blocked":dict(blocked),"historical_overlap_signal_days":len(overlap_days),
  "accepted_both_loss_days":both_loss_days,
  "research_max_losing_streak":max_losing_streak(rs),
  "ebb_max_losing_streak":max_losing_streak(es),
  "portfolio_max_losing_trade_streak":max_losing_streak(alls),
  "accepted_trades":[{"day":d,"engine":en,"net":round(p/100,2)} for d,en,p in accepted],
 }

def execute():
 core.STATE["stage"]="running"; out={};errors=[]
 workers=max(1,min(int(os.getenv("FLAME_SHARED_WORKERS","3")),6))
 core.emit("shared_repaired_spec",research_entries=len(RESEARCH),ebb_trades=len(EBB),workers=workers,
  research_rule="tp25_stop2x + breakeven arm at +$10",governor_pct=10,kelly=False,live_changed=False)
 with ThreadPoolExecutor(max_workers=workers) as ex:
  futs={ex.submit(replay_one,p,t):(p,t[0]) for p,t in RESEARCH};done=0
  for fut in as_completed(futs):
   day,tr,err=fut.result();done+=1
   if tr:out[day]=tr
   if err:errors.append(err);core.emit("shared_repaired_day_error",**err)
   if done%10==0 or done==len(RESEARCH):core.emit("shared_repaired_progress",completed=done,total=len(RESEARCH),errors=len(errors))
 if errors:
  core.STATE["stage"]="failed";core.emit("shared_repaired_failed",errors=errors);return
 result=run_portfolio(out)
 core.emit("shared_repaired_result",**result)
 core.STATE["stage"]="complete";core.emit("shared_repaired_complete",errors=0,**{k:v for k,v in result.items() if k!="accepted_trades"})

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="shared-repaired-portfolio":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
