"""Fast frozen-entry exit repair for the validated Jan-May 2025 Research development set.
Uses 28 exact Research entries recovered from completed cleanroom dual_day logs.
Only exits are varied against fresh post-entry ThetaData quote paths. Research only.
"""
import os, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import HTTPServer
import flame_research_exit_repair as repair
import flame_two_entry_optimized as base

core=repair.core
core.SPEC.update({
 "id":"flame-research-frozen28-exit-repair-20260925",
 "start":"2025-01-01","end":"2025-05-30",
 "scope":"frozen 28 validated Research entries; fresh post-entry exit replay only",
 "no_saved_price_inputs":True,
 "no_previous_trade_inputs":False,
 "frozen_entry_source":"completed 102-session cleanroom dual_day ledger",
})

TRADES=[
("2025-01-07",5900000,"0.4693709743730300123338358229"),
("2025-01-13",5750000,"0.3754940711462153759627552399"),
("2025-01-14",5780000,"0.5474981870920957215373459028"),
("2025-01-30",6040000,"0.5141897089186672604348002105"),
("2025-02-04",6010000,"0.3086053412462908011869436202"),
("2025-02-13",6060000,"0.4782608695652636000840159675"),
("2025-03-06",5730000,"0.5090689238210399032648125756"),
("2025-03-07",5640000,"0.6815498551035554246795229032"),
("2025-03-12",5580000,"0.6229801242455885736535636537"),
("2025-03-13",5510000,"0.4385554885404140991463814491"),
("2025-03-14",5620000,"0.4266122374094315481257411903"),
("2025-03-18",5590000,"0.3091757061259054964027177568"),
("2025-03-19",5650000,"0.5136363636363636363636363636"),
("2025-03-21",5580000,"0.5595369349503550420653279848"),
("2025-03-26",5700000,"0.7354497354497354497354497354"),
("2025-04-01",5610000,"0.3604551476891761961208132969"),
("2025-04-03",5410000,"0.4790764790764790764790764791"),
("2025-04-10",5150000,"0.5861236894553142338606523921"),
("2025-04-11",5240000,"0.3909977183157021364862061813"),
("2025-04-14",5340000,"0.5780083238874704206362515255"),
("2025-04-21",5100000,"0.6976344341021479918921841187"),
("2025-04-23",5360000,"0.5525606469002695417789757412"),
("2025-04-28",5470000,"0.4932880478731847553599264698"),
("2025-04-30",5480000,"0.5884869882391451752437513152"),
("2025-05-08",5680000,"0.6877349959545000237970586835"),
("2025-05-15",5890000,"0.6630434782609056001890359188"),
("2025-05-19",5930000,"0.3803547640748790577017457758"),
("2025-05-29",5860000,"0.5467836257309847901918539042"),
]

def replay_one(item):
 day,k,eff=item
 last=None
 for attempt in range(1,5):
  feed=core.Feed()
  try:
   df=base.DayFeed(feed,day,{})
   variants={name:repair.replay_variant(df,k,2,720,**cfg) for name,cfg in repair.VARIANTS.items()}
   if attempt>1: core.emit("frozen28_recovered",day=day,attempt=attempt)
   return {"day":day,"eff":float(eff),"variants":variants},None
  except Exception as exc:
   last=exc
   if "transport_failed" not in str(exc) or attempt==4: break
   core.emit("frozen28_retry",day=day,attempt=attempt,reason=str(exc)[:240])
   time.sleep(2*attempt)
 return None,{"day":day,"kind":type(last).__name__,"reason":str(last)[:240]}

def execute():
 core.STATE["stage"]="running"; rows=[]; errors=[]
 workers=max(1,min(int(os.getenv("FLAME_FROZEN28_WORKERS","3")),6))
 core.emit("frozen28_spec",entries=len(TRADES),workers=workers,variants=repair.VARIANTS,live_changed=False)
 with ThreadPoolExecutor(max_workers=workers) as ex:
  futs={ex.submit(replay_one,t):t[0] for t in TRADES}
  done=0
  for fut in as_completed(futs):
   row,err=fut.result(); done+=1
   if row: rows.append(row)
   if err:
    errors.append(err); core.emit("frozen28_day_error",**err)
   if done%10==0 or done==len(TRADES):
    core.emit("frozen28_progress",completed=done,total=len(TRADES),errors=len(errors),day=futs[fut])
 rows.sort(key=lambda x:x["day"])
 if errors:
  core.STATE["stage"]="failed"; core.emit("frozen28_failed",errors=errors,completed=len(rows)); return
 results={name:repair.summarize(rows,name) for name in repair.VARIANTS}
 for x in results.values(): core.emit("frozen28_result",**x)
 core.STATE["stage"]="complete"; core.emit("frozen28_complete",entries=len(rows),errors=0,results=results)

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="frozen28-exit-repair":
  threading.Thread(target=execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
