"""Minimal stand-in for AlphaGEX's ``database_adapter`` used by TSUNAMI.

TSUNAMI was ported from AlphaGEX (GOLIATH), whose persistence modules all
do ``from database_adapter import get_connection, is_database_available``.
SpreadWorks has no such module — its ORM layer is SQLAlchemy — but TSUNAMI's
stores are plain-SQL psycopg2 and only need these two functions. Both
services share the same Postgres (alphagex-db), so a direct psycopg2
connection against DATABASE_URL is equivalent to what the adapter provided.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", "").strip()


def is_database_available() -> bool:
    """True when DATABASE_URL is configured and psycopg2 is importable."""
    if not _database_url():
        return False
    try:
        import psycopg2  # noqa: F401
    except ImportError:
        return False
    return True


def get_connection():
    """Return a new psycopg2 connection. Caller closes it.

    Mirrors database_adapter.get_connection() semantics: plain connection,
    no pooling, caller is responsible for commit/close.
    """
    import psycopg2

    url = _database_url()
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return psycopg2.connect(url)
