# 1DTE Directional Options Research — Design Spec

**Date**: 2026-05-10
**Status**: Spec — pending review
**Author**: Claude (with operator)
**Predecessor**: `2026-05-07-helios-1dte-directional-design.md` (NO-GO 2026-05-08)
**Branches**: `claude/touch-pin-validation` (Phase 1), `claude/skew-signal-validation` (Phase 2)

## 1. Purpose

Find a positive-expectancy 1DTE SPY directional/probabilistic options signal that closes positions **same day** — or rule it out empirically and stop. The HELIOS NO-GO of 2026-05-08 demonstrated that a GEX-magnet directional signal locks at ~63% directional WR, while every 1DTE SPY vehicle (debit *and* credit) needs ≥68% WR to break even. Tightening filters does not move the ceiling.

This spec defines a phased validation program built on two orthogonal hypotheses, with a confidence model attached to each. No production scaffolding is built until a phase produces evidence of edge.

## 2. Goal & non-goals

### Goal
Validate (or reject) two hypotheses, in order:
1. **Phase 1 (D, "intraday wall-gravity")** — for 1DTE SPY, debit verticals struck at the GEX wall have positive expectancy from open to ~15:55 ET, due to intraday gravity toward high-OI strikes.
2. **Phase 2 (A, "skew + charm stack")** — for 1DTE SPY, a directional signal built from intraday IV-skew dynamics + dealer charm pressure produces ≥66% WR, sufficient to break even on debit verticals after costs.

### Non-goals
- No production bot scaffolding (DB tables, routes, frontend, scheduler) until a phase produces GO.
- No overnight or T+1 holds — every position closes by 15:55 ET on the entry day.
- Non-SPY underlyings, longer DTE, naked single-leg vehicles — out of scope.
- Strategies dependent on intraday VIX / VVIX / live order-flow data not yet in the backtest DB.

## 3. Background

The HELIOS NO-GO (`docs/superpowers/specs/2026-05-07-helios-1dte-directional-design.md`, status memo `project_helios_intraday_walls_2026_05_08.md`) demonstrated a structural ~63% WR ceiling on the GEX-magnet directional signal across the full sweep of imbalance thresholds, PT/SL configs, and trail strategies. The best credit-vertical config landed at WR=57.8%, RR=1.44, BE=59.0%, EV=−$2.35/trade — essentially break-even, never positive.

The lesson was: tuning a structurally weak signal produces diminishing returns. The path forward is either (a) a different signal source orthogonal to magnets, or (b) a different question that does not require a 68% directional WR.

This spec pursues (b) first (Phase 1) and (a) second (Phase 2), with a confidence model in each.

## 4. Hypotheses

### Phase 1 — Intraday Wall-Gravity (D)

**Claim**: at minute 5 of day T, a 1DTE debit vertical struck at the call_wall (long leg AT wall, short leg one strike OTM) has positive expected PnL by 15:55 ET on day T, conditioned on a non-trivial subset of (magnet_imbalance, vix, distance_to_wall, regime) bins.

**Why it might work**: 1DTE is the most charm-dominated regime. Walls are high-OI strikes that act as gravitational targets for spot during the trading day before expiration. Intraday gravity toward the wall is a different effect from end-of-day pinning at expiration close — and same-day exit avoids overnight gap risk.

**Why it might not**: market-makers price this exact gravity into the vertical's entry debit. If priced perfectly, expected PnL is zero by definition. The edge — if any — is in regimes where the empirical gravity differs from the priced gravity.

**Confidence model**: bin-conditional empirical gap. Trade only bins where (1) historical mean PnL > +$5 after costs, (2) n_trades ≥ 30 in train, (3) OOS sign matches and magnitude is within ±50% of in-sample. The lookup table *is* the confidence model. No classifier.

### Phase 2 — Skew + Charm Stack (A)

**Claim**: a directional signal that fires only when (intraday skew is flattening AND dealer charm pressure agrees AND magnet imbalance agrees) achieves ≥66% WR on 1DTE SPY debit verticals, exited per HELIOS-tested PT/SL/trail rules with a hard time-stop at 15:55.

**Why it might work**: skew dynamics carry positioning information orthogonal to OI-magnets. Charm flows are theoretically grounded for short-dated options. Three orthogonal confirmers agreeing should lift WR by ~3pp over magnet-alone (which sat at 63%).

**Why it might not**: skew on 1DTE is noisy; pre-FOMC and event days produce artificial skew that does not reflect positioning. Charm and magnet may not be as orthogonal as the theory suggests.

**Confidence model**: composite z-score across the three confirmers, threshold-tuned via walk-forward. Single scalar.

## 5. Phasing

```
Phase 1 (D)     ──> GO ?  ──Yes──>  Phase 3 productize Phase 1 only
   harness                              (or proceed to Phase 2 for stack)
                  └──No──>  Phase 2 (A)  ──> GO ?  ──Yes──>  Phase 3 productize
                              harness                            Phase 2
                                          └──No──>  STOP. Document NO-GO.
```

Each phase ships a research artifact (markdown report + per-trade CSV), not a bot. Phase 3 productization is deliberately under-specified here — its shape depends on which phase passes and is decided post-GO with a follow-up spec.

## 6. Data inventory (verified 2026-05-10)

### Backtest-grade (2023-01-03 → 2025-12-05, 728 trading days)
- **`helios_options_intraday`** (production DB) — 11.83M rows. SPY 1DTE chain bid/ask + OHLCV at 1-min resolution. Schema: `(trade_date, expiration_date, strike, right, bar_time, open, high, low, close, volume, bid, ask)`. Spot derivable via put-call parity.
- **`orat_options_eod`** (backtest DB) — 5.56M SPY rows over 1,239 days. Full greeks + `call_iv` + `put_iv` per strike. Used for prior-day EOD context features.
- **`vix_history`** (backtest DB) — 1,496 rows, daily OHLC.

### Single-snapshot (limited)
- **`helios_options_oi`** (production DB) — exactly **one OI observation per `(trade_date, expiration)`**. Δ-OI overnight at the contract level requires a paired `orat_options_eod` lookup (not used in this spec; Δ-OI is not a Phase 1 or Phase 2 feature).
- **`regime_signals`** (production DB) — 10,036 rows over 5 years; ~1 row/day in 2023-24. Usable as a "today's regime label" feature (one-row-per-day join), **not** as an intraday signal source.

### Live-only (cannot drive 2023-25 backtest)
- `watchtower_order_flow_history` (3 mo, 2026-02 onward), `watchtower_snapshots` — useful for live-trading signal computation in Phase 3, not for Phase 1/2 backtests.

### Empty / unusable
- `vix_term_structure`, `forward_magnets`, `options_flow`, `regime_signals` (backtest DB), `price_history` (backtest DB) — schemas exist, **all 0 rows**. Not used in this spec.

### What we do NOT have
- No intraday SPY price data (must derive spot via parity from `helios_options_intraday`)
- No intraday VIX (use prior-day close)
- No VVIX or VIX9D / VIX3M term structure (`vix_term_structure` empty)
- No ThetaData OPTION.STANDARD bid/ask before 2023-01-03 (per HELIOS memo); backtest start is hard-floored at 2023-01-03

## 7. Phase 1 — Intraday Wall-Gravity harness

### 7.1 Module layout

```
backtest/touch_pin/
├── __init__.py
├── loader.py        # Pull (T, T+1) chain at minute 5 + OI; filter open-auction NaN
├── walls.py         # Re-export compute_intraday_walls from quant.walls
├── vehicle.py       # Build call/put vertical specs (long_K, short_K, entry_mid)
├── implied.py       # P_implied via BS Φ(d2) AND price/width — both reported
├── realized.py      # Per-minute spot via parity; touched_during_day; exit_mid at bar 385
├── engine.py        # Per-day orchestration; collects trade rows
├── binning.py       # Bucket trades by (magnet_imb, vix, distance, regime)
├── report.py        # Markdown writer + sensitivity battery
└── cli.py           # python -m backtest.touch_pin --start ... --end ...
```

### 7.2 Per-day flow

```
For T in days [2023-01-03 .. 2025-12-05]:

  [09:35 ET] Pull chain @ minute 5
    SELECT FROM helios_options_intraday
      WHERE trade_date=T AND expiration_date=T+1 AND bar_time=T 13:35Z
    SELECT FROM helios_options_oi
      WHERE trade_date=T AND expiration_date=T+1
    spot_5 = put-call parity at most-ATM strike

  Compute walls (compute_intraday_walls from existing quant.walls)
    call_wall, put_support, flip_point
    magnet_imbalance = call_peak / put_peak

  Build candidate verticals
    PIN-CALL: long call @ call_wall,    short call @ call_wall + 1 pt
    PIN-PUT:  long put  @ put_support,  short put  @ put_support - 1 pt
    Entry mid = mid_long − mid_short  (from same minute-5 bar)
    Skip side if either leg has bid=0 or ask=0 or width > 5pt

  Compute implied P(direction-favorable) — both methods
    Method 1: BS Φ(d2) at long-strike, σ from leg IV
    Method 2: P_implied = entry_mid / vertical_width
    Cross-check: |M1 - M2| < 0.05; if not, log warning

  [09:36 → 15:55 ET] Walk minute bars
    For each minute, compute parity-spot from the pair of strikes nearest spot
    Record:
      touched_during_day = 1 if any minute spot crossed past long_K
      time_first_touch    = bar_time of first cross (NULL if never)

  [15:55 ET, bar 385] Exit
    exit_mid = mid_long(385) − mid_short(385)
    Skip trade if either leg has bid=0/ask=0 at bar 385 (record reason)

  Realize PnL
    pnl_gross = exit_mid − entry_mid
    slippage  = 2 ticks (1 per leg) = $0.02
    commission = $5.20 (4 legs total: 2 to open, 2 to close, $1.30/contract)
    pnl_net   = pnl_gross − slippage − commission

  Append row to trades.csv:
    (T, side, long_K, short_K, width, entry_mid, exit_mid,
     spot_5, spot_close, vix_close_T-1, magnet_imbalance,
     distance_pct, regime_label, implied_method1, implied_method2,
     touched_during_day, pnl_net)
```

### 7.3 Bin scheme

| Dimension | Buckets |
|---|---|
| `magnet_imbalance` | `<1.2`, `1.2-1.5`, `1.5-2.0`, `>2.0` |
| `vix_close_T-1` | `<15`, `15-20`, `20-30`, `>30` |
| `distance_to_wall_pct` | `<0.3%`, `0.3-0.6%`, `>0.6%` |
| `regime_label` | from `regime_signals` (T-1 latest row); fallback `"unlabeled"` |

Per bin: `n_trades`, `mean_pnl`, `median_pnl`, `std_pnl`, `win_rate`, `mean_touched_pct`, `mean_implied_method1`, `mean_implied_method2`.

### 7.4 GO criteria — frozen before run

A bin (or set of bins) qualifies for GO if **all four** hold:

1. **Sample integrity**: n ≥ 30 trades in 2023-24 train; n ≥ 15 in 2025 OOS.
2. **Edge size**: bin mean PnL ≥ **+$5 per vertical** after 2 ticks slippage + $5.20 commission.
3. **OOS stability**: 2025 mean PnL same sign as 2023-24 mean, magnitude within ±50%.
4. **Per-trade Sharpe**: ≥ 0.3 in qualifying bins (mean_pnl / std_pnl).

**Aggregate GO**: ≥100 trades distributed across qualifying bins, **and** at least one of {pin-call, pin-put} has a qualifying bin (or one direction has ≥150 trades qualifying).

If any of (1-4) fails for both directions → **NO-GO Phase 1, pivot to Phase 2.**

### 7.5 Sensitivity battery (every report)

Each report runs and shows side-by-side:
- Slippage: 0 ticks / 1 tick / 2 ticks per leg
- Fill assumption: mid / cross-spread
- Entry minute: 5 / 10
- Exit minute: 380 (15:50) / 385 (15:55) / 389 (15:59)
- Excluding 2024 (regime drop-out check)

GO requires the result to hold across the full battery, not just baseline.

## 8. Phase 2 — Skew + Charm Stack harness

### 8.1 Module layout

```
backtest/skew_signal/
├── __init__.py
├── loader.py
├── iv_solver.py     # Wraps quant.bs IV solver; per-strike IV from bid/ask mid
├── skew.py          # 25Δ skew, ATM-vs-wing slope, Δskew_15m
├── charm.py         # Per-strike charm; aggregate (charm × OI) per side
├── signal.py        # BULL/BEAR/NONE rule + composite z-score
├── engine.py        # Wraps existing helios_intraday._simulate_intraday + time-stop at 385
├── binning.py
├── report.py
└── cli.py
```

### 8.2 Per-minute flow

```
For T in days, for M in [09:35 .. 14:00 ET]:

  Pull all 1DTE SPY quote bars at minute M
  Solve σ per strike via NR on bid/ask mid (quant.bs)

  Compute features:
    skew_25d_M      = put_iv@25Δ − call_iv@25Δ
    skew_slope_M    = (skew_25d_M − skew_10d_M) / 15Δ
    delta_skew_15m  = skew_25d_M − skew_25d_(M−15)
    charm_call_M    = Σ (charm × OI) over OTM calls (delta in [0.10, 0.40])
    charm_put_M     = Σ (charm × OI) over OTM puts  (delta in [-0.40, -0.10])
    magnet_imb_M    = call_gex_peak / put_gex_peak  (reuse quant.walls)
    vix_T-1         = vix_history close on prior day
    regime_label    = regime_signals (T-1 latest)

  Signal:
    BULL if  delta_skew_15m < −θ_skew  AND  charm_call_M > θ_charm  AND  magnet_imb_M ≥ 1.3
    BEAR if  delta_skew_15m > +θ_skew  AND  charm_put_M  > θ_charm  AND  magnet_imb_M ≤ 1/1.3
    else NONE

  composite_z = sign × (skew_z × charm_z × magnet_z)

  If signal fires:
    Vehicle: 1DTE call/put debit vertical (long ATM, short 1-strike OTM)
    Simulate via existing helios_intraday._simulate_intraday(PT=20, SL=30, trail=5/8)
    + hard time-stop at bar 385 if not stopped/targeted
    Record exit reason (PT / SL / trail / time-stop)
    Append trade
```

One signal per day max — if multiple minutes fire, take the first.

### 8.3 GO criteria — frozen before run

1. **n ≥ 150** trades over 728 days
2. **WR ≥ 66%** (HELIOS hit 63% — 3pp lift gets us within striking distance of break-even)
3. **RR ≥ 1.5**, **post-cost EV ≥ +$5 per trade**
4. **Walk-forward**: train (θ_skew, θ_charm) on 2023-24, validate on 2025 — degradation ≤ 5pp WR

Additional health check (informational, not GO-blocking):
- **% time-stop exits ≤ 40%** — if more than 40% of trades end in time-stop, the signal is not decisive enough; report findings but flag.

If all four pass → **GO Phase 2, proceed to Phase 3 productize.**

## 9. Phase 3 — Productize (post-GO)

Out of scope for this spec. Documented here for context only.

If Phase 1 or 2 returns GO, a follow-up spec will define the productization. Decisions deferred to that spec:
- Reuse the existing HELIOS scaffolding (8 DB tables, 13 routes, frontend page on `claude/helios-1dte-directional-design`) by swapping the signal module — OR start a sibling bot.
- Confidence model attachment: bin lookup (Phase 1), composite z (Phase 2), or calibrated classifier (if both fire).
- Live signal computation: ThetaData polling for intraday quote bars + OI; production deploy shape.

## 10. Reuse strategy

The HELIOS branch (`claude/helios-1dte-directional-design`, unmerged) ships these proven primitives:
- `backtest/intraday_walls/bs.py` — BS pricer + IV solver (Newton-Raphson + Brent fallback)
- `backtest/intraday_walls/walls.py` — `compute_intraday_walls(...)` and parity-spot derivation
- `backtest/helios_intraday/_simulate_intraday(...)` — trade simulation with PT/SL/trail

**Strategy**: promote `bs.py` and `walls.py` to a shared `quant/` module on this branch (`claude/1dte-research-design`) so both Phase 1 and Phase 2 import from one place. The HELIOS branch stays dormant; we don't merge or delete it. The existing `_simulate_intraday` is reused as-is for Phase 2 (Phase 1 doesn't need it — it's a single open/close pair, not a stop/target simulation).

Promotion plan:
- `quant/bs.py`     ← copied from `backtest/intraday_walls/bs.py`
- `quant/walls.py`  ← copied from `backtest/intraday_walls/walls.py` (with parity-spot helper)
- The HELIOS branch's local copies remain; they are bit-identical to the new `quant/` versions and continue to work if HELIOS is ever revived.

## 11. Validation methodology

### 11.1 Walk-forward splits (frozen)

| Split | Days | Phase 1 use | Phase 2 use |
|---|---|---|---|
| Train | 2023-01-03 → 2023-12-29 (~250) | Bin discovery | Parameter grid search |
| Validation | 2024-01-02 → 2024-12-31 (~250) | Bin selection | Parameter selection |
| **OOS (untouched until final)** | 2025-01-02 → 2025-12-05 (~228) | Final test | Final test |

**Phase 1 (no parameters)**: bin selection picked from Train+Validation union. **Freeze** the bin set, then run on 2025 OOS. GO requires 2025 metrics pass §7.4 criterion (3) for each frozen bin.

**Phase 2 (θ_skew, θ_charm)**: grid search on Train, validate on Validation, **freeze parameters**, test on 2025. GO requires 2025 WR within 5pp of validation WR.

### 11.2 Anti-look-ahead discipline

Enforced as assertions in `loader.py` and `engine.py`:
1. Bin features only use minute-5 (Phase 1) or minute-M (Phase 2) data — never post-entry information.
2. `regime_label` uses the latest `regime_signals` row with `timestamp <= T 09:30 ET`.
3. `vix` uses prior-day close from `vix_history` (no intraday VIX in our data).
4. `magnet_imbalance` is computed from the chain at decision-time minute. ✓
5. EOD spot is read only after the trade row is logged.
6. The OOS slice (2025) is not loaded by `binning.py` or `signal.py` parameter-tuning code paths; it is loaded only by the final-evaluation pass after parameters/bins are frozen.

## 12. Testing strategy

### Unit tests (per module, deterministic synthetic fixtures)

Phase 1:
- `test_implied.py` — known BS roundtrip (price → IV → price → P(d2)); both implied methods agree within 0.05 on synthetic case
- `test_realized.py` — synthetic chain with known wall-touch pattern; assert `touched_during_day` & exit_mid correct
- `test_walls_integration.py` — match a specific date's walls (e.g., 2024-06-04) vs the existing HELIOS recorded output

Phase 2:
- `test_iv_solver.py` — synthetic price → IV → price roundtrip within 1e-4
- `test_skew.py` — flat-skew chain → 0 skew; put-heavy → positive 25Δ skew
- `test_charm.py` — known SPY 1DTE strike → known charm value (cross-checked vs textbook)
- `test_signal.py` — feature combinations → expected BULL/BEAR/NONE

### Integration smoke (5-day mini-run, both phases)

Run on `2024-06-03 → 2024-06-07`. Assertions:
- ≤ 5 trades for Phase 1; ≤ 5 trades for Phase 2
- All trades have valid entry/exit prices (no NaN)
- All bin labels populated
- CSV schema matches spec exactly
- Re-run produces byte-identical output (determinism check)

### Regression pin

Lock 2024-06-04's exact output (entry_mid, walls, implied_method1, implied_method2, exit_mid, pnl_net) — any code change must reproduce or explicitly update via `pytest --update-fixtures`.

### Sensitivity battery (built into report.py — runs every report)

See §7.5. GO requires result to hold across the full battery.

## 13. Confidence model — summary across phases

| Phase | Confidence model | Trade gate |
|---|---|---|
| Phase 1 | Bin-conditional empirical lookup table (no classifier) | Trade only bins with frozen mean_pnl > +$5 AND OOS-stable |
| Phase 2 | Composite z-score `sign × skew_z × charm_z × magnet_z` | Trade only when `composite_z > θ_z` (tuned on Train, frozen on OOS) |
| Phase 3 (post-GO) | Calibrated logistic on `[bin_pnl, composite_z, vix, regime_label, magnet_imb]` if both phases fire; else use winner's native model | Spec'd post-GO |

The confidence model is **not** an afterthought — it is the gate that decides whether to fire a trade. Each phase's GO bar is calibrated assuming the confidence model is in use (e.g., Phase 1 GO requires bin filtering, not whole-population trading).

## 14. Risks & failure modes

### Sample shrinkage
After bin filtering, qualifying-bin trade counts may be too low for stable inference. Mitigation: GO bar requires n ≥ 30 in train + n ≥ 15 in OOS per qualifying bin; aggregate ≥100. If the union of qualifying bins falls under 100, declare NO-GO regardless of per-bin metrics.

### Look-ahead leakage
Walk-forward CV is mandatory; OOS slice is hard-frozen until final evaluation. Code-enforced assertions (§11.2). Risk: regime_signals join could leak future state if `timestamp` semantics are misread — the loader's regime-join must use `timestamp <= T 09:30 ET` strictly.

### Regime drift
2024 had two distinct regime breaks (Aug VIX spike, Q4 election). Sensitivity battery includes a "exclude 2024" run to check signal stability across regimes. If GO depends on 2024 alone, it is not GO.

### Slippage / fill realism
Mid-fill is optimistic. Sensitivity battery requires GO at 2 ticks/leg slippage. If GO depends on mid-fill, it is not GO.

### Phantom edge from data quality
ThetaData OPTION.STANDARD bundle had quote-bar gaps before 2023-01-03 (per HELIOS memo). Our backtest start is hard-floored at 2023-01-03. Risk: even within 2023-25, there may be sparsely-quoted minutes near close. Mitigation: skip-trade rule when bid=0/ask=0 at entry or exit; log skip count in report.

### 1DTE on FOMC / NFP / event days
Pre-event skew is artificial. Phase 2 will report signal counts and PnL on FOMC days separately; if FOMC days dominate the loss tail, add a same-day-event blocker (informational, not Phase-2-GO-blocking on first pass).

## 15. Success criteria summary

| Phase | n | Edge metric | OOS test | Sensitivity |
|---|---|---|---|---|
| Phase 1 | ≥100 across qualifying bins | bin mean PnL ≥ +$5/trade | sign matches; magnitude within ±50% | survives 2-tick slippage, 15:50 exit, no-2024 |
| Phase 2 | ≥150 over full window | WR ≥ 66%, RR ≥ 1.5, EV ≥ +$5 | WR within 5pp of validation | same |

## 16. Out-of-scope decisions deferred to plan / implementation

- Specific θ_skew, θ_charm grid ranges (decided in Phase 2 implementation)
- Bin boundary tuning (current spec uses round numbers; plan may refine)
- Whether to ship a NO-GO report as a project memo
- Branch strategy beyond `claude/touch-pin-validation` and `claude/skew-signal-validation` (e.g., do they merge to main as research artifacts?)

## 17. Approval to proceed

Once approved, the next step is to invoke the writing-plans skill to produce a concrete step-by-step implementation plan for **Phase 1 only**. Phase 2 gets its own plan only if Phase 1 returns NO-GO or if the operator decides to build the stack regardless of Phase 1 outcome.
