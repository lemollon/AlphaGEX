"""Clean first segment for dual-engine reconciliation."""
import os, threading
from http.server import HTTPServer
import flame_dual_engine_extended_cluster as x

x.core.SPEC.update({
    "id":"flame-dual-engine-segment-a-20260924",
    "start":"2025-06-02",
    "end":"2026-04-28",
    "closures":[
        "2025-06-19","2025-07-03","2025-07-04","2025-09-01",
        "2025-11-27","2025-11-28","2025-12-24","2025-12-25",
        "2026-01-01","2026-01-19","2026-02-16","2026-04-03"
    ],
    "expected_sessions":225,
    "max_requests":1200,
    "deadline_seconds":7200,
    "scope":"clean segment A for frozen dual-engine reconciliation",
})
if __name__=="__main__":
    # This isolated research runner always executes Segment A on boot.
    # No environment gate: prevents a healthy service from idling with no research job.
    threading.Thread(target=x.execute,daemon=True).start()
    HTTPServer(("0.0.0.0",int(os.getenv("PORT","10000"))),x.core.Handler).serve_forever()
