"""Cross-process lifecycle serialization. Failure to lock never permits an order."""
from functools import wraps
from threading import local
from .db import db_connection

_state = local()

def serialized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        if getattr(_state, "locked", False):
            return method(self, *args, **kwargs)
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT pg_try_advisory_lock(8675309, 42)")
            if not cursor.fetchone()[0]:
                return False
            _state.locked = True
            try:
                return method(self, *args, **kwargs)
            finally:
                _state.locked = False
                cursor.execute("SELECT pg_advisory_unlock(8675309, 42)")
                conn.commit()
    return wrapped
