import os, threading
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x
x.core.SPEC.update({
 "id":"flame-dual-engine-apr29-20260924",
 "start":"2026-04-29","end":"2026-04-29","closures":[],
 "expected_sessions":1,"max_requests":50,"deadline_seconds":900,
 "scope":"single missing full-session reconciliation day"
})
if __name__=="__main__":
 if os.getenv("FLAME_FRESH_MODE")=="dual-engine-apr29":
  threading.Thread(target=x.execute,daemon=True).start()
 HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),x.core.Handler).serve_forever()
