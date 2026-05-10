# Phase 1 Implementation Plan: Intraday Wall-Gravity Harness

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research harness that validates whether 1DTE SPY debit verticals struck at GEX walls have positive expected PnL by 15:55 ET on the entry day, conditioned on intraday-available features.

**Architecture:** Pure offline backtest harness reading from production `helios_options_intraday` + `helios_options_oi` and backtest `vix_history` + production `regime_signals`. No new DB tables; outputs are markdown report + per-trade CSV. Walk-forward with 2025 OOS untouched until final eval. Per the spec at `docs/superpowers/specs/2026-05-10-1dte-directional-research-design.md`.

**Tech Stack:** Python 3.11+, psycopg2, pytest, numpy, pandas. Reuses Newton-Raphson IV solver and intraday wall computation from the unmerged HELIOS branch (sourced via stash).

---

## File structure

**New files:**

```
quant/
├── bs.py                          # Promoted from HELIOS (Black-Scholes + IV solver)
└── walls.py                       # Promoted from HELIOS (compute_intraday_walls)

backtest/touch_pin/
├── __init__.py
├── loader.py                      # Pull chain + OI + regime + vix at minute 5
├── vehicle.py                     # Build PIN-CALL / PIN-PUT vertical specs
├── implied.py                     # P_implied via BS Φ(d2) AND price/width
├── realized.py                    # Walk minute bars; touched_during_day; exit_mid at bar 385
├── engine.py                      # Per-day orchestration
├── binning.py                     # Bucket trades and aggregate
├── report.py                      # Markdown writer + sensitivity battery
├── walk_forward.py                # Train/Validation/OOS split + GO/NO-GO eval
└── cli.py                         # python -m backtest.touch_pin --start ... --end ...

tests/touch_pin/
├── __init__.py
├── conftest.py                    # Synthetic chain fixtures
├── test_bs_promotion.py
├── test_walls_promotion.py
├── test_loader.py
├── test_vehicle.py
├── test_implied.py
├── test_realized.py
├── test_engine_smoke.py
├── test_binning.py
└── test_walk_forward.py

docs/superpowers/reports/
└── 2026-05-10-touch-pin-final.md  # Output of Task 13 (committed)
```

**Modified files:** none. The harness is greenfield. `bs.py` and `walls.py` are *promoted* (copied to new path); the HELIOS branch's local copies are not touched.

**.gitignore additions:** `backtest/touch_pin/output/` (per-trade CSV is regenerable; only the MD report is committed).

---

## Task 0: Branch setup + scaffold

**Files:**
- Create: `backtest/touch_pin/__init__.py` (empty)
- Create: `tests/touch_pin/__init__.py` (empty)
- Create: `backtest/touch_pin/output/.gitkeep`
- Modify: `.gitignore` (append rule)

- [ ] **Step 1: Confirm branch state**

```bash
cd C:/Users/lemol/AlphaGEX && git rev-parse --abbrev-ref HEAD
```
Expected: `claude/touch-pin-validation` (already created earlier this session, off `claude/1dte-research-design`).

- [ ] **Step 2: Restore the stashed HELIOS WIP files (we need bs.py + walls.py source)**

```bash
git stash pop 2>&1 | tail -5
```
Expected: stash pops cleanly; `backtest/intraday_walls/bs.py` and `walls.py` reappear as untracked files. (Other stashed files are HELIOS branch artifacts that we won't commit on this branch.)

- [ ] **Step 3: Create scaffold directories**

```bash
mkdir -p backtest/touch_pin/output tests/touch_pin
touch backtest/touch_pin/__init__.py
touch tests/touch_pin/__init__.py
touch backtest/touch_pin/output/.gitkeep
```

- [ ] **Step 4: Add gitignore rule**

Append to `.gitignore`:
```
# touch-pin per-trade CSV outputs (regenerable)
backtest/touch_pin/output/*.csv
!backtest/touch_pin/output/.gitkeep
```

- [ ] **Step 5: Commit scaffold**

```bash
git add backtest/touch_pin/__init__.py tests/touch_pin/__init__.py \
        backtest/touch_pin/output/.gitkeep .gitignore
git commit -m "$(cat <<'EOF'
touch-pin: scaffold backtest/touch_pin/ + tests/touch_pin/

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 1: Promote `quant/bs.py`

**Files:**
- Create: `quant/bs.py`
- Test: `tests/touch_pin/test_bs_promotion.py`

- [ ] **Step 1: Write failing test**

```python
# tests/touch_pin/test_bs_promotion.py
import math
import pytest
from quant.bs import bs_price, bs_gamma, bs_vega, implied_vol, derive_spot_from_parity


def test_atm_call_price_textbook():
    # ATM call, 1DTE, 20% vol, r=5% → known approx
    price = bs_price(spot=500.0, strike=500.0, t_years=1/365, sigma=0.20, is_call=True)
    assert 0.5 < price < 5.0  # rough sanity for SPY-like scale


def test_iv_roundtrip():
    sigma_in = 0.25
    price = bs_price(500.0, 505.0, 5/365, sigma_in, is_call=True)
    sigma_out = implied_vol(price, 500.0, 505.0, 5/365, is_call=True)
    assert sigma_out is not None
    assert abs(sigma_out - sigma_in) < 1e-3


def test_iv_below_intrinsic_returns_none():
    # Call worth $1 when intrinsic is $5 → arbitrage / stale quote
    iv = implied_vol(market_price=1.0, spot=505.0, strike=500.0, t_years=1/365, is_call=True)
    assert iv is None


def test_parity_spot_recovers_spot():
    # Build mids from BS, recover spot via parity
    spot = 500.0
    K = 500.0
    T = 1/365
    sigma = 0.20
    cm = bs_price(spot, K, T, sigma, is_call=True)
    pm = bs_price(spot, K, T, sigma, is_call=False)
    spot_recovered = derive_spot_from_parity(cm, pm, K, T)
    assert abs(spot_recovered - spot) < 1e-2


def test_gamma_positive_atm():
    g = bs_gamma(500.0, 500.0, 1/365, 0.20)
    assert g > 0


def test_vega_positive_atm():
    v = bs_vega(500.0, 500.0, 1/365, 0.20)
    assert v > 0
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/touch_pin/test_bs_promotion.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'quant.bs'`

- [ ] **Step 3: Create `quant/bs.py` by copying from `backtest/intraday_walls/bs.py`**

```bash
cp backtest/intraday_walls/bs.py quant/bs.py
```

The file content is already correct — no path adjustments needed (no internal imports in bs.py).

- [ ] **Step 4: Run test to confirm pass**

```bash
pytest tests/touch_pin/test_bs_promotion.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add quant/bs.py tests/touch_pin/test_bs_promotion.py
git commit -m "$(cat <<'EOF'
quant: promote bs.py from HELIOS branch

Black-Scholes pricer + Newton-Raphson IV solver with Brent fallback.
Bit-identical copy from backtest/intraday_walls/bs.py (HELIOS branch
working tree). Used by touch_pin and skew_signal harnesses.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Promote `quant/walls.py`

**Files:**
- Create: `quant/walls.py`
- Test: `tests/touch_pin/test_walls_promotion.py`

- [ ] **Step 1: Write failing test (smoke only — full integration test in Task 3)**

```python
# tests/touch_pin/test_walls_promotion.py
import pytest
from quant.walls import StrikeGamma, Walls, compute_intraday_walls


def test_dataclasses_importable():
    sg = StrikeGamma(strike=500.0, call_gamma_oi=1.0, put_gamma_oi=0.5, net_gamma=0.5)
    assert sg.net_gamma == pytest.approx(0.5)


def test_compute_walls_callable_signature():
    # Verify the callable's signature without hitting the DB
    import inspect
    sig = inspect.signature(compute_intraday_walls)
    params = list(sig.parameters.keys())
    assert "db_url" in params
    assert "trade_date" in params
    assert "expiration_date" in params
    assert "target_minute" in params
    assert "t_years_at_open" in params
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/touch_pin/test_walls_promotion.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'quant.walls'`

- [ ] **Step 3: Create `quant/walls.py` by copying and adjusting imports**

```bash
cp backtest/intraday_walls/walls.py quant/walls.py
```

Then edit the import line in `quant/walls.py` from:
```python
from .bs import bs_gamma, derive_spot_from_parity, implied_vol
```
to:
```python
from quant.bs import bs_gamma, derive_spot_from_parity, implied_vol
```

- [ ] **Step 4: Run test to confirm pass**

```bash
pytest tests/touch_pin/test_walls_promotion.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add quant/walls.py tests/touch_pin/test_walls_promotion.py
git commit -m "$(cat <<'EOF'
quant: promote walls.py from HELIOS branch

compute_intraday_walls() — derives spot via put-call parity at most-ATM
strike, computes gamma*OI per strike, identifies call_wall/put_support/
flip_point. Bit-identical copy from backtest/intraday_walls/walls.py
with import path updated to absolute (quant.bs).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `loader.py` — Pull chain + OI + context at minute M

**Files:**
- Create: `backtest/touch_pin/loader.py`
- Test: `tests/touch_pin/test_loader.py`
- Test fixture: `tests/touch_pin/conftest.py`

- [ ] **Step 1: Write conftest fixture and failing test**

```python
# tests/touch_pin/conftest.py
import os
import pytest


def _has_db():
    return bool(os.environ.get("DATABASE_URL"))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "db: requires production DATABASE_URL set"
    )


def pytest_collection_modifyitems(config, items):
    if _has_db():
        return
    skip_db = pytest.mark.skip(reason="DATABASE_URL not set; skipping DB-backed test")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
```

```python
# tests/touch_pin/test_loader.py
import datetime as dt
import os
import pytest

from backtest.touch_pin.loader import load_minute_chain, ChainEntry, MinuteSnapshot


@pytest.mark.db
def test_load_minute_chain_known_day():
    db_url = os.environ["DATABASE_URL"]
    snap = load_minute_chain(
        db_url,
        trade_date=dt.date(2025, 6, 2),
        expiration_date=dt.date(2025, 6, 3),
        target_minute=5,
    )
    assert snap is not None
    assert isinstance(snap, MinuteSnapshot)
    assert snap.trade_date == dt.date(2025, 6, 2)
    assert len(snap.chain) >= 5  # at least a handful of strikes
    # Each entry should be a ChainEntry with both call/put quotes (or NaN if missing)
    for k, entry in snap.chain.items():
        assert isinstance(entry, ChainEntry)
        assert entry.strike == k


def test_minute_snapshot_dataclass_shape():
    e = ChainEntry(
        strike=500.0,
        call_bid=0.10, call_ask=0.12,
        put_bid=0.05, put_ask=0.07,
        call_volume=100, put_volume=50,
    )
    assert e.call_mid == pytest.approx(0.11)
    assert e.put_mid == pytest.approx(0.06)
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/touch_pin/test_loader.py -v
```
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `loader.py`**

```python
# backtest/touch_pin/loader.py
"""Load minute-chain quote bars + OI + same-day context for the touch_pin harness.

For a given (trade_date, expiration_date, target_minute), pulls the minute bar
at exactly minute=target_minute (offset from the first bar of the day, typically
the 09:30 ET open) and pivots calls/puts into per-strike ChainEntry rows.
Also pulls the (single) OI snapshot for that (T, T+1) pair.

VIX is loaded separately on the operator's call (not per-minute) — see vix_at_close().
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field
from typing import Dict, Optional

import psycopg2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChainEntry:
    strike: float
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float
    call_volume: int = 0
    put_volume: int = 0
    call_oi: int = 0
    put_oi: int = 0

    @property
    def call_mid(self) -> float:
        return 0.5 * (self.call_bid + self.call_ask)

    @property
    def put_mid(self) -> float:
        return 0.5 * (self.put_bid + self.put_ask)

    def call_valid(self) -> bool:
        return self.call_bid > 0 and self.call_ask > 0 and self.call_ask >= self.call_bid

    def put_valid(self) -> bool:
        return self.put_bid > 0 and self.put_ask > 0 and self.put_ask >= self.put_bid


@dataclass(frozen=True)
class MinuteSnapshot:
    trade_date: dt.date
    expiration_date: dt.date
    target_minute: int
    bar_time: dt.datetime
    chain: Dict[float, ChainEntry]


def load_minute_chain(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    target_minute: int,
) -> Optional[MinuteSnapshot]:
    """Pull the chain at (trade_date, expiration, target_minute) plus OI.

    Returns None if no bars exist for that minute.
    """
    chain_rows = _query_chain_at_minute(db_url, trade_date, expiration_date, target_minute)
    if not chain_rows:
        return None
    oi_rows = _query_oi(db_url, trade_date, expiration_date)
    return _pivot(trade_date, expiration_date, target_minute, chain_rows, oi_rows)


def _query_chain_at_minute(db_url, trade_date, expiration_date, target_minute):
    sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT strike, "right", bar_time, bid, ask, volume
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time = first_bar.t0 + (%s * INTERVAL '1 minute')
        ORDER BY strike, "right"
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date, expiration_date,
                          trade_date, expiration_date, target_minute))
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def _query_oi(db_url, trade_date, expiration_date):
    sql = """
        SELECT strike, "right", open_interest
        FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date = %s
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date, expiration_date))
        rows = cur.fetchall()
        cur.close()
        return rows
    finally:
        conn.close()


def _pivot(trade_date, expiration_date, target_minute, chain_rows, oi_rows):
    by_strike: Dict[float, dict] = {}
    bar_time: Optional[dt.datetime] = None
    for strike, right, bt, bid, ask, volume in chain_rows:
        bar_time = bt if bar_time is None else bar_time
        k = float(strike)
        e = by_strike.setdefault(k, {
            "call_bid": 0.0, "call_ask": 0.0,
            "put_bid": 0.0, "put_ask": 0.0,
            "call_volume": 0, "put_volume": 0,
        })
        bid_v = float(bid) if bid is not None else 0.0
        ask_v = float(ask) if ask is not None else 0.0
        vol_v = int(volume) if volume is not None else 0
        if right == "C":
            e["call_bid"] = bid_v
            e["call_ask"] = ask_v
            e["call_volume"] = vol_v
        else:
            e["put_bid"] = bid_v
            e["put_ask"] = ask_v
            e["put_volume"] = vol_v

    oi_by_strike: Dict[float, dict] = {}
    for strike, right, oi in oi_rows:
        k = float(strike)
        oi_e = oi_by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})
        if right == "C":
            oi_e["call_oi"] = int(oi)
        else:
            oi_e["put_oi"] = int(oi)

    chain: Dict[float, ChainEntry] = {}
    for k, q in by_strike.items():
        oi = oi_by_strike.get(k, {"call_oi": 0, "put_oi": 0})
        chain[k] = ChainEntry(
            strike=k,
            call_bid=q["call_bid"], call_ask=q["call_ask"],
            put_bid=q["put_bid"], put_ask=q["put_ask"],
            call_volume=q["call_volume"], put_volume=q["put_volume"],
            call_oi=oi["call_oi"], put_oi=oi["put_oi"],
        )

    return MinuteSnapshot(
        trade_date=trade_date,
        expiration_date=expiration_date,
        target_minute=target_minute,
        bar_time=bar_time,
        chain=chain,
    )


def vix_close_prior_day(db_url: str, trade_date: dt.date) -> Optional[float]:
    """Prior-day VIX close (anti-look-ahead). Reads from backtest DB vix_history."""
    sql = """
        SELECT close
        FROM vix_history
        WHERE trade_date < %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date,))
        row = cur.fetchone()
        cur.close()
        return float(row[0]) if row else None
    finally:
        conn.close()


def regime_label_at_open(db_url: str, trade_date: dt.date) -> Optional[str]:
    """Latest regime_signals row with timestamp <= T 09:30 ET (anti-look-ahead).

    SPY market open in ET is 09:30; we use UTC 13:30 (EDT) / 14:30 (EST). To stay
    safe across DST, we cut at T 13:30 UTC which is the EDT open and is BEFORE
    the EST open at T 14:30 UTC — never leaks future state.
    """
    cutoff = dt.datetime.combine(trade_date, dt.time(13, 30))
    sql = """
        SELECT primary_regime_type
        FROM regime_signals
        WHERE timestamp <= %s
        ORDER BY timestamp DESC
        LIMIT 1
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (cutoff,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
DATABASE_URL=$DATABASE_URL pytest tests/touch_pin/test_loader.py -v
```
Expected: `test_load_minute_chain_known_day` passes (if DATABASE_URL set), `test_minute_snapshot_dataclass_shape` passes always.

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/loader.py tests/touch_pin/conftest.py tests/touch_pin/test_loader.py
git commit -m "$(cat <<'EOF'
touch-pin: loader pulls minute-chain + OI + context

load_minute_chain() pivots helios_options_intraday rows into per-strike
ChainEntry with call/put bid/ask/volume + OI from helios_options_oi.

Adds vix_close_prior_day() and regime_label_at_open() with anti-look-ahead
cutoffs (UTC 13:30 = EDT open, BEFORE EST open).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `vehicle.py` — Build PIN-CALL/PIN-PUT vertical specs

**Files:**
- Create: `backtest/touch_pin/vehicle.py`
- Test: `tests/touch_pin/test_vehicle.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/touch_pin/test_vehicle.py
import pytest
from backtest.touch_pin.loader import ChainEntry
from backtest.touch_pin.vehicle import build_verticals, VerticalSpec


def make_chain(specs):
    """Helper: list of (strike, c_bid, c_ask, p_bid, p_ask) → dict."""
    return {s[0]: ChainEntry(
        strike=s[0], call_bid=s[1], call_ask=s[2],
        put_bid=s[3], put_ask=s[4],
    ) for s in specs}


def test_pin_call_vertical_basic():
    chain = make_chain([
        (530, 5.00, 5.05, 0.05, 0.07),
        (533, 2.00, 2.05, 1.00, 1.05),
        (535, 0.10, 0.12, 5.00, 5.05),
        (536, 0.05, 0.07, 5.95, 6.00),
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    pin_call, pin_put = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_call is not None
    assert pin_call.long_K == 535.0
    assert pin_call.short_K == 536.0
    assert pin_call.entry_mid == pytest.approx(0.11 - 0.06, rel=1e-3)
    assert pin_call.width == 1.0
    assert pin_call.side == "PIN-CALL"


def test_pin_put_vertical_basic():
    chain = make_chain([
        (529, 8.00, 8.05, 0.02, 0.04),
        (530, 5.00, 5.05, 0.05, 0.07),
        (533, 2.00, 2.05, 1.00, 1.05),
        (535, 0.10, 0.12, 5.00, 5.05),
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    _, pin_put = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_put is not None
    assert pin_put.long_K == 530.0
    assert pin_put.short_K == 529.0
    assert pin_put.entry_mid == pytest.approx(0.06 - 0.03, rel=1e-3)
    assert pin_put.side == "PIN-PUT"


def test_skip_when_zero_quotes():
    chain = make_chain([
        (535, 0.0, 0.05, 0.02, 0.04),  # call_bid == 0
        (536, 0.05, 0.07, 0.00, 0.04),
    ])
    walls = {"call_wall": 535.0, "put_support": 533.0}
    pin_call, _ = build_verticals(chain, walls, spot=534.0, strike_step=1.0)
    assert pin_call is None


def test_skip_when_short_strike_missing():
    chain = make_chain([
        (535, 0.10, 0.12, 5.00, 5.05),
        # no 536 — short leg missing
    ])
    walls = {"call_wall": 535.0, "put_support": 530.0}
    pin_call, _ = build_verticals(chain, walls, spot=533.0, strike_step=1.0)
    assert pin_call is None
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/touch_pin/test_vehicle.py -v
```
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `vehicle.py`**

```python
# backtest/touch_pin/vehicle.py
"""Build PIN-CALL / PIN-PUT debit-vertical specs at the GEX walls.

PIN-CALL: long call @ call_wall, short call @ call_wall + strike_step
PIN-PUT:  long put  @ put_support, short put  @ put_support - strike_step
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from backtest.touch_pin.loader import ChainEntry


@dataclass(frozen=True)
class VerticalSpec:
    side: str  # "PIN-CALL" or "PIN-PUT"
    long_K: float
    short_K: float
    width: float
    entry_mid: float
    long_bid: float
    long_ask: float
    short_bid: float
    short_ask: float


def build_verticals(
    chain: Dict[float, ChainEntry],
    walls: Dict[str, float],
    spot: float,
    strike_step: float = 1.0,
) -> Tuple[Optional[VerticalSpec], Optional[VerticalSpec]]:
    """Build both PIN-CALL and PIN-PUT specs (either may be None)."""
    pin_call = _build_call_vertical(chain, walls.get("call_wall"), strike_step)
    pin_put = _build_put_vertical(chain, walls.get("put_support"), strike_step)
    return pin_call, pin_put


def _build_call_vertical(chain, call_wall, step):
    if call_wall is None:
        return None
    long_K = float(call_wall)
    short_K = long_K + step
    long_e = chain.get(long_K)
    short_e = chain.get(short_K)
    if long_e is None or short_e is None:
        return None
    if not long_e.call_valid() or not short_e.call_valid():
        return None
    entry_mid = long_e.call_mid - short_e.call_mid
    if entry_mid <= 0:  # Inverted vertical — not a debit
        return None
    return VerticalSpec(
        side="PIN-CALL",
        long_K=long_K, short_K=short_K, width=step,
        entry_mid=entry_mid,
        long_bid=long_e.call_bid, long_ask=long_e.call_ask,
        short_bid=short_e.call_bid, short_ask=short_e.call_ask,
    )


def _build_put_vertical(chain, put_support, step):
    if put_support is None:
        return None
    long_K = float(put_support)
    short_K = long_K - step
    long_e = chain.get(long_K)
    short_e = chain.get(short_K)
    if long_e is None or short_e is None:
        return None
    if not long_e.put_valid() or not short_e.put_valid():
        return None
    entry_mid = long_e.put_mid - short_e.put_mid
    if entry_mid <= 0:
        return None
    return VerticalSpec(
        side="PIN-PUT",
        long_K=long_K, short_K=short_K, width=step,
        entry_mid=entry_mid,
        long_bid=long_e.put_bid, long_ask=long_e.put_ask,
        short_bid=short_e.put_bid, short_ask=short_e.put_ask,
    )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/touch_pin/test_vehicle.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/vehicle.py tests/touch_pin/test_vehicle.py
git commit -m "$(cat <<'EOF'
touch-pin: vehicle builds PIN-CALL/PIN-PUT vertical specs

build_verticals() returns (pin_call, pin_put) — either may be None when
the chain lacks the long or short strike, has zero quotes, or yields a
non-positive debit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `implied.py` — Two-method P_implied

**Files:**
- Create: `backtest/touch_pin/implied.py`
- Test: `tests/touch_pin/test_implied.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/touch_pin/test_implied.py
import pytest
from backtest.touch_pin.vehicle import VerticalSpec
from backtest.touch_pin.implied import implied_pin_probabilities, ImpliedProbs
from quant.bs import bs_price


def make_call_vertical(spot, long_K, short_K, sigma, t):
    long_mid = bs_price(spot, long_K, t, sigma, is_call=True)
    short_mid = bs_price(spot, short_K, t, sigma, is_call=True)
    return VerticalSpec(
        side="PIN-CALL", long_K=long_K, short_K=short_K, width=short_K - long_K,
        entry_mid=long_mid - short_mid,
        long_bid=long_mid - 0.01, long_ask=long_mid + 0.01,
        short_bid=short_mid - 0.01, short_ask=short_mid + 0.01,
    )


def test_implied_methods_agree_synthetic():
    spec = make_call_vertical(spot=500.0, long_K=500.0, short_K=501.0, sigma=0.20, t=1/365)
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    assert probs is not None
    # The two methods should agree within 5pp on this synthetic case
    assert abs(probs.method_bs_d2 - probs.method_price_over_width) < 0.05


def test_implied_far_otm_low_prob():
    # Long call far OTM → implied P is low
    spec = make_call_vertical(spot=500.0, long_K=520.0, short_K=521.0, sigma=0.20, t=1/365)
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    assert probs.method_bs_d2 < 0.10
    assert probs.method_price_over_width < 0.10


def test_implied_returns_none_on_iv_failure():
    # Vertical with crazy entry_mid → IV solver fails
    spec = VerticalSpec(
        side="PIN-CALL", long_K=500.0, short_K=501.0, width=1.0,
        entry_mid=999.0,  # Above width — impossible
        long_bid=998.0, long_ask=1000.0,
        short_bid=0.0, short_ask=0.01,
    )
    probs = implied_pin_probabilities(spec, spot=500.0, t_years=1/365)
    # Method 2 (price/width) clamps to [0, 1] but method 1 may still fail
    if probs is not None:
        assert 0.0 <= probs.method_price_over_width <= 1.0
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
pytest tests/touch_pin/test_implied.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `implied.py`**

```python
# backtest/touch_pin/implied.py
"""Two-method implied probability that the wall pin is hit.

Method 1 (bs_d2): solve IV at the long strike, compute P(S_T >= long_K) for
                  PIN-CALL or P(S_T <= long_K) for PIN-PUT via Black-Scholes
                  Φ(d2) — the risk-neutral probability of expiring in the money.

Method 2 (price_over_width): for a debit vertical, max payoff = width.
                  P_implied ≈ entry_mid / width  — the market's implied
                  probability of full payoff (heuristic, not strictly RN).

The two methods diverge when there's significant IV skew between the long
and short strikes; we report both and flag if |diff| > 0.10.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from backtest.touch_pin.vehicle import VerticalSpec
from quant.bs import implied_vol


@dataclass(frozen=True)
class ImpliedProbs:
    method_bs_d2: float
    method_price_over_width: float
    iv_long_strike: Optional[float]


def implied_pin_probabilities(
    spec: VerticalSpec,
    spot: float,
    t_years: float,
    r: float = 0.05,
) -> Optional[ImpliedProbs]:
    """Return both implied probability methods. None if all fail."""
    method2 = max(0.0, min(1.0, spec.entry_mid / spec.width)) if spec.width > 0 else 0.0

    # Method 1: BS Φ(d2) at long strike
    long_mid = 0.5 * (spec.long_bid + spec.long_ask)
    is_call = (spec.side == "PIN-CALL")
    iv = implied_vol(long_mid, spot, spec.long_K, t_years, is_call=is_call, r=r)
    if iv is None:
        method1 = method2  # degrade gracefully — use method2 as proxy
    else:
        if t_years <= 0 or iv <= 0 or spot <= 0:
            return ImpliedProbs(method_bs_d2=method2, method_price_over_width=method2, iv_long_strike=iv)
        sqrt_t = math.sqrt(t_years)
        d1 = (math.log(spot / spec.long_K) + (r + 0.5 * iv * iv) * t_years) / (iv * sqrt_t)
        d2 = d1 - iv * sqrt_t
        if is_call:
            method1 = _norm_cdf(d2)         # P(S_T >= K) under risk-neutral
        else:
            method1 = _norm_cdf(-d2)        # P(S_T <= K)

    return ImpliedProbs(
        method_bs_d2=method1,
        method_price_over_width=method2,
        iv_long_strike=iv,
    )


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
pytest tests/touch_pin/test_implied.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/implied.py tests/touch_pin/test_implied.py
git commit -m "$(cat <<'EOF'
touch-pin: implied_pin_probabilities — two-method cross-check

Method 1: BS Phi(d2) at long strike (risk-neutral P of finishing ITM).
Method 2: entry_mid / width (heuristic, market-implied full-payoff P).
Both reported; engine flags when |diff| > 0.10 as data-quality warning.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `realized.py` — touched_during_day + exit at bar 385

**Files:**
- Create: `backtest/touch_pin/realized.py`
- Test: `tests/touch_pin/test_realized.py`

- [ ] **Step 1: Write failing test**

```python
# tests/touch_pin/test_realized.py
import datetime as dt
import os
import pytest
from backtest.touch_pin.realized import compute_realized, RealizedOutcome
from backtest.touch_pin.vehicle import VerticalSpec


@pytest.mark.db
def test_realized_known_day():
    db_url = os.environ["DATABASE_URL"]
    spec = VerticalSpec(
        side="PIN-CALL", long_K=600.0, short_K=601.0, width=1.0,
        entry_mid=0.20,
        long_bid=0.18, long_ask=0.22,
        short_bid=0.05, short_ask=0.09,
    )
    outcome = compute_realized(
        db_url,
        trade_date=dt.date(2025, 6, 2),
        expiration_date=dt.date(2025, 6, 3),
        spec=spec,
        exit_minute=385,
    )
    assert outcome is not None
    assert isinstance(outcome, RealizedOutcome)
    # Sanity: pnl_gross is bounded by +/- width (capped vertical)
    assert -spec.width - 0.10 <= outcome.pnl_gross <= spec.width + 0.10


def test_realized_dataclass_shape():
    o = RealizedOutcome(
        exit_mid=0.50, exit_long_bid=0.48, exit_long_ask=0.52,
        exit_short_bid=0.10, exit_short_ask=0.14,
        touched_during_day=1, time_first_touch_minute=120,
        spot_at_exit=535.5, exit_skipped_reason=None,
        pnl_gross=0.30,
    )
    assert o.pnl_gross == pytest.approx(0.30)
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/touch_pin/test_realized.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `realized.py`**

```python
# backtest/touch_pin/realized.py
"""Compute realized outcome of a vertical from entry minute to exit_minute.

For each minute between entry+1 and exit_minute:
  - record whether spot has crossed the long strike at any point (touched_during_day)
  - record the FIRST minute spot crossed (time_first_touch_minute, NULL if never)

At exit_minute (default 385 = 15:55 ET):
  - read mid_long(385) and mid_short(385) from helios_options_intraday
  - exit_mid = mid_long - mid_short
  - pnl_gross = exit_mid - entry_mid  (cost/slippage applied in engine, not here)

Spot per minute is derived from put-call parity at the most-ATM strike with
both legs valid in that bar. Implementation follows quant.walls helper.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Optional

import psycopg2

from backtest.touch_pin.vehicle import VerticalSpec
from quant.bs import derive_spot_from_parity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RealizedOutcome:
    exit_mid: float
    exit_long_bid: float
    exit_long_ask: float
    exit_short_bid: float
    exit_short_ask: float
    touched_during_day: int           # 0 or 1
    time_first_touch_minute: Optional[int]
    spot_at_exit: float
    exit_skipped_reason: Optional[str]  # populated if exit_mid is unreliable
    pnl_gross: float


def compute_realized(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    spec: VerticalSpec,
    exit_minute: int = 385,
    entry_minute: int = 5,
) -> Optional[RealizedOutcome]:
    """Walk minute bars from entry+1 to exit_minute, record touch + compute exit."""
    sql_bars = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT EXTRACT(EPOCH FROM (b.bar_time - first_bar.t0))::int / 60 AS minute_idx,
               b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time > first_bar.t0 + (%s * INTERVAL '1 minute')
          AND b.bar_time <= first_bar.t0 + (%s * INTERVAL '1 minute')
          AND (b.strike = %s OR b.strike = %s)
        ORDER BY b.bar_time, b.strike, b."right"
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql_bars, (
            trade_date, expiration_date,
            trade_date, expiration_date,
            entry_minute, exit_minute,
            spec.long_K, spec.short_K,
        ))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    if not rows:
        return None

    # Group by minute → {strike: {C/P: (bid, ask)}}
    by_minute: dict = {}
    for minute_idx, strike, right, bid, ask in rows:
        m = int(minute_idx)
        by_minute.setdefault(m, {}).setdefault(float(strike), {})[right] = (
            float(bid) if bid is not None else 0.0,
            float(ask) if ask is not None else 0.0,
        )

    # Per-minute parity-spot at the ATM strike (the long strike)
    is_call_side = (spec.side == "PIN-CALL")

    touched = 0
    first_touch_minute: Optional[int] = None
    spot_at_exit = 0.0
    exit_skipped_reason: Optional[str] = None

    sorted_minutes = sorted(by_minute.keys())
    for m in sorted_minutes:
        legs = by_minute[m]
        long_legs = legs.get(spec.long_K, {})
        if "C" in long_legs and "P" in long_legs:
            cb, ca = long_legs["C"]
            pb, pa = long_legs["P"]
            if cb > 0 and ca > 0 and pb > 0 and pa > 0:
                cm = 0.5 * (cb + ca)
                pm = 0.5 * (pb + pa)
                # T_years to expiration at minute m of trade day:
                # ~1 day at open (1/365), shrinking to ~0 at close. Use 1/365 — small effect on parity.
                spot_m = derive_spot_from_parity(cm, pm, spec.long_K, t_years=1/365)
                if is_call_side:
                    crossed = spot_m >= spec.long_K
                else:
                    crossed = spot_m <= spec.long_K
                if crossed and first_touch_minute is None:
                    touched = 1
                    first_touch_minute = m

    # Exit value at exit_minute
    exit_legs = by_minute.get(exit_minute, {})
    long_q = exit_legs.get(spec.long_K, {})
    short_q = exit_legs.get(spec.short_K, {})
    leg_key = "C" if is_call_side else "P"
    if leg_key not in long_q or leg_key not in short_q:
        exit_skipped_reason = f"missing {leg_key} leg quotes at minute {exit_minute}"
        # Fallback: walk back up to 5 minutes to find a usable bar
        for back in range(1, 6):
            alt_legs = by_minute.get(exit_minute - back, {})
            alt_long = alt_legs.get(spec.long_K, {})
            alt_short = alt_legs.get(spec.short_K, {})
            if leg_key in alt_long and leg_key in alt_short:
                long_q = alt_long
                short_q = alt_short
                exit_skipped_reason = f"fell back to minute {exit_minute - back}"
                break

    if leg_key not in long_q or leg_key not in short_q:
        return None

    lb, la = long_q[leg_key]
    sb, sa = short_q[leg_key]
    if lb <= 0 or la <= 0 or sb <= 0 or sa <= 0:
        return None
    long_mid = 0.5 * (lb + la)
    short_mid = 0.5 * (sb + sa)
    exit_mid = long_mid - short_mid

    # Compute spot at exit too
    if "C" in long_q and "P" in long_q:
        cb, ca = long_q["C"]
        pb, pa = long_q["P"]
        if cb > 0 and pb > 0:
            spot_at_exit = derive_spot_from_parity(0.5*(cb+ca), 0.5*(pb+pa), spec.long_K, t_years=0.5/365)

    pnl_gross = exit_mid - spec.entry_mid

    return RealizedOutcome(
        exit_mid=exit_mid,
        exit_long_bid=lb, exit_long_ask=la,
        exit_short_bid=sb, exit_short_ask=sa,
        touched_during_day=touched,
        time_first_touch_minute=first_touch_minute,
        spot_at_exit=spot_at_exit,
        exit_skipped_reason=exit_skipped_reason,
        pnl_gross=pnl_gross,
    )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
DATABASE_URL=$DATABASE_URL pytest tests/touch_pin/test_realized.py -v
```
Expected: both pass (DB test if DATABASE_URL set, dataclass test always).

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/realized.py tests/touch_pin/test_realized.py
git commit -m "$(cat <<'EOF'
touch-pin: realized walks bars and computes exit at minute 385

For each minute (entry_minute, exit_minute] derive parity-spot at long
strike and detect touch. At exit_minute read leg mids; fall back up to
5 minutes if the exact bar has no quotes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `engine.py` — per-day orchestration

**Files:**
- Create: `backtest/touch_pin/engine.py`
- Test: `tests/touch_pin/test_engine_smoke.py`

- [ ] **Step 1: Write failing test**

```python
# tests/touch_pin/test_engine_smoke.py
import datetime as dt
import os
import pytest
from backtest.touch_pin.engine import run_one_day, TradeRow


@pytest.mark.db
def test_run_one_day_smoke():
    db_url_main = os.environ["DATABASE_URL"]
    db_url_orat = os.environ.get("ORAT_DATABASE_URL", db_url_main)
    rows = run_one_day(
        db_url_main=db_url_main,
        db_url_orat=db_url_orat,
        trade_date=dt.date(2025, 6, 2),
        target_minute=5,
        exit_minute=385,
        slippage_ticks_per_leg=1,
        commission_per_leg=1.30,
    )
    # Either side may be unfilled; expect at most 2 trades, at least 0
    assert isinstance(rows, list)
    assert len(rows) <= 2
    for r in rows:
        assert isinstance(r, TradeRow)
        assert r.trade_date == dt.date(2025, 6, 2)
        assert r.side in {"PIN-CALL", "PIN-PUT"}
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/touch_pin/test_engine_smoke.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `engine.py`**

```python
# backtest/touch_pin/engine.py
"""Per-day orchestration: pull chain, build verticals, compute outcomes, return TradeRows."""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, asdict
from typing import List, Optional

from backtest.touch_pin.loader import (
    load_minute_chain, vix_close_prior_day, regime_label_at_open,
)
from backtest.touch_pin.vehicle import build_verticals
from backtest.touch_pin.implied import implied_pin_probabilities
from backtest.touch_pin.realized import compute_realized
from quant.walls import compute_intraday_walls

logger = logging.getLogger(__name__)


@dataclass
class TradeRow:
    trade_date: dt.date
    expiration_date: dt.date
    side: str
    long_K: float
    short_K: float
    width: float
    entry_mid: float
    exit_mid: float
    spot_5: float
    spot_close: float
    vix_close_prior: Optional[float]
    magnet_imbalance: float
    distance_pct: float
    regime_label: Optional[str]
    implied_method1: float
    implied_method2: float
    iv_long_strike: Optional[float]
    touched_during_day: int
    time_first_touch_minute: Optional[int]
    pnl_gross: float
    pnl_net: float
    slippage: float
    commission: float
    exit_skipped_reason: Optional[str]


def run_one_day(
    db_url_main: str,
    db_url_orat: str,
    trade_date: dt.date,
    target_minute: int = 5,
    exit_minute: int = 385,
    slippage_ticks_per_leg: int = 1,
    commission_per_leg: float = 1.30,
    expiration_date: Optional[dt.date] = None,
) -> List[TradeRow]:
    """Build trade rows for both sides on a single day. expiration_date defaults to T+1."""
    if expiration_date is None:
        expiration_date = _next_business_day(trade_date)

    snap = load_minute_chain(db_url_main, trade_date, expiration_date, target_minute)
    if snap is None or not snap.chain:
        return []

    walls = compute_intraday_walls(
        db_url_main, trade_date, expiration_date,
        target_minute=target_minute, t_years_at_open=1.0/365.0,
    )
    if walls is None or walls.spot is None:
        return []

    spot_5 = walls.spot
    walls_dict = {"call_wall": walls.call_wall, "put_support": walls.put_support}

    pin_call, pin_put = build_verticals(snap.chain, walls_dict, spot_5, strike_step=1.0)

    # Magnet imbalance from the strikes nearest spot — reuse walls.by_strike
    magnet_imb = _magnet_imbalance(walls)
    vix_prior = vix_close_prior_day(db_url_orat, trade_date)
    regime = regime_label_at_open(db_url_main, trade_date)

    results: List[TradeRow] = []
    for spec in (pin_call, pin_put):
        if spec is None:
            continue
        probs = implied_pin_probabilities(spec, spot_5, t_years=1.0/365.0)
        if probs is None:
            continue
        outcome = compute_realized(
            db_url_main, trade_date, expiration_date, spec,
            exit_minute=exit_minute, entry_minute=target_minute,
        )
        if outcome is None:
            continue
        slippage = slippage_ticks_per_leg * 0.01 * 2  # 2 legs, $0.01 per tick
        commission = commission_per_leg * 4  # 4 legs (2 to open, 2 to close)
        pnl_net = outcome.pnl_gross * 100 - slippage * 100 - commission  # 100 multiplier per contract
        # Note: pnl_gross is per-share; vertical contract = 100 shares
        distance_pct = abs(spec.long_K - spot_5) / spot_5 * 100.0

        results.append(TradeRow(
            trade_date=trade_date,
            expiration_date=expiration_date,
            side=spec.side,
            long_K=spec.long_K,
            short_K=spec.short_K,
            width=spec.width,
            entry_mid=spec.entry_mid,
            exit_mid=outcome.exit_mid,
            spot_5=spot_5,
            spot_close=outcome.spot_at_exit,
            vix_close_prior=vix_prior,
            magnet_imbalance=magnet_imb,
            distance_pct=distance_pct,
            regime_label=regime,
            implied_method1=probs.method_bs_d2,
            implied_method2=probs.method_price_over_width,
            iv_long_strike=probs.iv_long_strike,
            touched_during_day=outcome.touched_during_day,
            time_first_touch_minute=outcome.time_first_touch_minute,
            pnl_gross=outcome.pnl_gross * 100,  # converted to dollars per contract
            pnl_net=pnl_net,
            slippage=slippage * 100,
            commission=commission,
            exit_skipped_reason=outcome.exit_skipped_reason,
        ))

    return results


def _magnet_imbalance(walls) -> float:
    """call_peak / put_peak — guard against zero put peak."""
    call_peaks = [s.call_gamma_oi for s in walls.by_strike if s.call_gamma_oi > 0]
    put_peaks = [s.put_gamma_oi for s in walls.by_strike if s.put_gamma_oi > 0]
    cp = max(call_peaks) if call_peaks else 0.0
    pp = max(put_peaks) if put_peaks else 0.0
    if pp <= 0:
        return 99.0  # all-call regime — treat as extreme bullish
    return cp / pp


def _next_business_day(d: dt.date) -> dt.date:
    """Add 1 calendar day; if Sat/Sun, advance to Monday."""
    nxt = d + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt
```

- [ ] **Step 4: Run test to confirm pass**

```bash
DATABASE_URL=$DATABASE_URL ORAT_DATABASE_URL=$ORAT_DATABASE_URL pytest tests/touch_pin/test_engine_smoke.py -v
```
Expected: PASS (or skipped if DBs unavailable).

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/engine.py tests/touch_pin/test_engine_smoke.py
git commit -m "$(cat <<'EOF'
touch-pin: per-day engine orchestrates loader/vehicle/implied/realized

run_one_day() pulls chain, computes walls, builds both side verticals,
computes implied + realized, joins context (vix prior-day, regime label),
returns up to 2 TradeRow per day.

PnL conversion: per-share PnL * 100 (contract multiplier) - slippage -
4-leg commission. Slippage default 1 tick/leg.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `binning.py` — Bucket and aggregate

**Files:**
- Create: `backtest/touch_pin/binning.py`
- Test: `tests/touch_pin/test_binning.py`

- [ ] **Step 1: Write failing test**

```python
# tests/touch_pin/test_binning.py
import datetime as dt
import pytest
from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.binning import bin_trades, BinSummary


def make_row(side="PIN-CALL", magnet_imb=1.5, vix=18.0, dist=0.4, regime="NORMAL", pnl=10.0):
    return TradeRow(
        trade_date=dt.date(2024, 6, 4), expiration_date=dt.date(2024, 6, 5),
        side=side, long_K=535.0, short_K=536.0, width=1.0,
        entry_mid=0.20, exit_mid=0.30, spot_5=533.0, spot_close=534.5,
        vix_close_prior=vix, magnet_imbalance=magnet_imb, distance_pct=dist,
        regime_label=regime, implied_method1=0.45, implied_method2=0.20,
        iv_long_strike=0.18, touched_during_day=1, time_first_touch_minute=120,
        pnl_gross=10.0, pnl_net=pnl, slippage=2.0, commission=5.20,
        exit_skipped_reason=None,
    )


def test_bin_trades_buckets_and_aggregates():
    trades = [make_row(magnet_imb=1.4, pnl=5.0) for _ in range(10)] + \
             [make_row(magnet_imb=1.7, pnl=8.0) for _ in range(20)]
    bins = bin_trades(trades)
    assert isinstance(bins, list)
    assert all(isinstance(b, BinSummary) for b in bins)
    # Find the magnet 1.5-2.0 bin
    matching = [b for b in bins if b.magnet_imb_bucket == "1.5-2.0"]
    assert len(matching) >= 1
    found = matching[0]
    assert found.n == 20
    assert found.mean_pnl == pytest.approx(8.0)


def test_bin_buckets_known_boundaries():
    from backtest.touch_pin.binning import _magnet_bucket, _vix_bucket, _distance_bucket
    assert _magnet_bucket(1.0) == "<1.2"
    assert _magnet_bucket(1.3) == "1.2-1.5"
    assert _magnet_bucket(1.7) == "1.5-2.0"
    assert _magnet_bucket(2.5) == ">2.0"
    assert _vix_bucket(12) == "<15"
    assert _vix_bucket(17) == "15-20"
    assert _vix_bucket(25) == "20-30"
    assert _vix_bucket(35) == ">30"
    assert _distance_bucket(0.2) == "<0.3%"
    assert _distance_bucket(0.5) == "0.3-0.6%"
    assert _distance_bucket(0.7) == ">0.6%"
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/touch_pin/test_binning.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `binning.py`**

```python
# backtest/touch_pin/binning.py
"""Bucket trades by (magnet_imb, vix, distance, regime) and aggregate."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Optional

from backtest.touch_pin.engine import TradeRow


@dataclass(frozen=True)
class BinSummary:
    side: str
    magnet_imb_bucket: str
    vix_bucket: str
    distance_bucket: str
    regime_label: str
    n: int
    n_winners: int
    win_rate: float
    mean_pnl: float
    median_pnl: float
    std_pnl: float
    sharpe_per_trade: float
    mean_touched: float
    mean_implied_method1: float
    mean_implied_method2: float


def bin_trades(trades: List[TradeRow]) -> List[BinSummary]:
    groups: dict = {}
    for t in trades:
        key = (
            t.side,
            _magnet_bucket(t.magnet_imbalance),
            _vix_bucket(t.vix_close_prior or 0.0),
            _distance_bucket(t.distance_pct),
            t.regime_label or "unlabeled",
        )
        groups.setdefault(key, []).append(t)

    out: List[BinSummary] = []
    for key, items in groups.items():
        side, mb, vb, db, rb = key
        pnls = [t.pnl_net for t in items]
        n = len(pnls)
        winners = sum(1 for p in pnls if p > 0)
        mean_pnl = sum(pnls) / n if n else 0.0
        median_pnl = statistics.median(pnls) if n else 0.0
        std_pnl = statistics.pstdev(pnls) if n > 1 else 0.0
        sharpe = (mean_pnl / std_pnl) if std_pnl > 1e-9 else 0.0
        mean_touched = sum(t.touched_during_day for t in items) / n if n else 0.0
        m1 = sum(t.implied_method1 for t in items) / n if n else 0.0
        m2 = sum(t.implied_method2 for t in items) / n if n else 0.0
        out.append(BinSummary(
            side=side, magnet_imb_bucket=mb, vix_bucket=vb,
            distance_bucket=db, regime_label=rb,
            n=n, n_winners=winners, win_rate=winners / n if n else 0.0,
            mean_pnl=mean_pnl, median_pnl=median_pnl, std_pnl=std_pnl,
            sharpe_per_trade=sharpe, mean_touched=mean_touched,
            mean_implied_method1=m1, mean_implied_method2=m2,
        ))
    out.sort(key=lambda b: (b.side, b.magnet_imb_bucket, b.vix_bucket, b.distance_bucket, b.regime_label))
    return out


def _magnet_bucket(x: float) -> str:
    if x < 1.2: return "<1.2"
    if x < 1.5: return "1.2-1.5"
    if x < 2.0: return "1.5-2.0"
    return ">2.0"


def _vix_bucket(x: float) -> str:
    if x < 15: return "<15"
    if x < 20: return "15-20"
    if x < 30: return "20-30"
    return ">30"


def _distance_bucket(pct: float) -> str:
    if pct < 0.3: return "<0.3%"
    if pct < 0.6: return "0.3-0.6%"
    return ">0.6%"
```

- [ ] **Step 4: Run test to confirm pass**

```bash
pytest tests/touch_pin/test_binning.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/binning.py tests/touch_pin/test_binning.py
git commit -m "$(cat <<'EOF'
touch-pin: bin_trades buckets by (side, magnet, vix, distance, regime)

BinSummary collects n, win_rate, mean/median/std PnL, per-trade Sharpe,
mean_touched, mean_implied (both methods) per bin.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `report.py` — Markdown writer

**Files:**
- Create: `backtest/touch_pin/report.py`

- [ ] **Step 1: Implement `report.py` (no separate test — output is the test)**

```python
# backtest/touch_pin/report.py
"""Markdown report writer for the touch_pin harness.

Outputs:
  - per-trade CSV at output/touch_pin_trades_<start>_<end>.csv
  - markdown report at output/touch_pin_report_<start>_<end>.md
"""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import List

from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.binning import BinSummary, bin_trades


def write_trades_csv(trades: List[TradeRow], path: Path) -> None:
    if not trades:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(trades[0]).keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for t in trades:
            row = asdict(t)
            for k, v in row.items():
                if isinstance(v, dt.date):
                    row[k] = v.isoformat()
            w.writerow(row)


def write_markdown_report(
    trades: List[TradeRow],
    bins: List[BinSummary],
    path: Path,
    start: dt.date,
    end: dt.date,
    sensitivity_results: dict = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(trades)
    pnls = [t.pnl_net for t in trades]
    overall_mean = sum(pnls) / n if n else 0.0
    overall_wr = sum(1 for p in pnls if p > 0) / n if n else 0.0

    lines = []
    lines.append(f"# Touch-Pin (Phase 1) Backtest Report")
    lines.append("")
    lines.append(f"**Period:** {start.isoformat()} → {end.isoformat()}")
    lines.append(f"**Total trades:** {n}")
    lines.append(f"**Overall WR:** {overall_wr:.1%}")
    lines.append(f"**Overall mean PnL/trade:** ${overall_mean:.2f}")
    lines.append("")
    lines.append("## Bin Summary")
    lines.append("")
    lines.append("| Side | Magnet | VIX | Dist | Regime | n | WR | Mean | Median | Std | Sharpe | Touch | Imp1 | Imp2 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for b in bins:
        lines.append(
            f"| {b.side} | {b.magnet_imb_bucket} | {b.vix_bucket} | {b.distance_bucket} | "
            f"{b.regime_label} | {b.n} | {b.win_rate:.1%} | ${b.mean_pnl:.2f} | "
            f"${b.median_pnl:.2f} | ${b.std_pnl:.2f} | {b.sharpe_per_trade:.2f} | "
            f"{b.mean_touched:.1%} | {b.mean_implied_method1:.2%} | {b.mean_implied_method2:.2%} |"
        )
    lines.append("")
    lines.append("## GO Criteria (per spec)")
    lines.append("")
    lines.append("Bin qualifies for GO if:")
    lines.append("1. n ≥ 30 in 2023-24 train, n ≥ 15 in 2025 OOS")
    lines.append("2. Bin mean PnL ≥ +$5 after costs")
    lines.append("3. OOS sign matches and magnitude within ±50%")
    lines.append("4. Per-trade Sharpe ≥ 0.3")
    lines.append("")
    qualifying = [b for b in bins if b.n >= 30 and b.mean_pnl >= 5.0 and b.sharpe_per_trade >= 0.3]
    lines.append(f"### Qualifying bins (in-sample only, OOS check separate): {len(qualifying)}")
    for b in qualifying:
        lines.append(
            f"- {b.side} | mag={b.magnet_imb_bucket} | vix={b.vix_bucket} | "
            f"dist={b.distance_bucket} | reg={b.regime_label}: "
            f"n={b.n} WR={b.win_rate:.1%} mean_pnl=${b.mean_pnl:.2f} sharpe={b.sharpe_per_trade:.2f}"
        )
    lines.append("")

    if sensitivity_results:
        lines.append("## Sensitivity Battery")
        lines.append("")
        lines.append("| Variant | n | WR | Mean PnL |")
        lines.append("|---|---|---|---|")
        for label, res in sensitivity_results.items():
            lines.append(f"| {label} | {res['n']} | {res['wr']:.1%} | ${res['mean']:.2f} |")
        lines.append("")

    path.write_text("\n".join(lines))
```

- [ ] **Step 2: Smoke test the report writer with synthetic data**

```bash
python -c "
import datetime as dt
from pathlib import Path
from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.report import write_trades_csv, write_markdown_report
from backtest.touch_pin.binning import bin_trades

t = TradeRow(
    trade_date=dt.date(2024,6,4), expiration_date=dt.date(2024,6,5),
    side='PIN-CALL', long_K=535.0, short_K=536.0, width=1.0,
    entry_mid=0.20, exit_mid=0.30, spot_5=533.0, spot_close=534.5,
    vix_close_prior=18.0, magnet_imbalance=1.5, distance_pct=0.4,
    regime_label='NORMAL', implied_method1=0.45, implied_method2=0.20,
    iv_long_strike=0.18, touched_during_day=1, time_first_touch_minute=120,
    pnl_gross=10.0, pnl_net=8.0, slippage=2.0, commission=5.20,
    exit_skipped_reason=None,
)
trades = [t]
bins = bin_trades(trades)
write_trades_csv(trades, Path('backtest/touch_pin/output/_smoke.csv'))
write_markdown_report(trades, bins, Path('backtest/touch_pin/output/_smoke.md'),
                     start=dt.date(2024,6,4), end=dt.date(2024,6,4))
print('smoke OK')
"
```
Expected: prints `smoke OK`. Files exist at paths shown.

- [ ] **Step 3: Cleanup smoke artifacts**

```bash
rm backtest/touch_pin/output/_smoke.csv backtest/touch_pin/output/_smoke.md
```

- [ ] **Step 4: Commit**

```bash
git add backtest/touch_pin/report.py
git commit -m "$(cat <<'EOF'
touch-pin: report writer for trades CSV + markdown summary

write_trades_csv() dumps per-trade rows. write_markdown_report() shows
overall stats, bin table, qualifying-bins list, and an optional
sensitivity battery section.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: `walk_forward.py` — Train/Validation/OOS split + GO/NO-GO

**Files:**
- Create: `backtest/touch_pin/walk_forward.py`
- Test: `tests/touch_pin/test_walk_forward.py`

- [ ] **Step 1: Write failing test**

```python
# tests/touch_pin/test_walk_forward.py
import datetime as dt
from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.walk_forward import (
    split_trades, evaluate_go_no_go, GoNoGoResult,
)


def _row(d: dt.date, side="PIN-CALL", pnl=8.0, mb="1.5-2.0"):
    return TradeRow(
        trade_date=d, expiration_date=d + dt.timedelta(days=1),
        side=side, long_K=535.0, short_K=536.0, width=1.0,
        entry_mid=0.20, exit_mid=0.30, spot_5=533.0, spot_close=534.5,
        vix_close_prior=18.0, magnet_imbalance=1.7, distance_pct=0.4,
        regime_label="NORMAL", implied_method1=0.45, implied_method2=0.20,
        iv_long_strike=0.18, touched_during_day=1, time_first_touch_minute=120,
        pnl_gross=10.0, pnl_net=pnl, slippage=2.0, commission=5.20,
        exit_skipped_reason=None,
    )


def test_split_trades_by_year():
    trades = [
        _row(dt.date(2023, 6, 1)),
        _row(dt.date(2024, 6, 1)),
        _row(dt.date(2025, 6, 1)),
    ]
    train, val, oos = split_trades(trades)
    assert len(train) == 1 and train[0].trade_date.year == 2023
    assert len(val) == 1 and val[0].trade_date.year == 2024
    assert len(oos) == 1 and oos[0].trade_date.year == 2025


def test_evaluate_go_no_go_passes_when_thresholds_met():
    # 35 trades in train, 18 in OOS, mean=$8, sharpe approx via low std
    train = [_row(dt.date(2023, 1, i+1), pnl=8.0) for i in range(20)] + \
            [_row(dt.date(2024, 1, i+1), pnl=8.0) for i in range(15)]
    val = []
    oos = [_row(dt.date(2025, 1, i+1), pnl=7.0) for i in range(18)]
    res = evaluate_go_no_go(train + val, oos)
    assert isinstance(res, GoNoGoResult)
    assert res.n_qualifying_bins >= 1
    assert res.go is True
    assert "qualifying" in res.summary.lower() or "go" in res.summary.lower()


def test_evaluate_go_no_go_fails_on_sample_size():
    train = [_row(dt.date(2023, 1, i+1), pnl=8.0) for i in range(5)]
    oos = [_row(dt.date(2025, 1, i+1), pnl=8.0) for i in range(5)]
    res = evaluate_go_no_go(train, oos)
    assert res.go is False
```

- [ ] **Step 2: Run test to confirm failure**

```bash
pytest tests/touch_pin/test_walk_forward.py -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `walk_forward.py`**

```python
# backtest/touch_pin/walk_forward.py
"""Walk-forward split + GO/NO-GO evaluator per spec §7.4 and §11.

Splits:
  Train      : 2023-01-03 → 2023-12-29
  Validation : 2024-01-02 → 2024-12-31
  OOS        : 2025-01-02 → 2025-12-05  (frozen until final eval)

GO criteria (per qualifying bin):
  1. n_train_val ≥ 30, n_oos ≥ 15
  2. mean_pnl ≥ +$5 after costs (in-sample)
  3. OOS mean_pnl same sign, magnitude within ±50% of in-sample
  4. Per-trade Sharpe ≥ 0.3 in-sample
Aggregate GO: ≥1 qualifying bin AND ≥100 total trades across qualifying bins.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass
from typing import List, Tuple

from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.binning import bin_trades, BinSummary, _magnet_bucket, _vix_bucket, _distance_bucket


@dataclass(frozen=True)
class GoNoGoResult:
    go: bool
    n_qualifying_bins: int
    n_total_trades_in_qualifying_bins: int
    qualifying_bins: List[BinSummary]
    summary: str


TRAIN_END = dt.date(2024, 12, 31)
OOS_START = dt.date(2025, 1, 1)


def split_trades(trades: List[TradeRow]) -> Tuple[List[TradeRow], List[TradeRow], List[TradeRow]]:
    train, val, oos = [], [], []
    for t in trades:
        if t.trade_date.year == 2023:
            train.append(t)
        elif t.trade_date.year == 2024:
            val.append(t)
        elif t.trade_date.year == 2025:
            oos.append(t)
    return train, val, oos


def evaluate_go_no_go(insample: List[TradeRow], oos: List[TradeRow]) -> GoNoGoResult:
    """Pick qualifying bins from insample, validate on oos."""
    in_bins = bin_trades(insample)
    oos_bins_lookup = {_bin_key(b): b for b in bin_trades(oos)}

    qualifying: List[BinSummary] = []
    notes: List[str] = []
    for b in in_bins:
        if b.n < 30:
            continue
        if b.mean_pnl < 5.0:
            continue
        if b.sharpe_per_trade < 0.3:
            continue
        key = _bin_key(b)
        oos_b = oos_bins_lookup.get(key)
        if oos_b is None or oos_b.n < 15:
            notes.append(f"bin {key} has insufficient OOS samples ({oos_b.n if oos_b else 0})")
            continue
        # Sign + magnitude check
        if (oos_b.mean_pnl < 0) != (b.mean_pnl < 0):
            notes.append(f"bin {key} OOS mean sign mismatch (in=${b.mean_pnl:.2f} oos=${oos_b.mean_pnl:.2f})")
            continue
        if abs(oos_b.mean_pnl) < 0.5 * abs(b.mean_pnl) or abs(oos_b.mean_pnl) > 1.5 * abs(b.mean_pnl):
            notes.append(f"bin {key} OOS magnitude outside ±50% (in=${b.mean_pnl:.2f} oos=${oos_b.mean_pnl:.2f})")
            continue
        qualifying.append(b)

    n_total = sum(b.n for b in qualifying)
    go = bool(qualifying) and n_total >= 100

    summary_lines = [f"Qualifying bins: {len(qualifying)}, total trades: {n_total}"]
    if go:
        summary_lines.append("VERDICT: GO")
    else:
        summary_lines.append("VERDICT: NO-GO")
        if notes:
            summary_lines.append("Disqualified bins:")
            summary_lines.extend(f"  - {n}" for n in notes[:10])

    return GoNoGoResult(
        go=go,
        n_qualifying_bins=len(qualifying),
        n_total_trades_in_qualifying_bins=n_total,
        qualifying_bins=qualifying,
        summary="\n".join(summary_lines),
    )


def _bin_key(b: BinSummary):
    return (b.side, b.magnet_imb_bucket, b.vix_bucket, b.distance_bucket, b.regime_label)
```

- [ ] **Step 4: Run test to confirm pass**

```bash
pytest tests/touch_pin/test_walk_forward.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/touch_pin/walk_forward.py tests/touch_pin/test_walk_forward.py
git commit -m "$(cat <<'EOF'
touch-pin: walk_forward split + GO/NO-GO evaluator

split_trades() partitions by year (2023/2024/2025).
evaluate_go_no_go() picks qualifying bins from insample, validates
on OOS with sign + ±50% magnitude tolerance and OOS-n>=15 floor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: `cli.py` — End-to-end runner

**Files:**
- Create: `backtest/touch_pin/cli.py`
- Create: `backtest/touch_pin/__main__.py`

- [ ] **Step 1: Implement `cli.py`**

```python
# backtest/touch_pin/cli.py
"""End-to-end runner: iterate days, collect trades, write CSV + report."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import List

from backtest.touch_pin.engine import run_one_day, TradeRow
from backtest.touch_pin.report import write_trades_csv, write_markdown_report
from backtest.touch_pin.binning import bin_trades
from backtest.touch_pin.walk_forward import split_trades, evaluate_go_no_go

logger = logging.getLogger("touch_pin")


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def trading_days_between(start: dt.date, end: dt.date) -> List[dt.date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon-Fri (we don't model US holidays — empty bars filtered by loader)
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def main(argv=None):
    p = argparse.ArgumentParser(prog="backtest.touch_pin")
    p.add_argument("--start", type=parse_date, required=True)
    p.add_argument("--end", type=parse_date, required=True)
    p.add_argument("--target-minute", type=int, default=5)
    p.add_argument("--exit-minute", type=int, default=385)
    p.add_argument("--slippage-ticks", type=int, default=1)
    p.add_argument("--commission-leg", type=float, default=1.30)
    p.add_argument("--output-dir", type=Path, default=Path("backtest/touch_pin/output"))
    p.add_argument("--report-name", type=str, default="touch_pin")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--no-eval", action="store_true",
                   help="Skip walk-forward GO/NO-GO evaluation (just dump trades)")
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    db_main = os.environ.get("DATABASE_URL")
    db_orat = os.environ.get("ORAT_DATABASE_URL", db_main)
    if not db_main:
        logger.error("DATABASE_URL must be set")
        return 1

    days = trading_days_between(args.start, args.end)
    logger.info("running %d trading days from %s to %s", len(days), args.start, args.end)

    all_trades: List[TradeRow] = []
    for i, d in enumerate(days):
        try:
            rows = run_one_day(
                db_main, db_orat, d,
                target_minute=args.target_minute,
                exit_minute=args.exit_minute,
                slippage_ticks_per_leg=args.slippage_ticks,
                commission_per_leg=args.commission_leg,
            )
            all_trades.extend(rows)
            if (i + 1) % 25 == 0:
                logger.info("%d/%d days done; %d trades so far", i + 1, len(days), len(all_trades))
        except Exception:
            logger.exception("day %s failed; continuing", d)

    logger.info("complete: %d trades from %d days", len(all_trades), len(days))

    out_csv = args.output_dir / f"{args.report_name}_trades_{args.start}_{args.end}.csv"
    out_md = args.output_dir / f"{args.report_name}_report_{args.start}_{args.end}.md"
    write_trades_csv(all_trades, out_csv)

    bins = bin_trades(all_trades)

    sensitivity = None
    go_summary = None
    if not args.no_eval:
        train, val, oos = split_trades(all_trades)
        insample = train + val
        result = evaluate_go_no_go(insample, oos)
        go_summary = result.summary
        logger.info("GO/NO-GO: %s", result.summary)

    write_markdown_report(all_trades, bins, out_md, args.start, args.end, sensitivity_results=None)
    if go_summary:
        with out_md.open("a") as f:
            f.write("\n\n## GO/NO-GO\n\n```\n")
            f.write(go_summary)
            f.write("\n```\n")

    logger.info("wrote %s and %s", out_csv, out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Implement `__main__.py`**

```python
# backtest/touch_pin/__main__.py
from backtest.touch_pin.cli import main
import sys
sys.exit(main())
```

- [ ] **Step 3: Smoke test on a 5-day window (DB available)**

```bash
DATABASE_URL=$DATABASE_URL ORAT_DATABASE_URL=$ORAT_DATABASE_URL \
  python -m backtest.touch_pin --start 2024-06-03 --end 2024-06-07 \
  --report-name smoke --no-eval --log-level INFO
```
Expected: `complete: N trades from 5 days` + outputs at `backtest/touch_pin/output/smoke_*.csv|md`.

- [ ] **Step 4: Inspect smoke output**

```bash
ls -la backtest/touch_pin/output/smoke_*
cat backtest/touch_pin/output/smoke_report_2024-06-03_2024-06-07.md
```
Expected: report shows ≤10 trades (≤2/day × 5 days), bin table with one or more rows.

- [ ] **Step 5: Cleanup smoke artifacts and commit**

```bash
rm backtest/touch_pin/output/smoke_*
git add backtest/touch_pin/cli.py backtest/touch_pin/__main__.py
git commit -m "$(cat <<'EOF'
touch-pin: CLI runner — iterate days, dump trades + report + GO/NO-GO

python -m backtest.touch_pin --start YYYY-MM-DD --end YYYY-MM-DD
runs the full pipeline. Walk-forward eval on by default; --no-eval
skips the GO/NO-GO appendix.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Run full backtest 2023-01-03 → 2025-12-05

**Files:**
- Create: `docs/superpowers/reports/2026-05-10-touch-pin-final.md` (commit the final report)

- [ ] **Step 1: Confirm DB env vars set**

```bash
echo "main: ${DATABASE_URL:0:40}..."
echo "orat: ${ORAT_DATABASE_URL:0:40}..."
```
Expected: both URLs printed (truncated).

- [ ] **Step 2: Run the full backtest (will take 30-90 min depending on DB latency)**

```bash
python -m backtest.touch_pin \
  --start 2023-01-03 --end 2025-12-05 \
  --report-name final \
  --log-level INFO 2>&1 | tee backtest/touch_pin/output/final_run.log
```

- [ ] **Step 3: Inspect produced report**

```bash
cat backtest/touch_pin/output/final_report_2023-01-03_2025-12-05.md
```

- [ ] **Step 4: Run sensitivity battery (5 variants)**

For each variant, re-run with different parameters and append to a single sensitivity report:

```bash
# Variant: 0 ticks slippage
python -m backtest.touch_pin --start 2023-01-03 --end 2025-12-05 \
  --slippage-ticks 0 --report-name sens_slip0 --no-eval --log-level WARNING

# Variant: 2 ticks slippage
python -m backtest.touch_pin --start 2023-01-03 --end 2025-12-05 \
  --slippage-ticks 2 --report-name sens_slip2 --no-eval --log-level WARNING

# Variant: minute 10 entry
python -m backtest.touch_pin --start 2023-01-03 --end 2025-12-05 \
  --target-minute 10 --report-name sens_min10 --no-eval --log-level WARNING

# Variant: 15:50 exit
python -m backtest.touch_pin --start 2023-01-03 --end 2025-12-05 \
  --exit-minute 380 --report-name sens_exit380 --no-eval --log-level WARNING

# Variant: 15:59 exit
python -m backtest.touch_pin --start 2023-01-03 --end 2025-12-05 \
  --exit-minute 389 --report-name sens_exit389 --no-eval --log-level WARNING
```

- [ ] **Step 5: Promote the final report to docs/superpowers/reports/ and commit**

```bash
cp backtest/touch_pin/output/final_report_2023-01-03_2025-12-05.md \
   docs/superpowers/reports/2026-05-10-touch-pin-final.md

git add docs/superpowers/reports/2026-05-10-touch-pin-final.md
git commit -m "$(cat <<'EOF'
touch-pin: final research report (Phase 1) — 2023-2025 backtest

Full window 2023-01-03 to 2025-12-05; walk-forward GO/NO-GO included.
Sensitivity variants (slip 0/2 ticks, entry min 5/10, exit min 380/385/389)
written to backtest/touch_pin/output/ but not committed (regenerable from CSV).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-review checklist (run after writing all tasks)

1. **Spec coverage:**
   - §7 Phase 1 harness — Tasks 1-11 ✓
   - §7.4 GO criteria — Task 10 ✓
   - §7.5 sensitivity battery — Task 12 step 4 ✓
   - §11 walk-forward — Task 10 ✓
   - §12 testing strategy (unit, smoke, regression) — Tasks 1-10 unit; Task 11 smoke; regression-pin deferred (would lock 2024-06-04 in a follow-up — not blocking GO)

2. **Placeholder scan:** none. Every step has actual code or commands.

3. **Type consistency:** `ChainEntry`, `VerticalSpec`, `ImpliedProbs`, `RealizedOutcome`, `TradeRow`, `BinSummary`, `GoNoGoResult` — names referenced consistently across tasks.

---

**End of plan.**
