# UNDERTOW Dip-Buy Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add UNDERTOW — a SpreadWorks paper bot that buys ATM calls on short-term pullbacks across an ETF + mega-cap universe — implementing the SleekDip spec's §8 paper-trade gate.

**Architecture:** A new single-leg `dip_buy` strategy rides the existing SpreadWorks scanner → executor → monitor → per-bot-DB loop. The executor's debit P&L path and the scanner's already-multi-ticker monitor loop are reused unchanged. New: a dip detector (`dip_buy.py`), a daily-price-history fetch on the chain provider, a universe-loop entry path in the scanner, two new exit reasons (TIME_STOP / PRE_EXPIRY), a registry entry, and frontend wiring. Dip/exit params live in registry meta — no DB schema change.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest (SQLite in-memory), Tradier REST, Vite/React SPA frontend.

**Spec:** `docs/superpowers/specs/2026-06-10-undertow-dip-buy-bot-design.md`

**Working dir:** `C:\Users\lemol\AlphaGEX`, branch `claude/undertow-dip-buy-bot`. All `pytest` commands run from `spreadworks/` (where `pytest.ini` lives). All paths below are relative to `spreadworks/`.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `backend/bots/strategies/dip_buy.py` | Indicators (RSI, SMA, reference high) + `build_dip_buy_signal` | Create |
| `backend/bots/monitor.py` | Add `dip_buy` branch to `decide_exit` (TIME_STOP, PRE_EXPIRY) | Modify |
| `backend/bots/routes_helpers.py` | `get_daily_history()` on `LiveTradierChainProvider` | Modify |
| `backend/bots/scanner.py` | `ChainProvider.get_daily_history` proto; `dip_buy` in `_build_signal`; universe entry path; pass `entry_time`/`hold_days` to `decide_exit` | Modify |
| `backend/bots/registry.py` | `undertow` registry entry (`universe` + `params` + `defaults`) | Modify |
| `frontend/src/lib/botRegistry.js` | Mirror entry + `STRATEGY_LABEL` + `BOT_THEME` | Modify |
| `tests/test_dip_buy.py` | Strategy + indicator unit tests | Create |
| `tests/test_monitor.py` | `decide_exit` dip_buy-branch tests | Modify |
| `tests/test_scanner.py` | Universe-entry + multi-day-monitor tests; extend `FakeChainProvider` | Modify |
| `tests/test_registry.py` | `undertow` registered + tables auto-create | Modify |

---

## Task 1: Indicators — RSI, SMA, closed-bar filter

**Files:**
- Create: `backend/bots/strategies/dip_buy.py`
- Test: `tests/test_dip_buy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_dip_buy.py`:

```python
"""UNDERTOW dip-buy strategy + indicator tests."""
from __future__ import annotations

from datetime import date

from backend.bots.strategies.dip_buy import (
    closed_bars, rsi, sma,
)


def _bar(d: str, high: float, close: float) -> dict:
    return {"date": d, "open": close, "high": high, "low": close, "close": close}


def test_closed_bars_drops_todays_partial_and_sorts():
    hist = [
        _bar("2026-06-10", 105, 104),  # today — partial, must be dropped
        _bar("2026-06-08", 101, 100),
        _bar("2026-06-09", 103, 102),
    ]
    bars = closed_bars(hist, date(2026, 6, 10))
    assert [b["date"] for b in bars] == ["2026-06-08", "2026-06-09"]


def test_sma_simple_average_of_last_period():
    assert sma([10, 20, 30, 40], 2) == 35.0
    assert sma([10, 20, 30, 40], 4) == 25.0


def test_sma_insufficient_returns_none():
    assert sma([10, 20], 5) is None


def test_rsi_all_gains_is_100():
    # strictly rising closes -> no losses -> RSI 100
    assert rsi([1, 2, 3, 4, 5], 2) == 100.0


def test_rsi_all_losses_is_zero():
    assert rsi([5, 4, 3, 2, 1], 2) == 0.0


def test_rsi_insufficient_returns_none():
    assert rsi([5], 2) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dip_buy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.bots.strategies.dip_buy'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/bots/strategies/dip_buy.py`:

```python
"""UNDERTOW — single-leg long-call dip-buy entry signal builder.

Buys an ATM call when an underlying pulls back >= D% from its rolling
N-day reference high, confirmed oversold (RSI) and still in an uptrend
(above its SMA). Debit strategy: entry_price = the call mid (premium
paid); max loss = full premium. Mirrors the debit plumbing of RIVER
(long_butterfly) so the executor / MTM / close paths work unchanged.

All numeric defaults are STARTING HYPOTHESES to tune from the paper
track record — the entry edge is unproven and unbacktested (see spec §0).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


def closed_bars(history: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Return daily bars strictly BEFORE `today`, sorted ascending by date.

    Drops today's partial/in-progress bar so the reference high and
    indicators are computed only from completed sessions.
    """
    bars = [b for b in history if str(b["date"]) < today.isoformat()]
    return sorted(bars, key=lambda b: str(b["date"]))


def sma(values: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` values; None if too few."""
    if len(values) < period or period <= 0:
        return None
    window = values[-period:]
    return sum(float(v) for v in window) / period


def rsi(values: list[float], period: int) -> float | None:
    """Wilder-style RSI over `period` using simple gain/loss averages.

    Needs at least `period + 1` values. Returns 0..100, or None if too few.
    All-gains -> 100, all-losses -> 0.
    """
    if len(values) < period + 1 or period <= 0:
        return None
    deltas = [float(values[i]) - float(values[i - 1]) for i in range(1, len(values))]
    window = deltas[-period:]
    gains = [d for d in window if d > 0]
    losses = [-d for d in window if d < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 4)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dip_buy.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/strategies/dip_buy.py tests/test_dip_buy.py
git commit -m "feat(undertow): dip-buy indicators (RSI, SMA, closed-bar filter)"
```

---

## Task 2: `build_dip_buy_signal` — gates, contract, sizing

**Files:**
- Modify: `backend/bots/strategies/dip_buy.py`
- Test: `tests/test_dip_buy.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dip_buy.py`:

```python
from backend.bots.strategies.dip_buy import build_dip_buy_signal, DEFAULT_PARAMS


def _uptrend_history() -> list[dict]:
    """40 closed daily bars: 36 rising closes (101..136) to seat SMA(20),
    a spike high to 150, then 3 DOWN days into a pullback so RSI(2) reads
    oversold (last closes 143 -> 141 -> 140). SMA(20) ~= 131, well below the
    150 reference high, so a dip to ~140 is a real pullback inside an uptrend.
    """
    from datetime import timedelta
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        price = 101 + i
        d = base + timedelta(days=i)
        bars.append({"date": d.isoformat(), "open": price, "high": price,
                     "low": price, "close": price})
    bars.append({"date": (base + timedelta(days=36)).isoformat(),
                 "open": 144, "high": 150, "low": 143, "close": 145})
    bars.append({"date": (base + timedelta(days=37)).isoformat(),
                 "open": 145, "high": 146, "low": 142, "close": 143})
    bars.append({"date": (base + timedelta(days=38)).isoformat(),
                 "open": 143, "high": 143, "low": 140, "close": 141})
    bars.append({"date": (base + timedelta(days=39)).isoformat(),
                 "open": 141, "high": 141, "low": 139, "close": 140})
    return bars


def _chain(spot=140.0, strikes=range(120, 161, 5), bid=4.8, ask=5.2):
    opts = []
    for s in strikes:
        opts.append({"strike": s, "type": "call", "bid": bid, "ask": ask})
        opts.append({"strike": s, "type": "put", "bid": bid, "ask": ask})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": "NVDA",
            "options": opts}


def _params(**over):
    p = dict(DEFAULT_PARAMS)
    p.update(over)
    return p


def test_qualifying_dip_builds_atm_call_signal():
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
    )
    assert sig is not None
    assert sig.ticker == "NVDA"
    legs = sig.legs()
    assert len(legs) == 1
    assert legs[0]["side"] == "long" and legs[0]["type"] == "call"
    assert legs[0]["strike"] == 140  # ATM (nearest to spot 140)
    assert sig.debit == 5.0          # mid of 4.8/5.2
    # sizing: floor(25000*0.02 / (5.0*100)) = floor(500/500) = 1
    assert sig.contracts == 1
    assert sig.max_loss == 500.0     # full premium
    assert sig.pt_target_pnl == 0.40 * 500.0   # +40% of premium
    assert sig.sl_target_pnl == 0.50 * 500.0   # -50% of premium
    assert not hasattr(sig, "credit")


def test_shallow_dip_rejected():
    diag = []
    sig = build_dip_buy_signal(
        chain=_chain(spot=149.0), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "dip_too_shallow" in diag[0]


def test_downtrend_rejected_by_sma_gate():
    diag = []
    # spot below SMA(20): use a low spot that is still a "dip" but below trend
    sig = build_dip_buy_signal(
        chain=_chain(spot=110.0), history=_uptrend_history(),
        today=date(2026, 6, 10), params=_params(), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "below_sma_downtrend" in diag[0]


def test_wide_spread_rejected():
    diag = []
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0, bid=4.0, ask=6.0),  # spread 2.0 / mid 5.0 = 40%
        history=_uptrend_history(), today=date(2026, 6, 10),
        params=_params(use_rsi_confirm=False), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "spread_too_wide" in diag[0]


def test_sizing_below_one_rejected():
    diag = []
    sig = build_dip_buy_signal(
        chain=_chain(spot=140.0, bid=49.8, ask=50.2),  # $50 option -> $5000/ct
        history=_uptrend_history(), today=date(2026, 6, 10),
        params=_params(use_rsi_confirm=False), config={"bp_pct": 0.02,
        "pt_pct": 0.40, "sl_pct": 0.50, "max_contracts": 10}, equity=25000.0,
        diag=diag,
    )
    assert sig is None
    assert "sizing_below_one" in diag[0]
```

> Note: `_uptrend_history` rises by +1/day so RSI(2) at the pullback (last delta −8) is oversold; the `spot=140` ATM case passes the RSI gate. `use_rsi_confirm=False` is set only where a test isolates a different gate.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dip_buy.py -k build_dip_buy or shallow or downtrend or spread or sizing -v`
Expected: FAIL — `ImportError: cannot import name 'build_dip_buy_signal'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/bots/strategies/dip_buy.py`:

```python
# Starting-hypothesis params (spec §2/§3). Overridden per-bot via the
# registry meta "params" dict; this is the in-code default/fallback.
DEFAULT_PARAMS: dict[str, Any] = {
    "lookback_n": 5,
    "dip_threshold": 0.03,
    "use_rsi_confirm": True,
    "rsi_period": 2,
    "rsi_max": 10,
    "use_trend_gate": True,
    "sma_period": 20,
    "max_spread_pct": 0.15,
    "min_option_price": 0.20,
    "earnings_exclude_days": 3,
    "hold_days": 2,
}


@dataclass
class DipBuySignal:
    ticker: str
    expiration: str
    strike: int
    call_mid: float
    debit: float             # per contract premium paid (== call_mid)
    contracts: int
    max_profit: float        # per contract, $ (cosmetic: PT target)
    max_loss: float          # per contract, $ (== debit * 100)
    pt_target_pnl: float     # $ total
    sl_target_pnl: float     # $ total
    # Dip context — journaled, and used by the scanner to pick the deepest dip.
    dip_pct: float
    reference_high: float
    rsi_value: float | None

    def legs(self) -> list[dict[str, Any]]:
        return [{
            "side": "long", "type": "call", "strike": self.strike,
            "expiration": self.expiration, "entry_price": self.call_mid,
        }]


def _mid(opt: dict[str, Any]) -> float:
    return (float(opt["bid"]) + float(opt["ask"])) / 2.0


def _nearest_call(chain: dict, spot: float) -> dict | None:
    calls = [o for o in chain["options"] if o["type"] == "call"]
    if not calls:
        return None
    return min(calls, key=lambda o: abs(float(o["strike"]) - spot))


def build_dip_buy_signal(
    *,
    chain: dict[str, Any],
    history: list[dict[str, Any]],
    today: date,
    params: dict[str, Any],
    config: dict[str, Any],
    equity: float,
    diag: list[str] | None = None,
) -> DipBuySignal | None:
    """Build a single-leg long-call dip-buy signal or return None.

    `diag` (optional) collects ONE rejection reason for scan_activity.reason.
    Earnings exclusion is enforced by the scanner (needs the calendar), not here.
    """
    def _reject(msg: str):
        if diag is not None:
            diag.append(msg)
        return None

    n = int(params["lookback_n"])
    sma_period = int(params["sma_period"])
    rsi_period = int(params["rsi_period"])
    need = max(n, sma_period, rsi_period + 1)

    bars = closed_bars(history, today)
    if len(bars) < need:
        return _reject(f"insufficient_history: have={len(bars)} need={need}")

    highs = [float(b["high"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    spot = float(chain["spot"])
    if spot <= 0:
        return _reject("missing_spot")

    reference_high = max(highs[-n:])
    if reference_high <= 0:
        return _reject("bad_reference_high")
    dip_pct = (reference_high - spot) / reference_high
    if dip_pct < float(params["dip_threshold"]):
        return _reject(
            f"dip_too_shallow: dip={dip_pct:.3f} min={float(params['dip_threshold']):.3f}"
        )

    rsi_value = rsi(closes, rsi_period)
    if bool(params.get("use_rsi_confirm")):
        if rsi_value is None or rsi_value >= float(params["rsi_max"]):
            return _reject(f"rsi_not_oversold: rsi={rsi_value} max={params['rsi_max']}")

    if bool(params.get("use_trend_gate")):
        sma_value = sma(closes, sma_period)
        if sma_value is None or spot <= sma_value:
            return _reject(f"below_sma_downtrend: spot={spot:.2f} sma={sma_value}")

    call = _nearest_call(chain, spot)
    if call is None:
        return _reject("no_call_strikes")
    bid = float(call["bid"] or 0)
    ask = float(call["ask"] or 0)
    mid = (bid + ask) / 2.0
    if mid < float(params["min_option_price"]):
        return _reject(f"price_too_low: mid={mid:.2f} min={params['min_option_price']}")
    if mid <= 0 or (ask - bid) / mid > float(params["max_spread_pct"]):
        spr = (ask - bid) / mid if mid > 0 else 999
        return _reject(f"spread_too_wide: spread_pct={spr:.3f} max={params['max_spread_pct']}")

    debit = round(mid, 4)
    max_loss_per = debit * 100.0
    bp_pct = float(config.get("bp_pct", 0.02))
    raw_max_contracts = int(config.get("max_contracts", 0) or 0)
    raw_contracts = int((equity * bp_pct) // max_loss_per)
    contracts = (
        max(0, raw_contracts)
        if raw_max_contracts <= 0
        else max(0, min(raw_max_contracts, raw_contracts))
    )
    if contracts < 1:
        return _reject(
            f"sizing_below_one: equity={equity:.0f} bp_pct={bp_pct} "
            f"max_loss_per={max_loss_per:.0f}"
        )

    pt_pct = float(config.get("pt_pct", 0.40))
    sl_pct = float(config.get("sl_pct", 0.50))
    pt_target = pt_pct * max_loss_per * contracts
    sl_target = sl_pct * max_loss_per * contracts
    max_profit_per = pt_pct * max_loss_per  # cosmetic headline

    return DipBuySignal(
        ticker=chain.get("ticker", "SPY"),
        expiration=chain["expiration"],
        strike=int(call["strike"]),
        call_mid=debit,
        debit=debit,
        contracts=contracts,
        max_profit=max_profit_per,
        max_loss=max_loss_per,
        pt_target_pnl=round(pt_target, 2),
        sl_target_pnl=round(sl_target, 2),
        dip_pct=round(dip_pct, 4),
        reference_high=round(reference_high, 4),
        rsi_value=rsi_value,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dip_buy.py -v`
Expected: PASS (all tests, including Task 1)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/strategies/dip_buy.py tests/test_dip_buy.py
git commit -m "feat(undertow): build_dip_buy_signal — gates, ATM call, full-premium sizing"
```

---

## Task 3: Confirm debit MTM for a single long call

**Files:**
- Test: `tests/test_dip_buy.py`

This task asserts the EXISTING executor handles a 1-leg long call correctly (no code change — `dip_buy` is absent from `CREDIT_STRATEGIES`, so `compute_mtm` uses the debit path automatically). It locks that contract in a test.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dip_buy.py`:

```python
from backend.bots.executor import compute_mtm


def test_single_long_call_mtm_is_debit_pnl():
    legs = [{"side": "long", "type": "call", "strike": 140,
             "expiration": "2026-06-22", "entry_price": 5.0}]
    # paid 5.00, now worth 7.00 -> +$200 per contract
    mtm_value, mtm_pnl = compute_mtm(
        strategy="dip_buy", legs=legs, entry_price=5.0,
        contracts=1, leg_mids=[7.0],
    )
    assert mtm_value == 7.0
    assert mtm_pnl == 200.0
    # dropped to 2.00 -> -$300
    _, loss = compute_mtm(strategy="dip_buy", legs=legs, entry_price=5.0,
                          contracts=1, leg_mids=[2.0])
    assert loss == -300.0
```

- [ ] **Step 2: Run test to verify it fails — then passes**

Run: `pytest tests/test_dip_buy.py::test_single_long_call_mtm_is_debit_pnl -v`
Expected: PASS immediately (the debit path already handles this). If it FAILS, `dip_buy` was mistakenly added to `CREDIT_STRATEGIES` — it must NOT be.

- [ ] **Step 3: Commit**

```bash
git add tests/test_dip_buy.py
git commit -m "test(undertow): lock single long-call debit MTM contract"
```

---

## Task 4: `get_daily_history` on the chain provider

**Files:**
- Modify: `backend/bots/scanner.py` (add to `ChainProvider` Protocol)
- Modify: `backend/bots/routes_helpers.py` (`LiveTradierChainProvider.get_daily_history`)
- Test: `tests/test_scanner.py` (extend `FakeChainProvider`)

- [ ] **Step 1: Extend the Protocol**

In `backend/bots/scanner.py`, modify the `ChainProvider` Protocol (currently lines ~38-40):

```python
class ChainProvider(Protocol):
    def get_chain(self, *, ticker: str, dte: int, today: date) -> dict | None: ...
    def get_leg_mids(self, *, ticker: str, legs: list[dict[str, Any]]) -> list[float]: ...
    def get_daily_history(self, *, ticker: str, days: int) -> list[dict[str, Any]]: ...
```

- [ ] **Step 2: Implement on the live provider**

In `backend/bots/routes_helpers.py`, add this method to `LiveTradierChainProvider` (after `get_leg_mids`):

```python
    def get_daily_history(self, *, ticker: str, days: int) -> list[dict[str, Any]]:
        """Daily OHLC bars for the last `days` calendar days (Tradier history).

        Returns a list of {date, open, high, low, close} ascending by date.
        Empty list on any failure — the dip detector treats that as
        insufficient_history and simply skips the ticker.
        """
        from datetime import date as _date, timedelta as _td
        end = _date.today()
        start = end - _td(days=days)
        try:
            resp = self._client.get(
                f"{TRADIER_BASE}/markets/history",
                params={"symbol": ticker, "interval": "daily",
                        "start": start.isoformat(), "end": end.isoformat()},
                headers=_headers(),
            )
            if resp.status_code != 200:
                logger.warning(f"history fetch failed {resp.status_code} for {ticker}")
                return []
            days_node = (resp.json().get("history") or {}).get("day", []) or []
            if isinstance(days_node, dict):
                days_node = [days_node]
            out = [
                {"date": d["date"], "open": d.get("open"), "high": d.get("high"),
                 "low": d.get("low"), "close": d.get("close")}
                for d in days_node if d.get("date")
            ]
            out.sort(key=lambda b: str(b["date"]))
            return out
        except Exception as e:
            logger.warning(f"history fetch error for {ticker}: {e}")
            return []
```

- [ ] **Step 3: Extend the test fake (write failing test first)**

In `tests/test_scanner.py`, find `class FakeChainProvider(ChainProvider):` (~line 27). Update its `__init__` and add `get_daily_history`:

```python
class FakeChainProvider(ChainProvider):
    def __init__(self, *, chain_0dte=None, chain_1dte=None, chain_14dte=None,
                 chain_6dte=None, chain_9dte=None, daily_history=None,
                 chains_by_ticker=None):
        # ... keep existing assignments ...
        self.leg_mid_overrides = None
        self.daily_history = daily_history or {}        # ticker -> list[bar]
        self.chains_by_ticker = chains_by_ticker or {}  # ticker -> chain dict

    def get_daily_history(self, *, ticker, days):
        return list(self.daily_history.get(ticker, []))
```

Add a focused test:

```python
def test_fake_provider_returns_daily_history():
    p = FakeChainProvider(daily_history={"NVDA": [{"date": "2026-06-09",
        "open": 1, "high": 2, "low": 1, "close": 2}]})
    bars = p.get_daily_history(ticker="NVDA", days=40)
    assert len(bars) == 1 and bars[0]["date"] == "2026-06-09"
    assert p.get_daily_history(ticker="MSFT", days=40) == []
```

> Keep the existing `__init__` body intact — only ADD the two new kwargs/attrs and the method. The `# ... keep existing assignments ...` line is a placeholder for the lines already there; do not delete them.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS (existing tests unaffected + new `test_fake_provider_returns_daily_history`)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py backend/bots/routes_helpers.py tests/test_scanner.py
git commit -m "feat(undertow): get_daily_history on chain provider (Tradier daily bars)"
```

---

## Task 5: `decide_exit` — TIME_STOP + PRE_EXPIRY for dip_buy

**Files:**
- Modify: `backend/bots/monitor.py`
- Test: `tests/test_monitor.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_monitor.py`:

```python
from datetime import date, datetime, time
from backend.bots.monitor import decide_exit


def _call(now, *, entry, hold_days=2, exp="2026-06-22", mtm=0.0):
    return decide_exit(
        strategy="dip_buy", mtm_pnl=mtm, pt_target_pnl=200.0,
        sl_target_pnl=250.0, now_ct=now, front_expiration=date.fromisoformat(exp),
        eod_close_ct=time(14, 45), event_blackout=False,
        entry_time=entry, hold_days=hold_days,
    )


def test_dip_buy_pt_fires():
    d = _call(datetime(2026, 6, 10, 10, 0), entry=datetime(2026, 6, 10, 9, 0), mtm=250.0)
    assert d.should_close and d.reason == "PT"


def test_dip_buy_sl_fires():
    d = _call(datetime(2026, 6, 10, 10, 0), entry=datetime(2026, 6, 10, 9, 0), mtm=-300.0)
    assert d.should_close and d.reason == "SL"


def test_dip_buy_time_stop_fires_after_hold_days():
    # entered 2026-06-08, now 2026-06-10 -> 2 calendar days held >= hold_days 2
    d = _call(datetime(2026, 6, 10, 9, 0), entry=datetime(2026, 6, 8, 9, 0))
    assert d.should_close and d.reason == "TIME_STOP"


def test_dip_buy_holds_before_time_stop():
    d = _call(datetime(2026, 6, 9, 9, 0), entry=datetime(2026, 6, 8, 9, 0))
    assert not d.should_close


def test_dip_buy_pre_expiry_force_close():
    d = _call(datetime(2026, 6, 22, 9, 0), entry=datetime(2026, 6, 21, 9, 0),
              hold_days=99, exp="2026-06-22")
    assert d.should_close and d.reason == "PRE_EXPIRY"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitor.py -k dip_buy -v`
Expected: FAIL — `decide_exit() got an unexpected keyword argument 'entry_time'`

- [ ] **Step 3: Implement**

In `backend/bots/monitor.py`, change the `decide_exit` signature to add two optional params, and add the `dip_buy` branch. Replace the whole function:

```python
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
    entry_time: datetime | None = None,
    hold_days: int | None = None,
) -> ExitDecision:
    if event_blackout:
        return ExitDecision(True, "EVENT_HALT")

    if mtm_pnl >= pt_target_pnl:
        return ExitDecision(True, "PT")
    if mtm_pnl <= -abs(sl_target_pnl):
        return ExitDecision(True, "SL")

    if strategy == "dip_buy":
        # Multi-day long-call hold: no same-day EOD close. Exit on a hard
        # time-stop (kills post-peak decay) and never hold into expiry.
        if entry_time is not None and hold_days is not None:
            held_days = (now_ct.date() - entry_time.date()).days
            if held_days >= int(hold_days):
                return ExitDecision(True, "TIME_STOP")
        if now_ct.date() >= front_expiration:
            return ExitDecision(True, "PRE_EXPIRY")
        return ExitDecision(False, None)

    eod = eod_close_time_for_strategy(strategy, eod_close_ct)
    if strategy in ("iron_butterfly", "long_butterfly"):
        if now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")
    else:
        if now_ct.date() == front_expiration and now_ct.timetz().replace(tzinfo=None) >= eod:
            return ExitDecision(True, "EOD")

    return ExitDecision(False, None)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_monitor.py -v`
Expected: PASS (new dip_buy tests + all existing monitor tests)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/monitor.py tests/test_monitor.py
git commit -m "feat(undertow): decide_exit dip_buy branch — TIME_STOP + PRE_EXPIRY"
```

---

## Task 6: Register UNDERTOW (backend + frontend mirror)

**Files:**
- Modify: `backend/bots/registry.py`
- Modify: `frontend/src/lib/botRegistry.js`
- Test: `tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_registry.py`:

```python
def test_undertow_registered():
    from backend.bots.registry import get_bot
    meta = get_bot("undertow")
    assert meta["display"] == "UNDERTOW"
    assert meta["strategy"] == "dip_buy"
    assert "SPY" in meta["universe"] and "NVDA" in meta["universe"]
    assert meta["params"]["lookback_n"] == 5
    assert meta["defaults"]["enabled"] is False
    assert meta["defaults"]["max_concurrent_positions"] == 5


def test_undertow_tables_autocreate(db_session):
    # create_bot_tables ran in the fixture; the config row must be seeded.
    from sqlalchemy import text
    eng = db_session.get_bind()
    row = eng.connect().execute(
        text("SELECT enabled, bp_pct FROM undertow_config WHERE id=1")
    ).mappings().first()
    assert row is not None
    assert bool(row["enabled"]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_registry.py -k undertow -v`
Expected: FAIL — `KeyError: "Unknown bot: 'undertow'"`

- [ ] **Step 3: Add the registry entry**

In `backend/bots/registry.py`, add this entry to `BOT_REGISTRY` (after `meadow`, before the closing `}`):

```python
    # UNDERTOW — single-leg long-call dip-buyer across an ETF + mega-cap
    # universe. Buys an ATM ~10-DTE call when a name pulls back >= 3% from its
    # 5-day high, oversold (RSI(2)<10) and still above its 20-day SMA. Exits
    # all-or-nothing: PT +40% / SL -50% of premium / 2-day time-stop / never
    # hold to expiry. Paper-only, ships disabled. dip/exit params live here in
    # `params` (swept later); only universal knobs sit in undertow_config.
    "undertow": {
        "display": "UNDERTOW",
        "strategy": "dip_buy",
        "ticker": "SPY",  # nominal; real scanning iterates `universe`
        "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
        "front_dte": 10,
        "back_dte": None,
        "params": {
            "lookback_n": 5,
            "dip_threshold": 0.03,
            "use_rsi_confirm": True,
            "rsi_period": 2,
            "rsi_max": 10,
            "use_trend_gate": True,
            "sma_period": 20,
            "max_spread_pct": 0.15,
            "min_option_price": 0.20,
            "earnings_exclude_days": 3,
            "hold_days": 2,
        },
        "defaults": {
            "starting_capital": 25000.0,
            "enabled": False,
            "max_contracts": 10,
            "bp_pct": 0.02,
            "sd_mult": 1.0,
            "pt_pct": 0.40,
            "sl_pct": 0.50,
            "entry_start_ct": "08:35",
            "entry_end_ct": "14:30",
            "eod_close_ct": "14:45",
            "discord_alerts": False,
            "delta_skew": 0,
            "use_gex_walls": False,
            "max_concurrent_positions": 5,
        },
    },
```

- [ ] **Step 4: Mirror in the frontend registry**

In `frontend/src/lib/botRegistry.js`:

Add to `BOT_REGISTRY`:
```javascript
  undertow: { display: 'UNDERTOW', strategy: 'dip_buy', ticker: 'multi', version: 'v1.0' },
```

Add to `STRATEGY_LABEL`:
```javascript
  dip_buy:               'Dip-Buy Call',
```

Add to `BOT_THEME` (deep-water indigo, distinct from the existing palette):
```javascript
  undertow: {
    glyph:       'wave',                       // UNDERTOW = a pulling undercurrent
    primary:     '#818cf8',                    // indigo-400
    primarySoft: 'rgba(129,140,248,0.10)',
    primaryRing: 'rgba(129,140,248,0.30)',
    glow:        'rgba(129,140,248,0.18)',
    accentBg:    'linear-gradient(135deg, rgba(129,140,248,0.22) 0%, rgba(129,140,248,0.03) 100%)',
  },
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_registry.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/bots/registry.py frontend/src/lib/botRegistry.js tests/test_registry.py
git commit -m "feat(undertow): register bot (backend registry + frontend mirror)"
```

---

## Task 7: Scanner — universe entry path + dip_buy build + multi-day monitor

**Files:**
- Modify: `backend/bots/scanner.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_scanner.py` (reuse the `_uptrend_history`/`_chain` helpers — import them or redefine locally):

```python
from datetime import date, datetime, timedelta


def _undertow_history():
    # Same shape as test_dip_buy._uptrend_history: rising trend, spike high to
    # 150, then 3 down days so RSI(2) is oversold and SMA(20) ~= 131.
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        price = 101 + i
        d = base + timedelta(days=i)
        bars.append({"date": d.isoformat(), "open": price, "high": price,
                     "low": price, "close": price})
    bars.append({"date": (base + timedelta(days=36)).isoformat(),
                 "open": 144, "high": 150, "low": 143, "close": 145})
    bars.append({"date": (base + timedelta(days=37)).isoformat(),
                 "open": 145, "high": 146, "low": 142, "close": 143})
    bars.append({"date": (base + timedelta(days=38)).isoformat(),
                 "open": 143, "high": 143, "low": 140, "close": 141})
    bars.append({"date": (base + timedelta(days=39)).isoformat(),
                 "open": 141, "high": 141, "low": 139, "close": 140})
    return bars


def _undertow_chain(ticker, spot):
    opts = []
    for s in range(120, 161, 5):
        opts.append({"strike": s, "type": "call", "bid": 4.8, "ask": 5.2})
        opts.append({"strike": s, "type": "put", "bid": 4.8, "ask": 5.2})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker,
            "options": opts}


def _enable_undertow(engine):
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("UPDATE undertow_config SET enabled=1"))


def test_undertow_opens_deepest_dip(db_session):
    from backend.bots.scanner import run_scan_cycle
    # FakeChainProvider is defined in this test module (see top of file).
    eng = db_session.get_bind()
    _enable_undertow(eng)
    # NVDA dips to 140 (6.7%), AAPL to 145 (3.3%) — NVDA is deeper.
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _undertow_chain("NVDA", 140.0),
                          "AAPL": _undertow_chain("AAPL", 145.0)},
        daily_history={"NVDA": _undertow_history(), "AAPL": _undertow_history()},
    )
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    res = run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                         chain_provider=provider, event_blackout=False)
    assert res["outcome"] == "TRADE"
    from backend.bots.executor import list_open_positions
    opens = list_open_positions(eng, "undertow")
    assert len(opens) == 1
    assert opens[0]["ticker"] == "NVDA"


def test_undertow_skips_held_ticker_and_respects_concurrent_cap(db_session):
    from backend.bots.scanner import run_scan_cycle
    eng = db_session.get_bind()
    _enable_undertow(eng)
    from sqlalchemy import text
    with eng.begin() as conn:
        conn.execute(text("UPDATE undertow_config SET max_concurrent_positions=1"))
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _undertow_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    # second scan: cap=1 already reached -> blocked, still 1 open
    res2 = run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                          chain_provider=provider, event_blackout=False)
    from backend.bots.executor import list_open_positions
    assert len(list_open_positions(eng, "undertow")) == 1
    assert res2["outcome"] in ("BLOCKED_MAX_CONCURRENT", "MONITOR")
```

> Note: `FakeChainProvider.get_chain` must return the per-ticker chain when `chains_by_ticker` is set. Update it in Step 3 alongside the scanner.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scanner.py -k undertow -v`
Expected: FAIL — `NO_TRADE`/`KeyError`/`no signal` (no universe path yet)

- [ ] **Step 3: Implement**

**3a.** Update `FakeChainProvider.get_chain` in `tests/test_scanner.py` to honor `chains_by_ticker`:

```python
    def get_chain(self, *, ticker, dte, today):
        if self.chains_by_ticker:
            return self.chains_by_ticker.get(ticker)
        # ... keep existing dte-based fixture lookup for the other bots ...
```

**3b.** In `backend/bots/scanner.py`, add the `dip_buy` import at the top:

```python
from .strategies.dip_buy import build_dip_buy_signal, DEFAULT_PARAMS
```

**3c.** Add a `dip_buy` branch in `_build_signal` (before the DC/DD `front`/`back` block):

```python
    if strategy == "dip_buy":
        params = {**DEFAULT_PARAMS, **(diag_params or {})}
        chain = chain_provider.get_chain(ticker=ticker, dte=front_dte, today=today)
        if chain is None:
            if diag is not None:
                diag.append(f"chain_unavailable: ticker={ticker} dte={front_dte}")
            return None, None
        lookback_days = max(int(params["sma_period"]), int(params["lookback_n"])) + 25
        history = chain_provider.get_daily_history(ticker=ticker, days=lookback_days)
        if not history:
            if diag is not None:
                diag.append(f"history_unavailable: ticker={ticker}")
            return None, None
        sig = build_dip_buy_signal(
            chain=chain, history=history, today=today, params=params,
            config=config, equity=equity, diag=diag,
        )
        return sig, chain
```

Add a `diag_params` keyword to `_build_signal`'s signature (default `None`) so the per-bot `params` dict can flow in:

```python
def _build_signal(*, bot: str, strategy: str, chain_provider: ChainProvider,
                  config: dict, equity: float, today: date,
                  ticker: str, front_dte: int, back_dte: int | None,
                  diag: list[str] | None = None,
                  diag_params: dict | None = None):
```

**3d.** Add the universe entry path. In `_evaluate_entry`, after the `max_concurrent` gate and BEFORE the `allow_stacking` one-per-day block, insert:

```python
    universe = meta.get("universe")
    if universe and meta["strategy"] == "dip_buy":
        return _evaluate_universe_entry(
            engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
            chain_provider=chain_provider, opens=opens,
        )
```

Add `opens` to `_evaluate_entry`'s parameters (and pass it from `run_scan_cycle`):

```python
def _evaluate_entry(
    *, engine: Engine, bot: str, meta: dict, cfg: dict, now_ct: datetime,
    chain_provider: ChainProvider, event_blackout: bool, allow_stacking: bool,
    open_count: int, opens: list[dict[str, Any]],
) -> dict[str, Any]:
```

Then add the new function (place it above `_evaluate_entry`):

```python
def _evaluate_universe_entry(
    *, engine: Engine, bot: str, meta: dict, cfg: dict, now_ct: datetime,
    chain_provider: ChainProvider, opens: list[dict[str, Any]],
) -> dict[str, Any]:
    """Scan the bot's universe; open ONE new position on the deepest qualifying
    dip. Skips tickers already held open. Earnings-window names are excluded.
    Window / concurrent-cap gates were already checked by the caller."""
    held = {p["ticker"] for p in opens}
    params = dict(meta.get("params") or {})
    equity = account_equity(engine, bot)
    candidates: list[tuple[float, Any]] = []
    last_reason: str | None = None
    for ticker in meta["universe"]:
        if ticker in held:
            continue
        if _within_earnings_window(ticker, now_ct.date(),
                                   int(params.get("earnings_exclude_days", 0) or 0)):
            last_reason = f"earnings_excluded: {ticker}"
            continue
        diag: list[str] = []
        signal, _chain = _build_signal(
            bot=bot, strategy="dip_buy", chain_provider=chain_provider,
            config=cfg, equity=equity, today=now_ct.date(), ticker=ticker,
            front_dte=meta["front_dte"], back_dte=None, diag=diag,
            diag_params=params,
        )
        if signal is None:
            last_reason = diag[0] if diag else f"no_signal: {ticker}"
            continue
        candidates.append((signal.dip_pct, signal))

    if not candidates:
        return {"outcome": "NO_TRADE", "reason": last_reason or "no universe signal"}

    # Deepest dip wins.
    candidates.sort(key=lambda c: c[0], reverse=True)
    signal = candidates[0][1]
    pid = open_position(engine, bot, "dip_buy", signal, now_ct)
    return {"outcome": "TRADE", "reason": "OPENED", "position_id": pid}


def _within_earnings_window(ticker: str, today: date, exclude_days: int) -> bool:
    """True if `ticker` has earnings within `exclude_days` of `today`.

    Uses the existing earnings_calendar module; on ANY failure returns False
    (fail-open) so a calendar outage never blocks all entries."""
    if exclude_days <= 0:
        return False
    try:
        from .. import earnings_calendar  # backend/earnings_calendar.py
        nxt = earnings_calendar.next_earnings_date(ticker)  # may be None
        if nxt is None:
            return False
        return 0 <= (nxt - today).days <= exclude_days
    except Exception:
        return False
```

> Implementation note: `earnings_calendar` may not expose `next_earnings_date`. During Task 7, open `backend/earnings_calendar.py` and use whatever lookup it provides; if it has no per-ticker single-name lookup, keep `_within_earnings_window` returning `False` (earnings exclusion deferred) and leave a `# TODO` referencing spec §3. Do NOT block all entries on a missing calendar.

**3e.** Wire the universe entry trigger + monitor params in `run_scan_cycle`:

- Change the entry-trigger condition so universe bots evaluate every scan:

```python
        is_universe = bool(meta.get("universe"))
        entry_result: dict[str, Any] | None = None
        if (not opens) or allow_stacking or is_universe:
            entry_result = _evaluate_entry(
                engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
                chain_provider=chain_provider, event_blackout=event_blackout,
                allow_stacking=allow_stacking, open_count=len(opens), opens=opens,
            )
```

- In the monitor loop, pass `entry_time` + `hold_days` to `decide_exit` for dip_buy. Replace the `d = decide_exit(...)` call with:

```python
            dip_hold_days = None
            dip_entry_time = None
            if pos["strategy"] == "dip_buy":
                dip_hold_days = int((meta.get("params") or {}).get("hold_days", 2))
                dip_entry_time = pos["entry_time"] if isinstance(pos["entry_time"], datetime) \
                    else datetime.fromisoformat(str(pos["entry_time"]))

            d = decide_exit(
                strategy=pos["strategy"], mtm_pnl=mtm_pnl,
                pt_target_pnl=pt_target, sl_target_pnl=float(pos["sl_target_pnl"]),
                now_ct=now_ct, front_expiration=front_exp,
                eod_close_ct=_parse_time(cfg["eod_close_ct"]),
                event_blackout=event_blackout,
                entry_time=dip_entry_time, hold_days=dip_hold_days,
            )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS (all existing + new undertow tests)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py tests/test_scanner.py
git commit -m "feat(undertow): scanner universe entry path + dip_buy build + multi-day monitor"
```

---

## Task 8: Journal dip context into scan_activity + position notes

**Files:**
- Modify: `backend/bots/scanner.py`
- Modify: `backend/bots/executor.py`
- Test: `tests/test_scanner.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_scanner.py`:

```python
def test_undertow_journals_dip_context(db_session):
    from backend.bots.scanner import run_scan_cycle
    import json as _json
    eng = db_session.get_bind()
    _enable_undertow(eng)
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _undertow_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)
    run_scan_cycle(engine=eng, bot="undertow", now_ct=now,
                   chain_provider=provider, event_blackout=False)
    from backend.bots.executor import list_open_positions
    pos = list_open_positions(eng, "undertow")[0]
    notes = _json.loads(pos["notes"])
    assert notes["ticker"] == "NVDA"
    assert notes["dip_pct"] > 0.03
    assert notes["reference_high"] == 150.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scanner.py::test_undertow_journals_dip_context -v`
Expected: FAIL — `notes` is `None` / not JSON.

- [ ] **Step 3: Implement**

**3a.** In `backend/bots/executor.py`, give `open_position` an optional `notes` param that writes to the existing `notes` column:

Change the signature:
```python
def open_position(
    engine: Engine,
    bot: str,
    strategy: str,
    signal: Any,
    now: datetime,
    notes: str | None = None,
) -> str:
```

In the INSERT, add the `notes` column + bind. Change the column list to end with `account_label, notes` and `VALUES (... 'paper', :notes)`, and add `"notes": notes` to the params dict. (The `notes` column already exists in `_POSITIONS_DDL`.)

**3b.** In `backend/bots/scanner.py` `_evaluate_universe_entry`, build and pass notes when opening. `scanner.py` already imports `json` at module level — reuse it. Replace the existing `pid = open_position(engine, bot, "dip_buy", signal, now_ct)` line with:

```python
    notes = json.dumps({
        "ticker": signal.ticker, "dip_pct": signal.dip_pct,
        "reference_high": signal.reference_high, "rsi": signal.rsi_value,
        "strike": signal.strike, "expiration": signal.expiration,
        "debit": signal.debit,
    })
    pid = open_position(engine, bot, "dip_buy", signal, now_ct, notes=notes)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_scanner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py backend/bots/executor.py tests/test_scanner.py
git commit -m "feat(undertow): journal dip context into position notes"
```

---

## Task 9: Full backend suite + frontend build verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole SpreadWorks backend suite**

Run: `pytest -v 2>&1 | tee /tmp/undertow_pytest.txt`
Expected: All pass. No existing test regressed (BREEZE/TIDE/DRIFT/RIVER/FLOW/MEADOW behavior unchanged — confirm the `iron_*`/`double_*` tests still pass).

- [ ] **Step 2: Frontend builds**

Run: `cd frontend && npm run build 2>&1 | tee /tmp/undertow_fe_build.txt`
Expected: Build succeeds. UNDERTOW appears in the bot list (Vite SPA reads `BOT_REGISTRY`). If the deployed Render service serves a committed `dist/` (per memory: SpreadWorks dist-drift), commit the rebuilt `frontend/dist/` too.

- [ ] **Step 3: Verify the dashboard renders for the new bot**

Run: `cd frontend && npm run dev` and open `/undertow` (or the app's bot selector). Confirm the shared `BotDashboard` renders UNDERTOW with the indigo theme, an empty positions table, and the dip-buy strategy label. (Manual check; no automated assertion.)

- [ ] **Step 4: Commit any dist rebuild**

```bash
git add frontend/dist 2>/dev/null || true
git commit -m "build(undertow): rebuild frontend dist with UNDERTOW registered" || echo "no dist to commit"
```

---

## Task 10: Smoke-test a live scan (paper, disabled by default)

**Files:** none (verification only)

- [ ] **Step 1: Confirm the bot is wired into the scan loop**

UNDERTOW is auto-included: `scan_bots_tick` iterates `list_bots()`, which now contains `undertow`. No scheduler change is needed. Confirm by reading `backend/__init__.py` `scan_bots_tick` — it must not hardcode bot names.

- [ ] **Step 2: Force one scan via the API (after deploy) to validate live data**

UNDERTOW ships `enabled: False`, so it will log `BLOCKED_DISABLED` on the normal loop. To validate the live Tradier path WITHOUT enabling it, temporarily enable it on a paper deploy and hit the force-trade route:

```
POST /api/spreadworks/bots/undertow/toggle      # enable
POST /api/spreadworks/bots/undertow/force-trade  # one immediate scan
GET  /api/spreadworks/bots/undertow/scan-activity # inspect outcome + reason
POST /api/spreadworks/bots/undertow/toggle      # disable again
```

Expected: a `TRADE` (if a universe name is dipping) or a `NO_TRADE` with a specific reason (e.g. `dip_too_shallow: ...`, `history_unavailable: ...`). A `history_unavailable` for every ticker means the Tradier `/markets/history` call needs debugging (check `TRADIER_TOKEN`, symbol, date range).

- [ ] **Step 3: Leave it disabled**

Confirm `GET /api/spreadworks/bots/undertow/status` shows `enabled: false` before finishing. Per spec §0 and the SpreadWorks paper-only invariant, UNDERTOW stays OFF until the operator opts in.

---

## Self-review notes (carried into execution)

- **No DB migration:** `undertow` in `BOT_REGISTRY` makes `create_bot_tables` build all 5 tables and seed config on startup. The `notes` column already exists in `_POSITIONS_DDL`.
- **Debit invariant:** `dip_buy` must stay OUT of `CREDIT_STRATEGIES` (Task 3 locks this). The signal exposes `.debit`, never `.credit`, so the scanner's discord-open `entry_price` resolution and the executor both take the debit path.
- **Honest-framing reminders (spec §0):** underlying-dip interpretation only; mid fills (optimistic); overnight gap risk (multi-day hold, RTH-only monitoring); entry edge unproven/unbacktested. Do not add language anywhere implying validated edge.
- **v2 deferred:** scale-out / trailing runner, put track, option-price-dip `D`, ADV/OI liquidity floors. Do not build these now.
