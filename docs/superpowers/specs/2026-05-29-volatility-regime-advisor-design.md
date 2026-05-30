# Volatility Regime Advisor — Design Spec

**Date:** 2026-05-29
**Status:** Draft for review
**Author:** Claude (with operator)

## 1. Purpose

Give a single, authoritative read on the SPY/VIX volatility regime that answers, in plain terms:

1. **What regime are we in** (calm/contango, stressed/backwardation, exhaustion, complacent/floor)?
2. **Directional recommendation** for discretionary options trading — *lean puts / lean calls / neutral / buy-the-bounce* — with conviction and rationale.
3. **When** the move or reversal is likely to land (a timing window) **and what expiration to buy** — because the operator trades options and DTE selection is the whole game.
4. **How often this call has been right** — both historically (2006–2026 backtest) and going forward (a live, self-scoring track record).

This is **advisory/educational**, not auto-execution. It never gates or fires bot trades. It surfaces information on a dedicated IronForge page and in the daily brief.

### Background — what the data actually says

A 20-year study (`backtest/vvix_vix_analysis/`, 5,029 trading days) established:

- **VVIX "divergence" (VVIX rising while VIX calm) does NOT predict spikes** — it is statistically noise (t≈0.9, spike-lift ~1.1×). It will be shown but **explicitly flagged low-confidence**.
- **VIX term structure is the real edge.** Backwardation (VIX > VIX3M): forward VIX −8.4%@5d (t=−7.4, vol mean-reverts down → fade), forward SPY +0.91%@5d (t=2.8, contrarian bullish), and **P(next-day |SPY| > 2%) = 4.06× base** (a genuine stress flag). Term-structure flattening is a milder, more *leading* version.
- **Exhaustion (VIX makes a 10-day high but VVIX won't confirm, VIX in top quintile)** → vol fades (−7.65%@5d, t=−4.3) and SPY bounces (+0.79%@3d, t=2.1). This is VVIX's one real contribution and the primary **bullish** signal.
- **Floor (VVIX<85 & VIX<14)** → slow upward vol drift, benign for premium sellers.

The advisor operationalizes these findings. See memory `project_vix_vvix_signal_study_2026_05_29` and `project_vvix_cboe_live_feed_2026_05_29`.

## 2. Architecture

**Brain in AlphaGEX (Python), page in IronForge (proxy + render)** — mirrors the existing `/gex` page pattern (IronForge proxies AlphaGEX analysis endpoints).

```
 CBOE CDN (live + history)  ──►  unified_data_provider  ──►  vol_regime_advisor.py
                                                                  │
   backtest evidence.json  ──────────────────────────────────────┤
   (static, from harness)                                         │
                                                                  ▼
                            alphagex-db: vol_advisor_log  ◄── collector worker (daily snapshot + scorer)
                                                                  │
                                          GET /api/vix/regime-advisor        (current report + evidence + live record)
                                          GET /api/vix/regime-advisor/history (log + outcomes, for charts)
                                                                  │
                                                                  ▼
                            IronForge: /volatility page (proxy + render)
                            IronForge: daily brief vol-regime line (BriefingMacroRibbon)
```

**Why this split:** the live VIX/VVIX/term-structure feed and the backtest both live in AlphaGEX. Building the brain there keeps the recommendation logic next to its evidence; IronForge stays a thin presentation layer, as it already is for GEX.

## 3. Components

### 3.1 Signal + recommendation engine — `core/vol_regime_advisor.py` (NEW)

**Inputs:**
- Live curve: VIX, VVIX, VIX9D, VIX3M, VIX6M via `unified_data_provider.get_vix_term_structure()` / `get_vvix()` (already shipped).
- Trailing history for z-scores/percentiles: the CBOE daily history CSVs (`cdn.cboe.com/api/global/us_indices/daily_prices/<SYM>_History.csv`), fetched and cached once/day in-process (tiny; ~252 trading days needed for percentiles).

**Signal definitions** (t-only, identical to the validated harness):

| Signal | Condition | Class | Confidence |
|---|---|---|---|
| `backwardation` | VIX > VIX3M | stress-here / fade-vol / contrarian-bullish | high |
| `ts_flattening` | VIX/VIX3M > 0.95 and (VIX/VIX3M)[t−20] < 0.90 | early spike warning | medium |
| `exhaustion` | VIX ≥ 10d-high AND VVIX < its 10d-high AND VIX 252d-pct > 0.80 | bullish bounce / vol fade | medium |
| `double_floor` | VVIX < 85 AND VIX < 14 | complacent, slow vol-up | low/informational |
| `divergence` | VVIX z(60) > 1 AND VIX z(60) < 0 | (debunked) | **flagged low-confidence** |

**Output — `VolRegimeReport` (dataclass → dict):**
- `regime_label`: one of `contango_calm | backwardation_stressed | exhaustion | floor_complacent | mixed`
- `recommendation`: `{ stance: lean_puts | lean_calls | neutral | buy_the_bounce, conviction: low|medium|high, rationale: str }`
- `outlook`: expected VIX and SPY direction over 1/3/5/10d, as ranges drawn from the backtest conditional stats for the active signal(s)
- `timing`: see 3.3
- `signals`: list of `{ key, active: bool, value: float, confidence, hit_rate, blurb }`
- `inputs`: the live curve values + as-of timestamp + source

**Recommendation resolution (deterministic precedence):**
1. `backwardation` active → stance depends on horizon: short-term still-stressed (don't fight the spike) but 5d contrarian-bullish; report as `buy_the_bounce` (medium/high) with explicit "stress present" caveat.
2. else `exhaustion` active → `buy_the_bounce` / `lean_calls` (medium).
3. else `ts_flattening` active → `lean_puts` (medium) — rising-vol warning.
4. else `double_floor` active → `neutral` with "vol cheap, slow drift up; favor owning optionality" note (low).
5. else → `neutral`.
Conviction scales with signal strength (z-score / percentile depth) and agreement across signals.

### 3.2 Historical evidence — `backtest/vvix_vix_analysis/` (EXTEND)

Add `build_evidence.py` (or extend `analyze.py`) to emit **`evidence.json`** consumed by the engine. Per signal:
- `n` (sample size, # firings)
- `fwd_vix_{1,3,5,10}` mean %, `fwd_spy_{1,3,5}` mean %, with t-stats
- `hit_rate` — the fraction of firings where the signal's **defined call was correct** (see below)
- `base_rate` and `lift`
- `as_of` data range

**"Correct" definition per signal** (one canonical call each, so hit-rate is unambiguous):
- `exhaustion` correct ⇔ SPY up over next 3d (bounce realized).
- `backwardation` correct ⇔ SPY up over next 5d (fade/contrarian realized).
- `ts_flattening` correct ⇔ VIX rises ≥ +20% within next 5d (spike realized).
- `double_floor` correct ⇔ VIX higher in 10d (drift realized).
- `divergence` correct ⇔ VIX rises ≥ +20% within 5d (kept for honesty; expected near base rate).

`evidence.json` is committed so the page works without re-running the backtest. A `make`/script note documents regeneration.

### 3.3 Timing & expiration estimator — part of harness + engine (NEW)

For each signal, compute the **distribution of trading-days-until-its-event** across all historical firings:
- `exhaustion`: days until VIX falls ≥10% from signal-day close (within a 21d cap); secondary = day of SPY max-favorable-excursion within 21d.
- `backwardation`: days until VIX peaks then reverts ≥10% (the fade lands).
- `ts_flattening`: days until VIX first crosses +20% (the spike lands).
- `double_floor`: days until VIX first rises ≥20%.

Outputs per signal (in `evidence.json`, surfaced live by the engine):
- `timing_median`, `timing_p25`, `timing_p75` (trading days)
- `timing_cdf`: array of `P(event landed by day k)` for k = 1..21 (drives the timing chart)
- `suggested_dte`: derived as `ceil(p75 in calendar days) + theta_buffer` → mapped to a recommended expiration band (e.g. "10–14 DTE"). Buffer default = ~30% of p75, min 2 calendar days.
- `structure_note`: IV-regime-aware hint (e.g. exhaustion/high-VIX → prefer **call debit spread** over long calls to blunt IV crush; flattening/low-VIX → long premium fine).

The recommendation card shows **"Expected window: 3–8 trading days (median 5) · Target expiration ~10–14 DTE"**. The forward tracker (3.4) also scores whether the move landed **inside** the predicted window.

### 3.4 Forward tracking + scorer — `alphagex-db` + collector worker (NEW)

**Table `vol_advisor_log`:**
```
id              SERIAL PK
log_date        DATE UNIQUE        -- one row per trading day
vix, vvix, vix9d, vix3m, vix6m  REAL
regime_label    TEXT
stance          TEXT               -- lean_puts|lean_calls|neutral|buy_the_bounce
conviction      TEXT
active_signals  JSONB              -- which fired + values
predicted_dir   TEXT               -- spy_up|spy_down|vol_up|vol_down
horizon_days    INT                -- the signal's timing_median (or canonical horizon)
window_p75_days INT                -- predicted outer window
-- filled in later by the scorer:
realized_vix_chg, realized_spy_ret  REAL
event_landed_day  INT              -- actual trading-days-to-event (NULL if none in cap)
correct          BOOLEAN           -- call right/wrong by canonical definition
in_window        BOOLEAN           -- event landed within window_p75_days
scored_at       TIMESTAMPTZ
created_at      TIMESTAMPTZ DEFAULT NOW()
```

**Writer:** the `alphagex-collector` worker calls the engine once per trading day (after close) and inserts the snapshot (idempotent on `log_date`).

**Scorer:** same worker, daily pass over rows where `scored_at IS NULL` and whose horizon has fully elapsed; computes realized VIX/SPY outcome from CBOE/Yahoo history, sets `correct` / `in_window` / `event_landed_day`. Yields a live rolling-accuracy record per signal and overall.

### 3.5 Endpoints — `backend/api/routes/vix_routes.py` (EXTEND)

- `GET /api/vix/regime-advisor` → `{ report: VolRegimeReport, evidence: {per-signal backtest stats+timing}, live_record: {overall + per-signal accuracy, n_scored, n_in_window} }`. Computes the report live; reads evidence.json + a `vol_advisor_log` aggregate.
- `GET /api/vix/regime-advisor/history?days=180` → log rows + outcomes for the live-track-record chart/table.

Both reuse the existing fallback discipline in `vix_routes.py` (never throw; degrade to report-only if DB/log unavailable).

### 3.6 IronForge page — `ironforge/webapp/src/app/volatility/page.tsx` (NEW)

Thin proxy to the two endpoints (server route under `app/api/...` if IronForge needs to inject the AlphaGEX base URL, matching how `/gex` proxies). Sections:

1. **Header / regime** — regime label, live VIX/VVIX (with tick arrows), headline recommendation.
2. **Recommendation card** — stance, conviction, plain-English rationale, short-term meaning, **expected window + target expiration (DTE)**, structure note.
3. **Term-structure curve** — VIX9D·VIX·VIX3M·VIX6M plotted; contango vs backwardation read at a glance.
4. **VIX vs VVIX** — normalized (z-score) overlay + VVIX/VIX ratio, active-signal regions shaded.
5. **Timing chart** — cumulative `P(move landed by day k)` for the active signal, suggested-expiration band shaded.
6. **Signals panel** — one card per signal: active dot, current value, confidence, historical hit-rate; divergence visibly marked low-confidence.
7. **Historical accuracy table** (2006–2026) — N · fwd VIX% · fwd SPY% · hit-rate · t · median timing.
8. **Live track record** — rolling-accuracy chart since launch + table of recent calls → outcome (✓/✗, in-window ✓/✗).

**Visual standard:** custom SVG glyphs + refined typography; reuse IronForge's existing chart stack (recharts/d3 already in deps) and match `BriefingCard`/dashboard styling. No emojis/stock icons (per `feedback_no_cheap_visuals`).

### 3.7 Daily-brief hook — IronForge `BriefingMacroRibbon` + brief route (EXTEND)

Add a **vol-regime line** to the daily brief, sourced from `/api/vix/regime-advisor`: one paragraph — regime + recommendation + short-term outlook + target expiration. Advisory only; does not change any entry/exit logic. Degrade silently if the endpoint is unavailable.

## 4. Data flow (current report)

1. Page (or brief) calls `/api/vix/regime-advisor`.
2. Engine pulls live curve (CBOE, cached) + trailing history → computes signals, recommendation, outlook, timing.
3. Engine merges static `evidence.json` (backtest hit-rates + timing) and a `vol_advisor_log` accuracy aggregate.
4. Returns combined JSON; IronForge renders.
5. Independently, once/day after close, the collector snapshots the report into `vol_advisor_log` and scores matured rows.

## 5. Error handling

- Engine never raises to the route; on partial data it returns `regime_label=mixed`, `stance=neutral`, and flags which inputs were missing (consistent with existing `vix_routes` fallback).
- CBOE history fetch failure → fall back to live-curve-only signals that don't need percentiles (backwardation, flattening, exhaustion all use the curve / short windows; only z-score-based divergence degrades — acceptable, it's low-confidence anyway).
- DB/log unavailable → endpoint returns report + evidence with `live_record: null`; page hides the live-track section gracefully.
- Scorer is idempotent and resumable (keys on `scored_at IS NULL`).

## 6. Testing

- **Engine unit tests** (`tests/test_vol_regime_advisor.py`): synthetic curve inputs → asserts each signal fires on its boundary and the recommendation precedence resolves correctly; missing-input degradation path.
- **Evidence/timing parity**: a harness test asserts `evidence.json` regenerates to the same numbers (within tolerance) and that timing CDFs are monotonic and in [0,1].
- **Scorer test**: seeded `vol_advisor_log` rows with known forward series → asserts `correct` / `in_window` / `event_landed_day` computed correctly.
- **Endpoint smoke**: `/api/vix/regime-advisor` returns 200 with required keys against live CBOE (network) and in a no-DB fallback.
- **Page**: type-check + build (`next build`) green; manual check the 8 sections render with live data.

## 7. Scope / phasing

1. **Backend brain** — `vol_regime_advisor.py` + `evidence.json` (with timing) + `/api/vix/regime-advisor` + unit tests.
2. **Forward tracking** — `vol_advisor_log` table + collector writer/scorer + `/regime-advisor/history`.
3. **IronForge page** — `/volatility` with all 8 sections + charts.
4. **Daily-brief line** — vol-regime paragraph in `BriefingMacroRibbon`.

Each phase is independently shippable; 1 is the foundation.

## 8. Branch logistics

The IronForge source lives on `origin/main` (`ironforge/webapp/...`); local `main` is stale. The feature branch will be created from `origin/main` and the shipped VVIX-feed commit (`c3822a5b`, currently on `claude/vvix-cboe-live-feed`) cherry-picked/merged in, so both the backend feed and the IronForge app are present in one tree.

## 9. Non-goals (YAGNI)

- No auto-gating, sizing, or execution of any bot from these signals.
- No new options-pricing or auto order construction — the "structure note" and DTE are advisory text only.
- No intraday recompute in phase 1 (daily EOD cadence; the study is daily). Intraday refresh can come later if wanted.
- Not rebuilding the existing `/vix` co-pilot page; this is a separate IronForge `/volatility` page.

## 10. Open questions

- (resolved) Track record in alphagex-db — yes.
- (resolved) New `/volatility` page rather than folding into `/vix` — yes.
- Confirm whether IronForge needs a server-side proxy route (env-injected AlphaGEX base URL) or can call the public API base directly — verify against how `/gex` proxies during phase 3.
