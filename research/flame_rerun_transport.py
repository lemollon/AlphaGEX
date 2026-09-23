"""Bounded retry wrapper for the isolated research worker, not an order executor."""
import os
import threading
import time
from datetime import datetime, timezone
from http.server import HTTPServer
import requests
import flame_controlled_rerun as core

original_get = core.Feed.get

def retry_get(self, path, params):
    for attempt in range(3):
        try:
            return original_get(self, path, params)
        except (requests.ConnectionError, requests.Timeout) as exc:
            retryable = True
        except requests.HTTPError as exc:
            retryable = exc.response is not None and exc.response.status_code in (502, 503, 504)
        if not retryable or attempt == 2:
            raise core.DataError('provider_request_failed_after_bounded_attempts')
        core.emit('transport_retry', attempt=attempt+1, request_count=self.calls,
                  path=path, delay_seconds=2*(attempt+1))
        time.sleep(2*(attempt+1))

core.Feed.get = retry_get

if __name__ == '__main__':
    if os.getenv('FLAME_FRESH_MODE') == 'controlled-rerun' and datetime.now(timezone.utc) < datetime.fromisoformat('2026-09-23T22:00:00+00:00'):
        core.emit('execution_wrapper', max_attempts=3, transient_statuses=[502,503,504],
                  no_saved_data_fallback=True, trading_config_sha256=core.validate_spec(core.SPEC))
        threading.Thread(target=core.execute, daemon=True).start()
    HTTPServer(('0.0.0.0', int(os.getenv('PORT','10000'))), core.Handler).serve_forever()
