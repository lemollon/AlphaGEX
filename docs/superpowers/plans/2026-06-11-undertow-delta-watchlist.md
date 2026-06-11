# UNDERTOW / DELTA Universe Watchlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only universe watchlist to the `/undertow` and `/delta` dashboards showing, per tracked stock, the live signal status and — when a setup is firing — the exact candidate spread (strikes, expiration, debit/credit, sizing) the bot would open.

**Architecture:** Extract the scanner's per-ticker evaluation into one shared helper (`_evaluate_ticker`) so the live entry path and the watchlist share identical logic (no drift). Add a read-only collector (`evaluate_universe_watchlist`), a `GET /api/spreadworks/bots/{bot}/watchlist` endpoint, and a `WatchlistPanel` React component rendered only for the two universe bots.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / pytest (backend); React + Vite + Tailwind (frontend, committed `dist/` served by Render).

Spec: `docs/superpowers/specs/2026-06-11-undertow-delta-watchlist-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `spreadworks/backend/bots/strategies/setups.py` | + `compute_indicators()` pure helper (dip%/rip%/rsi/sma for display, reusing dip_buy math) |
| `spreadworks/backend/bots/scanner.py` | + `TickerEval`, `_evaluate_ticker`, `evaluate_universe_watchlist`, `ticker_eval_to_row`; rewrite `_evaluate_universe_entry` to reuse `_evaluate_ticker` |
| `spreadworks/backend/routes_bots.py` | + `GET /{bot}/watchlist` endpoint |
| `spreadworks/frontend/src/lib/botApi.js` | + `watchlist()` helper |
| `spreadworks/frontend/src/components/bots/WatchlistPanel.jsx` | new panel component |
| `spreadworks/frontend/src/pages/BotDashboard.jsx` | render `WatchlistPanel` for universe bots |
| `spreadworks/tests/test_setups.py` | tests for `compute_indicators` |
| `spreadworks/tests/test_scanner.py` | tests for `_evaluate_ticker`, `evaluate_universe_watchlist`, `ticker_eval_to_row` |
| `spreadworks/tests/test_routes_bots.py` | endpoint 200/400 tests |
| `spreadworks/frontend/dist/*` | rebuilt bundle (Render serves committed dist) |

**Working dir for all Python commands:** `spreadworks/` (so `backend...` imports resolve and pytest finds tests). Run from `C:\Users\lemol\AlphaGEX\spreadworks`.

---

## Task 1: `compute_indicators` helper in setups.py

So WATCHING rows (no setup) can still display dip%/rip%/rsi/sma. Reuses the same `closed_bars/sma/rsi` math `detect_setup` uses — single source of truth. `detect_setup` is **not** modified (preserves live behavior + existing tests).

**Files:**
- Modify: `spreadworks/backend/bots/strategies/setups.py`
- Test: `spreadworks/tests/test_setups.py`

- [ ] **Step 1: Write the failing test**

Add to `spreadworks/tests/test_setups.py`:

```python
def test_compute_indicators_returns_dip_rip_rsi_sma():
    from datetime import date, timedelta
    from backend.bots.strategies.setups import compute_indicators, DEFAULT_SETUP_PARAMS
    # 36 flat-rising days then a spike-high and 3 down days (same shape the
    # scanner tests use): ref_high=150, spot below it -> positive dip_pct.
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        p = 101 + i
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": p, "high": p, "low": p, "close": p})
    bars += [
        {"date": (base + timedelta(days=36)).isoformat(), "open": 144, "high": 150, "low": 143, "close": 145},
        {"date": (base + timedelta(days=37)).isoformat(), "open": 145, "high": 146, "low": 142, "close": 143},
        {"date": (base + timedelta(days=38)).isoformat(), "open": 143, "high": 143, "low": 140, "close": 141},
        {"date": (base + timedelta(days=39)).isoformat(), "open": 141, "high": 141, "low": 139, "close": 140},
    ]
    ind = compute_indicators(spot=140.0, history=bars,
                             today=date(2026, 6, 10),
                             params=DEFAULT_SETUP_PARAMS)
    assert ind is not None
    assert ind["ref_high"] == 150.0
    assert round(ind["dip_pct"], 4) == round((150.0 - 140.0) / 150.0, 4)
    assert ind["rip_pct"] == 0.0  # spot is below ref_high, no rip
    assert ind["rsi"] is not None
    assert ind["sma"] is not None


def test_compute_indicators_insufficient_history_returns_none():
    from datetime import date
    from backend.bots.strategies.setups import compute_indicators, DEFAULT_SETUP_PARAMS
    assert compute_indicators(spot=100.0, history=[], today=date(2026, 6, 10),
                              params=DEFAULT_SETUP_PARAMS) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_setups.py::test_compute_indicators_returns_dip_rip_rsi_sma -v`
Expected: FAIL with `ImportError: cannot import name 'compute_indicators'`

- [ ] **Step 3: Add the implementation**

In `spreadworks/backend/bots/strategies/setups.py`, after the `detect_setup` function, add:

```python
def compute_indicators(*, spot: float, history: list[dict[str, Any]], today: date,
                       params: dict[str, Any]) -> dict[str, Any] | None:
    """Display-only indicator snapshot, computed with the SAME math detect_setup
    uses. Returns {ref_high, ref_low, dip_pct, rip_pct, rsi, sma} or None when
    there are not enough closed bars. Pure: no side effects, never raises on
    normal input. detect_setup is unchanged — this exists so WATCHING rows
    (setup rejected) can still show the numbers."""
    n = int(params["lookback_n"]); sma_period = int(params["sma_period"])
    rsi_period = int(params["rsi_period"])
    need = max(n, sma_period, rsi_period + 1)
    bars = closed_bars(history, today)
    if len(bars) < need or spot <= 0:
        return None
    highs = [float(b["high"]) for b in bars]
    lows = [float(b["low"]) for b in bars]
    closes = [float(b["close"]) for b in bars]
    ref_high = max(highs[-n:]); ref_low = min(lows[-n:])
    dip_pct = (ref_high - spot) / ref_high if ref_high > 0 else 0.0
    rip_pct = (spot - ref_low) / ref_low if ref_low > 0 else 0.0
    return {
        "ref_high": round(ref_high, 4),
        "ref_low": round(ref_low, 4),
        "dip_pct": round(max(0.0, dip_pct), 4),
        "rip_pct": round(max(0.0, rip_pct), 4),
        "rsi": rsi(closes, rsi_period),
        "sma": sma(closes, sma_period),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_setups.py -v`
Expected: PASS (all, including the two new tests)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/strategies/setups.py tests/test_setups.py
git commit -m "feat(spreads): add compute_indicators display helper for watchlist"
```

---

## Task 2: Extract `_evaluate_ticker` + `TickerEval`, rewrite `_evaluate_universe_entry`

Refactor only — behavior must stay identical. The existing universe-entry scanner tests are the safety net.

**Files:**
- Modify: `spreadworks/backend/bots/scanner.py:226-295` (the `_evaluate_universe_entry` function)
- Test: `spreadworks/tests/test_scanner.py`

- [ ] **Step 1: Write the failing test (the new shared helper)**

Add to `spreadworks/tests/test_scanner.py` (the `_spread_chain`, `_undertow_history`, `FakeChainProvider`, `CT` helpers already exist in this file):

```python
def test_evaluate_ticker_signal_and_held_and_watching():
    from datetime import datetime
    from backend.bots.scanner import _evaluate_ticker
    from backend.bots.registry import get_bot
    meta = get_bot("undertow")
    cfg = dict(meta["defaults"])
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)

    # SIGNAL: NVDA dips to 140 from a 150 ref-high, oversold, above SMA(~131).
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0)},
        daily_history={"NVDA": _undertow_history()},
    )
    sig_eval = _evaluate_ticker(engine=None, bot="undertow", meta=meta, cfg=cfg,
                                now_ct=now, chain_provider=provider,
                                ticker="NVDA", held=False, equity=25000.0)
    assert sig_eval.signal is not None
    assert sig_eval.setup.direction == "bullish"
    assert sig_eval.indicators is not None and sig_eval.indicators["dip_pct"] > 0

    # HELD: short-circuits, no chain fetch, no signal.
    held_eval = _evaluate_ticker(engine=None, bot="undertow", meta=meta, cfg=cfg,
                                 now_ct=now, chain_provider=provider,
                                 ticker="NVDA", held=True, equity=25000.0)
    assert held_eval.held is True
    assert held_eval.signal is None and held_eval.setup is None

    # WATCHING: a name with no chain available -> reason, no signal.
    empty = FakeChainProvider(chains_by_ticker={}, daily_history={})
    watch_eval = _evaluate_ticker(engine=None, bot="undertow", meta=meta, cfg=cfg,
                                  now_ct=now, chain_provider=empty,
                                  ticker="SPY", held=False, equity=25000.0)
    assert watch_eval.signal is None
    assert "chain_unavailable" in (watch_eval.reason or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scanner.py::test_evaluate_ticker_signal_and_held_and_watching -v`
Expected: FAIL with `ImportError: cannot import name '_evaluate_ticker'`

- [ ] **Step 3: Add `TickerEval` + `_evaluate_ticker` and rewrite `_evaluate_universe_entry`**

In `spreadworks/backend/bots/scanner.py`, add the import for `compute_indicators` to the existing setups import line:

```python
from .strategies.setups import detect_setup, compute_indicators, DEFAULT_SETUP_PARAMS
```

Add the `Setup`/`VerticalSignal` types to the typing imports near the top (after the existing strategy imports), and a `dataclass`/`field` import. At the top of the file the line `from dataclasses import dataclass` already exists. Add this dataclass just above `_evaluate_universe_entry`:

```python
@dataclass
class TickerEval:
    """One universe name's evaluation. `signal is not None` means a spread is
    currently buildable (would be opened if it's the deepest). Shared by the
    live entry path and the read-only watchlist so they cannot drift."""
    ticker: str
    held: bool
    spot: float | None = None
    chain_expiration: str | None = None
    setup: Any = None          # strategies.setups.Setup | None
    signal: Any = None         # strategies.vertical_spread.VerticalSignal | None
    indicators: dict | None = None
    reason: str | None = None


def _evaluate_ticker(*, engine, bot: str, meta: dict, cfg: dict, now_ct: datetime,
                     chain_provider: ChainProvider, ticker: str, held: bool,
                     equity: float) -> TickerEval:
    """Evaluate ONE universe name. Held names short-circuit WITHOUT fetching
    (preserving the live scanner's skip-held behavior and API cost). For
    non-held names: earnings gate -> chain -> history -> detect_setup ->
    build_vertical_signal, capturing the first rejection reason for display."""
    if held:
        return TickerEval(ticker=ticker, held=True, reason="held")

    params = dict(meta.get("params") or {})
    if _within_earnings_window(ticker, now_ct, int(params.get("earnings_exclude_days", 0) or 0)):
        return TickerEval(ticker=ticker, held=False, reason=f"earnings_excluded: {ticker}")

    chain = chain_provider.get_chain(ticker=ticker, dte=meta["front_dte"], today=now_ct.date())
    if chain is None:
        return TickerEval(ticker=ticker, held=False, reason=f"chain_unavailable: {ticker}")
    spot = float(chain["spot"])
    exp = chain.get("expiration")

    lookback = max(int(params.get("sma_period", 20)), int(params.get("lookback_n", 5))) + 25
    history = chain_provider.get_daily_history(ticker=ticker, days=lookback)
    if not history:
        return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                          reason=f"history_unavailable: {ticker}")

    merged = {**DEFAULT_SETUP_PARAMS, **params}
    indicators = compute_indicators(spot=spot, history=history, today=now_ct.date(), params=merged)

    sdiag: list[str] = []
    setup = detect_setup(spot=spot, history=history, today=now_ct.date(),
                         params=merged, diag=sdiag)
    if setup is None:
        return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                          indicators=indicators,
                          reason=sdiag[0] if sdiag else f"no_setup: {ticker}")

    kind = _vertical_kind(meta.get("vertical_mode", "debit"), setup.direction)
    vdiag: list[str] = []
    signal = build_vertical_signal(kind=kind, chain=chain, config=cfg, equity=equity,
                                   params={**DEFAULT_VERTICAL_PARAMS, **params}, diag=vdiag)
    if signal is None:
        return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                          setup=setup, indicators=indicators,
                          reason=vdiag[0] if vdiag else f"no_signal: {ticker}")

    return TickerEval(ticker=ticker, held=False, spot=spot, chain_expiration=exp,
                      setup=setup, signal=signal, indicators=indicators)
```

Add `from typing import Any` if not already imported (the file already imports `from typing import Any, Protocol` — confirm it's present; if so, no change).

Now **replace** the body of `_evaluate_universe_entry` (lines ~234-272, everything from `held = {p["ticker"] ...}` down to the `candidates.sort(...)` line) so it delegates to `_evaluate_ticker`. Keep the rationale/notes/open block below `candidates.sort` unchanged. The replaced section:

```python
    held = {p["ticker"] for p in opens}
    equity = account_equity(engine, bot)
    evals = [
        _evaluate_ticker(engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
                         chain_provider=chain_provider, ticker=t, held=(t in held),
                         equity=equity)
        for t in meta["universe"]
    ]
    candidates = [e for e in evals if e.signal is not None]
    if not candidates:
        # surface the last non-held rejection reason, mirroring the old loop
        last_reason = next((e.reason for e in reversed(evals) if e.reason and not e.held), None)
        return {"outcome": "NO_TRADE", "reason": last_reason or "no universe signal"}

    candidates.sort(key=lambda e: e.setup.magnitude_pct, reverse=True)  # deepest dip/rip wins
    best = candidates[0]
    signal, setup = best.signal, best.setup
```

Note the existing code below this point references local names `signal` and `setup` (e.g. `signal.ticker`, `setup.direction`). The line `_mag, signal, setup = candidates[0]` is removed; the `signal, setup = best.signal, best.setup` line above provides them. Delete the old `candidates: list[tuple...] = []` / `last_reason` / `for ticker in meta["universe"]: ...` block entirely — it is fully replaced by the list comprehension above.

- [ ] **Step 4: Run the new test AND the full existing scanner suite**

Run: `python -m pytest tests/test_scanner.py -v`
Expected: PASS — the new `test_evaluate_ticker_*` test AND all existing tests, especially `test_undertow_opens_deepest_dip`, `test_undertow_skips_held_ticker_and_respects_concurrent_cap`, `test_undertow_time_stop_closes_position_end_to_end`, `test_undertow_journals_dip_context` (proves the refactor preserved live behavior).

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py tests/test_scanner.py
git commit -m "refactor(spreads): extract _evaluate_ticker shared by entry + watchlist"
```

---

## Task 3: `evaluate_universe_watchlist` collector + `ticker_eval_to_row`

**Files:**
- Modify: `spreadworks/backend/bots/scanner.py` (add two functions after `_evaluate_ticker`)
- Test: `spreadworks/tests/test_scanner.py`

- [ ] **Step 1: Write the failing test**

Add to `spreadworks/tests/test_scanner.py`:

```python
def test_evaluate_universe_watchlist_statuses(db_session):
    from datetime import datetime
    from backend.bots.scanner import (
        evaluate_universe_watchlist, ticker_eval_to_row, _evaluate_ticker,
    )
    from backend.bots.registry import get_bot
    from backend.bots.executor import open_position
    from backend.bots.strategies.vertical_spread import build_vertical_signal, DEFAULT_VERTICAL_PARAMS
    eng = db_session.get_bind()
    _enable_undertow(eng)
    meta = get_bot("undertow")
    cfg = dict(meta["defaults"])
    now = datetime(2026, 6, 10, 9, 0, tzinfo=CT)

    # Open a real AAPL position so AAPL shows HELD.
    aapl_chain = _spread_chain("AAPL", 140.0)
    aapl_sig = build_vertical_signal(
        kind="bull_call_spread", chain=aapl_chain, config=cfg, equity=25000.0,
        params={**DEFAULT_VERTICAL_PARAMS, **(meta.get("params") or {})},
    )
    assert aapl_sig is not None
    open_position(eng, "undertow", "bull_call_spread", aapl_sig, now)

    # NVDA has a buildable dip -> SIGNAL. Other universe names: no chain -> WATCHING.
    provider = FakeChainProvider(
        chains_by_ticker={"NVDA": _spread_chain("NVDA", 140.0),
                          "AAPL": _spread_chain("AAPL", 140.0)},
        daily_history={"NVDA": _undertow_history(), "AAPL": _undertow_history()},
    )
    evals = evaluate_universe_watchlist(engine=eng, bot="undertow", meta=meta,
                                        cfg=cfg, now_ct=now, chain_provider=provider)
    rows = [ticker_eval_to_row(e) for e in evals]
    by_ticker = {r["ticker"]: r for r in rows}

    assert len(rows) == len(meta["universe"])
    assert by_ticker["AAPL"]["status"] == "HELD"
    assert by_ticker["NVDA"]["status"] == "SIGNAL"
    assert by_ticker["NVDA"]["candidate"]["kind"] == "bull_call_spread"
    assert by_ticker["NVDA"]["candidate"]["long_strike"] is not None
    assert by_ticker["NVDA"]["candidate"]["short_strike"] is not None
    assert by_ticker["NVDA"]["expiration"] == "2026-06-22"
    assert by_ticker["SPY"]["status"] == "WATCHING"
    assert by_ticker["SPY"]["candidate"] is None
    assert "chain_unavailable" in (by_ticker["SPY"]["reason"] or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scanner.py::test_evaluate_universe_watchlist_statuses -v`
Expected: FAIL with `ImportError: cannot import name 'evaluate_universe_watchlist'`

- [ ] **Step 3: Add the collector and serializer**

In `spreadworks/backend/bots/scanner.py`, immediately after `_evaluate_ticker`, add:

```python
def evaluate_universe_watchlist(*, engine, bot: str, meta: dict, cfg: dict,
                                now_ct: datetime, chain_provider: ChainProvider
                                ) -> list[TickerEval]:
    """READ-ONLY evaluation of every universe name. Never opens, never writes
    scan_activity/equity. One TickerEval per name in meta['universe'] order."""
    opens = list_open_positions(engine, bot)
    held = {p["ticker"] for p in opens}
    equity = account_equity(engine, bot)
    return [
        _evaluate_ticker(engine=engine, bot=bot, meta=meta, cfg=cfg, now_ct=now_ct,
                         chain_provider=chain_provider, ticker=t, held=(t in held),
                         equity=equity)
        for t in meta["universe"]
    ]


def ticker_eval_to_row(e: TickerEval) -> dict[str, Any]:
    """Serialize a TickerEval to a JSON-safe watchlist row. Candidate spread is
    present ONLY when a signal is buildable (status SIGNAL)."""
    status = "HELD" if e.held else ("SIGNAL" if e.signal is not None else "WATCHING")
    ind = e.indicators or {}
    row: dict[str, Any] = {
        "ticker": e.ticker,
        "status": status,
        "held": e.held,
        "spot": e.spot,
        "expiration": e.chain_expiration,
        "dip_pct": ind.get("dip_pct"),
        "rip_pct": ind.get("rip_pct"),
        "rsi": ind.get("rsi"),
        "sma20": ind.get("sma"),
        "reason": e.reason,
        "candidate": None,
    }
    if e.signal is not None and e.setup is not None:
        s = e.signal
        legs = s.legs()
        long_leg = next((l for l in legs if l["side"] == "long"), {})
        short_leg = next((l for l in legs if l["side"] == "short"), {})
        row["candidate"] = {
            "kind": s.kind,
            "direction": e.setup.direction,
            "long_strike": long_leg.get("strike"),
            "short_strike": short_leg.get("strike"),
            "width": s.width,
            "net": s.net,
            "is_credit": s.is_credit,
            "max_profit": s.max_profit,
            "max_loss": s.max_loss,
            "contracts": s.contracts,
            "pt_target_pnl": s.pt_target_pnl,
            "sl_target_pnl": s.sl_target_pnl,
        }
    return row
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scanner.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add backend/bots/scanner.py tests/test_scanner.py
git commit -m "feat(spreads): read-only evaluate_universe_watchlist + row serializer"
```

---

## Task 4: `GET /{bot}/watchlist` endpoint

**Files:**
- Modify: `spreadworks/backend/routes_bots.py` (add endpoint after `get_scan_activity`, ~line 538)
- Test: `spreadworks/tests/test_routes_bots.py`

- [ ] **Step 1: Write the failing tests**

Add to `spreadworks/tests/test_routes_bots.py`:

```python
class _WatchlistFakeProvider:
    """Minimal ChainProvider for the watchlist endpoint test."""
    def __init__(self, chains, history):
        self._chains = chains
        self._history = history
    def get_chain(self, *, ticker, dte, today):
        return self._chains.get(ticker)
    def get_leg_mids(self, *, ticker, legs):
        return [leg["entry_price"] for leg in legs]
    def get_daily_history(self, *, ticker, days):
        return list(self._history.get(ticker, []))


def _wl_chain(ticker, spot):
    opts = []
    for s in range(100, 201, 5):
        call_mid = max(0.30, (spot - s) * 0.4 + 6.0)
        put_mid = max(0.30, (s - spot) * 0.4 + 6.0)
        opts.append({"strike": s, "type": "call", "bid": round(call_mid - 0.05, 2), "ask": round(call_mid + 0.05, 2)})
        opts.append({"strike": s, "type": "put", "bid": round(put_mid - 0.05, 2), "ask": round(put_mid + 0.05, 2)})
    return {"spot": spot, "expiration": "2026-06-22", "ticker": ticker, "options": opts}


def _wl_history():
    from datetime import date, timedelta
    bars = []
    base = date(2026, 4, 1)
    for i in range(36):
        p = 101 + i
        bars.append({"date": (base + timedelta(days=i)).isoformat(),
                     "open": p, "high": p, "low": p, "close": p})
    bars += [
        {"date": (base + timedelta(days=36)).isoformat(), "open": 144, "high": 150, "low": 143, "close": 145},
        {"date": (base + timedelta(days=37)).isoformat(), "open": 145, "high": 146, "low": 142, "close": 143},
        {"date": (base + timedelta(days=38)).isoformat(), "open": 143, "high": 143, "low": 140, "close": 141},
        {"date": (base + timedelta(days=39)).isoformat(), "open": 141, "high": 141, "low": 139, "close": 140},
    ]
    return bars


def test_watchlist_returns_rows_for_universe_bot(client, monkeypatch):
    from backend.bots import routes_helpers
    provider = _WatchlistFakeProvider(
        chains={"NVDA": _wl_chain("NVDA", 140.0)},
        history={"NVDA": _wl_history()},
    )
    monkeypatch.setattr(routes_helpers, "build_live_chain_provider", lambda: provider)
    r = client.get("/api/spreadworks/bots/undertow/watchlist")
    assert r.status_code == 200
    d = r.json()
    assert d["bot"] == "undertow"
    assert d["mode"] == "debit"
    assert isinstance(d["universe"], list) and "NVDA" in d["universe"]
    assert len(d["rows"]) == len(d["universe"])
    by_ticker = {row["ticker"]: row for row in d["rows"]}
    assert by_ticker["NVDA"]["status"] == "SIGNAL"
    assert by_ticker["NVDA"]["candidate"]["kind"] == "bull_call_spread"
    assert by_ticker["SPY"]["status"] == "WATCHING"


def test_watchlist_400_for_non_universe_bot(client):
    r = client.get("/api/spreadworks/bots/flow/watchlist")
    assert r.status_code == 400


def test_watchlist_404_for_unknown_bot(client):
    r = client.get("/api/spreadworks/bots/notabot/watchlist")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_routes_bots.py -k watchlist -v`
Expected: FAIL — `test_watchlist_returns_rows_for_universe_bot` and `test_watchlist_400_for_non_universe_bot` return 404 (route not defined yet).

- [ ] **Step 3: Add the endpoint**

In `spreadworks/backend/routes_bots.py`, after the `get_scan_activity` function (before `list_all_bots`), add:

```python
@router.get("/{bot}/watchlist")
def get_watchlist(bot: str):
    """Read-only universe watchlist for the vertical-spread bots (UNDERTOW /
    DELTA). Per tracked name: live signal status + the exact candidate spread
    when a setup is firing. 400 for non-universe bots."""
    _validate(bot)
    meta = BOT_REGISTRY[bot]
    if not (meta.get("universe") and meta.get("vertical_mode")):
        raise HTTPException(400, f"{bot} is not a universe bot")
    from .bots.scanner import evaluate_universe_watchlist, ticker_eval_to_row
    from .bots.routes_helpers import build_live_chain_provider
    cfg = load_config(ENGINE, bot)
    now = datetime.now(CT)
    provider = build_live_chain_provider()
    evals = evaluate_universe_watchlist(
        engine=ENGINE, bot=bot, meta=meta, cfg=cfg, now_ct=now,
        chain_provider=provider,
    )
    return {
        "bot": bot,
        "mode": meta.get("vertical_mode"),
        "as_of_ct": now.replace(tzinfo=None).isoformat(timespec="seconds"),
        "universe": list(meta["universe"]),
        "rows": [ticker_eval_to_row(e) for e in evals],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_routes_bots.py -k watchlist -v`
Expected: PASS (all three)

- [ ] **Step 5: Run the full backend suite (regression check)**

Run: `python -m pytest -q`
Expected: PASS — full SpreadWorks suite green (previously 157 tests + the new ones).

- [ ] **Step 6: Commit**

```bash
git add backend/routes_bots.py tests/test_routes_bots.py
git commit -m "feat(spreads): GET /bots/{bot}/watchlist endpoint for universe bots"
```

---

## Task 5: Frontend — `botApi.watchlist` + `WatchlistPanel`

No frontend unit-test harness exists in this project; verification is a successful `vite build`. **Run frontend commands from `C:\Users\lemol\AlphaGEX\spreadworks\frontend`.**

- [ ] **Step 1: Add the API helper**

In `spreadworks/frontend/src/lib/botApi.js`, add this line inside the `botApi` object (after the `scanActivity` line):

```javascript
  watchlist:      (b)        => _get(`/api/spreadworks/bots/${b}/watchlist`),
```

- [ ] **Step 2: Create the WatchlistPanel component**

Create `spreadworks/frontend/src/components/bots/WatchlistPanel.jsx`:

```jsx
import { useState, useEffect, useCallback } from 'react';
import { botApi } from '../../lib/botApi';

const REFRESH = 60_000; // ~60s auto-poll (8 chain fetches/poll)

function pctText(v) {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}
function num(v, d = 2) {
  if (v == null || Number.isNaN(v)) return '—';
  return Number(v).toFixed(d);
}

const STATUS_STYLE = {
  SIGNAL:   (theme) => ({ color: theme.primary, background: theme.primarySoft, ring: theme.primaryRing }),
  HELD:     ()      => ({ color: '#7dd3fc', background: 'rgba(125,211,252,0.10)', ring: 'rgba(125,211,252,0.30)' }),
  WATCHING: ()      => ({ color: '#94a3b8', background: 'rgba(148,163,184,0.08)', ring: 'rgba(148,163,184,0.22)' }),
};

function StatusBadge({ status, theme }) {
  const s = (STATUS_STYLE[status] || STATUS_STYLE.WATCHING)(theme);
  return (
    <span
      className="sw-mono text-[10.5px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
      style={{ color: s.color, background: s.background, boxShadow: `inset 0 0 0 1px ${s.ring}` }}
    >
      {status}
    </span>
  );
}

function CandidateLine({ c }) {
  if (!c) return <span className="text-text-muted">—</span>;
  const net = c.is_credit ? `cr ${num(c.net)}` : `db ${num(c.net)}`;
  const dir = c.kind.replace(/_/g, ' ');
  return (
    <span className="sw-mono text-[12px]">
      <span className="text-text-primary">{c.long_strike}</span>
      <span className="text-text-muted">/</span>
      <span className="text-text-primary">{c.short_strike}</span>
      <span className="text-text-tertiary"> · {dir} · {net} · ×{c.contracts}</span>
      <span className="text-sw-green"> +{num(c.max_profit, 0)}</span>
      <span className="text-text-muted">/</span>
      <span className="text-sw-red">−{num(c.max_loss, 0)}</span>
    </span>
  );
}

export default function WatchlistPanel({ bot, theme }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fetchWatchlist = useCallback(async () => {
    try {
      const d = await botApi.watchlist(bot);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, [bot]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => { if (!cancelled) await fetchWatchlist(); };
    run();
    const h = setInterval(run, REFRESH);
    return () => { cancelled = true; clearInterval(h); };
  }, [fetchWatchlist]);

  const rows = data?.rows || [];

  return (
    <div
      className="rounded-lg sw-glass"
      style={{ boxShadow: 'inset 0 0 0 1px rgba(125,211,252,0.08), inset 0 1px 0 rgba(255,255,255,0.04)' }}
    >
      <div
        className="px-5 py-4 flex items-center justify-between"
        style={{ borderBottom: '1px solid rgba(125,211,252,0.08)' }}
      >
        <div className="flex items-center gap-3">
          <h3 className="text-[14px] font-semibold text-text-primary">Universe Watchlist</h3>
          <span className="text-[11.5px] text-text-tertiary">
            {rows.length ? `${rows.length} names · live candidate spreads` : 'Tracked names'}
          </span>
        </div>
        <button
          onClick={fetchWatchlist}
          className="sw-mono px-3 py-1 text-[11px] font-medium rounded transition-all"
          style={{ color: theme.primary, background: theme.primarySoft }}
        >
          Refresh
        </button>
      </div>

      {error && !data ? (
        <div className="px-5 py-6 text-[13px] text-sw-red">Failed to load watchlist: {error.message}</div>
      ) : !data ? (
        <div className="px-5 py-6 text-[13px] text-text-tertiary">Loading watchlist…</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-text-tertiary text-[10.5px] uppercase tracking-[0.14em]">
                <th className="text-left font-semibold px-4 py-2.5">Ticker</th>
                <th className="text-left font-semibold px-3 py-2.5">Status</th>
                <th className="text-right font-semibold px-3 py-2.5">Spot</th>
                <th className="text-right font-semibold px-3 py-2.5">Dip%</th>
                <th className="text-right font-semibold px-3 py-2.5">Rip%</th>
                <th className="text-right font-semibold px-3 py-2.5">RSI(2)</th>
                <th className="text-right font-semibold px-3 py-2.5">SMA20</th>
                <th className="text-left font-semibold px-3 py-2.5">Expiry</th>
                <th className="text-left font-semibold px-4 py-2.5">Candidate / Reason</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.ticker} className="border-t border-white/[0.04]">
                  <td className="px-4 py-2.5 sw-mono font-semibold text-white">{r.ticker}</td>
                  <td className="px-3 py-2.5"><StatusBadge status={r.status} theme={theme} /></td>
                  <td className="px-3 py-2.5 text-right sw-mono">{num(r.spot)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{pctText(r.dip_pct)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{pctText(r.rip_pct)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{num(r.rsi, 1)}</td>
                  <td className="px-3 py-2.5 text-right sw-mono">{num(r.sma20)}</td>
                  <td className="px-3 py-2.5 sw-mono text-text-tertiary">{r.expiration || '—'}</td>
                  <td className="px-4 py-2.5">
                    {r.status === 'SIGNAL'
                      ? <CandidateLine c={r.candidate} />
                      : <span className="text-text-tertiary">{r.reason || '—'}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Render it for universe bots in BotDashboard**

In `spreadworks/frontend/src/pages/BotDashboard.jsx`:

Add the import near the other `components/bots/*` imports (after the `ConfigTab` import, line 13):

```javascript
import WatchlistPanel from '../components/bots/WatchlistPanel';
```

Then, in the main return block, insert the panel between `<EquityCurveCard ... />` and `<ActivityTabs ... />` (after the closing `/>` of EquityCurveCard around line 771):

```jsx
        {meta.ticker === 'multi' && (
          <WatchlistPanel bot={bot} theme={theme} />
        )}
```

- [ ] **Step 4: Build the frontend to verify it compiles**

Run (from `spreadworks/frontend`): `npx vite build`
Expected: build succeeds, writes to `dist/` (new hashed bundle in `dist/assets/`).

- [ ] **Step 5: Commit source + rebuilt dist**

```bash
git add frontend/src/lib/botApi.js frontend/src/components/bots/WatchlistPanel.jsx frontend/src/pages/BotDashboard.jsx frontend/dist
git commit -m "feat(spreads): UNDERTOW/DELTA universe watchlist dashboard panel"
```

---

## Task 6: Final verification & merge

- [ ] **Step 1: Full backend suite**

Run (from `spreadworks/`): `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Confirm frontend build is clean**

Run (from `spreadworks/frontend`): `npx vite build`
Expected: success, no errors.

- [ ] **Step 3: Merge to main (Render auto-deploys)**

Per AlphaGEX policy, merge verified feature branches without waiting. SpreadWorks backend (`spreadworks-backend.onrender.com`) serves the API; the frontend `dist/` is committed and served. This is paper-only and read-only — no risk-control or kill-switch change.

```bash
git checkout main
git merge --no-ff claude/undertow-delta-watchlist -m "Merge claude/undertow-delta-watchlist: UNDERTOW/DELTA universe watchlist"
git push origin main
```

- [ ] **Step 4: Post-deploy smoke check**

After the Render deploy finishes, verify the live endpoint returns rows:

```bash
curl -s "https://spreadworks-backend.onrender.com/api/spreadworks/bots/undertow/watchlist" | head -c 600
curl -s "https://spreadworks-backend.onrender.com/api/spreadworks/bots/delta/watchlist" | head -c 600
```

Expected: JSON with `bot`, `mode`, `universe` (8 names), and `rows` (8 rows, each with `status` ∈ {HELD, SIGNAL, WATCHING}). Then load `/undertow` and `/delta` in the UI and confirm the Universe Watchlist panel renders above the activity tabs.

---

## Self-Review notes

- **Spec coverage:** parity refactor (Task 2) ✓; read-only endpoint + 400 guard (Task 4) ✓; per-ticker row shape incl. live expiration + gate status + candidate-when-signaling (Tasks 3-4) ✓; frontend panel for universe bots only, ~60s poll, universe from response (Task 5) ✓; cost/resilience (held short-circuit + fail-soft reasons) ✓; tests for all three statuses + 400 (Tasks 2-4) ✓.
- **Type consistency:** `TickerEval` fields (`held`, `spot`, `chain_expiration`, `setup`, `signal`, `indicators`, `reason`) are referenced identically in `_evaluate_ticker`, `ticker_eval_to_row`, and tests. `evaluate_universe_watchlist` and `ticker_eval_to_row` names match between scanner.py, the endpoint, and tests. `compute_indicators` returns keys `dip_pct/rip_pct/rsi/sma/ref_high/ref_low`; serializer maps `sma`→`sma20`.
- **No placeholders:** every code step contains full content.
