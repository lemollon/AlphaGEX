# BLAZE GEX-on-0DTE Backtest — Design

**Date:** 2026-05-24
**Status:** Design (awaiting review → implementation plan)
**Owner:** Leron Mollon

## Summary

Reconstruct GEX walls historically from the option chain and backtest BLAZE's
**actual production signals** (`wall_fade`, `wall_break`, `flip_cross`) on **0DTE
SPY**, using the newly-backfilled 1-min 0DTE data (850 sessions, 2023-01-03 →
2026-05-22). Goal: a clean GO/NO-GO on whether the production GEX directional
thesis is profitable on 0DTE — data the strategy has never been tested against.

## Context & Motivation

- **Production BLAZE is GEX-driven.** Live BLAZE trades ATM $1-wide debit
  verticals triggered by `wall_fade`/`wall_break`/`flip_cross` (see
  `ironforge/webapp/src/lib/blaze/setups.ts`, port of `trading/helios/setups/`).
  Live results are poor (~29% WR over 14 trades; losses are SL-on-adverse-move,
  not slow-to-PT — see memory `project_blaze_atm_loss_analysis_2026_05_24`).
- **Pre-computed GEX is not stored historically** (`gex_snapshots*` empty,
  `gex_history` sparse) — so we cannot replay the signal from stored snapshots.
- **But GEX is reconstructable from the chain**, and the code already exists:
  `backtest/intraday_walls/walls.py` (call/put walls + flip from per-strike
  gamma×OI) and `backtest/intraday_walls/bs.py` (spot-from-parity, IV, BS gamma).
- **Prior GEX backtests NO-GO'd — but never on 0DTE.** `intraday_walls` reached
  ~63% WR (< the ≥68% 1DTE bar); JOSHUA replay starved on missing NEGATIVE-regime
  data; touch-pin (29%) and skew+charm (19.5%) also NO-GO. The `intraday_walls`
  note flags the machinery as *"salvageable for future 0DTE strategies."* This
  spec is that un-done experiment.

## Scope Decision (confirmed)

**Local band first.** Reconstruct walls + approximate regime from the **ATM±10**
strikes already in `helios_options_intraday` (plus a quick 0DTE OI re-pull).
Fast, reuses existing code, gets a read on whether 0DTE walls have *any* edge
before investing in a full-board backfill. **Full-board faithful reconstruction
(true net-GEX + regime across all strikes/expirations) is an explicit future
upgrade, only if the local test is promising.**

## Data

- **Prices:** `helios_options_intraday`, 0DTE rows (`expiration_date = trade_date`),
  850 sessions, ATM±10 strikes × C/P, 1-min OHLC + bid/ask.
- **Open interest:** re-run `scripts/backfill_thetadata_oi.py` (Terminal up) to
  pull OI for the new 0DTE contracts — it iterates every contract already in
  `helios_options_intraday`, so it backfills the 0DTE strikes into
  `helios_options_oi`. OI is one value/contract/day (OPRA EOD).
- Conservative fills throughout: **buy at ask, sell at bid.**

## GEX Reconstruction (local band)

Per `(trade_date, minute)` on the same-day expiration, via `walls.py` + `bs.py`:

1. **Spot** — derive from put-call parity at the ATM strike (`derive_spot_from_parity`).
2. **Per-strike IV** — back out from mid prices (`implied_vol`).
3. **Per-strike gamma** — Black-Scholes (`bs_gamma`) at (spot, K, T-to-close, IV).
4. **Walls** — `call_wall` = strike with max call gamma×OI above spot;
   `put_wall` = max put gamma×OI below spot; `flip_point` = where net gamma
   flips sign.
5. **Regime (approximation)** — from the sign/magnitude of summed net-gamma over
   the band: positive → MODERATE/HIGH/EXTREME_POSITIVE (pinning/fade), negative →
   the NEGATIVE tiers (momentum/break). Thresholds calibrated on the data.
6. **σ-band** — ATM IV × √(T-to-close), to feed the setups' expected-move gate.

This produces a `GexSnapshot`-shaped object per minute (spot, net_gex, flip_point,
call_wall, put_wall, regime, sigma_1d_band_width).

> **Known fidelity limitation:** band-local net-gamma is an approximation of
> production's full-board GEX. Regime classification is the least faithful piece
> (it's the gap that starved JOSHUA). Reported per-regime so we can see whether
> NEGATIVE-regime days appear at all on 0DTE.

## Signal

Reuse the **real** setup logic (`trading/helios/setups/{wall_fade,wall_break,
flip_cross}.py`) via the existing `backtest/joshua_replay` harness, fed the
reconstructed snapshot each minute. Honor production's per-setup daily caps and
the signal-reset/one-position-at-a-time semantics. `wall_fade` is expected to
dominate on 0DTE (positive-gamma pinning); `wall_break`/`flip_cross` fire only if
NEGATIVE-regime minutes are reconstructed.

## Trade Structure & Sizing

- **Structure:** ATM $1-wide debit vertical in the setup's direction (long
  `round(spot)`, short ±1) — identical to live BLAZE.
- **Sizing:** **1 contract** in the backtest for clean EV. Kelly/BP sizing is a
  post-GO concern, not part of this experiment.

## Exit Logic & Fills

- **Entry:** on the trigger minute, debit = long ask − short bid (worst-case).
- **Exit trigger (grid):** PT at X% of debit, SL at Y% of debit. The PT/SL
  threshold is *evaluated* each 1-min bar against the spread's mark
  (long mid − short mid), matching production's monitor; once triggered, the
  **fill** is taken at the conservative close (sell long bid − buy short ask).
- **Hard EOD/expiry close:** 0DTE settles at 4 PM ET — if held to expiry,
  P&L = intrinsic value of the vertical − debit (no fill slippage at settlement).

## Backtest Harness & Code Reuse

- Extend `backtest/joshua_replay` (or a thin new `backtest/blaze_gex_0dte/`) to:
  iterate 0DTE sessions → reconstruct snapshots (`walls.py`) → run setups →
  simulate the vertical's fills/exits on the 0DTE bars → record trades.
- Pure functions where possible (reconstruction, signal eval, exit decision) for
  unit testing; DB I/O isolated.

## Parameter Grid

- Opening/entry window cutoffs (e.g., no new entries after 1:30 / 2:00 PM ET).
- PT ∈ {20, 30, 50}% of debit; SL ∈ {30, 50, 100}% of debit.
- Regime thresholds for the positive/negative classification.
- (Setup-internal thresholds — `wall_fade_em_threshold` etc. — held at production
  defaults first, then sensitivity-checked.)

## Outputs / Metrics

Per setup × config: **trades, win rate, EV/contract, total P&L, max drawdown,
profit factor**, plus **per-year (2023/24/25/26)** and **per-regime** breakdowns.
Persist results to a backtest table + a summary the dashboard/EMBER can read.

## GO / NO-GO Criteria

- **GO:** EV/contract > 0 net of conservative fills, **positive in every year**,
  **profit factor > 1.2**.
- **WR** reported against the ~68% 1DTE reference as context (wall_fade is
  mean-reversion, so WR is more load-bearing than for a breakout debit spread,
  but EV/PF is the decision metric).
- **NO-GO** → document why (which setups, which regimes/years failed) and stop;
  do not tune thresholds into a backtest-overfit. Per memory
  `feedback_blaze_collect_data_first`, BLAZE stays frozen unless a result clears
  this bar honestly.

## Out of Scope (this pass)

- Full-board / multi-expiration OI backfill and true net-GEX (future upgrade).
- 1DTE re-test (already NO-GO'd; revisit only if 0DTE shows edge).
- Live-bot wiring, Kelly sizing, dashboard changes — all post-GO.

## Risks & Known Limitations

1. **Regime fidelity** — band-local approximation; may mis-class positive/negative,
   suppressing `wall_break`/`flip_cross` (as in JOSHUA). Mitigated by per-regime
   reporting + the full-board upgrade path.
2. **0DTE liquidity/quotes** — wide bid/ask near expiry can make conservative
   fills pessimistic; report fill assumptions and a mid-fill sensitivity.
3. **Survivorship/holiday gaps** — 4 known 2026-holiday no-data days; benign.
4. **Overfitting the grid** — guard with per-year robustness in the GO bar.
