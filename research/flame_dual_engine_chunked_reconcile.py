"""Chunked dual-engine reconciliation runner.

Runs three bounded historical chunks sequentially so one provider issue cannot
erase all progress. Research only; no live/customer writes.
"""
import os, threading, time
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x

CHUNKS = [
    ("A1","2025-06-02","2025-10-10",91,[
        "2025-06-19","2025-07-03","2025-07-04","2025-09-01"
    ]),
    ("A2","2025-10-13","2026-01-15",64,[
        "2025-11-27","2025-11-28","2025-12-24","2025-12-25","2026-01-01"
    ]),
    ("A3","2026-01-16","2026-04-28",70,[
        "2026-01-19","2026-02-16","2026-04-03"
    ]),
]

def run_chunks():
    for name,start,end,expected,closures in CHUNKS:
        x.core.SPEC.update({
            "id":f"flame-dual-engine-{name.lower()}-20260924",
            "start":start,
            "end":end,
            "closures":closures,
            "expected_sessions":expected,
            "max_requests":600,
            "deadline_seconds":2400,
            "scope":f"chunked frozen dual-engine reconciliation {name}",
        })
        x.core.emit("chunk_start",chunk=name,start=start,end=end,expected_sessions=expected)
        x.execute()
        x.core.emit("chunk_done",chunk=name,state=x.core.STATE.get("stage"))
        time.sleep(1)

if __name__=="__main__":
    threading.Thread(target=run_chunks,daemon=True).start()
    HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),x.core.Handler).serve_forever()
