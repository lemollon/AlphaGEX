# IronForge Auto-Hedge — Technical Spec

**Status:** DRAFT for review (no production code yet)
**Author:** generated for the IronForge hedge initiative
**Scope:** FLAME (2DTE), SPARK (1DTE, real-money), INFERNO (0DTE) — the three IC seller bots
**Last updated:** 2026-06-11

---

## 1. Objective

Add a **per-bot, standing, accumulating hedge book** that buys cheap convexity (debit
verticals) as the gamma regime deteriorates, so the IC seller's P&L stays **flat or
profitable on high-volatility days** — the days that typically occur when **price is below
the GEX flip** (negative-gamma, dealers amplify moves) — and is protected against
**squeeze risk when price breaks back up through the flip**, *without* eroding the ICs'
baseline profitability on normal days.

The hedge is **not** a per-trade overlay tied to one condor's lifecycle. It is an
**account-level inventory** per bot that scales with a regime **danger score** and is held
across days/weeks. "We can't time the market, but we can be prepared."

### 1.1 Success criteria (these become the backtest GO/NO-GO gates — §9)

A configuration ships to live **only if all five pass** on the historical sample:

| # | Gate | Threshold |
|---|------|-----------|
| G1 | **Tail reduction** — worst-5% daily P&L (CVaR₅) of *IC+hedge* vs *IC-alone* | ≥ 40% improvement |
| G2 | **Below-flip days** — mean daily P&L of *IC+hedge* on days where spot < GEX flip | ≥ 0 (flat-or-better); IC-alone is negative on this subset |
| G3 | **Return retention** — full-sample net P&L of *IC+hedge* vs *IC-alone* | ≥ 85% (hedge drag ≤ 15%) |
| G4 | **Risk-adjusted** — Calmar (CAGR / MaxDD) of *IC+hedge* vs *IC-alone* | ≥ IC-alone (ideally >) |
| G5 | **Squeeze subset** — on above-flip breakout days, *IC+hedge* P&L tail | ≥ 30% improvement |

G2 + G5 encode "flat/profitable on rough days + squeeze protection." G3 + G4 encode "ICs
stay profitable."

### 1.2 Non-goals (v1)

- No VIX options. Rationale in §3.1 — tenor/settlement mismatch makes them unsizable for a
  0–2 DTE book. SPY verticals are same-underlying and exactly layerable on the IC payoff.
- No change to IC strike selection, sizing, or exit logic. The hedge is additive.
- No auto-**trim** at regime bottoms in v1 (alert-only). We only auto-**add** and let
  tranches expire/roll. Auto-trim is the most misfire-prone piece; deferred to v2.

---

## 2. Architecture

```
scanner.ts (per-cycle, per bot)
   └─ scanBot(bot)                         [existing]
        ├─ ... IC management + entry ...    [unchanged]
        └─ runHedgeCycle(bot, gexSnap)      [NEW]
              ├─ lib/hedge/score.ts     → dangerScore(g) from GexSnapshot + vol_alerts
              ├─ lib/hedge/target.ts    → targetConvexity(g, book) + accumulation gap
              ├─ lib/hedge/select.ts    → choose put/call vertical, strikes, tenor
              ├─ lib/hedge/executor.ts  → paper fill (reuse tradier helpers) + DB insert
              └─ lib/hedge/manage.ts    → mark tranches, expire, roll, budget cap
```

**Key design properties**

1. **Per-bot books.** Each bot owns `{bot}_hedge_tranches` + `{bot}_hedge_state`. FLAME's
   hedge protects FLAME's condors only; same for SPARK and INFERNO. No shared book.
2. **Lives in the TypeScript scanner path.** The Python `trading/` engine is reference-only
   and has GEX hardcoded to zero. The live regime feed already exists in TS via
   `blaze/gex-client.ts` + `lib/gex/proxy.ts` (the same source BLAZE trades on). The hedge
   reads a `GexSnapshot` (`lib/blaze/types.ts`) from that feed — **not** the placeholder
   GEX columns the IC insert path writes.
3. **Reuses existing primitives.** `buildOccSymbol`, `getOptionQuote` (`lib/tradier.ts`),
   the BLAZE worst-case fill model (long ask − short bid), and the `botTable()/dbQuery()`
   DB layer. New code is the *policy* (when/how much/what tenor), not new plumbing.
4. **Decoupled lifecycle.** Hedge tranches are multi-day. They are **not** closed at the
   IC EOD cutoff. They expire on their own dated schedule or roll while danger persists.
5. **PDT-free.** A debit vertical opened and held ≥ 1 session is **not a day trade**, so the
   hedge never consumes the 4-in-5 PDT budget that constrains the ICs. This is a structural
   reason to prefer multi-day tenors and is load-bearing for SPARK (real-money).

---

## 3. Instrument & regime logic

### 3.1 Why SPY debit verticals, not VIX

- **Tenor.** VIX options expire monthly + sparse Wed weeklies and price the VIX *future*
  (already discounts mean reversion). A 0–2 DTE condor has no matching VIX expiry; a VIX
  spread would outlive the condor by weeks.
- **Sizability.** VIX cash-settles to VRO; the "SPY down X% → VIX future +Y" beta is
  unstable and convex — not exactly layerable. A SPY vertical's payoff is a deterministic
  function of where SPY lands, so it lays directly on the IC payoff diagram.
- **Reuse.** Same chain, same fill model, same lifecycle code as BLAZE.

### 3.2 The two hedges (direction set by where we are in the gamma cycle)

| Regime state (from `GexSnapshot`) | IC risk | Hedge |
|---|---|---|
| Positive gamma, spot ≫ flip | low | none — let theta run |
| **Topping / spot falling toward flip (pos→neg)** | rising | **PUT debit vertical** (downside) — primary |
| **Below flip, negative gamma (high-vol days)** | severe | maintain/extend PUT hedge; IC may widen/halt |
| **Squeeze: spot breaks back **up** through flip (neg→pos)** | upside breach + vol crush | **CALL debit vertical** (squeeze cap); stop adding puts |

Direction is decided by `previous_regime → regime` (the `regime_flipped` edge) and spot vs
`flip_point`, reusing exactly the inputs BLAZE's `flip_cross` setup already consumes
(`lib/blaze/setups.ts::evaluateFlipCross`).

### 3.3 Strike & tenor selection (`lib/hedge/select.ts`)

- **Put hedge:** long strike at/just below the IC short put (or just below `flip_point`,
  whichever is higher) so it activates where the book starts bleeding; short strike
  `long − hedge_width`. Default `hedge_width = $5` (matches IC wing for clean 1:1 payoff
  reasoning; configurable).
- **Call hedge (squeeze):** long strike at/just above `flip_point` or the IC short call;
  short strike `long + hedge_width`.
- **Tenor ladder.** Base tranches **5–20 trading days out** (cheap carry, vega-rich — pays
  on vol expansion, not just spot). When `g` spikes acutely (flip just crossed), add **one
  shorter-dated 1–3 DTE tranche** for the acute move (gamma-rich). New helper
  `tradingDaysOut(from, n)` (generalizes BLAZE's `nextTradingDay`).
- **Cheapness guard:** reject if `debit ≤ 0` or `debit ≥ hedge_width` (same as BLAZE), and
  if `debit/hedge_width > max_debit_ratio` (don't buy expensive convexity after vol already
  blew out — we want to have bought it *before*).

---

## 4. The math

All per-contract dollars. `$5` IC wing ⇒ max IC value `$500`/contract.

### 4.1 Danger score `g ∈ [0,1]` (`lib/hedge/score.ts`)

```
proximity = clamp(1 − |spot − flip_point| / (k_prox · sigma_1d_band_width), 0, 1)
regime_sign = (net_gex < 0) ? 1 : 0
flip_edge   = regime_flipped_recently ? 1 : 0          // last N cycles
vol_alert   = (backwardation || ts_flattening active) ? 1 : 0   // from vol_alerts table
vol_stress  = clamp((vix − vix_lo) / (vix_hi − vix_lo), 0, 1)

g = w1·proximity + w2·regime_sign + w3·flip_edge + w4·vol_alert + w5·vol_stress
    (weights sum to 1; defaults below, calibrated in backtest)
```

Default weights (pre-calibration): `w1=0.30, w2=0.25, w3=0.20, w4=0.15, w5=0.10`.
`direction = (spot < flip_point) ? 'put' : (squeeze_detected ? 'call' : 'put')`.

### 4.2 Target convexity & accumulation (`lib/hedge/target.ts`)

```
IC_book_maxloss = Σ over open + expected-this-horizon condors of (500 − credit)·N_ic     ($)
T(g)            = coverage_cap · g^γ · IC_book_maxloss          // desired hedge max payoff
current_cap     = Σ over open tranches of (hedge_width·100 − debit)·N_tranche
gap             = max(0, T(g) − current_cap)

if gap > 0 and within budget:
    add ONE tranche sized to close ~ladder_fraction of the gap
    N_tranche = floor( (ladder_fraction · gap) / (hedge_width·100 − debit) )
```

- `coverage_cap` (default 0.6) — most you'll ever cover.
- `γ` (default 2.0) — convex ramp: add slowly when danger is mild, fast as it spikes.
- `ladder_fraction` (default 0.34) — average in over ~3 cycles/days, never one big entry.
- **Budget cap (hard):** cumulative hedge debit over a rolling 30 calendar days
  ≤ `monthly_hedge_budget_pct` (default 4%) × starting capital. This bounds worst-case bleed
  if the regime threatens for weeks and never breaks. When the cap is hit, `runHedgeCycle`
  logs `BUDGET_CAPPED` and adds nothing.

Because `T(g)` scales with `IC_book_maxloss` (which scales with the bots' Kelly sizing), the
hedge **auto-scales** with position size — no separate tuning per bot.

### 4.3 Worked example (INFERNO 0DTE, illustrative)

`SPY 600`, credit `$1.40`, `N_ic = 8` ⇒ `IC_book_maxloss = (500−140)·8 = $2,880`.
`g = 0.7` (spot just under flip, negative gamma, backwardation active).
`T = 0.6 · 0.7² · 2880 ≈ $847`. Put vertical long 590 / short 585, `debit $0.70` ⇒ payoff
cap `$430`/contract. First add: `floor(0.34·847 / 430) = 0` → bump to floor of 1 contract
(`min_add = 1`) = `$70` spent. Next cycles, as `g` rises toward 0.9, `T` grows and the
ladder accumulates 3–4 contracts, ~`$280` total = ~5% of the day's credit, covering ~60% of
the condor's tail if SPY breaks 585.

---

## 5. Data model (PostgreSQL, auto-created via `db.ts` on first use)

Conventions match existing tables (`NUMERIC(10,2)`, `dte_mode`, `account_type`, CT
timestamps).

### 5.1 `{bot}_hedge_tranches` — one row per hedge vertical

```sql
CREATE TABLE IF NOT EXISTS {bot}_hedge_tranches (
    tranche_id        SERIAL PRIMARY KEY,
    ticker            TEXT NOT NULL DEFAULT 'SPY',
    direction         TEXT NOT NULL,            -- 'put' | 'call'
    long_strike       NUMERIC(10,2) NOT NULL,
    short_strike      NUMERIC(10,2) NOT NULL,
    long_symbol       TEXT NOT NULL,
    short_symbol      TEXT NOT NULL,
    hedge_width       NUMERIC(10,2) NOT NULL,
    debit             NUMERIC(10,4) NOT NULL,   -- per contract, entry
    contracts         INTEGER NOT NULL,
    expiration        DATE NOT NULL,
    spot_at_entry     NUMERIC(10,2),
    flip_at_entry     NUMERIC(10,2),
    g_at_entry        NUMERIC(6,4),             -- danger score when opened
    reason            TEXT,                     -- 'topping_putcross' etc.
    max_payoff        NUMERIC(12,2),            -- (width*100 - debit)*contracts
    cost_usd          NUMERIC(12,2),            -- debit*100*contracts
    mark              NUMERIC(10,4),            -- latest per-contract mark
    unrealized_pnl    NUMERIC(12,2) DEFAULT 0,
    realized_pnl      NUMERIC(12,2),
    status            TEXT NOT NULL DEFAULT 'open',  -- open|closed|expired|rolled
    close_reason      TEXT,                     -- EXPIRE|ROLL|REGIME_HEALED|MANUAL
    open_time         TIMESTAMPTZ DEFAULT NOW(),
    close_time        TIMESTAMPTZ,
    open_date         DATE,
    dte_mode          TEXT NOT NULL,
    account_type      TEXT NOT NULL DEFAULT 'sandbox'
);
```

### 5.2 `{bot}_hedge_state` — rolling book + budget accounting

```sql
CREATE TABLE IF NOT EXISTS {bot}_hedge_state (
    id                    SERIAL PRIMARY KEY,
    dte_mode              TEXT NOT NULL,
    g_current             NUMERIC(6,4),
    target_convexity      NUMERIC(12,2),
    current_convexity     NUMERIC(12,2),
    rolling_30d_spend     NUMERIC(12,2),
    last_add_at           TIMESTAMPTZ,
    last_cycle_outcome    TEXT,            -- ADD|HOLD|BUDGET_CAPPED|NO_DANGER|HEALED
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);
```

Hedge events also append to the existing `{bot}_logs` (`HEDGE_ADD`, `HEDGE_EXPIRE`,
`HEDGE_ROLL`, `HEDGE_BUDGET_CAP`) so they surface in the existing logs UI with no new
component.

---

## 6. Execution (`lib/hedge/executor.ts`)

Mirrors `lib/blaze/executor.ts::openVertical`:

1. `expiration = tradingDaysOut(snap.snapshot_at, tenor_days)`.
2. Build OCC symbols via `buildOccSymbol`; fetch `getOptionQuote` for both legs.
3. `debit = longQ.ask − shortQ.bid` (worst-case paper fill, conservative — consistent with
   IC fills). Reject if `debit ≤ 0`, `debit ≥ hedge_width`, or `debit/hedge_width >
   max_debit_ratio`.
4. `contracts` from §4.2 accumulation gap (not Kelly — coverage-driven), clamped to
   `[min_add, gap_remaining]`.
5. Insert tranche; **BP impact = `cost_usd` only** (a debit spread's max loss is the debit
   paid — do **not** reserve collateral like an IC). Decrement `buying_power` by `cost_usd`,
   leave `collateral_in_use` untouched.
6. Append `HEDGE_ADD` to `{bot}_logs`; upsert `{bot}_hedge_state`.

**Marking & close (`lib/hedge/manage.ts`)** runs each cycle:
- Mark each open tranche `mark = longMid − shortMid` (cap `[0, hedge_width]`), update
  `unrealized_pnl = (mark − debit)·100·contracts`.
- **Expire** at expiration date: `realized_pnl` = intrinsic at settlement; release nothing
  (cost already spent). `status='expired'`.
- **Roll** while `g ≥ roll_floor` and tranche within `roll_dte` of expiry: close + open a
  new dated tranche (logged `HEDGE_ROLL`).
- **No EOD close** (unlike ICs). Tranches persist overnight by design.

---

## 7. Integration points

- `scanner.ts::scanBot()` — after IC management/entry, call
  `await runHedgeCycle(bot, gexSnap)` inside the existing `try`. Must be **non-fatal**: a
  hedge error logs and continues; it can never block IC trading (per common-mistakes §3).
- `gexSnap` — obtain via the existing BLAZE gex-client path (`lib/gex/proxy.ts`). If the GEX
  feed is stale (`> gex_stale_max_seconds`) or unavailable, `runHedgeCycle` **holds** (adds
  nothing) and logs `NO_GEX`. Never hedge on stale regime data.
- Config — extend the per-bot config object (read from `{bot}_config`, defaults in a new
  `DEFAULT_HEDGE_CONFIG`): all knobs in §4 (`coverage_cap, gamma, ladder_fraction,
  monthly_hedge_budget_pct, hedge_width, tenor_days, acute_tenor_days, max_debit_ratio,
  min_add, roll_floor, roll_dte, w1..w5, k_prox, vix_lo, vix_hi`).
- API routes (`webapp/src/app/api/[bot]/hedge/...`), all read except the last:
  - `GET /hedge/state` — current `g`, target vs current convexity, 30d spend vs budget.
  - `GET /hedge/tranches` — open + recent tranches with marks.
  - `GET /hedge/performance` — hedge-only P&L, and **IC+hedge combined** daily series.
  - `GET /hedge/diagnose` — why we did/didn't add this cycle (score breakdown).
  - `POST /hedge/roll` / `POST /hedge/close` — manual ops (per the webapp-backend rule).
- Frontend — one `HedgeCard.tsx` on each bot dashboard: danger gauge (`g`), coverage
  bar (current/target), 30d budget bar, open tranches, and a combined-equity overlay toggle
  on the existing `EquityChart`.

---

## 8. Lifecycle & safety

- **Non-blocking:** hedge failures never touch IC flow.
- **Idempotent adds:** one add per cycle max; `last_add_at` + `ladder_fraction` prevent
  dog-piling.
- **Budget hard stop:** §4.2.
- **Stale-data hold:** §7.
- **Paper/real parity:** INFERNO/FLAME paper, SPARK real-money. The hedge respects the same
  `account_type` routing as ICs (`get_tradier_*` resolvers). SPARK hedge orders go to
  production only with prod creds present (fail-loud, same as today).
- **Reconciliation:** a `reconcileHedge(bot)` (cousin of `reconcileCollateral`) detects
  tranches past expiration still `open` and settles them — prevents stranded convexity.

---

## 9. Backtest harness (REQUIRED before any live enable)

Mirrors `backtest/blaze_gex_0dte/` (proven pattern: `loader → reconstruct → providers →
account_sim → metrics`). New package: **`backtest/ironforge_hedge/`**.

### 9.1 Data inputs
- **Option chains (1-min):** ORAT DB via `ORAT_DATABASE_URL`, reusing
  `blaze_gex_0dte/loader.py::load_day` (extended to load the IC strikes *and* the hedge
  strikes/tenors — multi-expiry, since hedges are dated days/weeks out).
- **Regime stream:** reuse `blaze_gex_0dte/reconstruct.py::build_snapshots` to rebuild the
  per-minute `GexSnapshot` (flip_point, net_gex, walls, sigma) from the chain via BS gamma.
- **VIX / vol_alerts:** historical VIX from the same chain reconstruction; backtest the
  `backwardation/ts_flattening/exhaustion` signals from VIX term structure if available, else
  ablate `w4` to 0 for the historical run and note the limitation.
- **Hedge leg repricing fallback:** when a dated hedge strike isn't in ORAT, reprice via
  Black-Scholes (`backtest/intraday_walls/bs.py`) off reconstructed IV — clearly flagged in
  output as `REPRICED` vs `MARKET`.

### 9.2 Simulator (`account_sim.py`)
- Replays each session: runs the **real IC logic** (entry/exit/stop as live) to get the
  IC-alone daily P&L, **and** runs `runHedgeCycle` policy (ported to py, or the TS policy
  exercised via a thin runner) to accumulate/mark/expire hedge tranches across days.
- Produces two aligned daily P&L series: **IC-alone** and **IC+hedge**, per bot.
- Carries the hedge book across days (this is the crucial difference from the per-trade
  blaze sim — state persists).

### 9.3 Metrics & verdict (`metrics.py`)
- Per bot: total P&L, CAGR, MaxDD, Calmar, CVaR₅, win rate, profit factor — for both series.
- Subset cuts: **below-flip days**, **above-flip breakout (squeeze) days**, **high-VIX
  days**.
- Emits the **GO/NO-GO** table against §1.1 (G1–G5). All five GO ⇒ eligible to enable.
- Param sweep (`cli.py`) over `coverage_cap, γ, tenor_days, monthly_hedge_budget_pct,
  hedge_width` to find the frontier that maximizes G3·G4 subject to G1,G2,G5 passing.

### 9.4 Run convention
```bash
python -m backtest.ironforge_hedge.cli --bot spark --start 2023-01-01 --end 2026-06-01 \
    2>&1 | tee /tmp/hedge_spark_bt.txt          # Render shell has no scrollback
```

> **Note on the "webapp-only backend" rule:** that rule governs *production* diagnostics/fix
> tooling. This is **offline research**, mirroring the existing `backtest/blaze_gex_0dte/`
> python harness (same precedent). Confirm placement before building (Open Decision D4).

---

## 10. Phased rollout

1. **M1 — Backtest harness** (`backtest/ironforge_hedge/`) + GO/NO-GO report on SPARK &
   INFERNO. *No live code.* Gate the rest on a GO.
2. **M2 — Policy modules** (`lib/hedge/{score,target,select}.ts`) + unit tests (vitest,
   pure, mirroring `derive.test.ts`). No execution.
3. **M3 — Executor + tables + manage/reconcile**, wired into `scanBot` behind a per-bot
   `hedge_enabled` flag (default OFF). Paper bots first (INFERNO/FLAME).
4. **M4 — API routes + `HedgeCard.tsx`** for visibility while it runs in shadow.
5. **M5 — Enable SPARK (real-money)** only after M1 GO holds out-of-sample and M3/M4 have
   run clean in paper for an agreed window.

---

## 11. Open decisions

- **D1 — `hedge_width`:** match IC wing ($5) for clean payoff math, or go wider/cheaper
  (e.g. $10) for more convexity per dollar? *Recommend $5 v1; sweep in backtest.*
- **D2 — Squeeze (call) hedge in v1 or v2?** Adds cost on the side that breaches less often.
  *Recommend v2 unless G5 fails without it.*
- **D3 — Expected-condor horizon in `IC_book_maxloss`:** count only currently-open condors,
  or also anticipated condors over the hedge tenor? *Recommend open-only v1 (simpler, slightly
  under-hedged); revisit if G2 fails.*
- **D4 — Backtest location:** `backtest/ironforge_hedge/` (python, mirrors blaze) vs a TS
  harness inside the webapp. *Recommend python/backtest per precedent — confirm.*
- **D5 — Auto-trim at bottoms:** alert-only v1 (recommended) vs auto-trim.
```
