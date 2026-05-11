# JOSHUA Directional GEX Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate then ship a 1DTE SPY directional bot driven by the production `/api/gex/SPY` feed, using a 3-setup stack (wall_fade / wall_break / flip_cross) with hard same-day exits.

**Architecture:** Promote the dormant HELIOS scaffold from `claude/helios-1dte-directional-design` (DB tables, routes, frontend page, executor, paper-account flow). Replace `signals.py` / `strategy.py` with a setup-stack dispatcher that consumes a `GexSnapshot` from a new `gex_client.py` polling `/api/gex/SPY`. Add a `helios_daily_state` table for per-setup armed/fired tracking. Validate via Phase A: a 3-month replay over `watchtower_snapshots`+`argus_strikes` (joined to derive call_wall / put_wall / flip_point) before committing live cycles. If replay GO, smoke-test paper Phase B for 4-6 weeks.

**Tech Stack:** Python 3.11, FastAPI, psycopg2, pytest. Production postgres (`DATABASE_URL`) for live + replay data. Black-Scholes pricing already at `quant/bs.py`. Walks-forward harness pattern reused from `backtest/touch_pin/` and `backtest/skew_signal/`.

**Spec:** `docs/superpowers/specs/2026-05-11-joshua-directional-gex-bot-design.md`

---

## File Structure

```
trading/helios/
├── __init__.py             # PROMOTE from helios branch (unchanged)
├── models.py               # PROMOTE + add SetupType enum, DailyState dataclass
├── db.py                   # PROMOTE + add load_daily_state, upsert_daily_state, insert_signal_v2
├── executor.py             # PROMOTE (unchanged)
├── monitor.py              # PROMOTE + rewrite exit logic (no trail, time-stop 15:55 CT)
├── trader.py               # PROMOTE + rewrite run_cycle to use gex_client + setup dispatch
├── signals.py              # REPLACE — setup-stack dispatcher
├── strategy.py             # REPLACE — exit decision tree (PT/SL/TIME_STOP)
├── gex_client.py           # NEW — polls /api/gex/SPY, returns GexSnapshot, 90s staleness gate
└── setups/
    ├── __init__.py         # NEW — exports evaluate_all
    ├── base.py             # NEW — SetupAction dataclass, BaseSetup ABC
    ├── wall_fade.py        # NEW — positive-gamma mean-reversion
    ├── wall_break.py       # NEW — negative-gamma momentum
    └── flip_cross.py       # NEW — regime-transition with 5-min buffer

migrations/
├── 2026-05-07-helios-bot-tables.sql       # PROMOTE from helios branch (idempotent)
├── 2026-05-07-helios-options-intraday.sql # PROMOTE (idempotent)
└── 2026-05-11-helios-daily-state.sql      # NEW — single-table migration

backend/api/routes/
└── helios_routes.py         # PROMOTE (unchanged) — 13 routes at /api/joshua/*

frontend/src/app/joshua/
├── page.tsx                 # PROMOTE (unchanged)
└── components/JoshuaEquityChart.tsx  # PROMOTE (unchanged)

scheduler/
└── trader_scheduler.py      # MODIFY — register HeliosTrader at 60s interval (if not already)

backtest/joshua_replay/      # NEW — Phase A replay harness
├── __init__.py
├── data.py                  # snapshot loader (watchtower_snapshots + argus_strikes join, walls/flip reconstruction)
├── quotes.py                # 1DTE option mid loader (helios_options_intraday OR Black-Scholes synthetic)
├── engine.py                # replay loop: snapshot → setup dispatch → vertical → simulate_intraday
├── report.py                # markdown + CSV; per-setup WR/EV
└── cli.py                   # python -m backtest.joshua_replay --start ... --end ...

tests/trading/helios/
├── __init__.py              # PROMOTE
├── test_models.py           # PROMOTE + add SetupType / DailyState tests
├── test_executor.py         # PROMOTE (unchanged)
├── test_gex_client.py       # NEW
├── test_signals_dispatch.py # NEW — replaces test_signals.py
├── test_strategy.py         # REPLACE — new exit logic
├── test_db_daily_state.py   # NEW
└── setups/
    ├── __init__.py          # NEW
    ├── test_wall_fade.py    # NEW
    ├── test_wall_break.py   # NEW
    └── test_flip_cross.py   # NEW

tests/backtest/joshua_replay/
├── __init__.py
├── test_data.py             # NEW — snapshot loader with fixture
├── test_engine.py           # NEW — synthetic snapshot → expected trade
└── test_report.py           # NEW

docs/superpowers/reports/
└── 2026-05-11-joshua-replay.md   # Phase A output (committed at end of Task 22)
```

---

## Task 0: Setup branch and verify scaffold availability

**Files:**
- Verify: `C:/Users/lemol/AlphaGEX/trading/helios/` does not yet exist on `claude/joshua-directional-gex-bot` branch (only `__pycache__`)
- Reference: `origin/claude/helios-1dte-directional-design` has the scaffold

- [ ] **Step 1: Confirm working branch and clean state**

Run: `git status && git branch --show-current`
Expected:
```
On branch claude/joshua-directional-gex-bot
Your branch is up to date with 'origin/claude/joshua-directional-gex-bot'.
nothing to commit, working tree clean
```
(Untracked `backtest/*/output/final_report_*.md` files are pre-existing and can be ignored.)

- [ ] **Step 2: Confirm helios scaffold is available on remote**

Run: `git ls-tree -r origin/claude/helios-1dte-directional-design --name-only | grep "trading/helios/"`
Expected:
```
trading/helios/__init__.py
trading/helios/db.py
trading/helios/executor.py
trading/helios/models.py
trading/helios/monitor.py
trading/helios/signals.py
trading/helios/strategy.py
trading/helios/trader.py
```

---

## Task 1: Promote HELIOS scaffold from helios branch

**Files:**
- Create: `trading/helios/__init__.py`, `db.py`, `executor.py`, `models.py`, `monitor.py`, `signals.py`, `strategy.py`, `trader.py`
- Create: `backend/api/routes/helios_routes.py`
- Create: `frontend/src/app/joshua/page.tsx`, `frontend/src/app/joshua/components/JoshuaEquityChart.tsx`
- Create: `migrations/2026-05-07-helios-bot-tables.sql`, `migrations/2026-05-07-helios-options-intraday.sql`
- Create: `tests/trading/helios/__init__.py`, `test_executor.py`, `test_models.py`, `test_signals.py`, `test_strategy.py`

- [ ] **Step 1: Check out helios files into this branch (no merge of unrelated commits)**

Run:
```bash
git checkout origin/claude/helios-1dte-directional-design -- \
  trading/helios/ \
  backend/api/routes/helios_routes.py \
  frontend/src/app/joshua/ \
  migrations/2026-05-07-helios-bot-tables.sql \
  migrations/2026-05-07-helios-options-intraday.sql \
  tests/trading/helios/
```
Expected: no errors. `git status` shows the new files under "Changes to be committed".

- [ ] **Step 2: Verify imports do not break the rest of the repo**

Run: `python -c "from trading.helios import db, models, executor, monitor, signals, strategy, trader; print('OK')"`
Expected: `OK` (with optional warnings about missing modules being OK if dependencies are intentionally re-imported lazily).

If `quant.gex_walls` is missing on this branch, that's expected — we'll remove it in Task 7 (signals.py rewrite). For now the import will error; record the trace and proceed.

- [ ] **Step 3: Run the promoted unit tests as-is to establish a baseline**

Run: `pytest tests/trading/helios/test_executor.py tests/trading/helios/test_models.py -v --no-cov`
Expected: both files pass. `test_signals.py` / `test_strategy.py` will fail because dependencies will be replaced — that's expected; those tests get replaced in Tasks 7 and 9.

- [ ] **Step 4: Commit the scaffold promotion**

```bash
git add trading/helios/ backend/api/routes/helios_routes.py frontend/src/app/joshua/ migrations/2026-05-07-helios-bot-tables.sql migrations/2026-05-07-helios-options-intraday.sql tests/trading/helios/
git commit -m "joshua: promote HELIOS scaffold (db, routes, frontend, migrations, executor/monitor/trader)"
```

---

## Task 2: Add `helios_daily_state` migration

**Files:**
- Create: `migrations/2026-05-11-helios-daily-state.sql`

- [ ] **Step 1: Write the migration file**

```sql
-- JOSHUA — per-day setup armed/fired tracking.
-- One row per trading day. Each setup arms at market open and locks after firing.

CREATE TABLE IF NOT EXISTS helios_daily_state (
    trade_date          DATE         PRIMARY KEY,
    wall_fade_fired     BOOLEAN      NOT NULL DEFAULT FALSE,
    wall_break_fired    BOOLEAN      NOT NULL DEFAULT FALSE,
    flip_cross_fired    BOOLEAN      NOT NULL DEFAULT FALSE,
    last_signal_minute  INTEGER,
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_helios_daily_state_date
    ON helios_daily_state(trade_date DESC);
```

- [ ] **Step 2: Verify the migration is well-formed SQL**

Run (Windows): `python -c "import psycopg2.extensions; open('migrations/2026-05-11-helios-daily-state.sql').read()"`
Expected: no exception (parsing handled when applied).

- [ ] **Step 3: Commit the migration**

```bash
git add migrations/2026-05-11-helios-daily-state.sql
git commit -m "joshua: migration — helios_daily_state table"
```

(Apply against production postgres is deferred to Task 19 — pre-merge step.)

---

## Task 3: Extend `models.py` with `SetupType`, `DailyState`, and exit-reason enums

**Files:**
- Modify: `trading/helios/models.py`
- Test: `tests/trading/helios/test_models.py`

- [ ] **Step 1: Write failing tests for the new types**

Append to `tests/trading/helios/test_models.py`:

```python
import datetime as dt
import pytest

from trading.helios.models import (
    SetupType, DailyState, ExitReason, JoshuaConfig
)


def test_setup_type_values():
    assert SetupType.WALL_FADE.value == "wall_fade"
    assert SetupType.WALL_BREAK.value == "wall_break"
    assert SetupType.FLIP_CROSS.value == "flip_cross"


def test_daily_state_default_unfired():
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    assert state.wall_fade_fired is False
    assert state.wall_break_fired is False
    assert state.flip_cross_fired is False
    assert state.last_signal_minute is None


def test_daily_state_setup_fired_check():
    state = DailyState(trade_date=dt.date(2026, 5, 11), wall_fade_fired=True)
    assert state.is_fired(SetupType.WALL_FADE)
    assert not state.is_fired(SetupType.WALL_BREAK)
    assert not state.is_fired(SetupType.FLIP_CROSS)


def test_exit_reason_values():
    assert ExitReason.PT.value == "PT"
    assert ExitReason.SL.value == "SL"
    assert ExitReason.TIME_STOP.value == "TIME_STOP"
    assert ExitReason.DATA_FAILURE.value == "DATA_FAILURE"


def test_joshua_config_defaults():
    cfg = JoshuaConfig()
    assert cfg.ticker == "SPY"
    assert cfg.profit_target_pct == 20.0
    assert cfg.stop_loss_pct == 30.0
    assert cfg.eod_time_ct == "15:55"
    assert cfg.risk_per_trade_pct == 0.20
    assert cfg.buying_power_usage_pct == 0.85
    assert cfg.spread_width == 1
    assert cfg.gex_stale_max_seconds == 90
    assert cfg.poll_seconds == 60
    assert cfg.wall_fade_em_threshold == 0.30
    assert cfg.wall_break_em_threshold == 0.20
    assert cfg.flip_hysteresis_pct == 0.0015  # 0.15%
    assert cfg.flip_buffer_minutes == 5
```

- [ ] **Step 2: Run tests; expect import errors**

Run: `pytest tests/trading/helios/test_models.py -v --no-cov`
Expected: `ImportError: cannot import name 'SetupType' ...`

- [ ] **Step 3: Add the new types to `models.py`**

Append to `trading/helios/models.py`:

```python
class SetupType(str, Enum):
    WALL_FADE = "wall_fade"
    WALL_BREAK = "wall_break"
    FLIP_CROSS = "flip_cross"


class ExitReason(str, Enum):
    PT = "PT"
    SL = "SL"
    TIME_STOP = "TIME_STOP"
    DATA_FAILURE = "DATA_FAILURE"


@dataclass(frozen=True)
class DailyState:
    trade_date: dt.date
    wall_fade_fired: bool = False
    wall_break_fired: bool = False
    flip_cross_fired: bool = False
    last_signal_minute: Optional[int] = None

    def is_fired(self, setup: SetupType) -> bool:
        return {
            SetupType.WALL_FADE: self.wall_fade_fired,
            SetupType.WALL_BREAK: self.wall_break_fired,
            SetupType.FLIP_CROSS: self.flip_cross_fired,
        }[setup]


@dataclass(frozen=True)
class JoshuaConfig:
    ticker: str = "SPY"
    spread_width: int = 1
    profit_target_pct: float = 20.0
    stop_loss_pct: float = 30.0
    eod_time_ct: str = "15:55"
    risk_per_trade_pct: float = 0.20
    buying_power_usage_pct: float = 0.85
    gex_stale_max_seconds: int = 90
    poll_seconds: int = 60
    wall_fade_em_threshold: float = 0.30
    wall_break_em_threshold: float = 0.20
    flip_hysteresis_pct: float = 0.0015  # ±0.15%
    flip_buffer_minutes: int = 5
    quotes_unavailable_max_cycles: int = 10
```

Top-of-file imports need `import datetime as dt` added if not already present.

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/test_models.py -v --no-cov`
Expected: all new tests pass; the original tests (test_setup_type_values is new; old SpreadType/SkipReason tests stay) still pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/models.py tests/trading/helios/test_models.py
git commit -m "joshua: add SetupType, DailyState, ExitReason, JoshuaConfig"
```

---

## Task 4: Extend `db.py` with `load_daily_state` / `upsert_daily_state` / `insert_signal_v2`

**Files:**
- Modify: `trading/helios/db.py`
- Test: `tests/trading/helios/test_db_daily_state.py`

- [ ] **Step 1: Write failing test (uses real DATABASE_URL gated by env)**

Create `tests/trading/helios/test_db_daily_state.py`:

```python
"""DB tests for helios_daily_state — require DATABASE_URL."""
import datetime as dt
import os
import pytest

from trading.helios.db import HeliosDatabase
from trading.helios.models import DailyState, SetupType


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping DB-backed test",
)


def _fresh_db():
    db = HeliosDatabase()
    today = dt.date.today()
    with db._connect() as conn:
        with conn.cursor() as c:
            c.execute("DELETE FROM helios_daily_state WHERE trade_date = %s", (today,))
        conn.commit()
    return db, today


def test_load_daily_state_missing_returns_blank_state():
    db, today = _fresh_db()
    state = db.load_daily_state(today)
    assert state.trade_date == today
    assert not state.wall_fade_fired
    assert not state.wall_break_fired
    assert not state.flip_cross_fired


def test_upsert_daily_state_sets_setup_fired():
    db, today = _fresh_db()
    db.upsert_daily_state(today, fired=SetupType.WALL_FADE, signal_minute=120)
    state = db.load_daily_state(today)
    assert state.wall_fade_fired is True
    assert state.wall_break_fired is False
    assert state.last_signal_minute == 120


def test_upsert_daily_state_idempotent_multi_setup():
    db, today = _fresh_db()
    db.upsert_daily_state(today, fired=SetupType.WALL_FADE, signal_minute=60)
    db.upsert_daily_state(today, fired=SetupType.FLIP_CROSS, signal_minute=200)
    state = db.load_daily_state(today)
    assert state.wall_fade_fired is True
    assert state.flip_cross_fired is True
    assert state.last_signal_minute == 200
```

- [ ] **Step 2: Run test; expect skip or method-missing error**

Run: `pytest tests/trading/helios/test_db_daily_state.py -v --no-cov`
Expected: either all three SKIPPED (no DATABASE_URL) or all three FAIL with `AttributeError: 'HeliosDatabase' object has no attribute 'load_daily_state'`.

- [ ] **Step 3: Add the daily-state methods to `db.py`**

Append the following methods to `HeliosDatabase` in `trading/helios/db.py`:

```python
    # =========================================================================
    # READS / WRITES — daily setup state
    # =========================================================================

    def load_daily_state(self, trade_date) -> "DailyState":
        """Return the daily state for trade_date. If no row, return blank."""
        from .models import DailyState  # avoid circular at module import
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
                c.execute(
                    """
                    SELECT trade_date, wall_fade_fired, wall_break_fired,
                           flip_cross_fired, last_signal_minute
                    FROM helios_daily_state
                    WHERE trade_date = %s
                    """,
                    (trade_date,),
                )
                row = c.fetchone()
                if row is None:
                    return DailyState(trade_date=trade_date)
                return DailyState(
                    trade_date=row["trade_date"],
                    wall_fade_fired=row["wall_fade_fired"],
                    wall_break_fired=row["wall_break_fired"],
                    flip_cross_fired=row["flip_cross_fired"],
                    last_signal_minute=row["last_signal_minute"],
                )

    def upsert_daily_state(self, trade_date, *, fired, signal_minute: Optional[int] = None) -> None:
        """Set `<setup>_fired = TRUE` for the given setup. Upserts the row.

        `fired` is a SetupType. signal_minute is optional minutes-since-open.
        """
        column_map = {
            "wall_fade": "wall_fade_fired",
            "wall_break": "wall_break_fired",
            "flip_cross": "flip_cross_fired",
        }
        col = column_map[fired.value if hasattr(fired, "value") else fired]
        with self._connect() as conn:
            with conn.cursor() as c:
                c.execute(
                    f"""
                    INSERT INTO helios_daily_state (trade_date, {col}, last_signal_minute)
                    VALUES (%s, TRUE, %s)
                    ON CONFLICT (trade_date)
                    DO UPDATE SET
                        {col} = TRUE,
                        last_signal_minute = COALESCE(EXCLUDED.last_signal_minute, helios_daily_state.last_signal_minute),
                        updated_at = NOW()
                    """,
                    (trade_date, signal_minute),
                )
                conn.commit()
```

- [ ] **Step 4: Run tests; expect skip or pass**

Run: `pytest tests/trading/helios/test_db_daily_state.py -v --no-cov`
Expected: all three SKIPPED (no DATABASE_URL) or PASS (with DATABASE_URL after migration applied).

If the migration hasn't been applied to dev DB yet, run:
```bash
psql $DATABASE_URL -f migrations/2026-05-11-helios-daily-state.sql
```

- [ ] **Step 5: Commit**

```bash
git add trading/helios/db.py tests/trading/helios/test_db_daily_state.py
git commit -m "joshua: db — load_daily_state, upsert_daily_state helpers"
```

---

## Task 5: Build `gex_client.py` — polling client for `/api/gex/SPY`

**Files:**
- Create: `trading/helios/gex_client.py`
- Test: `tests/trading/helios/test_gex_client.py`

- [ ] **Step 1: Write failing tests**

Create `tests/trading/helios/test_gex_client.py`:

```python
"""Tests for the GexClient — pure transport + parse layer."""
import datetime as dt
import pytest

from trading.helios.gex_client import GexClient, GexSnapshot, GexStaleError


class FakeHttp:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        return self  # response-like

    def json(self):
        return self.payload

    @property
    def status_code(self):
        return self.status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")


def _payload(net_gex=2.0e9, spot=500.0, flip=499.0, call_wall=502.0, put_wall=496.0, vix=18.0):
    return {
        "success": True,
        "data": {
            "symbol": "SPY",
            "net_gex": net_gex,
            "flip_point": flip,
            "call_wall": call_wall,
            "put_wall": put_wall,
            "spot_price": spot,
            "vix": vix,
            "regime": "HIGH_POSITIVE",
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    }


def test_gex_client_parses_snapshot():
    http = FakeHttp(_payload())
    client = GexClient(base_url="http://test", http=http, stale_max_seconds=90)
    snap = client.get_spy(now=dt.datetime.now(dt.timezone.utc))
    assert isinstance(snap, GexSnapshot)
    assert snap.symbol == "SPY"
    assert snap.net_gex == 2.0e9
    assert snap.spot == 500.0
    assert snap.call_wall == 502.0
    assert snap.put_wall == 496.0
    assert snap.flip_point == 499.0
    assert snap.regime == "HIGH_POSITIVE"


def test_gex_client_rejects_stale_snapshot():
    # Snapshot timestamp is 2 minutes old, stale_max is 90s
    old_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=120)).isoformat()
    pl = _payload()
    pl["data"]["timestamp"] = old_ts
    http = FakeHttp(pl)
    client = GexClient(base_url="http://test", http=http, stale_max_seconds=90)
    with pytest.raises(GexStaleError):
        client.get_spy(now=dt.datetime.now(dt.timezone.utc))


def test_gex_client_sigma_1d_band_width_derived_from_vix_and_spot():
    http = FakeHttp(_payload(vix=20.0, spot=500.0))
    client = GexClient(base_url="http://test", http=http, stale_max_seconds=90)
    snap = client.get_spy(now=dt.datetime.now(dt.timezone.utc))
    # σ_1d ≈ spot * vix/100 * sqrt(1/252) — for vix=20 spot=500: 500*0.20*0.063 ≈ 6.30
    assert 5.5 <= snap.sigma_1d_band_width <= 7.0


def test_gex_client_retries_on_5xx_once():
    pl = _payload()
    bad = FakeHttp({}, status=502)
    good = FakeHttp(pl)
    calls = {"n": 0}

    class FakeHttpRetry:
        def get(self, url, timeout=None):
            calls["n"] += 1
            return bad if calls["n"] == 1 else good
        def json(self):
            return pl

    client = GexClient(base_url="http://test", http=FakeHttpRetry(), stale_max_seconds=90, retry_backoff=0.0)
    snap = client.get_spy(now=dt.datetime.now(dt.timezone.utc))
    assert calls["n"] == 2
    assert snap.symbol == "SPY"
```

- [ ] **Step 2: Run test; expect import error**

Run: `pytest tests/trading/helios/test_gex_client.py -v --no-cov`
Expected: `ImportError: cannot import name 'GexClient' from 'trading.helios.gex_client'`

- [ ] **Step 3: Implement `gex_client.py`**

Create `trading/helios/gex_client.py`:

```python
"""HELIOS — GEX polling client for /api/gex/SPY.

Wraps the production GEX endpoint with:
  - Parse → GexSnapshot dataclass
  - 90s staleness gate (raises GexStaleError)
  - Single retry on 5xx with backoff
  - 1-day expected-move computation from vix + spot

No external state. All I/O is via the injectable `http` object so this is
testable without a network.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252.0
SQRT_INV_TRADING_DAYS = math.sqrt(1.0 / TRADING_DAYS_PER_YEAR)


class GexStaleError(RuntimeError):
    """Raised when the upstream snapshot's timestamp is older than the staleness threshold."""


@dataclass(frozen=True)
class GexSnapshot:
    symbol: str
    spot: float
    net_gex: float
    flip_point: float
    call_wall: float
    put_wall: float
    vix: float
    regime: str
    sigma_1d_band_width: float  # 1-day 1-sigma move in dollars
    snapshot_at: dt.datetime    # tz-aware UTC


class GexClient:
    """Polling client. Inject `http` for tests."""

    def __init__(
        self,
        *,
        base_url: str,
        http=None,
        stale_max_seconds: int = 90,
        retry_backoff: float = 5.0,
        timeout: float = 5.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.stale_max_seconds = stale_max_seconds
        self.retry_backoff = retry_backoff
        self.timeout = timeout
        if http is None:
            import requests
            self.http = requests
        else:
            self.http = http

    def get_spy(self, *, now: Optional[dt.datetime] = None) -> GexSnapshot:
        url = f"{self.base_url}/api/gex/SPY"
        resp = self._get_with_retry(url)
        data = resp.json().get("data") or {}

        ts_raw = data.get("timestamp")
        snapshot_at = _parse_iso_utc(ts_raw) if ts_raw else (now or dt.datetime.now(dt.timezone.utc))
        now = now or dt.datetime.now(dt.timezone.utc)
        age_sec = (now - snapshot_at).total_seconds()
        if age_sec > self.stale_max_seconds:
            raise GexStaleError(f"gex snapshot age={age_sec:.1f}s > {self.stale_max_seconds}s")

        spot = float(data.get("spot_price") or 0.0)
        vix = float(data.get("vix") or 0.0)
        sigma_1d = spot * (vix / 100.0) * SQRT_INV_TRADING_DAYS if spot > 0 and vix > 0 else 0.0

        return GexSnapshot(
            symbol=str(data.get("symbol", "SPY")),
            spot=spot,
            net_gex=float(data.get("net_gex") or 0.0),
            flip_point=float(data.get("flip_point") or 0.0),
            call_wall=float(data.get("call_wall") or 0.0),
            put_wall=float(data.get("put_wall") or 0.0),
            vix=vix,
            regime=str(data.get("regime") or "NEUTRAL"),
            sigma_1d_band_width=sigma_1d,
            snapshot_at=snapshot_at,
        )

    def _get_with_retry(self, url):
        try:
            resp = self.http.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except Exception as e1:
            logger.warning("gex_client first-try failed (%s), retrying once", e1)
            if self.retry_backoff > 0:
                time.sleep(self.retry_backoff)
            resp = self.http.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp


def _parse_iso_utc(s: str) -> dt.datetime:
    s = s.replace("Z", "+00:00")
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/test_gex_client.py -v --no-cov`
Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/gex_client.py tests/trading/helios/test_gex_client.py
git commit -m "joshua: gex_client — GexSnapshot + 90s staleness gate + retry"
```

---

## Task 6: Build `setups/base.py` — `SetupAction` and `BaseSetup` ABC

**Files:**
- Create: `trading/helios/setups/__init__.py`
- Create: `trading/helios/setups/base.py`
- Test: `tests/trading/helios/setups/__init__.py`, `tests/trading/helios/setups/test_base.py`

- [ ] **Step 1: Write failing test**

Create `tests/trading/helios/setups/__init__.py` (empty file) and `tests/trading/helios/setups/test_base.py`:

```python
import pytest

from trading.helios.models import SetupType
from trading.helios.setups.base import SetupAction


def test_setup_action_call_vertical():
    a = SetupAction(
        setup=SetupType.WALL_FADE,
        direction="call",
        long_strike=500.0,
        short_strike=501.0,
        reason="test",
    )
    assert a.setup == SetupType.WALL_FADE
    assert a.direction == "call"
    assert a.long_strike == 500.0
    assert a.short_strike == 501.0


def test_setup_action_invalid_direction_raises():
    with pytest.raises(ValueError):
        SetupAction(
            setup=SetupType.WALL_FADE,
            direction="banana",
            long_strike=500.0,
            short_strike=501.0,
            reason="test",
        )
```

- [ ] **Step 2: Run test; expect import error**

Run: `pytest tests/trading/helios/setups/test_base.py -v --no-cov`
Expected: `ModuleNotFoundError: No module named 'trading.helios.setups'`

- [ ] **Step 3: Implement base + package init**

Create `trading/helios/setups/__init__.py`:
```python
"""JOSHUA setup stack — wall_fade, wall_break, flip_cross."""
```

Create `trading/helios/setups/base.py`:
```python
"""Base types for JOSHUA setups.

A SetupAction is the output of a setup's `evaluate(...)` method:
  - direction "call" → buy ATM call, sell ATM+spread_width call (BULL_CALL debit)
  - direction "put"  → buy ATM put, sell ATM-spread_width put (BEAR_PUT debit)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from trading.helios.models import SetupType


@dataclass(frozen=True)
class SetupAction:
    setup: SetupType
    direction: Literal["call", "put"]
    long_strike: float
    short_strike: float
    reason: str

    def __post_init__(self):
        if self.direction not in ("call", "put"):
            raise ValueError(f"direction must be 'call' or 'put', got {self.direction!r}")
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/setups/test_base.py -v --no-cov`
Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/setups/__init__.py trading/helios/setups/base.py tests/trading/helios/setups/__init__.py tests/trading/helios/setups/test_base.py
git commit -m "joshua: setups — SetupAction base type"
```

---

## Task 7: Build `setups/wall_fade.py` — positive-gamma mean-reversion

**Files:**
- Create: `trading/helios/setups/wall_fade.py`
- Test: `tests/trading/helios/setups/test_wall_fade.py`

- [ ] **Step 1: Write failing tests**

Create `tests/trading/helios/setups/test_wall_fade.py`:

```python
import datetime as dt
import pytest

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import SetupType, JoshuaConfig
from trading.helios.setups.wall_fade import evaluate


def _snap(*, spot=500.0, call_wall=501.0, put_wall=495.0, regime="HIGH_POSITIVE", sigma=5.0):
    return GexSnapshot(
        symbol="SPY",
        spot=spot,
        net_gex=2.0e9,
        flip_point=498.0,
        call_wall=call_wall,
        put_wall=put_wall,
        vix=18.0,
        regime=regime,
        sigma_1d_band_width=sigma,
        snapshot_at=dt.datetime.now(dt.timezone.utc),
    )


def test_wall_fade_fires_put_when_spot_near_call_wall():
    snap = _snap(spot=500.0, call_wall=501.0, sigma=5.0)  # (501-500)/5 = 0.20 < 0.30
    action = evaluate(snap, config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.WALL_FADE
    assert action.direction == "put"
    assert action.long_strike == 500.0
    assert action.short_strike == 499.0


def test_wall_fade_fires_call_when_spot_near_put_wall():
    snap = _snap(spot=496.0, put_wall=495.0, sigma=5.0)  # (496-495)/5 = 0.20 < 0.30
    action = evaluate(snap, config=JoshuaConfig())
    assert action is not None
    assert action.direction == "call"
    assert action.long_strike == 496.0
    assert action.short_strike == 497.0


def test_wall_fade_skips_when_spot_far_from_wall():
    snap = _snap(spot=500.0, call_wall=510.0, put_wall=490.0, sigma=5.0)
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_fade_skips_when_regime_not_positive():
    snap = _snap(spot=500.0, call_wall=501.0, sigma=5.0, regime="MODERATE_NEGATIVE")
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_fade_skips_when_sigma_zero():
    snap = _snap(spot=500.0, call_wall=501.0, sigma=0.0)
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_fade_picks_closer_wall_when_both_near():
    # Spot is closer to call_wall than put_wall — fade down
    snap = _snap(spot=500.0, call_wall=501.0, put_wall=499.0, sigma=10.0)
    action = evaluate(snap, config=JoshuaConfig())
    assert action.direction == "put"
```

- [ ] **Step 2: Run tests; expect import error**

Run: `pytest tests/trading/helios/setups/test_wall_fade.py -v --no-cov`
Expected: `ModuleNotFoundError: No module named 'trading.helios.setups.wall_fade'`

- [ ] **Step 3: Implement `wall_fade.py`**

Create `trading/helios/setups/wall_fade.py`:

```python
"""Setup 1 — wall_fade: positive-gamma mean-reversion.

Fires in positive-gamma regime when spot is within `wall_fade_em_threshold`
multiples of the 1-day expected-move band from either wall. Trades a debit
vertical that fades back toward the flip point.
"""
from __future__ import annotations

from typing import Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction

POSITIVE_REGIMES = {"MODERATE_POSITIVE", "HIGH_POSITIVE", "EXTREME_POSITIVE"}


def evaluate(snapshot: GexSnapshot, *, config: JoshuaConfig) -> Optional[SetupAction]:
    if snapshot.regime not in POSITIVE_REGIMES:
        return None
    if snapshot.sigma_1d_band_width <= 0:
        return None

    spot = snapshot.spot
    cw = snapshot.call_wall
    pw = snapshot.put_wall
    sigma = snapshot.sigma_1d_band_width
    thr = config.wall_fade_em_threshold

    near_call = cw > 0 and spot < cw and (cw - spot) / sigma < thr
    near_put = pw > 0 and spot > pw and (spot - pw) / sigma < thr

    if not near_call and not near_put:
        return None

    if near_call and near_put:
        # Prefer the closer wall (fade in its direction)
        d_call = cw - spot
        d_put = spot - pw
        if d_call <= d_put:
            near_put = False
        else:
            near_call = False

    long_strike = float(round(spot))
    if near_call:
        # Fade down — bear put vertical (long ATM put, short ATM-1 put)
        short_strike = long_strike - config.spread_width
        return SetupAction(
            setup=SetupType.WALL_FADE,
            direction="put",
            long_strike=long_strike,
            short_strike=short_strike,
            reason=f"call_wall within {(cw - spot)/sigma:.2f}σ overhead",
        )
    # near_put — fade up — bull call vertical
    short_strike = long_strike + config.spread_width
    return SetupAction(
        setup=SetupType.WALL_FADE,
        direction="call",
        long_strike=long_strike,
        short_strike=short_strike,
        reason=f"put_wall within {(spot - pw)/sigma:.2f}σ below",
    )
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/setups/test_wall_fade.py -v --no-cov`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/setups/wall_fade.py tests/trading/helios/setups/test_wall_fade.py
git commit -m "joshua: setup — wall_fade (positive-gamma mean-reversion)"
```

---

## Task 8: Build `setups/wall_break.py` — negative-gamma momentum

**Files:**
- Create: `trading/helios/setups/wall_break.py`
- Test: `tests/trading/helios/setups/test_wall_break.py`

- [ ] **Step 1: Write failing tests**

Create `tests/trading/helios/setups/test_wall_break.py`:

```python
import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import SetupType, JoshuaConfig
from trading.helios.setups.wall_break import evaluate


def _snap(*, spot=500.0, call_wall=501.0, put_wall=495.0, regime="HIGH_NEGATIVE", sigma=5.0):
    return GexSnapshot(
        symbol="SPY", spot=spot, net_gex=-2.0e9, flip_point=498.0,
        call_wall=call_wall, put_wall=put_wall, vix=22.0, regime=regime,
        sigma_1d_band_width=sigma,
        snapshot_at=dt.datetime.now(dt.timezone.utc),
    )


def test_wall_break_fires_call_when_spot_above_call_wall_by_em_threshold():
    # (502 - 500)/5 = 0.40 > 0.20
    snap = _snap(spot=502.0, call_wall=500.0, sigma=5.0)
    a = evaluate(snap, config=JoshuaConfig())
    assert a is not None
    assert a.setup == SetupType.WALL_BREAK
    assert a.direction == "call"
    assert a.long_strike == 502.0
    assert a.short_strike == 503.0


def test_wall_break_fires_put_when_spot_below_put_wall_by_em_threshold():
    # (500-498)/5 = 0.40 > 0.20
    snap = _snap(spot=498.0, put_wall=500.0, sigma=5.0)
    a = evaluate(snap, config=JoshuaConfig())
    assert a is not None
    assert a.direction == "put"
    assert a.long_strike == 498.0
    assert a.short_strike == 497.0


def test_wall_break_skips_when_break_too_shallow():
    # (500.5-500)/5 = 0.10 < 0.20
    snap = _snap(spot=500.5, call_wall=500.0, sigma=5.0)
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_break_skips_when_regime_positive():
    snap = _snap(spot=502.0, call_wall=500.0, sigma=5.0, regime="HIGH_POSITIVE")
    assert evaluate(snap, config=JoshuaConfig()) is None


def test_wall_break_skips_when_sigma_zero():
    snap = _snap(spot=502.0, call_wall=500.0, sigma=0.0)
    assert evaluate(snap, config=JoshuaConfig()) is None
```

- [ ] **Step 2: Run tests; expect import error**

Run: `pytest tests/trading/helios/setups/test_wall_break.py -v --no-cov`
Expected: `ModuleNotFoundError: No module named 'trading.helios.setups.wall_break'`

- [ ] **Step 3: Implement `wall_break.py`**

Create `trading/helios/setups/wall_break.py`:

```python
"""Setup 2 — wall_break: negative-gamma momentum.

Fires in negative-gamma regime when spot has cleared a wall by ≥
`wall_break_em_threshold` multiples of σ_1d. Dealer hedging in negative
gamma amplifies the break — chase momentum with a debit vertical in the
direction of the break.
"""
from __future__ import annotations

from typing import Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction

NEGATIVE_REGIMES = {"MODERATE_NEGATIVE", "HIGH_NEGATIVE", "EXTREME_NEGATIVE"}


def evaluate(snapshot: GexSnapshot, *, config: JoshuaConfig) -> Optional[SetupAction]:
    if snapshot.regime not in NEGATIVE_REGIMES:
        return None
    if snapshot.sigma_1d_band_width <= 0:
        return None

    spot = snapshot.spot
    cw = snapshot.call_wall
    pw = snapshot.put_wall
    sigma = snapshot.sigma_1d_band_width
    thr = config.wall_break_em_threshold

    broke_call = cw > 0 and spot > cw and (spot - cw) / sigma > thr
    broke_put = pw > 0 and spot < pw and (pw - spot) / sigma > thr

    if not broke_call and not broke_put:
        return None

    long_strike = float(round(spot))
    if broke_call:
        return SetupAction(
            setup=SetupType.WALL_BREAK,
            direction="call",
            long_strike=long_strike,
            short_strike=long_strike + config.spread_width,
            reason=f"spot {(spot - cw)/sigma:.2f}σ above call_wall",
        )
    return SetupAction(
        setup=SetupType.WALL_BREAK,
        direction="put",
        long_strike=long_strike,
        short_strike=long_strike - config.spread_width,
        reason=f"spot {(pw - spot)/sigma:.2f}σ below put_wall",
    )
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/setups/test_wall_break.py -v --no-cov`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/setups/wall_break.py tests/trading/helios/setups/test_wall_break.py
git commit -m "joshua: setup — wall_break (negative-gamma momentum)"
```

---

## Task 9: Build `setups/flip_cross.py` — regime-transition

**Files:**
- Create: `trading/helios/setups/flip_cross.py`
- Test: `tests/trading/helios/setups/test_flip_cross.py`

- [ ] **Step 1: Write failing tests**

Create `tests/trading/helios/setups/test_flip_cross.py`:

```python
import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import SetupType, JoshuaConfig
from trading.helios.setups.flip_cross import evaluate, FlipBuffer


def _snap(*, spot, net_gex, flip=500.0, sigma=5.0, ts=None):
    return GexSnapshot(
        symbol="SPY", spot=spot, net_gex=net_gex, flip_point=flip,
        call_wall=505.0, put_wall=495.0, vix=18.0,
        regime="HIGH_POSITIVE" if net_gex > 0 else "HIGH_NEGATIVE",
        sigma_1d_band_width=sigma,
        snapshot_at=ts or dt.datetime.now(dt.timezone.utc),
    )


def test_flip_cross_fires_call_on_upward_cross_with_regime_flip():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    # 5 min ago: below flip - 0.15%, net_gex negative
    buf.add(_snap(spot=499.0, net_gex=-1.0e9, ts=base))
    # 3 min ago: still below
    buf.add(_snap(spot=499.2, net_gex=-0.5e9, ts=base + dt.timedelta(minutes=2)))
    # Now: above flip + 0.15%, net_gex positive
    now_snap = _snap(spot=501.0, net_gex=1.0e9, ts=base + dt.timedelta(minutes=5))
    a = evaluate(now_snap, buffer=buf, config=JoshuaConfig())
    assert a is not None
    assert a.setup == SetupType.FLIP_CROSS
    assert a.direction == "call"
    assert a.long_strike == 501.0
    assert a.short_strike == 502.0


def test_flip_cross_fires_put_on_downward_cross_with_regime_flip():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=501.0, net_gex=1.0e9, ts=base))
    buf.add(_snap(spot=500.5, net_gex=0.5e9, ts=base + dt.timedelta(minutes=2)))
    now_snap = _snap(spot=499.0, net_gex=-1.0e9, ts=base + dt.timedelta(minutes=5))
    a = evaluate(now_snap, buffer=buf, config=JoshuaConfig())
    assert a is not None
    assert a.direction == "put"


def test_flip_cross_skips_if_no_regime_flip():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=499.0, net_gex=1.0e9, ts=base))  # already positive
    now_snap = _snap(spot=501.0, net_gex=1.5e9, ts=base + dt.timedelta(minutes=5))
    assert evaluate(now_snap, buffer=buf, config=JoshuaConfig()) is None


def test_flip_cross_skips_if_hysteresis_not_breached():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    # 5 min ago at 500.3 (within 0.15% of 500); now at 500.4 (within 0.15%)
    buf.add(_snap(spot=500.3, net_gex=-1.0e9, ts=base))
    now_snap = _snap(spot=500.4, net_gex=1.0e9, ts=base + dt.timedelta(minutes=5))
    assert evaluate(now_snap, buffer=buf, config=JoshuaConfig()) is None


def test_flip_cross_skips_if_buffer_too_short():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    # Only 2 minutes of history — not enough
    buf.add(_snap(spot=499.0, net_gex=-1.0e9, ts=base + dt.timedelta(minutes=3)))
    now_snap = _snap(spot=501.0, net_gex=1.0e9, ts=base + dt.timedelta(minutes=5))
    assert evaluate(now_snap, buffer=buf, config=JoshuaConfig()) is None


def test_flip_buffer_evicts_old_entries():
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    buf.add(_snap(spot=499.0, net_gex=-1.0e9, ts=base))
    buf.add(_snap(spot=499.5, net_gex=-0.5e9, ts=base + dt.timedelta(minutes=10)))  # 10 min later
    # First entry is now older than 5 min from the latest → evicted
    earliest = buf.earliest_within(base + dt.timedelta(minutes=10), minutes=5)
    assert earliest is not None
    assert earliest.spot == 499.5
```

- [ ] **Step 2: Run tests; expect import error**

Run: `pytest tests/trading/helios/setups/test_flip_cross.py -v --no-cov`
Expected: `ModuleNotFoundError: No module named 'trading.helios.setups.flip_cross'`

- [ ] **Step 3: Implement `flip_cross.py`**

Create `trading/helios/setups/flip_cross.py`:

```python
"""Setup 3 — flip_cross: regime-transition directional.

Fires when:
  1. Spot has crossed the flip point through both ±hysteresis bands
  2. net_gex has flipped sign within the 5-min buffer window
The buffer requires ≥ flip_buffer_minutes of history; otherwise we abstain.
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from typing import Deque, Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction


class FlipBuffer:
    """5-minute rolling buffer of GexSnapshots, indexed by snapshot_at."""

    def __init__(self, max_minutes: int = 5):
        self._snaps: Deque[GexSnapshot] = deque()
        self.max_minutes = max_minutes

    def add(self, snap: GexSnapshot) -> None:
        self._snaps.append(snap)
        # Trim entries older than max_minutes from the latest
        latest = snap.snapshot_at
        cutoff = latest - dt.timedelta(minutes=self.max_minutes)
        while self._snaps and self._snaps[0].snapshot_at < cutoff:
            self._snaps.popleft()

    def earliest_within(self, now: dt.datetime, *, minutes: int) -> Optional[GexSnapshot]:
        cutoff = now - dt.timedelta(minutes=minutes)
        for s in self._snaps:
            if s.snapshot_at >= cutoff:
                return s
        return None

    def has_buffer(self, now: dt.datetime, *, minutes: int) -> bool:
        earliest = self.earliest_within(now, minutes=minutes)
        if earliest is None:
            return False
        return (now - earliest.snapshot_at).total_seconds() >= (minutes - 1) * 60


def evaluate(snapshot: GexSnapshot, *, buffer: FlipBuffer, config: JoshuaConfig) -> Optional[SetupAction]:
    now = snapshot.snapshot_at
    if not buffer.has_buffer(now, minutes=config.flip_buffer_minutes):
        return None

    past = buffer.earliest_within(now, minutes=config.flip_buffer_minutes)
    if past is None:
        return None

    flip = snapshot.flip_point
    hyst = flip * config.flip_hysteresis_pct
    upper = flip + hyst
    lower = flip - hyst

    crossed_up = past.spot < lower and snapshot.spot > upper
    crossed_down = past.spot > upper and snapshot.spot < lower
    if not crossed_up and not crossed_down:
        return None

    regime_flip_to_pos = past.net_gex < 0 and snapshot.net_gex > 0
    regime_flip_to_neg = past.net_gex > 0 and snapshot.net_gex < 0

    long_strike = float(round(snapshot.spot))
    if crossed_up and regime_flip_to_pos:
        return SetupAction(
            setup=SetupType.FLIP_CROSS,
            direction="call",
            long_strike=long_strike,
            short_strike=long_strike + config.spread_width,
            reason="upward flip cross with net_gex sign-flip",
        )
    if crossed_down and regime_flip_to_neg:
        return SetupAction(
            setup=SetupType.FLIP_CROSS,
            direction="put",
            long_strike=long_strike,
            short_strike=long_strike - config.spread_width,
            reason="downward flip cross with net_gex sign-flip",
        )
    return None
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/setups/test_flip_cross.py -v --no-cov`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/setups/flip_cross.py tests/trading/helios/setups/test_flip_cross.py
git commit -m "joshua: setup — flip_cross (regime-transition with 5-min buffer)"
```

---

## Task 10: Replace `signals.py` — setup-stack dispatcher

**Files:**
- Modify (replace contents): `trading/helios/signals.py`
- Create: `tests/trading/helios/test_signals_dispatch.py`
- Delete: `tests/trading/helios/test_signals.py` (uses removed quant.gex_walls dependency)

- [ ] **Step 1: Write failing tests**

Create `tests/trading/helios/test_signals_dispatch.py`:

```python
"""Dispatcher tests: flip_cross > wall_break > wall_fade ordering."""
import datetime as dt

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import DailyState, SetupType, JoshuaConfig
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch


def _snap(**kw):
    defaults = dict(
        symbol="SPY", spot=500.0, net_gex=2.0e9, flip_point=499.0,
        call_wall=501.0, put_wall=495.0, vix=18.0, regime="HIGH_POSITIVE",
        sigma_1d_band_width=5.0,
        snapshot_at=dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc),
    )
    defaults.update(kw)
    return GexSnapshot(**defaults)


def test_dispatch_returns_none_when_no_setup_qualifies():
    snap = _snap(spot=500.0, call_wall=520.0, put_wall=480.0, regime="NEUTRAL")
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    buf = FlipBuffer()
    action = dispatch(snap, state=state, buffer=buf, config=JoshuaConfig())
    assert action is None


def test_dispatch_skips_setups_already_fired_today():
    # wall_fade would qualify, but state says it's already fired
    snap = _snap(spot=500.0, call_wall=501.0, regime="HIGH_POSITIVE", sigma_1d_band_width=5.0)
    state = DailyState(trade_date=dt.date(2026, 5, 11), wall_fade_fired=True)
    buf = FlipBuffer()
    action = dispatch(snap, state=state, buffer=buf, config=JoshuaConfig())
    assert action is None


def test_dispatch_prefers_flip_cross_when_multiple_qualify():
    # Construct a situation where both flip_cross and wall_fade would fire
    buf = FlipBuffer(max_minutes=5)
    base = dt.datetime(2026, 5, 11, 14, 0, tzinfo=dt.timezone.utc)
    past = _snap(spot=499.0, net_gex=-1.0e9, regime="HIGH_NEGATIVE",
                 flip_point=500.0, call_wall=501.0, sigma_1d_band_width=5.0,
                 snapshot_at=base)
    buf.add(past)
    now_snap = _snap(spot=501.0, net_gex=1.0e9, regime="HIGH_POSITIVE",
                     flip_point=500.0, call_wall=502.0, sigma_1d_band_width=5.0,
                     snapshot_at=base + dt.timedelta(minutes=5))
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    action = dispatch(now_snap, state=state, buffer=buf, config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.FLIP_CROSS


def test_dispatch_wall_fade_when_only_qualifier():
    snap = _snap(spot=500.0, call_wall=501.0, regime="HIGH_POSITIVE", sigma_1d_band_width=5.0)
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    action = dispatch(snap, state=state, buffer=FlipBuffer(), config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.WALL_FADE


def test_dispatch_wall_break_when_only_qualifier():
    snap = _snap(spot=502.0, call_wall=500.0, regime="HIGH_NEGATIVE", sigma_1d_band_width=5.0)
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    action = dispatch(snap, state=state, buffer=FlipBuffer(), config=JoshuaConfig())
    assert action is not None
    assert action.setup == SetupType.WALL_BREAK
```

- [ ] **Step 2: Delete the obsolete signals test**

Run: `git rm tests/trading/helios/test_signals.py`
Expected: file removed from index.

- [ ] **Step 3: Run new test; expect pre-rewrite failure**

Run: `pytest tests/trading/helios/test_signals_dispatch.py -v --no-cov`
Expected: `ImportError: cannot import name 'dispatch' from 'trading.helios.signals'`

- [ ] **Step 4: Rewrite `trading/helios/signals.py`**

Replace contents:

```python
"""JOSHUA setup-stack dispatcher.

Pure function. No I/O.

Order of dispatch:
  1. flip_cross — regime transition is highest-conviction
  2. wall_break — negative-gamma momentum
  3. wall_fade  — positive-gamma mean-reversion

A setup is skipped if it's already fired today (per DailyState). The
first unfired qualifying setup wins.
"""
from __future__ import annotations

from typing import Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import DailyState, JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction
from trading.helios.setups import wall_fade, wall_break, flip_cross


def dispatch(
    snapshot: GexSnapshot,
    *,
    state: DailyState,
    buffer: "flip_cross.FlipBuffer",
    config: JoshuaConfig,
) -> Optional[SetupAction]:
    if not state.is_fired(SetupType.FLIP_CROSS):
        action = flip_cross.evaluate(snapshot, buffer=buffer, config=config)
        if action is not None:
            return action

    if not state.is_fired(SetupType.WALL_BREAK):
        action = wall_break.evaluate(snapshot, config=config)
        if action is not None:
            return action

    if not state.is_fired(SetupType.WALL_FADE):
        action = wall_fade.evaluate(snapshot, config=config)
        if action is not None:
            return action

    return None
```

- [ ] **Step 5: Run tests; expect pass**

Run: `pytest tests/trading/helios/test_signals_dispatch.py -v --no-cov`
Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add trading/helios/signals.py tests/trading/helios/test_signals_dispatch.py tests/trading/helios/test_signals.py
git commit -m "joshua: signals — replace with setup-stack dispatcher"
```

---

## Task 11: Replace `strategy.py` — exit decision tree

**Files:**
- Modify (replace contents): `trading/helios/strategy.py`
- Modify (replace contents): `tests/trading/helios/test_strategy.py`

- [ ] **Step 1: Replace `tests/trading/helios/test_strategy.py`**

```python
"""Tests for JOSHUA exit decision tree.

Triggers (first-match):
  1. pnl_pct >= profit_target_pct → PT
  2. pnl_pct <= -stop_loss_pct → SL
  3. now_ct >= eod_time_ct → TIME_STOP
  4. quotes_unavailable_streak >= max → DATA_FAILURE
"""
import datetime as dt
import pytest

from trading.helios.models import JoshuaConfig, ExitReason
from trading.helios.strategy import decide_exit, ExitDecision


def _now(h, m):
    return dt.datetime(2026, 5, 11, h, m)


def test_pt_hit():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.20, now_ct=_now(10, 0), quotes_unavail_streak=0, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.PT


def test_sl_hit():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=0.70, now_ct=_now(10, 0), quotes_unavail_streak=0, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.SL


def test_time_stop_at_15_55_ct():
    cfg = JoshuaConfig()  # eod_time_ct=15:55
    d = decide_exit(debit=1.00, mark_to_close=1.05, now_ct=_now(15, 55), quotes_unavail_streak=0, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.TIME_STOP


def test_time_stop_not_yet_before_15_55():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.05, now_ct=_now(15, 54), quotes_unavail_streak=0, config=cfg)
    assert not d.should_exit


def test_data_failure_after_10_streaks():
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.05, now_ct=_now(10, 0), quotes_unavail_streak=10, config=cfg)
    assert d.should_exit
    assert d.reason == ExitReason.DATA_FAILURE


def test_pt_takes_precedence_over_sl():
    # Impossible in practice but tests ordering
    cfg = JoshuaConfig()
    d = decide_exit(debit=1.00, mark_to_close=1.20, now_ct=_now(15, 55), quotes_unavail_streak=0, config=cfg)
    assert d.reason == ExitReason.PT  # PT fires before TIME_STOP


def test_no_trailing_stop_field_in_decision():
    # The decision has no TRAIL reason
    assert "TRAIL" not in {r.value for r in ExitReason}
```

- [ ] **Step 2: Run; expect import errors / failures**

Run: `pytest tests/trading/helios/test_strategy.py -v --no-cov`
Expected: existing tests for HeliosConfig / decide_exit signature fail.

- [ ] **Step 3: Replace `trading/helios/strategy.py`**

```python
"""JOSHUA exit decision tree. Pure function. No I/O.

Order of precedence at every check:
  1. PT (always armed)
  2. SL (always armed — no grace period; 1DTE noise is the noise)
  3. TIME_STOP (now_ct >= eod_time_ct)
  4. DATA_FAILURE (quotes_unavail_streak >= max)

No trailing stop. Phase 2 showed it killed winners on 1DTE.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from trading.helios.models import ExitReason, JoshuaConfig


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: Optional[ExitReason] = None


def decide_exit(
    *,
    debit: float,
    mark_to_close: float,
    now_ct: dt.datetime,
    quotes_unavail_streak: int,
    config: JoshuaConfig,
) -> ExitDecision:
    pnl_pct = (mark_to_close / debit - 1.0) * 100.0

    if pnl_pct >= config.profit_target_pct:
        return ExitDecision(True, ExitReason.PT)

    if pnl_pct <= -config.stop_loss_pct:
        return ExitDecision(True, ExitReason.SL)

    eod_h, eod_m = (int(x) for x in config.eod_time_ct.split(":"))
    if now_ct.hour > eod_h or (now_ct.hour == eod_h and now_ct.minute >= eod_m):
        return ExitDecision(True, ExitReason.TIME_STOP)

    if quotes_unavail_streak >= config.quotes_unavailable_max_cycles:
        return ExitDecision(True, ExitReason.DATA_FAILURE)

    return ExitDecision(False, None)
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/trading/helios/test_strategy.py -v --no-cov`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add trading/helios/strategy.py tests/trading/helios/test_strategy.py
git commit -m "joshua: strategy — replace exit tree (PT/SL/TIME_STOP/DATA_FAILURE)"
```

---

## Task 12: Rewire `monitor.py` to use new `decide_exit`

**Files:**
- Modify: `trading/helios/monitor.py`

- [ ] **Step 1: Read current monitor to find HeliosConfig + ExitReason references**

Run: `grep -n "HeliosConfig\|HeliosTradeSignal\|stop_loss_grace_minutes\|EOD\|ExitReason" trading/helios/monitor.py`
Note the lines that need updating.

- [ ] **Step 2: Update import + cycle logic**

Replace the top imports in `trading/helios/monitor.py`:

```python
from __future__ import annotations

import datetime as dt
import logging
import time
from typing import Optional

from trading.helios.db import HeliosDatabase
from trading.helios.executor import close_paper
from trading.helios.models import JoshuaConfig, ExitReason
from trading.helios.strategy import decide_exit
```

In the `HeliosMonitor` class, replace the constructor's `config: HeliosConfig` annotation with `config: JoshuaConfig`. In `run_one_cycle`, replace any usage of `stop_loss_grace_minutes` or `minutes_since_entry` with the new signature:

```python
        decision = decide_exit(
            debit=float(pos["debit"]),
            mark_to_close=mark_to_close,
            now_ct=now_ct,
            quotes_unavail_streak=self._streak,
            config=self.config,
        )
```

Add `self._streak: int = 0` to `__init__` and bump/reset it on quote-fetch failure/success.

- [ ] **Step 3: Run unit tests; expect pass for db/executor; monitor may not have unit tests yet — that's OK**

Run: `pytest tests/trading/helios/ -v --no-cov -k "not signals"`
Expected: all non-signals tests pass (models, executor, strategy, db, gex_client, setups). `test_signals.py` is removed; `test_signals_dispatch.py` already passes.

- [ ] **Step 4: Smoke-test monitor instantiation**

Run: `python -c "from trading.helios.monitor import HeliosMonitor; print('import OK')"`
Expected: `import OK`

- [ ] **Step 5: Commit**

```bash
git add trading/helios/monitor.py
git commit -m "joshua: monitor — wire to new decide_exit signature, drop grace period"
```

---

## Task 13: Rewire `trader.py` to use gex_client + setup dispatcher

**Files:**
- Modify: `trading/helios/trader.py`

- [ ] **Step 1: Rewrite `run_cycle` to use the new signal stack**

Replace the body of `trading/helios/trader.py` with:

```python
"""JOSHUA entry-cycle orchestrator.

Runs every 60 seconds during market hours. Pulls a GexSnapshot from
gex_client, runs the setup-stack dispatcher, and opens a paper position
if a setup fires. Not pure — talks to /api/gex/SPY, Tradier (for chain),
and Postgres.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
from typing import Optional

from trading.helios.db import HeliosDatabase
from trading.helios.executor import open_paper
from trading.helios.gex_client import GexClient, GexStaleError, GexSnapshot
from trading.helios.models import JoshuaConfig, SetupType, SpreadType
from trading.helios.setups.base import SetupAction
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch

logger = logging.getLogger(__name__)


class HeliosTrader:
    """Entry-cycle orchestrator. One instance per worker process."""

    def __init__(
        self,
        db: HeliosDatabase,
        tradier,                # for chain mid lookup
        config: JoshuaConfig,
        gex_client: Optional[GexClient] = None,
    ):
        self.db = db
        self.tradier = tradier
        self.config = config
        self.gex_client = gex_client or GexClient(
            base_url=os.environ.get("ALPHAGEX_API_BASE", "http://localhost:8000"),
            stale_max_seconds=config.gex_stale_max_seconds,
        )
        self._flip_buffer = FlipBuffer(max_minutes=config.flip_buffer_minutes)

    def run_cycle(self) -> None:
        now_ct = self._now_ct()
        if not self._is_market_hours(now_ct):
            return

        try:
            snapshot = self.gex_client.get_spy()
        except GexStaleError as e:
            logger.info("HELIOS: gex stale (%s) — skip", e)
            self.db.insert_scan_activity(outcome="SKIP", detail=f"gex_stale:{e}")
            return
        except Exception as e:
            logger.warning("HELIOS: gex fetch failed: %s", e)
            self.db.insert_scan_activity(outcome="ERROR", detail=f"gex_fetch:{e}")
            return

        self._flip_buffer.add(snapshot)

        trade_date = now_ct.date()
        state = self.db.load_daily_state(trade_date)

        action = dispatch(
            snapshot,
            state=state,
            buffer=self._flip_buffer,
            config=self.config,
        )

        if action is None:
            self.db.insert_scan_activity(outcome="NO_TRADE", detail=f"regime={snapshot.regime}")
            return

        if self.db.get_open_position() is not None:
            self.db.insert_scan_activity(outcome="SKIP", detail="position_already_open")
            return

        self._open(action, snapshot, now_ct)

    def _open(self, action: SetupAction, snap: GexSnapshot, now_ct: dt.datetime) -> None:
        expiration_date = self._next_trading_day(now_ct.date())
        try:
            long_sym, long_mid, short_sym, short_mid = self._pull_vertical_mids(
                long_strike=action.long_strike,
                short_strike=action.short_strike,
                expiration=expiration_date,
                is_call=(action.direction == "call"),
            )
        except Exception as e:
            logger.warning("HELIOS: chain fetch failed: %s", e)
            self.db.insert_scan_activity(outcome="ERROR", detail=f"chain:{e}")
            return

        spread_type = SpreadType.BULL_CALL if action.direction == "call" else SpreadType.BEAR_PUT
        opened = open_paper(
            db=self.db,
            spread_type=spread_type,
            long_symbol=long_sym,
            short_symbol=short_sym,
            long_strike=action.long_strike,
            short_strike=action.short_strike,
            long_mid=long_mid,
            short_mid=short_mid,
            expiration_date=expiration_date,
            config=self._executor_config(),
        )
        if opened is None:
            self.db.insert_scan_activity(outcome="SKIP", detail="open_paper:invalid")
            return

        self.db.upsert_daily_state(
            now_ct.date(),
            fired=action.setup,
            signal_minute=_minutes_since_open(now_ct),
        )
        self.db.insert_scan_activity(outcome="TRADE", detail=f"{action.setup.value}:{action.direction}")

    def _executor_config(self):
        # Bridge to executor's per-trade risk dollars based on current balance
        balance = max(self.db.get_starting_capital() + self.db.get_realized_pnl(), 0.0)
        risk = balance * self.config.risk_per_trade_pct * self.config.buying_power_usage_pct
        from trading.helios.models import HeliosConfig  # legacy executor wants this
        return HeliosConfig(
            ticker=self.config.ticker,
            spread_width=self.config.spread_width,
            risk_per_trade=max(risk, 0.0),
            profit_target_pct=self.config.profit_target_pct,
            stop_loss_pct=self.config.stop_loss_pct,
        )

    def _pull_vertical_mids(self, *, long_strike, short_strike, expiration, is_call):
        chain = self.tradier.get_option_chain(self.config.ticker, expiration)
        side = "call" if is_call else "put"
        long_q = _find_strike(chain, long_strike, side)
        short_q = _find_strike(chain, short_strike, side)
        return (
            long_q["symbol"],
            (float(long_q["bid"]) + float(long_q["ask"])) / 2.0,
            short_q["symbol"],
            (float(short_q["bid"]) + float(short_q["ask"])) / 2.0,
        )

    def _next_trading_day(self, today: dt.date) -> dt.date:
        d = today + dt.timedelta(days=1)
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        return d

    def _now_ct(self) -> dt.datetime:
        return dt.datetime.utcnow() - dt.timedelta(hours=5)

    def _is_market_hours(self, now_ct: dt.datetime) -> bool:
        if now_ct.weekday() >= 5:
            return False
        if now_ct.hour < 8 or (now_ct.hour == 8 and now_ct.minute < 30):
            return False
        if now_ct.hour > 15:
            return False
        if now_ct.hour == 15 and now_ct.minute >= 55:
            return False
        return True


def _find_strike(chain, strike, side):
    for q in chain:
        if abs(float(q["strike"]) - strike) < 1e-3 and str(q.get("option_type", "")).lower() == side:
            return q
    raise KeyError(f"strike {strike} {side} not in chain")


def _minutes_since_open(now_ct: dt.datetime) -> int:
    open_time = now_ct.replace(hour=8, minute=30, second=0, microsecond=0)
    return max(int((now_ct - open_time).total_seconds() // 60), 0)
```

- [ ] **Step 2: Smoke-test import**

Run: `python -c "from trading.helios.trader import HeliosTrader; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add trading/helios/trader.py
git commit -m "joshua: trader — rewire run_cycle to gex_client + setup dispatcher"
```

---

## Task 14: Build replay-data loader (`backtest/joshua_replay/data.py`)

**Files:**
- Create: `backtest/joshua_replay/__init__.py`, `data.py`
- Test: `tests/backtest/joshua_replay/__init__.py`, `test_data.py`

The replay reads `watchtower_snapshots` for top-level fields and joins `argus_strikes` to reconstruct call_wall, put_wall, flip_point. The regime field in watchtower_snapshots is 3-level (POSITIVE/NEGATIVE/NEUTRAL); we map to the 7-level scheme that the production endpoint emits by binning `total_net_gamma`.

- [ ] **Step 1: Write failing test (DB-gated)**

Create `tests/backtest/joshua_replay/__init__.py` (empty) and `tests/backtest/joshua_replay/test_data.py`:

```python
"""Replay loader tests — DB-gated."""
import datetime as dt
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping DB-backed test",
)

from backtest.joshua_replay.data import load_snapshots, regime_from_net_gex


def test_regime_from_net_gex_thresholds():
    assert regime_from_net_gex(-4e9) == "EXTREME_NEGATIVE"
    assert regime_from_net_gex(-2.5e9) == "HIGH_NEGATIVE"
    assert regime_from_net_gex(-1.5e9) == "MODERATE_NEGATIVE"
    assert regime_from_net_gex(0.0) == "NEUTRAL"
    assert regime_from_net_gex(1.5e9) == "MODERATE_POSITIVE"
    assert regime_from_net_gex(2.5e9) == "HIGH_POSITIVE"
    assert regime_from_net_gex(4e9) == "EXTREME_POSITIVE"


def test_load_snapshots_one_day_returns_rows():
    # Pick a known-populated day — most recent trading day with watchtower data
    snaps = load_snapshots(dt.date(2026, 5, 1), dt.date(2026, 5, 1), symbol="SPY")
    if not snaps:
        pytest.skip("no watchtower data for 2026-05-01")
    s = snaps[0]
    assert s.symbol == "SPY"
    assert s.spot > 0
    assert s.flip_point > 0  # derived
    assert s.call_wall >= s.spot or s.call_wall == 0
    assert s.put_wall <= s.spot or s.put_wall == 0
```

- [ ] **Step 2: Run; expect skip or module-missing**

Run: `pytest tests/backtest/joshua_replay/test_data.py -v --no-cov`
Expected: SKIPPED or `ModuleNotFoundError: backtest.joshua_replay`

- [ ] **Step 3: Implement loader**

Create `backtest/joshua_replay/__init__.py` (empty).

Create `backtest/joshua_replay/data.py`:

```python
"""Replay data loader.

Reads watchtower_snapshots + argus_strikes for a date range and reconstructs
the same shape that /api/gex/SPY returns (GexSnapshot).

Walls and flip point are derived from per-strike gamma:
  - call_wall = strike argmax of call_gamma * OI (proxy: call_gamma alone)
  - put_wall  = strike argmin of put_gamma  * OI (largest negative)
  - flip_point = strike where cumulative net_gamma crosses zero
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
from dataclasses import dataclass
from typing import List, Optional

import psycopg2
import psycopg2.extras

from trading.helios.gex_client import GexSnapshot

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252.0


def regime_from_net_gex(net_gex: float) -> str:
    if net_gex <= -3e9:
        return "EXTREME_NEGATIVE"
    if net_gex <= -2e9:
        return "HIGH_NEGATIVE"
    if net_gex <= -1e9:
        return "MODERATE_NEGATIVE"
    if net_gex >= 3e9:
        return "EXTREME_POSITIVE"
    if net_gex >= 2e9:
        return "HIGH_POSITIVE"
    if net_gex >= 1e9:
        return "MODERATE_POSITIVE"
    return "NEUTRAL"


def load_snapshots(
    start: dt.date,
    end: dt.date,
    *,
    symbol: str = "SPY",
    db_url: Optional[str] = None,
) -> List[GexSnapshot]:
    """Load snapshots in chronological order. Caller passes a date range."""
    url = db_url or os.environ["DATABASE_URL"]
    with psycopg2.connect(url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                """
                SELECT
                    s.id, s.snapshot_time, s.spot_price, s.expected_move, s.vix,
                    s.total_net_gamma, s.gamma_regime
                FROM watchtower_snapshots s
                WHERE s.symbol = %s
                  AND s.snapshot_time::date BETWEEN %s AND %s
                ORDER BY s.snapshot_time ASC
                """,
                (symbol, start, end),
            )
            snap_rows = c.fetchall()
            if not snap_rows:
                return []

            ids = tuple(r["id"] for r in snap_rows)
            c.execute(
                """
                SELECT snapshot_id, strike, net_gamma, call_gamma, put_gamma
                FROM argus_strikes
                WHERE snapshot_id IN %s
                ORDER BY snapshot_id, strike ASC
                """,
                (ids,),
            )
            strikes_by_snap = {}
            for r in c.fetchall():
                strikes_by_snap.setdefault(r["snapshot_id"], []).append(r)

    out: List[GexSnapshot] = []
    for row in snap_rows:
        strikes = strikes_by_snap.get(row["id"], [])
        if not strikes:
            continue
        cw, pw, flip = _derive_walls_and_flip(strikes, float(row["spot_price"]))
        net_gex = float(row["total_net_gamma"] or 0.0)
        sigma_1d = float(row["expected_move"] or 0.0)
        if sigma_1d == 0 and row["vix"]:
            sigma_1d = float(row["spot_price"]) * (float(row["vix"]) / 100.0) * math.sqrt(1.0 / TRADING_DAYS_PER_YEAR)
        out.append(GexSnapshot(
            symbol=symbol,
            spot=float(row["spot_price"]),
            net_gex=net_gex,
            flip_point=flip,
            call_wall=cw,
            put_wall=pw,
            vix=float(row["vix"] or 0.0),
            regime=regime_from_net_gex(net_gex),
            sigma_1d_band_width=sigma_1d,
            snapshot_at=row["snapshot_time"],
        ))
    return out


def _derive_walls_and_flip(strikes_rows, spot: float):
    """Pick max call_gamma → call_wall above spot; max abs(put_gamma) → put_wall below spot.
    Flip = strike where cumulative net_gamma crosses zero."""
    if not strikes_rows:
        return 0.0, 0.0, spot
    above = [r for r in strikes_rows if float(r["strike"]) > spot]
    below = [r for r in strikes_rows if float(r["strike"]) < spot]
    call_wall = float(max(above, key=lambda r: float(r["call_gamma"] or 0))["strike"]) if above else 0.0
    put_wall = float(max(below, key=lambda r: abs(float(r["put_gamma"] or 0)))["strike"]) if below else 0.0

    cum = 0.0
    flip = float(strikes_rows[0]["strike"])
    prev_sign = None
    for r in strikes_rows:
        ng = float(r["net_gamma"] or 0.0)
        cum += ng
        sign = 1 if cum > 0 else (-1 if cum < 0 else 0)
        if prev_sign is not None and sign != 0 and prev_sign != 0 and sign != prev_sign:
            flip = float(r["strike"])
            break
        if sign != 0:
            prev_sign = sign
    return call_wall, put_wall, flip
```

- [ ] **Step 4: Run; expect pass or skip**

Run: `pytest tests/backtest/joshua_replay/test_data.py -v --no-cov`
Expected: 2 pass / 0 fail (or SKIPPED with no DB URL).

- [ ] **Step 5: Commit**

```bash
git add backtest/joshua_replay/__init__.py backtest/joshua_replay/data.py tests/backtest/joshua_replay/__init__.py tests/backtest/joshua_replay/test_data.py
git commit -m "joshua: replay — snapshot loader + regime/walls/flip derivation"
```

---

## Task 15: Build replay-quote loader (`backtest/joshua_replay/quotes.py`)

**Files:**
- Create: `backtest/joshua_replay/quotes.py`

The replay needs option mids for the 1DTE vertical. Strategy:
1. First try `helios_options_intraday` (table from helios branch with minute-resolution chain bars).
2. Fall back to Black-Scholes synthetic mid via `quant.bs.bs_price` using a flat IV proxy (VIX/100).

- [ ] **Step 1: Implement `quotes.py`**

Create `backtest/joshua_replay/quotes.py`:

```python
"""Replay option-mid loader.

Primary: helios_options_intraday minute bars (if populated for the (date, strike, expiration)).
Fallback: Black-Scholes synthetic mid via quant.bs.bs_price with sigma = vix/100.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import os
from dataclasses import dataclass
from typing import Optional

import psycopg2
import psycopg2.extras

from quant.bs import bs_price

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerticalMids:
    long_mid: float
    short_mid: float
    debit: float


def load_minute_marks(
    *,
    trade_date: dt.date,
    expiration: dt.date,
    long_strike: float,
    short_strike: float,
    is_call: bool,
    db_url: Optional[str] = None,
) -> dict:
    """Return {minutes_since_open: debit} for the day, if available."""
    url = db_url or os.environ["DATABASE_URL"]
    side = "C" if is_call else "P"
    try:
        with psycopg2.connect(url) as conn:
            with conn.cursor() as c:
                c.execute(
                    """
                    SELECT
                        EXTRACT(EPOCH FROM (bar_time - (bar_time::date + INTERVAL '8 hours 30 minutes'))) / 60 AS minute,
                        strike, mid
                    FROM helios_options_intraday
                    WHERE bar_time::date = %s
                      AND expiration_date = %s
                      AND option_type = %s
                      AND strike IN (%s, %s)
                    ORDER BY bar_time ASC, strike ASC
                    """,
                    (trade_date, expiration, side, long_strike, short_strike),
                )
                rows = c.fetchall()
    except psycopg2.errors.UndefinedTable:
        return {}
    if not rows:
        return {}

    by_minute = {}
    for minute, strike, mid in rows:
        bucket = by_minute.setdefault(int(minute), {})
        bucket[float(strike)] = float(mid)
    out = {}
    for minute, mids in by_minute.items():
        if long_strike in mids and short_strike in mids:
            out[minute] = mids[long_strike] - mids[short_strike]
    return out


def synthetic_vertical(
    *,
    spot: float,
    long_strike: float,
    short_strike: float,
    is_call: bool,
    t_years: float,
    sigma: float,
    r: float = 0.05,
) -> VerticalMids:
    long_p = bs_price(spot, long_strike, t_years, sigma, is_call, r)
    short_p = bs_price(spot, short_strike, t_years, sigma, is_call, r)
    debit = long_p - short_p
    return VerticalMids(long_mid=long_p, short_mid=short_p, debit=debit)
```

- [ ] **Step 2: Smoke-import**

Run: `python -c "from backtest.joshua_replay.quotes import synthetic_vertical, load_minute_marks; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backtest/joshua_replay/quotes.py
git commit -m "joshua: replay — option-mid loader (DB primary + BS synthetic fallback)"
```

---

## Task 16: Build replay engine (`backtest/joshua_replay/engine.py`)

**Files:**
- Create: `backtest/joshua_replay/engine.py`
- Test: `tests/backtest/joshua_replay/test_engine.py`

- [ ] **Step 1: Write failing test (DB-independent — uses fixture snapshots)**

Create `tests/backtest/joshua_replay/test_engine.py`:

```python
import datetime as dt
import pytest

from backtest.joshua_replay.engine import replay_day, TradeOutcome
from trading.helios.gex_client import GexSnapshot
from trading.helios.models import JoshuaConfig


def _snap(*, spot, net_gex, regime, sigma, ts, call_wall=505.0, put_wall=495.0, flip=500.0):
    return GexSnapshot(
        symbol="SPY", spot=spot, net_gex=net_gex, flip_point=flip,
        call_wall=call_wall, put_wall=put_wall, vix=18.0, regime=regime,
        sigma_1d_band_width=sigma, snapshot_at=ts,
    )


def test_replay_day_no_qualifying_snaps_returns_no_trades():
    base = dt.datetime(2026, 5, 1, 14, 0, tzinfo=dt.timezone.utc)
    snaps = [
        _snap(spot=500.0, net_gex=0.5e9, regime="NEUTRAL", sigma=5.0,
              ts=base + dt.timedelta(minutes=i)) for i in range(60)
    ]
    out = replay_day(snaps, config=JoshuaConfig(), spot_mark_provider=lambda *a, **kw: 1.0)
    assert out == []


def test_replay_day_fires_wall_fade_once():
    base = dt.datetime(2026, 5, 1, 14, 0, tzinfo=dt.timezone.utc)
    # All minutes have spot near call_wall in positive regime → fires once at first minute
    snaps = [
        _snap(spot=500.0, net_gex=2.0e9, regime="HIGH_POSITIVE", sigma=5.0, call_wall=501.0,
              ts=base + dt.timedelta(minutes=i)) for i in range(60)
    ]
    out = replay_day(snaps, config=JoshuaConfig(),
                      spot_mark_provider=lambda **kw: 0.80)  # debit pinned → 20% PT hit
    assert len(out) == 1
    assert out[0].setup == "wall_fade"
    assert out[0].direction == "put"
```

- [ ] **Step 2: Run; expect import error**

Run: `pytest tests/backtest/joshua_replay/test_engine.py -v --no-cov`
Expected: `ModuleNotFoundError: backtest.joshua_replay.engine`

- [ ] **Step 3: Implement engine**

Create `backtest/joshua_replay/engine.py`:

```python
"""Replay engine — drives a list of snapshots through the setup-stack
dispatcher and simulates each fire to PT/SL/TIME_STOP.

Uses minimal per-day state — DailyState reset each day. FlipBuffer scoped
per day too (5-min buffer doesn't span days).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from typing import Callable, List, Optional

from trading.helios.gex_client import GexSnapshot
from trading.helios.models import DailyState, JoshuaConfig, SetupType
from trading.helios.setups.base import SetupAction
from trading.helios.setups.flip_cross import FlipBuffer
from trading.helios.signals import dispatch
from quant.sim import simulate_intraday, MarkSeries


@dataclass(frozen=True)
class TradeOutcome:
    trade_date: dt.date
    setup: str
    direction: str
    entry_minute: int
    exit_minute: int
    debit: float
    exit_reason: str
    realized_pct: float


SpotMarkProvider = Callable[..., float]


def replay_day(
    snapshots: List[GexSnapshot],
    *,
    config: JoshuaConfig,
    spot_mark_provider: SpotMarkProvider,
    debit_estimator: Optional[Callable[[GexSnapshot, SetupAction], float]] = None,
) -> List[TradeOutcome]:
    """Replay one trading day.

    `spot_mark_provider(snapshot=..., action=..., minute=..., entry_minute=...)`
    returns a $-priced mark for the vertical at that minute. The simplest provider
    can be a closure over a precomputed minute→debit dict from quotes.load_minute_marks.

    `debit_estimator(snapshot, action)` returns the entry debit. If None, uses a flat
    $0.50 placeholder — replace with synthetic BS in `cli.py`.
    """
    if not snapshots:
        return []

    trade_date = snapshots[0].snapshot_at.date()
    state = DailyState(trade_date=trade_date)
    buffer = FlipBuffer(max_minutes=config.flip_buffer_minutes)
    outcomes: List[TradeOutcome] = []
    eod_h, eod_m = (int(x) for x in config.eod_time_ct.split(":"))
    eod_minute = (eod_h - 8) * 60 + (eod_m - 30)  # minutes since 8:30 CT open

    for snap in snapshots:
        buffer.add(snap)
        entry_minute = _minutes_since_open_ct(snap.snapshot_at)
        if entry_minute >= eod_minute:
            break
        action = dispatch(snap, state=state, buffer=buffer, config=config)
        if action is None:
            continue

        debit = debit_estimator(snap, action) if debit_estimator else 0.50
        if debit <= 0:
            continue

        marks = {}
        for future_snap in snapshots:
            m = _minutes_since_open_ct(future_snap.snapshot_at)
            if m < entry_minute:
                continue
            if m > eod_minute:
                break
            marks[m] = spot_mark_provider(
                snapshot=future_snap, action=action, minute=m, entry_minute=entry_minute, debit=debit,
            )
        if entry_minute not in marks:
            marks[entry_minute] = debit

        ms = MarkSeries(marks)
        sim = simulate_intraday(
            debit=debit,
            entry_minute=entry_minute,
            eod_minute=eod_minute,
            bars=ms,
            pt_pct=config.profit_target_pct,
            sl_pct=config.stop_loss_pct,
        )
        outcomes.append(TradeOutcome(
            trade_date=trade_date,
            setup=action.setup.value,
            direction=action.direction,
            entry_minute=entry_minute,
            exit_minute=sim.exit_minute,
            debit=debit,
            exit_reason=sim.exit_reason,
            realized_pct=sim.realized_pct,
        ))
        # lock the setup
        state = _mark_fired(state, action.setup)

    return outcomes


def _minutes_since_open_ct(ts: dt.datetime) -> int:
    # Convert UTC → CT (approximate: UTC - 5)
    ct = ts - dt.timedelta(hours=5)
    open_t = ct.replace(hour=8, minute=30, second=0, microsecond=0)
    return max(int((ct - open_t).total_seconds() // 60), 0)


def _mark_fired(state: DailyState, setup: SetupType) -> DailyState:
    return DailyState(
        trade_date=state.trade_date,
        wall_fade_fired=state.wall_fade_fired or setup == SetupType.WALL_FADE,
        wall_break_fired=state.wall_break_fired or setup == SetupType.WALL_BREAK,
        flip_cross_fired=state.flip_cross_fired or setup == SetupType.FLIP_CROSS,
        last_signal_minute=state.last_signal_minute,
    )
```

- [ ] **Step 4: Run tests; expect pass**

Run: `pytest tests/backtest/joshua_replay/test_engine.py -v --no-cov`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backtest/joshua_replay/engine.py tests/backtest/joshua_replay/test_engine.py
git commit -m "joshua: replay — engine with FlipBuffer + simulate_intraday integration"
```

---

## Task 17: Build replay report (`backtest/joshua_replay/report.py`)

**Files:**
- Create: `backtest/joshua_replay/report.py`
- Test: `tests/backtest/joshua_replay/test_report.py`

- [ ] **Step 1: Write failing test**

Create `tests/backtest/joshua_replay/test_report.py`:

```python
import datetime as dt

from backtest.joshua_replay.engine import TradeOutcome
from backtest.joshua_replay.report import build_report


def _t(date, setup, direction, debit, pct, reason):
    return TradeOutcome(
        trade_date=date, setup=setup, direction=direction,
        entry_minute=60, exit_minute=120, debit=debit,
        exit_reason=reason, realized_pct=pct,
    )


def test_report_aggregates_per_setup_metrics():
    trades = [
        _t(dt.date(2026, 5, 1), "wall_fade", "put", 0.50, 20.0, "PT"),
        _t(dt.date(2026, 5, 1), "wall_fade", "put", 0.50, -30.0, "SL"),
        _t(dt.date(2026, 5, 2), "wall_fade", "call", 0.50, 20.0, "PT"),
        _t(dt.date(2026, 5, 3), "wall_break", "call", 0.40, 20.0, "PT"),
    ]
    report = build_report(trades, start=dt.date(2026, 5, 1), end=dt.date(2026, 5, 3))
    assert "JOSHUA Replay Report" in report
    assert "wall_fade" in report
    assert "wall_break" in report
    # 4 trades, 3 wins → 75%
    assert "75.0%" in report or "75%" in report
```

- [ ] **Step 2: Run; expect import error**

Run: `pytest tests/backtest/joshua_replay/test_report.py -v --no-cov`
Expected: `ModuleNotFoundError: backtest.joshua_replay.report`

- [ ] **Step 3: Implement report**

Create `backtest/joshua_replay/report.py`:

```python
"""Replay report — markdown summary per-setup + overall."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import List

from backtest.joshua_replay.engine import TradeOutcome


def build_report(trades: List[TradeOutcome], *, start: dt.date, end: dt.date) -> str:
    lines = [
        "# JOSHUA Replay Report",
        "",
        f"**Window**: {start} → {end}",
        f"**Total trades**: {len(trades)}",
        "",
    ]
    if not trades:
        lines.append("**No trades fired.**")
        return "\n".join(lines)

    overall_wr = _wr(trades)
    overall_ev = _ev_per_trade(trades)
    lines.extend([
        f"**Overall WR**: {overall_wr:.1f}%",
        f"**Overall EV/trade**: ${overall_ev:.2f}",
        "",
        "## Per-setup breakdown",
        "",
        "| Setup | Trades | WR | PT% | SL% | TIME_STOP% | EV/trade ($) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    by_setup = defaultdict(list)
    for t in trades:
        by_setup[t.setup].append(t)
    for setup in sorted(by_setup):
        ts = by_setup[setup]
        wr = _wr(ts)
        ev = _ev_per_trade(ts)
        pt = 100.0 * sum(1 for t in ts if t.exit_reason == "PT") / len(ts)
        sl = 100.0 * sum(1 for t in ts if t.exit_reason == "SL") / len(ts)
        time_stop = 100.0 * sum(1 for t in ts if t.exit_reason in ("EOD", "TIME_STOP")) / len(ts)
        lines.append(
            f"| {setup} | {len(ts)} | {wr:.1f}% | {pt:.1f}% | {sl:.1f}% | {time_stop:.1f}% | {ev:.2f} |"
        )
    lines.append("")
    lines.append("## GO/NO-GO check")
    lines.append("")
    bar_n = len(trades) >= 30
    bar_wr = overall_wr >= 55.0
    bar_ev = overall_ev >= 3.0
    bar_diversification = len(by_setup) >= 2
    lines.append(f"- n ≥ 30 trades: {'✅' if bar_n else '❌'} ({len(trades)})")
    lines.append(f"- WR ≥ 55%: {'✅' if bar_wr else '❌'} ({overall_wr:.1f}%)")
    lines.append(f"- EV ≥ +$3/trade: {'✅' if bar_ev else '❌'} (${overall_ev:.2f})")
    lines.append(f"- 2+ setups firing: {'✅' if bar_diversification else '❌'} ({len(by_setup)})")
    verdict = "GO" if all([bar_n, bar_wr, bar_ev, bar_diversification]) else "NO-GO"
    lines.append("")
    lines.append(f"**Verdict: {verdict}**")
    return "\n".join(lines)


def _wr(trades: List[TradeOutcome]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.realized_pct > 0)
    return 100.0 * wins / len(trades)


def _ev_per_trade(trades: List[TradeOutcome]) -> float:
    if not trades:
        return 0.0
    # PnL per trade in $: realized_pct × debit_dollars (debit is per-share; contracts assumed 1 for simplicity)
    pnls = [(t.realized_pct / 100.0) * t.debit * 100.0 for t in trades]
    return sum(pnls) / len(pnls)
```

- [ ] **Step 4: Run; expect pass**

Run: `pytest tests/backtest/joshua_replay/test_report.py -v --no-cov`
Expected: 1 test passes.

- [ ] **Step 5: Commit**

```bash
git add backtest/joshua_replay/report.py tests/backtest/joshua_replay/test_report.py
git commit -m "joshua: replay — markdown report with per-setup metrics + GO/NO-GO"
```

---

## Task 18: Build replay CLI (`backtest/joshua_replay/cli.py`)

**Files:**
- Create: `backtest/joshua_replay/cli.py`

- [ ] **Step 1: Implement CLI**

Create `backtest/joshua_replay/cli.py`:

```python
"""JOSHUA replay CLI.

Usage:
    python -m backtest.joshua_replay --start 2026-02-09 --end 2026-05-11

Writes:
    docs/superpowers/reports/2026-05-11-joshua-replay.md
    backtest/joshua_replay/output/trades.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import logging
import math
import os
import pathlib
from collections import defaultdict
from typing import Optional

from backtest.joshua_replay.data import load_snapshots
from backtest.joshua_replay.engine import replay_day, TradeOutcome
from backtest.joshua_replay.quotes import load_minute_marks, synthetic_vertical
from backtest.joshua_replay.report import build_report
from trading.helios.models import JoshuaConfig
from trading.helios.setups.base import SetupAction
from trading.helios.gex_client import GexSnapshot
from quant.bs import bs_price

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("joshua_replay")


def _t_years_to_expiration(snap_ct: dt.datetime, expiration: dt.date) -> float:
    open_next = dt.datetime.combine(expiration, dt.time(15, 0))  # 3pm CT close
    delta_sec = (open_next - snap_ct).total_seconds()
    return max(delta_sec / (365.0 * 86400.0), 1e-6)


def _next_trading_day(d: dt.date) -> dt.date:
    nd = d + dt.timedelta(days=1)
    while nd.weekday() >= 5:
        nd += dt.timedelta(days=1)
    return nd


def _build_debit_estimator():
    def estimator(snap: GexSnapshot, action: SetupAction) -> float:
        sigma = max(snap.vix / 100.0, 0.05)
        expiration = _next_trading_day(snap.snapshot_at.date())
        snap_ct = snap.snapshot_at - dt.timedelta(hours=5)
        t_years = _t_years_to_expiration(snap_ct, expiration)
        is_call = action.direction == "call"
        v = synthetic_vertical(
            spot=snap.spot,
            long_strike=action.long_strike,
            short_strike=action.short_strike,
            is_call=is_call,
            t_years=t_years,
            sigma=sigma,
        )
        return max(v.debit, 0.05)
    return estimator


def _build_spot_mark_provider():
    """Synthetic mark-to-close at each future minute. Uses snapshot at minute m for spot,
    Black-Scholes-prices both legs with shrinking T-to-expiration."""
    def provider(*, snapshot: GexSnapshot, action: SetupAction, minute: int, entry_minute: int, debit: float) -> float:
        sigma = max(snapshot.vix / 100.0, 0.05)
        expiration = _next_trading_day(snapshot.snapshot_at.date())
        snap_ct = snapshot.snapshot_at - dt.timedelta(hours=5)
        t_years = _t_years_to_expiration(snap_ct, expiration)
        is_call = action.direction == "call"
        long_p = bs_price(snapshot.spot, action.long_strike, t_years, sigma, is_call)
        short_p = bs_price(snapshot.spot, action.short_strike, t_years, sigma, is_call)
        return max(long_p - short_p, 0.0)
    return provider


def run(start: dt.date, end: dt.date, *, out_dir: Optional[pathlib.Path] = None):
    out_dir = out_dir or pathlib.Path("backtest/joshua_replay/output")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = pathlib.Path("docs/superpowers/reports/2026-05-11-joshua-replay.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "trades.csv"

    config = JoshuaConfig()
    debit_estimator = _build_debit_estimator()
    spot_mark = _build_spot_mark_provider()

    all_trades: list = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # skip weekends
            logger.info("Loading snapshots for %s", cur)
            snaps = load_snapshots(cur, cur, symbol="SPY")
            if snaps:
                day_trades = replay_day(snaps, config=config,
                                        spot_mark_provider=spot_mark,
                                        debit_estimator=debit_estimator)
                all_trades.extend(day_trades)
                logger.info("  %d snapshots → %d trades", len(snaps), len(day_trades))
            else:
                logger.info("  no snapshots")
        cur += dt.timedelta(days=1)

    # Write CSV
    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trade_date", "setup", "direction", "entry_minute", "exit_minute",
                    "debit", "exit_reason", "realized_pct"])
        for t in all_trades:
            w.writerow([t.trade_date, t.setup, t.direction, t.entry_minute, t.exit_minute,
                        f"{t.debit:.4f}", t.exit_reason, f"{t.realized_pct:.2f}"])
    logger.info("CSV: %s", csv_path)

    # Write markdown report
    report = build_report(all_trades, start=start, end=end)
    report_path.write_text(report)
    logger.info("Report: %s", report_path)
    print(report)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", required=True, help="YYYY-MM-DD")
    p.add_argument("--end", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    run(
        dt.date.fromisoformat(args.start),
        dt.date.fromisoformat(args.end),
    )


if __name__ == "__main__":
    main()
```

Also add `backtest/joshua_replay/__main__.py`:

```python
from backtest.joshua_replay.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-import**

Run: `python -c "from backtest.joshua_replay.cli import run; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backtest/joshua_replay/cli.py backtest/joshua_replay/__main__.py
git commit -m "joshua: replay — CLI with BS-synthetic mids + per-day driver"
```

---

## Task 19: Apply migration to dev/production postgres

**Files:**
- Reference: `migrations/2026-05-11-helios-daily-state.sql`

- [ ] **Step 1: Apply daily_state migration**

```bash
psql $DATABASE_URL -f migrations/2026-05-11-helios-daily-state.sql
```
Expected:
```
CREATE TABLE
CREATE INDEX
```

If the helios scaffold tables aren't present yet on prod, apply those first:
```bash
psql $DATABASE_URL -f migrations/2026-05-07-helios-bot-tables.sql
psql $DATABASE_URL -f migrations/2026-05-07-helios-options-intraday.sql
```

- [ ] **Step 2: Verify table exists**

```bash
psql $DATABASE_URL -c "\d helios_daily_state"
```
Expected: shows columns `trade_date`, `wall_fade_fired`, `wall_break_fired`, `flip_cross_fired`, `last_signal_minute`, `updated_at`.

- [ ] **Step 3: Run DB-backed tests against prod**

```bash
PYTHONIOENCODING=utf-8 pytest tests/trading/helios/test_db_daily_state.py -v --no-cov
```
Expected: 3 tests pass (no longer skipped).

---

## Task 20: Phase A replay — run 3 months and review

**Files:**
- Write: `docs/superpowers/reports/2026-05-11-joshua-replay.md`
- Write: `backtest/joshua_replay/output/trades.csv`

- [ ] **Step 1: Run the replay**

```bash
PYTHONIOENCODING=utf-8 python -m backtest.joshua_replay --start 2026-02-09 --end 2026-05-09 2>&1 | tee /tmp/joshua_replay.log
```
Expected: completes in 10-30 minutes. Final stdout block ends with `**Verdict: GO**` or `**Verdict: NO-GO**`.

- [ ] **Step 2: Read the report**

Run: `cat docs/superpowers/reports/2026-05-11-joshua-replay.md`
Expected: markdown report with per-setup table + GO/NO-GO bullets.

- [ ] **Step 3: Commit the report and CSV**

```bash
git add docs/superpowers/reports/2026-05-11-joshua-replay.md backtest/joshua_replay/output/trades.csv
git commit -m "joshua: Phase A replay report + trades.csv"
```

- [ ] **Step 4: Decision branch**

- **If verdict = GO**: proceed to Task 21 (live wiring).
- **If verdict = NO-GO**: save a `project_joshua_no_go_2026_05_11.md` memory, archive the branch (no merge), stop here. Document the failure mode in the memory (which bar failed, suspected cause).

---

## Task 21: Wire scheduler entry (only if GO)

**Files:**
- Modify: `scheduler/trader_scheduler.py`

- [ ] **Step 1: Locate the bot registry in `scheduler/trader_scheduler.py`**

Run: `grep -n "fortress\|solomon\|gideon\|HeliosTrader\|joshua" scheduler/trader_scheduler.py`

- [ ] **Step 2: Add HELIOS entry**

Find the section that registers other bots and add a HELIOS entry that runs `HeliosTrader.run_cycle` every 60 seconds during market hours. Use the same pattern as the nearest existing 0DTE/1DTE bot. Critical: the scheduler must:
  - Look up `helios_config.enabled` (JSON value) before firing. If `false` (default), skip.
  - Instantiate `HeliosTrader(db=HeliosDatabase(), tradier=<existing tradier client>, config=JoshuaConfig())`.

Example wiring (adapt to actual scheduler structure):

```python
from trading.helios.db import HeliosDatabase
from trading.helios.models import JoshuaConfig
from trading.helios.trader import HeliosTrader

def _helios_enabled() -> bool:
    try:
        db = HeliosDatabase()
        with db._connect() as conn:
            with conn.cursor() as c:
                c.execute("SELECT value FROM helios_config WHERE key = 'enabled'")
                row = c.fetchone()
                if not row:
                    return False
                return bool(row[0])
    except Exception:
        return False

def helios_cycle(tradier):
    if not _helios_enabled():
        return
    HeliosTrader(db=HeliosDatabase(), tradier=tradier, config=JoshuaConfig()).run_cycle()
```

Register with the scheduler's 60s tick or APScheduler `interval=60` job.

- [ ] **Step 3: Smoke-test scheduler import**

Run: `python -c "import scheduler.trader_scheduler; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add scheduler/trader_scheduler.py
git commit -m "joshua: scheduler — wire HeliosTrader.run_cycle (gated by helios_config.enabled)"
```

---

## Task 22: Merge to main (only if GO)

**Files:**
- Reference: branch `claude/joshua-directional-gex-bot`

- [ ] **Step 1: Confirm working tree clean + tests green**

Run: `git status && pytest tests/trading/helios/ tests/backtest/joshua_replay/ -v --no-cov`
Expected: clean tree, all tests pass (DB tests may skip locally).

- [ ] **Step 2: Push branch**

```bash
git push origin claude/joshua-directional-gex-bot
```

- [ ] **Step 3: Open PR + merge**

```bash
gh pr create --title "joshua: directional GEX bot off live /api/gex/SPY" --body "$(cat <<'EOF'
## Summary
- Promote HELIOS scaffold (db, routes, frontend, executor, paper-account flow) from `claude/helios-1dte-directional-design`
- Replace `signals.py` + `strategy.py` with setup-stack dispatcher (wall_fade / wall_break / flip_cross)
- Add `gex_client.py` polling `/api/gex/SPY` with 90s staleness gate
- Add `helios_daily_state` migration + db helpers for per-setup fired-today tracking
- Add `backtest/joshua_replay/` harness — runs against `watchtower_snapshots`+`argus_strikes`
- Phase A replay report: see `docs/superpowers/reports/2026-05-11-joshua-replay.md`
- Scheduler entry gated by `helios_config.enabled = true`

## Test plan
- [ ] `pytest tests/trading/helios/ tests/backtest/joshua_replay/`
- [ ] Apply `migrations/2026-05-11-helios-daily-state.sql` on prod
- [ ] Set `helios_config.enabled = true` in production DB to start paper trading
- [ ] Monitor `/api/joshua/status` and `helios_scan_activity` for first day

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Then auto-merge once CI passes:
```bash
gh pr merge --merge --delete-branch
```

- [ ] **Step 4: Enable in production (paper-only)**

```bash
psql $DATABASE_URL -c "INSERT INTO helios_config (key, value) VALUES ('enabled', 'true'::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();"
```

- [ ] **Step 5: Save memory for next session**

Write `C:/Users/lemol/.claude/projects/C--Users-lemol/memory/project_joshua_live_2026_05_11.md`:

```markdown
---
name: JOSHUA bot live (paper) on AlphaGEX
description: 1DTE SPY directional bot driven by /api/gex/SPY; 3-setup stack (wall_fade/wall_break/flip_cross); paper-only on helios_paper_account; replay verdict GO at <commit>
type: project
---

JOSHUA went live (paper-only) on <date>.

- Internal codename: HELIOS. Display: JOSHUA. Routes at /api/joshua/*. Frontend /joshua.
- 3 setups in `trading/helios/setups/`. Dispatcher at `trading/helios/signals.py`.
- Daily state in `helios_daily_state`; positions in `helios_positions`; equity in `helios_equity_snapshots`.
- Phase A replay report: `docs/superpowers/reports/2026-05-11-joshua-replay.md`.
- Enabled via `UPDATE helios_config SET value='true'::jsonb WHERE key='enabled'`.

**Why:** Phase A replay cleared the GO bar (≥30 trades, ≥55% WR, ≥+$3 EV, 2+ setups). Three prior NO-GOs all reconstructed GEX from chain quotes; this consumes the production feed.

**How to apply:** Monitor weekly for 4 weeks. If live WR ≥ 60% / EV ≥ +$5/trade post-cost / time-stop ≤ 30%, escalate to operator for live-money rollout decision.
```

Then add a line to `MEMORY.md`:
```markdown
- [JOSHUA bot live (paper)](project_joshua_live_2026_05_11.md) — 1DTE SPY directional off /api/gex/SPY; 3-setup stack; replay GO; paper Phase B monitoring
```

---

## Self-review notes

**Spec coverage** — every spec section maps to a task:
- §5 Reuse strategy → Task 1
- §6.1 Daily state → Tasks 2-4
- §6.2 wall_fade → Task 7
- §6.3 wall_break → Task 8
- §6.4 flip_cross → Task 9
- §6.5 Conflict resolution → Task 10 (dispatcher order)
- §7 Polling + scan loop → Tasks 5 (gex_client), 13 (trader)
- §8 Position management → Tasks 11 (strategy), 12 (monitor)
- §9 Sizing → Task 13 (`_executor_config`)
- §10 Components file map → File Structure section
- §11.A Phase A replay → Tasks 14-20
- §11.B Phase B paper → Tasks 21-22 + memory
- §12 Risks → mitigations applied: 90s staleness (Task 5), 5-min buffer (Task 9), no trail (Task 11), paper account (Task 22)

**No placeholders** — all code blocks complete; no `TODO`/`TBD`; all method signatures match across tasks (e.g., `decide_exit(*, debit, mark_to_close, now_ct, quotes_unavail_streak, config)` consistent in Tasks 11+12).

**Type consistency** — `JoshuaConfig` is the only config type used after Task 3. Legacy `HeliosConfig` is referenced only inside `_executor_config()` in Task 13 as a bridge to the unchanged executor. `SetupAction.direction` is `"call"` or `"put"` everywhere.
