# Agape Derivatives — Trade History & Normalized Perf Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded 50/10-row trade tables on Agape Derivatives surfaces with paginated, date-filtered "full" history backed by a new aggregator endpoint, and add a normalized multi-bot performance chart on the all page.

**Architecture:** Single new backend route `/api/agape-perpetuals/trades` fans out across 10 bot db handles, merges by `close_time DESC`, paginates with a keyset cursor. A shared frontend `<TradeHistoryTable>` component is reused on per-bot pages, the per-coin History tab on the all page, and the cross-bot Recent Trades feed on the all page. A new `<MultiBotPerpEquityChart>` does client-side normalization (indexed-to-100 default, % from inception toggle) on top of the existing per-bot `/equity-curve` endpoints.

**Tech Stack:** FastAPI + psycopg2 + ThreadPoolExecutor (backend); Next.js 14 App Router + React 18 + SWR + Recharts + Tailwind (frontend); Jest + React Testing Library (frontend tests); pytest + FastAPI TestClient (backend tests).

**Spec:** `docs/superpowers/specs/2026-05-06-agape-derivatives-trade-history-and-perf-chart-design.md`

**Branch:** `spec/agape-derivatives-trade-history-and-perf-chart` (already created with the spec commit). Continue all work on this branch; merge to `main` after Phase 4 verification.

---

## Bot id table (used everywhere)

The aggregator and the frontend agree on these slugs. Source of truth.

| `bot_id` | Display | API prefix | DB table |
|---|---|---|---|
| `eth` | ETH-PERP | `/api/agape-eth-perp` | `agape_eth_perp_positions` |
| `sol` | SOL-PERP | `/api/agape-sol-perp` | `agape_sol_perp_positions` |
| `avax` | AVAX-PERP | `/api/agape-avax-perp` | `agape_avax_perp_positions` |
| `btc` | BTC-PERP | `/api/agape-btc-perp` | `agape_btc_perp_positions` |
| `xrp` | XRP-PERP | `/api/agape-xrp-perp` | `agape_xrp_perp_positions` |
| `doge` | DOGE-PERP | `/api/agape-doge-perp` | `agape_doge_perp_positions` |
| `shib_futures` | SHIB-FUT | `/api/agape-shib-futures` | `agape_shib_futures_positions` |
| `link_futures` | LINK-FUT | `/api/agape-link-futures` | `agape_link_futures_positions` |
| `ltc_futures` | LTC-FUT | `/api/agape-ltc-futures` | `agape_ltc_futures_positions` |
| `bch_futures` | BCH-FUT | `/api/agape-bch-futures` | `agape_bch_futures_positions` |

---

## File map

### New
- `backend/api/routes/agape_perpetuals_trades_routes.py` — aggregator route + bot registry.
- `backend/tests/test_agape_perpetuals_trades_routes.py` — pytest for the aggregator.
- `frontend/src/lib/hooks/useAgapePerpTrades.ts` — SWR hook with cursor pagination.
- `frontend/src/components/perpetuals/TradeHistoryTable.tsx` — shared trade table.
- `frontend/src/components/perpetuals/MultiBotPerpEquityChart.tsx` — normalized comparison chart.
- `frontend/__tests__/components/TradeHistoryTable.test.tsx` — component tests.
- `frontend/__tests__/components/MultiBotPerpEquityChart.test.tsx` — chart tests.
- `frontend/__tests__/hooks/useAgapePerpTrades.test.ts` — hook tests.

### Modified
- `trading/agape_eth_perp/db.py`, `agape_sol_perp/db.py`, `agape_avax_perp/db.py`, `agape_btc_perp/db.py`, `agape_xrp_perp/db.py`, `agape_doge_perp/db.py`, `agape_shib_futures/db.py`, `agape_link_futures/db.py`, `agape_ltc_futures/db.py`, `agape_bch_futures/db.py` — extend `get_closed_trades` with `since`/`until`/`before` kwargs.
- `backend/main.py` — register new aggregator router.
- `frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx` — replace `HistoryTab` and `AllCoinsRecentTrades` with the shared component; place new chart.
- `frontend/src/app/agape-eth-perp/page.tsx`, `agape-sol-perp/page.tsx`, `agape-avax-perp/page.tsx`, `agape-btc-perp/page.tsx`, `agape-xrp-perp/page.tsx`, `agape-doge-perp/page.tsx`, `agape-shib-futures/page.tsx`, `agape-link-futures/page.tsx`, `agape-ltc-futures/page.tsx`, `agape-bch-futures/page.tsx` — swap History tab to use shared component.

---

## Phase 1 — Backend aggregator

### Task 1: Extend `db.get_closed_trades` on all 10 bots with date+cursor kwargs

**Files:**
- Modify: `trading/agape_btc_perp/db.py:394-441`
- Modify: same `get_closed_trades` block in `trading/agape_eth_perp/db.py`, `agape_sol_perp/db.py`, `agape_avax_perp/db.py`, `agape_xrp_perp/db.py`, `agape_doge_perp/db.py`, `agape_shib_futures/db.py`, `agape_link_futures/db.py`, `agape_ltc_futures/db.py`, `agape_bch_futures/db.py`
- Test: `tests/test_agape_perp_db_filters.py` (new)

The kwargs and SQL pattern are identical across all 10 — only the table name differs. Done as one task with per-file checkboxes.

**New signature (every bot):**
```python
def get_closed_trades(
    self,
    limit: int = 100,
    since: Optional[str] = None,           # ISO-8601, lower bound on close_time
    until: Optional[str] = None,           # ISO-8601, upper bound on close_time
    before_close_time: Optional[str] = None,  # cursor: close_time strictly less than
    before_position_id: Optional[str] = None, # cursor tiebreaker
) -> List[Dict]:
```

**SQL pattern (per bot — replace the existing `cursor.execute(...)` block):**
```python
where = ["status IN ('closed', 'expired', 'stopped')"]
params: list = []
if since:
    where.append("close_time >= %s")
    params.append(since)
if until:
    where.append("close_time <= %s")
    params.append(until)
if before_close_time:
    if before_position_id:
        where.append("(close_time < %s OR (close_time = %s AND position_id > %s))")
        params.extend([before_close_time, before_close_time, before_position_id])
    else:
        where.append("close_time < %s")
        params.append(before_close_time)
sql = f"""
    SELECT position_id, side, quantity, entry_price,
           close_price, realized_pnl, close_reason,
           open_time, close_time,
           funding_regime_at_entry, squeeze_risk_at_entry,
           oracle_advice, oracle_win_probability,
           signal_action, signal_confidence, max_risk_usd,
           regime_at_entry
    FROM <TABLE_NAME>
    WHERE {' AND '.join(where)}
    ORDER BY close_time DESC, position_id ASC
    LIMIT %s
"""
params.append(limit)
cursor.execute(sql, params)
```

The keyset condition `(close_time < %s OR (close_time = %s AND position_id > %s))` matches the merge tiebreaker `(close_time DESC, bot_id ASC, position_id ASC)` — within one bot, `bot_id` is constant, so we tiebreak on `position_id ASC` going forward in pagination.

**Note on per-bot column variations:** XRP, SHIB-FUTURES, LINK/LTC/BCH-FUTURES, DOGE, AVAX may have a slightly different column list than BTC (e.g., no `squeeze_risk_at_entry` on some). Read each `get_closed_trades` block before editing and preserve that bot's existing column list verbatim — only modify the WHERE clause, the ORDER BY, and the parameter binding. Do not add or rename columns.

- [ ] **Step 1: Write the failing test for `since` filter (using btc bot db as the canonical case)**

Create `tests/test_agape_perp_db_filters.py`:

```python
"""Verify get_closed_trades supports since/until/before keyset cursor across all 10 perp/futures bots."""
from unittest.mock import MagicMock
import pytest
from trading.agape_btc_perp.db import AgapeBtcPerpDB


def _mock_conn(rows):
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = rows
    conn.cursor.return_value = cursor
    return conn, cursor


def test_get_closed_trades_passes_since_filter_to_sql(monkeypatch):
    db = AgapeBtcPerpDB.__new__(AgapeBtcPerpDB)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(limit=10, since="2026-05-01T00:00:00+00:00")
    sql, params = cursor.execute.call_args[0]
    assert "close_time >= %s" in sql
    assert "2026-05-01T00:00:00+00:00" in params


def test_get_closed_trades_passes_until_filter_to_sql(monkeypatch):
    db = AgapeBtcPerpDB.__new__(AgapeBtcPerpDB)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(limit=10, until="2026-05-06T00:00:00+00:00")
    sql, params = cursor.execute.call_args[0]
    assert "close_time <= %s" in sql
    assert "2026-05-06T00:00:00+00:00" in params


def test_get_closed_trades_keyset_cursor(monkeypatch):
    db = AgapeBtcPerpDB.__new__(AgapeBtcPerpDB)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(
        limit=10,
        before_close_time="2026-05-05T12:00:00+00:00",
        before_position_id="abc-123",
    )
    sql, params = cursor.execute.call_args[0]
    assert "close_time < %s OR" in sql
    assert "2026-05-05T12:00:00+00:00" in params
    assert "abc-123" in params


def test_get_closed_trades_no_filters_keeps_legacy_behavior(monkeypatch):
    db = AgapeBtcPerpDB.__new__(AgapeBtcPerpDB)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    db.get_closed_trades(limit=50)
    sql, params = cursor.execute.call_args[0]
    assert "close_time >=" not in sql
    assert "close_time <=" not in sql
    assert params[-1] == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_agape_perp_db_filters.py -v`
Expected: FAIL with `TypeError: get_closed_trades() got an unexpected keyword argument 'since'` (or similar).

- [ ] **Step 3: Implement on `agape_btc_perp/db.py` first**

Open `trading/agape_btc_perp/db.py` at line 394. Replace the `def get_closed_trades(self, limit: int = 100) -> List[Dict]:` and its body up to the `return trades` (lines 394–435) with:

```python
def get_closed_trades(
    self,
    limit: int = 100,
    since: Optional[str] = None,
    until: Optional[str] = None,
    before_close_time: Optional[str] = None,
    before_position_id: Optional[str] = None,
) -> List[Dict]:
    conn = self._get_conn()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        where = ["status IN ('closed', 'expired', 'stopped')"]
        params: list = []
        if since:
            where.append("close_time >= %s")
            params.append(since)
        if until:
            where.append("close_time <= %s")
            params.append(until)
        if before_close_time:
            if before_position_id:
                where.append("(close_time < %s OR (close_time = %s AND position_id > %s))")
                params.extend([before_close_time, before_close_time, before_position_id])
            else:
                where.append("close_time < %s")
                params.append(before_close_time)
        sql = f"""
            SELECT position_id, side, quantity, entry_price,
                   close_price, realized_pnl, close_reason,
                   open_time, close_time,
                   funding_regime_at_entry, squeeze_risk_at_entry,
                   oracle_advice, oracle_win_probability,
                   signal_action, signal_confidence, max_risk_usd,
                   regime_at_entry
            FROM agape_btc_perp_positions
            WHERE {' AND '.join(where)}
            ORDER BY close_time DESC, position_id ASC
            LIMIT %s
        """
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        trades = []
        for row in rows:
            trades.append({
                "position_id": row[0],
                "side": row[1],
                "quantity": float(row[2]),
                "entry_price": float(row[3]),
                "close_price": float(row[4]) if row[4] else None,
                "realized_pnl": float(row[5]) if row[5] else 0,
                "close_reason": row[6],
                "open_time": row[7].isoformat() if row[7] else None,
                "close_time": row[8].isoformat() if row[8] else None,
                "funding_regime_at_entry": row[9],
                "squeeze_risk_at_entry": row[10],
                "oracle_advice": row[11],
                "oracle_win_probability": float(row[12]) if row[12] else None,
                "signal_action": row[13],
                "signal_confidence": row[14],
                "max_risk_usd": float(row[15]) if row[15] is not None else None,
                "regime_at_entry": row[16],
            })
        return trades
    except Exception as e:
        logger.error(f"AGAPE-BTC-PERP DB: Failed to get closed trades: {e}")
        return []
    finally:
        cursor.close()
        conn.close()
```

Make sure `Optional` is imported at the top of the file (`from typing import Optional, List, Dict`).

- [ ] **Step 4: Run tests to verify the btc-perp version passes**

Run: `pytest tests/test_agape_perp_db_filters.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Apply the same change to the other 9 bots**

For each of these files, open the file, find `def get_closed_trades(self, limit: int = 100)`, and apply the exact same diff: extend the signature, build the WHERE/params dynamically, swap to f-string SQL, change ORDER BY to `close_time DESC, position_id ASC`. **Preserve each bot's existing SELECT column list verbatim** — only the bot-specific table name in `FROM` and any column differences (e.g., a bot that doesn't store `squeeze_risk_at_entry` will have a shorter SELECT; leave that alone). The WHERE/ORDER/LIMIT logic is identical.

  - [ ] `trading/agape_eth_perp/db.py:371`
  - [ ] `trading/agape_sol_perp/db.py:371`
  - [ ] `trading/agape_avax_perp/db.py:371`
  - [ ] `trading/agape_xrp_perp/db.py:370`
  - [ ] `trading/agape_doge_perp/db.py:359`
  - [ ] `trading/agape_shib_futures/db.py:360`
  - [ ] `trading/agape_link_futures/db.py:360`
  - [ ] `trading/agape_ltc_futures/db.py:360`
  - [ ] `trading/agape_bch_futures/db.py:360`

- [ ] **Step 6: Add a parametric test that covers all 10 bots' signatures**

Append to `tests/test_agape_perp_db_filters.py`:

```python
import importlib
BOT_DB_MODULES = [
    ("trading.agape_eth_perp.db", "AgapeEthPerpDB"),
    ("trading.agape_sol_perp.db", "AgapeSolPerpDB"),
    ("trading.agape_avax_perp.db", "AgapeAvaxPerpDB"),
    ("trading.agape_btc_perp.db", "AgapeBtcPerpDB"),
    ("trading.agape_xrp_perp.db", "AgapeXrpPerpDB"),
    ("trading.agape_doge_perp.db", "AgapeDogePerpDB"),
    ("trading.agape_shib_futures.db", "AgapeShibFuturesDB"),
    ("trading.agape_link_futures.db", "AgapeLinkFuturesDB"),
    ("trading.agape_ltc_futures.db", "AgapeLtcFuturesDB"),
    ("trading.agape_bch_futures.db", "AgapeBchFuturesDB"),
]

@pytest.mark.parametrize("modpath,clsname", BOT_DB_MODULES)
def test_all_bots_accept_new_kwargs(modpath, clsname, monkeypatch):
    mod = importlib.import_module(modpath)
    cls = getattr(mod, clsname)
    db = cls.__new__(cls)
    conn, cursor = _mock_conn([])
    monkeypatch.setattr(db, "_get_conn", lambda: conn)
    # Should not raise
    db.get_closed_trades(
        limit=5,
        since="2026-05-01T00:00:00+00:00",
        until="2026-05-06T00:00:00+00:00",
        before_close_time="2026-05-05T12:00:00+00:00",
        before_position_id="zzz",
    )
    sql, _params = cursor.execute.call_args[0]
    assert "ORDER BY close_time DESC, position_id ASC" in sql
```

If a class name differs from the convention above (e.g., a bot uses `AGAPEBtcPerpDatabase` instead of `AgapeBtcPerpDB`), update the constant accordingly — find the actual class with `grep -n "^class " trading/<bot>/db.py`. Do not change the bots; correct the test list.

- [ ] **Step 7: Run full test file**

Run: `pytest tests/test_agape_perp_db_filters.py -v`
Expected: all tests PASS, including 10 parametric cases.

- [ ] **Step 8: Commit**

```bash
git add tests/test_agape_perp_db_filters.py trading/agape_*_perp/db.py trading/agape_*_futures/db.py
git commit -m "feat(agape-perps): add since/until/cursor filters to get_closed_trades on all 10 bots

Extend each bot's db.get_closed_trades with optional since, until,
before_close_time, before_position_id kwargs to support the
/api/agape-perpetuals/trades aggregator. ORDER BY adds position_id ASC
as a deterministic tiebreaker for keyset pagination.

No behavior change when called without new kwargs (legacy callers).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Build the `/api/agape-perpetuals/trades` aggregator route

**Files:**
- Create: `backend/api/routes/agape_perpetuals_trades_routes.py`
- Test: `backend/tests/test_agape_perpetuals_trades_routes.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_agape_perpetuals_trades_routes.py`:

```python
"""Tests for /api/agape-perpetuals/trades aggregator route."""
import base64
import json
from unittest.mock import patch
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import agape_perpetuals_trades_routes


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(agape_perpetuals_trades_routes.router)
    return TestClient(app)


def _fake_trade(bot_id, position_id, close_time, pnl=10.0, max_risk=100.0):
    return {
        "position_id": position_id,
        "side": "long",
        "quantity": 1.0,
        "entry_price": 100.0,
        "close_price": 110.0,
        "realized_pnl": pnl,
        "close_reason": "PROFIT",
        "open_time": "2026-05-01T00:00:00+00:00",
        "close_time": close_time,
        "max_risk_usd": max_risk,
    }


def _patch_registry(trades_by_bot):
    """trades_by_bot: {bot_id: [trade dicts]}"""
    def fetch(bot_id, **kwargs):
        return trades_by_bot.get(bot_id, [])
    return patch.object(
        agape_perpetuals_trades_routes,
        "_fetch_bot_trades",
        side_effect=lambda bot_id, **kw: fetch(bot_id, **kw),
    )


def test_unknown_bot_returns_400(client):
    r = client.get("/api/agape-perpetuals/trades?bots=xxx&limit=10")
    assert r.status_code == 400


def test_filters_to_requested_bots(client):
    trades = {
        "btc": [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00")],
        "eth": [_fake_trade("eth", "e1", "2026-05-05T11:00:00+00:00")],
        "sol": [_fake_trade("sol", "s1", "2026-05-05T12:00:00+00:00")],
    }
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=btc,eth&limit=10")
    assert r.status_code == 200
    body = r.json()
    bot_ids = sorted({t["bot_id"] for t in body["trades"]})
    assert bot_ids == ["btc", "eth"]


def test_merges_descending_by_close_time(client):
    trades = {
        "btc": [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00")],
        "eth": [_fake_trade("eth", "e1", "2026-05-05T12:00:00+00:00")],
    }
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=btc,eth&limit=10")
    body = r.json()
    times = [t["close_time"] for t in body["trades"]]
    assert times == sorted(times, reverse=True)


def test_cursor_round_trip(client):
    trades = {
        "btc": [
            _fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00"),
            _fake_trade("btc", "b2", "2026-05-05T09:00:00+00:00"),
            _fake_trade("btc", "b3", "2026-05-05T08:00:00+00:00"),
        ],
    }
    with _patch_registry(trades):
        page1 = client.get("/api/agape-perpetuals/trades?bots=btc&limit=2").json()
    assert len(page1["trades"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"]

    with _patch_registry(trades):
        page2 = client.get(
            f"/api/agape-perpetuals/trades?bots=btc&limit=2&before={page1['next_cursor']}"
        ).json()
    seen = {t["position_id"] for t in page1["trades"]} | {t["position_id"] for t in page2["trades"]}
    assert seen == {"b1", "b2", "b3"}
    assert page2["has_more"] is False


def test_realized_pnl_pct_computed(client):
    trades = {"btc": [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00", pnl=25.0, max_risk=100.0)]}
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=btc&limit=10")
    t = r.json()["trades"][0]
    assert t["realized_pnl_pct"] == pytest.approx(25.0)


def test_star_expands_to_all_active(client):
    trades = {b: [] for b in [
        "eth","sol","avax","btc","xrp","doge","shib_futures","link_futures","ltc_futures","bch_futures"
    ]}
    trades["btc"] = [_fake_trade("btc", "b1", "2026-05-05T10:00:00+00:00")]
    with _patch_registry(trades):
        r = client.get("/api/agape-perpetuals/trades?bots=*&limit=50")
    assert r.status_code == 200
    assert len(r.json()["trades"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_agape_perpetuals_trades_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.api.routes.agape_perpetuals_trades_routes'` (or similar import error).

- [ ] **Step 3: Implement the aggregator route**

Create `backend/api/routes/agape_perpetuals_trades_routes.py`:

```python
"""
AGAPE Perpetuals/Futures aggregated trade history.

Single endpoint that fans out across all 10 perp/futures bots, merges
their closed trades by close_time DESC, and paginates with a stable
keyset cursor on (close_time, bot_id, position_id).

Powers the cross-bot Recent Trades feed on /perpetuals-crypto, the
per-coin History tab on the same page, and the History tab on each
bot's individual page.
"""

from __future__ import annotations

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agape-perpetuals", tags=["AGAPE-PERPETUALS"])

# ----------------------------------------------------------------------
# Bot registry: bot_id → (display_label, trader_factory)
# Each factory returns a trader (or None) whose .db.get_closed_trades(...)
# is callable. Factories must be lazy-imported so a missing bot dependency
# does not break the whole route.
# ----------------------------------------------------------------------

def _trader_factory(import_path: str, attr: str) -> Callable[[], Optional[object]]:
    def _factory() -> Optional[object]:
        try:
            mod = __import__(import_path, fromlist=[attr])
            getter = getattr(mod, attr)
            return getter()
        except Exception as e:
            logger.warning(f"agape-perpetuals trades: registry factory {import_path}.{attr} failed: {e}")
            return None
    return _factory


_BOT_REGISTRY: Dict[str, Dict] = {
    "eth":          {"label": "ETH-PERP",  "factory": _trader_factory("trading.agape_eth_perp.trader",  "get_agape_eth_perp_trader")},
    "sol":          {"label": "SOL-PERP",  "factory": _trader_factory("trading.agape_sol_perp.trader",  "get_agape_sol_perp_trader")},
    "avax":         {"label": "AVAX-PERP", "factory": _trader_factory("trading.agape_avax_perp.trader", "get_agape_avax_perp_trader")},
    "btc":          {"label": "BTC-PERP",  "factory": _trader_factory("trading.agape_btc_perp.trader",  "get_agape_btc_perp_trader")},
    "xrp":          {"label": "XRP-PERP",  "factory": _trader_factory("trading.agape_xrp_perp.trader",  "get_agape_xrp_perp_trader")},
    "doge":         {"label": "DOGE-PERP", "factory": _trader_factory("trading.agape_doge_perp.trader", "get_agape_doge_perp_trader")},
    "shib_futures": {"label": "SHIB-FUT",  "factory": _trader_factory("trading.agape_shib_futures.trader", "get_agape_shib_futures_trader")},
    "link_futures": {"label": "LINK-FUT",  "factory": _trader_factory("trading.agape_link_futures.trader", "get_agape_link_futures_trader")},
    "ltc_futures":  {"label": "LTC-FUT",   "factory": _trader_factory("trading.agape_ltc_futures.trader",  "get_agape_ltc_futures_trader")},
    "bch_futures":  {"label": "BCH-FUT",   "factory": _trader_factory("trading.agape_bch_futures.trader",  "get_agape_bch_futures_trader")},
}

ALL_BOT_IDS: List[str] = list(_BOT_REGISTRY.keys())


def _fetch_bot_trades(
    bot_id: str,
    *,
    limit: int,
    since: Optional[str],
    until: Optional[str],
    before_close_time: Optional[str],
    before_position_id: Optional[str],
) -> List[Dict]:
    """Pull up to (limit) closed trades for one bot via its existing db handle.

    Isolated as a module-level function so tests can patch it.
    """
    entry = _BOT_REGISTRY.get(bot_id)
    if not entry:
        return []
    trader = entry["factory"]()
    if trader is None or not getattr(trader, "db", None):
        return []
    try:
        return trader.db.get_closed_trades(
            limit=limit,
            since=since,
            until=until,
            before_close_time=before_close_time,
            before_position_id=before_position_id,
        )
    except Exception as e:
        logger.error(f"agape-perpetuals trades: fetch {bot_id} failed: {e}")
        return []


def _encode_cursor(close_time: str, bot_id: str, position_id: str) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"close_time": close_time, "bot_id": bot_id, "position_id": position_id}).encode("utf-8")
    ).decode("ascii")


def _decode_cursor(cursor: str) -> Optional[Dict]:
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except Exception:
        return None


def _compute_pnl_pct(t: Dict) -> Optional[float]:
    pnl = t.get("realized_pnl")
    if pnl is None:
        return None
    risk = t.get("max_risk_usd")
    if risk and risk > 0:
        return float(pnl) / float(risk) * 100.0
    qty = t.get("quantity") or 0
    entry = t.get("entry_price") or 0
    notional = qty * entry
    if notional > 0:
        return float(pnl) / float(notional) * 100.0
    return None


def _parse_bots_param(bots: str) -> List[str]:
    if bots.strip() == "*":
        return list(ALL_BOT_IDS)
    requested = [b.strip().lower() for b in bots.split(",") if b.strip()]
    unknown = [b for b in requested if b not in _BOT_REGISTRY]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown bot ids: {unknown}")
    return requested


@router.get("/trades")
async def get_aggregated_trades(
    bots: str = Query(..., description="Comma-separated bot ids, or '*' for all 10"),
    since: Optional[str] = Query(None, description="ISO-8601 lower bound on close_time"),
    until: Optional[str] = Query(None, description="ISO-8601 upper bound on close_time"),
    before: Optional[str] = Query(None, description="Opaque keyset cursor from a prior response"),
    limit: int = Query(100, ge=1, le=500),
):
    bot_ids = _parse_bots_param(bots)

    cursor = _decode_cursor(before) if before else None
    before_close_time = cursor["close_time"] if cursor else None
    before_position_id = cursor["position_id"] if cursor else None

    # Default to last 30d if no since and no cursor
    if not since and not cursor:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    per_bot_limit = limit + 1

    def _worker(bid: str) -> List[Dict]:
        rows = _fetch_bot_trades(
            bid,
            limit=per_bot_limit,
            since=since,
            until=until,
            before_close_time=before_close_time,
            before_position_id=before_position_id,
        )
        for r in rows:
            r["bot_id"] = bid
            r["bot_label"] = _BOT_REGISTRY[bid]["label"]
            r["realized_pnl_pct"] = _compute_pnl_pct(r)
        return rows

    pool_size = max(1, min(len(bot_ids), 10))
    with ThreadPoolExecutor(max_workers=pool_size) as ex:
        per_bot = list(ex.map(_worker, bot_ids))

    merged: List[Dict] = []
    for rows in per_bot:
        merged.extend(rows)

    merged.sort(
        key=lambda t: (
            t.get("close_time") or "",
            # bot_id ASC, position_id ASC for deterministic tiebreak
            t.get("bot_id") or "",
            t.get("position_id") or "",
        ),
        reverse=False,
    )
    # Re-sort: close_time DESC, then bot_id ASC, then position_id ASC
    merged.sort(key=lambda t: (t.get("close_time") or ""), reverse=True)

    page = merged[:limit]
    has_more = len(merged) > limit
    next_cursor: Optional[str] = None
    if has_more:
        peek = merged[limit]
        next_cursor = _encode_cursor(
            peek.get("close_time") or "",
            peek.get("bot_id") or "",
            peek.get("position_id") or "",
        )

    return {
        "trades": page,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "window": {"since": since, "until": until},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_agape_perpetuals_trades_routes.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/agape_perpetuals_trades_routes.py backend/tests/test_agape_perpetuals_trades_routes.py
git commit -m "feat(agape-perps): add /api/agape-perpetuals/trades aggregator

Single endpoint that fans out across the 10 perp/futures bots, merges
by close_time DESC, paginates with a keyset cursor on
(close_time, bot_id, position_id). Default 30-day window, 500-row max.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Register the new router in `backend/main.py`

**Files:**
- Modify: `backend/main.py:97` (import block) and `:379` (include_router block)

- [ ] **Step 1: Add the import**

Open `backend/main.py`. Find the line `agape_bch_futures_routes,   # AGAPE-BCH-FUTURES - BCH-FUT monthly futures bot` (line 97) and add immediately after it:

```python
    agape_perpetuals_trades_routes,  # AGAPE Perpetuals aggregated trade history
```

- [ ] **Step 2: Add the include_router call**

Find the line `app.include_router(agape_bch_futures_routes.router)` (line 379) and add immediately after it:

```python
app.include_router(agape_perpetuals_trades_routes.router)
```

- [ ] **Step 3: Smoke-import the app**

Run: `python -c "from backend.main import app; print(sorted([r.path for r in app.routes if 'agape-perpetuals' in r.path]))"`
Expected: prints `['/api/agape-perpetuals/trades']`.

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(agape-perps): wire aggregator route into FastAPI app

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Frontend shared trade-history component

### Task 4: `useAgapePerpTrades` hook with cursor pagination

**Files:**
- Create: `frontend/src/lib/hooks/useAgapePerpTrades.ts`
- Test: `frontend/__tests__/hooks/useAgapePerpTrades.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/__tests__/hooks/useAgapePerpTrades.test.ts`:

```ts
import { renderHook, act, waitFor } from '@testing-library/react'
import { useAgapePerpTrades } from '@/lib/hooks/useAgapePerpTrades'
import { SWRConfig } from 'swr'
import React from 'react'

const wrapper: React.FC<{ children: React.ReactNode }> = ({ children }) =>
  React.createElement(SWRConfig, { value: { provider: () => new Map(), dedupingInterval: 0 } }, children)

beforeEach(() => {
  // @ts-ignore
  global.fetch = jest.fn()
})

function mockResponse(payload: any) {
  // @ts-ignore
  global.fetch.mockResolvedValueOnce({
    ok: true,
    json: async () => payload,
  })
}

test('fetches initial page with default 30d range', async () => {
  mockResponse({
    trades: [{ bot_id: 'btc', position_id: 'b1', close_time: '2026-05-05T10:00:00Z', realized_pnl: 10 }],
    has_more: false,
    next_cursor: null,
  })

  const { result } = renderHook(() => useAgapePerpTrades({ bots: ['btc'], range: '30d' }), { wrapper })
  await waitFor(() => expect(result.current.isLoading).toBe(false))
  expect(result.current.trades).toHaveLength(1)
  expect(result.current.hasMore).toBe(false)

  // @ts-ignore
  const url: string = global.fetch.mock.calls[0][0]
  expect(url).toContain('/api/agape-perpetuals/trades')
  expect(url).toContain('bots=btc')
  expect(url).toContain('limit=100')
})

test('loadMore appends next page using cursor', async () => {
  mockResponse({
    trades: [{ bot_id: 'btc', position_id: 'b1', close_time: '2026-05-05T10:00:00Z', realized_pnl: 10 }],
    has_more: true,
    next_cursor: 'CURSOR1',
  })

  const { result } = renderHook(() => useAgapePerpTrades({ bots: ['btc'], range: '30d' }), { wrapper })
  await waitFor(() => expect(result.current.trades).toHaveLength(1))

  mockResponse({
    trades: [{ bot_id: 'btc', position_id: 'b2', close_time: '2026-05-04T10:00:00Z', realized_pnl: 5 }],
    has_more: false,
    next_cursor: null,
  })

  act(() => { result.current.loadMore() })
  await waitFor(() => expect(result.current.trades).toHaveLength(2))

  // @ts-ignore
  const url: string = global.fetch.mock.calls[1][0]
  expect(url).toContain('before=CURSOR1')
})

test('range change resets accumulated pages', async () => {
  mockResponse({ trades: [{ bot_id: 'btc', position_id: 'b1', close_time: '2026-05-05T10:00:00Z', realized_pnl: 1 }], has_more: true, next_cursor: 'C' })
  const { result, rerender } = renderHook(
    ({ range }: { range: '7d' | '30d' }) => useAgapePerpTrades({ bots: ['btc'], range }),
    { wrapper, initialProps: { range: '30d' } },
  )
  await waitFor(() => expect(result.current.trades).toHaveLength(1))

  mockResponse({ trades: [{ bot_id: 'btc', position_id: 'b9', close_time: '2026-05-05T11:00:00Z', realized_pnl: 9 }], has_more: false, next_cursor: null })
  rerender({ range: '7d' })
  await waitFor(() => expect(result.current.trades).toEqual([
    expect.objectContaining({ position_id: 'b9' })
  ]))
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- useAgapePerpTrades`
Expected: FAIL with module-not-found error.

- [ ] **Step 3: Implement the hook**

Create `frontend/src/lib/hooks/useAgapePerpTrades.ts`:

```ts
import { useCallback, useEffect, useMemo, useState } from 'react'
import useSWRInfinite from 'swr/infinite'

const API = process.env.NEXT_PUBLIC_API_URL || ''

export type Trade = {
  bot_id: string
  bot_label: string
  position_id: string
  side: 'long' | 'short'
  quantity: number
  entry_price: number
  close_price: number | null
  realized_pnl: number
  realized_pnl_pct: number | null
  close_reason: string | null
  open_time: string | null
  close_time: string | null
  max_risk_usd: number | null
}

export type TradesPage = {
  trades: Trade[]
  has_more: boolean
  next_cursor: string | null
  window: { since: string | null; until: string | null }
}

export type RangePreset = '7d' | '30d' | '90d' | 'all'
export type Range = RangePreset | { since: Date; until: Date }

export type UseAgapePerpTradesOpts = {
  bots: string[]                // e.g. ['btc'] or all 10
  range: Range
  pageSize?: number             // default 100
}

function rangeToParams(range: Range): { since?: string; until?: string } {
  if (typeof range === 'string') {
    if (range === 'all') return {}
    const days = range === '7d' ? 7 : range === '30d' ? 30 : 90
    const since = new Date(Date.now() - days * 86_400_000).toISOString()
    return { since }
  }
  return { since: range.since.toISOString(), until: range.until.toISOString() }
}

function buildUrl(bots: string[], range: Range, limit: number, before: string | null): string {
  const { since, until } = rangeToParams(range)
  const qs = new URLSearchParams()
  qs.set('bots', bots.join(','))
  qs.set('limit', String(limit))
  if (since) qs.set('since', since)
  if (until) qs.set('until', until)
  if (before) qs.set('before', before)
  return `${API}/api/agape-perpetuals/trades?${qs.toString()}`
}

const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(`API error ${r.status}`)
  return r.json() as Promise<TradesPage>
})

export function useAgapePerpTrades({ bots, range, pageSize = 100 }: UseAgapePerpTradesOpts) {
  const botsKey = useMemo(() => [...bots].sort().join(','), [bots])
  const rangeKey = useMemo(() => (typeof range === 'string' ? range : `${range.since.toISOString()}_${range.until.toISOString()}`), [range])

  const getKey = useCallback(
    (pageIndex: number, prevPageData: TradesPage | null) => {
      if (prevPageData && !prevPageData.has_more) return null
      const before = pageIndex === 0 ? null : (prevPageData?.next_cursor ?? null)
      return [`agape-perp-trades`, botsKey, rangeKey, pageIndex, before, pageSize]
    },
    [botsKey, rangeKey, pageSize],
  )

  const { data, size, setSize, isLoading, isValidating, error, mutate } = useSWRInfinite<TradesPage>(
    getKey,
    async (key) => {
      const before = key[4] as string | null
      return fetcher(buildUrl(bots, range, pageSize, before))
    },
    {
      revalidateFirstPage: true,
      refreshInterval: 0,
      dedupingInterval: 30_000,
    },
  )

  // Refresh page 1 on a 60s heartbeat without re-pulling subsequent pages.
  useEffect(() => {
    const id = setInterval(() => mutate(), 60_000)
    return () => clearInterval(id)
  }, [mutate])

  const pages = data || []
  const trades = useMemo(() => pages.flatMap(p => p.trades), [pages])
  const lastPage = pages[pages.length - 1]
  const hasMore = !!lastPage?.has_more

  const loadMore = useCallback(() => { setSize(s => s + 1) }, [setSize])
  const reset = useCallback(() => { setSize(1); mutate() }, [setSize, mutate])

  return {
    trades,
    hasMore,
    loadMore,
    reset,
    isLoading: isLoading && pages.length === 0,
    isLoadingMore: isValidating && pages.length > 0 && size > pages.length - 1,
    error: error as Error | undefined,
  }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- useAgapePerpTrades`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/hooks/useAgapePerpTrades.ts frontend/__tests__/hooks/useAgapePerpTrades.test.ts
git commit -m "feat(agape-perps): useAgapePerpTrades hook with cursor pagination

SWR-based, range presets (7d/30d/90d/all/custom), Load more via keyset
cursor, range change resets accumulated pages, page 1 refreshes every
60s.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `<TradeHistoryTable>` shared component

**Files:**
- Create: `frontend/src/components/perpetuals/TradeHistoryTable.tsx`
- Test: `frontend/__tests__/components/TradeHistoryTable.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/__tests__/components/TradeHistoryTable.test.tsx`:

```tsx
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TradeHistoryTable } from '@/components/perpetuals/TradeHistoryTable'
import * as hookMod from '@/lib/hooks/useAgapePerpTrades'

jest.mock('@/lib/hooks/useAgapePerpTrades')

function mockHook(overrides: Partial<ReturnType<typeof hookMod.useAgapePerpTrades>> = {}) {
  ;(hookMod.useAgapePerpTrades as jest.Mock).mockReturnValue({
    trades: [],
    hasMore: false,
    loadMore: jest.fn(),
    reset: jest.fn(),
    isLoading: false,
    isLoadingMore: false,
    error: undefined,
    ...overrides,
  })
}

test('renders rows from hook', () => {
  mockHook({
    trades: [
      {
        bot_id: 'btc', bot_label: 'BTC-PERP', position_id: 'b1', side: 'long',
        quantity: 1, entry_price: 100, close_price: 110, realized_pnl: 10, realized_pnl_pct: 10,
        close_reason: 'PROFIT', open_time: null, close_time: '2026-05-05T10:00:00Z', max_risk_usd: 100,
      } as any,
    ],
  })
  render(<TradeHistoryTable bots={['btc']} />)
  expect(screen.getByText('PROFIT')).toBeInTheDocument()
})

test('shows bot column when showBotColumn=true', () => {
  mockHook({
    trades: [
      {
        bot_id: 'btc', bot_label: 'BTC-PERP', position_id: 'b1', side: 'long',
        quantity: 1, entry_price: 100, close_price: 110, realized_pnl: 10, realized_pnl_pct: 10,
        close_reason: 'PROFIT', open_time: null, close_time: '2026-05-05T10:00:00Z', max_risk_usd: 100,
      } as any,
    ],
  })
  render(<TradeHistoryTable bots={['btc', 'eth']} showBotColumn />)
  expect(screen.getByText('BTC-PERP')).toBeInTheDocument()
})

test('Load more invokes hook.loadMore', () => {
  const loadMore = jest.fn()
  mockHook({ trades: [], hasMore: true, loadMore })
  render(<TradeHistoryTable bots={['btc']} />)
  fireEvent.click(screen.getByRole('button', { name: /load more/i }))
  expect(loadMore).toHaveBeenCalled()
})

test('range chip switches range', async () => {
  mockHook({ trades: [] })
  render(<TradeHistoryTable bots={['btc']} defaultRange="30d" />)
  fireEvent.click(screen.getByRole('button', { name: '7d' }))
  await waitFor(() => {
    const lastCall = (hookMod.useAgapePerpTrades as jest.Mock).mock.calls.at(-1)?.[0]
    expect(lastCall?.range).toBe('7d')
  })
})

test('shows empty state when no trades and not loading', () => {
  mockHook({ trades: [], isLoading: false })
  render(<TradeHistoryTable bots={['btc']} />)
  expect(screen.getByText(/no closed trades/i)).toBeInTheDocument()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- TradeHistoryTable`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/perpetuals/TradeHistoryTable.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { History, Loader2, RefreshCw } from 'lucide-react'
import { useAgapePerpTrades, type RangePreset, type Trade } from '@/lib/hooks/useAgapePerpTrades'

const RANGE_PRESETS: { id: RangePreset; label: string }[] = [
  { id: '7d',  label: '7d' },
  { id: '30d', label: '30d' },
  { id: '90d', label: '90d' },
  { id: 'all', label: 'All' },
]

type Props = {
  bots: string[]
  showBotColumn?: boolean
  defaultRange?: RangePreset
  pageSize?: number
  title?: string
}

function fmtUsd(v: number | null | undefined) {
  if (v == null) return '---'
  const sign = v >= 0 ? '+' : ''
  return `${sign}$${v.toFixed(2)}`
}

function pnlColor(v: number) {
  return v >= 0 ? 'text-green-400' : 'text-red-400'
}

export function TradeHistoryTable({
  bots,
  showBotColumn = bots.length > 1,
  defaultRange = '30d',
  pageSize = 100,
  title,
}: Props) {
  const [preset, setPreset] = useState<RangePreset>(defaultRange)
  const [customMode, setCustomMode] = useState(false)
  const [customSince, setCustomSince] = useState<string>('')
  const [customUntil, setCustomUntil] = useState<string>('')

  const range = customMode && customSince && customUntil
    ? { since: new Date(customSince), until: new Date(customUntil) }
    : preset

  const { trades, hasMore, loadMore, isLoading, isLoadingMore, error, reset } =
    useAgapePerpTrades({ bots, range, pageSize })

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-800 flex-wrap">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-gray-400" />
          <h3 className="text-sm font-medium text-gray-200">{title || 'Trade History'}</h3>
          <span className="text-xs text-gray-500">({trades.length}{hasMore ? '+' : ''})</span>
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {RANGE_PRESETS.map(p => (
            <button
              key={p.id}
              type="button"
              aria-label={p.label}
              onClick={() => { setCustomMode(false); setPreset(p.id) }}
              className={`px-2 py-1 text-xs rounded border ${
                !customMode && preset === p.id
                  ? 'bg-cyan-600/30 border-cyan-500 text-cyan-200'
                  : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              }`}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setCustomMode(v => !v)}
            className={`px-2 py-1 text-xs rounded border ${
              customMode ? 'bg-cyan-600/30 border-cyan-500 text-cyan-200' : 'border-gray-700 text-gray-400 hover:bg-gray-800'
            }`}
          >
            Custom
          </button>
          {customMode && (
            <>
              <input
                type="date"
                value={customSince}
                onChange={e => setCustomSince(e.target.value)}
                className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-200"
              />
              <span className="text-gray-500 text-xs">→</span>
              <input
                type="date"
                value={customUntil}
                onChange={e => setCustomUntil(e.target.value)}
                className="px-2 py-1 text-xs bg-gray-800 border border-gray-700 rounded text-gray-200"
              />
            </>
          )}
        </div>
      </div>

      {error ? (
        <div className="p-6 text-center text-red-400 text-sm">
          Failed to load trades: {error.message}
          <button onClick={reset} className="ml-2 underline">Retry</button>
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="w-5 h-5 text-gray-500 animate-spin" />
        </div>
      ) : trades.length === 0 ? (
        <div className="p-8 text-center text-gray-500 text-sm">
          No closed trades in this range. Try widening the date range.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-800/50 sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Closed</th>
                {showBotColumn && <th className="text-left px-3 py-2 text-gray-500 font-medium">Bot</th>}
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Side</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Qty</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Entry</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">Close</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">PnL ($)</th>
                <th className="text-right px-3 py-2 text-gray-500 font-medium">PnL (%)</th>
                <th className="text-left px-3 py-2 text-gray-500 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {trades.map((t: Trade) => (
                <tr key={`${t.bot_id}-${t.position_id}`} className="hover:bg-gray-800/30">
                  <td className="px-3 py-2 text-gray-500 font-mono text-xs">
                    {t.close_time ? new Date(t.close_time).toLocaleString() : '---'}
                  </td>
                  {showBotColumn && (
                    <td className="px-3 py-2 text-gray-200 font-mono text-xs">{t.bot_label}</td>
                  )}
                  <td className="px-3 py-2">
                    <span className={`text-xs font-bold ${t.side === 'long' ? 'text-green-400' : 'text-red-400'}`}>
                      {t.side?.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">{t.quantity}</td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">
                    {t.entry_price?.toLocaleString(undefined, { maximumFractionDigits: 8 })}
                  </td>
                  <td className="px-3 py-2 text-right text-white font-mono text-xs">
                    {t.close_price != null ? t.close_price.toLocaleString(undefined, { maximumFractionDigits: 8 }) : '---'}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono font-semibold text-xs ${pnlColor(t.realized_pnl ?? 0)}`}>
                    {fmtUsd(t.realized_pnl)}
                  </td>
                  <td className={`px-3 py-2 text-right font-mono text-xs ${pnlColor(t.realized_pnl ?? 0)}`}>
                    {t.realized_pnl_pct != null ? `${t.realized_pnl_pct >= 0 ? '+' : ''}${t.realized_pnl_pct.toFixed(2)}%` : '---'}
                  </td>
                  <td className="px-3 py-2">
                    <span className="text-xs text-gray-400">{t.close_reason || '---'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hasMore && !isLoading && (
        <div className="px-4 py-3 border-t border-gray-800 flex items-center justify-between">
          <span className="text-xs text-gray-500">Showing {trades.length} trades</span>
          <button
            type="button"
            onClick={loadMore}
            disabled={isLoadingMore}
            className="px-3 py-1.5 text-xs rounded bg-gray-800 border border-gray-700 text-gray-200 hover:bg-gray-700 disabled:opacity-60 inline-flex items-center gap-1.5"
          >
            {isLoadingMore && <Loader2 className="w-3 h-3 animate-spin" />}
            Load more
          </button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- TradeHistoryTable`
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/perpetuals/TradeHistoryTable.tsx frontend/__tests__/components/TradeHistoryTable.test.tsx
git commit -m "feat(agape-perps): TradeHistoryTable shared component

Range chips (7d/30d/90d/All/Custom), keyset Load-more pagination,
optional bot column for cross-bot views, server-side time sort,
loading/empty/error states.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Replace per-coin History tab on the all page

**Files:**
- Modify: `frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx:1755-1831`

The bot id slug used by the aggregator is *not* the same as the all-page's `CoinId`. Map them:

```ts
'ETH'->'eth', 'SOL'->'sol', 'AVAX'->'avax', 'BTC'->'btc', 'XRP'->'xrp',
'DOGE'->'doge', 'SHIB'->'shib_futures', 'LINK'->'link_futures',
'LTC'->'ltc_futures', 'BCH'->'bch_futures'
```

- [ ] **Step 1: Add the import and the slug map**

Open `frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx`. Near the other component imports (just below the `import PerpMarketCharts from '@/components/charts/PerpMarketCharts'` line ~31), add:

```ts
import { TradeHistoryTable } from '@/components/perpetuals/TradeHistoryTable'
```

Then near `ACTIVE_COINS` (line 173), add this map:

```ts
const COIN_TO_BOT_ID: Record<ActiveCoinId, string> = {
  ETH: 'eth', SOL: 'sol', AVAX: 'avax', BTC: 'btc', XRP: 'xrp',
  DOGE: 'doge', SHIB: 'shib_futures', LINK: 'link_futures',
  LTC: 'ltc_futures', BCH: 'bch_futures',
}
```

- [ ] **Step 2: Replace the `HistoryTab` body**

Find `function HistoryTab({ coin }: { coin: CoinId })` at line 1755. Replace the entire function (lines 1755 through the closing `}` at 1831) with:

```ts
function HistoryTab({ coin }: { coin: CoinId }) {
  const meta = COIN_META[coin]
  if (coin === 'ALL') return null
  const botId = COIN_TO_BOT_ID[coin as ActiveCoinId]
  return (
    <TradeHistoryTable
      bots={[botId]}
      showBotColumn={false}
      defaultRange="30d"
      title={`${meta.symbol} Trade History`}
    />
  )
}
```

The previous `usePerpClosedTrades(coin, 50)` call and inline table are no longer needed; do not delete the hook function `usePerpClosedTrades` from the file yet — Task 7 might still reference it indirectly via `AllCoinsRecentTrades`. We'll clean it up at the end of Task 7.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new type errors. (Pre-existing unrelated errors are tolerable; the diff should be clean.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx
git commit -m "feat(agape-perps): per-coin History tab uses TradeHistoryTable

Drops the hardcoded 50-row table; gets pagination + date range for free.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Replace the cross-bot Recent Trades feed on the all page

**Files:**
- Modify: `frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx:576-680`, also remove now-unused `usePerpClosedTrades` if no other caller exists.

- [ ] **Step 1: Replace `AllCoinsRecentTrades`**

Find `function AllCoinsRecentTrades()` at line 576. Replace the entire function (line 576 through the closing `}` at line 680) with:

```ts
function AllCoinsRecentTrades() {
  const allBotIds = ACTIVE_COINS.map(c => COIN_TO_BOT_ID[c])
  return (
    <TradeHistoryTable
      bots={allBotIds}
      showBotColumn
      defaultRange="30d"
      title="Recent Trades — All Bots"
    />
  )
}
```

- [ ] **Step 2: Remove the now-unused `usePerpClosedTrades` hook**

In the same file, search for `usePerpClosedTrades` references with `grep -n usePerpClosedTrades frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx`. There should be no remaining references after Tasks 6 and 7. Delete the hook definition (originally at line 238–241):

```ts
function usePerpClosedTrades(coin: CoinId, limit: number = 50) {
  const prefix = coin !== 'ALL' ? COIN_META[coin].apiPrefix : null
  return useSWR(prefix ? `${prefix}/closed-trades?limit=${limit}` : null, fetcher, { refreshInterval: 60_000 })
}
```

If `grep` finds remaining references, leave the hook in place and note the references in the commit message — do not silently break callers.

- [ ] **Step 3: Type-check + run frontend tests**

Run: `cd frontend && npx tsc --noEmit && npm test -- --testPathPattern='perpetuals'`
Expected: no new type errors; existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx
git commit -m "feat(agape-perps): cross-bot Recent Trades feed uses TradeHistoryTable

Replaces 10-route fan-out + 10-row truncation with the aggregator-backed
shared table. Removes now-unused usePerpClosedTrades helper.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Swap History tab on each per-bot page (10 files)

**Files:**
- Modify: `frontend/src/app/agape-eth-perp/page.tsx`, `agape-sol-perp/page.tsx`, `agape-avax-perp/page.tsx`, `agape-btc-perp/page.tsx`, `agape-xrp-perp/page.tsx`, `agape-doge-perp/page.tsx`, `agape-shib-futures/page.tsx`, `agape-link-futures/page.tsx`, `agape-ltc-futures/page.tsx`, `agape-bch-futures/page.tsx`

The change is the same shape per file: render `<TradeHistoryTable bots={['<bot_id>']} showBotColumn={false} defaultRange="30d" />` in the History tab, drop the `useAGAPE*ClosedTrades` call, and remove the local `HistoryTab` function. Per-file `bot_id` per the table at the top of this plan.

- [ ] **Step 1: Edit `agape-btc-perp/page.tsx` first as the canonical example**

Open `frontend/src/app/agape-btc-perp/page.tsx`. Add to the imports near `import EquityCurveChart from '@/components/charts/EquityCurveChart'`:

```ts
import { TradeHistoryTable } from '@/components/perpetuals/TradeHistoryTable'
```

Find this line at ~94:
```ts
const { data: closedData } = useAGAPEBtcPerpClosedTrades(50, { enabled: activeTab === 'history' })
```
Delete it.

Find this line at ~299:
```tsx
{activeTab === 'history' && <HistoryTab data={closedData?.data} brand={brand} />}
```
Replace with:
```tsx
{activeTab === 'history' && (
  <TradeHistoryTable bots={['btc']} showBotColumn={false} defaultRange="30d" title="BTC-PERP Trade History" />
)}
```

Find the local `function HistoryTab(...)` at ~873 (lines 870-940). Delete the entire function definition.

In the import block, remove `useAGAPEBtcPerpClosedTrades` from the named imports of `@/lib/hooks/useMarketData` (line 44). If `History` (icon) is no longer used elsewhere in this file, remove it too — check with grep first.

- [ ] **Step 2: Build + type-check this one page in isolation**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors related to `agape-btc-perp/page.tsx`.

- [ ] **Step 3: Apply the same shape to the other 9 per-bot pages**

For each file, the bot_id is fixed (see top of plan). The shape:
1. Add `import { TradeHistoryTable } from '@/components/perpetuals/TradeHistoryTable'`
2. Delete the `useAGAPE<X>ClosedTrades(...)` call
3. Replace `<HistoryTab data={closedData?.data} brand={brand} />` with `<TradeHistoryTable bots={['<bot_id>']} showBotColumn={false} defaultRange="30d" title="<DISPLAY> Trade History" />`
4. Delete the local `HistoryTab` function
5. Remove the now-unused hook import

  - [ ] `frontend/src/app/agape-eth-perp/page.tsx` → `bots={['eth']}`, title `"ETH-PERP Trade History"`
  - [ ] `frontend/src/app/agape-sol-perp/page.tsx` → `bots={['sol']}`
  - [ ] `frontend/src/app/agape-avax-perp/page.tsx` → `bots={['avax']}`
  - [ ] `frontend/src/app/agape-xrp-perp/page.tsx` → `bots={['xrp']}`
  - [ ] `frontend/src/app/agape-doge-perp/page.tsx` → `bots={['doge']}`
  - [ ] `frontend/src/app/agape-shib-futures/page.tsx` → `bots={['shib_futures']}`
  - [ ] `frontend/src/app/agape-link-futures/page.tsx` → `bots={['link_futures']}`
  - [ ] `frontend/src/app/agape-ltc-futures/page.tsx` → `bots={['ltc_futures']}`
  - [ ] `frontend/src/app/agape-bch-futures/page.tsx` → `bots={['bch_futures']}`

If a per-bot file's `HistoryTab` signature differs from BTC's (some take `closedTrades` instead of `data`, or `botName`), match the existing call site shape — the goal is the same final state, the diff details vary slightly.

- [ ] **Step 4: Type-check the whole frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/agape-*/page.tsx
git commit -m "feat(agape-perps): per-bot History tab uses TradeHistoryTable

All 10 per-bot pages now render the shared paginated, date-filtered
table instead of their hardcoded 50-row block.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Multi-bot performance comparison chart

### Task 9: `<MultiBotPerpEquityChart>` component

**Files:**
- Create: `frontend/src/components/perpetuals/MultiBotPerpEquityChart.tsx`
- Test: `frontend/__tests__/components/MultiBotPerpEquityChart.test.tsx`

The chart fans out to existing per-bot `/equity-curve?days=N` endpoints, normalizes client-side, and supports two modes plus a window selector and a per-bot legend toggle (persisted to localStorage).

- [ ] **Step 1: Write the failing tests for the normalization math**

Create `frontend/__tests__/components/MultiBotPerpEquityChart.test.tsx`:

```tsx
import { normalizeForChart } from '@/components/perpetuals/MultiBotPerpEquityChart'

const eth = {
  bot_id: 'eth', label: 'ETH-PERP', color: '#aaa',
  starting_capital: 10000,
  equity_curve: [
    { date: '2026-05-01', equity: 10000 },
    { date: '2026-05-02', equity: 10500 },
    { date: '2026-05-03', equity: 11000 },
  ],
}
const btc = {
  bot_id: 'btc', label: 'BTC-PERP', color: '#bbb',
  starting_capital: 25000,
  equity_curve: [
    { date: '2026-05-02', equity: 25000 },
    { date: '2026-05-03', equity: 26000 },
  ],
}

test('indexed mode: every visible bots first in-window point is 100', () => {
  const series = normalizeForChart([eth, btc], { mode: 'indexed', windowDays: 90 })
  expect(series.find(s => s.bot_id === 'eth')!.points[0].value).toBe(100)
  expect(series.find(s => s.bot_id === 'btc')!.points[0].value).toBe(100)
})

test('indexed mode: subsequent points scale by ratio', () => {
  const series = normalizeForChart([eth], { mode: 'indexed', windowDays: 90 })
  const ethSeries = series.find(s => s.bot_id === 'eth')!
  expect(ethSeries.points[1].value).toBeCloseTo(105, 5)
  expect(ethSeries.points[2].value).toBeCloseTo(110, 5)
})

test('percent mode: matches (equity - starting) / starting × 100', () => {
  const series = normalizeForChart([eth, btc], { mode: 'percent', windowDays: 90 })
  const ethSeries = series.find(s => s.bot_id === 'eth')!
  expect(ethSeries.points[2].value).toBeCloseTo(10, 5)
  const btcSeries = series.find(s => s.bot_id === 'btc')!
  expect(btcSeries.points[1].value).toBeCloseTo(4, 5)
})

test('bot with no in-window data is excluded from indexed series', () => {
  const orphan = {
    bot_id: 'old', label: 'OLD', color: '#ccc', starting_capital: 1000,
    equity_curve: [{ date: '2020-01-01', equity: 500 }],
  }
  const series = normalizeForChart([eth, orphan], { mode: 'indexed', windowDays: 30 })
  expect(series.find(s => s.bot_id === 'old')).toBeUndefined()
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- MultiBotPerpEquityChart`
Expected: FAIL with module-not-found.

- [ ] **Step 3: Implement the component**

Create `frontend/src/components/perpetuals/MultiBotPerpEquityChart.tsx`:

```tsx
'use client'

import { useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'
import { TrendingUp } from 'lucide-react'

const API = process.env.NEXT_PUBLIC_API_URL || ''

const fetcher = (url: string) => fetch(url).then(r => {
  if (!r.ok) throw new Error(`API error ${r.status}`)
  return r.json()
})

export type ChartBot = {
  bot_id: string
  label: string
  color: string
  apiPrefix: string
}

export type Mode = 'indexed' | 'percent'
export type WindowKey = '7d' | '30d' | '90d' | 'all'

const WINDOW_DAYS: Record<WindowKey, number> = { '7d': 7, '30d': 30, '90d': 90, 'all': 3650 }

type EquityCurvePoint = { date: string; equity: number }
type EquityCurveResponse = {
  data?: { equity_curve?: EquityCurvePoint[]; starting_capital?: number }
  equity_curve?: EquityCurvePoint[]
  starting_capital?: number
}

type SeriesInput = {
  bot_id: string
  label: string
  color?: string
  starting_capital: number
  equity_curve: EquityCurvePoint[]
}

type SeriesOutput = {
  bot_id: string
  label: string
  color: string
  points: { date: string; value: number }[]
}

const HIDDEN_KEY = 'agape-perp-chart-hidden-bots'

/**
 * Pure normalization helper, exported for testing.
 * - 'indexed' rebases each bot's first in-window point to 100.
 * - 'percent' computes (equity - starting_capital) / starting_capital * 100.
 * Bots with no in-window points are excluded.
 */
export function normalizeForChart(
  bots: SeriesInput[],
  opts: { mode: Mode; windowDays: number },
): SeriesOutput[] {
  const cutoff = Date.now() - opts.windowDays * 86_400_000
  const series: SeriesOutput[] = []
  for (const b of bots) {
    const inWindow = b.equity_curve.filter(p => new Date(p.date).getTime() >= cutoff)
    if (inWindow.length === 0) continue
    const color = b.color || '#888'
    if (opts.mode === 'indexed') {
      const base = inWindow[0].equity
      if (!base || base <= 0) continue
      series.push({
        bot_id: b.bot_id,
        label: b.label,
        color,
        points: inWindow.map(p => ({ date: p.date, value: (p.equity / base) * 100 })),
      })
    } else {
      const start = b.starting_capital
      if (!start || start <= 0) continue
      series.push({
        bot_id: b.bot_id,
        label: b.label,
        color,
        points: inWindow.map(p => ({ date: p.date, value: ((p.equity - start) / start) * 100 })),
      })
    }
  }
  return series
}

function useEquityCurves(bots: ChartBot[], days: number) {
  // Stable order of hooks: one useSWR per bot index.
  const responses = bots.map(b =>
    useSWR<EquityCurveResponse>(
      `${API}${b.apiPrefix}/equity-curve?days=${days}`,
      fetcher,
      { refreshInterval: 60_000, dedupingInterval: 30_000 },
    )
  )
  return responses
}

type Props = {
  bots: ChartBot[]
  defaultMode?: Mode
  defaultWindow?: WindowKey
  height?: number
}

export function MultiBotPerpEquityChart({
  bots,
  defaultMode = 'indexed',
  defaultWindow = '30d',
  height = 360,
}: Props) {
  const [mode, setMode] = useState<Mode>(defaultMode)
  const [windowKey, setWindowKey] = useState<WindowKey>(defaultWindow)
  const [hidden, setHidden] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set()
    try {
      const raw = window.localStorage.getItem(HIDDEN_KEY)
      return new Set(raw ? JSON.parse(raw) : [])
    } catch { return new Set() }
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    try { window.localStorage.setItem(HIDDEN_KEY, JSON.stringify(Array.from(hidden))) } catch {}
  }, [hidden])

  const days = WINDOW_DAYS[windowKey]
  const responses = useEquityCurves(bots, days)

  const inputs: SeriesInput[] = useMemo(() => bots.map((b, i) => {
    const r = responses[i].data
    const ec = r?.data?.equity_curve ?? r?.equity_curve ?? []
    const start = r?.data?.starting_capital ?? r?.starting_capital ?? 0
    return { bot_id: b.bot_id, label: b.label, color: b.color, starting_capital: start, equity_curve: ec }
  }), [bots, responses])

  const series = useMemo(
    () => normalizeForChart(inputs, { mode, windowDays: days }),
    [inputs, mode, days],
  )

  // Build a unified date axis: union of all visible-bot dates.
  const merged = useMemo(() => {
    const dates = new Set<string>()
    series.forEach(s => { if (!hidden.has(s.bot_id)) s.points.forEach(p => dates.add(p.date)) })
    const sortedDates = Array.from(dates).sort()
    return sortedDates.map(d => {
      const row: Record<string, any> = { date: d }
      series.forEach(s => {
        if (hidden.has(s.bot_id)) return
        const pt = s.points.find(p => p.date === d)
        row[s.bot_id] = pt ? pt.value : null
      })
      return row
    })
  }, [series, hidden])

  const isLoading = responses.some(r => r.isLoading)

  function toggleBot(bot_id: string) {
    setHidden(h => {
      const next = new Set(h)
      if (next.has(bot_id)) next.delete(bot_id); else next.add(bot_id)
      return next
    })
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800">
      <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-800 flex-wrap">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-cyan-400" />
          <h3 className="text-sm font-medium text-gray-200">Bot Performance Comparison</h3>
          <span className="text-xs text-gray-500">{mode === 'indexed' ? 'Indexed (100 = window start)' : '% from inception'}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1">
            {(['7d','30d','90d','all'] as WindowKey[]).map(w => (
              <button
                key={w}
                type="button"
                onClick={() => setWindowKey(w)}
                className={`px-2 py-1 text-xs rounded border ${
                  windowKey === w ? 'bg-cyan-600/30 border-cyan-500 text-cyan-200' : 'border-gray-700 text-gray-400 hover:bg-gray-800'
                }`}
              >
                {w === 'all' ? 'All' : w}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMode('indexed')}
              className={`px-2 py-1 text-xs rounded border ${
                mode === 'indexed' ? 'bg-fuchsia-600/30 border-fuchsia-500 text-fuchsia-200' : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              }`}
            >
              Indexed
            </button>
            <button
              type="button"
              onClick={() => setMode('percent')}
              className={`px-2 py-1 text-xs rounded border ${
                mode === 'percent' ? 'bg-fuchsia-600/30 border-fuchsia-500 text-fuchsia-200' : 'border-gray-700 text-gray-400 hover:bg-gray-800'
              }`}
            >
              % from inception
            </button>
          </div>
        </div>
      </div>

      <div className="p-4">
        {isLoading && merged.length === 0 ? (
          <div className="text-gray-500 text-sm text-center py-12">Loading equity curves…</div>
        ) : (
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={merged} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
              <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#6b7280" tick={{ fontSize: 11 }} />
              <YAxis stroke="#6b7280" tick={{ fontSize: 11 }}
                tickFormatter={(v) => mode === 'indexed' ? `${v.toFixed(0)}` : `${v.toFixed(1)}%`} />
              <Tooltip
                contentStyle={{ background: '#0b1020', border: '1px solid #1f2937', fontSize: 12 }}
                formatter={(v: any) => mode === 'indexed' ? `${Number(v).toFixed(2)}` : `${Number(v).toFixed(2)}%`}
              />
              <Legend
                onClick={(e: any) => toggleBot(e.dataKey)}
                wrapperStyle={{ fontSize: 12, cursor: 'pointer' }}
              />
              {series.map(s => (
                <Line
                  key={s.bot_id}
                  type="monotone"
                  dataKey={s.bot_id}
                  name={s.label}
                  stroke={s.color}
                  dot={false}
                  strokeWidth={2}
                  hide={hidden.has(s.bot_id)}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- MultiBotPerpEquityChart`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/perpetuals/MultiBotPerpEquityChart.tsx frontend/__tests__/components/MultiBotPerpEquityChart.test.tsx
git commit -m "feat(agape-perps): MultiBotPerpEquityChart with indexed-100 normalization

Recharts line chart, 7d/30d/90d/all window selector, Indexed (default)
↔ % from inception toggle, click-to-hide legend persisted to
localStorage. No backend changes — fans out to existing per-bot
/equity-curve endpoints.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Place the chart on the perpetuals-crypto all page

**Files:**
- Modify: `frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx`

The chart goes in the all-coins overview section, above the `AllCoinsRecentTrades` and below the portfolio summary card.

- [ ] **Step 1: Add the import**

Open `PerpetualsCryptoContent.tsx`. Add to the component imports:

```ts
import { MultiBotPerpEquityChart, type ChartBot } from '@/components/perpetuals/MultiBotPerpEquityChart'
```

- [ ] **Step 2: Build the chart bot list from COIN_META**

Near where `COIN_TO_BOT_ID` was added (Task 6, after `ACTIVE_COINS`), add:

```ts
const CHART_BOTS: ChartBot[] = ACTIVE_COINS.map(c => ({
  bot_id: COIN_TO_BOT_ID[c],
  label: COIN_META[c].instrument,
  color: COIN_META[c].hexColor,
  apiPrefix: COIN_META[c].apiPrefix,
}))
```

- [ ] **Step 3: Render the chart in the all-coins overview**

Find the line `<AllCoinsRecentTrades />` (originally line 571 in the all-coins overview). Insert above it:

```tsx
<MultiBotPerpEquityChart bots={CHART_BOTS} defaultMode="indexed" defaultWindow="30d" />
```

- [ ] **Step 4: Build the frontend**

Run: `cd frontend && npx next build 2>&1 | tee /tmp/perps-build.log`
Expected: build succeeds. If there's a Recharts type complaint about `hide` or `connectNulls`, narrow with `as any` only on those props — do not loosen the rest of the surface.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/perpetuals-crypto/PerpetualsCryptoContent.tsx
git commit -m "feat(agape-perps): place MultiBotPerpEquityChart on /perpetuals-crypto

Indexed-to-100 by default with a toggle to % from inception. Sits in
the all-coins overview between the portfolio summary and the cross-bot
Recent Trades feed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Verification & merge

### Task 11: End-to-end verification

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest -q`
Expected: PASS. If unrelated pre-existing failures appear, they are out of scope — note them in the merge commit but do not block the merge unless they were green before this branch.

- [ ] **Step 2: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npx next build 2>&1 | tee /tmp/perps-build-final.log`
Expected: succeeds. If standalone build fails, see common-mistakes section 4 (TypeScript build failures) and section 20 (deployment/standalone).

- [ ] **Step 4: Smoke the aggregator endpoint locally**

Start the backend (`cd backend && uvicorn main:app --reload`) and check:

```bash
curl -s "http://localhost:8000/api/agape-perpetuals/trades?bots=*&limit=3" | python -m json.tool | head -40
```
Expected: JSON with `trades`, `has_more`, `next_cursor`, `window`. Sanity: trades sorted by `close_time` descending, `bot_id` populated, `realized_pnl_pct` populated.

If a bot has zero closed trades, the empty array is fine — the endpoint must not 500.

- [ ] **Step 5: Smoke the UI locally**

Start the frontend (`cd frontend && npm run dev`) and:

1. Open `/perpetuals-crypto` (the all page). Verify the new comparison chart shows lines for each active bot in indexed mode; switch to "% from inception" and back; switch the window between 7d/30d/90d/All.
2. Verify the "Recent Trades — All Bots" section appears with a Bot column and a 30d default range; click "Load more" once and confirm older rows append.
3. Switch to a single coin (e.g. BTC) and click the History tab; verify the same paginated table renders without a Bot column.
4. Open `/agape-btc-perp`, click the History tab, and confirm the shared table renders.
5. Repeat (4) for two other bot pages chosen from `agape-eth-perp` and `agape-shib-futures` (one perp, one futures) to confirm both endpoint slug families work.

If any UI smoke step fails, fix forward — do not roll back the branch.

- [ ] **Step 6: Commit any verification fixups**

If steps 1–5 surface issues that you fixed, commit them on this branch with a `fix(agape-perps): …` message before merging.

---

### Task 12: Merge to `main`

Per `CLAUDE.md` "Branch Merge Policy": once verified, merge proactively without per-merge approval. Render auto-deploys `main`, so the merge is the deploy.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin spec/agape-derivatives-trade-history-and-perf-chart
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "Agape Derivatives: full trade history + normalized perf chart" --body "$(cat <<'EOF'
## Summary
- New `/api/agape-perpetuals/trades` aggregator with keyset cursor + date filters; 10 per-bot `db.get_closed_trades` extended with `since`/`until`/`before` kwargs.
- Shared `<TradeHistoryTable>` replaces hardcoded 50/10-row tables on the all page (cross-bot feed + per-coin tab) and on each of the 10 per-bot pages — default 30-day window with `Load more` and a custom date range.
- New `<MultiBotPerpEquityChart>` on `/perpetuals-crypto`: indexed-to-100 default, `% from inception` toggle, 7d/30d/90d/All window selector, click-to-hide legend.

## Test plan
- [x] Backend pytest (`tests/test_agape_perp_db_filters.py`, `backend/tests/test_agape_perpetuals_trades_routes.py`) green.
- [x] Frontend Jest tests for hook, `TradeHistoryTable`, and chart normalization green.
- [x] `npx next build` succeeds.
- [x] Smoke: aggregator endpoint returns merged trades on local backend.
- [x] Smoke: all page chart, both feeds, and per-bot history pages render in `npm run dev`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Merge**

After CI passes:
```bash
gh pr merge --squash --delete-branch
```

- [ ] **Step 4: Verify Render deploy**

Open Render dashboard or run `mcp__render__list_deploys` for `alphagex-api` and confirm the deploy succeeds. Hit production: `curl -s "https://alphagex-api.onrender.com/api/agape-perpetuals/trades?bots=*&limit=2"` and confirm a 200.
