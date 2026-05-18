"""Shared pytest fixtures for SpreadWorks bots."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Force a SQLite in-memory DB for tests BEFORE importing backend code.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("TRADIER_TOKEN", "test")
os.environ.setdefault("TRADIER_ACCOUNT_ID", "test")
os.environ.setdefault("DISCORD_WEBHOOK_URL", "")

from backend.db import Base  # noqa: E402
from backend import models  # noqa: E402,F401 — register models
from backend.bots.db import create_bot_tables  # noqa: E402

CT = ZoneInfo("America/Chicago")
FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    create_bot_tables(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def fake_chain_0dte():
    return json.loads((FIXTURE_DIR / "spy_0dte_chain.json").read_text())


@pytest.fixture
def fake_chain_1dte():
    return json.loads((FIXTURE_DIR / "spy_1dte_chain.json").read_text())


@pytest.fixture
def fake_chain_14dte():
    return json.loads((FIXTURE_DIR / "spy_14dte_chain.json").read_text())


@pytest.fixture
def market_open_ct():
    """A safe within-entry-window time: 09:00 CT on a Wednesday."""
    return datetime(2026, 5, 20, 9, 0, tzinfo=CT)


@pytest.fixture
def after_eod_ct():
    """After EOD close on a Wednesday."""
    return datetime(2026, 5, 20, 14, 50, tzinfo=CT)
