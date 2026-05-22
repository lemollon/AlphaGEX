# EMBER Phase 1 — Intraday Credit-Spread Exit Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless engine that finds the optimal intraday exit policy for 1DTE SPY credit spreads (SPARK first) by replaying synthesized iron condors against `helios_options_intraday` minute bid/ask data, with realistic ask-cross fills and walk-forward validation.

**Architecture:** A new Python package `backtest/ember/` of small, pure, independently-testable units (models → fills → policy → engine → report) plus a thin DB loader (`data.py`) and a SPARK entry adapter, wired together by a CLI. Pricing logic reuses the existing `quant/bs.py` (Black-Scholes, IV solver, parity spot). The engine operates only on a position's minute-by-minute combo P&L path, so it is strategy-agnostic and later adapters (BLAZE, faithful-SPARK) plug in without engine changes.

**Tech Stack:** Python 3.11+, `psycopg2` (DB), `pytest` (tests), stdlib only otherwise. DB = production Postgres via `DATABASE_URL` (table `helios_options_intraday`).

**Spec:** `docs/superpowers/specs/2026-05-20-ember-phase1-intraday-exit-engine-design.md`

**Conventions discovered:**
- Tests live in `tests/backtest/ember/` (mirrors `tests/backtest/joshua_replay/`). Run from repo root.
- DB access pattern: `psycopg2.connect(os.environ["DATABASE_URL"])`. The minute table columns are `trade_date, expiration_date, strike, "right" (C/P), bar_time (timestamptz), open, high, low, close, volume, bid, ask`. `right` is a SQL reserved word — always quote it `"right"`.
- `bar_time AT TIME ZONE 'America/New_York'` yields a clean 09:30–16:00 session. Minute index = minutes since 09:30 ET (0…390).
- `quant/bs.py` already provides: `bs_price(spot, strike, t_years, sigma, is_call, r=DEFAULT_R)`, `bs_vega(...)`, `implied_vol(market_price, spot, strike, t_years, is_call, r=DEFAULT_R) -> Optional[float]`, `derive_spot_from_parity(call_mid, put_mid, strike, t_years=0.0, r=DEFAULT_R)`, `DEFAULT_R = 0.05`. It does **not** have a delta function — Task 1 adds one.
- Commission model: per-leg, per-contract (the `backtest_framework` %-of-value model is wrong for 4-leg options). `$0.65/leg`, charged open + close.

**Deviation from spec:** The spec said "reuse `backtest_framework` cost model + metrics." On inspection that cost model is percentage-of-trade-value (built for single-leg equity) and a poor fit for a 4-leg IC. This plan instead uses a per-leg-per-contract commission constant and computes its own (simple) metrics. Everything else matches the spec.

---

## File Structure

```
quant/bs.py                          # MODIFY: add bs_delta()
backtest/ember/
  __init__.py                        # package marker
  models.py                          # Quote, Leg, Position, MinuteChain, DayChain
  fills.py                           # leg_price, signed_cashflow, commission, fill-model constants
  policy.py                          # ExitPolicy, default_grid(), SPARK_BASELINE
  engine.py                          # price_path(), evaluate_exit(), TradeResult
  report.py                          # summarize(), write_trades_csv(), write_summary_csv(), write_report_md()
  walkforward.py                     # split()
  data.py                            # query_day_rows(), build_day_chain(), load_day(), list_trade_dates(), t_years(), delta_at()
  adapters/
    __init__.py
    base.py                          # StrategyAdapter protocol, AdapterConfig
    spark.py                         # SparkRepresentativeIC
  cli.py                             # run orchestration + arg parsing
  __main__.py                        # `python -m backtest.ember`
tests/backtest/ember/
  __init__.py
  test_bs_delta.py
  test_models.py
  test_fills.py
  test_policy.py
  test_engine.py
  test_report.py
  test_walkforward.py
  test_data.py
  test_spark_adapter.py
  test_cli_smoke.py
```

Each file has one responsibility. `engine.py` never imports `adapters/` or `data.py` (it takes a `Position` and a `DayChain` — both plain data), keeping it strategy- and source-agnostic.

---

## Task 1: Add `bs_delta` to quant/bs.py

**Files:**
- Modify: `quant/bs.py` (add function after `bs_gamma`, ~line 82)
- Test: `tests/backtest/ember/test_bs_delta.py`

- [ ] **Step 1: Create `tests/backtest/ember/__init__.py` (empty) and write the failing test**

```python
# tests/backtest/ember/__init__.py  -> empty file
```

```python
# tests/backtest/ember/test_bs_delta.py
import math
from quant.bs import bs_delta


def test_atm_call_delta_near_half():
    # ATM, 30 days, 20% vol -> call delta a little above 0.5
    d = bs_delta(spot=100.0, strike=100.0, t_years=30 / 365, sigma=0.20, is_call=True)
    assert 0.50 < d < 0.60


def test_atm_put_delta_near_minus_half():
    d = bs_delta(spot=100.0, strike=100.0, t_years=30 / 365, sigma=0.20, is_call=False)
    assert -0.60 < d < -0.40


def test_put_call_delta_parity():
    # call_delta - put_delta == 1 (no dividends)
    c = bs_delta(100.0, 105.0, 30 / 365, 0.25, True)
    p = bs_delta(100.0, 105.0, 30 / 365, 0.25, False)
    assert math.isclose(c - p, 1.0, abs_tol=1e-9)


def test_expired_call_is_zero_or_one():
    assert bs_delta(110.0, 100.0, 0.0, 0.20, True) == 1.0   # ITM call at expiry
    assert bs_delta(90.0, 100.0, 0.0, 0.20, True) == 0.0    # OTM call at expiry


def test_deep_otm_short_put_delta_small():
    # 16-delta-ish region: a put ~5% OTM should have |delta| well under 0.5
    d = bs_delta(100.0, 95.0, 1 / 365, 0.18, False)
    assert -0.5 < d < 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_bs_delta.py -v`
Expected: FAIL with `ImportError: cannot import name 'bs_delta' from 'quant.bs'`

- [ ] **Step 3: Add `bs_delta` to `quant/bs.py`** (insert immediately after `bs_gamma`, before `bs_charm`)

```python
def bs_delta(
    spot: float,
    strike: float,
    t_years: float,
    sigma: float,
    is_call: bool,
    r: float = DEFAULT_R,
) -> float:
    """Option delta (∂Price/∂spot). Call in [0,1], put in [-1,0].

    At/past expiry (or non-positive sigma) returns the intrinsic delta:
    ±1 if in-the-money, 0 if out-of-the-money.
    """
    if t_years <= 0 or sigma <= 0 or spot <= 0:
        if is_call:
            return 1.0 if spot > strike else 0.0
        return -1.0 if spot < strike else 0.0
    sqrt_t = math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t_years) / (sigma * sqrt_t)
    if is_call:
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_bs_delta.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add quant/bs.py tests/backtest/ember/__init__.py tests/backtest/ember/test_bs_delta.py
git commit -m "feat(ember): add bs_delta to quant/bs for strike selection"
```

---

## Task 2: Data models (`models.py`)

**Files:**
- Create: `backtest/ember/__init__.py` (empty), `backtest/ember/models.py`
- Test: `tests/backtest/ember/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_models.py
import datetime as dt
from backtest.ember.models import Quote, Leg, Position, MinuteChain, DayChain


def test_quote_mid_uses_bid_ask():
    assert Quote(bid=1.0, ask=1.4, close=1.1).mid == 1.2


def test_quote_mid_falls_back_to_close_on_bad_spread():
    # crossed/zero quote -> use close
    assert Quote(bid=0.0, ask=0.0, close=0.9).mid == 0.9
    assert Quote(bid=2.0, ask=1.0, close=1.3).mid == 1.3


def test_position_holds_legs():
    legs = [Leg(95.0, "P", -1), Leg(90.0, "P", 1), Leg(105.0, "C", -1), Leg(110.0, "C", 1)]
    pos = Position(legs=legs, entry_minute=30, entry_credit=1.20)
    assert pos.contracts == 1
    assert len(pos.legs) == 4


def test_daychain_lookup():
    q = Quote(0.5, 0.7, 0.6)
    mc = MinuteChain(minute=0, spot=100.0, quotes={(95.0, "P"): q})
    day = DayChain(trade_date=dt.date(2024, 6, 3), expiration=dt.date(2024, 6, 4), minutes={0: mc})
    assert day.spot(0) == 100.0
    assert day.quote(0, 95.0, "P") is q
    assert day.quote(0, 999.0, "C") is None
    assert day.spot(7) is None
    assert day.sorted_minutes == [0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember'`

- [ ] **Step 3: Create the package and models**

```python
# backtest/ember/__init__.py  -> empty file
```

```python
# backtest/ember/models.py
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Quote:
    bid: float
    ask: float
    close: float

    @property
    def mid(self) -> float:
        """Mid of a valid two-sided quote, else last trade (close)."""
        if self.bid is not None and self.ask is not None and self.ask >= self.bid > 0:
            return (self.bid + self.ask) / 2.0
        return self.close


@dataclass(frozen=True)
class Leg:
    strike: float
    right: str            # "C" or "P"
    qty: int              # +1 long (bought), -1 short (sold)


@dataclass
class Position:
    legs: List[Leg]
    entry_minute: int          # minutes since 09:30 ET
    entry_credit: float        # net credit per spread, price units (>0)
    contracts: int = 1


@dataclass(frozen=True)
class MinuteChain:
    minute: int
    spot: float
    quotes: Dict[Tuple[float, str], Quote]   # (strike, right) -> Quote


@dataclass
class DayChain:
    trade_date: dt.date
    expiration: dt.date
    minutes: Dict[int, MinuteChain] = field(default_factory=dict)

    def spot(self, minute: int) -> Optional[float]:
        mc = self.minutes.get(minute)
        return mc.spot if mc else None

    def quote(self, minute: int, strike: float, right: str) -> Optional[Quote]:
        mc = self.minutes.get(minute)
        if not mc:
            return None
        return mc.quotes.get((strike, right))

    @property
    def sorted_minutes(self) -> List[int]:
        return sorted(self.minutes.keys())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_models.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/__init__.py backtest/ember/models.py tests/backtest/ember/test_models.py
git commit -m "feat(ember): core data models (Quote/Leg/Position/DayChain)"
```

---

## Task 3: Combo pricing & fills (`fills.py`)

The differentiator: real bid/ask fills. `signed_cashflow` returns cash flow per 1 contract in price units — positive = cash received, negative = cash paid. `pnl = signed_cashflow(open) + signed_cashflow(close)`.

**Files:**
- Create: `backtest/ember/fills.py`
- Test: `tests/backtest/ember/test_fills.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_fills.py
import math
import pytest
from backtest.ember.models import Quote, Leg
from backtest.ember.fills import (
    leg_price, signed_cashflow, commission,
    FILL_ASK_CROSS, FILL_MID, FILL_MID_SLIP, COMMISSION_PER_LEG,
)

# A short put credit spread: sell 95P, buy 90P
LEGS = [Leg(95.0, "P", -1), Leg(90.0, "P", 1)]
QUOTES = {
    (95.0, "P"): Quote(bid=1.00, ask=1.20, close=1.10),  # short leg
    (90.0, "P"): Quote(bid=0.40, ask=0.55, close=0.48),  # long leg
}


def test_leg_price_buy_vs_sell_ask_cross():
    q = QUOTES[(95.0, "P")]
    assert leg_price(q, buying=True, fill=FILL_ASK_CROSS) == 1.20   # pay ask
    assert leg_price(q, buying=False, fill=FILL_ASK_CROSS) == 1.00  # receive bid


def test_open_credit_ask_cross_is_conservative():
    # OPEN: sell 95P at bid (+1.00), buy 90P at ask (-0.55) -> credit 0.45
    cf = signed_cashflow(LEGS, QUOTES, action="open", fill=FILL_ASK_CROSS)
    assert math.isclose(cf, 0.45, abs_tol=1e-9)


def test_close_cost_ask_cross_is_conservative():
    # CLOSE: buy back 95P at ask (-1.20), sell 90P at bid (+0.40) -> -0.80
    cf = signed_cashflow(LEGS, QUOTES, action="close", fill=FILL_ASK_CROSS)
    assert math.isclose(cf, -0.80, abs_tol=1e-9)


def test_mid_open_credit():
    # mids: 95P=1.10, 90P=0.475 -> open credit = 1.10 - 0.475 = 0.625
    cf = signed_cashflow(LEGS, QUOTES, action="open", fill=FILL_MID)
    assert math.isclose(cf, 0.625, abs_tol=1e-9)


def test_mid_slip_penalizes_both_sides():
    cf = signed_cashflow(LEGS, QUOTES, action="open", fill=FILL_MID_SLIP, slippage=0.03)
    # sell 95P at 1.10-0.03=1.07, buy 90P at 0.475+0.03=0.505 -> 0.565
    assert math.isclose(cf, 0.565, abs_tol=1e-9)


def test_commission_four_legs_open_and_close():
    legs4 = LEGS + [Leg(105.0, "C", -1), Leg(110.0, "C", 1)]
    assert commission(legs4, contracts=1) == COMMISSION_PER_LEG * 4 * 2
    assert commission(legs4, contracts=3) == COMMISSION_PER_LEG * 4 * 2 * 3


def test_unknown_fill_raises():
    with pytest.raises(ValueError):
        leg_price(QUOTES[(90.0, "P")], buying=True, fill="bogus")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_fills.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.fills'`

- [ ] **Step 3: Write `fills.py`**

```python
# backtest/ember/fills.py
from __future__ import annotations

from typing import Dict, List, Tuple

from backtest.ember.models import Leg, Quote

FILL_ASK_CROSS = "ask_cross"
FILL_MID = "mid"
FILL_MID_SLIP = "mid_slip"

COMMISSION_PER_LEG = 0.65   # $/contract/leg (one side)
CONTRACT_MULTIPLIER = 100   # options multiplier


def leg_price(quote: Quote, buying: bool, fill: str, slippage: float = 0.03) -> float:
    """Per-contract execution price for one leg under a fill model."""
    if fill == FILL_ASK_CROSS:
        return quote.ask if buying else quote.bid
    if fill == FILL_MID:
        return quote.mid
    if fill == FILL_MID_SLIP:
        return quote.mid + slippage if buying else quote.mid - slippage
    raise ValueError(f"unknown fill model: {fill!r}")


def signed_cashflow(
    legs: List[Leg],
    quotes: Dict[Tuple[float, str], Quote],
    action: str,                 # "open" or "close"
    fill: str,
    slippage: float = 0.03,
) -> float:
    """Net cash flow per 1 contract, price units. + = received, - = paid.

    A long leg is bought to open / sold to close; a short leg is sold to
    open / bought to close. Buying pays (cash out), selling receives (cash in).
    """
    total = 0.0
    for leg in legs:
        buying = (leg.qty > 0) == (action == "open")
        q = quotes[(leg.strike, leg.right)]
        px = leg_price(q, buying, fill, slippage)
        total += (-px if buying else px) * abs(leg.qty)
    return total


def commission(legs: List[Leg], contracts: int) -> float:
    """Round-trip (open + close) commission in dollars."""
    return COMMISSION_PER_LEG * len(legs) * 2 * contracts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_fills.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/fills.py tests/backtest/ember/test_fills.py
git commit -m "feat(ember): combo cash-flow pricing with ask-cross/mid/slippage fills"
```

---

## Task 4: Exit policy & grid (`policy.py`)

**Files:**
- Create: `backtest/ember/policy.py`
- Test: `tests/backtest/ember/test_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_policy.py
from backtest.ember.policy import ExitPolicy, default_grid, SPARK_BASELINE


def test_spark_baseline_matches_live_config():
    assert SPARK_BASELINE.profit_target_pct == 30
    assert SPARK_BASELINE.stop_loss_mult == 0.5
    assert SPARK_BASELINE.time_stop_minute is None


def test_default_grid_includes_baseline_and_is_nonempty():
    grid = default_grid()
    assert len(grid) > 10
    assert any(p.name == "spark_live" for p in grid)
    # names are unique
    names = [p.name for p in grid]
    assert len(names) == len(set(names))


def test_policy_is_hashable_frozen():
    p = ExitPolicy(name="x", profit_target_pct=40, stop_loss_mult=1.5, time_stop_minute=None)
    assert {p: 1}[p] == 1   # hashable
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_policy.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.policy'`

- [ ] **Step 3: Write `policy.py`**

```python
# backtest/ember/policy.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ExitPolicy:
    name: str
    profit_target_pct: Optional[float]   # % of entry credit captured; None disables
    stop_loss_mult: Optional[float]      # loss threshold = mult * credit; None disables
    time_stop_minute: Optional[int]      # minutes since 09:30 ET; None = EOD only
    trail_activation_pct: Optional[float] = None   # % of credit before trail arms
    trail_giveback_pct: Optional[float] = None     # % of credit given back from peak
    min_hold_minutes: int = 5


# SPARK's current live exit config (see project_spark_config_locks): PT 30%, SL 0.5x credit, EOD.
SPARK_BASELINE = ExitPolicy(
    name="spark_live",
    profit_target_pct=30.0,
    stop_loss_mult=0.5,
    time_stop_minute=None,
    min_hold_minutes=5,
)


def default_grid() -> List[ExitPolicy]:
    """The PT x SL x time-stop sweep, plus the SPARK baseline."""
    pts = [20.0, 30.0, 40.0, 50.0, 60.0]
    sls = [0.5, 1.0, 1.5, 2.0, 2.5]
    time_stops = [None, 14 * 60 + 30, 15 * 60]  # None (EOD), 14:30, 15:00 -> wait, see note
    # NOTE: minute index is minutes-since-09:30, so 14:30 ET = 300, 15:55 ET = 385.
    time_stops = [None, 180, 300, 385]  # None=EOD, 12:30, 14:30, 15:55 ET
    grid: List[ExitPolicy] = [SPARK_BASELINE]
    for pt in pts:
        for sl in sls:
            for ts in time_stops:
                ts_label = "eod" if ts is None else f"t{ts}"
                grid.append(
                    ExitPolicy(
                        name=f"pt{int(pt)}_sl{sl}_{ts_label}",
                        profit_target_pct=pt,
                        stop_loss_mult=sl,
                        time_stop_minute=ts,
                        min_hold_minutes=5,
                    )
                )
    return grid
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_policy.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/policy.py tests/backtest/ember/test_policy.py
git commit -m "feat(ember): exit policy model + default PT/SL/time-stop grid"
```

---

## Task 5: Exit engine (`engine.py`)

Pure replay: given a `DayChain`, a `Position`, and an `ExitPolicy`, walk minute-by-minute and return a `TradeResult`. Exit precedence each minute: **SL → PT → TRAIL → TIME**, with forced **EOD** at the last minute. Missing-leg minutes forward-fill the last valid close cash flow.

**Files:**
- Create: `backtest/ember/engine.py`
- Test: `tests/backtest/ember/test_engine.py`

- [ ] **Step 1: Write the failing test** (synthetic chain — no DB)

```python
# tests/backtest/ember/test_engine.py
import datetime as dt
import math
from backtest.ember.models import Quote, Leg, Position, MinuteChain, DayChain
from backtest.ember.policy import ExitPolicy
from backtest.ember.fills import FILL_ASK_CROSS, FILL_MID, CONTRACT_MULTIPLIER
from backtest.ember.engine import evaluate_exit, price_path


# Single short put credit spread: sell 95P / buy 90P.
LEGS = [Leg(95.0, "P", -1), Leg(90.0, "P", 1)]


def _chain(spread_mids_by_minute):
    """Build a DayChain where the combo mid follows the given path.
    We model it by setting the 95P mid to `value` and 90P mid to 0 (tight quotes)."""
    minutes = {}
    for m, val in spread_mids_by_minute.items():
        quotes = {
            (95.0, "P"): Quote(bid=val, ask=val, close=val),
            (90.0, "P"): Quote(bid=0.0, ask=0.0, close=0.0),  # mid falls back to close=0
        }
        minutes[m] = MinuteChain(minute=m, spot=100.0, quotes=quotes)
    return DayChain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), minutes)


def _pos(entry_minute=0, credit=1.00):
    return Position(legs=LEGS, entry_minute=entry_minute, entry_credit=credit)


def test_profit_target_triggers():
    # Entry combo mid 1.00 (credit). Decays to 0.50 by minute 10 -> 50% captured.
    chain = _chain({0: 1.00, 5: 0.80, 10: 0.50, 385: 0.50})
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "PT"
    assert r.exit_minute == 10


def test_stop_loss_triggers():
    # Combo mid rises to 1.50 -> loss = 0.50 per spread = 0.5x credit.
    chain = _chain({0: 1.00, 5: 1.20, 8: 1.50, 385: 1.50})
    policy = ExitPolicy("sl05", profit_target_pct=None, stop_loss_mult=0.5, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "SL"
    assert r.exit_minute == 8


def test_time_stop_triggers():
    chain = _chain({0: 1.00, 100: 0.95, 300: 0.90, 385: 0.90})
    policy = ExitPolicy("ts", profit_target_pct=None, stop_loss_mult=None, time_stop_minute=300, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "TIME"
    assert r.exit_minute == 300


def test_eod_when_nothing_triggers():
    chain = _chain({0: 1.00, 200: 0.92, 385: 0.88})
    policy = ExitPolicy("eod", profit_target_pct=99, stop_loss_mult=99, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_reason == "EOD"
    assert r.exit_minute == 385


def test_pnl_sign_and_commission():
    # Mid fill, credit 1.00 -> decays to 0.50, exit by PT. Gross profit per contract = 0.50*100 = 50.
    chain = _chain({0: 1.00, 10: 0.50, 385: 0.50})
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=1)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    # gross = (open_cf + close_cf) * 100 ; open_cf=+1.00, close_cf=-0.50 -> +0.50*100 = 50
    # net = 50 - commission(2 legs) = 50 - 0.65*2*2 = 50 - 2.6 = 47.4
    assert math.isclose(r.pnl, 47.4, abs_tol=1e-6)


def test_min_hold_blocks_instant_exit():
    # PT would hit at minute 1 but min_hold=5 forces waiting; value back up by 5 -> EOD instead.
    chain = _chain({0: 1.00, 1: 0.40, 5: 0.95, 385: 0.95})
    policy = ExitPolicy("pt50", profit_target_pct=50, stop_loss_mult=None, time_stop_minute=None, min_hold_minutes=5)
    r = evaluate_exit(chain, _pos(credit=1.00), policy, fill=FILL_MID)
    assert r.exit_minute >= 5
    assert r.exit_reason in ("EOD", "PT")


def test_price_path_forward_fills_missing_minute():
    chain = _chain({0: 1.00, 10: 0.80, 385: 0.60})
    pos = _pos(credit=1.00)
    path = price_path(chain, pos, fill=FILL_MID)
    minutes = [m for m, _ in path]
    assert minutes == [0, 10, 385]   # only minutes present in the chain
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.engine'`

- [ ] **Step 3: Write `engine.py`**

```python
# backtest/ember/engine.py
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import List, Optional, Tuple

from backtest.ember.fills import CONTRACT_MULTIPLIER, commission, signed_cashflow
from backtest.ember.models import DayChain, Position
from backtest.ember.policy import ExitPolicy


@dataclass
class TradeResult:
    trade_date: dt.date
    policy: str
    entry_minute: int
    exit_minute: int
    exit_reason: str            # "PT" | "SL" | "TRAIL" | "TIME" | "EOD"
    entry_credit: float         # price units, per spread
    exit_cost: float            # price units paid to close, per spread (>=0 typical)
    pnl: float                  # dollars, net of commission, for position.contracts
    max_favorable: float        # best gross dollars seen
    max_adverse: float          # worst gross dollars seen


def _all_legs_quotable(chain: DayChain, position: Position, minute: int) -> bool:
    for leg in position.legs:
        if chain.quote(minute, leg.strike, leg.right) is None:
            return False
    return True


def price_path(
    chain: DayChain,
    position: Position,
    fill: str,
    slippage: float = 0.03,
) -> List[Tuple[int, float]]:
    """[(minute, gross_pnl_dollars)] for each minute >= entry where all legs quote.

    gross_pnl = (open_cashflow + close_cashflow_now) * multiplier * contracts.
    open_cashflow is fixed at entry (= +entry_credit by construction)."""
    open_cf = position.entry_credit
    out: List[Tuple[int, float]] = []
    for minute in chain.sorted_minutes:
        if minute < position.entry_minute:
            continue
        if not _all_legs_quotable(chain, position, minute):
            continue
        quotes = chain.minutes[minute].quotes
        close_cf = signed_cashflow(position.legs, quotes, action="close", fill=fill, slippage=slippage)
        gross = (open_cf + close_cf) * CONTRACT_MULTIPLIER * position.contracts
        out.append((minute, gross))
    return out


def evaluate_exit(
    chain: DayChain,
    position: Position,
    policy: ExitPolicy,
    fill: str,
    slippage: float = 0.03,
) -> Optional[TradeResult]:
    """Replay the position under one policy. Returns None if it never quotes."""
    path = price_path(chain, position, fill, slippage)
    if not path:
        return None

    credit_dollars = position.entry_credit * CONTRACT_MULTIPLIER * position.contracts
    pt_target = (policy.profit_target_pct / 100.0) * credit_dollars if policy.profit_target_pct else None
    sl_thresh = (policy.stop_loss_mult * credit_dollars) if policy.stop_loss_mult else None
    trail_arm = (policy.trail_activation_pct / 100.0) * credit_dollars if policy.trail_activation_pct else None
    trail_give = (policy.trail_giveback_pct / 100.0) * credit_dollars if policy.trail_giveback_pct else None

    peak = float("-inf")
    max_fav = float("-inf")
    max_adv = float("inf")
    last_minute, last_gross = path[-1]

    chosen_minute: Optional[int] = None
    chosen_reason: Optional[str] = None
    chosen_gross: Optional[float] = None

    for minute, gross in path:
        max_fav = max(max_fav, gross)
        max_adv = min(max_adv, gross)
        peak = max(peak, gross)
        if minute - position.entry_minute < policy.min_hold_minutes:
            continue
        # Precedence: SL -> PT -> TRAIL -> TIME
        if sl_thresh is not None and gross <= -sl_thresh:
            chosen_minute, chosen_reason, chosen_gross = minute, "SL", gross
            break
        if pt_target is not None and gross >= pt_target:
            chosen_minute, chosen_reason, chosen_gross = minute, "PT", gross
            break
        if trail_arm is not None and trail_give is not None and peak >= trail_arm and gross <= peak - trail_give:
            chosen_minute, chosen_reason, chosen_gross = minute, "TRAIL", gross
            break
        if policy.time_stop_minute is not None and minute >= policy.time_stop_minute:
            chosen_minute, chosen_reason, chosen_gross = minute, "TIME", gross
            break

    if chosen_minute is None:
        chosen_minute, chosen_reason, chosen_gross = last_minute, "EOD", last_gross

    comm = commission(position.legs, position.contracts)
    net_pnl = chosen_gross - comm
    # exit_cost (price units, per spread) implied by gross: gross = (credit - exit_cost)*mult*contracts
    exit_cost = position.entry_credit - chosen_gross / (CONTRACT_MULTIPLIER * position.contracts)

    return TradeResult(
        trade_date=chain.trade_date,
        policy=policy.name,
        entry_minute=position.entry_minute,
        exit_minute=chosen_minute,
        exit_reason=chosen_reason,
        entry_credit=position.entry_credit,
        exit_cost=exit_cost,
        pnl=net_pnl,
        max_favorable=max_fav,
        max_adverse=max_adv,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_engine.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/engine.py tests/backtest/ember/test_engine.py
git commit -m "feat(ember): minute-replay exit engine (SL>PT>TRAIL>TIME>EOD)"
```

---

## Task 6: Metrics & report artifacts (`report.py`)

**Files:**
- Create: `backtest/ember/report.py`
- Test: `tests/backtest/ember/test_report.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_report.py
import datetime as dt
import csv
from backtest.ember.engine import TradeResult
from backtest.ember.report import summarize, write_trades_csv


def _tr(pnl, reason="PT", minute=10):
    return TradeResult(
        trade_date=dt.date(2024, 6, 3), policy="p", entry_minute=0, exit_minute=minute,
        exit_reason=reason, entry_credit=1.0, exit_cost=0.5, pnl=pnl, max_favorable=pnl, max_adverse=-1.0,
    )


def test_summarize_basic_stats():
    trades = [_tr(40), _tr(40), _tr(-60), _tr(40)]
    s = summarize(trades)
    assert s["n"] == 4
    assert s["win_rate"] == 75.0
    assert abs(s["ev_per_contract"] - 15.0) < 1e-9   # (40+40-60+40)/4
    assert abs(s["total_pnl"] - 60.0) < 1e-9
    assert s["max_drawdown"] >= 0.0


def test_summarize_empty():
    s = summarize([])
    assert s["n"] == 0
    assert s["win_rate"] == 0.0
    assert s["ev_per_contract"] == 0.0


def test_pct_eod_counts_eod_exits():
    s = summarize([_tr(10, reason="EOD"), _tr(10, reason="PT")])
    assert s["pct_eod"] == 50.0


def test_write_trades_csv(tmp_path):
    path = tmp_path / "trades.csv"
    write_trades_csv([_tr(40), _tr(-60)], str(path))
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 2
    assert rows[0]["exit_reason"] == "PT"
    assert "pnl" in rows[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_report.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.report'`

- [ ] **Step 3: Write `report.py`**

```python
# backtest/ember/report.py
from __future__ import annotations

import csv
import statistics
from dataclasses import asdict
from typing import Dict, List

from backtest.ember.engine import TradeResult


def summarize(trades: List[TradeResult]) -> Dict[str, float]:
    """Per-policy summary stats. Sharpe is per-trade (mean/std), not annualized."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "win_rate": 0.0, "ev_per_contract": 0.0, "total_pnl": 0.0,
                "sharpe": 0.0, "max_drawdown": 0.0, "avg_hold_min": 0.0, "pct_eod": 0.0}
    pnls = [t.pnl for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    mean = total / n
    std = statistics.pstdev(pnls) if n > 1 else 0.0
    sharpe = (mean / std) if std > 0 else 0.0
    # max drawdown of the cumulative equity curve (in dollars, positive number)
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += p
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    avg_hold = sum(t.exit_minute - t.entry_minute for t in trades) / n
    pct_eod = 100.0 * sum(1 for t in trades if t.exit_reason == "EOD") / n
    return {
        "n": n,
        "win_rate": round(100.0 * wins / n, 2),
        "ev_per_contract": round(mean, 4),
        "total_pnl": round(total, 2),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 2),
        "avg_hold_min": round(avg_hold, 1),
        "pct_eod": round(pct_eod, 2),
    }


def write_trades_csv(trades: List[TradeResult], path: str) -> None:
    fields = list(asdict(trades[0]).keys()) if trades else [
        "trade_date", "policy", "entry_minute", "exit_minute", "exit_reason",
        "entry_credit", "exit_cost", "pnl", "max_favorable", "max_adverse",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow(asdict(t))


def write_summary_csv(rows: List[Dict], path: str) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def write_report_md(
    path: str,
    *,
    fill: str,
    best: Dict,
    baseline: Dict,
    oos_best: Dict,
    n_days: int,
) -> None:
    lines = [
        "# EMBER Phase 1 — SPARK 1DTE intraday exit study",
        "",
        f"- Trading days: {n_days}",
        f"- Headline fill model: `{fill}`",
        "",
        "## Best policy (in-sample)",
        f"- **{best.get('policy', '?')}** — EV/contract ${best.get('ev_per_contract', 0)}, "
        f"win rate {best.get('win_rate', 0)}%, total ${best.get('total_pnl', 0)}, "
        f"Sharpe {best.get('sharpe', 0)}, maxDD ${best.get('max_drawdown', 0)}",
        "",
        "## SPARK live baseline (PT 30 / SL 0.5x / EOD)",
        f"- EV/contract ${baseline.get('ev_per_contract', 0)}, win rate {baseline.get('win_rate', 0)}%, "
        f"total ${baseline.get('total_pnl', 0)}",
        "",
        "## Out-of-sample (2025) check of the chosen policy",
        f"- EV/contract ${oos_best.get('ev_per_contract', 0)}, win rate {oos_best.get('win_rate', 0)}%, "
        f"total ${oos_best.get('total_pnl', 0)}",
        "",
    ]
    with open(path, "w") as f:
        f.write("\n".join(lines))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_report.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/report.py tests/backtest/ember/test_report.py
git commit -m "feat(ember): summary metrics + CSV/markdown report writers"
```

---

## Task 7: Walk-forward split (`walkforward.py`)

**Files:**
- Create: `backtest/ember/walkforward.py`
- Test: `tests/backtest/ember/test_walkforward.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_walkforward.py
import datetime as dt
from backtest.ember.walkforward import split


def test_split_default_2024_train_2025_oos():
    dates = [dt.date(2023, 1, 3), dt.date(2024, 12, 31), dt.date(2025, 1, 2), dt.date(2025, 6, 1)]
    train, oos = split(dates)
    assert train == [dt.date(2023, 1, 3), dt.date(2024, 12, 31)]
    assert oos == [dt.date(2025, 1, 2), dt.date(2025, 6, 1)]


def test_split_custom_boundary():
    dates = [dt.date(2024, 1, 1), dt.date(2024, 7, 1)]
    train, oos = split(dates, train_end=dt.date(2024, 3, 31))
    assert train == [dt.date(2024, 1, 1)]
    assert oos == [dt.date(2024, 7, 1)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_walkforward.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.walkforward'`

- [ ] **Step 3: Write `walkforward.py`**

```python
# backtest/ember/walkforward.py
from __future__ import annotations

import datetime as dt
from typing import List, Tuple

DEFAULT_TRAIN_END = dt.date(2024, 12, 31)


def split(
    trade_dates: List[dt.date],
    train_end: dt.date = DEFAULT_TRAIN_END,
) -> Tuple[List[dt.date], List[dt.date]]:
    """Partition dates into in-sample (<= train_end) and out-of-sample (> train_end)."""
    train = sorted(d for d in trade_dates if d <= train_end)
    oos = sorted(d for d in trade_dates if d > train_end)
    return train, oos
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_walkforward.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/walkforward.py tests/backtest/ember/test_walkforward.py
git commit -m "feat(ember): walk-forward train/OOS date split"
```

---

## Task 8: Data layer (`data.py`)

Splits into a thin DB query and a **pure** row→`DayChain` builder (unit-tested with fake rows). The live query is covered by an integration test that skips when `DATABASE_URL` is unset. Spot per minute is derived via put-call parity at the strike with the smallest `|call_mid - put_mid|` (nearest the forward).

**Files:**
- Create: `backtest/ember/data.py`
- Test: `tests/backtest/ember/test_data.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_data.py
import datetime as dt
import os
import math
import pytest
from backtest.ember.data import build_day_chain, t_years, delta_at, load_day, list_trade_dates


def _row(minute, strike, right, bid, ask, close):
    return {"minute": minute, "strike": strike, "right": right, "bid": bid, "ask": ask, "close": close}


def test_build_day_chain_groups_and_derives_spot():
    # At minute 0: 100C mid=2.0, 100P mid=1.0 -> spot ~ 100 + (2-1) = 101 (discount ~1 at 1DTE)
    rows = [
        _row(0, 100.0, "C", 1.9, 2.1, 2.0),
        _row(0, 100.0, "P", 0.9, 1.1, 1.0),
        _row(0, 105.0, "C", 0.4, 0.6, 0.5),
        _row(0, 105.0, "P", 5.0, 5.2, 5.1),
    ]
    day = build_day_chain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), rows)
    assert day.sorted_minutes == [0]
    # spot from the strike minimizing |C-P| -> strike 100 (|2-1|=1 < |0.5-5.1|)
    assert math.isclose(day.spot(0), 101.0, abs_tol=0.5)
    assert day.quote(0, 100.0, "C").mid == 2.0


def test_build_day_chain_skips_minute_without_both_rights():
    rows = [_row(5, 100.0, "C", 1.0, 1.2, 1.1)]  # no put -> can't derive spot
    day = build_day_chain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), rows)
    assert day.sorted_minutes == []   # minute dropped


def test_t_years_positive_and_small_for_1dte():
    # minute 0 on day T (09:30 ET), expiry 16:00 ET next day -> < 2 calendar days
    ty = t_years(dt.date(2024, 6, 3), dt.date(2024, 6, 4), minute=0)
    assert 0 < ty < (2.0 / 365.0)


def test_delta_at_short_put_is_negative_small():
    rows = [
        _row(0, 100.0, "C", 1.9, 2.1, 2.0),
        _row(0, 100.0, "P", 0.9, 1.1, 1.0),
        _row(0, 95.0, "C", 5.0, 5.2, 5.1),
        _row(0, 95.0, "P", 0.2, 0.3, 0.25),
    ]
    day = build_day_chain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), rows)
    d = delta_at(day, minute=0, strike=95.0, right="P")
    assert d is None or (-0.5 < d < 0.0)


@pytest.mark.integration
def test_load_day_live_db():
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set")
    dates = list_trade_dates(os.environ["DATABASE_URL"], dt.date(2024, 1, 1), dt.date(2024, 1, 31))
    assert dates, "expected some 1DTE trading days in Jan 2024"
    day = load_day(dates[0], os.environ["DATABASE_URL"])
    assert day.sorted_minutes
    assert 0 <= day.sorted_minutes[0] <= 5
    mid_min = day.sorted_minutes[len(day.sorted_minutes) // 2]
    assert day.spot(mid_min) and 300 < day.spot(mid_min) < 800
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_data.py -v -m "not integration"`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.data'`

- [ ] **Step 3: Register the `integration` marker and write `data.py`**

First ensure the marker exists (append to repo-root `pytest.ini` under `[pytest] markers:` if not already present — check first with `grep -n "integration" pytest.ini`; only add if missing):

```ini
markers =
    integration: tests that hit the live database (skipped without DATABASE_URL)
```

```python
# backtest/ember/data.py
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras

from quant.bs import DEFAULT_R, bs_delta, derive_spot_from_parity, implied_vol
from backtest.ember.models import DayChain, MinuteChain, Quote

# Minutes since 09:30 ET, computed in the America/New_York wall clock.
_DAY_ROWS_SQL = """
    SELECT
        (EXTRACT(EPOCH FROM (
            (bar_time AT TIME ZONE 'America/New_York')
            - date_trunc('day', bar_time AT TIME ZONE 'America/New_York')
            - INTERVAL '9 hours 30 minutes'
        )) / 60)::int AS minute,
        strike::float8 AS strike,
        "right"        AS right,
        bid::float8    AS bid,
        ask::float8    AS ask,
        close::float8  AS close
    FROM helios_options_intraday
    WHERE trade_date = %s
      AND (expiration_date - trade_date) = 1
    ORDER BY minute, strike
"""

_DATES_SQL = """
    SELECT DISTINCT trade_date
    FROM helios_options_intraday
    WHERE (expiration_date - trade_date) = 1
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date
"""


def query_day_rows(trade_date: dt.date, db_url: str) -> List[dict]:
    with psycopg2.connect(db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(_DAY_ROWS_SQL, (trade_date,))
            return [dict(r) for r in c.fetchall()]


def list_trade_dates(db_url: str, start: dt.date, end: dt.date) -> List[dt.date]:
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as c:
            c.execute(_DATES_SQL, (start, end))
            return [r[0] for r in c.fetchall()]


def t_years(trade_date: dt.date, expiration: dt.date, minute: int) -> float:
    """Calendar time from the given minute (09:30 ET + minute) to 16:00 ET on expiry, in years."""
    bar = dt.datetime.combine(trade_date, dt.time(9, 30)) + dt.timedelta(minutes=minute)
    expiry_close = dt.datetime.combine(expiration, dt.time(16, 0))
    seconds = (expiry_close - bar).total_seconds()
    return max(seconds, 0.0) / (365.0 * 24 * 3600)


def build_day_chain(trade_date: dt.date, expiration: dt.date, rows: List[dict]) -> DayChain:
    """Pure transform: rows -> DayChain. Derives spot per minute via put-call parity.

    A minute is kept only if it has at least one strike with BOTH a call and a put
    (needed to derive spot)."""
    by_minute: Dict[int, Dict[Tuple[float, str], Quote]] = {}
    for r in rows:
        minute = int(r["minute"])
        if minute < 0 or minute > 390:
            continue
        q = Quote(bid=float(r["bid"] or 0.0), ask=float(r["ask"] or 0.0), close=float(r["close"] or 0.0))
        by_minute.setdefault(minute, {})[(float(r["strike"]), r["right"])] = q

    minutes: Dict[int, MinuteChain] = {}
    for minute, quotes in by_minute.items():
        ty = t_years(trade_date, expiration, minute)
        # find strikes that have both C and P
        strikes = {k[0] for k in quotes}
        paired = [s for s in strikes if (s, "C") in quotes and (s, "P") in quotes]
        if not paired:
            continue
        atm = min(paired, key=lambda s: abs(quotes[(s, "C")].mid - quotes[(s, "P")].mid))
        spot = derive_spot_from_parity(
            quotes[(atm, "C")].mid, quotes[(atm, "P")].mid, atm, t_years=ty, r=DEFAULT_R
        )
        minutes[minute] = MinuteChain(minute=minute, spot=spot, quotes=quotes)

    return DayChain(trade_date=trade_date, expiration=expiration, minutes=minutes)


def delta_at(day: DayChain, minute: int, strike: float, right: str) -> Optional[float]:
    """Black-Scholes delta for one option at a minute, or None if IV won't solve."""
    mc = day.minutes.get(minute)
    if not mc:
        return None
    q = mc.quotes.get((strike, right))
    if not q:
        return None
    ty = t_years(day.trade_date, day.expiration, minute)
    is_call = right == "C"
    sigma = implied_vol(q.mid, mc.spot, strike, ty, is_call)
    if sigma is None:
        return None
    return bs_delta(mc.spot, strike, ty, sigma, is_call)


def load_day(trade_date: dt.date, db_url: str, expiration: Optional[dt.date] = None) -> DayChain:
    rows = query_day_rows(trade_date, db_url)
    exp = expiration or (trade_date + dt.timedelta(days=1))
    return build_day_chain(trade_date, exp, rows)
```

> **Note on `expiration` in `load_day`:** the SQL filters `(expiration_date - trade_date) = 1`, so the expiry is exactly `trade_date + 1` calendar day. `t_years` uses calendar time, which is correct.

- [ ] **Step 4: Run unit tests (skip integration) to verify they pass**

Run: `python -m pytest tests/backtest/ember/test_data.py -v -m "not integration"`
Expected: PASS (4 passed, 1 deselected)

- [ ] **Step 5: (Optional, if `DATABASE_URL` is set) run the integration test**

Run: `python -m pytest tests/backtest/ember/test_data.py::test_load_day_live_db -v`
Expected: PASS (or SKIP if `DATABASE_URL` unset)

- [ ] **Step 6: Commit**

```bash
git add backtest/ember/data.py tests/backtest/ember/test_data.py pytest.ini
git commit -m "feat(ember): DB data layer — day chain loader + parity spot + delta"
```

---

## Task 9: SPARK adapter (`adapters/base.py`, `adapters/spark.py`)

**Files:**
- Create: `backtest/ember/adapters/__init__.py` (empty), `backtest/ember/adapters/base.py`, `backtest/ember/adapters/spark.py`
- Test: `tests/backtest/ember/test_spark_adapter.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backtest/ember/test_spark_adapter.py
import datetime as dt
from backtest.ember.models import Quote, MinuteChain, DayChain
from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.adapters.spark import SparkRepresentativeIC


def _synthetic_day():
    """One minute (entry=0) chain around spot=500, strikes 480..520 step 5, both rights."""
    quotes = {}
    spot = 500.0
    for k in range(480, 521, 5):
        # crude prices: ITM intrinsic + 0.5 time value, OTM 0.5..2.0 decaying
        c_intrinsic = max(spot - k, 0.0)
        p_intrinsic = max(k - spot, 0.0)
        c_mid = c_intrinsic + max(2.5 - 0.05 * abs(k - spot), 0.2)
        p_mid = p_intrinsic + max(2.5 - 0.05 * abs(k - spot), 0.2)
        quotes[(float(k), "C")] = Quote(c_mid - 0.1, c_mid + 0.1, c_mid)
        quotes[(float(k), "P")] = Quote(p_mid - 0.1, p_mid + 0.1, p_mid)
    mc = MinuteChain(minute=0, spot=spot, quotes=quotes)
    return DayChain(dt.date(2024, 6, 3), dt.date(2024, 6, 4), {0: mc})


def test_spark_adapter_builds_iron_condor():
    day = _synthetic_day()
    cfg = AdapterConfig(entry_minute=0, short_delta=0.16, wing_width=5.0)
    adapter = SparkRepresentativeIC()
    assert adapter.eligible(day, cfg)
    pos = adapter.build_entry(day, cfg)
    assert pos is not None
    # 4 legs: short put, long put (lower), short call, long call (higher)
    assert len(pos.legs) == 4
    rights = sorted(leg.right for leg in pos.legs)
    assert rights == ["C", "C", "P", "P"]
    # net qty zero (2 short, 2 long)
    assert sum(leg.qty for leg in pos.legs) == 0
    # entry credit positive
    assert pos.entry_credit > 0
    # wings are wing_width away from shorts
    puts = sorted([leg for leg in pos.legs if leg.right == "P"], key=lambda l: l.strike)
    calls = sorted([leg for leg in pos.legs if leg.right == "C"], key=lambda l: l.strike)
    assert puts[0].qty == 1 and puts[1].qty == -1     # long put below short put
    assert calls[1].qty == 1 and calls[0].qty == -1   # long call above short call


def test_spark_adapter_ineligible_when_entry_minute_missing():
    day = _synthetic_day()
    cfg = AdapterConfig(entry_minute=99, short_delta=0.16, wing_width=5.0)
    assert not SparkRepresentativeIC().eligible(day, cfg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_spark_adapter.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.adapters'`

- [ ] **Step 3: Write the adapter base and SPARK adapter**

```python
# backtest/ember/adapters/__init__.py  -> empty file
```

```python
# backtest/ember/adapters/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from backtest.ember.models import DayChain, Position


@dataclass(frozen=True)
class AdapterConfig:
    entry_minute: int = 0          # minutes since 09:30 ET
    short_delta: float = 0.16      # target |delta| for short strikes
    wing_width: float = 5.0        # dollars between short and long strike


class StrategyAdapter(Protocol):
    def eligible(self, day: DayChain, cfg: AdapterConfig) -> bool: ...
    def build_entry(self, day: DayChain, cfg: AdapterConfig) -> Optional[Position]: ...
```

```python
# backtest/ember/adapters/spark.py
from __future__ import annotations

from typing import Optional

from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.data import delta_at
from backtest.ember.fills import FILL_ASK_CROSS, signed_cashflow
from backtest.ember.models import DayChain, Leg, Position


class SparkRepresentativeIC:
    """Builds one representative 1DTE SPY iron condor per day.

    Short strikes are chosen at the target |delta|; wings sit `wing_width`
    dollars further OTM. Entry credit is priced conservatively (ask-cross)."""

    def eligible(self, day: DayChain, cfg: AdapterConfig) -> bool:
        mc = day.minutes.get(cfg.entry_minute)
        if not mc:
            return False
        # need at least a few strikes each side and a spot
        return mc.spot is not None and len(mc.quotes) >= 8

    def _pick_short(self, day: DayChain, cfg: AdapterConfig, right: str) -> Optional[float]:
        mc = day.minutes[cfg.entry_minute]
        spot = mc.spot
        best_strike = None
        best_err = float("inf")
        for (strike, r) in mc.quotes:
            if r != right:
                continue
            # restrict to OTM side
            if right == "P" and strike >= spot:
                continue
            if right == "C" and strike <= spot:
                continue
            d = delta_at(day, cfg.entry_minute, strike, right)
            if d is None:
                continue
            err = abs(abs(d) - cfg.short_delta)
            if err < best_err:
                best_err, best_strike = err, strike
        return best_strike

    def build_entry(self, day: DayChain, cfg: AdapterConfig) -> Optional[Position]:
        if not self.eligible(day, cfg):
            return None
        mc = day.minutes[cfg.entry_minute]
        short_put = self._pick_short(day, cfg, "P")
        short_call = self._pick_short(day, cfg, "C")
        if short_put is None or short_call is None:
            return None
        long_put = short_put - cfg.wing_width
        long_call = short_call + cfg.wing_width

        legs = [
            Leg(short_put, "P", -1),
            Leg(long_put, "P", 1),
            Leg(short_call, "C", -1),
            Leg(long_call, "C", 1),
        ]
        # all four legs must quote at entry
        for leg in legs:
            if (leg.strike, leg.right) not in mc.quotes:
                return None
        credit = signed_cashflow(legs, mc.quotes, action="open", fill=FILL_ASK_CROSS)
        if credit <= 0:
            return None
        return Position(legs=legs, entry_minute=cfg.entry_minute, entry_credit=credit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_spark_adapter.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backtest/ember/adapters/ tests/backtest/ember/test_spark_adapter.py
git commit -m "feat(ember): StrategyAdapter protocol + SPARK representative IC adapter"
```

---

## Task 10: CLI orchestration (`cli.py`, `__main__.py`)

Wires everything: list trade dates → load each day → build entry → evaluate every policy → split walk-forward → pick best in-sample policy by EV (tie-break Sharpe) → evaluate it OOS → write artifacts.

**Files:**
- Create: `backtest/ember/cli.py`, `backtest/ember/__main__.py`
- Test: `tests/backtest/ember/test_cli_smoke.py`

- [ ] **Step 1: Write the failing test** (smoke test of the pure orchestration core, no DB)

```python
# tests/backtest/ember/test_cli_smoke.py
import datetime as dt
from backtest.ember.models import Quote, MinuteChain, DayChain
from backtest.ember.policy import default_grid
from backtest.ember.cli import run_policies_for_day, pick_best


def _day(trade_date, decay):
    """Iron-condor-able day: spot 500, strikes 480..520, combo decays by `decay` factor by EOD."""
    minutes = {}
    spot = 500.0
    for m, factor in [(0, 1.0), (200, 1.0 - decay / 2), (385, 1.0 - decay)]:
        quotes = {}
        for k in range(480, 521, 5):
            c_intrinsic = max(spot - k, 0.0)
            p_intrinsic = max(k - spot, 0.0)
            tv = max(2.5 - 0.05 * abs(k - spot), 0.2) * factor
            c_mid = c_intrinsic + tv
            p_mid = p_intrinsic + tv
            quotes[(float(k), "C")] = Quote(c_mid - 0.1, c_mid + 0.1, c_mid)
            quotes[(float(k), "P")] = Quote(p_mid - 0.1, p_mid + 0.1, p_mid)
        minutes[m] = MinuteChain(minute=m, spot=spot, quotes=quotes)
    return DayChain(trade_date, trade_date + dt.timedelta(days=1), minutes)


def test_run_and_pick_best_produces_results():
    from backtest.ember.adapters.base import AdapterConfig
    from backtest.ember.adapters.spark import SparkRepresentativeIC
    from backtest.ember.fills import FILL_MID

    days = [_day(dt.date(2024, 1, 3 + i), decay=0.6) for i in range(5)]
    adapter = SparkRepresentativeIC()
    cfg = AdapterConfig(entry_minute=0, short_delta=0.16, wing_width=5.0)
    grid = default_grid()

    # results: policy_name -> list[TradeResult]
    results = {}
    for day in days:
        per_day = run_policies_for_day(day, adapter, cfg, grid, fill=FILL_MID)
        for name, tr in per_day.items():
            results.setdefault(name, []).append(tr)

    assert results, "expected trades for at least one policy"
    best_name, best_summary = pick_best(results)
    assert best_name in results
    assert best_summary["n"] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/backtest/ember/test_cli_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backtest.ember.cli'`

- [ ] **Step 3: Write `cli.py` and `__main__.py`**

```python
# backtest/ember/cli.py
from __future__ import annotations

import argparse
import datetime as dt
import os
from typing import Dict, List, Tuple

from backtest.ember.adapters.base import AdapterConfig
from backtest.ember.adapters.spark import SparkRepresentativeIC
from backtest.ember.data import list_trade_dates, load_day
from backtest.ember.engine import TradeResult, evaluate_exit
from backtest.ember.fills import FILL_ASK_CROSS, FILL_MID, FILL_MID_SLIP
from backtest.ember.policy import ExitPolicy, default_grid
from backtest.ember.report import (summarize, write_report_md, write_summary_csv, write_trades_csv)
from backtest.ember.walkforward import split


def run_policies_for_day(day, adapter, cfg: AdapterConfig, grid: List[ExitPolicy], fill: str) -> Dict[str, TradeResult]:
    """Build the day's entry once, evaluate every policy against it."""
    out: Dict[str, TradeResult] = {}
    pos = adapter.build_entry(day, cfg)
    if pos is None:
        return out
    for policy in grid:
        tr = evaluate_exit(day, pos, policy, fill=fill)
        if tr is not None:
            out[policy.name] = tr
    return out


def pick_best(results: Dict[str, List[TradeResult]]) -> Tuple[str, dict]:
    """Choose the policy with the highest EV/contract, tie-broken by Sharpe."""
    best_name, best_summary, best_key = None, None, (float("-inf"), float("-inf"))
    for name, trades in results.items():
        s = summarize(trades)
        key = (s["ev_per_contract"], s["sharpe"])
        if key > best_key:
            best_key, best_name, best_summary = key, name, dict(s, policy=name)
    return best_name, best_summary


def run(start: dt.date, end: dt.date, fill: str, out_dir: str, db_url: str,
        entry_minute: int, short_delta: float, wing_width: float) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    adapter = SparkRepresentativeIC()
    cfg = AdapterConfig(entry_minute=entry_minute, short_delta=short_delta, wing_width=wing_width)
    grid = default_grid()

    dates = list_trade_dates(db_url, start, end)
    train_dates, oos_dates = split(dates)

    train_results: Dict[str, List[TradeResult]] = {}
    oos_results: Dict[str, List[TradeResult]] = {}
    all_trades: List[TradeResult] = []

    for d in dates:
        day = load_day(d, db_url)
        per_day = run_policies_for_day(day, adapter, cfg, grid, fill=fill)
        bucket = train_results if d in set(train_dates) else oos_results
        for name, tr in per_day.items():
            bucket.setdefault(name, []).append(tr)
            all_trades.append(tr)

    best_name, best_summary = pick_best(train_results)
    baseline_summary = dict(summarize(train_results.get("spark_live", [])), policy="spark_live")
    oos_best_summary = dict(summarize(oos_results.get(best_name, [])), policy=best_name)

    # artifacts
    write_trades_csv(all_trades, os.path.join(out_dir, "trades.csv"))
    summary_rows = [dict(summarize(v), policy=k) for k, v in sorted(train_results.items())]
    write_summary_csv(summary_rows, os.path.join(out_dir, "summary.csv"))
    write_report_md(
        os.path.join(out_dir, "report.md"),
        fill=fill, best=best_summary, baseline=baseline_summary,
        oos_best=oos_best_summary, n_days=len(dates),
    )
    return {"best": best_summary, "baseline": baseline_summary, "oos_best": oos_best_summary,
            "n_days": len(dates), "out_dir": out_dir}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m backtest.ember", description="EMBER Phase 1 SPARK exit study")
    p.add_argument("--start", default="2023-01-03", type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--end", default="2025-12-05", type=lambda s: dt.date.fromisoformat(s))
    p.add_argument("--fill", default=FILL_ASK_CROSS, choices=[FILL_ASK_CROSS, FILL_MID, FILL_MID_SLIP])
    p.add_argument("--out", default="backtest/ember/out/latest")
    p.add_argument("--entry-minute", default=30, type=int, help="minutes since 09:30 ET (default 30 = 10:00 ET)")
    p.add_argument("--short-delta", default=0.16, type=float)
    p.add_argument("--wing-width", default=5.0, type=float)
    args = p.parse_args(argv)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return 1

    res = run(args.start, args.end, args.fill, args.out, db_url,
              args.entry_minute, args.short_delta, args.wing_width)
    b, base, oos = res["best"], res["baseline"], res["oos_best"]
    print(f"Days: {res['n_days']}  ->  artifacts in {res['out_dir']}")
    print(f"BEST  (in-sample): {b['policy']:>18}  EV/ct ${b['ev_per_contract']:>8}  WR {b['win_rate']}%  total ${b['total_pnl']}")
    print(f"SPARK baseline   : {base['policy']:>18}  EV/ct ${base['ev_per_contract']:>8}  WR {base['win_rate']}%  total ${base['total_pnl']}")
    print(f"BEST  (OOS 2025) : {oos['policy']:>18}  EV/ct ${oos['ev_per_contract']:>8}  WR {oos['win_rate']}%  total ${oos['total_pnl']}")
    return 0
```

```python
# backtest/ember/__main__.py
import sys
from backtest.ember.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/backtest/ember/test_cli_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run the whole EMBER test suite**

Run: `python -m pytest tests/backtest/ember/ -v -m "not integration"`
Expected: PASS (all tasks' tests green)

- [ ] **Step 6: Commit**

```bash
git add backtest/ember/cli.py backtest/ember/__main__.py tests/backtest/ember/test_cli_smoke.py
git commit -m "feat(ember): CLI orchestration — sweep, walk-forward, artifacts"
```

---

## Task 11: First live run + sanity check (manual gate)

This is the Phase 1 deliverable: run against real data, eyeball the artifacts, confirm correctness before declaring done.

- [ ] **Step 1: Run a short live window first (one month) to validate plumbing**

Run (pipe through tee — Render shells have no scrollback, per repo convention):
```bash
DATABASE_URL="$DATABASE_URL" python -m backtest.ember --start 2024-01-02 --end 2024-01-31 --fill ask_cross --out backtest/ember/out/jan2024 2>&1 | tee /tmp/ember_jan2024.txt
```
Expected: prints a BEST / SPARK baseline / OOS line (OOS will be empty for a 2024-only window — that is fine for this smoke run) and writes `backtest/ember/out/jan2024/{trades.csv,summary.csv,report.md}`.

- [ ] **Step 2: Sanity-check `trades.csv`**

Open `backtest/ember/out/jan2024/trades.csv`. Verify by inspection:
- `entry_credit > 0` and `0 <= exit_cost` on most rows.
- `exit_minute >= entry_minute` always.
- `exit_reason` ∈ {PT, SL, TRAIL, TIME, EOD}.
- Spot-implied: pick one trade, confirm `pnl ≈ (entry_credit - exit_cost) * 100 - 2.6` (4-leg commission).

- [ ] **Step 3: Run the full window**

```bash
DATABASE_URL="$DATABASE_URL" python -m backtest.ember --start 2023-01-03 --end 2025-12-05 --fill ask_cross --out backtest/ember/out/full 2>&1 | tee /tmp/ember_full.txt
```
Expected: ~560+ 1DTE days processed; `report.md` shows in-sample best vs SPARK baseline vs OOS-2025 of the chosen policy.

- [ ] **Step 4: Re-run under the two sensitivity fills**

```bash
DATABASE_URL="$DATABASE_URL" python -m backtest.ember --start 2023-01-03 --end 2025-12-05 --fill mid --out backtest/ember/out/full_mid 2>&1 | tee /tmp/ember_full_mid.txt
DATABASE_URL="$DATABASE_URL" python -m backtest.ember --start 2023-01-03 --end 2025-12-05 --fill mid_slip --out backtest/ember/out/full_slip 2>&1 | tee /tmp/ember_full_slip.txt
```
Expected: the chosen policy's edge should not flip sign between `ask_cross` and `mid` — if it does, the edge is fill-fragile (flag it in the report; that is itself a finding).

- [ ] **Step 5: Record the finding and commit the report**

Append a short findings paragraph to `report.md` (best policy, whether it beats SPARK's live PT30/SL0.5x baseline, OOS hold-up, fill sensitivity, GO/NO-GO on the *strategy*). Then:
```bash
git add backtest/ember/out/full/report.md backtest/ember/out/full/summary.csv
git commit -m "docs(ember): Phase 1 full-run report + exit-policy finding"
```
> Note: `trades.csv` files can be large; `.gitignore` `backtest/ember/out/**/trades.csv` if size is a concern. Commit `report.md` + `summary.csv` (small) so the result is in git.

---

## Self-Review

**1. Spec coverage** (each spec section → task):
- §5 architecture / package layout → Tasks 2–10 (matches the file tree exactly).
- §6 data layer (spot via parity, greeks via BS, combo bid/ask, liquidity guards) → Task 8 (`build_day_chain`, `t_years`, `delta_at`) + Task 3 (combo pricing); null/missing guards in `build_day_chain` (skips minutes without paired C/P) and `price_path` (forward-fills missing-leg minutes).
- §7 SPARK representative adapter (entry time, delta shorts, wings) → Task 9 + CLI flags (`--entry-minute` default 30 = 10:00 ET, `--short-delta` 0.16, `--wing-width` 5).
- §8 exit sweep (PT/SL/time/trailing + baseline) → Task 4 (`default_grid`, `SPARK_BASELINE`) + Task 5 (engine precedence incl. trailing).
- §9 fill model (ask-cross headline + mid/slippage bands) → Task 3 + CLI `--fill` + Task 11 Step 4.
- §10 walk-forward (2023–24 train / 2025 OOS) → Task 7 + CLI wiring; external 2026 sanity check is **out of this plan's automated scope** (the table has no 2026 data; noted as a manual follow-up — see gap below).
- §11 StrategyAdapter seam → Task 9 (`base.py` Protocol).
- §12 outputs (trades.csv, summary.csv, sweep, report.md) + success criteria → Task 6 + Task 11. **Gap fixed:** the spec lists a `sweep.json` heatmap artifact; `summary.csv` (per-policy PT×SL grid) covers the same data for Phase 1, and the Phase 3 UI can derive the heatmap from it — explicitly deferring `sweep.json` to Phase 3 rather than building an unused artifact now (YAGNI).

**2. Placeholder scan:** No "TBD/TODO/handle edge cases" — every code step has complete code; every test step has real assertions. The one `pytest.ini` edit is conditional with a check-first instruction.

**3. Type consistency:** `Quote/Leg/Position/MinuteChain/DayChain` (Task 2) are used with identical signatures everywhere. `signed_cashflow(legs, quotes, action, fill, slippage)` (Task 3) is called identically in `engine.price_path` and `spark.build_entry`. `evaluate_exit(chain, position, policy, fill, slippage)` and `TradeResult` fields (Task 5) match their use in `report.summarize`/`write_trades_csv` (Task 6) and `cli.run_policies_for_day` (Task 10). `AdapterConfig(entry_minute, short_delta, wing_width)` is consistent across Tasks 9–10. Minute convention (since 09:30 ET) is consistent in `data._DAY_ROWS_SQL`, `t_years`, `policy.default_grid` time-stops, and the CLI `--entry-minute` help text.

**Known follow-ups (intentionally deferred, not gaps):**
- External 2026 SPARK-trades sanity check (spec §10) — manual, needs the live `spark_positions` table, done after the engine ships.
- 2DTE/3DTE coverage exists in the data but Phase 1 filters to `dte=1` (SPARK's regime) by design.
