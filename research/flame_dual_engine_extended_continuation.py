"""Continuation of frozen dual-engine extension after provider hang on 2026-04-29.
Runs standard full sessions 2026-04-30 through 2026-08-31 only.
Trading rules and diagnostics are imported unchanged from flame_dual_engine_extended_cluster.
"""
import os, threading
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as ext

core=ext.core
core.SPEC.update({
 "id":"flame-dual-engine-extended-continuation-20260924",
 "start":"2026-04-30",
 "end":"2026-08-31",
 "closures":["2026-05-25","2026-06-19","2026-07-03"],
 "expected_sessions":85,
 "max_requests":600,
 "deadline_seconds":3600,
 "scope":"continuation of frozen dual-engine extension after isolated 2026-04-29 provider hang",
})

if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-extended-cont":
  threading.Thread(target=ext.execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),core.Handler).serve_forever()
