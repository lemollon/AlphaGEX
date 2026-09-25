"""Resume only unfinished frozen dual-engine Flame validation.
A1/A2/A3 and Apr 29 are complete and intentionally NOT rerun.
Remaining:
B1: 2026-04-30..2026-06-30
B2: 2026-07-01..2026-08-31
Trading logic is imported unchanged from flame_dual_engine_extended_cluster.
Research only; no live/customer writes.
"""
import os, threading, time
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x

CHUNKS = [
    ("B1","2026-04-30","2026-06-30",42,
     ["2026-05-25","2026-06-19"]),
    ("B2","2026-07-01","2026-08-31",43,
     ["2026-07-03"]),
]

def run():
    for name,start,end,expected,closures in CHUNKS:
        x.core.SPEC.update({
            "id":f"flame-dual-engine-resume-{name.lower()}-20260924",
            "start":start,"end":end,"closures":closures,
            "expected_sessions":expected,
            "max_requests":600,
            "deadline_seconds":3600,
            "scope":f"resume unfinished frozen dual-engine validation {name}; completed chunks excluded",
            "no_saved_price_inputs":True,
            "no_previous_trade_inputs":True,
        })
        x.core.emit("resume_chunk_start",chunk=name,start=start,end=end,expected_sessions=expected)
        x.execute()
        x.core.emit("resume_chunk_done",chunk=name,state=x.core.STATE.get("stage"))
        if x.core.STATE.get("stage") != "complete":
            break
        time.sleep(1)

if __name__=="__main__":
    if os.getenv("FLAME_RESUME_ENABLED","1") == "1":
        threading.Thread(target=run,daemon=True).start()
    HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),x.core.Handler).serve_forever()
