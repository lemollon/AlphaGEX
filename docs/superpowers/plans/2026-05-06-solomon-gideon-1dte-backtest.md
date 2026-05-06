# SOLOMON / GIDEON 1DTE Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a modular Python backtest harness that runs the SOLOMON and GIDEON GEX-walls directional entry signal on SPY 1DTE debit spreads, hold-to-expiration, against ORAT's 6-year EOD chain history (2020-2025).

**Architecture:** Pure-function components (signals, pricing, payoff) wired together by an engine that drives a daily loop, with a thin data layer over the ORAT postgres and a report writer that emits CSV/JSON scorecards. No DB writes, no live trading impact.

**Tech Stack:** Python 3.11, pandas, psycopg2, pytest. Reads from ORAT postgres via `ORAT_DATABASE_URL` env var. No new dependencies needed.

**Spec:** `docs/superpowers/specs/2026-05-06-solomon-gideon-1dte-backtest-design.md`

---

## File Structure

```
backtest/directional_1dte/
├── __init__.py        # package marker
├── __main__.py        # CLI entry (argparse, runs engine, calls report)
├── config.py          # BotConfig dataclass + SOLOMON, GIDEON, BOT_CONFIGS
├── data.py            # 4 ORAT loaders: trading_days, chain, vix, walls
├── signals.py         # Signal dataclass + generate_signal pure function
├── pricing.py         # select_strikes + lookup_debit
├── payoff.py          # compute_payoff pure function
├── engine.py          # Trade dataclass + BacktestResult + run()
├── report.py          # write_results(): CSVs + JSON + run.json + comparison
└── tests/
    ├── __init__.py
    ├── conftest.py    # synthetic chain/walls fixtures
    ├── test_signals.py
    ├── test_pricing.py
    ├── test_payoff.py
    ├── test_engine.py
    ├── test_data_integration.py   # ORAT-hitting, marked @pytest.mark.integration
    └── test_report.py
```

Output directory: `backtest/results/2026-05-06-solomon-gideon-1dte/{solomon,gideon}/`.

---

### Task 1: Package skeleton + config

**Files:**
- Create: `backtest/directional_1dte/__init__.py`
- Create: `backtest/directional_1dte/config.py`
- Create: `backtest/directional_1dte/tests/__init__.py`
- Create: `backtest/directional_1dte/tests/conftest.py`

- [ ] **Step 1: Create empty package markers**

```bash
mkdir -p backtest/directional_1dte/tests
touch backtest/directional_1dte/__init__.py
touch backtest/directional_1dte/tests/__init__.py
```

- [ ] **Step 2: Write the failing test for config**

Create `backtest/directional_1dte/tests/conftest.py`:

```python
import pytest
from backtest.directional_1dte.config import BOT_CONFIGS, BotConfig


@pytest.fixture
def solomon():
    return BOT_CONFIGS["solomon"]


@pytest.fixture
def gideon():
    return BOT_CONFIGS["gideon"]
```

Append to `backtest/directional_1dte/tests/__init__.py` (leave empty — marker only).

Create `backtest/directional_1dte/tests/test_config.py`:

```python
from backtest.directional_1dte.config import BOT_CONFIGS, SOLOMON, GIDEON


def test_solomon_matches_live_production():
    assert SOLOMON.name == "solomon"
    assert SOLOMON.ticker == "SPY"
    assert SOLOMON.wall_filter_pct == 1.0
    assert SOLOMON.spread_width == 2
    assert SOLOMON.min_vix == 12.0
    assert SOLOMON.max_vix == 35.0
    assert SOLOMON.risk_per_trade == 1000.0
    assert SOLOMON.starting_capital == 100000.0


def test_gideon_matches_live_production():
    assert GIDEON.name == "gideon"
    assert GIDEON.spread_width == 3
    assert GIDEON.max_vix == 30.0  # tighter than SOLOMON


def test_bot_configs_dict():
    assert set(BOT_CONFIGS.keys()) == {"solomon", "gideon"}
    assert BOT_CONFIGS["solomon"] is SOLOMON
    assert BOT_CONFIGS["gideon"] is GIDEON
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest backtest/directional_1dte/tests/test_config.py -v`
Expected: FAIL with `ImportError: cannot import name 'BOT_CONFIGS' from 'backtest.directional_1dte.config'`

- [ ] **Step 4: Implement config**

Create `backtest/directional_1dte/config.py`:

```python
"""Per-bot configuration for the SOLOMON / GIDEON 1DTE backtest.

Mirrors live production parameters from trading/solomon_v2/models.py
and trading/gideon/models.py. Risk and capital are research defaults.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    name: str
    ticker: str
    wall_filter_pct: float
    spread_width: int
    min_vix: float
    max_vix: float
    risk_per_trade: float
    starting_capital: float


SOLOMON = BotConfig(
    name="solomon",
    ticker="SPY",
    wall_filter_pct=1.0,
    spread_width=2,
    min_vix=12.0,
    max_vix=35.0,
    risk_per_trade=1000.0,
    starting_capital=100000.0,
)

GIDEON = BotConfig(
    name="gideon",
    ticker="SPY",
    wall_filter_pct=1.0,
    spread_width=3,
    min_vix=12.0,
    max_vix=30.0,
    risk_per_trade=1000.0,
    starting_capital=100000.0,
)

BOT_CONFIGS: dict[str, BotConfig] = {
    "solomon": SOLOMON,
    "gideon": GIDEON,
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest backtest/directional_1dte/tests/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backtest/directional_1dte/
git commit -m "feat: 1dte backtest package skeleton + bot configs"
```

---

### Task 2: Payoff function (TDD)

**Files:**
- Create: `backtest/directional_1dte/payoff.py`
- Create: `backtest/directional_1dte/tests/test_payoff.py`

- [ ] **Step 1: Write the failing test**

Create `backtest/directional_1dte/tests/test_payoff.py`:

```python
import pytest
from backtest.directional_1dte.payoff import compute_payoff


class TestBullCall:
    """Bull call spread: long ATM call, short OTM call."""

    def test_full_payoff_above_short_strike(self):
        # Long 500, short 502, spot at 510 -> max payoff = width = 2
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 510.0) == 2.0

    def test_zero_payoff_below_long_strike(self):
        # Long 500, short 502, spot at 495 -> 0
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 495.0) == 0.0

    def test_partial_payoff_between_strikes(self):
        # Long 500, short 502, spot at 501 -> 1.0
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 501.0) == 1.0

    def test_payoff_at_long_strike(self):
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 500.0) == 0.0

    def test_payoff_at_short_strike(self):
        assert compute_payoff("BULL_CALL", 500.0, 502.0, 502.0) == 2.0


class TestBearPut:
    """Bear put spread: long ATM put, short OTM put."""

    def test_full_payoff_below_short_strike(self):
        # Long 500, short 498, spot at 490 -> max payoff = 2
        assert compute_payoff("BEAR_PUT", 500.0, 498.0, 490.0) == 2.0

    def test_zero_payoff_above_long_strike(self):
        assert compute_payoff("BEAR_PUT", 500.0, 498.0, 505.0) == 0.0

    def test_partial_payoff_between_strikes(self):
        # Long 500, short 498, spot at 499 -> 1.0
        assert compute_payoff("BEAR_PUT", 500.0, 498.0, 499.0) == 1.0


def test_payoff_bounded_by_width():
    # Way above
    assert compute_payoff("BULL_CALL", 500.0, 502.0, 999.0) == 2.0
    # Way below
    assert compute_payoff("BEAR_PUT", 500.0, 498.0, 0.0) == 2.0


def test_unknown_spread_type_raises():
    with pytest.raises(ValueError, match="Unknown spread_type"):
        compute_payoff("UNKNOWN", 500.0, 502.0, 501.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backtest/directional_1dte/tests/test_payoff.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement payoff**

Create `backtest/directional_1dte/payoff.py`:

```python
"""Hold-to-expiration intrinsic-value payoff for vertical debit spreads."""


def compute_payoff(
    spread_type: str,
    long_strike: float,
    short_strike: float,
    spot_at_expiry: float,
) -> float:
    """Per-share payoff at expiration. Bounded by [0, abs(short_strike - long_strike)]."""
    if spread_type == "BULL_CALL":
        return max(0.0, min(spot_at_expiry, short_strike) - long_strike)
    if spread_type == "BEAR_PUT":
        return max(0.0, long_strike - max(spot_at_expiry, short_strike))
    raise ValueError(f"Unknown spread_type: {spread_type}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backtest/directional_1dte/tests/test_payoff.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/directional_1dte/payoff.py backtest/directional_1dte/tests/test_payoff.py
git commit -m "feat: hold-to-expiration intrinsic payoff for debit spreads"
```

---

### Task 3: Signals function (TDD)

**Files:**
- Create: `backtest/directional_1dte/signals.py`
- Create: `backtest/directional_1dte/tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

Create `backtest/directional_1dte/tests/test_signals.py`:

```python
import pytest
from backtest.directional_1dte.signals import Signal, generate_signal
from backtest.directional_1dte.config import SOLOMON


def walls(call_wall, put_wall, spot):
    return {"call_wall": call_wall, "put_wall": put_wall, "spot": spot}


class TestVixGate:
    def test_skip_when_vix_missing(self, solomon):
        sig, reason = generate_signal(walls(510, 500, 505), spot=505, vix=None, config=solomon)
        assert sig is None
        assert reason == "NO_VIX_DATA"

    def test_skip_when_vix_below_min(self, solomon):
        sig, reason = generate_signal(walls(510, 500, 505), 505, vix=10.0, config=solomon)
        assert sig is None
        assert reason == "VIX_OUT_OF_RANGE"

    def test_skip_when_vix_above_max(self, solomon):
        sig, reason = generate_signal(walls(510, 500, 505), 505, vix=40.0, config=solomon)
        assert sig is None
        assert reason == "VIX_OUT_OF_RANGE"


class TestWallProximity:
    def test_bullish_when_within_filter_of_put_wall(self, solomon):
        # spot 500, put_wall 498 -> 0.4% away (< 1%)
        sig, reason = generate_signal(walls(550, 498, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BULLISH"
        assert sig.spread_type == "BULL_CALL"

    def test_bearish_when_within_filter_of_call_wall(self, solomon):
        # spot 500, call_wall 502 -> 0.4% away
        sig, reason = generate_signal(walls(502, 450, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BEARISH"
        assert sig.spread_type == "BEAR_PUT"

    def test_skip_when_neither_wall_in_range(self, solomon):
        # spot 500, walls 480 and 520 -> 4% away each
        sig, reason = generate_signal(walls(520, 480, 500), 500, vix=18.0, config=solomon)
        assert sig is None
        assert reason == "NOT_NEAR_WALL"


class TestTieBreak:
    def test_picks_closer_wall_in_dollars_when_both_within_filter(self, solomon):
        # spot 500. put_wall 499 ($1 away). call_wall 503 ($3 away). Both within 1%.
        sig, reason = generate_signal(walls(503, 499, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BULLISH"  # closer wall = put_wall

    def test_bullish_wins_exact_dollar_tie(self, solomon):
        # spot 500. put_wall 498.5, call_wall 501.5. Both $1.50 away, both within 1%.
        sig, reason = generate_signal(walls(501.5, 498.5, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BULLISH"


class TestMissingWalls:
    def test_skip_when_walls_dict_is_none(self, solomon):
        sig, reason = generate_signal(None, 500, 18.0, solomon)
        assert sig is None
        assert reason == "NO_WALLS_FOUND"

    def test_skip_when_call_wall_missing(self, solomon):
        sig, reason = generate_signal({"put_wall": 498, "call_wall": None, "spot": 500}, 500, 18.0, solomon)
        assert sig is None
        assert reason == "NO_WALLS_FOUND"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backtest/directional_1dte/tests/test_signals.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement signals**

Create `backtest/directional_1dte/signals.py`:

```python
"""Wall-proximity entry signal for SOLOMON / GIDEON 1DTE backtest.

Mirrors trading/solomon_v2/signals.py:check_wall_proximity exactly.
Returns (Signal, None) on entry, (None, skip_reason_str) on skip.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Signal:
    direction: str   # "BULLISH" or "BEARISH"
    spread_type: str # "BULL_CALL" or "BEAR_PUT"
    reason: str      # human-readable rationale


def generate_signal(walls, spot: float, vix: Optional[float], config):
    """Return (Signal, None) on entry, (None, skip_reason) on skip."""
    if vix is None:
        return None, "NO_VIX_DATA"
    if vix < config.min_vix or vix > config.max_vix:
        return None, "VIX_OUT_OF_RANGE"
    if not walls or walls.get("call_wall") is None or walls.get("put_wall") is None:
        return None, "NO_WALLS_FOUND"

    call_wall = float(walls["call_wall"])
    put_wall = float(walls["put_wall"])
    if spot <= 0:
        return None, "NO_WALLS_FOUND"

    dist_to_put_pct = abs(spot - put_wall) / spot * 100
    dist_to_call_pct = abs(call_wall - spot) / spot * 100

    near_put = dist_to_put_pct <= config.wall_filter_pct
    near_call = dist_to_call_pct <= config.wall_filter_pct

    if near_put and near_call:
        d_put = abs(spot - put_wall)
        d_call = abs(call_wall - spot)
        if d_put <= d_call:  # bullish wins exact ties
            return (
                Signal("BULLISH", "BULL_CALL",
                       f"Tie-break to put wall (${d_put:.2f} vs ${d_call:.2f})"),
                None,
            )
        return (
            Signal("BEARISH", "BEAR_PUT",
                   f"Tie-break to call wall (${d_call:.2f} vs ${d_put:.2f})"),
            None,
        )

    if near_put:
        return Signal("BULLISH", "BULL_CALL", f"Within {dist_to_put_pct:.2f}% of put wall"), None
    if near_call:
        return Signal("BEARISH", "BEAR_PUT", f"Within {dist_to_call_pct:.2f}% of call wall"), None
    return None, "NOT_NEAR_WALL"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backtest/directional_1dte/tests/test_signals.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/directional_1dte/signals.py backtest/directional_1dte/tests/test_signals.py
git commit -m "feat: wall-proximity entry signal mirroring solomon_v2"
```

---

### Task 4: Pricing — strike selection + chain debit lookup (TDD)

**Files:**
- Create: `backtest/directional_1dte/pricing.py`
- Create: `backtest/directional_1dte/tests/test_pricing.py`

- [ ] **Step 1: Write the failing test**

Create `backtest/directional_1dte/tests/test_pricing.py`:

```python
import datetime as dt
import pandas as pd
import pytest
from backtest.directional_1dte.pricing import select_strikes, lookup_debit


class TestSelectStrikes:
    def test_bullish_atm_long_otm_call_short(self):
        long_k, short_k = select_strikes(spot=500.4, direction="BULLISH", width=2)
        assert long_k == 500.0
        assert short_k == 502.0

    def test_bearish_atm_long_otm_put_short(self):
        long_k, short_k = select_strikes(spot=500.4, direction="BEARISH", width=2)
        assert long_k == 500.0
        assert short_k == 498.0

    def test_atm_rounds_half_up(self):
        long_k, _ = select_strikes(spot=500.5, direction="BULLISH", width=2)
        assert long_k in (500.0, 501.0)  # banker's rounding ok either way

    def test_unknown_direction_raises(self):
        with pytest.raises(ValueError):
            select_strikes(500.0, "SIDEWAYS", 2)


@pytest.fixture
def synthetic_chain():
    """Chain indexed (expiration_date, strike) with 4 strikes around 500."""
    exp = dt.date(2024, 3, 15)
    rows = [
        # strike, call_bid, call_ask, call_mid, put_bid, put_ask, put_mid
        (498.0, 3.10, 3.20, 3.15, 0.50, 0.55, 0.52),
        (500.0, 1.80, 1.90, 1.85, 1.20, 1.30, 1.25),
        (502.0, 0.90, 1.00, 0.95, 2.40, 2.50, 2.45),
        (504.0, 0.40, 0.50, 0.45, 4.10, 4.20, 4.15),
    ]
    df = pd.DataFrame(
        [(exp, s, cb, ca, cm, pb, pa, pm) for s, cb, ca, cm, pb, pa, pm in rows],
        columns=["expiration_date", "strike", "call_bid", "call_ask", "call_mid",
                 "put_bid", "put_ask", "put_mid"],
    ).set_index(["expiration_date", "strike"])
    return df, exp


class TestLookupDebit:
    def test_bull_call_debit_is_long_call_mid_minus_short_call_mid(self, synthetic_chain):
        chain, exp = synthetic_chain
        result = lookup_debit(chain, exp, long_strike=500.0, short_strike=502.0,
                              spread_type="BULL_CALL")
        assert result is not None
        assert result["debit"] == pytest.approx(1.85 - 0.95)
        assert result["long_mid"] == 1.85
        assert result["short_mid"] == 0.95

    def test_bear_put_debit_is_long_put_mid_minus_short_put_mid(self, synthetic_chain):
        chain, exp = synthetic_chain
        result = lookup_debit(chain, exp, long_strike=500.0, short_strike=498.0,
                              spread_type="BEAR_PUT")
        assert result is not None
        assert result["debit"] == pytest.approx(1.25 - 0.52)

    def test_returns_none_when_long_strike_missing(self, synthetic_chain):
        chain, exp = synthetic_chain
        assert lookup_debit(chain, exp, 7777.0, 502.0, "BULL_CALL") is None

    def test_returns_none_when_short_strike_missing(self, synthetic_chain):
        chain, exp = synthetic_chain
        assert lookup_debit(chain, exp, 500.0, 9999.0, "BULL_CALL") is None

    def test_returns_none_when_bid_greater_than_ask(self, synthetic_chain):
        chain, exp = synthetic_chain
        # Corrupt one row
        chain.loc[(exp, 500.0), "call_bid"] = 5.0
        chain.loc[(exp, 500.0), "call_ask"] = 1.0
        assert lookup_debit(chain, exp, 500.0, 502.0, "BULL_CALL") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backtest/directional_1dte/tests/test_pricing.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement pricing**

Create `backtest/directional_1dte/pricing.py`:

```python
"""Strike selection and chain debit lookup for vertical debit spreads."""
from typing import Optional


def select_strikes(spot: float, direction: str, width: int) -> tuple[float, float]:
    """ATM long, OTM short. Mirrors solomon_v2/signals.py:calculate_spread_strikes."""
    long_strike = float(round(spot))
    if direction == "BULLISH":
        return long_strike, long_strike + width
    if direction == "BEARISH":
        return long_strike, long_strike - width
    raise ValueError(f"Unknown direction: {direction}")


def lookup_debit(chain, expiration, long_strike, short_strike, spread_type) -> Optional[dict]:
    """Return {debit, long_mid, short_mid, long_bid, long_ask, short_bid, short_ask}
    or None if either strike is missing or bid>ask data corruption."""
    try:
        long_row = chain.loc[(expiration, long_strike)]
        short_row = chain.loc[(expiration, short_strike)]
    except KeyError:
        return None

    if spread_type == "BULL_CALL":
        bid_col, ask_col, mid_col = "call_bid", "call_ask", "call_mid"
    elif spread_type == "BEAR_PUT":
        bid_col, ask_col, mid_col = "put_bid", "put_ask", "put_mid"
    else:
        return None

    long_bid, long_ask, long_mid = long_row[bid_col], long_row[ask_col], long_row[mid_col]
    short_bid, short_ask, short_mid = short_row[bid_col], short_row[ask_col], short_row[mid_col]

    # Reject corrupt rows where bid > ask
    if long_bid is not None and long_ask is not None and float(long_bid) > float(long_ask):
        return None
    if short_bid is not None and short_ask is not None and float(short_bid) > float(short_ask):
        return None
    if long_mid is None or short_mid is None:
        return None

    debit = float(long_mid) - float(short_mid)
    return {
        "debit": debit,
        "long_mid": float(long_mid),
        "short_mid": float(short_mid),
        "long_bid": float(long_bid) if long_bid is not None else None,
        "long_ask": float(long_ask) if long_ask is not None else None,
        "short_bid": float(short_bid) if short_bid is not None else None,
        "short_ask": float(short_ask) if short_ask is not None else None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backtest/directional_1dte/tests/test_pricing.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/directional_1dte/pricing.py backtest/directional_1dte/tests/test_pricing.py
git commit -m "feat: strike selection + ORAT chain debit lookup"
```

---

### Task 5: Data layer — ORAT loaders + integration test

**Files:**
- Create: `backtest/directional_1dte/data.py`
- Create: `backtest/directional_1dte/tests/test_data_integration.py`
- Modify: `pytest.ini` to register `integration` marker (only if not already registered)

- [ ] **Step 1: Verify pytest.ini integration marker registration**

Run: `grep -E 'markers|integration' pytest.ini`
Expected: confirm whether `integration` marker exists. If absent, add to `[pytest]` section in `pytest.ini`:

```ini
markers =
    integration: hits real ORAT postgres, requires ORAT_DATABASE_URL
```

- [ ] **Step 2: Write the failing integration test**

Create `backtest/directional_1dte/tests/test_data_integration.py`:

```python
"""Integration tests against real ORAT postgres. Marked @integration; skipped without DB env."""
import datetime as dt
import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("ORAT_DATABASE_URL"),
        reason="ORAT_DATABASE_URL not set",
    ),
]


def test_load_trading_days_returns_expected_count_for_known_week():
    from backtest.directional_1dte.data import load_trading_days
    # Week of 2024-03-11 (M-F, no holidays) — exactly 5 trading days
    days = load_trading_days(dt.date(2024, 3, 11), dt.date(2024, 3, 15))
    assert len(days) == 5
    assert days[0] == dt.date(2024, 3, 11)
    assert days[-1] == dt.date(2024, 3, 15)


def test_load_chain_returns_indexed_dataframe_with_required_columns():
    from backtest.directional_1dte.data import load_chain
    chain = load_chain(dt.date(2024, 3, 15))
    assert len(chain) > 100  # SPY March 2024 has thousands of strikes
    required = {"call_bid", "call_ask", "call_mid", "put_bid", "put_ask", "put_mid",
                "underlying_price", "dte"}
    assert required.issubset(set(chain.columns))
    assert chain.index.names == ["expiration_date", "strike"]


def test_load_vix_returns_float_for_known_date():
    from backtest.directional_1dte.data import load_vix
    vix = load_vix(dt.date(2024, 3, 15))
    assert vix is not None
    assert 5.0 < vix < 100.0


def test_load_vix_returns_none_for_weekend():
    from backtest.directional_1dte.data import load_vix
    assert load_vix(dt.date(2024, 3, 16)) is None


def test_load_gex_walls_returns_walls_for_known_date():
    from backtest.directional_1dte.data import load_gex_walls
    walls = load_gex_walls(dt.date(2024, 3, 15))
    assert walls is not None
    assert "call_wall" in walls and walls["call_wall"] > 0
    assert "put_wall" in walls and walls["put_wall"] > 0
    assert "spot" in walls and walls["spot"] > 0
    assert walls["put_wall"] < walls["spot"] < walls["call_wall"] + 5  # rough sanity
```

- [ ] **Step 3: Run integration test to verify it fails**

Run: `ORAT_DATABASE_URL=$ORAT_DATABASE_URL pytest backtest/directional_1dte/tests/test_data_integration.py -v -m integration`
Expected: FAIL with ImportError

(On Windows PowerShell: `$env:ORAT_DATABASE_URL=...; pytest ...`)

- [ ] **Step 4: Implement data layer**

Create `backtest/directional_1dte/data.py`:

```python
"""ORAT postgres loaders. Read-only. Connection per call (no pool).

All functions return None for missing data rather than raising — the engine
records the absence as a categorized skip, never silently drops the day.
"""
import datetime as dt
import os
from typing import Optional

import pandas as pd
import psycopg2


def _conn():
    url = os.environ.get("ORAT_DATABASE_URL")
    if not url:
        raise RuntimeError("ORAT_DATABASE_URL not set")
    return psycopg2.connect(url)


def load_trading_days(start: dt.date, end: dt.date, ticker: str = "SPY") -> list[dt.date]:
    """Distinct trade_date for ticker between [start, end] inclusive."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT trade_date
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date
            """,
            (ticker, start, end),
        )
        return [r[0] for r in cur.fetchall()]


def load_chain(trade_date: dt.date, ticker: str = "SPY") -> pd.DataFrame:
    """All option rows for ticker on trade_date, indexed by (expiration_date, strike)."""
    with _conn() as c:
        df = pd.read_sql(
            """
            SELECT trade_date, expiration_date, strike,
                   call_bid, call_ask, call_mid,
                   put_bid, put_ask, put_mid,
                   underlying_price, dte
            FROM orat_options_eod
            WHERE ticker = %s AND trade_date = %s
            """,
            c,
            params=(ticker, trade_date),
        )
    if df.empty:
        return df.set_index(["expiration_date", "strike"]) if "expiration_date" in df else df
    return df.set_index(["expiration_date", "strike"])


def load_vix(trade_date: dt.date) -> Optional[float]:
    """VIX close for trade_date or None."""
    with _conn() as c, c.cursor() as cur:
        cur.execute("SELECT close FROM vix_history WHERE trade_date = %s", (trade_date,))
        row = cur.fetchone()
    return float(row[0]) if row else None


def load_gex_walls(trade_date: dt.date, ticker: str = "SPY") -> Optional[dict]:
    """Read precomputed call_wall, put_wall, spot_close from gex_structure_daily."""
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            SELECT call_wall, put_wall, spot_close
            FROM gex_structure_daily
            WHERE symbol = %s AND trade_date = %s
            """,
            (ticker, trade_date),
        )
        row = cur.fetchone()
    if not row or row[0] is None or row[1] is None or row[2] is None:
        return None
    return {
        "call_wall": float(row[0]),
        "put_wall": float(row[1]),
        "spot": float(row[2]),
    }
```

- [ ] **Step 5: Run integration test to verify it passes**

Run (Windows PowerShell):
```powershell
$env:ORAT_DATABASE_URL = "<paste from .env or vault>"
pytest backtest/directional_1dte/tests/test_data_integration.py -v -m integration
```
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add backtest/directional_1dte/data.py backtest/directional_1dte/tests/test_data_integration.py pytest.ini
git commit -m "feat: ORAT data loaders for chains/VIX/walls + integration tests"
```

---

### Task 6: Engine — daily loop driver (TDD with synthetic data)

**Files:**
- Create: `backtest/directional_1dte/engine.py`
- Create: `backtest/directional_1dte/tests/test_engine.py`

- [ ] **Step 1: Write the failing test**

Create `backtest/directional_1dte/tests/test_engine.py`:

```python
"""Engine tests use synthetic data injected via dependency injection.
No DB hits. Fast, deterministic."""
import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd
import pytest

from backtest.directional_1dte.engine import Trade, BacktestResult, run_with_loaders
from backtest.directional_1dte.config import SOLOMON


@dataclass
class StubLoaders:
    """Inject synthetic data into the engine via this stub."""
    trading_days: list
    chains: dict   # date -> DataFrame indexed (expiration, strike)
    vix: dict      # date -> float | None
    walls: dict    # date -> {call_wall, put_wall, spot} | None

    def load_trading_days(self, start, end, ticker="SPY"):
        return [d for d in self.trading_days if start <= d <= end]

    def load_chain(self, d, ticker="SPY"):
        return self.chains.get(d, pd.DataFrame())

    def load_vix(self, d):
        return self.vix.get(d)

    def load_gex_walls(self, d, ticker="SPY"):
        return self.walls.get(d)


def make_chain(expiration: dt.date, spot: float, strikes_with_prices):
    """strikes_with_prices: list of (strike, call_mid, put_mid). Bid/ask = mid ± 0.05."""
    rows = []
    for s, c_mid, p_mid in strikes_with_prices:
        rows.append({
            "expiration_date": expiration, "strike": s,
            "call_bid": c_mid - 0.05, "call_ask": c_mid + 0.05, "call_mid": c_mid,
            "put_bid": p_mid - 0.05, "put_ask": p_mid + 0.05, "put_mid": p_mid,
            "underlying_price": spot, "dte": (expiration - dt.date.today()).days,
        })
    return pd.DataFrame(rows).set_index(["expiration_date", "strike"])


class TestSingleTradeDay:
    def test_bullish_signal_produces_trade_and_settles_above_short(self, solomon):
        d0 = dt.date(2024, 3, 11)  # Monday
        d1 = dt.date(2024, 3, 12)
        # Day 0: spot 500, put_wall 499 (within 1%), VIX 18 -> BULLISH bull-call
        # Strikes 500/502, debit 0.80
        loaders = StubLoaders(
            trading_days=[d0, d1],
            chains={
                d0: make_chain(d1, 500.0, [(498, 3.0, 0.5), (500, 1.5, 1.5),
                                            (502, 0.7, 2.7), (504, 0.3, 4.5)]),
                # Day 1 chain only needs underlying_price for settlement
                d1: pd.DataFrame([{"expiration_date": d1, "strike": 500.0,
                                   "call_bid": 0, "call_ask": 0, "call_mid": 0,
                                   "put_bid": 0, "put_ask": 0, "put_mid": 0,
                                   "underlying_price": 503.0, "dte": 0}]
                                 ).set_index(["expiration_date", "strike"]),
            },
            vix={d0: 18.0, d1: 18.5},
            walls={d0: {"call_wall": 540, "put_wall": 499, "spot": 500},
                   d1: {"call_wall": 540, "put_wall": 502, "spot": 503}},
        )
        result = run_with_loaders(solomon, dt.date(2024, 3, 11), dt.date(2024, 3, 12), loaders)
        assert len(result.trades) == 1
        t = result.trades[0]
        assert t.direction == "BULLISH"
        assert t.long_strike == 500.0
        assert t.short_strike == 502.0
        assert t.entry_debit == pytest.approx(0.80)  # 1.5 - 0.7
        # contracts = floor(1000 / 80) = 12
        assert t.contracts == 12
        # spot 503 settled, payoff = min(503, 502) - 500 = 2.0; pnl = (2.0 - 0.80) * 12 * 100 = 1440
        assert t.realized_pnl == pytest.approx(1440.0)


class TestSkipDays:
    def test_skip_recorded_when_vix_out_of_range(self, solomon):
        d0 = dt.date(2024, 3, 11); d1 = dt.date(2024, 3, 12)
        loaders = StubLoaders(
            trading_days=[d0, d1],
            chains={d0: pd.DataFrame(), d1: pd.DataFrame()},
            vix={d0: 50.0, d1: 50.0},  # above max
            walls={d0: {"call_wall": 540, "put_wall": 499, "spot": 500}},
        )
        result = run_with_loaders(solomon, d0, d1, loaders)
        assert len(result.trades) == 0
        assert len(result.skips) == 1
        assert result.skips[0].reason == "VIX_OUT_OF_RANGE"

    def test_long_weekend_gap_recorded(self, solomon):
        # 5-day gap between trading days
        d0 = dt.date(2024, 3, 11); d1 = dt.date(2024, 3, 18)
        loaders = StubLoaders(
            trading_days=[d0, d1],
            chains={d0: make_chain(d1, 500.0, [(500, 1.5, 1.5), (502, 0.7, 2.7)])},
            vix={d0: 18.0},
            walls={d0: {"call_wall": 540, "put_wall": 499, "spot": 500}},
        )
        result = run_with_loaders(solomon, d0, d1, loaders)
        assert len(result.trades) == 0
        assert any(s.reason == "NO_NEAR_EXPIRATION" for s in result.skips)


class TestNoSilentDrops:
    def test_every_day_produces_trade_or_skip(self, solomon):
        days = [dt.date(2024, 3, 11), dt.date(2024, 3, 12), dt.date(2024, 3, 13)]
        loaders = StubLoaders(
            trading_days=days,
            chains={d: pd.DataFrame() for d in days},
            vix={d: 50.0 for d in days},  # all skipped on VIX
            walls={d: {"call_wall": 540, "put_wall": 499, "spot": 500} for d in days},
        )
        result = run_with_loaders(solomon, days[0], days[-1], loaders)
        # Last day has no T+1 so it's not processed; first two should produce skips
        assert len(result.trades) + len(result.skips) == len(days) - 1


class TestEquityCurve:
    def test_equity_starts_at_starting_capital(self, solomon):
        loaders = StubLoaders(trading_days=[], chains={}, vix={}, walls={})
        result = run_with_loaders(solomon, dt.date(2024, 1, 1), dt.date(2024, 1, 1), loaders)
        assert result.starting_capital == solomon.starting_capital
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backtest/directional_1dte/tests/test_engine.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement engine**

Create `backtest/directional_1dte/engine.py`:

```python
"""Daily loop driver. Pure orchestration over signals/pricing/payoff/data."""
import datetime as dt
import logging
import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from backtest.directional_1dte import data as default_data
from backtest.directional_1dte.config import BotConfig
from backtest.directional_1dte.signals import generate_signal
from backtest.directional_1dte.pricing import select_strikes, lookup_debit
from backtest.directional_1dte.payoff import compute_payoff


logger = logging.getLogger(__name__)


@dataclass
class Trade:
    bot: str
    entry_date: dt.date
    expiration_date: dt.date
    direction: str
    spread_type: str
    spot_at_entry: float
    long_strike: float
    short_strike: float
    entry_debit: float
    contracts: int
    spot_at_expiry: float
    payoff_per_share: float
    realized_pnl: float
    vix_at_entry: float
    call_wall: float
    put_wall: float
    long_bid: Optional[float]
    long_ask: Optional[float]
    short_bid: Optional[float]
    short_ask: Optional[float]
    expiry_not_t_plus_1: bool


@dataclass
class Skip:
    bot: str
    entry_date: dt.date
    reason: str
    detail: str = ""


@dataclass
class EquityPoint:
    date: dt.date
    equity: float


@dataclass
class BacktestResult:
    bot: str
    config: BotConfig
    start: dt.date
    end: dt.date
    starting_capital: float
    trades: list = field(default_factory=list)
    skips: list = field(default_factory=list)
    equity: list = field(default_factory=list)


def _pick_expiration(chain, trade_date: dt.date) -> Optional[dt.date]:
    """Return the soonest expiration > trade_date in the chain, or None.
    Skips if gap > 4 calendar days (handles pre-2022 SPY MWF cycle)."""
    if chain.empty:
        return None
    expirations = sorted({d for d, _ in chain.index if d > trade_date})
    if not expirations:
        return None
    chosen = expirations[0]
    if (chosen - trade_date).days > 4:
        return None
    return chosen


def run_with_loaders(config: BotConfig, start: dt.date, end: dt.date, loaders) -> BacktestResult:
    """Engine with injectable loaders (for testing). Mirrors run() exactly."""
    result = BacktestResult(
        bot=config.name,
        config=config,
        start=start,
        end=end,
        starting_capital=config.starting_capital,
    )
    equity = config.starting_capital
    trading_days = loaders.load_trading_days(start, end, ticker=config.ticker)
    if not trading_days:
        return result

    for i, t_day in enumerate(trading_days[:-1]):
        # Load entry-day data
        chain_t = loaders.load_chain(t_day, ticker=config.ticker)
        vix_t = loaders.load_vix(t_day)
        walls_t = loaders.load_gex_walls(t_day, ticker=config.ticker)
        spot_t = walls_t["spot"] if walls_t else None

        if spot_t is None or chain_t.empty:
            result.skips.append(Skip(config.name, t_day, "NO_DATA",
                                     "missing chain or walls"))
            continue

        # Generate signal
        signal, reason = generate_signal(walls_t, spot_t, vix_t, config)
        if signal is None:
            result.skips.append(Skip(config.name, t_day, reason or "UNKNOWN_SKIP"))
            continue

        # Pick expiration
        expiration = _pick_expiration(chain_t, t_day)
        if expiration is None:
            result.skips.append(Skip(config.name, t_day, "NO_NEAR_EXPIRATION",
                                     f"no expiration within 4 days of {t_day}"))
            continue
        expiry_not_t_plus_1 = (expiration != trading_days[i + 1])

        # Select strikes & look up debit
        long_k, short_k = select_strikes(spot_t, signal.direction, config.spread_width)
        priced = lookup_debit(chain_t, expiration, long_k, short_k, signal.spread_type)
        if priced is None:
            result.skips.append(Skip(config.name, t_day, "STRIKES_MISSING_FROM_CHAIN",
                                     f"{long_k}/{short_k} on {expiration}"))
            continue
        debit = priced["debit"]
        if debit <= 0 or debit >= config.spread_width:
            result.skips.append(Skip(config.name, t_day, "DEBIT_INVALID",
                                     f"debit={debit:.3f} width={config.spread_width}"))
            continue
        contracts = int(math.floor(config.risk_per_trade / (debit * 100)))
        if contracts < 1:
            result.skips.append(Skip(config.name, t_day, "SIZE_BELOW_1_CONTRACT",
                                     f"debit={debit:.3f}"))
            continue

        # Settle on the expiration day's chain
        chain_exp = loaders.load_chain(expiration, ticker=config.ticker)
        if chain_exp.empty:
            result.skips.append(Skip(config.name, t_day, "NO_T+1_DATA",
                                     f"no chain for {expiration}"))
            continue
        underlying_series = chain_exp["underlying_price"].dropna()
        if underlying_series.empty:
            result.skips.append(Skip(config.name, t_day, "NO_T+1_DATA",
                                     "no underlying price on expiry"))
            continue
        spot_expiry = float(underlying_series.median())
        if abs(underlying_series.max() - underlying_series.min()) / spot_expiry > 0.005:
            logger.warning("Underlying spread > 0.5%% on %s: min=%.2f max=%.2f",
                           expiration, underlying_series.min(), underlying_series.max())

        payoff = compute_payoff(signal.spread_type, long_k, short_k, spot_expiry)
        pnl = (payoff - debit) * 100 * contracts
        equity += pnl

        result.trades.append(Trade(
            bot=config.name,
            entry_date=t_day,
            expiration_date=expiration,
            direction=signal.direction,
            spread_type=signal.spread_type,
            spot_at_entry=spot_t,
            long_strike=long_k,
            short_strike=short_k,
            entry_debit=debit,
            contracts=contracts,
            spot_at_expiry=spot_expiry,
            payoff_per_share=payoff,
            realized_pnl=pnl,
            vix_at_entry=vix_t,
            call_wall=walls_t["call_wall"],
            put_wall=walls_t["put_wall"],
            long_bid=priced.get("long_bid"),
            long_ask=priced.get("long_ask"),
            short_bid=priced.get("short_bid"),
            short_ask=priced.get("short_ask"),
            expiry_not_t_plus_1=expiry_not_t_plus_1,
        ))
        result.equity.append(EquityPoint(t_day, equity))

    return result


def run(config: BotConfig, start: dt.date, end: dt.date) -> BacktestResult:
    """Production entry: uses default data loaders against ORAT."""
    return run_with_loaders(config, start, end, default_data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backtest/directional_1dte/tests/test_engine.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/directional_1dte/engine.py backtest/directional_1dte/tests/test_engine.py
git commit -m "feat: backtest engine daily loop with injectable loaders"
```

---

### Task 7: Report — CSV/JSON writers (TDD)

**Files:**
- Create: `backtest/directional_1dte/report.py`
- Create: `backtest/directional_1dte/tests/test_report.py`

- [ ] **Step 1: Write the failing test**

Create `backtest/directional_1dte/tests/test_report.py`:

```python
import datetime as dt
import json
import math
from pathlib import Path

import pytest
from backtest.directional_1dte.config import SOLOMON
from backtest.directional_1dte.engine import BacktestResult, Trade, Skip, EquityPoint
from backtest.directional_1dte.report import write_results, summary_stats


def _trade(date, pnl, direction="BULLISH", debit=0.80, vix=18.0):
    return Trade(
        bot="solomon", entry_date=date, expiration_date=date,
        direction=direction, spread_type="BULL_CALL" if direction == "BULLISH" else "BEAR_PUT",
        spot_at_entry=500.0, long_strike=500.0, short_strike=502.0,
        entry_debit=debit, contracts=12, spot_at_expiry=503.0,
        payoff_per_share=2.0, realized_pnl=pnl, vix_at_entry=vix,
        call_wall=540.0, put_wall=499.0,
        long_bid=None, long_ask=None, short_bid=None, short_ask=None,
        expiry_not_t_plus_1=False,
    )


@pytest.fixture
def result(tmp_path):
    r = BacktestResult(bot="solomon", config=SOLOMON,
                       start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 5),
                       starting_capital=100000.0)
    r.trades = [
        _trade(dt.date(2024, 1, 2), 100.0),
        _trade(dt.date(2024, 1, 3), -200.0, direction="BEARISH"),
        _trade(dt.date(2024, 1, 4), 50.0, vix=25.0),
    ]
    r.skips = [Skip("solomon", dt.date(2024, 1, 5), "NOT_NEAR_WALL")]
    r.equity = [EquityPoint(dt.date(2024, 1, 2), 100100.0),
                EquityPoint(dt.date(2024, 1, 3), 99900.0),
                EquityPoint(dt.date(2024, 1, 4), 99950.0)]
    return r


def test_summary_stats_basic(result):
    s = summary_stats(result)
    assert s["total_trades"] == 3
    assert s["total_skips"] == 1
    assert s["total_pnl"] == pytest.approx(-50.0)
    assert s["win_rate"] == pytest.approx(2/3)
    assert s["avg_win"] == pytest.approx(75.0)
    assert s["avg_loss"] == pytest.approx(-200.0)


def test_write_results_creates_all_files(result, tmp_path):
    out = tmp_path / "solomon"
    write_results(result, out)
    assert (out / "summary.json").exists()
    assert (out / "trades.csv").exists()
    assert (out / "skips.csv").exists()
    assert (out / "equity_curve.csv").exists()
    assert (out / "by_year.csv").exists()
    assert (out / "by_vix_bucket.csv").exists()
    assert (out / "by_direction.csv").exists()
    assert (out / "top_trades.csv").exists()
    assert (out / "worst_trades.csv").exists()
    assert (out / "run.json").exists()


def test_summary_json_is_valid(result, tmp_path):
    out = tmp_path / "solomon"
    write_results(result, out)
    payload = json.loads((out / "summary.json").read_text())
    assert payload["bot"] == "solomon"
    assert payload["total_trades"] == 3
    assert payload["total_pnl"] == pytest.approx(-50.0)


def test_by_vix_bucket_partitions_trades(result, tmp_path):
    import csv
    out = tmp_path / "solomon"
    write_results(result, out)
    rows = list(csv.DictReader((out / "by_vix_bucket.csv").open()))
    bucket_counts = {r["bucket"]: int(r["trades"]) for r in rows}
    # vix 18, 18, 25 -> normal=2, elevated=1
    assert bucket_counts.get("normal_15_22", 0) == 2
    assert bucket_counts.get("elevated_22_28", 0) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backtest/directional_1dte/tests/test_report.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement report**

Create `backtest/directional_1dte/report.py`:

```python
"""Scorecard CSV/JSON writers for BacktestResult."""
import csv
import dataclasses
import json
import math
from datetime import date, datetime
from pathlib import Path
from statistics import mean, pstdev

from backtest.directional_1dte.engine import BacktestResult


VIX_BUCKETS = [
    ("low_lt_15", lambda v: v < 15),
    ("normal_15_22", lambda v: 15 <= v < 22),
    ("elevated_22_28", lambda v: 22 <= v < 28),
    ("high_gte_28", lambda v: v >= 28),
]


def _ann_sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    mu = mean(daily_returns)
    sd = pstdev(daily_returns)
    if sd == 0:
        return 0.0
    return (mu / sd) * math.sqrt(252)


def _max_drawdown(equity_series: list[float]) -> float:
    if not equity_series:
        return 0.0
    peak = equity_series[0]
    max_dd = 0.0
    for v in equity_series:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return max_dd


def summary_stats(result: BacktestResult) -> dict:
    trades = result.trades
    n = len(trades)
    pnls = [t.realized_pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    equity_vals = [result.starting_capital] + [ep.equity for ep in result.equity]
    daily_pnl = [pnls[i] for i in range(n)]  # one return per trade (proxy)
    daily_pct = [p / result.starting_capital for p in daily_pnl]

    return {
        "bot": result.bot,
        "start": str(result.start),
        "end": str(result.end),
        "starting_capital": result.starting_capital,
        "ending_equity": equity_vals[-1] if equity_vals else result.starting_capital,
        "total_trades": n,
        "total_skips": len(result.skips),
        "total_pnl": sum(pnls),
        "win_rate": (len(wins) / n) if n else 0.0,
        "avg_win": (mean(wins) if wins else 0.0),
        "avg_loss": (mean(losses) if losses else 0.0),
        "expectancy": (mean(pnls) if pnls else 0.0),
        "profit_factor": (sum(wins) / abs(sum(losses))) if losses else float("inf") if wins else 0.0,
        "annualized_sharpe": _ann_sharpe(daily_pct),
        "max_drawdown_pct": _max_drawdown(equity_vals),
    }


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _trade_to_row(t):
    d = dataclasses.asdict(t)
    d["entry_date"] = str(d["entry_date"])
    d["expiration_date"] = str(d["expiration_date"])
    return d


def write_results(result: BacktestResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    s = summary_stats(result)

    # 1. summary.json
    (out_dir / "summary.json").write_text(json.dumps(s, indent=2, default=str))

    # 2. trades.csv
    if result.trades:
        rows = [_trade_to_row(t) for t in result.trades]
        _write_csv(out_dir / "trades.csv", rows, list(rows[0].keys()))
    else:
        (out_dir / "trades.csv").write_text("")

    # 3. skips.csv
    skip_rows = [{"entry_date": str(s.entry_date), "reason": s.reason, "detail": s.detail}
                 for s in result.skips]
    _write_csv(out_dir / "skips.csv", skip_rows, ["entry_date", "reason", "detail"])

    # 4. equity_curve.csv
    eq_rows = [{"date": str(p.date), "equity": p.equity} for p in result.equity]
    _write_csv(out_dir / "equity_curve.csv", eq_rows, ["date", "equity"])

    # 5. by_year.csv
    by_year = {}
    for t in result.trades:
        y = t.entry_date.year
        by_year.setdefault(y, []).append(t)
    yr_rows = [{
        "year": y,
        "trades": len(ts),
        "pnl": sum(t.realized_pnl for t in ts),
        "win_rate": sum(1 for t in ts if t.realized_pnl > 0) / len(ts),
    } for y, ts in sorted(by_year.items())]
    _write_csv(out_dir / "by_year.csv", yr_rows, ["year", "trades", "pnl", "win_rate"])

    # 6. by_vix_bucket.csv
    buckets = {name: [] for name, _ in VIX_BUCKETS}
    for t in result.trades:
        for name, pred in VIX_BUCKETS:
            if pred(t.vix_at_entry):
                buckets[name].append(t)
                break
    vb_rows = [{
        "bucket": name,
        "trades": len(ts),
        "pnl": sum(t.realized_pnl for t in ts),
        "win_rate": (sum(1 for t in ts if t.realized_pnl > 0) / len(ts)) if ts else 0,
    } for name, ts in buckets.items()]
    _write_csv(out_dir / "by_vix_bucket.csv", vb_rows, ["bucket", "trades", "pnl", "win_rate"])

    # 7. by_direction.csv
    dirs = {"BULLISH": [], "BEARISH": []}
    for t in result.trades:
        dirs[t.direction].append(t)
    dir_rows = [{
        "direction": k,
        "trades": len(v),
        "pnl": sum(t.realized_pnl for t in v),
        "win_rate": (sum(1 for t in v if t.realized_pnl > 0) / len(v)) if v else 0,
    } for k, v in dirs.items()]
    _write_csv(out_dir / "by_direction.csv", dir_rows, ["direction", "trades", "pnl", "win_rate"])

    # 8. top_trades.csv & worst_trades.csv
    top = sorted(result.trades, key=lambda t: t.realized_pnl, reverse=True)[:10]
    worst = sorted(result.trades, key=lambda t: t.realized_pnl)[:10]
    if top:
        _write_csv(out_dir / "top_trades.csv", [_trade_to_row(t) for t in top],
                   list(_trade_to_row(top[0]).keys()))
    if worst:
        _write_csv(out_dir / "worst_trades.csv", [_trade_to_row(t) for t in worst],
                   list(_trade_to_row(worst[0]).keys()))

    # 9. run.json (reproducibility metadata)
    skip_counts = {}
    for s in result.skips:
        skip_counts[s.reason] = skip_counts.get(s.reason, 0) + 1
    (out_dir / "run.json").write_text(json.dumps({
        "bot": result.bot,
        "config": dataclasses.asdict(result.config),
        "window": [str(result.start), str(result.end)],
        "trades": len(result.trades),
        "skips_by_reason": skip_counts,
        "ending_equity": s["ending_equity"] if isinstance(s, dict) and "ending_equity" in s else summary_stats(result)["ending_equity"],
        "written_at": datetime.utcnow().isoformat() + "Z",
    }, indent=2, default=str))


def write_comparison(results: dict, out_dir: Path) -> None:
    """Write top-level comparison.json + comparison.md across multiple bots."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries = {name: summary_stats(r) for name, r in results.items()}
    (out_dir / "comparison.json").write_text(json.dumps(summaries, indent=2, default=str))

    lines = ["# SOLOMON / GIDEON 1DTE Backtest Comparison\n"]
    fields = ["total_trades", "total_pnl", "win_rate", "avg_win", "avg_loss",
              "expectancy", "profit_factor", "annualized_sharpe", "max_drawdown_pct"]
    lines.append("| Metric | " + " | ".join(summaries.keys()) + " |")
    lines.append("|" + "---|" * (len(summaries) + 1))
    for f in fields:
        row = [f]
        for name in summaries:
            val = summaries[name].get(f, 0)
            if isinstance(val, float):
                row.append(f"{val:.4f}" if abs(val) < 100 else f"{val:.2f}")
            else:
                row.append(str(val))
        lines.append("| " + " | ".join(row) + " |")
    (out_dir / "comparison.md").write_text("\n".join(lines))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backtest/directional_1dte/tests/test_report.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backtest/directional_1dte/report.py backtest/directional_1dte/tests/test_report.py
git commit -m "feat: scorecard report writers (CSV + JSON + comparison)"
```

---

### Task 8: CLI entry + smoke run

**Files:**
- Create: `backtest/directional_1dte/__main__.py`

- [ ] **Step 1: Implement the CLI**

Create `backtest/directional_1dte/__main__.py`:

```python
"""CLI: python -m backtest.directional_1dte --bot {solomon,gideon,both} --start ... --end ..."""
import argparse
import datetime as dt
import logging
import os
import sys
from pathlib import Path

from backtest.directional_1dte.config import BOT_CONFIGS
from backtest.directional_1dte.engine import run
from backtest.directional_1dte.report import write_results, write_comparison


def parse_args():
    p = argparse.ArgumentParser(description="SOLOMON/GIDEON 1DTE directional backtest")
    p.add_argument("--bot", choices=["solomon", "gideon", "both"], default="both")
    p.add_argument("--start", default="2020-01-02", help="YYYY-MM-DD")
    p.add_argument("--end", default="2025-12-05", help="YYYY-MM-DD")
    p.add_argument("--output-dir", default=None,
                   help="Output dir; default backtest/results/<today>-solomon-gideon-1dte/")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not os.environ.get("ORAT_DATABASE_URL"):
        sys.exit("ORAT_DATABASE_URL not set in environment")

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    out_root = Path(args.output_dir or
                    f"backtest/results/{dt.date.today().isoformat()}-solomon-gideon-1dte")
    out_root.mkdir(parents=True, exist_ok=True)

    bot_names = ["solomon", "gideon"] if args.bot == "both" else [args.bot]
    results = {}
    for name in bot_names:
        cfg = BOT_CONFIGS[name]
        print(f"[{name}] running {start} -> {end} ...", flush=True)
        res = run(cfg, start, end)
        write_results(res, out_root / name)
        results[name] = res
        print(f"[{name}] {len(res.trades)} trades, {len(res.skips)} skips, "
              f"P&L ${sum(t.realized_pnl for t in res.trades):,.2f}", flush=True)

    if len(results) > 1:
        write_comparison(results, out_root)
        print(f"Comparison written to {out_root}/comparison.md", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-run on a one-month window to verify end-to-end**

Run (Windows PowerShell):
```powershell
$env:ORAT_DATABASE_URL = "<from .env or vault>"
python -m backtest.directional_1dte --bot both --start 2024-03-01 --end 2024-03-31 --verbose
```
Expected: completes in <10 seconds; writes `backtest/results/<today>-solomon-gideon-1dte/{solomon,gideon}/` with all CSV/JSON files; prints per-bot trade/skip counts and final P&L; writes comparison.md.

- [ ] **Step 3: Inspect smoke-run output**

```bash
cat backtest/results/*-solomon-gideon-1dte/comparison.md
head backtest/results/*-solomon-gideon-1dte/solomon/trades.csv
```
Verify: every column populated; no NaN; trade count + skip count == ~21 (March 2024 trading days).

- [ ] **Step 4: Commit**

```bash
git add backtest/directional_1dte/__main__.py
git commit -m "feat: 1dte backtest CLI entry"
```

---

### Task 9: Full backtest run + sanity checks + results commit

**Files:**
- Create: `backtest/results/<today>-solomon-gideon-1dte/` (output, committed for reproducibility)
- Create: `backtest/results/<today>-solomon-gideon-1dte/RESULTS.md` (human-readable summary)

- [ ] **Step 1: Run the full 6-year backtest**

Run (Windows PowerShell):
```powershell
$env:ORAT_DATABASE_URL = "<from .env or vault>"
python -m backtest.directional_1dte --bot both --start 2020-01-02 --end 2025-12-05 --verbose 2>&1 | tee backtest/results/$(Get-Date -Format yyyy-MM-dd)-solomon-gideon-1dte/run.log
```
Expected: completes in <2 min. Per-bot summary lines printed. ~1,239 trading days processed.

- [ ] **Step 2: Verify sanity checks asserted in spec**

Run this verification script inline:

```python
python -c "
import json, csv, glob
from pathlib import Path
out = Path(sorted(glob.glob('backtest/results/*-solomon-gideon-1dte'))[-1])
for bot in ['solomon', 'gideon']:
    s = json.loads((out / bot / 'summary.json').read_text())
    trades = list(csv.DictReader((out / bot / 'trades.csv').open()))
    skips = list(csv.DictReader((out / bot / 'skips.csv').open()))
    pnl = sum(float(t['realized_pnl']) for t in trades) if trades else 0
    print(f'[{bot}] trades={len(trades)} skips={len(skips)} reported_pnl={s[\"total_pnl\"]:.2f} ledger_pnl={pnl:.2f}')
    assert abs(s['total_pnl'] - pnl) < 0.01, f'{bot}: ledger pnl mismatch'
    if trades:
        risk = float(open(out/bot/'../comparison.json').read() if (out/'comparison.json').exists() else '{}') or 1000
        max_loss = min(float(t['realized_pnl']) for t in trades)
        # Loss should be bounded by risk_per_trade * 1.05 = 1050 (allow rounding)
        assert max_loss >= -1050, f'{bot}: max single-loss {max_loss} exceeds risk * 1.05'
    print(f'[{bot}] all sanity checks pass')
"
```
Expected output: `[solomon] all sanity checks pass`, `[gideon] all sanity checks pass`.

- [ ] **Step 3: Write RESULTS.md summarizing what we found**

Create `backtest/results/<today>-solomon-gideon-1dte/RESULTS.md` with the headline stats from `comparison.md` plus a verdict section. Template:

```markdown
# SOLOMON / GIDEON 1DTE Backtest — Results

**Run date:** YYYY-MM-DD
**Window:** 2020-01-02 → 2025-12-05 (~1,239 trading days)
**Strategy:** GEX-walls entry (no PROPHET, no ML), 1DTE SPY debit spreads, hold to expiration, $1,000 risk per trade.

## Headline (from comparison.md)

[paste table]

## Year-by-year (SOLOMON)

[paste content of solomon/by_year.csv as a markdown table]

## Year-by-year (GIDEON)

[paste content of gideon/by_year.csv as a markdown table]

## VIX-bucket breakdown

[paste both bots' by_vix_bucket.csv side by side]

## Direction breakdown

[paste both bots' by_direction.csv side by side]

## Skip reasons (SOLOMON)

[summarize skips.csv by reason — most common at top]

## Skip reasons (GIDEON)

[same]

## Verdict

[1-2 paragraphs answering: does the GEX-walls signal have edge on 1DTE? If yes, by how much? If no, what's the dominant failure mode? Is there a VIX or year regime where it works?]
```

- [ ] **Step 4: Commit results**

```bash
git add backtest/results/
git commit -m "results: SOLOMON/GIDEON 1DTE backtest 2020-2025"
```

- [ ] **Step 5: Run all tests to verify nothing broke**

```bash
pytest backtest/directional_1dte/tests/ -v -m "not integration"
```
Expected: all unit tests still pass.

---

## Self-review

After all tasks complete, verify:

1. Spec section "Bot configurations" → covered in Task 1.
2. Spec section "Entry signal" → covered in Task 3.
3. Spec section "Strike selection" + "Entry pricing" → Tasks 4 + 6.
4. Spec section "Exit (settlement)" → Tasks 2 + 6.
5. Spec section "Edge cases" → all categories represented in Task 6 engine + Task 5 data.
6. Spec section "Output" → Tasks 7 + 8 produce all listed files.
7. Spec section "Testing strategy" → Tasks 2-7 unit tests, Task 5 integration tests.
8. Spec section "Reproducibility metadata" → Task 7 `run.json`.
9. Spec section "Determinism" → enforced by pure functions; not separately tested but follows from absence of RNG/wall-clock.

If any gap, add the task before handing off.
