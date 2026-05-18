# SpreadWorks Auto-Bots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3 automated SPY paper-trading bots (GUST=Iron Butterfly 0DTE, TIDE=Double Calendar 1/14DTE, DRIFT=Double Diagonal 1/14DTE) to SpreadWorks, mirroring the IronForge FLAME/SPARK/INFERNO pattern but running in-process inside the existing FastAPI app with simulated mid-price fills.

**Architecture:** A new `spreadworks/backend/bots/` module hosts a 1-minute APScheduler job that scans each enabled bot, opens positions in per-bot Postgres tables, and monitors MTM with PT/SL/EOD exits. Frontend gets `/bots` overview + per-bot dashboards under SpreadWorks's existing Vite/React app.

**Tech Stack:** FastAPI, APScheduler, SQLAlchemy + raw SQL via `text()`, PostgreSQL, Vite + React, Recharts, Tradier REST (chain quotes only — no orders), Discord webhooks.

**Spec:** `docs/superpowers/specs/2026-05-18-spreadworks-auto-bots-design.md`

---

## File Structure

**New backend files:**
- `spreadworks/backend/bots/__init__.py` — package marker
- `spreadworks/backend/bots/registry.py` — `BOT_REGISTRY` with defaults + display info
- `spreadworks/backend/bots/db.py` — `bot_table()` helper + `create_bot_tables()` migration
- `spreadworks/backend/bots/strategies/__init__.py` — package marker
- `spreadworks/backend/bots/strategies/iron_butterfly.py` — GUST entry logic (pure function)
- `spreadworks/backend/bots/strategies/double_calendar.py` — TIDE entry logic (pure function)
- `spreadworks/backend/bots/strategies/double_diagonal.py` — DRIFT entry logic (pure function)
- `spreadworks/backend/bots/executor.py` — `open_position`, `close_position`, `compute_mtm`
- `spreadworks/backend/bots/monitor.py` — `decide_exit` (PT/SL/EOD/event_halt)
- `spreadworks/backend/bots/scanner.py` — `run_scan_cycle(bot)` orchestration
- `spreadworks/backend/bots/discord_alerts.py` — open/close embed helpers
- `spreadworks/backend/routes_bots.py` — `/api/spreadworks/bots/{bot}/*` handlers

**New tests (backend):**
- `spreadworks/tests/__init__.py`
- `spreadworks/tests/conftest.py` — pytest fixtures (test db, fake chain, frozen time)
- `spreadworks/tests/fixtures/spy_0dte_chain.json` — recorded chain fixture
- `spreadworks/tests/fixtures/spy_1dte_chain.json` — recorded chain fixture
- `spreadworks/tests/fixtures/spy_14dte_chain.json` — recorded chain fixture
- `spreadworks/tests/test_registry.py`
- `spreadworks/tests/test_iron_butterfly.py`
- `spreadworks/tests/test_double_calendar.py`
- `spreadworks/tests/test_double_diagonal.py`
- `spreadworks/tests/test_executor.py`
- `spreadworks/tests/test_monitor.py`
- `spreadworks/tests/test_scanner.py`
- `spreadworks/tests/test_routes_bots.py`

**New frontend files:**
- `spreadworks/frontend/src/lib/botRegistry.js` — frontend mirror of `bots/registry.py`
- `spreadworks/frontend/src/lib/botApi.js` — fetch helpers for bot endpoints
- `spreadworks/frontend/src/hooks/useBotStatus.js`
- `spreadworks/frontend/src/hooks/useBotPositions.js`
- `spreadworks/frontend/src/hooks/useBotEquity.js`
- `spreadworks/frontend/src/pages/BotsOverview.jsx`
- `spreadworks/frontend/src/pages/BotDashboard.jsx`
- `spreadworks/frontend/src/components/bots/BotCard.jsx`
- `spreadworks/frontend/src/components/bots/EquityTab.jsx`
- `spreadworks/frontend/src/components/bots/PerformanceTab.jsx`
- `spreadworks/frontend/src/components/bots/PositionsTab.jsx`
- `spreadworks/frontend/src/components/bots/TradesTab.jsx`
- `spreadworks/frontend/src/components/bots/LogsTab.jsx`
- `spreadworks/frontend/src/components/bots/ConfigTab.jsx`

**Modified files:**
- `spreadworks/backend/__init__.py` — register `scan_bots` APScheduler job + call `create_bot_tables` on startup
- `spreadworks/backend/routes.py` — no changes (new router mounted separately)
- `spreadworks/backend/main.py` — no changes
- `spreadworks/frontend/src/App.jsx` — add simple client-side routing for `/bots` + `/bots/:bot`
- `spreadworks/requirements.txt` — confirm `apscheduler` already pinned (add `freezegun` to dev deps)

---

## Task 1: Test scaffolding

**Files:**
- Create: `spreadworks/tests/__init__.py`
- Create: `spreadworks/tests/conftest.py`
- Create: `spreadworks/pytest.ini`
- Modify: `spreadworks/requirements.txt` (add `pytest`, `pytest-asyncio`, `freezegun`)

- [ ] **Step 1: Add test dev deps to `requirements.txt`**

Open `spreadworks/requirements.txt` and append (skip lines that already exist):

```
pytest>=8.0
pytest-asyncio>=0.23
freezegun>=1.4
```

- [ ] **Step 2: Create `spreadworks/pytest.ini`**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
asyncio_mode = auto
```

- [ ] **Step 3: Create `spreadworks/tests/__init__.py`** (empty file)

- [ ] **Step 4: Create `spreadworks/tests/conftest.py`**

```python
"""Shared pytest fixtures for SpreadWorks bots."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text
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
```

- [ ] **Step 5: Create fixture files**

`spreadworks/tests/fixtures/spy_0dte_chain.json`:

```json
{
  "spot": 500.0,
  "vix": 17.0,
  "atm_straddle_mid": 4.0,
  "expiration": "2026-05-20",
  "options": [
    {"strike": 494, "type": "put",  "bid": 0.40, "ask": 0.50},
    {"strike": 495, "type": "put",  "bid": 0.50, "ask": 0.60},
    {"strike": 496, "type": "put",  "bid": 0.65, "ask": 0.75},
    {"strike": 497, "type": "put",  "bid": 0.90, "ask": 1.00},
    {"strike": 498, "type": "put",  "bid": 1.20, "ask": 1.30},
    {"strike": 499, "type": "put",  "bid": 1.55, "ask": 1.65},
    {"strike": 500, "type": "put",  "bid": 2.00, "ask": 2.10},
    {"strike": 500, "type": "call", "bid": 2.00, "ask": 2.10},
    {"strike": 501, "type": "call", "bid": 1.55, "ask": 1.65},
    {"strike": 502, "type": "call", "bid": 1.20, "ask": 1.30},
    {"strike": 503, "type": "call", "bid": 0.90, "ask": 1.00},
    {"strike": 504, "type": "call", "bid": 0.65, "ask": 0.75},
    {"strike": 505, "type": "call", "bid": 0.50, "ask": 0.60},
    {"strike": 506, "type": "call", "bid": 0.40, "ask": 0.50}
  ],
  "gex": {"flip_point": 502.0, "call_wall": 505.0, "put_wall": 496.0}
}
```

`spreadworks/tests/fixtures/spy_1dte_chain.json`:

```json
{
  "spot": 500.0,
  "vix": 17.0,
  "atm_straddle_mid": 5.0,
  "expiration": "2026-05-21",
  "iv_atm": 0.16,
  "options": [
    {"strike": 495, "type": "put",  "bid": 1.10, "ask": 1.20},
    {"strike": 496, "type": "put",  "bid": 1.30, "ask": 1.40},
    {"strike": 500, "type": "put",  "bid": 2.50, "ask": 2.60},
    {"strike": 500, "type": "call", "bid": 2.50, "ask": 2.60},
    {"strike": 504, "type": "call", "bid": 1.30, "ask": 1.40},
    {"strike": 505, "type": "call", "bid": 1.10, "ask": 1.20}
  ]
}
```

`spreadworks/tests/fixtures/spy_14dte_chain.json`:

```json
{
  "spot": 500.0,
  "vix": 17.0,
  "atm_straddle_mid": 14.0,
  "expiration": "2026-06-03",
  "iv_atm": 0.18,
  "options": [
    {"strike": 495, "type": "put",  "bid": 3.80, "ask": 3.90},
    {"strike": 496, "type": "put",  "bid": 4.10, "ask": 4.20},
    {"strike": 500, "type": "put",  "bid": 6.90, "ask": 7.00},
    {"strike": 500, "type": "call", "bid": 6.90, "ask": 7.00},
    {"strike": 504, "type": "call", "bid": 4.10, "ask": 4.20},
    {"strike": 505, "type": "call", "bid": 3.80, "ask": 3.90}
  ]
}
```

- [ ] **Step 6: Commit**

```bash
cd C:/Users/lemol/alphagex
git checkout -b claude/spreadworks-auto-bots
git add spreadworks/pytest.ini spreadworks/requirements.txt spreadworks/tests/
git commit -m "test: scaffold pytest setup + chain fixtures for spreadworks bots"
```

---

## Task 2: Bot registry

**Files:**
- Create: `spreadworks/backend/bots/__init__.py` (empty)
- Create: `spreadworks/backend/bots/registry.py`
- Create: `spreadworks/tests/test_registry.py`

- [ ] **Step 1: Write the failing test** — `spreadworks/tests/test_registry.py`

```python
from backend.bots.registry import BOT_REGISTRY, get_bot, list_bots


def test_three_bots_registered():
    assert set(BOT_REGISTRY.keys()) == {"gust", "tide", "drift"}


def test_gust_defaults():
    b = get_bot("gust")
    assert b["strategy"] == "iron_butterfly"
    assert b["front_dte"] == 0
    assert b["back_dte"] is None
    assert b["defaults"]["pt_pct"] == 0.30
    assert b["defaults"]["sl_pct"] == 2.0
    assert b["defaults"]["sd_mult"] == 1.0
    assert b["defaults"]["eod_close_ct"] == "14:45"


def test_tide_defaults():
    b = get_bot("tide")
    assert b["strategy"] == "double_calendar"
    assert b["front_dte"] == 1
    assert b["back_dte"] == 14
    assert b["defaults"]["pt_pct"] == 0.50
    assert b["defaults"]["sl_pct"] == 1.0


def test_drift_defaults():
    b = get_bot("drift")
    assert b["strategy"] == "double_diagonal"
    assert b["front_dte"] == 1
    assert b["back_dte"] == 14
    assert b["defaults"]["delta_skew"] == 0


def test_get_bot_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_bot("nope")


def test_list_bots_returns_keys():
    assert sorted(list_bots()) == ["drift", "gust", "tide"]
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd C:/Users/lemol/alphagex/spreadworks
pytest tests/test_registry.py -v
```

Expected: `ModuleNotFoundError: backend.bots.registry`

- [ ] **Step 3: Create the package files**

`spreadworks/backend/bots/__init__.py`:

```python
"""SpreadWorks automated paper-trading bots (GUST / TIDE / DRIFT)."""
```

`spreadworks/backend/bots/registry.py`:

```python
"""Single source of truth for bot identity + config defaults.

When changing this file, mirror updates in
`spreadworks/frontend/src/lib/botRegistry.js`.
"""
from __future__ import annotations

from typing import Any

BOT_REGISTRY: dict[str, dict[str, Any]] = {
    "gust": {
        "display": "GUST",
        "strategy": "iron_butterfly",
        "ticker": "SPY",
        "front_dte": 0,
        "back_dte": None,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            "max_contracts": 2,
            "bp_pct": 0.10,
            "sd_mult": 1.0,
            "pt_pct": 0.30,
            "sl_pct": 2.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "10:30",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    "tide": {
        "display": "TIDE",
        "strategy": "double_calendar",
        "ticker": "SPY",
        "front_dte": 1,
        "back_dte": 14,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            "max_contracts": 2,
            "bp_pct": 0.10,
            "sd_mult": 1.0,
            "pt_pct": 0.50,
            "sl_pct": 1.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "10:30",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
    "drift": {
        "display": "DRIFT",
        "strategy": "double_diagonal",
        "ticker": "SPY",
        "front_dte": 1,
        "back_dte": 14,
        "defaults": {
            "starting_capital": 10000.0,
            "enabled": False,
            "max_contracts": 2,
            "bp_pct": 0.10,
            "sd_mult": 1.0,
            "pt_pct": 0.50,
            "sl_pct": 1.0,
            "entry_start_ct": "08:35",
            "entry_end_ct": "10:30",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
        },
    },
}


def list_bots() -> list[str]:
    return list(BOT_REGISTRY.keys())


def get_bot(bot: str) -> dict[str, Any]:
    if bot not in BOT_REGISTRY:
        raise KeyError(f"Unknown bot: {bot!r}. Known: {sorted(BOT_REGISTRY)}")
    return BOT_REGISTRY[bot]
```

- [ ] **Step 4: Run the test, confirm it passes**

```bash
pytest tests/test_registry.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/ spreadworks/tests/test_registry.py
git commit -m "feat(spreadworks): add BOT_REGISTRY for GUST/TIDE/DRIFT"
```

---

## Task 3: Bot table migration

**Files:**
- Create: `spreadworks/backend/bots/db.py`
- Create: `spreadworks/tests/test_bot_db.py`

- [ ] **Step 1: Write the failing test** — `spreadworks/tests/test_bot_db.py`

```python
from sqlalchemy import create_engine, inspect, text

from backend.bots.db import bot_table, create_bot_tables


def test_bot_table_naming():
    assert bot_table("gust", "config") == "gust_config"
    assert bot_table("tide", "positions") == "tide_positions"
    assert bot_table("drift", "scan_activity") == "drift_scan_activity"


def test_bot_table_rejects_unknown_bot():
    import pytest
    with pytest.raises(ValueError):
        bot_table("hacker", "positions")


def test_create_bot_tables_creates_all_15():
    engine = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(engine)
    insp = inspect(engine)
    names = set(insp.get_table_names())
    for bot in ["gust", "tide", "drift"]:
        for tbl in ["config", "positions", "closed_trades",
                    "equity_snapshots", "scan_activity"]:
            assert f"{bot}_{tbl}" in names, f"missing {bot}_{tbl}"


def test_create_bot_tables_seeds_config():
    engine = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(engine)
    with engine.begin() as conn:
        for bot in ["gust", "tide", "drift"]:
            row = conn.execute(
                text(f"SELECT pt_pct, sl_pct, enabled FROM {bot}_config")
            ).fetchone()
            assert row is not None, f"{bot}_config not seeded"
            assert row.enabled is False or row.enabled == 0


def test_create_bot_tables_does_not_overwrite_existing_config():
    """Memory rule: never auto-reset config values on restart."""
    engine = create_engine("sqlite:///:memory:", future=True)
    create_bot_tables(engine)
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE gust_config SET pt_pct = 0.99, max_contracts = 99"
        ))
    # Run migration a second time
    create_bot_tables(engine)
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT pt_pct, max_contracts FROM gust_config")
        ).fetchone()
        assert float(row.pt_pct) == 0.99
        assert row.max_contracts == 99
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_bot_db.py -v
```

Expected: `ModuleNotFoundError: backend.bots.db`

- [ ] **Step 3: Create `spreadworks/backend/bots/db.py`**

```python
"""Per-bot Postgres table helpers + idempotent migration.

Tables created (per bot in {gust, tide, drift}):
  {bot}_config            -- single-row config (1 = enabled, NULL/0 = disabled)
  {bot}_positions         -- open positions
  {bot}_closed_trades     -- realized P&L
  {bot}_equity_snapshots  -- equity curve points (1 per scan cycle)
  {bot}_scan_activity     -- scanner outcomes

Tables are created with `CREATE TABLE IF NOT EXISTS` and config rows are
seeded with `INSERT ... ON CONFLICT DO NOTHING` so a restart never
overwrites user-edited values (mirrors the IronForge SPARK config-lock fix).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .registry import BOT_REGISTRY, list_bots


def bot_table(bot: str, name: str) -> str:
    """Return `{bot}_{name}` after validating `bot` is registered."""
    if bot not in BOT_REGISTRY:
        raise ValueError(f"Unknown bot: {bot!r}. Known: {list_bots()}")
    return f"{bot}_{name}"


_CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    id                INTEGER PRIMARY KEY,
    starting_capital  NUMERIC(12,2) NOT NULL DEFAULT 10000,
    enabled           BOOLEAN NOT NULL DEFAULT 0,
    max_contracts     INTEGER NOT NULL DEFAULT 1,
    bp_pct            NUMERIC(4,3) NOT NULL DEFAULT 0.10,
    sd_mult           NUMERIC(4,2) NOT NULL DEFAULT 1.0,
    front_dte         INTEGER NOT NULL DEFAULT 0,
    back_dte          INTEGER,
    pt_pct            NUMERIC(5,4) NOT NULL DEFAULT 0.30,
    sl_pct            NUMERIC(5,4) NOT NULL DEFAULT 2.0,
    entry_start_ct    TEXT NOT NULL DEFAULT '08:35',
    entry_end_ct      TEXT NOT NULL DEFAULT '10:30',
    eod_close_ct      TEXT NOT NULL DEFAULT '14:45',
    discord_alerts    BOOLEAN NOT NULL DEFAULT 0,
    delta_skew        INTEGER NOT NULL DEFAULT 0,
    use_gex_walls     BOOLEAN NOT NULL DEFAULT 0,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_POSITIONS_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    position_id     TEXT PRIMARY KEY,
    ticker          TEXT NOT NULL DEFAULT 'SPY',
    strategy        TEXT NOT NULL,
    legs            TEXT NOT NULL,
    entry_price     NUMERIC(10,4) NOT NULL,
    contracts       INTEGER NOT NULL,
    entry_time      TIMESTAMP NOT NULL,
    status          TEXT NOT NULL DEFAULT 'OPEN',
    mtm_value       NUMERIC(10,4),
    mtm_pnl         NUMERIC(10,2),
    mtm_updated_at  TIMESTAMP,
    pt_target_pnl   NUMERIC(10,2) NOT NULL,
    sl_target_pnl   NUMERIC(10,2) NOT NULL,
    max_profit      NUMERIC(10,2) NOT NULL,
    max_loss        NUMERIC(10,2) NOT NULL,
    account_label   TEXT NOT NULL DEFAULT 'paper',
    notes           TEXT
)
"""

_CLOSED_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    position_id     TEXT PRIMARY KEY,
    close_price     NUMERIC(10,4) NOT NULL,
    close_time      TIMESTAMP NOT NULL,
    close_reason    TEXT NOT NULL,
    realized_pnl    NUMERIC(10,2) NOT NULL,
    contracts       INTEGER NOT NULL,
    legs            TEXT NOT NULL,
    entry_price     NUMERIC(10,4) NOT NULL,
    entry_time      TIMESTAMP NOT NULL,
    ticker          TEXT NOT NULL,
    strategy        TEXT NOT NULL
)
"""

_EQUITY_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time       TIMESTAMP NOT NULL,
    equity              NUMERIC(12,2) NOT NULL,
    unrealized_pnl      NUMERIC(10,2) NOT NULL DEFAULT 0,
    realized_pnl_today  NUMERIC(10,2) NOT NULL DEFAULT 0,
    cumulative_pnl      NUMERIC(10,2) NOT NULL DEFAULT 0,
    open_positions      INTEGER NOT NULL DEFAULT 0
)
"""

_SCAN_DDL = """
CREATE TABLE IF NOT EXISTS {t} (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_time       TIMESTAMP NOT NULL,
    outcome         TEXT NOT NULL,
    reason          TEXT,
    signal_data     TEXT,
    position_id     TEXT
)
"""

_TABLES = {
    "config": _CONFIG_DDL,
    "positions": _POSITIONS_DDL,
    "closed_trades": _CLOSED_DDL,
    "equity_snapshots": _EQUITY_DDL,
    "scan_activity": _SCAN_DDL,
}


def _is_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite"


def _autoincrement_for_dialect(ddl: str, engine: Engine) -> str:
    """Postgres uses SERIAL / BIGSERIAL, SQLite uses AUTOINCREMENT on INTEGER PK."""
    if _is_sqlite(engine):
        return ddl
    # Translate SQLite-style PKs to Postgres SERIAL.
    return (
        ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
           .replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
    )


def create_bot_tables(engine: Engine) -> None:
    """Create all per-bot tables and seed a config row per bot.

    Idempotent — safe to call on every startup.
    """
    with engine.begin() as conn:
        for bot in list_bots():
            for short, ddl in _TABLES.items():
                t = bot_table(bot, short)
                conn.execute(text(_autoincrement_for_dialect(ddl.format(t=t), engine)))
        # Seed config rows — ON CONFLICT DO NOTHING means restart never
        # overwrites user-edited values.
        for bot in list_bots():
            d = BOT_REGISTRY[bot]
            defs = d["defaults"]
            t = bot_table(bot, "config")
            if _is_sqlite(engine):
                # SQLite uses INSERT OR IGNORE
                stmt = text(
                    f"INSERT OR IGNORE INTO {t} ("
                    "id, starting_capital, enabled, max_contracts, bp_pct, sd_mult, "
                    "front_dte, back_dte, pt_pct, sl_pct, entry_start_ct, entry_end_ct, "
                    "eod_close_ct, discord_alerts, delta_skew, use_gex_walls"
                    ") VALUES ("
                    ":id, :sc, :en, :mc, :bp, :sd, :fdte, :bdte, :pt, :sl, "
                    ":es, :ee, :eod, :dc, :ds, :gw"
                    ")"
                )
            else:
                stmt = text(
                    f"INSERT INTO {t} ("
                    "id, starting_capital, enabled, max_contracts, bp_pct, sd_mult, "
                    "front_dte, back_dte, pt_pct, sl_pct, entry_start_ct, entry_end_ct, "
                    "eod_close_ct, discord_alerts, delta_skew, use_gex_walls"
                    ") VALUES ("
                    ":id, :sc, :en, :mc, :bp, :sd, :fdte, :bdte, :pt, :sl, "
                    ":es, :ee, :eod, :dc, :ds, :gw"
                    ") ON CONFLICT (id) DO NOTHING"
                )
            conn.execute(stmt, {
                "id": 1,
                "sc": defs["starting_capital"],
                "en": defs["enabled"],
                "mc": defs["max_contracts"],
                "bp": defs["bp_pct"],
                "sd": defs["sd_mult"],
                "fdte": d["front_dte"],
                "bdte": d["back_dte"],
                "pt": defs["pt_pct"],
                "sl": defs["sl_pct"],
                "es": defs["entry_start_ct"],
                "ee": defs["entry_end_ct"],
                "eod": defs["eod_close_ct"],
                "dc": defs["discord_alerts"],
                "ds": defs["delta_skew"],
                "gw": defs["use_gex_walls"],
            })


def load_config(engine: Engine, bot: str) -> dict[str, Any]:
    """Read the (single-row) config for `bot`."""
    t = bot_table(bot, "config")
    with engine.begin() as conn:
        row = conn.execute(text(f"SELECT * FROM {t} WHERE id = 1")).mappings().first()
    if row is None:
        raise RuntimeError(f"{t} not seeded — call create_bot_tables() first")
    return dict(row)
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_bot_db.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/db.py spreadworks/tests/test_bot_db.py
git commit -m "feat(spreadworks): per-bot tables + idempotent seed migration"
```

---

## Task 4: GUST strategy (Iron Butterfly entry)

**Files:**
- Create: `spreadworks/backend/bots/strategies/__init__.py` (empty)
- Create: `spreadworks/backend/bots/strategies/iron_butterfly.py`
- Create: `spreadworks/tests/test_iron_butterfly.py`

- [ ] **Step 1: Write the failing tests** — `spreadworks/tests/test_iron_butterfly.py`

```python
import pytest

from backend.bots.strategies.iron_butterfly import (
    build_iron_butterfly_signal,
    IronButterflySignal,
)


def _config(**overrides):
    base = {
        "starting_capital": 10000,
        "max_contracts": 2,
        "bp_pct": 0.10,
        "sd_mult": 1.0,
        "pt_pct": 0.30,
        "sl_pct": 2.0,
        "use_gex_walls": False,
    }
    base.update(overrides)
    return base


def test_picks_atm_body_and_symmetric_wings(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    assert sig.body_strike == 500
    # Wing distance = 1.0 * 4.0 * 0.85 ~= 3.4 -> round to 3 -> wings at 497/503
    assert sig.long_put_strike == 497
    assert sig.long_call_strike == 503


def test_skips_when_vix_too_high(fake_chain_0dte):
    chain = {**fake_chain_0dte, "vix": 30.0}
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_skips_when_flip_too_close(fake_chain_0dte):
    chain = {**fake_chain_0dte, "gex": {"flip_point": 500.5, "call_wall": 505, "put_wall": 496}}
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_skips_when_credit_below_floor(fake_chain_0dte):
    # Squeeze all premiums to ~zero to force credit < 0.30
    chain = {
        **fake_chain_0dte,
        "options": [
            {**o, "bid": 0.01, "ask": 0.02} for o in fake_chain_0dte["options"]
        ],
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(), equity=10000.0
    )
    assert sig is None


def test_credit_sizing(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    # Body credit = (2.05 + 2.05) - (0.55 + 0.55) but with 1c slippage either side.
    # We expect a positive credit and contracts >= 1.
    assert sig.credit > 0.30
    assert sig.contracts >= 1
    assert sig.contracts <= 2  # bounded by max_contracts


def test_gex_walls_clip_wings(fake_chain_0dte):
    # call_wall=505 sits OUTSIDE the computed wing (503) so clipping should
    # not change call wing, but put_wall=496 also outside put wing (497).
    # Move put_wall inside to verify clipping.
    chain = {
        **fake_chain_0dte,
        "gex": {"flip_point": 502.0, "call_wall": 505.0, "put_wall": 498.0},
    }
    sig = build_iron_butterfly_signal(
        chain=chain, config=_config(use_gex_walls=True), equity=10000.0
    )
    assert sig is not None
    # Put wing clipped UP to put_wall (closer to body)
    assert sig.long_put_strike == 498


def test_returns_legs_in_signal(fake_chain_0dte):
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte, config=_config(), equity=10000.0
    )
    assert sig is not None
    legs = sig.legs()
    assert len(legs) == 4
    sides = {(l["side"], l["type"]) for l in legs}
    assert sides == {("short", "call"), ("short", "put"),
                     ("long", "call"), ("long", "put")}
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_iron_butterfly.py -v
```

Expected: import error.

- [ ] **Step 3: Implement strategy** — `spreadworks/backend/bots/strategies/__init__.py` (empty file) then `spreadworks/backend/bots/strategies/iron_butterfly.py`:

```python
"""GUST — Iron Butterfly 0DTE entry signal builder.

Pure function `build_iron_butterfly_signal(chain, config, equity)` returns
an `IronButterflySignal` dataclass or `None` if no setup passes the gates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MIN_CREDIT = 0.30
MAX_VIX = 28.0
MIN_FLIP_DIST = 1.0


@dataclass
class IronButterflySignal:
    ticker: str
    expiration: str
    body_strike: int
    long_put_strike: int
    long_call_strike: int
    short_call_mid: float
    short_put_mid: float
    long_call_mid: float
    long_put_mid: float
    credit: float
    contracts: int
    max_profit: float        # per contract, $
    max_loss: float          # per contract, $
    wing_width: int
    pt_target_pnl: float     # $ total
    sl_target_pnl: float     # $ total

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "call", "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.short_call_mid},
            {"side": "short", "type": "put",  "strike": self.body_strike,
             "expiration": self.expiration, "entry_price": self.short_put_mid},
            {"side": "long",  "type": "call", "strike": self.long_call_strike,
             "expiration": self.expiration, "entry_price": self.long_call_mid},
            {"side": "long",  "type": "put",  "strike": self.long_put_strike,
             "expiration": self.expiration, "entry_price": self.long_put_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find_option(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def build_iron_butterfly_signal(
    *,
    chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
) -> IronButterflySignal | None:
    spot = float(chain["spot"])
    vix = float(chain.get("vix", 0))
    if vix >= MAX_VIX:
        return None

    gex = chain.get("gex") or {}
    flip = gex.get("flip_point")
    if flip is not None and abs(float(flip) - spot) < MIN_FLIP_DIST:
        return None

    atm_straddle = float(chain.get("atm_straddle_mid", 0))
    sd_mult = float(config.get("sd_mult", 1.0))
    wing_distance = max(1, round(sd_mult * atm_straddle * 0.85))

    body = round(spot)
    long_call_strike = body + wing_distance
    long_put_strike = body - wing_distance

    if config.get("use_gex_walls"):
        cw = gex.get("call_wall")
        pw = gex.get("put_wall")
        if cw is not None and body < cw < long_call_strike:
            long_call_strike = int(round(cw))
        if pw is not None and long_put_strike < pw < body:
            long_put_strike = int(round(pw))

    short_call = _find_option(chain, body, "call")
    short_put = _find_option(chain, body, "put")
    long_call = _find_option(chain, long_call_strike, "call")
    long_put = _find_option(chain, long_put_strike, "put")
    if not all([short_call, short_put, long_call, long_put]):
        return None

    sc_mid, sp_mid = _mid(short_call), _mid(short_put)
    lc_mid, lp_mid = _mid(long_call), _mid(long_put)
    credit = round(sc_mid + sp_mid - lc_mid - lp_mid, 4)
    if credit < MIN_CREDIT:
        return None

    wing_width_call = long_call_strike - body
    wing_width_put = body - long_put_strike
    wing_width = min(wing_width_call, wing_width_put)
    max_profit_per = credit * 100.0
    max_loss_per = (wing_width - credit) * 100.0
    if max_loss_per <= 0:
        return None

    bp_pct = float(config.get("bp_pct", 0.10))
    max_contracts = int(config.get("max_contracts", 1))
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = max(0, min(max_contracts, raw_contracts))
    if contracts < 1:
        return None

    pt_pct = float(config.get("pt_pct", 0.30))
    sl_pct = float(config.get("sl_pct", 2.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_profit_per * contracts

    return IronButterflySignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        body_strike=body,
        long_put_strike=long_put_strike,
        long_call_strike=long_call_strike,
        short_call_mid=sc_mid,
        short_put_mid=sp_mid,
        long_call_mid=lc_mid,
        long_put_mid=lp_mid,
        credit=credit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        wing_width=wing_width,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_iron_butterfly.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/strategies/ spreadworks/tests/test_iron_butterfly.py
git commit -m "feat(spreadworks): GUST iron butterfly entry signal"
```

---

## Task 5: TIDE strategy (Double Calendar entry)

**Files:**
- Create: `spreadworks/backend/bots/strategies/double_calendar.py`
- Create: `spreadworks/tests/test_double_calendar.py`

- [ ] **Step 1: Write tests** — `spreadworks/tests/test_double_calendar.py`

```python
from backend.bots.strategies.double_calendar import (
    build_double_calendar_signal,
    DoubleCalendarSignal,
)


def _cfg(**o):
    base = {"max_contracts": 2, "bp_pct": 0.10, "pt_pct": 0.50,
            "sl_pct": 1.0, "starting_capital": 10000}
    base.update(o); return base


def test_picks_strikes_at_implied_move(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    # implied_move from 1dte ATM straddle mid = 5.0; spot=500
    # call_strike = round(500 + 5) = 505; put_strike = round(500 - 5) = 495
    assert sig.call_strike == 505
    assert sig.put_strike == 495


def test_legs_use_same_strikes_different_expirations(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    legs = sig.legs()
    assert len(legs) == 4
    short_legs = [l for l in legs if l["side"] == "short"]
    long_legs = [l for l in legs if l["side"] == "long"]
    assert {l["expiration"] for l in short_legs} == {fake_chain_1dte["expiration"]}
    assert {l["expiration"] for l in long_legs} == {fake_chain_14dte["expiration"]}


def test_skips_when_back_iv_not_higher(fake_chain_1dte, fake_chain_14dte):
    flat = {**fake_chain_14dte, "iv_atm": 0.16}  # equal to front
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=flat,
        config=_cfg(), equity=10000.0,
    )
    assert sig is None


def test_skips_when_vix_too_high(fake_chain_1dte, fake_chain_14dte):
    spiked = {**fake_chain_1dte, "vix": 32.0}
    sig = build_double_calendar_signal(
        front_chain=spiked, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is None


def test_debit_is_positive(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_calendar_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig.debit > 0.20
    assert sig.contracts >= 1
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_double_calendar.py -v
```

- [ ] **Step 3: Implement** — `spreadworks/backend/bots/strategies/double_calendar.py`

```python
"""TIDE — Double Calendar entry signal builder.

Sells 1DTE strangle (put + call OTM), buys 14DTE strangle at SAME strikes.
Vega-positive, mildly theta-positive when back IV > front IV.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MIN_DEBIT = 0.20
MAX_DEBIT = 5.0
MAX_VIX = 30.0
MIN_VEGA_EDGE = 1.0  # back_iv - front_iv in vol points (0.01 = 1 vp)


@dataclass
class DoubleCalendarSignal:
    ticker: str
    front_expiration: str
    back_expiration: str
    call_strike: int
    put_strike: int
    short_front_call_mid: float
    short_front_put_mid: float
    long_back_call_mid: float
    long_back_put_mid: float
    debit: float
    contracts: int
    max_profit: float        # per contract, $ (target reference = debit)
    max_loss: float          # per contract, $ (entire debit)
    pt_target_pnl: float
    sl_target_pnl: float

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "call", "strike": self.call_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_call_mid},
            {"side": "short", "type": "put",  "strike": self.put_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_put_mid},
            {"side": "long",  "type": "call", "strike": self.call_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_call_mid},
            {"side": "long",  "type": "put",  "strike": self.put_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_put_mid},
        ]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _find(chain: dict, strike: int, opt_type: str) -> dict | None:
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def build_double_calendar_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    call_strike_override: int | None = None,
    put_strike_override: int | None = None,
) -> DoubleCalendarSignal | None:
    spot = float(front_chain["spot"])
    vix = float(front_chain.get("vix", 0))
    if vix >= MAX_VIX:
        return None

    front_iv = float(front_chain.get("iv_atm", 0))
    back_iv = float(back_chain.get("iv_atm", 0))
    # vol-point gap (0.01 per vp)
    if (back_iv - front_iv) < (MIN_VEGA_EDGE / 100.0):
        return None

    implied_move = float(front_chain.get("atm_straddle_mid", 0))
    if implied_move <= 0:
        return None

    call_strike = call_strike_override if call_strike_override is not None else round(spot + implied_move)
    put_strike = put_strike_override if put_strike_override is not None else round(spot - implied_move)

    sfc = _find(front_chain, call_strike, "call")
    sfp = _find(front_chain, put_strike, "put")
    lbc = _find(back_chain, call_strike, "call")
    lbp = _find(back_chain, put_strike, "put")
    if not all([sfc, sfp, lbc, lbp]):
        return None

    sfc_m, sfp_m = _mid(sfc), _mid(sfp)
    lbc_m, lbp_m = _mid(lbc), _mid(lbp)
    debit = round((lbc_m + lbp_m) - (sfc_m + sfp_m), 4)
    if debit < MIN_DEBIT or debit > MAX_DEBIT:
        return None

    max_loss_per = debit * 100.0
    max_profit_per = debit * 100.0  # PT reference: % of debit

    bp_pct = float(config.get("bp_pct", 0.10))
    max_contracts = int(config.get("max_contracts", 1))
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = max(0, min(max_contracts, raw_contracts))
    if contracts < 1:
        return None

    pt_pct = float(config.get("pt_pct", 0.50))
    sl_pct = float(config.get("sl_pct", 1.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_loss_per * contracts

    return DoubleCalendarSignal(
        ticker=front_chain.get("ticker", "SPY"),
        front_expiration=front_chain["expiration"],
        back_expiration=back_chain["expiration"],
        call_strike=call_strike,
        put_strike=put_strike,
        short_front_call_mid=sfc_m,
        short_front_put_mid=sfp_m,
        long_back_call_mid=lbc_m,
        long_back_put_mid=lbp_m,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
    )
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_double_calendar.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/strategies/double_calendar.py spreadworks/tests/test_double_calendar.py
git commit -m "feat(spreadworks): TIDE double calendar entry signal"
```

---

## Task 6: DRIFT strategy (Double Diagonal entry)

**Files:**
- Create: `spreadworks/backend/bots/strategies/double_diagonal.py`
- Create: `spreadworks/tests/test_double_diagonal.py`

- [ ] **Step 1: Write tests** — `spreadworks/tests/test_double_diagonal.py`

```python
from backend.bots.strategies.double_diagonal import (
    build_double_diagonal_signal,
)


def _cfg(**o):
    base = {"max_contracts": 2, "bp_pct": 0.10, "pt_pct": 0.50,
            "sl_pct": 1.0, "starting_capital": 10000, "delta_skew": 0}
    base.update(o); return base


def test_back_strikes_shifted_one_otm(fake_chain_1dte, fake_chain_14dte):
    sig = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(), equity=10000.0,
    )
    assert sig is not None
    # front call=505, back call should be 506
    assert sig.short_call_strike == 505
    assert sig.long_call_strike == 506
    # front put=495, back put should be 494
    assert sig.short_put_strike == 495
    assert sig.long_put_strike == 494


def test_delta_skew_shifts_back_strikes(fake_chain_1dte, fake_chain_14dte):
    # Need a chain with strikes 506/507 available. Extend the 14dte fixture
    # behavior at test-time isn't possible without modifying fixture; verify
    # the math via mismatching strike override path instead.
    # Approach: with delta_skew=1, both back strikes shift up by 1.
    # With our fixture, long_back_call=506 -> 507 and long_back_put=494 -> 495.
    # Our 14dte fixture has 495 put and 504 call but not 507 call. Expect None.
    sig = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=fake_chain_14dte,
        config=_cfg(delta_skew=1), equity=10000.0,
    )
    # 507 call not in fixture -> returns None
    assert sig is None


def test_skips_when_back_iv_not_higher(fake_chain_1dte, fake_chain_14dte):
    flat = {**fake_chain_14dte, "iv_atm": 0.16}
    sig = build_double_diagonal_signal(
        front_chain=fake_chain_1dte, back_chain=flat,
        config=_cfg(), equity=10000.0,
    )
    assert sig is None
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Implement** — `spreadworks/backend/bots/strategies/double_diagonal.py`

```python
"""DRIFT — Double Diagonal entry signal builder.

Identical to Double Calendar but the long-back strikes are shifted 1 OTM
relative to the short-front strikes (call up, put down). Optional
`delta_skew` config knob shifts BOTH back strikes by N (bullish if +).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .double_calendar import (
    MIN_DEBIT, MAX_DEBIT, MAX_VIX, MIN_VEGA_EDGE, _mid, _find,
)


@dataclass
class DoubleDiagonalSignal:
    ticker: str
    front_expiration: str
    back_expiration: str
    short_call_strike: int
    short_put_strike: int
    long_call_strike: int
    long_put_strike: int
    short_front_call_mid: float
    short_front_put_mid: float
    long_back_call_mid: float
    long_back_put_mid: float
    debit: float
    contracts: int
    max_profit: float
    max_loss: float
    pt_target_pnl: float
    sl_target_pnl: float
    delta_skew: int

    def legs(self) -> list[dict[str, Any]]:
        return [
            {"side": "short", "type": "call", "strike": self.short_call_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_call_mid},
            {"side": "short", "type": "put",  "strike": self.short_put_strike,
             "expiration": self.front_expiration, "entry_price": self.short_front_put_mid},
            {"side": "long",  "type": "call", "strike": self.long_call_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_call_mid},
            {"side": "long",  "type": "put",  "strike": self.long_put_strike,
             "expiration": self.back_expiration,  "entry_price": self.long_back_put_mid},
        ]


def build_double_diagonal_signal(
    *,
    front_chain: dict[str, Any],
    back_chain: dict[str, Any],
    config: dict[str, Any],
    equity: float,
) -> DoubleDiagonalSignal | None:
    spot = float(front_chain["spot"])
    vix = float(front_chain.get("vix", 0))
    if vix >= MAX_VIX:
        return None

    front_iv = float(front_chain.get("iv_atm", 0))
    back_iv = float(back_chain.get("iv_atm", 0))
    if (back_iv - front_iv) < (MIN_VEGA_EDGE / 100.0):
        return None

    implied_move = float(front_chain.get("atm_straddle_mid", 0))
    if implied_move <= 0:
        return None

    skew = int(config.get("delta_skew", 0))
    short_call_strike = round(spot + implied_move)
    short_put_strike = round(spot - implied_move)
    long_call_strike = short_call_strike + 1 + skew
    long_put_strike = short_put_strike - 1 + skew

    sfc = _find(front_chain, short_call_strike, "call")
    sfp = _find(front_chain, short_put_strike, "put")
    lbc = _find(back_chain, long_call_strike, "call")
    lbp = _find(back_chain, long_put_strike, "put")
    if not all([sfc, sfp, lbc, lbp]):
        return None

    sfc_m, sfp_m = _mid(sfc), _mid(sfp)
    lbc_m, lbp_m = _mid(lbc), _mid(lbp)
    debit = round((lbc_m + lbp_m) - (sfc_m + sfp_m), 4)
    if debit < MIN_DEBIT or debit > MAX_DEBIT:
        return None

    max_loss_per = (debit + 1.0) * 100.0  # debit + 1-strike width worst case
    max_profit_per = debit * 100.0

    bp_pct = float(config.get("bp_pct", 0.10))
    max_contracts = int(config.get("max_contracts", 1))
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = max(0, min(max_contracts, raw_contracts))
    if contracts < 1:
        return None

    pt_pct = float(config.get("pt_pct", 0.50))
    sl_pct = float(config.get("sl_pct", 1.0))
    pt_target = pt_pct * max_profit_per * contracts
    sl_target = sl_pct * max_loss_per * contracts

    return DoubleDiagonalSignal(
        ticker=front_chain.get("ticker", "SPY"),
        front_expiration=front_chain["expiration"],
        back_expiration=back_chain["expiration"],
        short_call_strike=short_call_strike,
        short_put_strike=short_put_strike,
        long_call_strike=long_call_strike,
        long_put_strike=long_put_strike,
        short_front_call_mid=sfc_m,
        short_front_put_mid=sfp_m,
        long_back_call_mid=lbc_m,
        long_back_put_mid=lbp_m,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        pt_target_pnl=pt_target,
        sl_target_pnl=sl_target,
        delta_skew=skew,
    )
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_double_diagonal.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/strategies/double_diagonal.py spreadworks/tests/test_double_diagonal.py
git commit -m "feat(spreadworks): DRIFT double diagonal entry signal"
```

---

## Task 7: Executor (open/close/MTM)

**Files:**
- Create: `spreadworks/backend/bots/executor.py`
- Create: `spreadworks/tests/test_executor.py`

- [ ] **Step 1: Write tests** — `spreadworks/tests/test_executor.py`

```python
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.bots.executor import (
    open_position, close_position, compute_mtm, list_open_positions,
    account_equity,
)
from backend.bots.strategies.iron_butterfly import build_iron_butterfly_signal

CT = ZoneInfo("America/Chicago")


def test_open_and_list_position(db_session, fake_chain_0dte):
    engine = db_session.bind
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 2, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    assert sig is not None
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    pid = open_position(engine, bot="gust", strategy="iron_butterfly",
                        signal=sig, now=now)
    assert pid.startswith("gust-2026-05-20-")
    opens = list_open_positions(engine, "gust")
    assert len(opens) == 1
    assert opens[0]["position_id"] == pid
    legs = json.loads(opens[0]["legs"])
    assert len(legs) == 4


def test_close_writes_to_closed_trades(db_session, fake_chain_0dte):
    engine = db_session.bind
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    pid = open_position(engine, "gust", "iron_butterfly", sig, now)
    later = datetime(2026, 5, 20, 11, 0, tzinfo=CT)
    close_position(engine, bot="gust", position_id=pid,
                   close_value=sig.credit * 0.7, close_reason="PT", now=later)
    with engine.begin() as conn:
        ct = conn.execute(text(
            "SELECT * FROM gust_closed_trades WHERE position_id=:p"
        ), {"p": pid}).mappings().first()
    assert ct is not None
    assert ct["close_reason"] == "PT"
    assert float(ct["realized_pnl"]) > 0  # we received credit, bought back cheaper
    # original position now CLOSED
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT status FROM gust_positions WHERE position_id=:p"
        ), {"p": pid}).mappings().first()
    assert row["status"] == "CLOSED"


def test_compute_mtm_credit_strategy(fake_chain_0dte):
    """For an IBF (credit), MTM PnL = (entry_credit - cost_to_close) * contracts * 100."""
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    legs = sig.legs()
    cost_to_close = sig.credit * 0.5  # halved
    mtm_value, mtm_pnl = compute_mtm(
        strategy="iron_butterfly",
        legs=legs,
        entry_price=sig.credit,
        contracts=sig.contracts,
        leg_mids=[l["entry_price"] for l in legs],  # unused for this test path
        cost_to_close_override=cost_to_close,
    )
    expected = (sig.credit - cost_to_close) * sig.contracts * 100
    assert abs(mtm_pnl - expected) < 0.01


def test_account_equity_starts_at_config(db_session):
    engine = db_session.bind
    eq = account_equity(engine, "gust")
    assert eq == 10000.0
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Implement** — `spreadworks/backend/bots/executor.py`

```python
"""Paper-trade executor — open / close / MTM for one bot.

NO BROKER CALLS. Fills use mid prices passed in by the caller; this module
never imports anything from Tradier. Keeps the paper-only invariant explicit.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import bot_table, load_config

logger = logging.getLogger("spreadworks.bots.executor")


def account_equity(engine: Engine, bot: str) -> float:
    """starting_capital + cumulative realized P&L (closed trades)."""
    cfg = load_config(engine, bot)
    t = bot_table(bot, "closed_trades")
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT COALESCE(SUM(realized_pnl), 0) AS s FROM {t}"
        )).mappings().first()
    return float(cfg["starting_capital"]) + float(row["s"] or 0)


def _new_position_id(bot: str, now: datetime) -> str:
    return f"{bot}-{now.date().isoformat()}-{uuid.uuid4().hex[:8]}"


def open_position(
    engine: Engine,
    bot: str,
    strategy: str,
    signal: Any,
    now: datetime,
) -> str:
    """Insert one OPEN row into {bot}_positions, return position_id."""
    pid = _new_position_id(bot, now)
    t = bot_table(bot, "positions")
    # All signals expose .legs(), .pt_target_pnl, .sl_target_pnl, .max_profit,
    # .max_loss, .contracts, .ticker plus EITHER .credit (IBF) OR .debit (DC/DD).
    entry_price = getattr(signal, "credit", None) or getattr(signal, "debit")
    legs_json = json.dumps(signal.legs())
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {t} ("
            "position_id, ticker, strategy, legs, entry_price, contracts, entry_time, "
            "status, mtm_value, mtm_pnl, mtm_updated_at, pt_target_pnl, sl_target_pnl, "
            "max_profit, max_loss, account_label"
            ") VALUES ("
            ":pid, :tk, :st, :legs, :ep, :ct, :et, 'OPEN', :mv, 0, :et, "
            ":pt, :sl, :mp, :ml, 'paper'"
            ")"
        ), {
            "pid": pid, "tk": signal.ticker, "st": strategy, "legs": legs_json,
            "ep": entry_price, "ct": signal.contracts, "et": now,
            "mv": entry_price,
            "pt": signal.pt_target_pnl, "sl": signal.sl_target_pnl,
            "mp": signal.max_profit * signal.contracts,
            "ml": signal.max_loss * signal.contracts,
        })
    logger.info(f"[{bot}] opened {pid} {strategy} entry={entry_price} contracts={signal.contracts}")
    return pid


def close_position(
    engine: Engine,
    bot: str,
    position_id: str,
    close_value: float,
    close_reason: str,
    now: datetime,
) -> float:
    """Move position OPEN -> CLOSED. Returns realized_pnl ($)."""
    t_pos = bot_table(bot, "positions")
    t_cls = bot_table(bot, "closed_trades")
    with engine.begin() as conn:
        row = conn.execute(text(
            f"SELECT * FROM {t_pos} WHERE position_id=:p AND status='OPEN'"
        ), {"p": position_id}).mappings().first()
        if row is None:
            raise ValueError(f"{position_id} not OPEN (already closed or unknown)")

        strategy = row["strategy"]
        entry_price = float(row["entry_price"])
        contracts = int(row["contracts"])
        if strategy == "iron_butterfly":
            realized = (entry_price - float(close_value)) * contracts * 100.0
        else:
            realized = (float(close_value) - entry_price) * contracts * 100.0

        conn.execute(text(
            f"UPDATE {t_pos} SET status='CLOSED', "
            "mtm_value=:cv, mtm_pnl=:rp, mtm_updated_at=:n "
            "WHERE position_id=:p"
        ), {"cv": close_value, "rp": realized, "n": now, "p": position_id})

        conn.execute(text(
            f"INSERT INTO {t_cls} ("
            "position_id, close_price, close_time, close_reason, realized_pnl, "
            "contracts, legs, entry_price, entry_time, ticker, strategy"
            ") VALUES ("
            ":pid, :cp, :ct, :cr, :rp, :con, :legs, :ep, :et, :tk, :st"
            ")"
        ), {
            "pid": position_id, "cp": close_value, "ct": now, "cr": close_reason,
            "rp": realized, "con": contracts, "legs": row["legs"],
            "ep": entry_price, "et": row["entry_time"],
            "tk": row["ticker"], "st": strategy,
        })
    logger.info(f"[{bot}] closed {position_id} reason={close_reason} pnl={realized:.2f}")
    return realized


def list_open_positions(engine: Engine, bot: str) -> list[dict[str, Any]]:
    t = bot_table(bot, "positions")
    with engine.begin() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM {t} WHERE status='OPEN' ORDER BY entry_time"
        )).mappings().all()
    return [dict(r) for r in rows]


def compute_mtm(
    *,
    strategy: str,
    legs: list[dict[str, Any]],
    entry_price: float,
    contracts: int,
    leg_mids: Iterable[float] | None = None,
    cost_to_close_override: float | None = None,
) -> tuple[float, float]:
    """Return (mtm_value, mtm_pnl).

    `leg_mids` must align with `legs` (same order). Each mid is the current
    market mid for that leg.

    For Iron Butterfly: mtm_value = short_call + short_put - long_call - long_put
        i.e. the cost to BUY BACK the structure (positive = it costs to close).
    For Double Calendar / Diagonal: mtm_value = long_back_call + long_back_put -
        short_front_call - short_front_put — i.e. the credit you'd RECEIVE to close.

    `cost_to_close_override` is used in tests to bypass the leg arithmetic.
    """
    if cost_to_close_override is not None:
        mtm_value = float(cost_to_close_override)
    else:
        mids = list(leg_mids or [])
        if len(mids) != len(legs):
            raise ValueError("leg_mids length mismatch")
        signed = 0.0
        for leg, m in zip(legs, mids):
            sign = 1.0 if leg["side"] == "short" else -1.0
            # IBF: closing buys back shorts (+) and sells longs (-)
            # DC/DD: closing buys back front shorts (+) and sells back longs (-)
            # Same sign convention works for both because we always compute
            # "cost to unwind from this side"; we invert for debit strats in
            # the PnL calculation below.
            signed += sign * m
        mtm_value = signed

    if strategy == "iron_butterfly":
        mtm_pnl = (entry_price - mtm_value) * contracts * 100.0
    else:
        # For debit strats, mtm_value above is signed as "cost to buy in",
        # but for DC/DD we want "current credit to unwind" — flip sign:
        mtm_value = -mtm_value
        mtm_pnl = (mtm_value - entry_price) * contracts * 100.0
    return round(mtm_value, 4), round(mtm_pnl, 2)


def update_mtm(engine: Engine, bot: str, position_id: str,
               mtm_value: float, mtm_pnl: float, now: datetime) -> None:
    t = bot_table(bot, "positions")
    with engine.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET mtm_value=:v, mtm_pnl=:p, mtm_updated_at=:n "
            "WHERE position_id=:pid"
        ), {"v": mtm_value, "p": mtm_pnl, "n": now, "pid": position_id})
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_executor.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/executor.py spreadworks/tests/test_executor.py
git commit -m "feat(spreadworks): executor open/close/MTM (paper-only)"
```

---

## Task 8: Monitor (PT / SL / EOD / event-halt decision)

**Files:**
- Create: `spreadworks/backend/bots/monitor.py`
- Create: `spreadworks/tests/test_monitor.py`

- [ ] **Step 1: Write tests** — `spreadworks/tests/test_monitor.py`

```python
from datetime import datetime, time, date
from zoneinfo import ZoneInfo

from backend.bots.monitor import (
    decide_exit, ExitDecision, eod_close_time_for_strategy,
    pt_pct_for_time_of_day,
)

CT = ZoneInfo("America/Chicago")


def test_pt_hit_returns_pt():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=50.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 11, 0, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "PT"


def test_sl_hit_returns_sl():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=-310.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 11, 0, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "SL"


def test_gust_eod_force_close():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 14, 46, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "EOD"


def test_tide_holds_overnight_when_not_expiry_day():
    d = decide_exit(
        strategy="double_calendar", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 14, 46, tzinfo=CT),
        front_expiration=date(2026, 5, 21),  # tomorrow
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert not d.should_close


def test_tide_closes_on_expiry_day_after_eod():
    d = decide_exit(
        strategy="double_calendar", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 21, 14, 46, tzinfo=CT),
        front_expiration=date(2026, 5, 21),
        eod_close_ct=time(14, 45),
        event_blackout=False,
    )
    assert d.should_close
    assert d.reason == "EOD"


def test_event_blackout_closes():
    d = decide_exit(
        strategy="iron_butterfly", mtm_pnl=10.0,
        pt_target_pnl=45.0, sl_target_pnl=300.0,
        now_ct=datetime(2026, 5, 20, 11, 0, tzinfo=CT),
        front_expiration=date(2026, 5, 20),
        eod_close_ct=time(14, 45),
        event_blackout=True,
    )
    assert d.should_close
    assert d.reason == "EVENT_HALT"


def test_pt_ladder_morning_midday_afternoon():
    # MORNING -> 0.30, MIDDAY -> 0.40, AFTERNOON -> 0.50
    assert pt_pct_for_time_of_day(time(9, 0)) == 0.30
    assert pt_pct_for_time_of_day(time(11, 30)) == 0.40
    assert pt_pct_for_time_of_day(time(13, 30)) == 0.50
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Implement** — `spreadworks/backend/bots/monitor.py`

```python
"""Shared exit decision logic for all 3 bots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time


@dataclass
class ExitDecision:
    should_close: bool
    reason: str | None  # PT | SL | EOD | EVENT_HALT | None


def pt_pct_for_time_of_day(now_ct_time: time) -> float:
    """GUST-only profit-target ladder.

    MORNING (open-11:00 CT) -> 0.30
    MIDDAY  (11:00-13:00 CT) -> 0.40
    AFTERNOON (13:00+)        -> 0.50

    Ported from IronForge SPARK fix-2.
    """
    if now_ct_time < time(11, 0):
        return 0.30
    if now_ct_time < time(13, 0):
        return 0.40
    return 0.50


def eod_close_time_for_strategy(strategy: str, eod_close_ct: time) -> time:
    return eod_close_ct  # currently uniform; kept for future per-strategy tweaks


def decide_exit(
    *,
    strategy: str,
    mtm_pnl: float,
    pt_target_pnl: float,
    sl_target_pnl: float,
    now_ct: datetime,
    front_expiration: date,
    eod_close_ct: time,
    event_blackout: bool,
) -> ExitDecision:
    if event_blackout:
        return ExitDecision(True, "EVENT_HALT")

    if mtm_pnl >= pt_target_pnl:
        return ExitDecision(True, "PT")
    if mtm_pnl <= -abs(sl_target_pnl):
        return ExitDecision(True, "SL")

    eod = eod_close_time_for_strategy(strategy, eod_close_ct)
    if strategy == "iron_butterfly":
        if now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")
    else:
        # DC / DD only force-close on the day the FRONT leg expires
        if now_ct.date() == front_expiration and now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")

    return ExitDecision(False, None)
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_monitor.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/monitor.py spreadworks/tests/test_monitor.py
git commit -m "feat(spreadworks): shared PT/SL/EOD/event-halt decision logic"
```

---

## Task 9: Scanner (per-bot orchestration)

**Files:**
- Create: `spreadworks/backend/bots/scanner.py`
- Create: `spreadworks/tests/test_scanner.py`

This task wires the registry + strategies + executor + monitor together,
including the 15-second per-bot timeout from the spec.

- [ ] **Step 1: Write tests** — `spreadworks/tests/test_scanner.py`

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from backend.bots.scanner import run_scan_cycle, ChainProvider

CT = ZoneInfo("America/Chicago")


class FakeChainProvider(ChainProvider):
    def __init__(self, *, chain_0dte=None, chain_1dte=None, chain_14dte=None):
        self.c0 = chain_0dte; self.c1 = chain_1dte; self.c14 = chain_14dte
        self.calls = 0
        self.leg_mid_overrides = None  # if set, get_leg_mids returns this

    def get_chain(self, *, ticker, dte, today):
        self.calls += 1
        if dte == 0: return self.c0
        if dte == 1: return self.c1
        if dte == 14: return self.c14
        return None

    def get_leg_mids(self, *, ticker, legs):
        if self.leg_mid_overrides is not None:
            return self.leg_mid_overrides
        return [leg["entry_price"] for leg in legs]


def _enable_bot(engine, bot):
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE {bot}_config SET enabled = 1 WHERE id = 1"))


def test_gust_opens_position_in_entry_window(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "gust")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] in ("TRADE", "NO_TRADE")  # not blocked
    # If TRADE, position should exist
    if res["outcome"] == "TRADE":
        with engine.begin() as conn:
            n = conn.execute(text(
                "SELECT COUNT(*) c FROM gust_positions WHERE status='OPEN'"
            )).mappings().first()["c"]
        assert n == 1


def test_gust_disabled_blocks_trading(db_session, fake_chain_0dte):
    engine = db_session.bind  # NOT enabling
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "BLOCKED_DISABLED"


def test_outside_entry_window_blocks_open(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "gust")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    # Before 08:35
    now = datetime(2026, 5, 20, 8, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "BLOCKED_OUTSIDE_WINDOW"


def test_event_blackout_blocks_open(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "gust")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                        chain_provider=provider, event_blackout=True)
    assert res["outcome"] == "BLOCKED_EVENT"


def test_existing_open_position_monitors_instead_of_opens(db_session, fake_chain_0dte):
    """If an OPEN position exists, the scanner should MONITOR (not open another)."""
    from backend.bots.strategies.iron_butterfly import build_iron_butterfly_signal
    from backend.bots.executor import open_position
    engine = db_session.bind
    _enable_bot(engine, "gust")
    sig = build_iron_butterfly_signal(
        chain=fake_chain_0dte,
        config={"max_contracts": 1, "bp_pct": 0.10, "sd_mult": 1.0,
                "pt_pct": 0.30, "sl_pct": 2.0, "use_gex_walls": False},
        equity=10000.0,
    )
    open_position(engine, "gust", "iron_butterfly", sig,
                  datetime(2026, 5, 20, 9, 0, tzinfo=CT))
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 30, tzinfo=CT)
    res = run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                        chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "MONITOR"


def test_scan_activity_row_written(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "gust")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT outcome FROM gust_scan_activity"
        )).mappings().all()
    assert len(rows) >= 1


def test_equity_snapshot_written(db_session, fake_chain_0dte):
    engine = db_session.bind
    _enable_bot(engine, "gust")
    provider = FakeChainProvider(chain_0dte=fake_chain_0dte)
    now = datetime(2026, 5, 20, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=engine, bot="gust", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT equity FROM gust_equity_snapshots"
        )).mappings().all()
    assert len(rows) == 1
    assert float(rows[0]["equity"]) >= 9000  # near starting capital
```

- [ ] **Step 2: Run, confirm fail**

- [ ] **Step 3: Implement** — `spreadworks/backend/bots/scanner.py`

```python
"""Per-bot 1-minute scanner orchestration.

A `ChainProvider` is injected so the live scanner uses Tradier (see
routes.py for the existing chain fetcher), but unit tests can pass fakes.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .db import bot_table, load_config
from .executor import (
    account_equity, list_open_positions, open_position,
    close_position, compute_mtm, update_mtm,
)
from .monitor import decide_exit, pt_pct_for_time_of_day
from .registry import BOT_REGISTRY, get_bot
from .strategies.iron_butterfly import build_iron_butterfly_signal
from .strategies.double_calendar import build_double_calendar_signal
from .strategies.double_diagonal import build_double_diagonal_signal

logger = logging.getLogger("spreadworks.bots.scanner")
CT = ZoneInfo("America/Chicago")
SCAN_TIMEOUT_SEC = 15


class ChainProvider(Protocol):
    def get_chain(self, *, ticker: str, dte: int, today: date) -> dict | None: ...
    def get_leg_mids(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float]: ...


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _log_scan(engine: Engine, bot: str, *, now: datetime, outcome: str,
              reason: str | None = None, signal: dict | None = None,
              position_id: str | None = None) -> None:
    t = bot_table(bot, "scan_activity")
    with engine.begin() as conn:
        conn.execute(text(
            f"INSERT INTO {t} (scan_time, outcome, reason, signal_data, position_id) "
            "VALUES (:t, :o, :r, :s, :p)"
        ), {"t": now, "o": outcome, "r": reason,
            "s": json.dumps(signal) if signal else None, "p": position_id})


def _write_equity_snapshot(engine: Engine, bot: str, now: datetime) -> None:
    cfg = load_config(engine, bot)
    realized_today_q = text(
        f"SELECT COALESCE(SUM(realized_pnl), 0) AS s "
        f"FROM {bot_table(bot, 'closed_trades')} "
        "WHERE DATE(close_time) = DATE(:n)"
    )
    cumulative_q = text(
        f"SELECT COALESCE(SUM(realized_pnl), 0) AS s "
        f"FROM {bot_table(bot, 'closed_trades')}"
    )
    open_q = text(
        f"SELECT COUNT(*) c, COALESCE(SUM(mtm_pnl), 0) u "
        f"FROM {bot_table(bot, 'positions')} WHERE status='OPEN'"
    )
    with engine.begin() as conn:
        r_today = float(conn.execute(realized_today_q, {"n": now}).mappings().first()["s"])
        cumulative = float(conn.execute(cumulative_q).mappings().first()["s"])
        row = conn.execute(open_q).mappings().first()
        open_n = int(row["c"]); unrealized = float(row["u"] or 0)
        equity = float(cfg["starting_capital"]) + cumulative + unrealized
        conn.execute(text(
            f"INSERT INTO {bot_table(bot, 'equity_snapshots')} ("
            "snapshot_time, equity, unrealized_pnl, realized_pnl_today, "
            "cumulative_pnl, open_positions"
            ") VALUES (:t, :e, :u, :r, :c, :n)"
        ), {"t": now, "e": equity, "u": unrealized, "r": r_today,
            "c": cumulative, "n": open_n})


def _within_window(now_ct: datetime, start: str, end: str) -> bool:
    t = now_ct.timetz().replace(tzinfo=None)
    return _parse_time(start) <= t < _parse_time(end)


def _build_signal(*, bot: str, strategy: str, chain_provider: ChainProvider,
                  config: dict, equity: float, today: date,
                  ticker: str, front_dte: int, back_dte: int | None):
    if strategy == "iron_butterfly":
        chain = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
        if chain is None: return None, None
        return build_iron_butterfly_signal(chain=chain, config=config, equity=equity), chain
    front = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
    back = chain_provider.get_chain(ticker=ticker, dte=back_dte, today=today)
    if front is None or back is None: return None, None
    if strategy == "double_calendar":
        return build_double_calendar_signal(
            front_chain=front, back_chain=back, config=config, equity=equity
        ), front
    if strategy == "double_diagonal":
        return build_double_diagonal_signal(
            front_chain=front, back_chain=back, config=config, equity=equity
        ), front
    raise ValueError(f"unknown strategy {strategy}")


def run_scan_cycle(
    *, engine: Engine, bot: str, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool,
) -> dict[str, Any]:
    """Execute one scan cycle for `bot`. Returns dict with at least 'outcome' key."""
    meta = get_bot(bot)
    cfg = load_config(engine, bot)
    result: dict[str, Any] = {"outcome": "NO_TRADE", "reason": None}

    try:
        if not bool(cfg.get("enabled")):
            result = {"outcome": "BLOCKED_DISABLED"}
            return result

        opens = list_open_positions(engine, bot)
        if opens:
            # Monitor branch — no new trades while one is open.
            for pos in opens:
                legs = json.loads(pos["legs"])
                mids = chain_provider.get_leg_mids(ticker=pos["ticker"], legs=legs)
                mtm_value, mtm_pnl = compute_mtm(
                    strategy=pos["strategy"], legs=legs,
                    entry_price=float(pos["entry_price"]),
                    contracts=int(pos["contracts"]),
                    leg_mids=mids,
                )
                update_mtm(engine, bot, pos["position_id"], mtm_value, mtm_pnl, now_ct)

                pt_target = float(pos["pt_target_pnl"])
                if pos["strategy"] == "iron_butterfly":
                    # Re-derive PT target each scan using the time-of-day ladder.
                    new_pt_pct = pt_pct_for_time_of_day(now_ct.timetz().replace(tzinfo=None))
                    pt_target = new_pt_pct * float(pos["max_profit"])

                front_exp_str = legs[0]["expiration"]  # legs share front expiration order for IBF; for DC/DD the short legs are first
                # For DC/DD the front expiration is the SHORT side, which we
                # placed first in legs[] in both strategy modules.
                front_exp = date.fromisoformat(front_exp_str)

                d = decide_exit(
                    strategy=pos["strategy"], mtm_pnl=mtm_pnl,
                    pt_target_pnl=pt_target, sl_target_pnl=float(pos["sl_target_pnl"]),
                    now_ct=now_ct, front_expiration=front_exp,
                    eod_close_ct=_parse_time(cfg["eod_close_ct"]),
                    event_blackout=event_blackout,
                )
                if d.should_close:
                    close_position(engine, bot, pos["position_id"],
                                   close_value=mtm_value, close_reason=d.reason,
                                   now=now_ct)
                    result = {"outcome": "TRADE", "reason": f"CLOSE_{d.reason}",
                              "position_id": pos["position_id"]}
                else:
                    result = {"outcome": "MONITOR", "position_id": pos["position_id"]}
            return result

        # No open positions — try to OPEN
        if event_blackout:
            result = {"outcome": "BLOCKED_EVENT"}
            return result
        if not _within_window(now_ct, cfg["entry_start_ct"], cfg["entry_end_ct"]):
            result = {"outcome": "BLOCKED_OUTSIDE_WINDOW"}
            return result

        equity = account_equity(engine, bot)
        signal, _chain = _build_signal(
            bot=bot, strategy=meta["strategy"], chain_provider=chain_provider,
            config=cfg, equity=equity, today=now_ct.date(),
            ticker=meta["ticker"], front_dte=meta["front_dte"],
            back_dte=meta["back_dte"],
        )
        if signal is None:
            result = {"outcome": "NO_TRADE", "reason": "no signal"}
            return result

        pid = open_position(engine, bot, meta["strategy"], signal, now_ct)
        result = {"outcome": "TRADE", "reason": "OPENED", "position_id": pid}
        return result
    finally:
        _log_scan(engine, bot, now=now_ct, outcome=result["outcome"],
                  reason=result.get("reason"),
                  position_id=result.get("position_id"))
        _write_equity_snapshot(engine, bot, now_ct)


async def run_scan_cycle_with_timeout(
    *, engine: Engine, bot: str, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool,
) -> dict[str, Any]:
    """Wrap one bot's scan in a 15s timeout so one slow bot can't starve
    the others (memory: 5/15 hung-scanner bug)."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                run_scan_cycle,
                engine=engine, bot=bot, now_ct=now_ct,
                chain_provider=chain_provider, event_blackout=event_blackout,
            ),
            timeout=SCAN_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{bot}] scan timeout after {SCAN_TIMEOUT_SEC}s")
        return {"outcome": "BLOCKED_TIMEOUT"}
    except Exception as e:
        logger.exception(f"[{bot}] scan exception: {e}")
        return {"outcome": "BLOCKED_EXCEPTION", "reason": str(e)[:200]}
```

- [ ] **Step 4: Run, confirm pass**

```bash
pytest tests/test_scanner.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/bots/scanner.py spreadworks/tests/test_scanner.py
git commit -m "feat(spreadworks): scanner with 15s per-bot timeout + monitor loop"
```

---

## Task 10: Wire scanner into APScheduler + startup migration

**Files:**
- Modify: `spreadworks/backend/__init__.py`

The existing `_start_scheduler` builds an `AsyncIOScheduler` and registers
Discord market open/close jobs. Add a new `scan_bots_tick` coroutine and
call `create_bot_tables(engine)` at app startup.

- [ ] **Step 1: Read existing scheduler block**

```bash
grep -n "_start_scheduler\|add_job\|AsyncIOScheduler" spreadworks/backend/__init__.py
```

- [ ] **Step 2: Add `create_bot_tables` call to startup**

In `spreadworks/backend/__init__.py`, locate the section where `Base.metadata.create_all(engine)` is called (after the model imports near top, or inside lifespan). After that line, add:

```python
from .bots.db import create_bot_tables
create_bot_tables(engine)
```

- [ ] **Step 3: Add the tick coroutine and register job inside `_start_scheduler`**

Inside `_start_scheduler(app)` after the existing `scheduler = AsyncIOScheduler(timezone=ZoneInfo('America/Chicago'))` (or equivalent), add:

```python
from .bots.scanner import run_scan_cycle_with_timeout
from .bots.registry import list_bots
from .bots.routes_helpers import build_live_chain_provider  # see Task 11

async def scan_bots_tick():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now_ct = datetime.now(ZoneInfo("America/Chicago"))
    # Only scan during 08:30-15:00 CT, Mon-Fri
    if now_ct.weekday() >= 5: return
    if not (8 <= now_ct.hour < 15): return
    provider = build_live_chain_provider()  # Tradier-backed at runtime
    # Reuse the existing event-blackout helper if available
    try:
        from .economic_events import is_event_blackout_active
        blackout = is_event_blackout_active("SPY", now_ct)
    except Exception:
        blackout = False
    for bot in list_bots():
        try:
            res = await run_scan_cycle_with_timeout(
                engine=engine, bot=bot, now_ct=now_ct,
                chain_provider=provider, event_blackout=blackout,
            )
            logger.info(f"[scan_bots:{bot}] {res}")
        except Exception as e:
            logger.exception(f"[scan_bots:{bot}] outer exception: {e}")

scheduler.add_job(
    scan_bots_tick, "cron",
    minute="*", hour="8-14",
    day_of_week="mon-fri",
    timezone=ZoneInfo("America/Chicago"),
    id="scan_bots", coalesce=True, max_instances=1,
)
```

Note: `is_event_blackout_active` may not exist with that exact name —
verify by grepping `economic_events.py` and adapt the import accordingly.
If the existing helper takes only `now_ct`, drop the ticker argument.

- [ ] **Step 4: Smoke test the import path**

```bash
cd spreadworks
python -c "import backend; print('imports ok')"
```

- [ ] **Step 5: Commit**

```bash
git add spreadworks/backend/__init__.py
git commit -m "feat(spreadworks): register scan_bots APScheduler job + auto-migrate bot tables"
```

---

## Task 11: Live chain provider + helper module

**Files:**
- Create: `spreadworks/backend/bots/routes_helpers.py`

The scanner needs a `ChainProvider` that pulls quotes from Tradier at
runtime. SpreadWorks already has helpers in `backend/routes.py` for
fetching chains — we wrap them.

- [ ] **Step 1: Implement** — `spreadworks/backend/bots/routes_helpers.py`

```python
"""Live ChainProvider — wraps the existing Tradier helpers in routes.py.

Used by the production scanner. Tests use a FakeChainProvider injected
directly, never this module.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger("spreadworks.bots.chain")

TRADIER_BASE = "https://api.tradier.com/v1"
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN", "")


def _headers() -> dict:
    return {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}


class LiveTradierChainProvider:
    """Synchronous Tradier chain fetcher.

    Scanner runs in a thread (via asyncio.to_thread) so blocking httpx is OK.
    """

    def __init__(self):
        self._client = httpx.Client(timeout=10.0)

    def get_chain(self, *, ticker: str, dte: int, today: date) -> dict | None:
        target = today + timedelta(days=dte)
        # Tradier returns the next available expiration on or after `target`
        exp = self._nearest_expiration_on_or_after(ticker, target)
        if exp is None:
            return None
        chain_resp = self._client.get(
            f"{TRADIER_BASE}/markets/options/chains",
            params={"symbol": ticker, "expiration": exp, "greeks": "true"},
            headers=_headers(),
        )
        if chain_resp.status_code != 200:
            logger.warning(f"chain fetch failed {chain_resp.status_code}")
            return None
        data = chain_resp.json().get("options", {}).get("option", []) or []
        spot = self._spot(ticker)
        if spot is None:
            return None
        atm_straddle = self._atm_straddle_mid(data, spot)
        vix = self._spot("VIX") or 0
        iv_atm = self._atm_iv(data, spot)
        return {
            "spot": spot, "vix": vix, "atm_straddle_mid": atm_straddle,
            "iv_atm": iv_atm, "expiration": exp, "ticker": ticker,
            "options": [
                {"strike": o["strike"], "type": o["option_type"],
                 "bid": o.get("bid") or 0, "ask": o.get("ask") or 0}
                for o in data
            ],
            # GEX populated by upstream `/api/spreadworks/gex` if you want it
            "gex": {},
        }

    def get_leg_mids(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float]:
        # Build OCC symbols and batch-fetch quotes
        symbols = [self._occ(ticker, leg) for leg in legs]
        resp = self._client.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": ",".join(symbols), "greeks": "false"},
            headers=_headers(),
        )
        if resp.status_code != 200:
            raise RuntimeError(f"quote fetch failed: {resp.status_code}")
        quotes = resp.json().get("quotes", {}).get("quote", []) or []
        if isinstance(quotes, dict):
            quotes = [quotes]
        by_sym = {q["symbol"]: q for q in quotes}
        out = []
        for sym in symbols:
            q = by_sym.get(sym, {})
            bid = float(q.get("bid") or 0); ask = float(q.get("ask") or 0)
            out.append((bid + ask) / 2.0)
        return out

    # ---- helpers ----
    def _nearest_expiration_on_or_after(self, ticker: str, target: date) -> str | None:
        resp = self._client.get(
            f"{TRADIER_BASE}/markets/options/expirations",
            params={"symbol": ticker, "includeAllRoots": "true"},
            headers=_headers(),
        )
        if resp.status_code != 200: return None
        dates = resp.json().get("expirations", {}).get("date", []) or []
        if isinstance(dates, str): dates = [dates]
        for d in dates:
            if d >= target.isoformat():
                return d
        return None

    def _spot(self, ticker: str) -> float | None:
        sym = "VIX" if ticker == "VIX" else ticker
        resp = self._client.get(
            f"{TRADIER_BASE}/markets/quotes",
            params={"symbols": sym}, headers=_headers(),
        )
        if resp.status_code != 200: return None
        q = resp.json().get("quotes", {}).get("quote", {}) or {}
        if isinstance(q, list): q = q[0] if q else {}
        return float(q.get("last") or 0) or None

    def _atm_straddle_mid(self, opts: list[dict], spot: float) -> float:
        if not opts: return 0.0
        strikes = sorted({o["strike"] for o in opts})
        atm = min(strikes, key=lambda s: abs(float(s) - spot))
        call = next((o for o in opts if o["strike"] == atm and o["option_type"] == "call"), None)
        put = next((o for o in opts if o["strike"] == atm and o["option_type"] == "put"), None)
        if not call or not put: return 0.0
        cm = (float(call.get("bid") or 0) + float(call.get("ask") or 0)) / 2
        pm = (float(put.get("bid") or 0) + float(put.get("ask") or 0)) / 2
        return round(cm + pm, 4)

    def _atm_iv(self, opts: list[dict], spot: float) -> float:
        if not opts: return 0.0
        atm = min({o["strike"] for o in opts}, key=lambda s: abs(float(s) - spot))
        for o in opts:
            if o["strike"] == atm and o["option_type"] == "call":
                greeks = o.get("greeks") or {}
                return float(greeks.get("mid_iv") or greeks.get("ask_iv") or 0)
        return 0.0

    def _occ(self, ticker: str, leg: dict) -> str:
        # OCC format: SPY  240520C00500000
        d = date.fromisoformat(leg["expiration"])
        yymmdd = d.strftime("%y%m%d")
        cp = "C" if leg["type"] == "call" else "P"
        strike_milli = int(round(float(leg["strike"]) * 1000))
        return f"{ticker}{yymmdd}{cp}{strike_milli:08d}"


def build_live_chain_provider() -> LiveTradierChainProvider:
    return LiveTradierChainProvider()
```

- [ ] **Step 2: Smoke test imports**

```bash
cd spreadworks
python -c "from backend.bots.routes_helpers import build_live_chain_provider; print('ok')"
```

- [ ] **Step 3: Commit**

```bash
git add spreadworks/backend/bots/routes_helpers.py
git commit -m "feat(spreadworks): live Tradier ChainProvider for bot scanner"
```

---

## Task 12: API routes (per-bot endpoints)

**Files:**
- Create: `spreadworks/backend/routes_bots.py`
- Modify: `spreadworks/backend/__init__.py` (mount the new router)
- Create: `spreadworks/tests/test_routes_bots.py`

- [ ] **Step 1: Write tests** — `spreadworks/tests/test_routes_bots.py`

```python
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db_session, monkeypatch):
    """Build a FastAPI app instance wired to the in-memory test DB."""
    from sqlalchemy.orm import sessionmaker
    from backend import app as backend_module
    # Override get_db to use the test engine
    from backend.db import get_db
    Session = sessionmaker(bind=db_session.bind, expire_on_commit=False)

    def override_get_db():
        s = Session()
        try: yield s
        finally: s.close()

    backend_module.dependency_overrides[get_db] = override_get_db

    # Also override the engine used by routes_bots
    from backend import routes_bots
    monkeypatch.setattr(routes_bots, "ENGINE", db_session.bind)

    with TestClient(backend_module) as c:
        yield c

    backend_module.dependency_overrides.clear()


def test_status_returns_basic_fields(client):
    r = client.get("/api/spreadworks/bots/gust/status")
    assert r.status_code == 200
    d = r.json()
    assert d["bot"] == "gust"
    assert d["enabled"] is False
    assert d["open_positions"] == 0


def test_unknown_bot_returns_404(client):
    r = client.get("/api/spreadworks/bots/notabot/status")
    assert r.status_code == 404


def test_toggle_flips_enabled(client):
    r = client.post("/api/spreadworks/bots/gust/toggle")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    r2 = client.post("/api/spreadworks/bots/gust/toggle")
    assert r2.json()["enabled"] is False


def test_config_get_and_post(client):
    r = client.get("/api/spreadworks/bots/gust/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["pt_pct"] == 0.30 or float(cfg["pt_pct"]) == 0.30

    r2 = client.post("/api/spreadworks/bots/gust/config", json={"pt_pct": 0.40})
    assert r2.status_code == 200
    r3 = client.get("/api/spreadworks/bots/gust/config")
    assert float(r3.json()["pt_pct"]) == 0.40
```

- [ ] **Step 2: Run, confirm fail**

```bash
pytest tests/test_routes_bots.py -v
```

- [ ] **Step 3: Implement** — `spreadworks/backend/routes_bots.py`

```python
"""SpreadWorks bot API routes: /api/spreadworks/bots/{bot}/*"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .bots.db import bot_table, load_config
from .bots.executor import account_equity, list_open_positions
from .bots.registry import BOT_REGISTRY, list_bots
from .db import engine as _global_engine

logger = logging.getLogger("spreadworks.routes_bots")
router = APIRouter(prefix="/api/spreadworks/bots", tags=["SpreadWorks Bots"])

# Tests override this via monkeypatch
ENGINE: Engine = _global_engine
CT = ZoneInfo("America/Chicago")


def _validate(bot: str) -> None:
    if bot not in BOT_REGISTRY:
        raise HTTPException(404, f"Unknown bot: {bot}")


@router.get("/{bot}/status")
def get_status(bot: str):
    _validate(bot)
    cfg = load_config(ENGINE, bot)
    opens = list_open_positions(ENGINE, bot)
    equity = account_equity(ENGINE, bot)
    with ENGINE.begin() as conn:
        last = conn.execute(text(
            f"SELECT MAX(scan_time) AS s FROM {bot_table(bot, 'scan_activity')}"
        )).mappings().first()
    return {
        "bot": bot,
        "display": BOT_REGISTRY[bot]["display"],
        "strategy": BOT_REGISTRY[bot]["strategy"],
        "enabled": bool(cfg["enabled"]),
        "open_positions": len(opens),
        "equity": float(equity),
        "starting_capital": float(cfg["starting_capital"]),
        "last_scan_at": str(last["s"]) if last["s"] else None,
    }


@router.get("/{bot}/positions")
def get_positions(bot: str):
    _validate(bot)
    rows = list_open_positions(ENGINE, bot)
    for r in rows:
        r["legs"] = json.loads(r["legs"]) if isinstance(r["legs"], str) else r["legs"]
    return {"positions": rows}


@router.get("/{bot}/position-monitor")
def get_position_monitor(bot: str):
    return get_positions(bot)


@router.get("/{bot}/equity-curve")
def get_equity_curve(bot: str):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    cfg = load_config(ENGINE, bot)
    sc = float(cfg["starting_capital"])
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT close_time, realized_pnl FROM {t} ORDER BY close_time"
        )).mappings().all()
    curve = []
    cum = 0.0
    for r in rows:
        cum += float(r["realized_pnl"])
        curve.append({"time": str(r["close_time"]), "equity": sc + cum, "pnl": cum})
    return {"curve": curve, "starting_capital": sc}


@router.get("/{bot}/equity-curve/intraday")
def get_equity_intraday(bot: str):
    _validate(bot)
    t = bot_table(bot, "equity_snapshots")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT snapshot_time, equity, unrealized_pnl, realized_pnl_today, "
            "open_positions FROM {0} WHERE DATE(snapshot_time) = DATE(CURRENT_TIMESTAMP) "
            "ORDER BY snapshot_time".format(t)
        )).mappings().all()
    return {"snapshots": [dict(r) for r in rows]}


@router.get("/{bot}/trades")
def get_trades(bot: str, limit: int = 100):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM {t} ORDER BY close_time DESC LIMIT :n"
        ), {"n": limit}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        d["legs"] = json.loads(d["legs"]) if isinstance(d["legs"], str) else d["legs"]
        out.append(d)
    return {"trades": out}


@router.get("/{bot}/performance")
def get_performance(bot: str):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        r = conn.execute(text(
            f"SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) AS wins, "
            "SUM(realized_pnl) AS total, "
            "AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl END) AS avg_win, "
            "AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl END) AS avg_loss "
            f"FROM {t}"
        )).mappings().first()
    n = int(r["n"] or 0)
    wins = int(r["wins"] or 0)
    return {
        "trades": n,
        "wins": wins,
        "win_rate": (wins / n) if n else 0,
        "total_pnl": float(r["total"] or 0),
        "avg_win": float(r["avg_win"] or 0),
        "avg_loss": float(r["avg_loss"] or 0),
    }


@router.get("/{bot}/daily-perf")
def get_daily_perf(bot: str, days: int = 30):
    _validate(bot)
    t = bot_table(bot, "closed_trades")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT DATE(close_time) AS d, SUM(realized_pnl) AS pnl, COUNT(*) AS n "
            f"FROM {t} GROUP BY DATE(close_time) ORDER BY d DESC LIMIT :n"
        ), {"n": days}).mappings().all()
    return {"days": [dict(r) for r in rows]}


@router.get("/{bot}/config")
def get_config(bot: str):
    _validate(bot)
    return load_config(ENGINE, bot)


class ConfigUpdate(BaseModel):
    starting_capital: float | None = None
    enabled: bool | None = None
    max_contracts: int | None = None
    bp_pct: float | None = None
    sd_mult: float | None = None
    pt_pct: float | None = None
    sl_pct: float | None = None
    entry_start_ct: str | None = None
    entry_end_ct: str | None = None
    eod_close_ct: str | None = None
    discord_alerts: bool | None = None
    delta_skew: int | None = None
    use_gex_walls: bool | None = None


@router.post("/{bot}/config")
def post_config(bot: str, body: ConfigUpdate):
    _validate(bot)
    t = bot_table(bot, "config")
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        return load_config(ENGINE, bot)
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["bot_id"] = 1
    with ENGINE.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET {set_clause}, updated_at = CURRENT_TIMESTAMP "
            "WHERE id = :bot_id"
        ), updates)
    return load_config(ENGINE, bot)


@router.post("/{bot}/toggle")
def post_toggle(bot: str):
    _validate(bot)
    t = bot_table(bot, "config")
    with ENGINE.begin() as conn:
        cur = conn.execute(text(f"SELECT enabled FROM {t} WHERE id=1")).scalar()
        new = not bool(cur)
        conn.execute(text(f"UPDATE {t} SET enabled = :e WHERE id=1"), {"e": new})
    return {"bot": bot, "enabled": new}


@router.post("/{bot}/force-trade")
def post_force_trade(bot: str):
    _validate(bot)
    # Trigger one immediate scan cycle bypassing the entry window check
    from .bots.scanner import run_scan_cycle
    from .bots.routes_helpers import build_live_chain_provider
    provider = build_live_chain_provider()
    now = datetime.now(CT)
    # Force window: temporarily widen the window by passing a tweaked config
    # Simpler: call run_scan_cycle with a now_ct guaranteed inside window
    # by saving/restoring the config. For paper purposes we just override
    # via a tiny patch:
    cfg = load_config(ENGINE, bot)
    t = bot_table(bot, "config")
    with ENGINE.begin() as conn:
        conn.execute(text(
            f"UPDATE {t} SET entry_start_ct='00:00', entry_end_ct='23:59' WHERE id=1"
        ))
    try:
        result = run_scan_cycle(
            engine=ENGINE, bot=bot, now_ct=now,
            chain_provider=provider, event_blackout=False,
        )
    finally:
        with ENGINE.begin() as conn:
            conn.execute(text(
                f"UPDATE {t} SET entry_start_ct=:s, entry_end_ct=:e WHERE id=1"
            ), {"s": cfg["entry_start_ct"], "e": cfg["entry_end_ct"]})
    return result


@router.post("/{bot}/force-close")
def post_force_close(bot: str, position_id: str):
    _validate(bot)
    from .bots.executor import close_position, list_open_positions, compute_mtm, update_mtm
    from .bots.routes_helpers import build_live_chain_provider
    opens = list_open_positions(ENGINE, bot)
    pos = next((p for p in opens if p["position_id"] == position_id), None)
    if pos is None:
        raise HTTPException(404, f"No OPEN position {position_id}")
    provider = build_live_chain_provider()
    legs = json.loads(pos["legs"]) if isinstance(pos["legs"], str) else pos["legs"]
    mids = provider.get_leg_mids(ticker=pos["ticker"], legs=legs)
    mtm_value, _ = compute_mtm(
        strategy=pos["strategy"], legs=legs,
        entry_price=float(pos["entry_price"]),
        contracts=int(pos["contracts"]), leg_mids=mids,
    )
    realized = close_position(ENGINE, bot, position_id,
                              close_value=mtm_value, close_reason="FORCE",
                              now=datetime.now(CT))
    return {"position_id": position_id, "realized_pnl": realized}


@router.get("/{bot}/logs")
@router.get("/{bot}/scan-activity")
def get_scan_activity(bot: str, limit: int = 200):
    _validate(bot)
    t = bot_table(bot, "scan_activity")
    with ENGINE.begin() as conn:
        rows = conn.execute(text(
            f"SELECT * FROM {t} ORDER BY scan_time DESC LIMIT :n"
        ), {"n": limit}).mappings().all()
    return {"rows": [dict(r) for r in rows]}


@router.get("")
def list_all_bots():
    """GET /api/spreadworks/bots — overview of all bots."""
    out = []
    for bot in list_bots():
        try:
            out.append(get_status(bot))
        except Exception as e:
            out.append({"bot": bot, "error": str(e)[:200]})
    return {"bots": out}
```

- [ ] **Step 4: Mount the router** — modify `spreadworks/backend/__init__.py`

Find where `app.include_router(router)` happens (existing routes.py is mounted there). Just below it, add:

```python
from .routes_bots import router as bots_router
app.include_router(bots_router)
```

- [ ] **Step 5: Run, confirm pass**

```bash
pytest tests/test_routes_bots.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add spreadworks/backend/routes_bots.py spreadworks/backend/__init__.py spreadworks/tests/test_routes_bots.py
git commit -m "feat(spreadworks): /api/spreadworks/bots/{bot}/* routes"
```

---

## Task 13: Discord alert helpers

**Files:**
- Create: `spreadworks/backend/bots/discord_alerts.py`

This task is light because it reuses the existing `_send_webhook_sync` and
`_dedup_ok` from `backend/__init__.py`.

- [ ] **Step 1: Implement** — `spreadworks/backend/bots/discord_alerts.py`

```python
"""Discord open/close embeds for bot positions.

Reuses `_send_webhook_sync` + `_dedup_ok` from backend.__init__ so we get
the existing 3-attempt retry + cross-process dedup for free.
"""
from __future__ import annotations

from typing import Any


_COLOR = {"open": 0x3498DB, "close_PT": 0x2ECC71, "close_SL": 0xE74C3C,
          "close_EOD": 0xF39C12, "close_FORCE": 0x9B59B6,
          "close_EVENT_HALT": 0xE67E22}


def post_open(*, bot: str, display: str, strategy: str,
              position_id: str, legs: list[dict[str, Any]],
              entry_price: float, contracts: int,
              max_profit: float, max_loss: float) -> bool:
    from .. import _send_webhook_sync, _dedup_ok  # late import to avoid circular
    if not _dedup_ok(f"bot:{bot}:position:{position_id}:open"):
        return False
    legs_text = "\n".join(
        f"  {l['side'].upper():5} {l['type'].upper():4} {l['strike']} {l['expiration']} @ {float(l['entry_price']):.2f}"
        for l in legs
    )
    embed = {
        "title": f"{display} — OPEN {strategy}",
        "description": f"`{position_id}`",
        "color": _COLOR["open"],
        "fields": [
            {"name": "Entry", "value": f"{entry_price:.2f}", "inline": True},
            {"name": "Contracts", "value": str(contracts), "inline": True},
            {"name": "Max Profit / Loss",
             "value": f"${max_profit:.0f} / ${max_loss:.0f}", "inline": True},
            {"name": "Legs", "value": f"```\n{legs_text}\n```", "inline": False},
        ],
    }
    return _send_webhook_sync(embed)


def post_close(*, bot: str, display: str, strategy: str,
               position_id: str, close_reason: str,
               realized_pnl: float, time_in_trade_min: int) -> bool:
    from .. import _send_webhook_sync, _dedup_ok
    if not _dedup_ok(f"bot:{bot}:position:{position_id}:close"):
        return False
    color = _COLOR.get(f"close_{close_reason}", 0x95A5A6)
    sign = "+" if realized_pnl >= 0 else ""
    embed = {
        "title": f"{display} — CLOSE {strategy} ({close_reason})",
        "description": f"`{position_id}`",
        "color": color,
        "fields": [
            {"name": "Realized P&L", "value": f"{sign}${realized_pnl:.2f}", "inline": True},
            {"name": "Time in Trade", "value": f"{time_in_trade_min} min", "inline": True},
        ],
    }
    return _send_webhook_sync(embed)
```

- [ ] **Step 2: Wire into scanner**

In `spreadworks/backend/bots/scanner.py`, locate the section that calls
`open_position(...)`. Wrap with discord alert (only if `cfg.discord_alerts`):

After `pid = open_position(...)`:

```python
if bool(cfg.get("discord_alerts")):
    from . import discord_alerts
    discord_alerts.post_open(
        bot=bot, display=meta["display"], strategy=meta["strategy"],
        position_id=pid, legs=signal.legs(),
        entry_price=getattr(signal, "credit", None) or getattr(signal, "debit"),
        contracts=signal.contracts,
        max_profit=signal.max_profit * signal.contracts,
        max_loss=signal.max_loss * signal.contracts,
    )
```

After `close_position(...)`:

```python
if bool(cfg.get("discord_alerts")):
    from . import discord_alerts
    from datetime import datetime
    entry_dt = pos["entry_time"] if isinstance(pos["entry_time"], datetime) \
        else datetime.fromisoformat(str(pos["entry_time"]))
    mins = int((now_ct - entry_dt.replace(tzinfo=now_ct.tzinfo)).total_seconds() // 60)
    discord_alerts.post_close(
        bot=bot, display=meta["display"], strategy=pos["strategy"],
        position_id=pos["position_id"], close_reason=d.reason,
        realized_pnl=mtm_pnl,
        time_in_trade_min=mins,
    )
```

- [ ] **Step 3: Smoke test imports**

```bash
python -c "from backend.bots.discord_alerts import post_open, post_close; print('ok')"
```

- [ ] **Step 4: Commit**

```bash
git add spreadworks/backend/bots/discord_alerts.py spreadworks/backend/bots/scanner.py
git commit -m "feat(spreadworks): optional Discord open/close embeds for bots"
```

---

## Task 14: Frontend — bot registry + API client

**Files:**
- Create: `spreadworks/frontend/src/lib/botRegistry.js`
- Create: `spreadworks/frontend/src/lib/botApi.js`

- [ ] **Step 1: Implement registry mirror** — `spreadworks/frontend/src/lib/botRegistry.js`

```javascript
// Frontend mirror of spreadworks/backend/bots/registry.py.
// Keep these in sync when editing.

export const BOT_REGISTRY = {
  gust:  { display: 'GUST',  strategy: 'iron_butterfly',  ticker: 'SPY' },
  tide:  { display: 'TIDE',  strategy: 'double_calendar', ticker: 'SPY' },
  drift: { display: 'DRIFT', strategy: 'double_diagonal', ticker: 'SPY' },
};

export const STRATEGY_LABEL = {
  iron_butterfly:   'Iron Butterfly',
  double_calendar:  'Double Calendar',
  double_diagonal:  'Double Diagonal',
};

export const BOT_THEME = {
  gust:  { accent: '#7DD3FC', glyph: 'wind' },
  tide:  { accent: '#38BDF8', glyph: 'wave' },
  drift: { accent: '#A78BFA', glyph: 'spiral' },
};
```

- [ ] **Step 2: Implement API client** — `spreadworks/frontend/src/lib/botApi.js`

```javascript
// SpreadWorks bot API helpers. Returns parsed JSON or throws on non-2xx.

const API_BASE = import.meta.env.VITE_API_URL || '';

async function _get(path) {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function _post(path, body) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export const botApi = {
  listAll:        ()         => _get(`/api/spreadworks/bots`),
  status:         (b)        => _get(`/api/spreadworks/bots/${b}/status`),
  positions:      (b)        => _get(`/api/spreadworks/bots/${b}/positions`),
  positionMonitor:(b)        => _get(`/api/spreadworks/bots/${b}/position-monitor`),
  equityCurve:    (b)        => _get(`/api/spreadworks/bots/${b}/equity-curve`),
  equityIntraday: (b)        => _get(`/api/spreadworks/bots/${b}/equity-curve/intraday`),
  trades:         (b, limit=100) => _get(`/api/spreadworks/bots/${b}/trades?limit=${limit}`),
  performance:    (b)        => _get(`/api/spreadworks/bots/${b}/performance`),
  dailyPerf:      (b)        => _get(`/api/spreadworks/bots/${b}/daily-perf`),
  config:         (b)        => _get(`/api/spreadworks/bots/${b}/config`),
  saveConfig:     (b, body)  => _post(`/api/spreadworks/bots/${b}/config`, body),
  toggle:         (b)        => _post(`/api/spreadworks/bots/${b}/toggle`),
  forceTrade:     (b)        => _post(`/api/spreadworks/bots/${b}/force-trade`),
  forceClose:     (b, pid)   => _post(`/api/spreadworks/bots/${b}/force-close?position_id=${encodeURIComponent(pid)}`),
  scanActivity:   (b, limit=200) => _get(`/api/spreadworks/bots/${b}/scan-activity?limit=${limit}`),
};
```

- [ ] **Step 3: Commit**

```bash
git add spreadworks/frontend/src/lib/botRegistry.js spreadworks/frontend/src/lib/botApi.js
git commit -m "feat(spreadworks): frontend bot registry + API client"
```

---

## Task 15: Frontend hooks

**Files:**
- Create: `spreadworks/frontend/src/hooks/useBotStatus.js`
- Create: `spreadworks/frontend/src/hooks/useBotPositions.js`
- Create: `spreadworks/frontend/src/hooks/useBotEquity.js`

- [ ] **Step 1: Implement** — `useBotStatus.js`

```javascript
import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

export function useBotStatus(bot, intervalMs = 5000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const d = await botApi.status(bot);
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, intervalMs]);
  return { data, error };
}
```

- [ ] **Step 2: Implement** — `useBotPositions.js`

```javascript
import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

export function useBotPositions(bot, intervalMs = 5000) {
  const [positions, setPositions] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const d = await botApi.positions(bot);
        if (!cancelled) setPositions(d.positions || []);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, intervalMs]);
  return { positions, error };
}
```

- [ ] **Step 3: Implement** — `useBotEquity.js`

```javascript
import { useEffect, useState } from 'react';
import { botApi } from '../lib/botApi';

export function useBotEquity(bot, mode = 'intraday', intervalMs = 30000) {
  const [curve, setCurve] = useState([]);
  const [error, setError] = useState(null);
  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const d = mode === 'intraday'
          ? await botApi.equityIntraday(bot)
          : await botApi.equityCurve(bot);
        const points = mode === 'intraday'
          ? (d.snapshots || []).map(s => ({ time: s.snapshot_time, equity: Number(s.equity) }))
          : (d.curve   || []).map(s => ({ time: s.time, equity: Number(s.equity) }));
        if (!cancelled) setCurve(points);
      } catch (e) {
        if (!cancelled) setError(e);
      }
    }
    tick();
    const h = setInterval(tick, intervalMs);
    return () => { cancelled = true; clearInterval(h); };
  }, [bot, mode, intervalMs]);
  return { curve, error };
}
```

- [ ] **Step 4: Commit**

```bash
git add spreadworks/frontend/src/hooks/useBotStatus.js spreadworks/frontend/src/hooks/useBotPositions.js spreadworks/frontend/src/hooks/useBotEquity.js
git commit -m "feat(spreadworks): React hooks for bot status/positions/equity"
```

---

## Task 16: Frontend pages — BotsOverview + BotCard

**Files:**
- Create: `spreadworks/frontend/src/components/bots/BotCard.jsx`
- Create: `spreadworks/frontend/src/pages/BotsOverview.jsx`
- Modify: `spreadworks/frontend/src/App.jsx`

- [ ] **Step 1: Implement BotCard** — `spreadworks/frontend/src/components/bots/BotCard.jsx`

```jsx
import { Link } from 'react-router-dom';
import { useBotStatus } from '../../hooks/useBotStatus';
import { BOT_REGISTRY, STRATEGY_LABEL, BOT_THEME } from '../../lib/botRegistry';

export default function BotCard({ bot }) {
  const { data, error } = useBotStatus(bot, 5000);
  const meta = BOT_REGISTRY[bot];
  const theme = BOT_THEME[bot];
  if (error) return <div className="bot-card error">Failed to load {bot}</div>;
  if (!data) return <div className="bot-card loading">Loading {bot}…</div>;
  return (
    <Link to={`/bots/${bot}`} className="bot-card"
          style={{ borderLeft: `4px solid ${theme.accent}` }}>
      <div className="bot-card-header">
        <div className="bot-name">{meta.display}</div>
        <div className="bot-strategy">{STRATEGY_LABEL[meta.strategy]}</div>
      </div>
      <div className="bot-card-row">
        <div>Enabled</div>
        <div>{data.enabled ? 'Yes' : 'No'}</div>
      </div>
      <div className="bot-card-row">
        <div>Open positions</div>
        <div>{data.open_positions}</div>
      </div>
      <div className="bot-card-row">
        <div>Equity</div>
        <div>${data.equity.toFixed(2)}</div>
      </div>
      <div className="bot-card-row muted">
        <div>Last scan</div>
        <div>{data.last_scan_at || '—'}</div>
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Implement BotsOverview** — `spreadworks/frontend/src/pages/BotsOverview.jsx`

```jsx
import BotCard from '../components/bots/BotCard';

export default function BotsOverview() {
  return (
    <div className="bots-overview">
      <h1>Bots</h1>
      <p className="hint">
        Automated paper-trading bots running inside SpreadWorks.
        Toggle a bot on from its dashboard.
      </p>
      <div className="bots-grid">
        {['gust', 'tide', 'drift'].map(b => <BotCard key={b} bot={b} />)}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add `react-router-dom` if missing**

Check `spreadworks/frontend/package.json` for `react-router-dom`. If absent:

```bash
cd spreadworks/frontend
npm install react-router-dom@6
```

- [ ] **Step 4: Add routes in App.jsx**

Read `spreadworks/frontend/src/App.jsx`, then wrap the existing top-level
component with a `<BrowserRouter>` and add `<Routes>`. Example diff:

```jsx
// At top:
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import BotsOverview from './pages/BotsOverview';
import BotDashboard from './pages/BotDashboard';

// Wrap return:
return (
  <BrowserRouter>
    <Routes>
      <Route path="/bots" element={<BotsOverview />} />
      <Route path="/bots/:bot" element={<BotDashboard />} />
      <Route path="/*" element={<ExistingHomeComponent />} />
    </Routes>
  </BrowserRouter>
);
```

Replace `ExistingHomeComponent` with whatever the current App returns.

- [ ] **Step 5: Commit**

```bash
git add spreadworks/frontend/src/pages/BotsOverview.jsx spreadworks/frontend/src/components/bots/BotCard.jsx spreadworks/frontend/src/App.jsx spreadworks/frontend/package.json spreadworks/frontend/package-lock.json
git commit -m "feat(spreadworks): /bots overview page with bot cards"
```

---

## Task 17: Frontend pages — BotDashboard + tabs

**Files:**
- Create: `spreadworks/frontend/src/components/bots/EquityTab.jsx`
- Create: `spreadworks/frontend/src/components/bots/PerformanceTab.jsx`
- Create: `spreadworks/frontend/src/components/bots/PositionsTab.jsx`
- Create: `spreadworks/frontend/src/components/bots/TradesTab.jsx`
- Create: `spreadworks/frontend/src/components/bots/LogsTab.jsx`
- Create: `spreadworks/frontend/src/components/bots/ConfigTab.jsx`
- Create: `spreadworks/frontend/src/pages/BotDashboard.jsx`

- [ ] **Step 1: BotDashboard with tab state** — `spreadworks/frontend/src/pages/BotDashboard.jsx`

```jsx
import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { BOT_REGISTRY, STRATEGY_LABEL } from '../lib/botRegistry';
import { botApi } from '../lib/botApi';
import { useBotStatus } from '../hooks/useBotStatus';
import EquityTab from '../components/bots/EquityTab';
import PerformanceTab from '../components/bots/PerformanceTab';
import PositionsTab from '../components/bots/PositionsTab';
import TradesTab from '../components/bots/TradesTab';
import LogsTab from '../components/bots/LogsTab';
import ConfigTab from '../components/bots/ConfigTab';

const TABS = ['Equity', 'Performance', 'Positions', 'Trades', 'Logs', 'Config'];

export default function BotDashboard() {
  const { bot } = useParams();
  const meta = BOT_REGISTRY[bot];
  const { data: status } = useBotStatus(bot, 5000);
  const [tab, setTab] = useState('Equity');

  if (!meta) return <div className="page-error">Unknown bot: {bot}</div>;

  async function onToggle() { await botApi.toggle(bot); }
  async function onForceTrade() { await botApi.forceTrade(bot); }

  return (
    <div className="bot-dashboard">
      <header>
        <Link to="/bots" className="back">← Bots</Link>
        <h1>{meta.display}</h1>
        <div className="bot-strategy-sub">{STRATEGY_LABEL[meta.strategy]} · {meta.ticker}</div>
        <div className="bot-toolbar">
          <button onClick={onToggle}>
            {status?.enabled ? 'Disable' : 'Enable'}
          </button>
          <button onClick={onForceTrade}>Force Trade</button>
          <div className="equity">Equity: ${status?.equity?.toFixed(2) ?? '—'}</div>
        </div>
      </header>
      <nav className="tabs">
        {TABS.map(t => (
          <button key={t} className={t === tab ? 'active' : ''}
                  onClick={() => setTab(t)}>{t}</button>
        ))}
      </nav>
      <section className="tab-body">
        {tab === 'Equity' && <EquityTab bot={bot} />}
        {tab === 'Performance' && <PerformanceTab bot={bot} />}
        {tab === 'Positions' && <PositionsTab bot={bot} />}
        {tab === 'Trades' && <TradesTab bot={bot} />}
        {tab === 'Logs' && <LogsTab bot={bot} />}
        {tab === 'Config' && <ConfigTab bot={bot} />}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: EquityTab** — `spreadworks/frontend/src/components/bots/EquityTab.jsx`

```jsx
import { useState } from 'react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { useBotEquity } from '../../hooks/useBotEquity';

export default function EquityTab({ bot }) {
  const [mode, setMode] = useState('intraday');
  const { curve } = useBotEquity(bot, mode, 15000);
  return (
    <div>
      <div className="mode-toggle">
        <button className={mode==='intraday'?'active':''} onClick={() => setMode('intraday')}>Intraday</button>
        <button className={mode==='historical'?'active':''} onClick={() => setMode('historical')}>Historical</button>
      </div>
      {curve.length < 2 ? (
        <div className="empty">No equity points yet. Bot will write one per scan cycle.</div>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={curve}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" tickFormatter={t => new Date(t).toLocaleTimeString()} />
            <YAxis dataKey="equity" domain={['dataMin - 50', 'dataMax + 50']} />
            <Tooltip />
            <Line type="monotone" dataKey="equity" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
```

- [ ] **Step 3: PerformanceTab** — `spreadworks/frontend/src/components/bots/PerformanceTab.jsx`

```jsx
import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function PerformanceTab({ bot }) {
  const [perf, setPerf] = useState(null);
  useEffect(() => { botApi.performance(bot).then(setPerf).catch(()=>{}); }, [bot]);
  if (!perf) return <div className="loading">Loading…</div>;
  return (
    <div className="performance-grid">
      <div><label>Trades</label><span>{perf.trades}</span></div>
      <div><label>Win rate</label><span>{(perf.win_rate*100).toFixed(1)}%</span></div>
      <div><label>Total P&amp;L</label><span>${perf.total_pnl.toFixed(2)}</span></div>
      <div><label>Avg win</label><span>${perf.avg_win.toFixed(2)}</span></div>
      <div><label>Avg loss</label><span>${perf.avg_loss.toFixed(2)}</span></div>
    </div>
  );
}
```

- [ ] **Step 4: PositionsTab** — `spreadworks/frontend/src/components/bots/PositionsTab.jsx`

```jsx
import { useBotPositions } from '../../hooks/useBotPositions';
import { botApi } from '../../lib/botApi';

export default function PositionsTab({ bot }) {
  const { positions } = useBotPositions(bot, 5000);
  async function onClose(pid) { await botApi.forceClose(bot, pid); }
  if (positions.length === 0) return <div className="empty">No open positions.</div>;
  return (
    <table className="positions-table">
      <thead><tr>
        <th>ID</th><th>Strategy</th><th>Legs</th><th>Entry</th>
        <th>MTM Value</th><th>MTM P&amp;L</th><th>PT / SL</th><th></th>
      </tr></thead>
      <tbody>
        {positions.map(p => (
          <tr key={p.position_id}>
            <td>{p.position_id}</td>
            <td>{p.strategy}</td>
            <td>{(p.legs||[]).map(l => `${l.side[0]}${l.type[0]} ${l.strike}`).join(' / ')}</td>
            <td>{Number(p.entry_price).toFixed(2)}</td>
            <td>{p.mtm_value ? Number(p.mtm_value).toFixed(2) : '—'}</td>
            <td>{p.mtm_pnl ? `$${Number(p.mtm_pnl).toFixed(2)}` : '—'}</td>
            <td>${Number(p.pt_target_pnl).toFixed(0)} / ${Number(p.sl_target_pnl).toFixed(0)}</td>
            <td><button onClick={() => onClose(p.position_id)}>Close</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: TradesTab** — `spreadworks/frontend/src/components/bots/TradesTab.jsx`

```jsx
import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function TradesTab({ bot }) {
  const [trades, setTrades] = useState([]);
  useEffect(() => {
    botApi.trades(bot, 100).then(d => setTrades(d.trades || [])).catch(()=>{});
  }, [bot]);
  if (trades.length === 0) return <div className="empty">No closed trades yet.</div>;
  return (
    <table className="trades-table">
      <thead><tr>
        <th>Closed</th><th>Reason</th><th>P&amp;L</th><th>Entry</th><th>Close</th><th>Contracts</th>
      </tr></thead>
      <tbody>
        {trades.map(t => (
          <tr key={t.position_id} className={Number(t.realized_pnl) >= 0 ? 'win' : 'loss'}>
            <td>{t.close_time}</td>
            <td>{t.close_reason}</td>
            <td>${Number(t.realized_pnl).toFixed(2)}</td>
            <td>{Number(t.entry_price).toFixed(2)}</td>
            <td>{Number(t.close_price).toFixed(2)}</td>
            <td>{t.contracts}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 6: LogsTab** — `spreadworks/frontend/src/components/bots/LogsTab.jsx`

```jsx
import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

export default function LogsTab({ bot }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    botApi.scanActivity(bot, 200).then(d => setRows(d.rows || [])).catch(()=>{});
  }, [bot]);
  return (
    <table className="logs-table">
      <thead><tr><th>Time</th><th>Outcome</th><th>Reason</th><th>Position</th></tr></thead>
      <tbody>
        {rows.map(r => (
          <tr key={r.id}>
            <td>{r.scan_time}</td>
            <td>{r.outcome}</td>
            <td>{r.reason || ''}</td>
            <td>{r.position_id || ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 7: ConfigTab** — `spreadworks/frontend/src/components/bots/ConfigTab.jsx`

```jsx
import { useEffect, useState } from 'react';
import { botApi } from '../../lib/botApi';

const FIELDS = [
  ['starting_capital','number'], ['max_contracts','number'],
  ['bp_pct','number'], ['sd_mult','number'],
  ['pt_pct','number'], ['sl_pct','number'],
  ['entry_start_ct','text'], ['entry_end_ct','text'], ['eod_close_ct','text'],
  ['delta_skew','number'],
  ['discord_alerts','checkbox'], ['use_gex_walls','checkbox'],
];

export default function ConfigTab({ bot }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { botApi.config(bot).then(setCfg).catch(()=>{}); }, [bot]);
  if (!cfg) return <div className="loading">Loading…</div>;

  function onChange(k, v) { setCfg(prev => ({ ...prev, [k]: v })); }
  async function onSave() {
    setSaving(true);
    try {
      const body = {};
      for (const [k] of FIELDS) body[k] = cfg[k];
      const updated = await botApi.saveConfig(bot, body);
      setCfg(updated);
    } finally { setSaving(false); }
  }

  return (
    <div className="config-form">
      {FIELDS.map(([k, type]) => (
        <div key={k} className="config-row">
          <label>{k}</label>
          {type === 'checkbox' ? (
            <input type="checkbox" checked={!!cfg[k]} onChange={e => onChange(k, e.target.checked)} />
          ) : (
            <input type={type} value={cfg[k] ?? ''}
                   onChange={e => onChange(k, type === 'number' ? Number(e.target.value) : e.target.value)} />
          )}
        </div>
      ))}
      <button onClick={onSave} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    </div>
  );
}
```

- [ ] **Step 8: Commit**

```bash
git add spreadworks/frontend/src/pages/BotDashboard.jsx spreadworks/frontend/src/components/bots/
git commit -m "feat(spreadworks): BotDashboard with 6 tabs (Equity/Perf/Positions/Trades/Logs/Config)"
```

---

## Task 18: Build + deploy

**Files:**
- Modify: `spreadworks/frontend/dist/` (rebuilt)

Per `feedback_spreadworks_dist_drift_2026_05_17`: the Render service serves
the committed `dist/` directly, no `npm run build` on deploy. We must
rebuild and commit it.

- [ ] **Step 1: Build the frontend**

```bash
cd C:/Users/lemol/alphagex/spreadworks/frontend
npm install
npm run build
```

Expected: `dist/` directory regenerated with the new pages.

- [ ] **Step 2: Verify dist contents include the new pages**

```bash
ls C:/Users/lemol/alphagex/spreadworks/frontend/dist/assets/ | head
```

- [ ] **Step 3: Commit dist**

```bash
git add spreadworks/frontend/dist/
git commit -m "build(spreadworks): rebuild dist with bot dashboards"
```

- [ ] **Step 4: Run the full test suite once more**

```bash
cd C:/Users/lemol/alphagex/spreadworks
pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Merge to main**

```bash
git checkout main
git pull
git merge --no-ff claude/spreadworks-auto-bots
git push origin main
```

Render auto-deploys. After 2–3 min, smoke-test:

```bash
curl -s https://<your-spreadworks-host>/api/spreadworks/bots | jq
```

Expected: JSON listing all 3 bots, each `enabled: false`, `open_positions: 0`.

---

## Self-Review Notes

- **Spec coverage:** All 14 spec sections map to tasks. §3 architecture → tasks 1-3, 10-12. §4 registry → task 2. §5 schema → task 3. §6 strategies → tasks 4-6. §7 monitor → task 8. §8 routes → task 12. §9 frontend → tasks 14-17. §10 risk → enforced across tasks (paper-only lock in task 7, no-overwrite seed in task 3, per-bot timeout in task 9). §11 Discord → task 13. §12 testing → each strategy/executor/monitor/scanner has its own test task. §13 open questions → out of scope by design. §14 acceptance criteria → verified in task 18 smoke test.
- **Placeholder scan:** No "TBD"/"TODO" remain. The only conditional in task 10 (`is_event_blackout_active` import name) is flagged with an explicit "verify by grep" instruction rather than left as a placeholder.
- **Type consistency:** `ChainProvider` protocol in task 9 (`get_chain`, `get_leg_mids`) matches the live implementation in task 11. `IronButterflySignal.legs()`, `DoubleCalendarSignal.legs()`, `DoubleDiagonalSignal.legs()` all return the same `{side, type, strike, expiration, entry_price}` shape used by executor task 7 and scanner task 9. `bot_table(bot, name)` signature consistent across all tasks. `decide_exit` parameters in task 8 match invocation in task 9.
