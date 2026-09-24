"""Parallel full-period dual-engine rerun. Trading rules unchanged."""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x

core=x.core; old=x.old; base=x.base
core.SPEC.update({
 "id":"flame-dual-engine-full-parallel-20260924",
 "start":"2025-06-02","end":"2026-08-31",
 "closures":[
  "2025-06-19","2025-07-03","2025-07-04","2025-09-01",
  "2025-11-27","2025-11-28","2025-12-24","2025-12-25",
  "2026-01-01","2026-01-19","2026-02-16","2026-04-03",
  "2026-05-25","2026-06-19","2026-07-03"
 ],
 "expected_sessions":311,
 "max_requests":100,
 "deadline_seconds":1800,
 "scope":"full frozen dual-engine rerun; independent days parallelized; bounded transport retries; no saved-data fallback",
})
WORKERS=12

def retryable(exc):
 s=str(exc)
 return ("transport_failed" in s or "ConnectTimeout" in s or "ReadTimeout" in s
         or "502" in s or "503" in s or "504" in s)

def process_day(vix,day,index):
 last=None
 for attempt in range(1,4):
  feed=core.Feed()
  try:
   stock=old.get_stock(feed,day)
   df=base.DayFeed(feed,day,stock)
   r,rm=old.research_trade(df)
   vg=old.vix_gate(vix,day)
   e,em=old.ebb_trade(df,vg)
   return day,index,{"research":r,"research_meta":rm,"ebb":e,"ebb_meta":em},feed.n
  except Exception as exc:
   last=exc
   if not retryable(exc) or attempt==3: raise
   core.emit("dual_parallel_retry",day=day,index=index,attempt=attempt,reason=str(exc)[:300])
   time.sleep(attempt)
 raise last

def execute():
 core.STATE["stage"]="running"; days=core.session_days(); daily={}; total_requests=0
 try:
  if len(days)!=core.SPEC["expected_sessions"]:
   raise core.DataError("session_count:"+str(len(days)))
  vix,vix_sha=old.get_vix()
  core.emit("dual_parallel_spec",configuration=core.SPEC,vix_source=old.VIX_URL,vix_sha256=vix_sha,
   workers=WORKERS,
   research_rules={"decision_et":720,"efficiency_min":0.30,"target_pct":50,"stop_mult":2,"width":2},
   ebb_rules={"decision_et":845,"vix_decay_ceiling":0.80,"otm_dollars":1,"width":2,"exit":"close_settlement"},
   portfolio_cap_pct=10,live_changed=False)
  with ThreadPoolExecutor(max_workers=WORKERS) as pool:
   futs=[pool.submit(process_day,vix,d,i) for i,d in enumerate(days,1)]
   for fut in as_completed(futs):
    day,index,rec,n=fut.result()
    daily[day]=rec; total_requests+=n
    core.emit("dual_parallel_day",day=day,index=index,**rec)
  if len(daily)!=len(days): raise core.DataError("incomplete_days:"+str(len(daily)))
  ordered={d:daily[d] for d in days}
  rc,_=x.engine_cluster(days,ordered,"research")
  ec,_=x.engine_cluster(days,ordered,"ebb")
  core.emit("dual_parallel_cluster",**rc)
  core.emit("dual_parallel_cluster",**ec)
  port=x.accepted_portfolio(days,ordered,10)
  core.emit("dual_parallel_portfolio",
   sessions=len(days),trades=len(port["accepted"]),blocked=port["blocked"],
   trading_net=x.money(port["trading_net_cents"]),
   subscription=x.money(port["subscription_cents"]),
   customer_net=x.money(port["customer_net_cents"]),
   ending_equity=x.money(port["ending_equity_cents"]),
   max_closed_equity_drawdown=x.money(port["max_closed_equity_drawdown_cents"]),
   overlap=x.overlap_cluster(days,ordered),qualification="RETROSPECTIVE_ONLY")
  core.STATE["stage"]="complete"
  core.emit("dual_parallel_complete",days=len(days),provider_requests=total_requests,prior_inputs=0,vix_sha256=vix_sha)
 except Exception as e:
  core.STATE["stage"]="failed"
  core.emit("dual_parallel_failed",kind=type(e).__name__,reason=str(e)[:600],completed_days=len(daily),provider_requests=total_requests)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-full-parallel":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
