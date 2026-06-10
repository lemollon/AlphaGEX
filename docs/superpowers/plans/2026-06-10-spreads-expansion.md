# SpreadWorks Spreads Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn SpreadWorks' single-leg dip-buyer into a vertical-spread suite — UNDERTOW v2 (directional **debit** verticals: bull call / bear put spreads), a new **DELTA** bot (directional **credit** spreads: put-credit / call-credit), plus a cheap fail-safe Opus-4.8 entry rationale on both.

**Architecture:** A shared `setups.py` detects the bullish "dip" / bearish "rip" setup (reusing UNDERTOW's `dip_buy` indicators). A shared `vertical_spread.py` builds any of the 4 two-leg verticals, reusing the existing scanner→executor→monitor loop (which already branches credit vs debit via `CREDIT_STRATEGIES`). A shared `ai_rationale.py` narrates each entry. Strike/width selection is greeks-free (% of spot). No DB schema change.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest (SQLite in-memory), Tradier REST, `anthropic` SDK (already a dependency), Vite/React SPA.

**Spec:** `docs/superpowers/specs/2026-06-10-spreads-expansion-design.md`

**Working dir:** `C:\Users\lemol\AlphaGEX`, branch `claude/spreads-expansion`. All `pytest` from `spreadworks/`. Paths below are relative to `spreadworks/`. The full suite has one PRE-EXISTING unrelated collection error in `tests/test_atm_iv_fallback.py` (`ModuleNotFoundError: No module named 'spreadworks'`, present on `main`) — always run with `--ignore=tests/test_atm_iv_fallback.py`.

---

## Background the implementer needs

**Existing strategy shape.** Each builder returns a dataclass exposing `.ticker`, `.expiration`,
`.contracts`, `.legs()` (list of `{side, type, strike, expiration, entry_price}`), `.max_profit`,
`.max_loss` (per-contract $), `.pt_target_pnl`, `.sl_target_pnl` ($ totals), and EITHER `.credit`
(credit strats) OR `.debit` (debit strats). The executor's `open_position` reads
`signal.credit if hasattr(signal,"credit") else signal.debit` for `entry_price`.

**`compute_mtm` sign convention** (`backend/bots/executor.py`): short legs `+mid`, long legs `−mid`
("cost to unwind from this side"). Credit strats: `pnl=(entry−mtm_value)×ct×100`. Debit strats:
`mtm_value` is negated, `pnl=(mtm_value−entry)×ct×100`. So leg ORDER doesn't matter but the
`side` field does, and `entry_price` must be the net debit/credit.

**`CREDIT_STRATEGIES`** (`backend/bots/strategies/__init__.py`) currently
`{"iron_condor","iron_butterfly","double_diagonal_credit"}`. Add the two credit verticals.

**UNDERTOW's existing dip detector** (`backend/bots/strategies/dip_buy.py`): `closed_bars(history,today)`,
`sma(values,period)`, `rsi(values,period)`, and gate logic inside `build_dip_buy_signal`. We REUSE the
three indicator functions and re-implement the gate as a reusable `detect_setup` (dip + the bearish
mirror). `dip_buy.py` is retained.

**Scanner** (`backend/bots/scanner.py`): `_evaluate_universe_entry` loops the universe, builds a
`dip_buy` signal per ticker (deepest dip wins), opens one. `_build_signal` has a `dip_buy` branch.
`run_scan_cycle`'s monitor loop passes `entry_time`/`hold_days` to `decide_exit` for `dip_buy`.

**`decide_exit`** (`backend/bots/monitor.py`): the `dip_buy` branch does PT/SL (generic) + TIME_STOP +
PRE_EXPIRY, no same-day EOD. We generalize that branch to all multi-day vertical strategies.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/bots/strategies/setups.py` | `detect_setup()` — bullish dip / bearish rip, reusing dip_buy indicators | Create |
| `backend/bots/strategies/vertical_spread.py` | `build_vertical_signal()` for the 4 verticals + `VerticalSignal` | Create |
| `backend/bots/strategies/__init__.py` | add credit verticals to `CREDIT_STRATEGIES` | Modify |
| `backend/bots/ai_rationale.py` | Opus-4.8 entry rationale, fail-safe | Create |
| `backend/bots/monitor.py` | generalize multi-day exit branch to verticals | Modify |
| `backend/bots/scanner.py` | route UNDERTOW/DELTA through setups + vertical builder; wire rationale | Modify |
| `backend/bots/registry.py` | re-route UNDERTOW to debit verticals; add DELTA | Modify |
| `frontend/src/lib/botRegistry.js` | strategy labels + DELTA entry + theme | Modify |
| `tests/test_setups.py` | setup detection tests | Create |
| `tests/test_vertical_spread.py` | builder + MTM-lock tests | Create |
| `tests/test_ai_rationale.py` | fail-safe rationale tests | Create |
| `tests/test_monitor.py` / `test_scanner.py` / `test_registry.py` | extend | Modify |

---

## PHASE A — UNDERTOW v2 (debit verticals)

### Task 1: `setups.py` — dip/rip setup detection

**Files:** Create `backend/bots/strategies/setups.py`; Test `tests/test_setups.py`

- [ ] **Step 1: Failing test** — create `tests/test_setups.py`:

```python
"""Shared dip/rip setup detection tests."""
from __future__ import annotations
from datetime import date, timedelta
from backend.bots.strategies.setups import detect_setup, DEFAULT_SETUP_PARAMS


def _hist(closes_highs_lows):
    bars, base = [], date(2026, 4, 1)
    for i, (c, h, l) in enumerate(closes_highs_lows):
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": c, "high": h, "low": l, "close": c})
    return bars


def _dip_history():
    # 36 rising closes 101..136, spike high 150, then 3 down days -> oversold, above SMA
    rows = [(101 + i, 101 + i, 101 + i) for i in range(36)]
    rows += [(145, 150, 143), (143, 146, 142), (141, 143, 140), (140, 141, 139)]
    return _hist(rows)


def _rip_history():
    # 36 FALLING closes 150..115, spike low 100, then 3 up days -> overbought, below SMA
    rows = [(150 - i, 150 - i, 150 - i) for i in range(36)]
    rows += [(105, 107, 100), (107, 108, 104), (109, 110, 106), (110, 111, 108)]
    return _hist(rows)


def _p(**o):
    p = dict(DEFAULT_SETUP_PARAMS); p.update(o); return p


def test_bullish_dip_detected():
    s = detect_setup(spot=140.0, history=_dip_history(), today=date(2026, 6, 10), params=_p())
    assert s is not None and s.direction == "bullish" and s.setup == "dip"
    assert s.magnitude_pct >= 0.03 and s.reference_level == 150.0


def test_bearish_rip_detected():
    s = detect_setup(spot=110.0, history=_rip_history(), today=date(2026, 6, 10), params=_p())
    assert s is not None and s.direction == "bearish" and s.setup == "rip"
    assert s.magnitude_pct >= 0.03 and s.reference_level == 100.0


def test_no_setup_when_shallow():
    diag = []
    s = detect_setup(spot=149.0, history=_dip_history(), today=date(2026, 6, 10),
                     params=_p(), diag=diag)
    assert s is None and "no_setup" in diag[0]
```

- [ ] **Step 2: Run** `pytest tests/test_setups.py -v` → FAIL (module missing).

- [ ] **Step 3: Implement** — create `backend/bots/strategies/setups.py`:

```python
"""Shared dip/rip setup detection for the vertical-spread bots.

Reuses UNDERTOW's dip_buy indicators. A BULLISH "dip" = oversold pullback in an
uptrend (buy/sell-puts-below). A BEARISH "rip" = overbought bounce in a downtrend
(buy-puts/sell-calls-above). All thresholds are starting hypotheses (spec §0).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Any

from .dip_buy import closed_bars, sma, rsi

DEFAULT_SETUP_PARAMS: dict[str, Any] = {
    "lookback_n": 5,
    "dip_threshold": 0.03,   # min pullback/bounce magnitude vs the reference extreme
    "rsi_period": 2,
    "rsi_oversold": 10,      # bullish dip requires RSI < this
    "rsi_overbought": 90,    # bearish rip requires RSI > this
    "use_rsi_confirm": True,
    "use_trend_gate": True,
    "sma_period": 20,
}


@dataclass
class Setup:
    direction: str        # "bullish" | "bearish"
    setup: str            # "dip" | "rip"
    magnitude_pct: float  # distance from the 5-day reference extreme
    reference_level: float
    rsi_value: float | None
    sma_value: float | None
    spot: float


def detect_setup(*, spot: float, history: list[dict[str, Any]], today: date,
                 params: dict[str, Any], diag: list[str] | None = None) -> Setup | None:
    """Return a bullish dip OR bearish rip Setup, or None (with a diag reason)."""
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    n = int(params["lookback_n"]); sma_period = int(params["sma_period"])
    rsi_period = int(params["rsi_period"])
    need = max(n, sma_period, rsi_period + 1)
    bars = closed_bars(history, today)
    if len(bars) < need:
        return _reject(f"insufficient_history: have={len(bars)} need={need}")
    if spot <= 0:
        return _reject("missing_spot")

    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    ref_high = max(highs[-n:]); ref_low = min(lows[-n:])
    rsi_value = rsi(closes, rsi_period)
    sma_value = sma(closes, sma_period)
    thr = float(params["dip_threshold"])

    dip_pct = (ref_high - spot) / ref_high if ref_high > 0 else 0.0
    rip_pct = (spot - ref_low) / ref_low if ref_low > 0 else 0.0

    # Bullish dip: pulled back >= thr from the 5-day high, oversold, above SMA.
    if dip_pct >= thr:
        if params.get("use_rsi_confirm") and (rsi_value is None or rsi_value >= float(params["rsi_oversold"])):
            return _reject(f"dip_rsi_not_oversold: rsi={rsi_value}")
        if params.get("use_trend_gate") and (sma_value is None or spot <= sma_value):
            return _reject(f"dip_below_sma: spot={spot:.2f} sma={sma_value}")
        return Setup("bullish", "dip", round(dip_pct, 4), round(ref_high, 4),
                     rsi_value, sma_value, spot)

    # Bearish rip: bounced >= thr from the 5-day low, overbought, below SMA.
    if rip_pct >= thr:
        if params.get("use_rsi_confirm") and (rsi_value is None or rsi_value <= float(params["rsi_overbought"])):
            return _reject(f"rip_rsi_not_overbought: rsi={rsi_value}")
        if params.get("use_trend_gate") and (sma_value is None or spot >= sma_value):
            return _reject(f"rip_above_sma: spot={spot:.2f} sma={sma_value}")
        return Setup("bearish", "rip", round(rip_pct, 4), round(ref_low, 4),
                     rsi_value, sma_value, spot)

    return _reject(f"no_setup: dip={dip_pct:.3f} rip={rip_pct:.3f} min={thr:.3f}")
```

- [ ] **Step 4: Run** `pytest tests/test_setups.py -v` → PASS (3).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/strategies/setups.py tests/test_setups.py
git commit -m "feat(spreads): shared dip/rip setup detection"
```

> Note for implementer: `_rip_history` falls from 150→115 over 36 bars then bounces 100→110, so the last 2 close-deltas are positive (RSI(2)=100 > 90 overbought) and spot 110 < SMA(20)≈ (mean of last 20 closes, which are ~129 down to 110 then the bounce) — verify the test passes; if `rip_above_sma` fires, the fixture's SMA is above spot and the test fixture must be adjusted so spot < SMA. The provided numbers are designed so SMA(20) ≈ 119 > 110 (bearish) — confirm by running.

---

### Task 2: `vertical_spread.py` — debit verticals (bull call / bear put)

**Files:** Create `backend/bots/strategies/vertical_spread.py`; Test `tests/test_vertical_spread.py`

- [ ] **Step 1: Failing test** — create `tests/test_vertical_spread.py`:

```python
"""Vertical-spread builder tests."""
from __future__ import annotations
from backend.bots.strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS


def _chain(spot, ticker="NVDA"):
    opts = []
    for s in range(100, 201, 5):
        opts.append({"strike": s, "type": "call", "bid": max(0.2, (spot - s) * 0.5 + 5) if s <= spot + 20 else 0.5,
                     "ask": max(0.4, (spot - s) * 0.5 + 5.4) if s <= spot + 20 else 0.7})
        opts.append({"strike": s, "type": "put", "bid": max(0.2, (s - spot) * 0.5 + 5) if s >= spot - 20 else 0.5,
                     "ask": max(0.4, (s - spot) * 0.5 + 5.4) if s >= spot - 20 else 0.7})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker, "options": opts}


def _p(**o):
    p = dict(DEFAULT_VERTICAL_PARAMS); p.update(o); return p


_CFG = {"bp_pct": 0.02, "pt_pct": 0.50, "sl_pct": 0.50, "max_contracts": 10}


def test_bull_call_spread_is_debit_two_legs():
    sig = build_vertical_signal(kind="bull_call_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "debit") and not hasattr(sig, "credit")
    legs = sig.legs()
    assert len(legs) == 2
    longs = [l for l in legs if l["side"] == "long"]
    shorts = [l for l in legs if l["side"] == "short"]
    assert len(longs) == 1 and len(shorts) == 1
    assert all(l["type"] == "call" for l in legs)
    # long strike (ATM) below short strike (OTM); debit > 0
    assert longs[0]["strike"] < shorts[0]["strike"]
    assert sig.debit > 0
    assert sig.max_loss == round(sig.debit * 100, 2)


def test_bear_put_spread_is_debit_puts():
    sig = build_vertical_signal(kind="bear_put_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "debit")
    legs = sig.legs()
    assert all(l["type"] == "put" for l in legs)
    longs = [l for l in legs if l["side"] == "long"][0]
    shorts = [l for l in legs if l["side"] == "short"][0]
    assert longs["strike"] > shorts["strike"]  # buy higher put, sell lower put
    assert sig.debit > 0
```

- [ ] **Step 2: Run** `pytest tests/test_vertical_spread.py -v` → FAIL.

- [ ] **Step 3: Implement** — create `backend/bots/strategies/vertical_spread.py`:

```python
"""Two-leg vertical-spread builders (greeks-free, % of spot).

Four kinds:
  bull_call_spread / bear_put_spread  -> DEBIT (not in CREDIT_STRATEGIES)
  bull_put_spread  / bear_call_spread -> CREDIT (in CREDIT_STRATEGIES)

Leg `side` follows the executor's sign convention (short +mid, long -mid). Strikes
are chosen by % of spot and snapped to available strikes. All defaults are starting
hypotheses (spec §0).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

DEFAULT_VERTICAL_PARAMS: dict[str, Any] = {
    "spread_pct": 0.04,       # width: long leg this far beyond the near leg
    "short_otm_pct": 0.03,    # credit only: near (short) leg this far OTM
    "max_spread_pct": 0.15,   # per-leg bid/ask spread ceiling (fraction of mid)
    "min_option_price": 0.20,
    "min_credit": 0.20,       # credit only
}

DEBIT_KINDS = {"bull_call_spread", "bear_put_spread"}
CREDIT_KINDS = {"bull_put_spread", "bear_call_spread"}


@dataclass
class VerticalSignal:
    kind: str
    ticker: str
    expiration: str
    contracts: int
    max_profit: float
    max_loss: float
    pt_target_pnl: float
    sl_target_pnl: float
    _legs: list[dict[str, Any]]
    width: int
    # debit OR credit set in __post_init__ via the factory below (see build).
    net: float = 0.0
    is_credit: bool = False

    def legs(self) -> list[dict[str, Any]]:
        return list(self._legs)


def _avail(chain, opt_type):
    return sorted({int(o["strike"]) for o in chain["options"] if o["type"] == opt_type})


def _nearest(strikes, target):
    return min(strikes, key=lambda s: abs(s - target)) if strikes else None


def _find(chain, strike, opt_type):
    for o in chain["options"]:
        if int(o["strike"]) == strike and o["type"] == opt_type:
            return o
    return None


def _mid(o):
    return (float(o["bid"] or 0) + float(o["ask"] or 0)) / 2.0


def _spread_ok(o, params):
    bid = float(o["bid"] or 0); ask = float(o["ask"] or 0)
    mid = (bid + ask) / 2.0
    if mid < float(params["min_option_price"]):
        return False, f"price_too_low: mid={mid:.2f}"
    if mid <= 0 or (ask - bid) / mid > float(params["max_spread_pct"]):
        return False, "spread_too_wide"
    return True, ""


def build_vertical_signal(*, kind, chain, config, equity, params, diag=None):
    def _reject(msg):
        if diag is not None:
            diag.append(msg)
        return None

    spot = float(chain["spot"])
    if spot <= 0:
        return _reject("missing_spot")
    opt_type = "call" if kind in ("bull_call_spread", "bear_call_spread") else "put"
    strikes = _avail(chain, opt_type)
    if not strikes:
        return _reject("no_strikes")
    spread_w = float(params["spread_pct"]) * spot
    otm = float(params["short_otm_pct"]) * spot

    # Pick the two strikes per kind.
    if kind == "bull_call_spread":      # buy ATM call, sell call spread_w higher
        near = _nearest(strikes, round(spot)); far = _nearest(strikes, round(spot + spread_w))
        long_k, short_k = near, far
    elif kind == "bear_put_spread":     # buy ATM put, sell put spread_w lower
        near = _nearest(strikes, round(spot)); far = _nearest(strikes, round(spot - spread_w))
        long_k, short_k = near, far
    elif kind == "bull_put_spread":     # sell put otm below, buy put spread_w further below
        near = _nearest(strikes, round(spot - otm)); far = _nearest(strikes, round(spot - otm - spread_w))
        short_k, long_k = near, far
    else:                                # bear_call_spread: sell call otm above, buy call further above
        near = _nearest(strikes, round(spot + otm)); far = _nearest(strikes, round(spot + otm + spread_w))
        short_k, long_k = near, far
    if long_k is None or short_k is None or long_k == short_k:
        return _reject(f"strike_select_failed: long={long_k} short={short_k}")

    lo = _find(chain, long_k, opt_type); so = _find(chain, short_k, opt_type)
    if not lo or not so:
        return _reject("strike_missing")
    for o in (lo, so):
        ok, why = _spread_ok(o, params)
        if not ok:
            return _reject(why)

    long_mid, short_mid = _mid(lo), _mid(so)
    width = abs(short_k - long_k)
    is_credit = kind in CREDIT_KINDS
    if is_credit:
        net = round(short_mid - long_mid, 4)            # credit collected
        if net < float(params["min_credit"]):
            return _reject(f"credit_too_low: credit={net:.2f}")
        max_loss_per = (width - net) * 100.0
        max_profit_per = net * 100.0
    else:
        net = round(long_mid - short_mid, 4)            # debit paid
        if net <= 0:
            return _reject(f"non_positive_debit: debit={net:.2f}")
        max_loss_per = net * 100.0
        max_profit_per = (width - net) * 100.0
    if max_loss_per <= 0:
        return _reject(f"non_positive_max_loss width={width} net={net}")

    bp_pct = float(config.get("bp_pct", 0.02))
    raw_cap = int(config.get("max_contracts", 0) or 0)
    raw = int((equity * bp_pct) // max_loss_per)
    contracts = max(0, raw) if raw_cap <= 0 else max(0, min(raw_cap, raw))
    if contracts < 1:
        return _reject(f"sizing_below_one: max_loss_per={max_loss_per:.0f}")

    pt_pct = float(config.get("pt_pct", 0.50)); sl_pct = float(config.get("sl_pct", 0.50))
    base = max_profit_per if is_credit else max_loss_per  # credit PT% of credit; debit PT% of debit
    pt = pt_pct * base * contracts
    sl = sl_pct * base * contracts

    legs = [
        {"side": "long", "type": opt_type, "strike": long_k,
         "expiration": chain["expiration"], "entry_price": long_mid},
        {"side": "short", "type": opt_type, "strike": short_k,
         "expiration": chain["expiration"], "entry_price": short_mid},
    ]
    sig = VerticalSignal(
        kind=kind, ticker=chain.get("ticker", "SPY"), expiration=chain["expiration"],
        contracts=contracts, max_profit=round(max_profit_per, 2), max_loss=round(max_loss_per, 2),
        pt_target_pnl=round(pt, 2), sl_target_pnl=round(sl, 2), _legs=legs, width=width,
        net=net, is_credit=is_credit,
    )
    # Expose .debit XOR .credit so the executor picks entry_price + the right P&L branch.
    if is_credit:
        sig.credit = net
    else:
        sig.debit = net
    return sig
```

- [ ] **Step 4: Run** `pytest tests/test_vertical_spread.py -v` → PASS (2).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/strategies/vertical_spread.py tests/test_vertical_spread.py
git commit -m "feat(spreads): vertical_spread builder — debit kinds (bull call / bear put)"
```

---

### Task 3: Credit verticals + CREDIT_STRATEGIES + MTM locks

**Files:** Modify `backend/bots/strategies/__init__.py`; Test `tests/test_vertical_spread.py`

- [ ] **Step 1: Failing tests** — append to `tests/test_vertical_spread.py`:

```python
from backend.bots.executor import compute_mtm


def test_bull_put_spread_is_credit():
    sig = build_vertical_signal(kind="bull_put_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "credit") and not hasattr(sig, "debit")
    legs = sig.legs()
    assert all(l["type"] == "put" for l in legs)
    s = [l for l in legs if l["side"] == "short"][0]
    lo = [l for l in legs if l["side"] == "long"][0]
    assert s["strike"] > lo["strike"]          # sell higher put, buy lower put
    assert sig.credit > 0
    assert sig.max_profit == round(sig.credit * 100, 2)


def test_bear_call_spread_is_credit():
    sig = build_vertical_signal(kind="bear_call_spread", chain=_chain(140.0),
                                config=_CFG, equity=25000.0, params=_p())
    assert sig is not None and hasattr(sig, "credit")
    s = [l for l in sig.legs() if l["side"] == "short"][0]
    lo = [l for l in sig.legs() if l["side"] == "long"][0]
    assert s["strike"] < lo["strike"]          # sell lower call, buy higher call


def test_debit_vertical_mtm_sign():
    # bull call spread: paid debit D, spread widens -> profit
    legs = [{"side": "long", "type": "call", "strike": 140, "expiration": "x", "entry_price": 5.0},
            {"side": "short", "type": "call", "strike": 146, "expiration": "x", "entry_price": 2.0}]
    # entry debit = 5-2 = 3.00 ; now long worth 7, short worth 3 -> spread 4 -> +$100
    _, pnl = compute_mtm(strategy="bull_call_spread", legs=legs, entry_price=3.0,
                         contracts=1, leg_mids=[7.0, 3.0])
    assert pnl == 100.0


def test_credit_vertical_mtm_sign():
    # bull put spread: collected credit C, spread narrows -> profit
    legs = [{"side": "long", "type": "put", "strike": 130, "expiration": "x", "entry_price": 1.0},
            {"side": "short", "type": "put", "strike": 136, "expiration": "x", "entry_price": 3.0}]
    # entry credit = 3-1 = 2.00 ; now short worth 1.5, long worth 0.5 -> cost-to-close 1.0 -> +$100
    _, pnl = compute_mtm(strategy="bull_put_spread", legs=legs, entry_price=2.0,
                         contracts=1, leg_mids=[0.5, 1.5])
    assert pnl == 100.0
```

- [ ] **Step 2: Run** `pytest tests/test_vertical_spread.py -k "credit or mtm" -v` → the credit-MTM test FAILS (bull_put_spread not in CREDIT_STRATEGIES → debit path → wrong sign).

- [ ] **Step 3: Implement** — edit `backend/bots/strategies/__init__.py`:

```python
CREDIT_STRATEGIES = frozenset(
    {"iron_condor", "iron_butterfly", "double_diagonal_credit",
     "bull_put_spread", "bear_call_spread"}
)
```

- [ ] **Step 4: Run** `pytest tests/test_vertical_spread.py -v` → PASS (all 6).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/strategies/__init__.py tests/test_vertical_spread.py
git commit -m "feat(spreads): credit verticals + register in CREDIT_STRATEGIES + MTM locks"
```

---

### Task 4: Generalize `decide_exit` multi-day branch to verticals

**Files:** Modify `backend/bots/monitor.py`; Test `tests/test_monitor.py`

- [ ] **Step 1: Failing test** — append to `tests/test_monitor.py`:

```python
from datetime import date as _d, datetime as _dt, time as _t
from backend.bots.monitor import decide_exit


def _vc(now, *, entry, hold_days=2, exp="2026-06-22", mtm=0.0, strat="bull_call_spread"):
    return decide_exit(strategy=strat, mtm_pnl=mtm, pt_target_pnl=200.0, sl_target_pnl=250.0,
                       now_ct=now, front_expiration=_d.fromisoformat(exp), eod_close_ct=_t(14, 45),
                       event_blackout=False, entry_time=entry, hold_days=hold_days)


def test_vertical_pt_sl_time_stop():
    assert _vc(_dt(2026, 6, 10, 10, 0), entry=_dt(2026, 6, 10, 9, 0), mtm=250.0).reason == "PT"
    assert _vc(_dt(2026, 6, 10, 10, 0), entry=_dt(2026, 6, 10, 9, 0), mtm=-300.0).reason == "SL"
    d = _vc(_dt(2026, 6, 10, 9, 0), entry=_dt(2026, 6, 8, 9, 0))
    assert d.should_close and d.reason == "TIME_STOP"
    # credit kind also multi-day
    d2 = _vc(_dt(2026, 6, 22, 9, 0), entry=_dt(2026, 6, 21, 9, 0), hold_days=99,
             strat="bull_put_spread")
    assert d2.reason == "PRE_EXPIRY"
```

- [ ] **Step 2: Run** `pytest tests/test_monitor.py -k vertical -v` → FAIL (verticals fall through to EOD logic → wrong reason / no close).

- [ ] **Step 3: Implement** — in `backend/bots/monitor.py`, replace the `if strategy == "dip_buy":` line in `decide_exit` with a set membership check. Add near the top of the module:

```python
MULTI_DAY_STRATEGIES = frozenset(
    {"dip_buy", "bull_call_spread", "bear_put_spread", "bull_put_spread", "bear_call_spread"}
)
```

Then change the branch guard from `if strategy == "dip_buy":` to `if strategy in MULTI_DAY_STRATEGIES:`. Leave the branch body (TIME_STOP / PRE_EXPIRY) unchanged.

- [ ] **Step 4: Run** `pytest tests/test_monitor.py -v` → PASS (all, incl. existing dip_buy + new vertical).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/monitor.py tests/test_monitor.py
git commit -m "feat(spreads): decide_exit multi-day branch covers vertical strategies"
```

---

### Task 5: Re-route UNDERTOW to debit verticals (registry + frontend)

**Files:** Modify `backend/bots/registry.py`, `frontend/src/lib/botRegistry.js`; Test `tests/test_registry.py`

- [ ] **Step 1: Failing test** — append to `tests/test_registry.py`:

```python
def test_undertow_is_vertical_debit():
    from backend.bots.registry import get_bot
    m = get_bot("undertow")
    assert m["vertical_mode"] == "debit"
    assert m["params"]["spread_pct"] == 0.04
    assert m["defaults"]["pt_pct"] == 0.50 and m["defaults"]["sl_pct"] == 0.50
```

- [ ] **Step 2: Run** `pytest tests/test_registry.py -k vertical_debit -v` → FAIL.

- [ ] **Step 3: Implement** — in `backend/bots/registry.py`, change UNDERTOW's `strategy` to `"vertical_debit"`, add `"vertical_mode": "debit"`, and merge the new params. Replace UNDERTOW's `strategy`, and set:

```python
        "strategy": "vertical_debit",
        "vertical_mode": "debit",
        "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            "lookback_n": 5, "dip_threshold": 0.03,
            "rsi_period": 2, "rsi_oversold": 10, "rsi_overbought": 90,
            "use_rsi_confirm": True, "use_trend_gate": True, "sma_period": 20,
            "spread_pct": 0.04, "max_spread_pct": 0.15, "min_option_price": 0.20,
            "earnings_exclude_days": 3, "hold_days": 2,
        },
```

Keep UNDERTOW's `defaults` block but set `pt_pct: 0.50`, `sl_pct: 0.50` (they may already be 0.40/0.50 — set both to 0.50). Leave `enabled`, sizing, window untouched.

In `frontend/src/lib/botRegistry.js`: change `undertow` entry `strategy: 'vertical_debit'`; add to `STRATEGY_LABEL`: `vertical_debit: 'Debit Vertical', vertical_credit: 'Credit Vertical',`.

- [ ] **Step 4: Run** `pytest tests/test_registry.py -v` → PASS (incl. existing undertow tests, which only assert display/enabled/universe — confirm none assert `strategy=="dip_buy"`; if one does, update it to `"vertical_debit"`).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/registry.py frontend/src/lib/botRegistry.js tests/test_registry.py
git commit -m "feat(spreads): re-route UNDERTOW to debit verticals"
```

---

### Task 6: Scanner — route vertical bots through setups + builder

**Files:** Modify `backend/bots/scanner.py`; Test `tests/test_scanner.py`

- [ ] **Step 1: Failing tests** — append to `tests/test_scanner.py` (reuse `FakeChainProvider`, `CT`, `_enable_undertow`, `_undertow_history` from earlier; add a rip history + a chain with both calls and puts):

```python
def _spread_chain(ticker, spot):
    opts = []
    for s in range(100, 201, 5):
        opts.append({"strike": s, "type": "call", "bid": 4.8, "ask": 5.2})
        opts.append({"strike": s, "type": "put", "bid": 4.8, "ask": 5.2})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker, "options": opts}


def test_undertow_opens_bull_call_spread_on_dip(db_session):
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()})
    res = run_scan_cycle(engine=eng, bot="undertow",
                         now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    pos = list_open_positions(eng, "undertow")[0]
    assert pos["strategy"] == "bull_call_spread"
    legs = _j.loads(pos["legs"])
    assert len(legs) == 2 and all(l["type"] == "call" for l in legs)
```

(Bearish-rip coverage for the scanner is exercised in Task 10 for DELTA; UNDERTOW's bullish path here is sufficient to prove the vertical routing.)

- [ ] **Step 2: Run** `pytest tests/test_scanner.py -k bull_call -v` → FAIL (no vertical routing yet).

- [ ] **Step 3: Implement** — in `backend/bots/scanner.py`:

Add imports:
```python
from .strategies.setups import detect_setup, DEFAULT_SETUP_PARAMS
from .strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS
```

Add a kind-resolution helper near `_evaluate_universe_entry`:
```python
def _vertical_kind(mode: str, direction: str) -> str:
    if mode == "debit":
        return "bull_call_spread" if direction == "bullish" else "bear_put_spread"
    return "bull_put_spread" if direction == "bullish" else "bear_call_spread"
```

In `_evaluate_universe_entry`, replace the dip_buy `_build_signal` call with the vertical path. For each non-held, non-earnings ticker:
```python
        chain = chain_provider.get_chain(ticker=ticker, dte=meta["front_dte"], today=now_ct.date())
        if chain is None:
            last_reason = f"chain_unavailable: {ticker}"; continue
        lookback = max(int(params.get("sma_period", 20)), int(params.get("lookback_n", 5))) + 25
        history = chain_provider.get_daily_history(ticker=ticker, days=lookback)
        if not history:
            last_reason = f"history_unavailable: {ticker}"; continue
        sdiag: list[str] = []
        setup = detect_setup(spot=float(chain["spot"]), history=history,
                             today=now_ct.date(),
                             params={**DEFAULT_SETUP_PARAMS, **params}, diag=sdiag)
        if setup is None:
            last_reason = sdiag[0] if sdiag else f"no_setup: {ticker}"; continue
        kind = _vertical_kind(meta.get("vertical_mode", "debit"), setup.direction)
        vdiag: list[str] = []
        signal = build_vertical_signal(
            kind=kind, chain=chain, config=cfg, equity=equity,
            params={**DEFAULT_VERTICAL_PARAMS, **params}, diag=vdiag)
        if signal is None:
            last_reason = vdiag[0] if vdiag else f"no_signal: {ticker}"; continue
        candidates.append((setup.magnitude_pct, signal, setup))
```

When opening the best candidate, pass `signal.kind` as the strategy and write notes (include the setup context). Replace the open block:
```python
    candidates.sort(key=lambda c: c[0], reverse=True)
    _mag, signal, setup = candidates[0]
    notes = json.dumps({
        "ticker": signal.ticker, "kind": signal.kind, "direction": setup.direction,
        "setup": setup.setup, "magnitude_pct": setup.magnitude_pct,
        "reference_level": setup.reference_level, "rsi": setup.rsi_value,
        "width": signal.width, "net": signal.net, "is_credit": signal.is_credit,
    })
    pid = open_position(engine, bot, signal.kind, signal, now_ct, notes=notes)
    return {"outcome": "TRADE", "reason": "OPENED", "position_id": pid}
```

Also: the universe-entry dispatch in `_evaluate_entry` currently guards on `meta["strategy"] == "dip_buy"`. Change it to dispatch for ANY universe bot:
```python
    universe = meta.get("universe")
    if universe and meta.get("vertical_mode"):
        return _evaluate_universe_entry(...)  # same args as before
```

The monitor loop already passes `entry_time`/`hold_days` for `dip_buy`; broaden that guard to verticals — change `if pos["strategy"] == "dip_buy":` to `if pos["strategy"] in MULTI_DAY:` where `MULTI_DAY = {"dip_buy","bull_call_spread","bear_put_spread","bull_put_spread","bear_call_spread"}` defined at module top of scanner.py.

> The `dip_buy` branch in `_build_signal` can stay (unused by UNDERTOW now, harmless). Do not delete it.

- [ ] **Step 4: Run** `pytest tests/test_scanner.py -v` → PASS (existing + new). Then full suite `pytest --ignore=tests/test_atm_iv_fallback.py -q`.

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py tests/test_scanner.py
git commit -m "feat(spreads): scanner routes vertical bots through setups + vertical builder"
```

---

## PHASE C — AI entry rationale

### Task 7: `ai_rationale.py` — fail-safe Opus-4.8 narration

**Files:** Create `backend/bots/ai_rationale.py`; Test `tests/test_ai_rationale.py`

- [ ] **Step 1: Failing test** — create `tests/test_ai_rationale.py`:

```python
"""AI entry rationale — must be fail-safe and never raise."""
from __future__ import annotations
import backend.bots.ai_rationale as air


class _FakeBlock:
    type = "text"
    def __init__(self, t): self.text = t


class _FakeMsg:
    def __init__(self, t): self.content = [_FakeBlock(t)]


class _FakeClient:
    def __init__(self, text=None, raise_exc=None):
        self._text = text; self._raise = raise_exc
        self.messages = self
    def create(self, **kwargs):
        if self._raise: raise self._raise
        return _FakeMsg(self._text)


CTX = {"ticker": "NVDA", "kind": "bull_call_spread", "direction": "bullish",
       "setup": "dip", "magnitude_pct": 0.067, "rsi": 5.0}


def test_returns_text_on_success(monkeypatch):
    monkeypatch.setattr(air, "_client", lambda: _FakeClient(text="Bought the NVDA dip."))
    out = air.generate_entry_rationale(bot="undertow", signal_context=CTX)
    assert out == "Bought the NVDA dip."


def test_returns_none_on_exception(monkeypatch):
    monkeypatch.setattr(air, "_client", lambda: _FakeClient(raise_exc=RuntimeError("boom")))
    assert air.generate_entry_rationale(bot="undertow", signal_context=CTX) is None


def test_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(air, "_enabled", lambda: False)
    assert air.generate_entry_rationale(bot="undertow", signal_context=CTX) is None


def test_returns_none_on_empty(monkeypatch):
    monkeypatch.setattr(air, "_client", lambda: _FakeClient(text="   "))
    assert air.generate_entry_rationale(bot="undertow", signal_context=CTX) is None
```

- [ ] **Step 2: Run** `pytest tests/test_ai_rationale.py -v` → FAIL.

- [ ] **Step 3: Implement** — create `backend/bots/ai_rationale.py`:

```python
"""Cheap, fail-safe entry rationale. EXPLANATORY ONLY — never gates/sizes/exits a trade.

Calls Claude (Opus 4.8) once per OPEN with a tiny structured context, ~160 output
tokens. Any failure returns None and the caller opens the trade anyway. Kill via
env SPREADWORKS_AI_RATIONALE=false.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any

logger = logging.getLogger("spreadworks.bots.ai_rationale")

MODEL = "claude-opus-4-8"
_SYSTEM = (
    "You explain a single options paper-trade in 1-2 plain sentences for a trader's "
    "dashboard. Say WHY the bot entered and WHAT level or exit it is watching. Be "
    "concrete and brief. No preamble, no markdown, no disclaimers. Output only the "
    "explanation text."
)


def _enabled() -> bool:
    return os.getenv("SPREADWORKS_AI_RATIONALE", "true").strip().lower() not in ("false", "0", "no")


def _client():
    import anthropic
    # max_retries=0: one shot, never a retry storm; short timeout so a slow API
    # call can't stall the scanner.
    return anthropic.Anthropic(max_retries=0, timeout=8.0)


def generate_entry_rationale(*, bot: str, signal_context: dict[str, Any]) -> str | None:
    if not _enabled():
        return None
    try:
        client = _client()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=160,
            system=_SYSTEM,
            messages=[{"role": "user", "content":
                       f"Bot {bot} just opened this paper trade:\n{json.dumps(signal_context)}"}],
        )
        text = ""
        for block in getattr(msg, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += block.text
        text = text.strip()
        return text or None
    except Exception as e:  # noqa: BLE001 — must never raise into the scanner
        logger.warning(f"[ai_rationale] {bot} failed: {e}")
        return None
```

- [ ] **Step 4: Run** `pytest tests/test_ai_rationale.py -v` → PASS (4).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/ai_rationale.py tests/test_ai_rationale.py
git commit -m "feat(spreads): fail-safe Opus-4.8 entry rationale module"
```

---

### Task 8: Wire rationale into scanner entry

**Files:** Modify `backend/bots/scanner.py`; Test `tests/test_scanner.py`

- [ ] **Step 1: Failing test** — append to `tests/test_scanner.py`:

```python
def test_undertow_writes_ai_rationale(db_session, monkeypatch):
    import backend.bots.ai_rationale as air
    monkeypatch.setattr(air, "generate_entry_rationale",
                        lambda *, bot, signal_context: "Test rationale.")
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()})
    run_scan_cycle(engine=eng, bot="undertow",
                   now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                   chain_provider=provider, event_blackout=False)
    notes = _j.loads(list_open_positions(eng, "undertow")[0]["notes"])
    assert notes["rationale"] == "Test rationale."
```

- [ ] **Step 2: Run** `pytest tests/test_scanner.py -k rationale -v` → FAIL (no rationale key).

- [ ] **Step 3: Implement** — in `backend/bots/scanner.py`, import at top:
```python
from . import ai_rationale
```
In `_evaluate_universe_entry`, before building `notes`, generate the rationale from the setup+signal context and add it to the notes dict:
```python
    rationale = ai_rationale.generate_entry_rationale(
        bot=bot,
        signal_context={
            "ticker": signal.ticker, "kind": signal.kind, "direction": setup.direction,
            "setup": setup.setup, "magnitude_pct": setup.magnitude_pct,
            "reference_level": setup.reference_level, "rsi": setup.rsi_value,
            "width": signal.width, "net": signal.net, "is_credit": signal.is_credit,
            "max_profit": signal.max_profit, "max_loss": signal.max_loss,
            "pt_target_pnl": signal.pt_target_pnl, "sl_target_pnl": signal.sl_target_pnl,
        },
    )
```
Then add `"rationale": rationale,` into the `notes = json.dumps({...})` payload built in Task 6.

> Reference: `air.generate_entry_rationale` is monkeypatched in tests, so the real API is never called in CI. In production a missing `ANTHROPIC_API_KEY` → None → blank rationale, trade still opens.

- [ ] **Step 4: Run** `pytest tests/test_scanner.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py tests/test_scanner.py
git commit -m "feat(spreads): wire AI entry rationale into universe entry"
```

---

## PHASE B — DELTA (credit verticals)

### Task 9: Register DELTA (backend + frontend)

**Files:** Modify `backend/bots/registry.py`, `frontend/src/lib/botRegistry.js`; Test `tests/test_registry.py`

- [ ] **Step 1: Failing test** — append to `tests/test_registry.py`:

```python
def test_delta_registered_credit(db_session):
    from backend.bots.registry import get_bot
    from sqlalchemy import text
    m = get_bot("delta")
    assert m["display"] == "DELTA" and m["vertical_mode"] == "credit"
    assert m["params"]["min_credit"] == 0.20
    assert m["defaults"]["enabled"] is False and m["defaults"]["sl_pct"] == 1.5
    eng = db_session.get_bind()
    row = eng.connect().execute(text("SELECT enabled FROM delta_config WHERE id=1")).first()
    assert row is not None
```

- [ ] **Step 2: Run** `pytest tests/test_registry.py -k delta -v` → FAIL.

- [ ] **Step 3: Implement** — add DELTA to `BOT_REGISTRY` in `backend/bots/registry.py`:

```python
    # DELTA — directional credit spreads on the UNDERTOW universe. Sells a put
    # credit spread on the bullish (oversold-dip) setup and a call credit spread
    # on the bearish (overbought-rip) setup. Defined risk = width - credit.
    # Paper-only, ships disabled.
    "delta": {
        "display": "DELTA",
        "strategy": "vertical_credit",
        "vertical_mode": "credit",
        "ticker": "SPY",
        "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            "lookback_n": 5, "dip_threshold": 0.03,
            "rsi_period": 2, "rsi_oversold": 10, "rsi_overbought": 90,
            "use_rsi_confirm": True, "use_trend_gate": True, "sma_period": 20,
            "short_otm_pct": 0.03, "spread_pct": 0.04, "max_spread_pct": 0.15,
            "min_option_price": 0.20, "min_credit": 0.20,
            "earnings_exclude_days": 3, "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0, "enabled": False, "max_contracts": 10,
            "bp_pct": 0.02, "sd_mult": 1.0, "pt_pct": 0.50, "sl_pct": 1.5,
            "entry_start_ct": "08:35", "entry_end_ct": "14:30", "eod_close_ct": "14:45",
            "discord_alerts": False, "delta_skew": 0, "use_gex_walls": False,
            "max_concurrent_positions": 5,
        },
    },
```

In `frontend/src/lib/botRegistry.js`: add `delta: { display: 'DELTA', strategy: 'vertical_credit', ticker: 'multi', version: 'v1.0' },` to `BOT_REGISTRY`, and a `BOT_THEME.delta` (teal-green, e.g. primary `#14b8a6`, full rgba palette + `glyph: 'wave'`).

- [ ] **Step 4: Run** `pytest tests/test_registry.py -v` then full suite `pytest --ignore=tests/test_atm_iv_fallback.py -q` → PASS (DELTA tables auto-create; bot-set tests that hardcode the list must be updated to include `delta` — they're in test_registry.py).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/registry.py frontend/src/lib/botRegistry.js tests/test_registry.py
git commit -m "feat(spreads): register DELTA credit-spread bot"
```

---

### Task 10: Scanner — DELTA credit routing (verify end-to-end)

**Files:** Test `tests/test_scanner.py` (routing already generic from Task 6)

- [ ] **Step 1: Failing/▶ test** — append to `tests/test_scanner.py`:

```python
def _rip_history_scanner():
    bars, base = [], date(2026, 4, 1)
    for i in range(36):
        c = 150 - i
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": c, "high": c, "low": c, "close": c})
    for c, h, l in [(105, 107, 100), (107, 108, 104), (109, 110, 106), (110, 111, 108)]:
        bars.append({"date": (base + timedelta(days=len(bars))).isoformat(),
                     "open": c, "high": h, "low": l, "close": c})
    return bars


def _enable(eng, bot):
    from sqlalchemy import text
    with eng.begin() as c:
        c.execute(text(f"UPDATE {bot}_config SET enabled=1"))


def test_delta_opens_put_credit_spread_on_dip(db_session):
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable(eng, "delta")
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()})  # dip history -> bullish -> put credit
    res = run_scan_cycle(engine=eng, bot="delta",
                         now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    pos = list_open_positions(eng, "delta")[0]
    assert pos["strategy"] == "bull_put_spread"
    assert all(l["type"] == "put" for l in _j.loads(pos["legs"]))


def test_delta_opens_call_credit_spread_on_rip(db_session):
    from backend.bots.scanner import run_scan_cycle
    from backend.bots.executor import list_open_positions
    import json as _j
    eng = db_session.get_bind(); _enable(eng, "delta")
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 110.0)},
        daily_history={"NVDA": _rip_history_scanner()})  # rip -> bearish -> call credit
    res = run_scan_cycle(engine=eng, bot="delta",
                         now_ct=datetime(2026, 6, 10, 9, 0, tzinfo=CT),
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    pos = list_open_positions(eng, "delta")[0]
    assert pos["strategy"] == "bear_call_spread"
    assert all(l["type"] == "call" for l in _j.loads(pos["legs"]))
```

- [ ] **Step 2: Run** `pytest tests/test_scanner.py -k delta -v`. If the rip test fails on `rip_above_sma` or `rip_rsi_not_overbought`, adjust `_rip_history_scanner` so the last 2 close-deltas are positive (overbought RSI(2)) and spot (110) < SMA(20) of the series. Do not weaken the production gates — fix the fixture.

- [ ] **Step 3: Implement** — none expected (routing is generic from Task 6). If a gap surfaces (e.g. DELTA not dispatched), fix the dispatch guard in `_evaluate_entry` to `meta.get("vertical_mode")` (already done in Task 6).

- [ ] **Step 4: Run** full suite `pytest --ignore=tests/test_atm_iv_fallback.py -q` → all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_scanner.py
git commit -m "test(spreads): DELTA credit-spread routing end-to-end"
```

---

### Task 11: Frontend build + full verification

**Files:** none (verification)

- [ ] **Step 1:** Full backend suite: `pytest --ignore=tests/test_atm_iv_fallback.py -q` → green.
- [ ] **Step 2:** `cd frontend && npm run build` → succeeds; grep the bundle for `DELTA` and `Credit Vertical`.
- [ ] **Step 3:** Commit rebuilt dist:
```bash
git add frontend/dist
git commit -m "build(spreads): rebuild frontend dist with DELTA + vertical labels"
```
- [ ] **Step 4:** Confirm scan loop auto-includes both bots (`backend/__init__.py` `scan_bots_tick` iterates `list_bots()` — no change needed).

---

## Self-review notes (carried into execution)

- **Sign/ordering invariant:** credit verticals MUST be in `CREDIT_STRATEGIES` (Task 3); the MTM-lock tests prove the P&L sign for both a debit and a credit vertical.
- **Fail-safe AI:** `generate_entry_rationale` returns `None` on ANY error and is monkeypatched in all scanner tests — the real API never runs in CI, and a missing key in prod blanks the rationale without blocking the trade.
- **No DB migration:** DELTA's tables auto-create from the registry; rationale + setup context ride in the existing `notes` column.
- **Honest framing:** same unproven signals as v1; mid-fill optimism is worse for 2-leg spreads; credit spreads can lose width−credit. Don't imply validated edge anywhere.
- **Greeks-free v1:** strikes are %-of-spot; delta-based selection is deferred.
- **Fixtures:** the rip fixtures must yield RSI(2) overbought + spot below SMA — verify by running, fix fixtures (not gates) if they don't.
