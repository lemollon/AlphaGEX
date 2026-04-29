"""
Admin read-only SQL endpoint.

POST /api/admin/sql
  Headers: X-Admin-Token: <ADMIN_SQL_TOKEN>
  Body: { "query": "SELECT ...", "params": [optional list], "limit": 1000 }
  Response: { "columns": [...], "rows": [[...]], "row_count": N, "truncated": bool, "elapsed_ms": float }

Designed for ad-hoc Postgres inspection from outside Render (e.g. Claude Code
sessions). Read-only, enforced via:
  - Static keyword reject list (DDL/DML rejected before execution)
  - Statement-level READ ONLY transaction — any write attempt errors out
  - statement_timeout caps runtime (default 30s)
  - Row cap on the response (default 1000, max 10000)

Auth uses a constant-time compare against ADMIN_SQL_TOKEN. If the env var is
not set the endpoint returns 503 (locked) so an unconfigured deploy can't be
abused.
"""

import hmac
import logging
import os
import re
import time
from collections import deque
from typing import Any, List, Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from database_adapter import get_connection


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Admin SQL"])

DEFAULT_ROW_LIMIT = 1000
MAX_ROW_LIMIT = 10_000
STATEMENT_TIMEOUT_MS = 30_000

WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|"
    r"COPY|VACUUM|REINDEX|CLUSTER|COMMENT|SECURITY|LOCK|"
    r"REFRESH|CALL|DO|EXECUTE)\b",
    re.IGNORECASE,
)

QUERY_AUDIT: deque = deque(maxlen=200)


class SqlRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=20_000)
    params: Optional[List[Any]] = None
    limit: int = Field(DEFAULT_ROW_LIMIT, ge=1, le=MAX_ROW_LIMIT)


def _check_token(provided: Optional[str]) -> None:
    expected = os.getenv("ADMIN_SQL_TOKEN", "")
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="ADMIN_SQL_TOKEN not configured on this deploy",
        )
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid admin token")


def _validate_read_only(query: str) -> None:
    stripped = query.strip().rstrip(";").strip()
    if not stripped:
        raise HTTPException(status_code=400, detail="Empty query")
    head = stripped.split(None, 1)[0].upper()
    if head not in {"SELECT", "WITH", "EXPLAIN", "SHOW", "VALUES", "TABLE"}:
        raise HTTPException(
            status_code=400,
            detail=f"Only read queries allowed (got: {head})",
        )
    if WRITE_KEYWORDS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="Query contains a write keyword; this endpoint is read-only",
        )
    if ";" in stripped:
        raise HTTPException(
            status_code=400,
            detail="Multi-statement queries not allowed",
        )


@router.post("/api/admin/sql")
async def admin_sql(
    body: SqlRequest,
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    _check_token(x_admin_token)
    _validate_read_only(body.query)

    started = time.perf_counter()
    conn = None
    try:
        conn = get_connection()
        conn.autocommit = False
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(body.query, body.params or None)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchmany(body.limit + 1) if columns else []
        conn.rollback()

        truncated = len(rows) > body.limit
        if truncated:
            rows = rows[: body.limit]

        elapsed_ms = (time.perf_counter() - started) * 1000
        QUERY_AUDIT.append(
            {
                "query": body.query[:500],
                "row_count": len(rows),
                "truncated": truncated,
                "elapsed_ms": round(elapsed_ms, 1),
            }
        )
        logger.info(
            "admin_sql executed: rows=%d truncated=%s elapsed_ms=%.1f",
            len(rows),
            truncated,
            elapsed_ms,
        )

        return {
            "columns": columns,
            "rows": [[r[c] for c in columns] for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
            "elapsed_ms": round(elapsed_ms, 1),
        }
    except HTTPException:
        if conn is not None:
            conn.rollback()
        raise
    except psycopg2.Error as e:
        if conn is not None:
            conn.rollback()
        logger.warning("admin_sql query error: %s", e)
        raise HTTPException(status_code=400, detail=f"Query error: {e}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/api/admin/sql/audit")
async def admin_sql_audit(
    x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token"),
):
    _check_token(x_admin_token)
    return {"queries": list(QUERY_AUDIT)}
