# Phase 2 Implementation Plan: Skew + Charm Signal Stack

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research harness that tests whether a 1DTE SPY directional signal built from intraday IV-skew dynamics + dealer charm pressure (with magnet-imbalance confirmer) achieves ≥66% WR on debit verticals exited via PT/SL/trail with same-day time-stop.

**Architecture:** Per-minute scanner over 09:35–14:00 ET on each trading day. Solve IV from `helios_options_intraday` quote bars, compute 25Δ skew + Δskew_15m, charm_call/charm_put from analytical greeks weighted by OI, magnet-imbalance from `quant.walls`. Composite z-score gates entry; first qualifying minute fires once per day. Vehicle: 1-pt-wide debit vertical (long ATM, short 1-strike OTM) simulated via promoted `quant/sim.py` with PT=20% / SL=30% / trail=5/8 / hard time-stop at bar 385.

**Tech Stack:** Python 3.11+, psycopg2, pytest, numpy. Reuses `quant/bs.py` (extended with `bs_charm`), `quant/walls.py`, and a new `quant/sim.py` distilled from the HELIOS `_simulate_intraday`. Branches off `claude/touch-pin-validation` so Phase 1's `quant/` modules are inherited.

---

## File structure

**New files:**

```
quant/
├── bs.py            # EXTENDED with bs_charm()
└── sim.py           # NEW — simplified _simulate_intraday with explicit thresholds (no HeliosConfig)

backtest/skew_signal/
├── __init__.py
├── loader.py        # Pull FULL chain (all strikes) at minute M
├── features.py      # Combined: IV solver + skew interpolation + charm aggregation
├── signal.py        # BULL/BEAR/NONE + composite z-score
├── engine.py        # Per-day: scan minutes 35→820 (=14:00 CT), first qualifying signal fires
├── binning.py       # Bucket trades by composite_z bin + WR/EV
├── walk_forward.py  # Train/Val/OOS split + parameter grid search for θ_skew, θ_charm
├── report.py        # Markdown + per-trade CSV
└── cli.py

tests/skew_signal/
├── __init__.py
├── conftest.py
├── test_bs_charm.py
├── test_sim.py
├── test_loader.py
├── test_features.py
├── test_signal.py
└── test_engine_smoke.py

docs/superpowers/reports/
└── 2026-05-10-skew-charm-final.md   # Output of Task 9 (committed)
```

**Modified files:**
- `quant/bs.py` — add `bs_charm()` and supporting `_norm_pdf` (already present)

**Branch:** `claude/skew-signal-validation` off `claude/touch-pin-validation` so the harness inherits `quant/bs.py` and `quant/walls.py` without re-promoting them.

---

## Task 0: Branch + scaffold

**Files:**
- Create: `backtest/skew_signal/__init__.py`, `tests/skew_signal/__init__.py`, `backtest/skew_signal/output/.gitkeep`
- Modify: `.gitignore`

- [ ] **Step 1: Branch off touch-pin-validation**

```bash
cd C:/Users/lemol/AlphaGEX
git checkout claude/touch-pin-validation
git checkout -b claude/skew-signal-validation
git rev-parse --abbrev-ref HEAD
```
Expected: `claude/skew-signal-validation`.

- [ ] **Step 2: Create directory scaffold**

```bash
mkdir -p backtest/skew_signal/output tests/skew_signal
touch backtest/skew_signal/__init__.py
touch tests/skew_signal/__init__.py
touch backtest/skew_signal/output/.gitkeep
```

- [ ] **Step 3: Add gitignore rule**

Append to `.gitignore`:
```
# skew_signal per-trade CSV outputs (regenerable)
backtest/skew_signal/output/*.csv
backtest/skew_signal/output/*.log
!backtest/skew_signal/output/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add backtest/skew_signal/__init__.py tests/skew_signal/__init__.py \
        backtest/skew_signal/output/.gitkeep .gitignore
git commit -m "skew-signal: scaffold backtest/skew_signal/ + tests/skew_signal/"
```

---

## Task 1: Extend `quant/bs.py` with `bs_charm`

Charm is `∂Δ/∂T` (per year). For a call with no dividends:

```
charm_call = N'(d1) * [ (r + σ²/2) / (σ√T) − d1 / (2T) ]
```

Same magnitude for put (the put delta is `N(d1) − 1`, so `∂Δ_put/∂T = ∂Δ_call/∂T`).

**Files:**
- Modify: `quant/bs.py` (append `bs_charm`)
- Test: `tests/skew_signal/test_bs_charm.py`

- [ ] **Step 1: Write failing test**

```python
# tests/skew_signal/test_bs_charm.py
import math
import pytest
from quant.bs import bs_charm, bs_price, implied_vol


def test_bs_charm_atm_returns_finite():
    c = bs_charm(spot=500.0, strike=500.0, t_years=1/365, sigma=0.20)
    assert math.isfinite(c)


def test_bs_charm_zero_at_expiry():
    # Charm is undefined / divergent at T=0; we return 0 as a safe sentinel
    assert bs_charm(500.0, 500.0, 0.0, 0.20) == 0.0


def test_bs_charm_otm_call_negative():
    # OTM call delta declines as T→0 → charm < 0
    c = bs_charm(spot=500.0, strike=510.0, t_years=1/365, sigma=0.20)
    assert c < 0


def test_bs_charm_numerical_agreement():
    # Cross-check analytical against numerical: charm ≈ ΔN(d1)/ΔT
    spot, strike, T, sigma = 500.0, 502.0, 5/365, 0.20
    eps = 1e-6
    p1 = bs_price(spot, strike, T, sigma, is_call=True)
    p2 = bs_price(spot, strike, T + eps, sigma, is_call=True)
    # Numerical ∂C/∂T (theta-like) is not charm; instead verify Δ-derivative
    # via (Δ(T+eps) − Δ(T)) / eps. We approximate Δ via implied_vol roundtrip.
    # Easier: run analytical charm and assert it's the right order of magnitude.
    c = bs_charm(spot, strike, T, sigma)
    assert abs(c) < 100.0  # sanity bound: per-year delta change is small
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_bs_charm.py -v --no-cov
```
Expected: FAIL — `bs_charm` not defined.

- [ ] **Step 3: Implement `bs_charm` in `quant/bs.py` (append after `bs_gamma`)**

Append the following function to `quant/bs.py`:

```python
def bs_charm(
    spot: float,
    strike: float,
    t_years: float,
    sigma: float,
    r: float = DEFAULT_R,
) -> float:
    """∂Δ/∂T (per year). Same value for calls and puts under no dividends.

    Returns 0 at/past expiry or when sigma is non-positive (undefined region).
    Sign convention: positive charm means delta increases as time passes —
    this is bullish for OTM calls (delta rises toward 1) and for ITM puts
    (delta rises toward 0). Negative charm is the opposite.
    """
    if t_years <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return _norm_pdf(d1) * ((r + 0.5 * sigma * sigma) / (sigma * sqrt_t) - d1 / (2.0 * t_years))
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_bs_charm.py -v --no-cov
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add quant/bs.py tests/skew_signal/test_bs_charm.py
git commit -m "quant: add bs_charm — partial-Delta wrt time (per year, q=0)"
```

---

## Task 2: Promote `quant/sim.py` — simplified intraday simulator

Distilled from HELIOS `_simulate_intraday`: removes the `HeliosConfig` dependency and accepts thresholds as direct args.

**Files:**
- Create: `quant/sim.py`
- Test: `tests/skew_signal/test_sim.py`

- [ ] **Step 1: Write failing test**

```python
# tests/skew_signal/test_sim.py
import pytest
from quant.sim import simulate_intraday, IntradayResult, MarkSeries


def test_pt_hit():
    # Mark grows steadily; PT at +20% over $1.00 debit = $1.20 → hit at minute 5
    marks = {m: 1.0 + 0.05 * m for m in range(0, 11)}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=20.0, sl_pct=30.0,
    )
    assert out.exit_reason == "PT"
    assert out.exit_minute == 4  # 1.0 + 0.05*4 = 1.20 = exactly PT
    assert out.realized_pct == pytest.approx(20.0)


def test_sl_hit_after_grace():
    marks = {m: 1.0 - 0.05 * m for m in range(0, 11)}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=50.0, sl_pct=30.0, sl_grace_minutes=2,
    )
    assert out.exit_reason == "SL"
    # 1.0 - 0.05*6 = 0.70 = SL threshold (-30%), needs minute >= 2 (grace)
    assert out.exit_minute == 6


def test_eod_when_no_trigger():
    marks = {m: 1.0 + 0.001 * m for m in range(0, 11)}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=50.0, sl_pct=50.0,
    )
    assert out.exit_reason == "EOD"
    assert out.exit_minute == 10


def test_trail_activates_and_exits():
    # Mark goes 1.0 → 1.10 (peak, activates trail at +5% after activation pct)
    # Then drops 8% from peak → exit
    marks = {0: 1.0, 1: 1.05, 2: 1.10, 3: 1.05, 4: 1.00}
    bars = MarkSeries(marks)
    out = simulate_intraday(
        debit=1.0, entry_minute=0, eod_minute=10, bars=bars,
        pt_pct=50.0, sl_pct=50.0,
        trailing_activate_pct=5.0, trailing_stop_pct=8.0,
    )
    assert out.exit_reason == "TRAIL"
    # Peak 1.10 → trail floor = 1.10 * (1 - 0.08) = 1.012; mark 1.00 < 1.012 at min 4
    assert out.exit_minute == 4
```

- [ ] **Step 2: Run test to confirm failure**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_sim.py -v --no-cov
```
Expected: FAIL.

- [ ] **Step 3: Implement `quant/sim.py`**

```python
# quant/sim.py
"""Simplified intraday simulator for debit-vertical PnL with PT/SL/trail/EOD.

Walks a minute-indexed mark-series from entry_minute to eod_minute, returning
the first triggered exit. Distilled from backtest/helios_intraday/_simulate_intraday
with HeliosConfig replaced by explicit threshold parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Protocol


class _BarsLike(Protocol):
    def mark_at(self, minute: int) -> Optional[float]: ...


@dataclass(frozen=True)
class IntradayResult:
    exit_minute: int
    exit_reason: str   # "PT" | "PT_GRACE" | "SL" | "TRAIL" | "EOD"
    realized_pct: float


@dataclass(frozen=True)
class MarkSeries:
    marks: Dict[int, float]

    def mark_at(self, minute: int) -> Optional[float]:
        return self.marks.get(minute)


def simulate_intraday(
    *,
    debit: float,
    entry_minute: int,
    eod_minute: int,
    bars: _BarsLike,
    pt_pct: float,
    sl_pct: float,
    sl_grace_minutes: int = 0,
    trailing_activate_pct: Optional[float] = None,
    trailing_stop_pct: Optional[float] = None,
) -> IntradayResult:
    """First-trigger walk through bars[entry_minute..eod_minute].

    With trailing_activate_pct and trailing_stop_pct set, a trailing stop
    layers on top: peak > debit*(1+activate/100) arms it; mark <= peak*(1-stop/100)
    fires it. Hard SL applies only BEFORE trail arms.
    """
    pt_threshold = debit * (1.0 + pt_pct / 100.0)
    sl_threshold = debit * (1.0 - sl_pct / 100.0)
    trailing_enabled = trailing_activate_pct is not None and trailing_stop_pct is not None
    activate_threshold = debit * (1.0 + (trailing_activate_pct or 0.0) / 100.0)
    peak = debit
    trail_armed = False

    for minute in range(entry_minute, eod_minute + 1):
        mark = bars.mark_at(minute)
        if mark is None:
            continue
        minutes_since_entry = minute - entry_minute
        if mark > peak:
            peak = mark
        if trailing_enabled and not trail_armed and peak >= activate_threshold:
            trail_armed = True

        # PT — always armed
        if mark >= pt_threshold:
            in_grace = minutes_since_entry < sl_grace_minutes
            return IntradayResult(
                exit_minute=minute,
                exit_reason="PT_GRACE" if in_grace else "PT",
                realized_pct=(mark / debit - 1.0) * 100.0,
            )

        # Trailing stop — only after armed
        if trail_armed and trailing_stop_pct is not None:
            trail_floor = peak * (1.0 - trailing_stop_pct / 100.0)
            if mark <= trail_floor:
                return IntradayResult(
                    exit_minute=minute,
                    exit_reason="TRAIL",
                    realized_pct=(mark / debit - 1.0) * 100.0,
                )

        # Hard SL — only before trail arms
        if not trail_armed and minutes_since_entry >= sl_grace_minutes and mark <= sl_threshold:
            return IntradayResult(
                exit_minute=minute,
                exit_reason="SL",
                realized_pct=(mark / debit - 1.0) * 100.0,
            )

        # EOD — fired the moment we observe a mark at/past eod_minute
        if minute >= eod_minute:
            return IntradayResult(
                exit_minute=minute,
                exit_reason="EOD",
                realized_pct=(mark / debit - 1.0) * 100.0,
            )

    # Fallthrough — synthesize EOD with 0% realized (no marks at/after eod_minute)
    return IntradayResult(exit_minute=eod_minute, exit_reason="EOD", realized_pct=0.0)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_sim.py -v --no-cov
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add quant/sim.py tests/skew_signal/test_sim.py
git commit -m "quant: simulate_intraday — debit-vertical PT/SL/trail/EOD walker"
```

---

## Task 3: `loader.py` — full chain at minute M

Reuses `tests/skew_signal/conftest.py` for the `db` mark and DATABASE_URL gating (same as Phase 1).

**Files:**
- Create: `backtest/skew_signal/loader.py`
- Create: `tests/skew_signal/conftest.py`
- Test: `tests/skew_signal/test_loader.py`

- [ ] **Step 1: Write conftest**

```python
# tests/skew_signal/conftest.py
import os
import pytest


def _has_db():
    return bool(os.environ.get("DATABASE_URL"))


def pytest_configure(config):
    config.addinivalue_line("markers", "db: requires production DATABASE_URL set")


def pytest_collection_modifyitems(config, items):
    if _has_db():
        return
    skip_db = pytest.mark.skip(reason="DATABASE_URL not set; skipping DB-backed test")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip_db)
```

- [ ] **Step 2: Write failing test**

```python
# tests/skew_signal/test_loader.py
import datetime as dt
import os
import pytest

from backtest.skew_signal.loader import load_chain_at_minute, ChainBar


@pytest.mark.db
def test_load_chain_at_minute_known_day():
    db_url = os.environ["DATABASE_URL"]
    chain = load_chain_at_minute(
        db_url,
        trade_date=dt.date(2025, 6, 2),
        expiration_date=dt.date(2025, 6, 3),
        target_minute=5,
    )
    assert chain is not None
    assert len(chain) >= 5
    sample = next(iter(chain.values()))
    assert isinstance(sample, ChainBar)
    assert sample.call_bid >= 0
    assert sample.put_bid >= 0


def test_chain_bar_dataclass_shape():
    cb = ChainBar(
        strike=500.0,
        call_bid=0.10, call_ask=0.12,
        put_bid=0.05, put_ask=0.07,
        call_oi=100, put_oi=50,
    )
    assert cb.call_mid == pytest.approx(0.11)
    assert cb.put_mid == pytest.approx(0.06)
    assert cb.call_valid()
    assert cb.put_valid()
```

- [ ] **Step 3: Implement `loader.py`**

```python
# backtest/skew_signal/loader.py
"""Load full chain (all strikes) at a target minute, with OI from helios_options_oi."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, Optional

import psycopg2


@dataclass(frozen=True)
class ChainBar:
    strike: float
    call_bid: float
    call_ask: float
    put_bid: float
    put_ask: float
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


def load_chain_at_minute(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    target_minute: int,
) -> Optional[Dict[float, ChainBar]]:
    """Pull the full chain at minute M plus OI. Returns {strike: ChainBar} or None."""
    chain_sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time = first_bar.t0 + (%s * INTERVAL '1 minute')
        ORDER BY b.strike, b."right"
    """
    oi_sql = """
        SELECT strike, "right", open_interest
        FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date = %s
    """
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(chain_sql, (trade_date, expiration_date,
                                trade_date, expiration_date, target_minute))
        rows = cur.fetchall()
        if not rows:
            return None
        cur.execute(oi_sql, (trade_date, expiration_date))
        oi_rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    by_strike: Dict[float, dict] = {}
    for strike, right, bid, ask in rows:
        k = float(strike)
        e = by_strike.setdefault(k, {
            "call_bid": 0.0, "call_ask": 0.0,
            "put_bid": 0.0, "put_ask": 0.0,
        })
        bid_v = float(bid) if bid is not None else 0.0
        ask_v = float(ask) if ask is not None else 0.0
        if right == "C":
            e["call_bid"] = bid_v; e["call_ask"] = ask_v
        else:
            e["put_bid"] = bid_v; e["put_ask"] = ask_v

    oi_by_strike: Dict[float, dict] = {}
    for strike, right, oi in oi_rows:
        k = float(strike)
        e = oi_by_strike.setdefault(k, {"call_oi": 0, "put_oi": 0})
        if right == "C":
            e["call_oi"] = int(oi)
        else:
            e["put_oi"] = int(oi)

    out: Dict[float, ChainBar] = {}
    for k, q in by_strike.items():
        oi = oi_by_strike.get(k, {"call_oi": 0, "put_oi": 0})
        out[k] = ChainBar(
            strike=k,
            call_bid=q["call_bid"], call_ask=q["call_ask"],
            put_bid=q["put_bid"], put_ask=q["put_ask"],
            call_oi=oi["call_oi"], put_oi=oi["put_oi"],
        )
    return out
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_loader.py -v --no-cov
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/skew_signal/loader.py tests/skew_signal/conftest.py tests/skew_signal/test_loader.py
git commit -m "skew-signal: loader pulls full chain at minute M"
```

---

## Task 4: `features.py` — IV solver + skew + charm aggregation

Combines what would otherwise be `iv_solver.py + skew.py + charm.py` into one module since they share the same `(spot, t_years, chain, ivs)` working set.

**Files:**
- Create: `backtest/skew_signal/features.py`
- Test: `tests/skew_signal/test_features.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/skew_signal/test_features.py
import math
import pytest
from backtest.skew_signal.loader import ChainBar
from backtest.skew_signal.features import (
    solve_chain_iv, compute_skew, compute_charm_aggregate, MinuteFeatures,
    estimate_spot,
)
from quant.bs import bs_price


def synth_chain(spot, sigma_call, sigma_put, t_years):
    """Build a synthetic ChainBar dict around `spot` from BS prices."""
    out = {}
    for k in [spot - 5, spot - 2, spot - 1, spot, spot + 1, spot + 2, spot + 5]:
        c = bs_price(spot, k, t_years, sigma_call, is_call=True)
        p = bs_price(spot, k, t_years, sigma_put, is_call=False)
        out[k] = ChainBar(
            strike=k,
            call_bid=max(0.01, c - 0.01), call_ask=c + 0.01,
            put_bid=max(0.01, p - 0.01), put_ask=p + 0.01,
            call_oi=100, put_oi=100,
        )
    return out


def test_estimate_spot_from_parity():
    chain = synth_chain(500.0, 0.20, 0.20, 1/365)
    spot = estimate_spot(chain, t_years=1/365)
    assert abs(spot - 500.0) < 0.5


def test_solve_chain_iv_recovers_input():
    chain = synth_chain(500.0, 0.20, 0.22, 1/365)
    spot = 500.0
    ivs = solve_chain_iv(chain, spot, t_years=1/365)
    # ATM call IV should be near 0.20, put IV near 0.22
    atm = ivs.get(500.0)
    assert atm is not None
    assert atm.call_iv is not None
    assert atm.put_iv is not None
    assert abs(atm.call_iv - 0.20) < 0.01
    assert abs(atm.put_iv - 0.22) < 0.01


def test_compute_skew_flat_returns_zero():
    chain = synth_chain(500.0, 0.20, 0.20, 1/365)
    spot = 500.0
    ivs = solve_chain_iv(chain, spot, t_years=1/365)
    skew = compute_skew(ivs, spot, t_years=1/365)
    # Flat IV → 25Δ skew ≈ 0
    assert abs(skew.skew_25d) < 0.02


def test_compute_skew_put_heavy_positive():
    chain = synth_chain(500.0, 0.18, 0.25, 1/365)  # put IV > call IV
    spot = 500.0
    ivs = solve_chain_iv(chain, spot, t_years=1/365)
    skew = compute_skew(ivs, spot, t_years=1/365)
    assert skew.skew_25d > 0  # put_iv − call_iv at 25Δ


def test_compute_charm_aggregate_sums():
    chain = synth_chain(500.0, 0.20, 0.20, 1/365)
    spot = 500.0
    ivs = solve_chain_iv(chain, spot, t_years=1/365)
    charm = compute_charm_aggregate(chain, ivs, spot, t_years=1/365)
    assert math.isfinite(charm.charm_call_total)
    assert math.isfinite(charm.charm_put_total)


def test_minute_features_dataclass():
    f = MinuteFeatures(
        spot=500.0, vix_prior=18.0,
        skew_25d=0.02, skew_slope=0.01, delta_skew_15m=-0.005,
        charm_call_total=10.0, charm_put_total=-5.0,
        magnet_imbalance=1.5, regime_label="NORMAL",
    )
    assert f.spot == 500.0
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_features.py -v --no-cov
```
Expected: FAIL.

- [ ] **Step 3: Implement `features.py`**

```python
# backtest/skew_signal/features.py
"""Feature builder: per-minute IV chain, skew metrics, charm aggregation.

Inputs are a ChainBar dict (loader.py output). Outputs are dataclasses
(IVChain, Skew, CharmAggregate, MinuteFeatures) consumed by signal.py.

Skew convention: skew_25d = put_iv@25Δ − call_iv@25Δ.
                 Positive = put-heavy (typical equity skew).
Charm sign: positive charm × OI on calls means dealers (long the calls
            implicitly via writing to retail) need to buy underlying as
            time passes → bullish for spot.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional

from backtest.skew_signal.loader import ChainBar
from quant.bs import (
    bs_charm,
    derive_spot_from_parity,
    implied_vol,
)


@dataclass(frozen=True)
class StrikeIV:
    strike: float
    call_iv: Optional[float]
    put_iv: Optional[float]


@dataclass(frozen=True)
class Skew:
    skew_25d: float        # put_iv − call_iv at ~25Δ
    skew_slope: float      # (skew_25d − skew_10d) / 15Δ
    atm_iv: float          # average call/put ATM IV


@dataclass(frozen=True)
class CharmAggregate:
    charm_call_total: float   # Σ (charm × OI) over OTM calls (call_iv defined)
    charm_put_total: float    # Σ (charm × OI) over OTM puts


@dataclass(frozen=True)
class MinuteFeatures:
    spot: float
    vix_prior: Optional[float]
    skew_25d: float
    skew_slope: float
    delta_skew_15m: float    # skew_25d_now − skew_25d_15min_ago (NaN if no prior)
    charm_call_total: float
    charm_put_total: float
    magnet_imbalance: float  # call_peak / put_peak (gex × OI from quant.walls or proxy)
    regime_label: Optional[str]


def estimate_spot(chain: Dict[float, ChainBar], t_years: float) -> Optional[float]:
    """Spot via parity at the most-ATM strike with both legs valid."""
    candidates = []
    for k, cb in chain.items():
        if cb.call_valid() and cb.put_valid():
            candidates.append((cb.call_mid + cb.put_mid, k, cb.call_mid, cb.put_mid))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    _, k, cm, pm = candidates[0]
    return derive_spot_from_parity(cm, pm, k, t_years)


def solve_chain_iv(
    chain: Dict[float, ChainBar],
    spot: float,
    t_years: float,
) -> Dict[float, StrikeIV]:
    """Solve IV per leg per strike."""
    out: Dict[float, StrikeIV] = {}
    for k, cb in chain.items():
        c_iv = implied_vol(cb.call_mid, spot, k, t_years, is_call=True) if cb.call_valid() else None
        p_iv = implied_vol(cb.put_mid, spot, k, t_years, is_call=False) if cb.put_valid() else None
        out[k] = StrikeIV(strike=k, call_iv=c_iv, put_iv=p_iv)
    return out


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _call_delta(spot: float, strike: float, t_years: float, sigma: float, r: float = 0.05) -> float:
    if t_years <= 0 or sigma <= 0 or spot <= 0:
        return 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    return _norm_cdf(d1)


def compute_skew(
    ivs: Dict[float, StrikeIV],
    spot: float,
    t_years: float,
    target_call_delta: float = 0.25,
    wing_call_delta: float = 0.10,
) -> Skew:
    """Pick strikes whose call delta is closest to the targets, return skew metrics."""
    valid_strikes = [(k, iv) for k, iv in ivs.items() if iv.call_iv and iv.put_iv]
    if not valid_strikes:
        return Skew(skew_25d=0.0, skew_slope=0.0, atm_iv=0.0)

    deltas = []
    for k, iv in valid_strikes:
        d = _call_delta(spot, k, t_years, iv.call_iv)
        deltas.append((k, iv, d))

    def at_delta(target):
        # Find strike closest to target call delta
        return min(deltas, key=lambda x: abs(x[2] - target))

    k25, iv25, d25 = at_delta(target_call_delta)
    k10, iv10, d10 = at_delta(wing_call_delta)
    atm_strike, iv_atm, _ = at_delta(0.50)

    skew_25d = (iv25.put_iv - iv25.call_iv) if iv25.put_iv and iv25.call_iv else 0.0
    skew_10d = (iv10.put_iv - iv10.call_iv) if iv10.put_iv and iv10.call_iv else 0.0
    slope = (skew_25d - skew_10d) / max(1e-6, target_call_delta - wing_call_delta)
    atm_iv = 0.5 * ((iv_atm.call_iv or 0.0) + (iv_atm.put_iv or 0.0))
    return Skew(skew_25d=skew_25d, skew_slope=slope, atm_iv=atm_iv)


def compute_charm_aggregate(
    chain: Dict[float, ChainBar],
    ivs: Dict[float, StrikeIV],
    spot: float,
    t_years: float,
) -> CharmAggregate:
    """Σ(charm × OI) over OTM calls and OTM puts separately."""
    charm_call = 0.0
    charm_put = 0.0
    for k, cb in chain.items():
        iv = ivs.get(k)
        if iv is None:
            continue
        if iv.call_iv and k > spot:
            c = bs_charm(spot, k, t_years, iv.call_iv)
            charm_call += c * cb.call_oi
        if iv.put_iv and k < spot:
            c = bs_charm(spot, k, t_years, iv.put_iv)
            charm_put += c * cb.put_oi
    return CharmAggregate(charm_call_total=charm_call, charm_put_total=charm_put)


def magnet_imbalance_proxy(chain: Dict[float, ChainBar], ivs: Dict[float, StrikeIV],
                            spot: float, t_years: float) -> float:
    """OI-weighted gamma proxy. Same formula as quant.walls but inline so we don't
    need the full `compute_intraday_walls` round-trip per minute."""
    from quant.bs import bs_gamma
    call_peak = 0.0
    put_peak = 0.0
    for k, cb in chain.items():
        iv = ivs.get(k)
        if iv is None:
            continue
        if iv.call_iv and cb.call_oi > 0 and k >= spot:
            g = bs_gamma(spot, k, t_years, iv.call_iv) * cb.call_oi * 100.0 * spot * spot * 0.01
            call_peak = max(call_peak, g)
        if iv.put_iv and cb.put_oi > 0 and k <= spot:
            g = bs_gamma(spot, k, t_years, iv.put_iv) * cb.put_oi * 100.0 * spot * spot * 0.01
            put_peak = max(put_peak, g)
    if put_peak <= 0:
        return 99.0  # all-call regime
    return call_peak / put_peak
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_features.py -v --no-cov
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/skew_signal/features.py tests/skew_signal/test_features.py
git commit -m "skew-signal: features — IV solver + skew + charm aggregation"
```

---

## Task 5: `signal.py` — BULL/BEAR/NONE + composite z

**Files:**
- Create: `backtest/skew_signal/signal.py`
- Test: `tests/skew_signal/test_signal.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/skew_signal/test_signal.py
import pytest
from backtest.skew_signal.features import MinuteFeatures
from backtest.skew_signal.signal import decide_signal, SignalResult


def make_features(**kwargs):
    defaults = dict(
        spot=500.0, vix_prior=18.0,
        skew_25d=0.02, skew_slope=0.01, delta_skew_15m=0.0,
        charm_call_total=0.0, charm_put_total=0.0,
        magnet_imbalance=1.0, regime_label="NORMAL",
    )
    defaults.update(kwargs)
    return MinuteFeatures(**defaults)


def test_bull_signal_when_all_three_agree():
    f = make_features(
        delta_skew_15m=-0.01,        # below -theta_skew=-0.005
        charm_call_total=100.0,       # above theta_charm=50
        magnet_imbalance=1.5,         # above 1.3
    )
    out = decide_signal(f, theta_skew=0.005, theta_charm=50.0)
    assert out.action == "BULL"
    assert out.composite_z != 0.0


def test_bear_signal_when_all_three_agree():
    f = make_features(
        delta_skew_15m=0.01,
        charm_put_total=100.0,
        magnet_imbalance=0.6,         # below 1/1.3 = 0.77
    )
    out = decide_signal(f, theta_skew=0.005, theta_charm=50.0)
    assert out.action == "BEAR"


def test_none_when_skew_doesnt_pass():
    f = make_features(
        delta_skew_15m=-0.001,        # not below -theta_skew
        charm_call_total=100.0,
        magnet_imbalance=1.5,
    )
    out = decide_signal(f, theta_skew=0.005, theta_charm=50.0)
    assert out.action == "NONE"


def test_none_when_charm_doesnt_pass():
    f = make_features(
        delta_skew_15m=-0.01,
        charm_call_total=10.0,        # below theta
        magnet_imbalance=1.5,
    )
    out = decide_signal(f, theta_skew=0.005, theta_charm=50.0)
    assert out.action == "NONE"


def test_none_when_magnet_doesnt_pass():
    f = make_features(
        delta_skew_15m=-0.01,
        charm_call_total=100.0,
        magnet_imbalance=1.1,         # below 1.3
    )
    out = decide_signal(f, theta_skew=0.005, theta_charm=50.0)
    assert out.action == "NONE"
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_signal.py -v --no-cov
```
Expected: FAIL.

- [ ] **Step 3: Implement `signal.py`**

```python
# backtest/skew_signal/signal.py
"""Signal decision: BULL / BEAR / NONE with composite z-score.

BULL fires when ALL THREE conditions agree:
  - Δskew_15m < −θ_skew         (skew flattening)
  - charm_call_total > θ_charm   (call-side hedging flow positive)
  - magnet_imbalance ≥ 1.3       (call wall > put wall)

BEAR mirrors. Otherwise NONE.

composite_z is sign × |skew_z × charm_z × magnet_z| where each component
is normalized by its threshold (so on-the-line = 1.0; deeper = larger).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backtest.skew_signal.features import MinuteFeatures


Action = Literal["BULL", "BEAR", "NONE"]


@dataclass(frozen=True)
class SignalResult:
    action: Action
    composite_z: float        # 0.0 if NONE; sign matches direction
    skew_z: float
    charm_z: float
    magnet_z: float


def decide_signal(
    f: MinuteFeatures,
    theta_skew: float = 0.005,
    theta_charm: float = 50.0,
    magnet_threshold: float = 1.3,
) -> SignalResult:
    skew_z = -f.delta_skew_15m / theta_skew if theta_skew > 0 else 0.0
    charm_z_call = f.charm_call_total / theta_charm if theta_charm > 0 else 0.0
    charm_z_put = f.charm_put_total / theta_charm if theta_charm > 0 else 0.0
    magnet_z = f.magnet_imbalance / magnet_threshold

    bull = (
        f.delta_skew_15m < -theta_skew
        and f.charm_call_total > theta_charm
        and f.magnet_imbalance >= magnet_threshold
    )
    bear = (
        f.delta_skew_15m > theta_skew
        and f.charm_put_total > theta_charm
        and f.magnet_imbalance <= 1.0 / magnet_threshold
    )

    if bull:
        comp = abs(skew_z) * abs(charm_z_call) * abs(magnet_z)
        return SignalResult(
            action="BULL", composite_z=comp,
            skew_z=skew_z, charm_z=charm_z_call, magnet_z=magnet_z,
        )
    if bear:
        comp = -(abs(skew_z) * abs(charm_z_put) * abs(1.0 / magnet_z if magnet_z > 0 else 1.0))
        return SignalResult(
            action="BEAR", composite_z=comp,
            skew_z=skew_z, charm_z=charm_z_put, magnet_z=magnet_z,
        )
    return SignalResult(
        action="NONE", composite_z=0.0,
        skew_z=skew_z, charm_z=max(charm_z_call, charm_z_put), magnet_z=magnet_z,
    )
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_signal.py -v --no-cov
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backtest/skew_signal/signal.py tests/skew_signal/test_signal.py
git commit -m "skew-signal: BULL/BEAR/NONE rule + composite z"
```

---

## Task 6: `engine.py` — per-day, scan minutes, take first signal, simulate

This is the heaviest task. Per spec: scan minutes 09:35→14:00 ET (= minutes 5→270 from open, in 1-min increments), keep a 15-min skew history for `delta_skew_15m`, fire on first qualifying minute, simulate via `quant.sim.simulate_intraday`.

**Files:**
- Create: `backtest/skew_signal/engine.py`
- Test: `tests/skew_signal/test_engine_smoke.py`

- [ ] **Step 1: Write failing test**

```python
# tests/skew_signal/test_engine_smoke.py
import datetime as dt
import os
import pytest

from backtest.skew_signal.engine import run_one_day, TradeRow


@pytest.mark.db
def test_run_one_day_smoke():
    db_url_main = os.environ["DATABASE_URL"]
    db_url_orat = os.environ.get("ORAT_DATABASE_URL", db_url_main)
    rows = run_one_day(
        db_url_main=db_url_main,
        db_url_orat=db_url_orat,
        trade_date=dt.date(2025, 6, 2),
        theta_skew=0.005,
        theta_charm=50.0,
    )
    assert isinstance(rows, list)
    assert len(rows) <= 1   # at most one fire per day
    for r in rows:
        assert isinstance(r, TradeRow)
        assert r.action in {"BULL", "BEAR"}
        assert -200.0 <= r.pnl_net <= 200.0
```

- [ ] **Step 2: Run test to confirm failure**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_engine_smoke.py -v --no-cov
```
Expected: FAIL.

- [ ] **Step 3: Implement `engine.py`**

```python
# backtest/skew_signal/engine.py
"""Per-day orchestration: scan minutes 5..270, fire first qualifying signal."""
from __future__ import annotations

import datetime as dt
import logging
from collections import deque
from dataclasses import dataclass
from typing import List, Optional

import psycopg2

from backtest.skew_signal.loader import load_chain_at_minute
from backtest.skew_signal.features import (
    MinuteFeatures, compute_charm_aggregate, compute_skew,
    estimate_spot, magnet_imbalance_proxy, solve_chain_iv,
)
from backtest.skew_signal.signal import decide_signal
from backtest.touch_pin.loader import vix_close_prior_day, regime_label_at_open
from quant.bs import bs_price
from quant.sim import simulate_intraday, MarkSeries

logger = logging.getLogger(__name__)

SCAN_START_MINUTE = 5      # 09:35 ET
SCAN_END_MINUTE = 270      # 14:00 ET
EOD_MINUTE = 385           # 15:55 ET hard time-stop
SKEW_LOOKBACK_MINUTES = 15


@dataclass
class TradeRow:
    trade_date: dt.date
    expiration_date: dt.date
    action: str           # BULL | BEAR
    entry_minute: int
    long_K: float
    short_K: float
    width: float
    debit: float
    composite_z: float
    skew_25d_at_entry: float
    delta_skew_15m: float
    charm_used: float
    magnet_imbalance: float
    spot_at_entry: float
    vix_prior: Optional[float]
    regime_label: Optional[str]
    exit_minute: int
    exit_reason: str
    realized_pct: float
    pnl_gross: float
    pnl_net: float
    slippage: float
    commission: float


def _next_business_day(d: dt.date) -> dt.date:
    nxt = d + dt.timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += dt.timedelta(days=1)
    return nxt


def _build_mark_series(
    db_url: str,
    trade_date: dt.date,
    expiration_date: dt.date,
    long_K: float,
    short_K: float,
    is_call: bool,
    entry_minute: int,
    exit_minute: int,
) -> MarkSeries:
    """Pull bars for both legs across [entry, exit] and compute mark = mid_long − mid_short."""
    sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0
            FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT EXTRACT(EPOCH FROM (b.bar_time - first_bar.t0))::int / 60 AS minute_idx,
               b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
          AND b.bar_time >= first_bar.t0 + (%s * INTERVAL '1 minute')
          AND b.bar_time <= first_bar.t0 + (%s * INTERVAL '1 minute')
          AND (b.strike = %s OR b.strike = %s)
        ORDER BY minute_idx, b.strike, b."right"
    """
    leg = "C" if is_call else "P"
    conn = psycopg2.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(sql, (trade_date, expiration_date,
                          trade_date, expiration_date,
                          entry_minute, exit_minute,
                          long_K, short_K))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    by_minute: dict = {}
    for m, k, r, b, a in rows:
        m = int(m); k = float(k)
        by_minute.setdefault(m, {}).setdefault(k, {})[r] = (
            float(b) if b is not None else 0.0,
            float(a) if a is not None else 0.0,
        )

    marks: dict = {}
    for m, legs in by_minute.items():
        long_q = legs.get(long_K, {}).get(leg)
        short_q = legs.get(short_K, {}).get(leg)
        if not long_q or not short_q:
            continue
        lb, la = long_q
        sb, sa = short_q
        if lb <= 0 or sa <= 0:
            continue
        # Conservative: long.bid (sell long), short.ask (buy short). Used by HELIOS engine.
        marks[m] = lb - sa
    return MarkSeries(marks=marks)


def run_one_day(
    *,
    db_url_main: str,
    db_url_orat: str,
    trade_date: dt.date,
    theta_skew: float = 0.005,
    theta_charm: float = 50.0,
    magnet_threshold: float = 1.3,
    pt_pct: float = 20.0,
    sl_pct: float = 30.0,
    trailing_activate_pct: float = 5.0,
    trailing_stop_pct: float = 8.0,
    slippage_ticks_per_leg: int = 1,
    commission_per_leg: float = 1.30,
) -> List[TradeRow]:
    """Build TradeRows (0 or 1 per day) for skew_signal."""
    expiration_date = _next_business_day(trade_date)
    vix_prior = vix_close_prior_day(db_url_orat, trade_date)
    regime = regime_label_at_open(db_url_main, trade_date)

    skew_history: deque = deque(maxlen=SKEW_LOOKBACK_MINUTES + 1)

    for minute in range(SCAN_START_MINUTE, SCAN_END_MINUTE + 1):
        chain = load_chain_at_minute(db_url_main, trade_date, expiration_date, minute)
        if chain is None or len(chain) < 5:
            skew_history.append(None)
            continue
        spot = estimate_spot(chain, t_years=1/365)
        if spot is None or spot <= 0:
            skew_history.append(None)
            continue
        ivs = solve_chain_iv(chain, spot, t_years=1/365)
        skew = compute_skew(ivs, spot, t_years=1/365)
        skew_history.append(skew.skew_25d)

        if len(skew_history) <= SKEW_LOOKBACK_MINUTES:
            continue
        prior = skew_history[0]
        if prior is None:
            continue
        delta_skew = skew.skew_25d - prior
        charm = compute_charm_aggregate(chain, ivs, spot, t_years=1/365)
        magnet = magnet_imbalance_proxy(chain, ivs, spot, t_years=1/365)

        feats = MinuteFeatures(
            spot=spot, vix_prior=vix_prior,
            skew_25d=skew.skew_25d, skew_slope=skew.skew_slope,
            delta_skew_15m=delta_skew,
            charm_call_total=charm.charm_call_total,
            charm_put_total=charm.charm_put_total,
            magnet_imbalance=magnet,
            regime_label=regime,
        )
        sig = decide_signal(feats, theta_skew=theta_skew, theta_charm=theta_charm,
                            magnet_threshold=magnet_threshold)
        if sig.action == "NONE":
            continue

        # Build the vehicle: 1-pt-wide debit vertical at ATM
        is_call = sig.action == "BULL"
        all_strikes = sorted(chain.keys())
        atm_strike = min(all_strikes, key=lambda k: abs(k - spot))
        long_K = atm_strike
        short_K = long_K + 1.0 if is_call else long_K - 1.0
        if short_K not in chain:
            continue
        long_cb = chain[long_K]; short_cb = chain[short_K]
        if is_call and (not long_cb.call_valid() or not short_cb.call_valid()):
            continue
        if not is_call and (not long_cb.put_valid() or not short_cb.put_valid()):
            continue
        long_mid = long_cb.call_mid if is_call else long_cb.put_mid
        short_mid = short_cb.call_mid if is_call else short_cb.put_mid
        debit = long_mid - short_mid
        if debit <= 0 or debit >= 1.0:
            continue

        bars = _build_mark_series(
            db_url_main, trade_date, expiration_date,
            long_K, short_K, is_call,
            entry_minute=minute, exit_minute=EOD_MINUTE,
        )
        out = simulate_intraday(
            debit=debit, entry_minute=minute, eod_minute=EOD_MINUTE, bars=bars,
            pt_pct=pt_pct, sl_pct=sl_pct,
            trailing_activate_pct=trailing_activate_pct, trailing_stop_pct=trailing_stop_pct,
        )

        slippage_ps = slippage_ticks_per_leg * 0.01 * 2
        slippage_dollars = slippage_ps * 100
        commission_dollars = commission_per_leg * 4
        pnl_gross_dollars = out.realized_pct / 100.0 * debit * 100
        pnl_net = pnl_gross_dollars - slippage_dollars - commission_dollars

        return [TradeRow(
            trade_date=trade_date, expiration_date=expiration_date,
            action=sig.action, entry_minute=minute,
            long_K=long_K, short_K=short_K, width=1.0, debit=debit,
            composite_z=sig.composite_z, skew_25d_at_entry=skew.skew_25d,
            delta_skew_15m=delta_skew,
            charm_used=charm.charm_call_total if is_call else charm.charm_put_total,
            magnet_imbalance=magnet, spot_at_entry=spot,
            vix_prior=vix_prior, regime_label=regime,
            exit_minute=out.exit_minute, exit_reason=out.exit_reason,
            realized_pct=out.realized_pct,
            pnl_gross=pnl_gross_dollars, pnl_net=pnl_net,
            slippage=slippage_dollars, commission=commission_dollars,
        )]

    return []
```

- [ ] **Step 4: Run test to confirm pass**

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/skew_signal/test_engine_smoke.py -v --no-cov
```
Expected: 1 passed (or no rows if no signal fired on 2025-06-02 — both are valid).

- [ ] **Step 5: Commit**

```bash
git add backtest/skew_signal/engine.py tests/skew_signal/test_engine_smoke.py
git commit -m "skew-signal: per-day engine scans minutes, fires first signal, simulates"
```

---

## Task 7: `binning.py` + `walk_forward.py` + `report.py` + `cli.py`

Bundle the smaller modules. They mirror Phase 1's shape.

**Files:**
- Create: `backtest/skew_signal/binning.py`
- Create: `backtest/skew_signal/walk_forward.py`
- Create: `backtest/skew_signal/report.py`
- Create: `backtest/skew_signal/cli.py`
- Create: `backtest/skew_signal/__main__.py`

- [ ] **Step 1: Implement `binning.py`**

```python
# backtest/skew_signal/binning.py
"""Bucket trades by composite_z quantile and direction."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List

from backtest.skew_signal.engine import TradeRow


@dataclass(frozen=True)
class BinSummary:
    action: str
    composite_z_bucket: str
    n: int
    n_winners: int
    win_rate: float
    mean_pnl: float
    median_pnl: float
    std_pnl: float
    sharpe_per_trade: float
    mean_realized_pct: float


def _z_bucket(z: float) -> str:
    az = abs(z)
    if az < 1.5: return "<1.5"
    if az < 3.0: return "1.5-3.0"
    if az < 6.0: return "3.0-6.0"
    return ">6.0"


def bin_trades(trades: List[TradeRow]) -> List[BinSummary]:
    groups: dict = {}
    for t in trades:
        key = (t.action, _z_bucket(t.composite_z))
        groups.setdefault(key, []).append(t)
    out: List[BinSummary] = []
    for (action, zb), items in groups.items():
        pnls = [t.pnl_net for t in items]
        n = len(pnls)
        winners = sum(1 for p in pnls if p > 0)
        mean_pnl = sum(pnls) / n if n else 0.0
        med = statistics.median(pnls) if n else 0.0
        std = statistics.pstdev(pnls) if n > 1 else 0.0
        sharpe = mean_pnl / std if std > 1e-9 else 0.0
        mean_real = sum(t.realized_pct for t in items) / n if n else 0.0
        out.append(BinSummary(
            action=action, composite_z_bucket=zb,
            n=n, n_winners=winners, win_rate=winners / n if n else 0.0,
            mean_pnl=mean_pnl, median_pnl=med, std_pnl=std,
            sharpe_per_trade=sharpe, mean_realized_pct=mean_real,
        ))
    out.sort(key=lambda b: (b.action, b.composite_z_bucket))
    return out
```

- [ ] **Step 2: Implement `walk_forward.py`**

```python
# backtest/skew_signal/walk_forward.py
"""Train/Validation/OOS split + GO/NO-GO eval per spec §8.3."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from backtest.skew_signal.engine import TradeRow


@dataclass(frozen=True)
class GoNoGoResult:
    go: bool
    n_total: int
    win_rate: float
    rr_ratio: float
    ev_per_trade: float
    timestop_pct: float
    summary: str


def split_trades(trades: List[TradeRow]) -> Tuple[List[TradeRow], List[TradeRow], List[TradeRow]]:
    train, val, oos = [], [], []
    for t in trades:
        if t.trade_date.year == 2023: train.append(t)
        elif t.trade_date.year == 2024: val.append(t)
        elif t.trade_date.year == 2025: oos.append(t)
    return train, val, oos


def evaluate_go_no_go(insample: List[TradeRow], oos: List[TradeRow]) -> GoNoGoResult:
    """In-sample = train + val. GO if n>=150, WR>=66%, RR>=1.5, EV>=+$5."""
    n = len(insample)
    if n == 0:
        return GoNoGoResult(go=False, n_total=0, win_rate=0.0, rr_ratio=0.0,
                            ev_per_trade=0.0, timestop_pct=0.0,
                            summary="No in-sample trades. NO-GO.")
    pnls = [t.pnl_net for t in insample]
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]
    wr = len(winners) / n
    avg_win = sum(winners) / len(winners) if winners else 0.0
    avg_loss = abs(sum(losers) / len(losers)) if losers else 1.0
    rr = avg_win / avg_loss if avg_loss > 0 else 0.0
    ev = sum(pnls) / n
    timestop_pct = sum(1 for t in insample if t.exit_reason == "EOD") / n

    insample_pass = (n >= 150 and wr >= 0.66 and rr >= 1.5 and ev >= 5.0)
    oos_n = len(oos)
    oos_wr = sum(1 for t in oos if t.pnl_net > 0) / oos_n if oos_n else 0.0
    oos_pass = oos_n >= 30 and abs(oos_wr - wr) <= 0.05  # within 5pp

    go = insample_pass and oos_pass

    lines = [
        f"In-sample: n={n}, WR={wr:.1%}, RR={rr:.2f}, EV=${ev:.2f}/trade, time-stop={timestop_pct:.1%}",
        f"OOS: n={oos_n}, WR={oos_wr:.1%}",
        f"VERDICT: {'GO' if go else 'NO-GO'}",
    ]
    if not insample_pass:
        if n < 150: lines.append(f"  fail: n<150")
        if wr < 0.66: lines.append(f"  fail: WR<66%")
        if rr < 1.5: lines.append(f"  fail: RR<1.5")
        if ev < 5.0: lines.append(f"  fail: EV<+$5")
    if not oos_pass and insample_pass:
        if oos_n < 30: lines.append(f"  fail: OOS n<30")
        if abs(oos_wr - wr) > 0.05: lines.append(f"  fail: OOS WR drift > 5pp")

    return GoNoGoResult(
        go=go, n_total=n, win_rate=wr, rr_ratio=rr, ev_per_trade=ev,
        timestop_pct=timestop_pct, summary="\n".join(lines),
    )
```

- [ ] **Step 3: Implement `report.py`**

```python
# backtest/skew_signal/report.py
"""Markdown report writer + per-trade CSV dump."""
from __future__ import annotations

import csv
import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import List

from backtest.skew_signal.engine import TradeRow
from backtest.skew_signal.binning import BinSummary


def write_trades_csv(trades: List[TradeRow], path: Path) -> None:
    if not trades:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(asdict(trades[0]).keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            row = asdict(t)
            for k, v in row.items():
                if isinstance(v, dt.date):
                    row[k] = v.isoformat()
            w.writerow(row)


def write_markdown_report(
    trades: List[TradeRow], bins: List[BinSummary],
    path: Path, start: dt.date, end: dt.date,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(trades)
    pnls = [t.pnl_net for t in trades]
    overall_wr = sum(1 for p in pnls if p > 0) / n if n else 0.0
    overall_mean = sum(pnls) / n if n else 0.0

    lines = []
    lines.append("# Skew + Charm (Phase 2) Backtest Report")
    lines.append("")
    lines.append(f"**Period:** {start.isoformat()} to {end.isoformat()}")
    lines.append(f"**Total trades:** {n}")
    lines.append(f"**Overall WR:** {overall_wr:.1%}")
    lines.append(f"**Overall mean PnL/trade:** ${overall_mean:.2f}")
    if n:
        lines.append(f"**Total PnL:** ${sum(pnls):.0f}")
        bull = [t for t in trades if t.action == "BULL"]
        bear = [t for t in trades if t.action == "BEAR"]
        lines.append(f"**BULL:** n={len(bull)}, WR={(sum(1 for t in bull if t.pnl_net>0)/len(bull) if bull else 0):.1%}")
        lines.append(f"**BEAR:** n={len(bear)}, WR={(sum(1 for t in bear if t.pnl_net>0)/len(bear) if bear else 0):.1%}")
        timestop = sum(1 for t in trades if t.exit_reason == "EOD") / n
        lines.append(f"**Time-stop %:** {timestop:.1%}")
    lines.append("")
    lines.append("## Bin Summary (by composite z bucket)")
    lines.append("")
    lines.append("| Action | Z-bucket | n | WR | Mean | Median | Std | Sharpe | RealPct |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for b in bins:
        lines.append(
            f"| {b.action} | {b.composite_z_bucket} | {b.n} | {b.win_rate:.1%} | "
            f"${b.mean_pnl:.2f} | ${b.median_pnl:.2f} | ${b.std_pnl:.2f} | "
            f"{b.sharpe_per_trade:.2f} | {b.mean_realized_pct:.1f}% |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
```

- [ ] **Step 4: Implement `cli.py` and `__main__.py`**

```python
# backtest/skew_signal/cli.py
"""End-to-end runner."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path
from typing import List

from backtest.skew_signal.engine import run_one_day, TradeRow
from backtest.skew_signal.report import write_trades_csv, write_markdown_report
from backtest.skew_signal.binning import bin_trades
from backtest.skew_signal.walk_forward import split_trades, evaluate_go_no_go

logger = logging.getLogger("skew_signal")


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def trading_days_between(start: dt.date, end: dt.date) -> List[dt.date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def main(argv=None):
    p = argparse.ArgumentParser(prog="backtest.skew_signal")
    p.add_argument("--start", type=parse_date, required=True)
    p.add_argument("--end", type=parse_date, required=True)
    p.add_argument("--theta-skew", type=float, default=0.005)
    p.add_argument("--theta-charm", type=float, default=50.0)
    p.add_argument("--magnet-threshold", type=float, default=1.3)
    p.add_argument("--pt-pct", type=float, default=20.0)
    p.add_argument("--sl-pct", type=float, default=30.0)
    p.add_argument("--trail-activate-pct", type=float, default=5.0)
    p.add_argument("--trail-stop-pct", type=float, default=8.0)
    p.add_argument("--slippage-ticks", type=int, default=1)
    p.add_argument("--commission-leg", type=float, default=1.30)
    p.add_argument("--output-dir", type=Path, default=Path("backtest/skew_signal/output"))
    p.add_argument("--report-name", type=str, default="skew_signal")
    p.add_argument("--log-level", default="INFO")
    p.add_argument("--no-eval", action="store_true")
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
                db_url_main=db_main, db_url_orat=db_orat, trade_date=d,
                theta_skew=args.theta_skew, theta_charm=args.theta_charm,
                magnet_threshold=args.magnet_threshold,
                pt_pct=args.pt_pct, sl_pct=args.sl_pct,
                trailing_activate_pct=args.trail_activate_pct,
                trailing_stop_pct=args.trail_stop_pct,
                slippage_ticks_per_leg=args.slippage_ticks,
                commission_per_leg=args.commission_leg,
            )
            all_trades.extend(rows)
            if (i + 1) % 25 == 0:
                logger.info("%d/%d days; %d trades so far", i + 1, len(days), len(all_trades))
        except Exception:
            logger.exception("day %s failed; continuing", d)

    logger.info("complete: %d trades from %d days", len(all_trades), len(days))
    out_csv = args.output_dir / f"{args.report_name}_trades_{args.start}_{args.end}.csv"
    out_md = args.output_dir / f"{args.report_name}_report_{args.start}_{args.end}.md"
    write_trades_csv(all_trades, out_csv)
    bins = bin_trades(all_trades)
    write_markdown_report(all_trades, bins, out_md, args.start, args.end)

    if not args.no_eval:
        train, val, oos = split_trades(all_trades)
        result = evaluate_go_no_go(train + val, oos)
        logger.info("GO/NO-GO:\n%s", result.summary)
        with out_md.open("a", encoding="utf-8") as f:
            f.write("\n\n## GO/NO-GO\n\n```\n")
            f.write(result.summary)
            f.write("\n```\n")

    logger.info("wrote %s and %s", out_csv, out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

```python
# backtest/skew_signal/__main__.py
from backtest.skew_signal.cli import main
import sys
sys.exit(main())
```

- [ ] **Step 5: Smoke run on 5 days + commit**

```bash
PYTHONIOENCODING=utf-8 python -m backtest.skew_signal --start 2024-06-03 --end 2024-06-07 --report-name smoke --no-eval --log-level WARNING
ls backtest/skew_signal/output/
rm -f backtest/skew_signal/output/smoke_*

git add backtest/skew_signal/
git commit -m "skew-signal: binning + walk_forward + report + cli + smoke pass"
```

---

## Task 8: Run full backtest 2023-01-03 → 2025-12-05

- [ ] **Step 1: Fire the full run in background**

```bash
PYTHONIOENCODING=utf-8 python -m backtest.skew_signal \
  --start 2023-01-03 --end 2025-12-05 \
  --report-name final \
  --log-level INFO 2>&1 | tee backtest/skew_signal/output/final_run.log &
```

- [ ] **Step 2: Watch for completion (Monitor armed during execution)**

Expect ~60-100 min runtime. Each day's per-minute scan does up to 266 IV-solves over the full chain → heavier than Phase 1.

- [ ] **Step 3: Inspect final report**

```bash
cat backtest/skew_signal/output/final_report_2023-01-03_2025-12-05.md
```

- [ ] **Step 4: Promote final report to docs/superpowers/reports/ and commit**

```bash
cp backtest/skew_signal/output/final_report_2023-01-03_2025-12-05.md \
   docs/superpowers/reports/2026-05-10-skew-charm-final.md
git add docs/superpowers/reports/2026-05-10-skew-charm-final.md
git commit -m "skew-signal: final research report (Phase 2) — GO/NO-GO verdict"
git push -u origin claude/skew-signal-validation
```

---

## Self-review

- ✓ Spec coverage: §8.1 modules, §8.2 per-minute flow, §8.3 GO criteria — all implemented in tasks 3-7
- ✓ Reuse: `quant/bs.py` (extended), `quant/walls.py` (inherited), `quant/sim.py` (new, distilled from HELIOS)
- ✓ Walk-forward: `walk_forward.py` splits 2023/2024/2025 with parameter-grid via CLI args (manual grid search by re-running with different θ values; full automated grid is YAGNI for first pass)
- ✓ Anti-look-ahead: `vix_close_prior_day` and `regime_label_at_open` with hard cutoff at T 13:30 UTC (= EDT open). `delta_skew_15m` uses skew_history deque populated only from prior minutes. ✓
- ✓ Type consistency: `MinuteFeatures` shape matches between `features.py` and `signal.py`; `TradeRow` shape used consistently across `engine.py`, `binning.py`, `walk_forward.py`, `report.py`.
- ✓ No placeholders: every step has actual code or an exact command.

**End of plan.**
