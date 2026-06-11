# UNDERTOW / DELTA Universe Watchlist — Design

**Date:** 2026-06-11
**Status:** Design (approved)
**Home:** `spreadworks/` (paper-bot platform within AlphaGEX)
**Bots:** `undertow` (vertical_debit), `delta` (vertical_credit) — the two `universe`/`vertical_mode` bots.

---

## 0. Problem & scope

UNDERTOW and DELTA scan an 8-name universe
(`SPY, QQQ, IWM, AAPL, NVDA, TSLA, AMD, META`) and open at most one vertical
spread on the deepest qualifying dip/rip. Today their dashboards show **only open
positions**. With zero positions open, the dashboards are blank and tell the
operator nothing about what the bots are tracking.

This feature adds a **universe watchlist** to the `/undertow` and `/delta`
dashboards: per tracked name, show the live signal status and — when a setup is
currently firing — the exact candidate spread (strikes, expiration, debit/credit,
sizing) the bot would open right now.

**In scope:** read-only watchlist endpoint + dashboard panel for the two universe
bots. **Out of scope:** the other six bots (single-ticker, not universe); changing
any entry/exit logic; backtesting.

---

## 1. Honest framing (a constraint from the code)

A vertical spread needs a **direction**, and direction only exists once
`detect_setup` returns a `bullish` (dip) or `bearish` (rip) `Setup`. With no
setup there is no `kind` to pass to `build_vertical_signal`, so **no real strikes
exist for a non-signaling name.**

Therefore:
- **Signaling name** → show the exact live candidate spread (this is literally what
  the bot would open).
- **Non-signaling name** → show the live ~10-DTE **expiration date** + the indicator
  values (spot, 5-day high/low, dip%/rip%, RSI(2), 20-day SMA) + the exact reason
  it is not triggering. **No fabricated strikes.**

This was a confirmed design decision: truthful status over speculative strikes.

---

## 2. Architecture — reuse vs. new

### 2.1 Parity refactor (`spreadworks/backend/bots/scanner.py`)

`_evaluate_universe_entry` already does the per-ticker work we need: skip held,
earnings gate, fetch chain (`front_dte`), fetch daily history, `detect_setup`,
`build_vertical_signal`. It stops at the first qualifying name and **opens**.

Extract the per-ticker body into one shared helper so the live path and the
watchlist cannot drift:

```python
@dataclass
class TickerEval:
    ticker: str
    held: bool
    spot: float | None
    chain_expiration: str | None      # real ~10-DTE expiration date
    setup: Setup | None               # from detect_setup
    signal: VerticalSignal | None     # from build_vertical_signal (None unless setup fires)
    reason: str | None                # gate/why-not (dip_below_sma, no_setup, earnings_excluded, chain_unavailable, credit_too_low, sizing_below_one, ...)

def _evaluate_ticker(*, engine, bot, meta, cfg, now_ct, chain_provider,
                     ticker, held: bool, equity: float) -> TickerEval: ...
```

- `_evaluate_universe_entry` is rewritten to: call `_evaluate_ticker` for each
  universe name, collect the `TickerEval`s, pick the deepest-magnitude one whose
  `signal is not None`, then open it (rationale + notes + `open_position`
  unchanged). Behavior is identical to today — verified by existing scanner tests.
- New read-only collector:

```python
def evaluate_universe_watchlist(*, engine, bot, meta, cfg, now_ct,
                                chain_provider) -> list[TickerEval]:
    opens = list_open_positions(engine, bot)
    held = {p["ticker"] for p in opens}
    equity = account_equity(engine, bot)
    return [_evaluate_ticker(engine=engine, bot=bot, meta=meta, cfg=cfg,
                             now_ct=now_ct, chain_provider=chain_provider,
                             ticker=t, held=(t in held), equity=equity)
            for t in meta["universe"]]
```

No DB writes, never opens.

### 2.2 Endpoint (`spreadworks/backend/routes.py`)

```
GET /api/spreadworks/bots/{bot}/watchlist
```

- 400 if the bot has no `universe`/`vertical_mode` (only `undertow`/`delta` qualify).
- Wires the **same live Tradier `ChainProvider`** the scanner uses (the existing
  chain fetcher in routes.py), builds `now_ct`, calls `evaluate_universe_watchlist`,
  and serializes each `TickerEval` to JSON.

Response shape:

```json
{
  "bot": "undertow",
  "mode": "debit",
  "as_of_ct": "2026-06-11T09:42:00",
  "universe": ["SPY","QQQ", "..."],
  "rows": [
    {
      "ticker": "NVDA",
      "status": "SIGNAL",                 // HELD | SIGNAL | WATCHING
      "held": false,
      "spot": 123.45,
      "expiration": "2026-06-21",
      "dip_pct": 0.041, "rip_pct": 0.0,
      "rsi": 8.3, "sma20": 119.1,
      "reason": null,
      "candidate": {                      // present only when status == SIGNAL
        "kind": "bull_call_spread",
        "direction": "bullish",
        "long_strike": 123, "short_strike": 128, "width": 5,
        "net": 2.10, "is_credit": false,
        "max_profit": 290.0, "max_loss": 210.0,
        "contracts": 2,
        "pt_target_pnl": 290.0, "sl_target_pnl": 105.0
      }
    },
    {
      "ticker": "SPY",
      "status": "WATCHING",
      "held": false,
      "spot": 572.58,
      "expiration": "2026-06-21",
      "dip_pct": 0.06, "rip_pct": 0.0,
      "rsi": 9.1, "sma20": 610.79,
      "reason": "dip_below_sma: spot=572.58 sma=610.79",
      "candidate": null
    }
  ]
}
```

`status` is derived: `held` → `HELD`; else `signal is not None` → `SIGNAL`; else
`WATCHING`.

### 2.3 Frontend (`spreadworks/frontend/src/...`)

- New `WatchlistPanel` component, rendered in `BotDashboard.jsx` **only for
  universe bots** (gate on `BOT_REGISTRY[bot].ticker === 'multi'`), placed above
  the open-positions table.
- SWR fetch of `/api/spreadworks/bots/{bot}/watchlist` with
  `refreshInterval: 60000` (~60s auto-poll).
- Renders a table: ticker · status badge · spot · dip%/rip% · RSI(2) · 20-day SMA ·
  expiration · reason. `SIGNAL` rows expand/inline-show the candidate spread legs
  (long/short strikes, width, net debit/credit, contracts, max P/L, est PT/SL).
- Status badges color-coded: `SIGNAL` = bot primary color, `HELD` = neutral/active,
  `WATCHING` = muted. Universe list comes from the response (no second mirror in
  `botRegistry.js`).
- Null-guard every field (cost: chain/history can be missing for a name → row
  shows `WATCHING` + `chain_unavailable`/`history_unavailable` reason, never crashes).

---

## 3. Cost & resilience

- Per load: 8 × (`get_chain` + `get_daily_history`). Bounded by the existing 15s
  scan-style guard inside the endpoint and the 60s SWR interval.
- A per-ticker failure degrades that one row to `WATCHING` + reason; it never fails
  the whole response (mirrors the scanner's `last_reason` fail-soft behavior).
- Endpoint is read-only — safe to call any time, including when the market is
  closed (rows will show stale/last quotes or `chain_unavailable`).

---

## 4. Testing

- **Parity:** `_evaluate_ticker` returns the same `setup`/`signal` that drove the
  old inline logic; existing `test_scanner.py` universe-entry tests still pass
  unchanged (proves the refactor didn't alter live behavior).
- **Watchlist collector:** with a fake `ChainProvider` produce all three statuses —
  HELD (open position on a name), SIGNAL (a name with a qualifying dip + buildable
  spread), WATCHING (a name rejected by `dip_below_sma`).
- **Endpoint:** 200 + correct shape for `undertow`/`delta`; 400 for a non-universe
  bot (e.g. `flow`).
- **Frontend:** panel renders for universe bots only; candidate spread shows for
  SIGNAL rows; null-guard test with a missing-chain row.

---

## 5. Files touched

| File | Change |
|---|---|
| `spreadworks/backend/bots/scanner.py` | extract `_evaluate_ticker` + `TickerEval`; add `evaluate_universe_watchlist`; rewrite `_evaluate_universe_entry` to reuse |
| `spreadworks/backend/routes.py` | new `GET /api/spreadworks/bots/{bot}/watchlist` |
| `spreadworks/frontend/src/components/bots/WatchlistPanel.jsx` | new panel (sits alongside the other `components/bots/*` tabs) |
| `spreadworks/frontend/src/pages/BotDashboard.jsx` | render panel for universe bots |
| `spreadworks/tests/test_scanner.py` | parity + watchlist collector tests |
| `spreadworks/tests/test_routes*.py` | endpoint 200/400 tests |
| `spreadworks/frontend/dist/*` | rebuilt bundle (Render serves committed dist) |

---

## 6. Out of scope (explicit)

- The six single-ticker bots (no universe).
- Any change to entry/exit/sizing logic.
- Hypothetical strikes for non-signaling names (rejected: speculative).
- Historical backtest of the bots themselves (separate, still de-scoped).
