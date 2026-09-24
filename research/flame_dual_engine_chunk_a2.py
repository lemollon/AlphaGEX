import os, threading
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x
x.core.SPEC.update({
 "id":"flame-dual-engine-chunk-a2-20260924",
 "start":"2025-11-03","end":"2026-04-28",
 "closures":["2025-11-27","2025-11-28","2025-12-24","2025-12-25","2026-01-01","2026-01-19","2026-02-16","2026-04-03"],
 "expected_sessions":119,"max_requests":800,"deadline_seconds":3600,
 "scope":"clean chunk A2 for frozen dual-engine reconciliation"
})
if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-chunk-a2":
  threading.Thread(target=x.execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),x.core.Handler).serve_forever()
