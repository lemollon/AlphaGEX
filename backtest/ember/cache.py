from __future__ import annotations

import hashlib
import json
from typing import List, Optional

import psycopg2
import psycopg2.extras

from backtest.ember.build import DayPath

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


def create_pending(db_url: str, build_id: str, params: dict) -> None:
    """Insert a pending build. If one already exists for this id, leave it untouched
    unless it failed (then reset to pending so it can be retried)."""
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """
                INSERT INTO ember_builds (build_id, params, status, progress)
                VALUES (%s, %s, 'pending', 0)
                ON CONFLICT (build_id) DO UPDATE
                    SET status = 'pending', progress = 0, error = NULL, updated_at = now()
                    WHERE ember_builds.status = 'failed'
                """,
                (build_id, json.dumps(params, default=str)),
            )


def set_progress(db_url: str, build_id: str, progress: int, message: Optional[str] = None) -> None:
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(
                """UPDATE ember_builds
                   SET status='running', progress=%s, progress_message=%s, updated_at=now()
                   WHERE build_id=%s""",
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
                          n_days, error, created_at, updated_at
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
