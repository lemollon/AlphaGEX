import os, threading
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x
x.core.SPEC.update({
 "id":"flame-dual-engine-chunk-a1-20260924",
 "start":"2025-06-02","end":"2025-10-31",
 "closures":["2025-06-19","2025-07-03","2025-07-04","2025-09-01"],
 "expected_sessions":106,"max_requests":700,"deadline_seconds":3600,
 "scope":"clean chunk A1 for frozen dual-engine reconciliation"
})
if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-chunk-a1":
  threading.Thread(target=x.execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),x.core.Handler).serve_forever()
