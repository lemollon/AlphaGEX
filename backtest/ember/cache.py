from __future__ import annotations

import hashlib
import json
from typing import List, Optional

import psycopg2
import psycopg2.extras

from backtest.ember.build import DayPath
from backtest.ember.dbutil import db_cursor

STALE_SECONDS = 120  # a build with no progress update for this long is considered stuck

_DDL = """
CREATE TABLE IF NOT EXISTS ember_builds (
    build_id          TEXT PRIMARY KEY,
    params            JSONB NOT NULL,
    status            TEXT NOT NULL DEFAULT 'pending',
    progress          INTEGER NOT NULL DEFAULT 0,
    progress_message  TEXT,
    n_days            INTEGER,
    paths             JSONB,
    error             TEXT,
    cancel_requested  BOOLEAN NOT NULL DEFAULT false,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def build_key(params: dict) -> str:
    """Deterministic 16-char id from the entry-config params (order-insensitive)."""
    norm = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def ensure_tables(db_url: str) -> None:
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(_DDL)
            c.execute("ALTER TABLE ember_builds ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT false")


def create_pending(db_url: str, build_id: str, params: dict) -> None:
    """Insert a pending build. If one exists, leave it untouched unless it failed or
    was canceled (then reset to pending so it can be re-run)."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO ember_builds (build_id, params, status, progress)
                VALUES (%s, %s, 'pending', 0)
                ON CONFLICT (build_id) DO UPDATE
                    SET status = 'pending', progress = 0, progress_message = NULL,
                        error = NULL, cancel_requested = false, updated_at = now()
                    WHERE ember_builds.status IN ('failed', 'canceled')
                """,
                (build_id, json.dumps(params, default=str)),
            )


def set_progress(db_url: str | None = None, build_id: str = None, progress: int = 0, message: Optional[str] = None, *, conn=None) -> None:
    with db_cursor(db_url, conn) as c:
        c.execute(
            "UPDATE ember_builds SET status='running', progress=%s, progress_message=%s, updated_at=now() WHERE build_id=%s",
            (progress, message, build_id),
        )


def set_completed(db_url: str, build_id: str, paths: List[DayPath]) -> None:
    payload = json.dumps([p.to_dict() for p in paths])
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """UPDATE ember_builds
                   SET status='completed', progress=100, progress_message=NULL,
                       n_days=%s, paths=%s, error=NULL, updated_at=now()
                   WHERE build_id=%s""",
                (len(paths), payload, build_id),
            )


def set_failed(db_url: str, build_id: str, error: str) -> None:
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """UPDATE ember_builds
                   SET status='failed', error=%s, updated_at=now()
                   WHERE build_id=%s""",
                (error, build_id),
            )


def get_build(db_url: str, build_id: str) -> Optional[dict]:
    """Lightweight build status (does NOT load the heavy `paths` blob)."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """SELECT build_id, params, status, progress, progress_message,
                          n_days, error, cancel_requested, created_at, updated_at
                   FROM ember_builds WHERE build_id=%s""",
                (build_id,),
            )
            row = c.fetchone()
            return dict(row) if row else None


def load_paths(db_url: str, build_id: str) -> List[DayPath]:
    """Load and deserialize the cached DayPaths for a completed build."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute("SELECT paths FROM ember_builds WHERE build_id=%s", (build_id,))
            row = c.fetchone()
    if not row or row[0] is None:
        return []
    raw = row[0]
    data = raw if isinstance(raw, list) else json.loads(raw)
    return [DayPath.from_dict(d) for d in data]


def request_cancel(db_url: str, build_id: str) -> bool:
    """Flag an in-flight build for cancellation. Returns True if a cancelable
    (pending/running) build was flagged."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """UPDATE ember_builds SET cancel_requested = true, updated_at = now()
                   WHERE build_id = %s AND status IN ('pending', 'running')""",
                (build_id,),
            )
            return c.rowcount > 0


def is_cancel_requested(db_url: str | None = None, build_id: str = None, *, conn=None) -> bool:
    with db_cursor(db_url, conn) as c:
        c.execute("SELECT cancel_requested FROM ember_builds WHERE build_id=%s", (build_id,))
        row = c.fetchone()
        return bool(row[0]) if row else False


def set_canceled(db_url: str, build_id: str) -> None:
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """UPDATE ember_builds
                   SET status = 'canceled', cancel_requested = false,
                       progress_message = 'canceled', updated_at = now()
                   WHERE build_id = %s""",
                (build_id,),
            )


def reap_stale_builds(db_url: str, max_idle_seconds: int = STALE_SECONDS) -> int:
    """Mark builds stuck in pending/running with no update for > max_idle_seconds as failed.
    Returns the number reaped. Healthy builds update every fraction of a second, so this
    only catches genuinely hung builds (e.g. a worker thread that died)."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """UPDATE ember_builds
                   SET status = 'failed', error = 'reaped: no progress for >%s s', updated_at = now()
                   WHERE status IN ('pending', 'running')
                     AND updated_at < now() - make_interval(secs => %s)""",
                (max_idle_seconds, max_idle_seconds),
            )
            return c.rowcount
