"""SpreadWorks database connection — SQLAlchemy engine + session factory."""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Render provides postgres:// but SQLAlchemy 2.x requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Log masked URL for debugging (show scheme + host only)
if DATABASE_URL:
    _masked = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "(no @ in URL — possibly malformed)"
    print(f"[SpreadWorks] DATABASE_URL host part: {_masked}")
else:
    print("[SpreadWorks] DATABASE_URL is empty/unset")

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
) if DATABASE_URL else None

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False) if engine else None

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session, auto-closes on exit."""
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
