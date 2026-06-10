# UNDERTOW — Dip-Buy Paper Bot (SpreadWorks)

**Date:** 2026-06-10
**Status:** Design approved, pending spec review → implementation plan
**Source spec:** `SleekDip_Strategy_Spec.docx` (standalone dip-buy options system)
**Home:** `spreadworks/` (paper-bot platform within AlphaGEX)

---

## 0. Scope & honest framing

UNDERTOW is a **SpreadWorks paper bot that buys calls on short-term pullbacks** across a
small ETF + mega-cap universe. It implements the **§8 "paper-trade gate"** of the source
spec — a zero-real-capital forward test of a dip-buy entry thesis — **not** the spec's
§4–7 historical backtester.

Carry these caveats forward verbatim; do not let the build imply more rigor than exists:

- **The entry edge is unproven.** There is no historical/out-of-sample validation behind
  the dip definition. The paper track record IS the validation, accumulated forward.
- **Underlying-dip interpretation only.** The spec's `D` values (20/30/40/55/70%) referred
  to *option-price* dips. We use *underlying* dips (small %), because we do not store
  per-contract price history. The option-price-dip interpretation is deferred.
- **Fills are at mid**, consistent with sibling SpreadWorks bots. The spec's realism
  modeling (next-bar worse-side-of-spread fills, `peak_capture_factor`) belongs to a
  backtester we are not building here, so paper fills are optimistic relative to live.
- **Overnight gap risk is real.** Positions are multi-day and are only monitored during
  RTH (08:00–14:59 CT). A gap can jump the stop-loss before the next scan.
- This is high-variance, lose-the-whole-premium territory. Paper only. Not financial advice.

This is the **"pragmatic paper bot first"** scope chosen during brainstorming: get the
entry thesis forward-testing fast with all-or-nothing exits; layer scale-out/trailing and a
larger universe later.

---

## 1. Architecture — reuse vs. new

UNDERTOW rides the existing SpreadWorks loop (scanner → executor → monitor → per-bot DB)
and adds the minimum needed for a single-leg, multi-ticker, multi-day-hold strategy.

| Reused unchanged | New / extended |
|---|---|
| Scanner **monitor loop** — already multi-ticker (keys leg quotes off `pos["ticker"]`) | `strategies/dip_buy.py` — single-leg long-call signal builder |
| Executor `open_position` / `close_position` + **debit P&L path** `(close−entry)×ct×100` | `get_daily_history()` on `ChainProvider` (Tradier `/v1/markets/history`, daily) |
| `compute_mtm` (single long leg: `signed=−mid` → debit path → `pnl=(mid−entry)×ct×100`) | Universe-loop entry path in scanner `_evaluate_entry` |
| Per-bot tables auto-created from `BOT_REGISTRY` (no manual migration) | `decide_exit` branch for `dip_buy`: `TIME_STOP` + `PRE_EXPIRY` |
| Generic `/api/spreadworks/bots/{bot}/*` routes (registry-driven) | `BOT_REGISTRY["undertow"]` + frontend `botRegistry.js` mirror + `/undertow` dashboard |
| Equity-snapshot + `scan_activity` journal | `dip_buy` added to debit handling (NOT in `CREDIT_STRATEGIES`) |

**No DB schema change.** Dip/exit/contract params live in the registry meta
(`universe` list + `params` dict), read directly by the scanner and strategy. Only the
universal knobs (capital, `bp_pct`, `pt_pct`, `sl_pct`, `max_concurrent_positions`,
entry window) live in `{bot}_config`. (Extra meta keys are ignored by the config-seed
loop, which reads a fixed key set.)

### Single-leg signal shape

`build_dip_buy_signal(...)` returns an object exposing the same surface the executor and
scanner already consume:

- `ticker`, `contracts`
- `legs()` → `[{"side":"long","type":"call","strike":K,"expiration":E,"entry_price":mid}]`
- `debit` (premium paid per contract, = ATM call mid) — **must NOT expose `.credit`**
- `pt_target_pnl`, `sl_target_pnl` ($ totals)
- `max_loss` (= `debit×100`, full premium), `max_profit` (cosmetic: PT $ target per
  contract — unbounded in reality, only PT/SL drive exits)

`get_leg_mids` builds an OCC symbol per leg and works unchanged for a 1-element list.

---

## 2. Entry — the dip detector (`dip_buy.py`)

Per ticker, each scan (within the entry window): fetch daily history + chain, then apply
gates in order. First failing gate produces a `diag` reason for `scan_activity.reason`.

1. **Reference high** = `max(high)` over the prior **N = 5** trading days (closed daily bars).
2. **Dip magnitude** = `(reference_high − spot) / reference_high`. Require **≥ D = 0.03** (3%).
3. **Confirmation gate** (default on): **RSI(2) < 10** on daily closes (oversold).
4. **Trend gate** (default on): `spot` **above the 20-day SMA** — buy pullbacks within
   uptrends, avoid falling-knife downtrends.
5. **Universe filter** (per the spec's §3):
   - option **bid/ask spread ≤ 15% of mid** (illiquidity proxy / "cheap options bleed here")
   - option **price ≥ $0.20** (one tick ≠ 20% noise)
   - **earnings-window exclusion** via existing `earnings_calendar.py` — skip a ticker
     within the configured days of its next earnings; **graceful pass** if the calendar is
     unavailable for that name.
     > **Known limitation:** `earnings_calendar.py` is a hardcoded marquee list (AAPL,
     > META, NVDA, TSLA, … big-caps) that goes stale each quarter and does **not** cover
     > every universe name — notably **AMD has no coverage**, so UNDERTOW can buy AMD
     > calls into an earnings print. The gate is best-effort and fail-open by design; a
     > real per-ticker earnings feed (or dropping uncovered names from the universe) is a
     > v2 hardening item.

`spot`, option bid/ask, and the chain come from the existing `get_chain`. Daily closes/highs
for the reference high, RSI(2), and SMA come from the new `get_daily_history`.

> Liquidity ADV/OI floors from the spec are proxied by the spread filter; the universe is
> pre-curated to liquid names, so explicit ADV/OI gating is deferred.

---

## 3. Contract selection + risk sizing

- **Direction:** calls only ("calls on dips"). Put track is out of scope for v1.
- **Strike:** **ATM** — nearest available strike to `spot`.
- **Expiry:** target **DTE ≈ 10** — nearest available expiration ≥ 7 days out.
- **`debit`** = ATM call mid for that strike/expiration.
- **Risk = full premium.** `contracts = floor(equity × bp_pct / (debit × 100))`,
  capped by ceiling `max_contracts`, **skip** (`sizing_below_one`) if < 1.

Default sizing knobs (`{bot}_config`):

| Knob | Default | Meaning |
|---|---|---|
| `starting_capital` | `25000` | larger than the $10k siblings so a single mega-cap call still sizes ≥1 |
| `bp_pct` | `0.02` | per-signal risk ≈ 2% (~$500) of equity, full premium at risk |
| `max_contracts` | `10` | ceiling so a cheap option can't balloon contract count |
| `max_concurrent_positions` | `5` | caps total premium-at-risk to ≈10% of account |

**One open position per ticker** at a time; **at most one new open per scan** (chosen =
deepest qualifying dip). Subsequent scans add more until `max_concurrent_positions`.

---

## 4. Exit manager (`decide_exit` branch for `dip_buy`)

All-or-nothing in v1 (PT/SL evaluated generically before the strategy branch):

| Exit | Rule | Rationale |
|---|---|---|
| **PT** | `mtm_pnl ≥ pt_target` where `pt_pct = 0.40` of premium | edge lives in modest, high-probability buckets |
| **SL** | `mtm_pnl ≤ −sl_target` where `sl_pct = 0.50` of premium | premium is max loss; cut the −99% finishers early |
| **TIME_STOP** | held ≥ `hold_days = 2` calendar days (from `entry_time.date()`) | kills post-peak decay |
| **PRE_EXPIRY** | `now.date() ≥ front_expiration` → force close | **never hold to expiry** |

No same-day EOD close (multi-day hold). `decide_exit` gains optional `entry_time` and
`hold_days` params used only on the `dip_buy` branch; existing strategies are unaffected.

**v2 (deferred):** scale-out — sell ⅔ at PT, trail a runner 25–40% off the high to catch
the +200% tails. Requires partial-close support in db/executor/monitor; out of scope until
the entry shows signal.

---

## 5. Registry entry (proposed)

```python
"undertow": {
    "display": "UNDERTOW",
    "strategy": "dip_buy",
    "ticker": "SPY",            # nominal; real scanning iterates `universe`
    "universe": ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "AMD", "META"],
    "front_dte": 10,            # target DTE for the long call
    "back_dte": None,
    "params": {                 # dip/exit hypotheses — code-level, swept later
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
        "enabled": False,               # ships OFF, paper only
        "max_contracts": 10,
        "bp_pct": 0.02,
        "sd_mult": 1.0,                 # unused by dip_buy
        "pt_pct": 0.40,                 # +40% of premium
        "sl_pct": 0.50,                 # −50% of premium
        "entry_start_ct": "08:35",
        "entry_end_ct": "14:30",
        "eod_close_ct": "14:45",        # unused by dip_buy (no same-day EOD)
        "discord_alerts": False,
        "delta_skew": 0,
        "use_gex_walls": False,
        "max_concurrent_positions": 5,
    },
},
```

`pt_target_pnl = pt_pct × debit × 100 × contracts`;
`sl_target_pnl = sl_pct × debit × 100 × contracts`.

---

## 6. Frontend (end-to-end, per project standard)

- Mirror the registry in `spreadworks/frontend/src/lib/botRegistry.js`.
- Add UNDERTOW to the bots overview / list.
- `/undertow` dashboard reusing the shared bot components: open positions (with **ticker**
  and **dip context** — reference high, dip %, RSI), equity curve, scan feed.
- The dist-build gotcha applies: rebuild + commit `frontend/dist/` if the deployed service
  serves committed dist.

---

## 7. Journaling

The `scan_activity` and `closed_trades` tables already provide the logger/journal the spec
wants "from day one." On each candidate scan, persist dip context (ticker, dip_pct,
reference_high, rsi, chosen strike/expiry) into `scan_activity.signal_data`; store the same
context in the position `notes` field at open.

---

## 8. Testing

- `dip_buy.py` unit tests with a `FakeChainProvider` exposing `get_daily_history`:
  qualifying dip, each gate rejecting (shallow dip, RSI not oversold, downtrend, wide
  spread, sub-$0.20, earnings window), sizing floor (`sizing_below_one`), ATM strike /
  DTE selection.
- `decide_exit` tests for the `dip_buy` branch: PT, SL, TIME_STOP at `hold_days`,
  PRE_EXPIRY, and "hold" when none fire.
- Scanner universe-path tests: skip already-held tickers, one-open-per-scan picks deepest
  dip, `max_concurrent_positions` cap, multi-day monitoring of an open position.
- Registry/db test: `undertow` tables auto-create; config seeds with the new defaults.

---

## 9. Out of scope (explicit)

- Historical backtester / parameter sweep / OOS split (spec §4–7) — belongs in AlphaGEX
  backtest infra, not SpreadWorks.
- Scale-out / trailing-runner exits (v2).
- Put track / straddle track (v1 is calls-on-dips only).
- Option-price-dip interpretation of `D`.
- Real-money execution — paper only, ships disabled.
