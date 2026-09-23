"""Fresh-source 102-session SPY loss-cluster study; research only."""
import os
import threading
from datetime import datetime, timezone
from http.server import HTTPServer
import flame_reset_stock as patched

core = patched.core
core.SPEC.update({
    "id": "flame-loss-cluster-102d-20260923",
    "start": "2025-01-01",
    "end": "2025-05-30",
    "closures": [
        "2025-01-01","2025-01-09","2025-01-20","2025-02-17",
        "2025-04-18","2025-05-26"
    ],
    "expected_sessions": 102,
    "max_requests": 230,
    "deadline_seconds": 3600,
    "scope": "retrospective 102-session fixed-rule loss-cluster study, not unseen validation",
    "no_saved_price_inputs": True,
    "no_previous_trade_inputs": True,
})

if __name__ == "__main__":
    if os.getenv("FLAME_FRESH_MODE") == "loss-cluster-102d":
        core.emit(
            "large_sample_start",
            sessions=102,
            start=core.SPEC["start"],
            end=core.SPEC["end"],
            prior_market_data_inputs=0,
            prior_result_inputs=0,
            live_trading_changed=False,
        )
        threading.Thread(target=core.execute, daemon=True).start()
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "10000"))), core.Handler).serve_forever()
