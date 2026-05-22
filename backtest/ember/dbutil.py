from __future__ import annotations

from contextlib import contextmanager

import psycopg2
import psycopg2.extras


@contextmanager
def db_cursor(db_url: str | None = None, conn=None, dict_rows: bool = False):
    """Yield a cursor.

    - If `conn` is provided, REUSE it (the caller owns its lifecycle — it should be
      autocommit so each statement is visible to other connections). The cursor is
      closed but the connection is left open.
    - Otherwise open a transient connection from `db_url`, commit on success, and close it
      (matches the pre-existing per-call behavior)."""
    factory = psycopg2.extras.RealDictCursor if dict_rows else None
    if conn is not None:
        cur = conn.cursor(cursor_factory=factory)
        try:
            yield cur
        finally:
            cur.close()
    else:
        transient = psycopg2.connect(db_url)
        try:
            with transient:  # commits on success / rolls back on exception
                with transient.cursor(cursor_factory=factory) as cur:
                    yield cur
        finally:
            transient.close()  # release the slot deterministically (don't wait for GC)


def open_build_connection(db_url: str):
    """Open a dedicated autocommit connection for the duration of one build."""
    c = psycopg2.connect(db_url)
    c.autocommit = True
    return c
