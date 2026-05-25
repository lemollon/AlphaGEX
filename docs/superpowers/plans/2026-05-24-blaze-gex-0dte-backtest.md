# BLAZE GEX-on-0DTE Backtest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruct GEX walls from the 0DTE option chain and backtest BLAZE's real `wall_fade`/`wall_break`/`flip_cross` signals on 850 sessions of 0DTE SPY, producing a per-setup/per-year/per-regime GO-NO-GO report.

**Architecture:** A new `backtest/blaze_gex_0dte/` package. Per trading day: load all 1-min 0DTE option bars + OI once (`loader.py`), reconstruct a per-minute `GexSnapshot` stream (`reconstruct.py`, reusing `bs.py` + the wall math from `walls.py`), then drive the existing `replay_day` engine with 0DTE-specific debit/mark providers (`providers.py`). `runner.py` iterates days; `metrics.py` aggregates and applies the GO-NO-GO bar; `cli.py` sweeps the PT/SL/cutoff grid.

**Tech Stack:** Python 3.14, psycopg2, pytest. Reuses `backtest/intraday_walls/bs.py`, `backtest/joshua_replay/engine.py`, `trading/helios/*`, `quant.sim`.

---

## Spec reference

`docs/superpowers/specs/2026-05-24-blaze-gex-0dte-backtest-design.md`.

## File structure

- Create `backtest/blaze_gex_0dte/__init__.py` — package marker.
- Create `backtest/blaze_gex_0dte/loader.py` — `DayChain` + `load_day(conn, trade_date)`: all 0DTE bars by minute + OI, one DB round-trip.
- Create `backtest/blaze_gex_0dte/reconstruct.py` — `build_snapshots(day) -> list[GexSnapshot]`: per-minute walls→snapshot with regime + sigma.
- Create `backtest/blaze_gex_0dte/providers.py` — `make_providers(day)` → `(debit_estimator, mark_provider)` reading the ATM±1 vertical from the bars; expiry settlement.
- Create `backtest/blaze_gex_0dte/runner.py` — `run_backtest(db_url, config, start, end) -> list[TradeOutcome]` (iterate days → snapshots → `replay_day`).
- Create `backtest/blaze_gex_0dte/metrics.py` — `summarize(outcomes)` + `go_no_go(summary)`.
- Create `backtest/blaze_gex_0dte/cli.py` + `__main__.py` — grid sweep + report table.
- Tests under `tests/backtest/blaze_gex_0dte/`.

Reused unchanged: `bs.py`, `joshua_replay/engine.py` (`replay_day`, `TradeOutcome`), `trading/helios` setups + `dispatch`, `quant.sim` (`simulate_intraday`, `MarkSeries`).

---

## Task 0: Backfill 0DTE open interest (operational prerequisite)

**Not TDD — a data step.** `helios_options_oi` currently covers only the old 1DTE strikes and stops 2025-12-05. `scripts/backfill_thetadata_oi.py` iterates every contract already in `helios_options_intraday`, so re-running it backfills the 0DTE contracts.

- [ ] **Step 1: Confirm Terminal is up**

Run: `python -c "import requests; print(requests.get('http://127.0.0.1:25510/v2/system/mdds/status',timeout=8).text)"`
Expected: `CONNECTED`

- [ ] **Step 2: Run the OI backfill**

Run: `python scripts/backfill_thetadata_oi.py --resume 2>&1 | Tee-Object backfill_oi_0dte.log`
Expected: completes with no failures; covers 0DTE contracts.

- [ ] **Step 3: Verify 0DTE OI coverage**

Run this query (via render MCP or psql) — expect a non-trivial day count and recent `max`:
```sql
SELECT COUNT(DISTINCT trade_date) AS oi_0dte_days, MIN(trade_date), MAX(trade_date)
FROM helios_options_oi WHERE expiration_date = trade_date;
```
Expected: hundreds of days through ~2026-05-22. If low/stale, OI did not cover 0DTE — stop and investigate before continuing.

---

## Task 1: Per-day 0DTE chain loader

**Files:**
- Create: `backtest/blaze_gex_0dte/__init__.py`
- Create: `backtest/blaze_gex_0dte/loader.py`
- Test: `tests/backtest/blaze_gex_0dte/test_loader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/blaze_gex_0dte/test_loader.py
import datetime as dt
from backtest.blaze_gex_0dte.loader import DayChain, bars_to_daychain

def test_bars_to_daychain_groups_by_minute_and_strike():
    # rows: (minute, strike, right, bid, ask)
    rows = [
        (0, 500.0, "C", 1.00, 1.10),
        (0, 500.0, "P", 0.90, 1.00),
        (0, 501.0, "C", 0.50, 0.60),
        (1, 500.0, "C", 1.05, 1.15),
    ]
    oi = {(500.0, "C"): 1000, (500.0, "P"): 800, (501.0, "C"): 500}
    day = bars_to_daychain(dt.date(2024, 3, 15), rows, oi)
    assert day.minutes() == [0, 1]
    assert day.mid(0, 500.0, "C") == 1.05
    assert day.oi[(500.0, "C")] == 1000
    assert day.mid(1, 501.0, "C") is None  # not present at minute 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_loader.py -v`
Expected: FAIL (`ModuleNotFoundError: backtest.blaze_gex_0dte.loader`).

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/blaze_gex_0dte/__init__.py
```
```python
# backtest/blaze_gex_0dte/loader.py
"""Load one 0DTE session's 1-min option bars + OI in a single DB pass."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

Key = Tuple[float, str]  # (strike, right)

@dataclass
class DayChain:
    trade_date: dt.date
    # minute -> {(strike,right): (bid, ask)}
    bars: Dict[int, Dict[Key, Tuple[float, float]]] = field(default_factory=dict)
    oi: Dict[Key, int] = field(default_factory=dict)

    def minutes(self) -> List[int]:
        return sorted(self.bars.keys())

    def mid(self, minute: int, strike: float, right: str) -> Optional[float]:
        q = self.bars.get(minute, {}).get((strike, right))
        if not q:
            return None
        bid, ask = q
        if bid is None or ask is None or bid <= 0 or ask < bid:
            return None
        return (bid + ask) / 2.0

    def quote(self, minute: int, strike: float, right: str) -> Optional[Tuple[float, float]]:
        return self.bars.get(minute, {}).get((strike, right))


def bars_to_daychain(trade_date, rows, oi) -> DayChain:
    """rows: iterable of (minute:int, strike:float, right:str, bid:float, ask:float)."""
    day = DayChain(trade_date=trade_date, oi=dict(oi))
    for minute, strike, right, bid, ask in rows:
        day.bars.setdefault(int(minute), {})[(float(strike), right)] = (
            None if bid is None else float(bid),
            None if ask is None else float(ask),
        )
    return day


def load_day(conn, trade_date: dt.date) -> Optional[DayChain]:
    """Load the 0DTE chain (expiration_date = trade_date) for one session."""
    sql = """
        WITH first_bar AS (
            SELECT MIN(bar_time) AS t0 FROM helios_options_intraday
            WHERE trade_date = %s AND expiration_date = %s
        )
        SELECT EXTRACT(EPOCH FROM (b.bar_time - first_bar.t0))::int / 60 AS minute,
               b.strike, b."right", b.bid, b.ask
        FROM helios_options_intraday b, first_bar
        WHERE b.trade_date = %s AND b.expiration_date = %s
        ORDER BY minute, b.strike, b."right"
    """
    oi_sql = """
        SELECT strike, "right", open_interest FROM helios_options_oi
        WHERE trade_date = %s AND expiration_date = %s
    """
    cur = conn.cursor()
    cur.execute(sql, (trade_date, trade_date, trade_date, trade_date))
    rows = cur.fetchall()
    cur.execute(oi_sql, (trade_date, trade_date))
    oi = {(float(k), r): int(o) for k, r, o in cur.fetchall()}
    cur.close()
    if not rows:
        return None
    return bars_to_daychain(trade_date, rows, oi)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_loader.py -v`
Expected: PASS (3 assertions). Add `tests/backtest/blaze_gex_0dte/__init__.py` (empty) if collection complains.

- [ ] **Step 5: Commit**

```bash
git add backtest/blaze_gex_0dte/__init__.py backtest/blaze_gex_0dte/loader.py tests/backtest/blaze_gex_0dte/
git commit -m "feat(blaze-gex): 0DTE per-day chain loader"
```

---

## Task 2: Reconstruct per-minute GexSnapshot

**Files:**
- Create: `backtest/blaze_gex_0dte/reconstruct.py`
- Test: `tests/backtest/blaze_gex_0dte/test_reconstruct.py`

Maps the loaded chain → a `GexSnapshot` per minute. Reuses `bs.py`. Regime is **sign-based** (sufficient: setups test set-membership, not tier). `t_years` at minute m = remaining hours to 4 PM ET / (24*365).

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/blaze_gex_0dte/test_reconstruct.py
import datetime as dt
from backtest.blaze_gex_0dte.loader import bars_to_daychain
from backtest.blaze_gex_0dte.reconstruct import build_snapshots, regime_for_net_gex

def test_regime_sign_mapping():
    assert regime_for_net_gex(1.0) == "MODERATE_POSITIVE"
    assert regime_for_net_gex(-1.0) == "MODERATE_NEGATIVE"
    assert regime_for_net_gex(0.0) == "MODERATE_POSITIVE"  # tie -> positive

def test_build_snapshots_yields_one_per_minute_with_walls():
    # Two strikes around an ATM ~500; minute 0 only.
    rows = [
        (0, 499.0, "C", 1.6, 1.7), (0, 499.0, "P", 0.5, 0.6),
        (0, 500.0, "C", 1.0, 1.1), (0, 500.0, "P", 1.0, 1.1),
        (0, 501.0, "C", 0.5, 0.6), (0, 501.0, "P", 1.6, 1.7),
    ]
    oi = {(499.0,"C"):100,(499.0,"P"):100,(500.0,"C"):5000,
          (500.0,"P"):5000,(501.0,"C"):100,(501.0,"P"):100}
    day = bars_to_daychain(dt.date(2024,3,15), rows, oi)
    snaps = build_snapshots(day)
    assert len(snaps) == 1
    s = snaps[0]
    assert 498.0 < s.spot < 502.0
    assert s.sigma_1d_band_width > 0
    assert s.regime in ("MODERATE_POSITIVE", "MODERATE_NEGATIVE")
    assert s.snapshot_at.tzinfo is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_reconstruct.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/blaze_gex_0dte/reconstruct.py
"""Reconstruct a per-minute GexSnapshot stream from a 0DTE DayChain."""
from __future__ import annotations
import datetime as dt
import math
from typing import List, Optional
from zoneinfo import ZoneInfo

from backtest.intraday_walls.bs import bs_gamma, implied_vol, derive_spot_from_parity
from trading.helios.gex_client import GexSnapshot
from .loader import DayChain

_ET = ZoneInfo("America/New_York")
_TRADING_DAYS = 252.0
_CLOSE_HOUR = 16  # 4 PM ET settlement

def regime_for_net_gex(net_gex: float) -> str:
    return "MODERATE_NEGATIVE" if net_gex < 0 else "MODERATE_POSITIVE"

def _t_years_remaining(trade_date: dt.date, minute: int, first_bar_et_hour=9, first_bar_et_min=30) -> float:
    open_et = dt.datetime(trade_date.year, trade_date.month, trade_date.day,
                          first_bar_et_hour, first_bar_et_min, tzinfo=_ET)
    now_et = open_et + dt.timedelta(minutes=minute)
    close_et = dt.datetime(trade_date.year, trade_date.month, trade_date.day, _CLOSE_HOUR, 0, tzinfo=_ET)
    secs = max((close_et - now_et).total_seconds(), 60.0)  # floor 1 min to avoid div-by-0
    return secs / (365.0 * 24.0 * 3600.0)

def _atm_strike(chain_keys, spot: float) -> Optional[float]:
    strikes = sorted({k for (k, _r) in chain_keys})
    if not strikes:
        return None
    return min(strikes, key=lambda k: abs(k - spot))

def build_snapshots(day: DayChain) -> List[GexSnapshot]:
    out: List[GexSnapshot] = []
    for minute in day.minutes():
        chain = day.bars[minute]
        t = _t_years_remaining(day.trade_date, minute)
        # spot via parity at the strike with both legs and smallest call+put (closest ATM)
        both = [(c[0] + p[0], k) for (k, r), c in chain.items()
                if r == "C" and (k, "P") in chain
                for p in [chain[(k, "P")]]
                if c[0] and p[0] and c[1] and p[1]]
        if not both:
            continue
        both.sort()
        atm_k = both[0][1]
        cm = (chain[(atm_k, "C")][0] + chain[(atm_k, "C")][1]) / 2
        pm = (chain[(atm_k, "P")][0] + chain[(atm_k, "P")][1]) / 2
        spot = derive_spot_from_parity(cm, pm, atm_k, t)
        if spot <= 0:
            continue
        # per-strike dollar gamma * OI
        by_strike = {}
        atm_iv = None
        for (k, r), q in chain.items():
            mid = day.mid(minute, k, r)
            if mid is None:
                continue
            oi = day.oi.get((k, r), 0)
            if oi <= 0:
                continue
            iv = implied_vol(mid, spot, k, t, r == "C")
            if iv is None:
                continue
            if k == atm_k and r == "C":
                atm_iv = iv
            dg = bs_gamma(spot, k, t, iv) * oi * 100.0 * spot * spot * 0.01
            d = by_strike.setdefault(k, {"C": 0.0, "P": 0.0})
            d["C" if r == "C" else "P"] += dg
        if not by_strike or atm_iv is None:
            continue
        call_above = [(v["C"], k) for k, v in by_strike.items() if k >= spot and v["C"] > 0]
        put_below = [(v["P"], k) for k, v in by_strike.items() if k <= spot and v["P"] > 0]
        call_wall = max(call_above)[1] if call_above else spot
        put_wall = max(put_below)[1] if put_below else spot
        net_gex = sum(v["C"] - v["P"] for v in by_strike.values())
        # flip: strike where cumulative net gamma crosses zero
        flip = spot
        cum = 0.0
        for k in sorted(by_strike):
            nxt = cum + (by_strike[k]["C"] - by_strike[k]["P"])
            if cum <= 0 < nxt or cum >= 0 > nxt:
                flip = k
                break
            cum = nxt
        sigma_1d = spot * atm_iv * math.sqrt(1.0 / _TRADING_DAYS)
        open_et = dt.datetime(day.trade_date.year, day.trade_date.month, day.trade_date.day, 9, 30, tzinfo=_ET)
        snap_at = (open_et + dt.timedelta(minutes=minute)).astimezone(dt.timezone.utc)
        out.append(GexSnapshot(
            symbol="SPY", spot=spot, net_gex=net_gex, flip_point=flip,
            call_wall=call_wall, put_wall=put_wall, vix=0.0,
            regime=regime_for_net_gex(net_gex),
            sigma_1d_band_width=sigma_1d, snapshot_at=snap_at,
        ))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_reconstruct.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backtest/blaze_gex_0dte/reconstruct.py tests/backtest/blaze_gex_0dte/test_reconstruct.py
git commit -m "feat(blaze-gex): reconstruct per-minute GexSnapshot from 0DTE chain"
```

---

## Task 3: 0DTE debit + mark providers

**Files:**
- Create: `backtest/blaze_gex_0dte/providers.py`
- Test: `tests/backtest/blaze_gex_0dte/test_providers.py`

`replay_day` needs: `debit_estimator(snap, action) -> float` (entry debit, worst-case = long ask − short bid) and `spot_mark_provider(snapshot, action, minute, entry_minute, debit) -> float` (spread mark = long mid − short mid each minute). Both read the ATM±1 vertical from the DayChain. The long strike is `round(spot)`, short is ±1 per direction (matches `setups.ts`).

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/blaze_gex_0dte/test_providers.py
import datetime as dt
from types import SimpleNamespace
from backtest.blaze_gex_0dte.loader import bars_to_daychain
from backtest.blaze_gex_0dte.providers import make_providers

def _action(direction, long_strike, short_strike):
    return SimpleNamespace(direction=direction, long_strike=long_strike, short_strike=short_strike)

def _snap(minute):
    # snapshot_at only needs to map back to `minute`; provider uses the explicit minute arg
    return SimpleNamespace(spot=500.0)

def test_debit_is_long_ask_minus_short_bid():
    rows = [
        (0, 500.0, "C", 1.00, 1.20),  # long call ask 1.20
        (0, 501.0, "C", 0.40, 0.55),  # short call bid 0.40
    ]
    day = bars_to_daychain(dt.date(2024,3,15), rows, {})
    debit_est, _mark = make_providers(day)
    a = _action("call", 500.0, 501.0)
    assert abs(debit_est(_snap(0), a) - (1.20 - 0.40)) < 1e-9

def test_mark_is_long_mid_minus_short_mid():
    rows = [
        (3, 500.0, "C", 1.40, 1.60),  # long mid 1.50
        (3, 501.0, "C", 0.50, 0.70),  # short mid 0.60
    ]
    day = bars_to_daychain(dt.date(2024,3,15), rows, {})
    _debit, mark = make_providers(day)
    a = _action("call", 500.0, 501.0)
    v = mark(snapshot=_snap(3), action=a, minute=3, entry_minute=0, debit=0.9)
    assert abs(v - (1.50 - 0.60)) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_providers.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/blaze_gex_0dte/providers.py
"""Debit + mark providers for the 0DTE ATM debit vertical, fed to replay_day."""
from __future__ import annotations
from typing import Callable, Tuple
from .loader import DayChain

def _right_for(direction: str) -> str:
    return "C" if direction == "call" else "P"

def make_providers(day: DayChain) -> Tuple[Callable, Callable]:
    def debit_estimator(snap, action) -> float:
        r = _right_for(action.direction)
        long_q = day.quote(0, float(action.long_strike), r)
        short_q = day.quote(0, float(action.short_strike), r)
        # find the entry minute's quotes: replay passes snap; entry minute is the
        # minute of the first mark. We read minute 0's chain only if needed, but
        # debit must use the ENTRY minute — see runner, which wraps with entry minute.
        if long_q is None or short_q is None:
            return 0.0
        long_ask = long_q[1]
        short_bid = short_q[0]
        if long_ask is None or short_bid is None:
            return 0.0
        return max(0.0, long_ask - short_bid)

    def mark_provider(*, snapshot, action, minute, entry_minute, debit) -> float:
        r = _right_for(action.direction)
        lm = day.mid(minute, float(action.long_strike), r)
        sm = day.mid(minute, float(action.short_strike), r)
        if lm is None or sm is None:
            return debit  # quote gap → hold value flat (no spurious PT/SL)
        return max(0.0, lm - sm)

    return debit_estimator, mark_provider
```

> NOTE for Task 5: the debit must be read at the **entry minute**, not minute 0. Task 5 wraps `debit_estimator` so it reads the entry minute's quotes (the engine calls it once at fire time). We pass the entry minute via a closure there.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_providers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backtest/blaze_gex_0dte/providers.py tests/backtest/blaze_gex_0dte/test_providers.py
git commit -m "feat(blaze-gex): 0DTE debit + mark providers"
```

---

## Task 4: Per-day runner wiring entry-minute debit

**Files:**
- Create: `backtest/blaze_gex_0dte/runner.py`
- Test: `tests/backtest/blaze_gex_0dte/test_runner.py`

Wires loader → reconstruct → `replay_day`. Reads the entry-minute debit correctly by building a per-fire debit reader. `replay_day` calls `debit_estimator(snap, action)` once at the fire minute; we compute the fire minute from `snap.snapshot_at` and read that minute's quotes.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/blaze_gex_0dte/test_runner.py
import datetime as dt
from backtest.blaze_gex_0dte.loader import bars_to_daychain
from backtest.blaze_gex_0dte.reconstruct import build_snapshots
from backtest.blaze_gex_0dte.runner import replay_daychain
from trading.helios.models import JoshuaConfig

def test_replay_daychain_runs_without_error_and_returns_list():
    # Minimal positive-gamma-ish day: ATM 500, OI clustered at 500.
    rows = []
    for m in range(0, 6):
        rows += [
            (m, 499.0, "C", 1.6, 1.7), (m, 499.0, "P", 0.5, 0.6),
            (m, 500.0, "C", 1.0, 1.1), (m, 500.0, "P", 1.0, 1.1),
            (m, 501.0, "C", 0.5, 0.6), (m, 501.0, "P", 1.6, 1.7),
        ]
    oi = {(499.0,"C"):100,(499.0,"P"):100,(500.0,"C"):9000,
          (500.0,"P"):9000,(501.0,"C"):100,(501.0,"P"):100}
    day = bars_to_daychain(dt.date(2024,3,15), rows, oi)
    out = replay_daychain(day, JoshuaConfig())
    assert isinstance(out, list)  # may be empty if no trigger; must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_runner.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/blaze_gex_0dte/runner.py
"""Drive one 0DTE DayChain through the real setups via replay_day."""
from __future__ import annotations
import datetime as dt
from typing import List, Optional

from backtest.joshua_replay.engine import replay_day, TradeOutcome
from trading.helios.models import JoshuaConfig
from .loader import DayChain, load_day
from .reconstruct import build_snapshots
from .providers import make_providers

def _minute_of(snapshot) -> int:
    ct = snapshot.snapshot_at - dt.timedelta(hours=5)  # UTC->ET(EST approx; engine uses same)
    open_t = ct.replace(hour=9, minute=30, second=0, microsecond=0)
    return int((ct - open_t).total_seconds() // 60)

def replay_daychain(day: DayChain, config: JoshuaConfig) -> List[TradeOutcome]:
    snaps = build_snapshots(day)
    if not snaps:
        return []
    _debit_min0, mark_provider = make_providers(day)

    def debit_estimator(snap, action) -> float:
        minute = _minute_of(snap)
        r = "C" if action.direction == "call" else "P"
        lq = day.quote(minute, float(action.long_strike), r)
        sq = day.quote(minute, float(action.short_strike), r)
        if not lq or not sq or lq[1] is None or sq[0] is None:
            return 0.0
        return max(0.0, lq[1] - sq[0])  # long ask - short bid

    return replay_day(
        snaps, config=config,
        spot_mark_provider=mark_provider,
        debit_estimator=debit_estimator,
    )

def run_backtest(db_url: str, config: JoshuaConfig, start: dt.date, end: dt.date) -> List[TradeOutcome]:
    import psycopg2
    conn = psycopg2.connect(db_url)
    all_out: List[TradeOutcome] = []
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT trade_date FROM helios_options_intraday "
            "WHERE expiration_date = trade_date AND trade_date BETWEEN %s AND %s ORDER BY trade_date",
            (start, end),
        )
        dates = [r[0] for r in cur.fetchall()]
        cur.close()
        for d in dates:
            day = load_day(conn, d)
            if day is None:
                continue
            all_out.extend(replay_daychain(day, config))
    finally:
        conn.close()
    return all_out
```

> The ATM debit vertical's settlement at expiry is handled by the mark series: the final minute's mark = long mid − short mid, which collapses to intrinsic as quotes converge near 4 PM. `simulate_intraday` closes at `eod_minute` using that mark. (A dedicated intrinsic-settlement override can be added later if EOD quotes are unreliable — see Task 6 sensitivity.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_runner.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backtest/blaze_gex_0dte/runner.py tests/backtest/blaze_gex_0dte/test_runner.py
git commit -m "feat(blaze-gex): per-day runner + full-range run_backtest"
```

---

## Task 5: Metrics + GO/NO-GO

**Files:**
- Create: `backtest/blaze_gex_0dte/metrics.py`
- Test: `tests/backtest/blaze_gex_0dte/test_metrics.py`

`TradeOutcome` carries `realized_pct` (% of debit), `debit`, `setup`, `trade_date`, `exit_reason`. P&L/contract = `realized_pct/100 * debit * 100` = `realized_pct * debit`. Summaries per setup, per year, per regime require the regime — Task 6 threads regime onto the outcome; for now group by setup/year and compute the core metrics.

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/blaze_gex_0dte/test_metrics.py
import datetime as dt
from backtest.blaze_gex_0dte.metrics import summarize, go_no_go, Summary

def _oc(setup, realized_pct, debit, date):
    from backtest.joshua_replay.engine import TradeOutcome
    return TradeOutcome(trade_date=date, setup=setup, direction="call",
                        entry_minute=10, exit_minute=20, debit=debit,
                        exit_reason="PT", realized_pct=realized_pct)

def test_summarize_computes_wr_ev_pf():
    ocs = [
        _oc("wall_fade", 20.0, 0.50, dt.date(2024,1,2)),   # +0.10
        _oc("wall_fade", -30.0, 0.50, dt.date(2024,1,3)),  # -0.15
        _oc("wall_fade", 20.0, 0.50, dt.date(2025,1,2)),   # +0.10
    ]
    s = summarize(ocs)["wall_fade"]
    assert s.trades == 3
    assert abs(s.win_rate - (2/3)) < 1e-9
    assert abs(s.total_pnl - (0.10 - 0.15 + 0.10)) < 1e-9
    # gross win 0.20, gross loss 0.15 -> PF = 1.333..
    assert abs(s.profit_factor - (0.20 / 0.15)) < 1e-6

def test_go_no_go_requires_positive_ev_and_pf():
    good = Summary(setup="x", trades=10, win_rate=0.5, ev_per_contract=2.0,
                   total_pnl=20.0, max_drawdown=-5.0, profit_factor=1.5,
                   pnl_by_year={2023: 1.0, 2024: 1.0, 2025: 1.0})
    bad = Summary(setup="y", trades=10, win_rate=0.5, ev_per_contract=2.0,
                  total_pnl=20.0, max_drawdown=-5.0, profit_factor=1.1,  # PF too low
                  pnl_by_year={2023: 1.0, 2024: -1.0})  # a negative year
    assert go_no_go(good) == "GO"
    assert go_no_go(bad) == "NO-GO"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_metrics.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/blaze_gex_0dte/metrics.py
"""Aggregate TradeOutcomes into per-setup summaries + GO/NO-GO verdict."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List
from backtest.joshua_replay.engine import TradeOutcome

@dataclass
class Summary:
    setup: str
    trades: int
    win_rate: float
    ev_per_contract: float       # dollars per contract per trade
    total_pnl: float             # dollars per contract, summed
    max_drawdown: float
    profit_factor: float
    pnl_by_year: Dict[int, float] = field(default_factory=dict)

def _pnl(oc: TradeOutcome) -> float:
    # realized_pct is % of debit; $/contract = (pct/100)*debit*100 = pct*debit
    return oc.realized_pct * oc.debit

def summarize(outcomes: List[TradeOutcome]) -> Dict[str, Summary]:
    by_setup: Dict[str, List[TradeOutcome]] = {}
    for oc in outcomes:
        by_setup.setdefault(oc.setup, []).append(oc)
    result: Dict[str, Summary] = {}
    for setup, ocs in by_setup.items():
        pnls = [_pnl(o) for o in ocs]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        gross_win = sum(wins)
        gross_loss = -sum(losses)
        # running drawdown on cumulative pnl
        cum, peak, mdd = 0.0, 0.0, 0.0
        for p in pnls:
            cum += p
            peak = max(peak, cum)
            mdd = min(mdd, cum - peak)
        by_year: Dict[int, float] = {}
        for o, p in zip(ocs, pnls):
            by_year[o.trade_date.year] = by_year.get(o.trade_date.year, 0.0) + p
        result[setup] = Summary(
            setup=setup,
            trades=len(ocs),
            win_rate=(len(wins) / len(ocs)) if ocs else 0.0,
            ev_per_contract=(sum(pnls) / len(ocs)) if ocs else 0.0,
            total_pnl=sum(pnls),
            max_drawdown=mdd,
            profit_factor=(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
            pnl_by_year=by_year,
        )
    return result

def go_no_go(s: Summary, *, min_profit_factor: float = 1.2) -> str:
    if s.ev_per_contract <= 0:
        return "NO-GO"
    if s.profit_factor < min_profit_factor:
        return "NO-GO"
    if s.pnl_by_year and any(v <= 0 for v in s.pnl_by_year.values()):
        return "NO-GO"
    return "GO"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_metrics.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backtest/blaze_gex_0dte/metrics.py tests/backtest/blaze_gex_0dte/test_metrics.py
git commit -m "feat(blaze-gex): per-setup metrics + GO/NO-GO verdict"
```

---

## Task 6: CLI grid sweep + report

**Files:**
- Create: `backtest/blaze_gex_0dte/cli.py`
- Create: `backtest/blaze_gex_0dte/__main__.py`
- Test: `tests/backtest/blaze_gex_0dte/test_cli.py`

Sweeps PT ∈ {20,30,50}, SL ∈ {30,50,100}, builds a `JoshuaConfig` per combo, runs `run_backtest`, prints a table + GO/NO-GO per (setup, config), writes CSV. CLI parsing is the only unit-tested piece (the full run is Task 7, operational).

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/blaze_gex_0dte/test_cli.py
from backtest.blaze_gex_0dte.cli import parse_args, build_grid

def test_parse_args_defaults():
    ns = parse_args(["--start", "2023-01-03", "--end", "2026-05-22"])
    assert str(ns.start) == "2023-01-03"
    assert str(ns.end) == "2026-05-22"

def test_build_grid_cartesian():
    grid = build_grid(pts=[20, 30], sls=[30, 50])
    assert len(grid) == 4
    assert (20, 30) in [(c.profit_target_pct, c.stop_loss_pct) for c in grid]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_cli.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

```python
# backtest/blaze_gex_0dte/cli.py
from __future__ import annotations
import argparse, csv, datetime as dt, os
from dataclasses import replace
from typing import List
from trading.helios.models import JoshuaConfig
from .runner import run_backtest
from .metrics import summarize, go_no_go

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BLAZE GEX-on-0DTE backtest grid sweep.")
    p.add_argument("--start", type=lambda s: dt.date.fromisoformat(s), default=dt.date(2023,1,3))
    p.add_argument("--end", type=lambda s: dt.date.fromisoformat(s), default=dt.date(2026,5,22))
    p.add_argument("--pts", type=int, nargs="+", default=[20, 30, 50])
    p.add_argument("--sls", type=int, nargs="+", default=[30, 50, 100])
    p.add_argument("--out", default="backtest/blaze_gex_0dte/output/results.csv")
    return p.parse_args(argv)

def build_grid(pts: List[int], sls: List[int]) -> List[JoshuaConfig]:
    base = JoshuaConfig()
    return [replace(base, profit_target_pct=float(pt), stop_loss_pct=float(sl))
            for pt in pts for sl in sls]

def main(argv=None) -> int:
    args = parse_args(argv)
    db_url = os.environ["DATABASE_URL"]
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    rows = []
    for cfg in build_grid(args.pts, args.sls):
        outcomes = run_backtest(db_url, cfg, args.start, args.end)
        for setup, s in summarize(outcomes).items():
            verdict = go_no_go(s)
            rows.append({
                "pt": cfg.profit_target_pct, "sl": cfg.stop_loss_pct, "setup": setup,
                "trades": s.trades, "win_rate": round(s.win_rate, 4),
                "ev_per_contract": round(s.ev_per_contract, 4),
                "total_pnl": round(s.total_pnl, 2), "max_dd": round(s.max_drawdown, 2),
                "profit_factor": round(s.profit_factor, 3),
                "pnl_by_year": s.pnl_by_year, "verdict": verdict,
            })
            print(f"PT{cfg.profit_target_pct:.0f}/SL{cfg.stop_loss_pct:.0f} {setup}: "
                  f"n={s.trades} wr={s.win_rate:.1%} ev=${s.ev_per_contract:.2f} "
                  f"pf={s.profit_factor:.2f} {verdict}")
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["verdict"])
        w.writeheader(); w.writerows(rows)
    return 0
```
```python
# backtest/blaze_gex_0dte/__main__.py
import sys
from .cli import main
if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/blaze_gex_0dte/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backtest/blaze_gex_0dte/cli.py backtest/blaze_gex_0dte/__main__.py tests/backtest/blaze_gex_0dte/test_cli.py
git commit -m "feat(blaze-gex): grid-sweep CLI + GO/NO-GO report"
```

---

## Task 7: Smoke-run + full backtest (operational)

**Not TDD.** Validate end-to-end on a small window, then run the full sweep.

- [ ] **Step 1: Smoke a 1-month window**

Run: `python -m backtest.blaze_gex_0dte --start 2024-03-01 --end 2024-03-28 --pts 20 --sls 30 2>&1 | Tee-Object smoke_gex0dte.log`
Expected: prints per-setup lines without error; `wall_fade` has > 0 trades.

- [ ] **Step 2: Run the full sweep**

Run: `python -m backtest.blaze_gex_0dte 2>&1 | Tee-Object full_gex0dte.log`
Expected: completes; `output/results.csv` written.

- [ ] **Step 3: Read the verdict**

Inspect `output/results.csv`: per (PT,SL,setup) — trades, WR, EV/contract, PF, per-year P&L, GO/NO-GO. Apply the spec bar (EV>0, every year positive, PF>1.2). Summarize which setups/regimes/years pass, and whether `wall_break`/`flip_cross` ever fired (NEGATIVE-regime days present?).

- [ ] **Step 4: Record the result to memory**

Write `project_blaze_gex_0dte_<verdict>_2026_05_24.md` (GO or NO-GO) with the headline metrics + which configs, and update `MEMORY.md`.

---

## Self-review notes

- **Spec coverage:** data prep → Task 0; reconstruction (walls + regime + sigma) → Task 2; signal reuse → Task 4 (`replay_day` + real setups); structure/exits/fills → Tasks 3–4; metrics + per-year/per-regime + GO/NO-GO → Tasks 5–6; full run → Task 7. Per-**regime** breakdown is partially deferred: Tasks 5–6 group by setup/year; threading regime onto each `TradeOutcome` (so we can group by regime) is a small follow-up — add a `regime` field by capturing `snap.regime` at fire time in `replay_daychain` if the first results warrant it.
- **Known caveat carried from spec:** regime is sign-based; if `wall_break`/`flip_cross` never fire (no NEGATIVE-regime minutes), that's a finding, not a bug — Task 7 Step 3 checks for it explicitly.
- **Performance:** `load_day` is one round-trip/day; reconstruction is in-memory — no per-minute reconnect (the flaw in `walls.py:compute_intraday_walls`).
