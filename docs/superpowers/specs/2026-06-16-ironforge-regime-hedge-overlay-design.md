# IronForge Regime-Gated Hedge Overlay — Design

**Date:** 2026-06-16
**Status:** Proposed (analysis done; calibrating before build).
**Motivation:** SPARK (live) took multi-day drawdowns — May 20 −$1,092, Jun 05 −$1,442, Jun 09 −$1,218 — and the volatility regime engine *was* flagging those days (ts_flattening / backwardation fired Jun 05 + Jun 09) but the warning was informational only, flapped intra-cycle, and nothing hedged. Goal: convert the existing regime signal into a **sized, far-dated hedge** placed only on flagged days.

## 1. What already exists (reuse, don't rebuild)
- **Regime engine** (`lib/volatility.ts` + AlphaGEX `/api/vix/regime-advisor`): regimes backwardation_stressed / contango_flattening / exhaustion / floor_complacent / contango_calm, from VIX, VVIX, VIX9D/3M/6M term structure. Signals: backwardation, ts_flattening, exhaustion, double_floor, divergence(VVIX).
- **Seller tail-risk WARN** (`lib/volAlerts.ts`, `botVolMessage`): backwardation/ts_flattening → "*~4× next-day tail risk for short premium — halt new ICs or widen wings*". **This is the hedge trigger condition, already defined.**
- **Intraday IC-risk tiles** (`lib/risk-signals.ts`): IV-rank, VIX rate-of-change, strike distance (σ), realized-vs-expected move.

## 2. Gaps to fix (regime-engine review)
1. **Flapping** — alerts fire/resolve within one 5-min cycle. → Compute a **once-daily latched regime read** pre-market (~8:25 CT), held for the session. Hedge decisions key off the latch, not per-cycle alerts.
2. **Empty history** — `/api/volatility/history` returns `{"rows":[]}`; the daily scored history isn't persisting. → Persist a daily `regime_daily` row (regime, signals, VIX/VVIX/term-structure, hedge decision, realized next-day SPY/VIX) so the trigger is **backtestable**.
3. **Informational only** — no action emitted. → Emit a concrete hedge order.

## 3. Strategy: regime-gated SPY put debit spread
**Don't hedge every day.** Hedge ON for the session iff the daily-latched regime trips ANY:
- regime ∈ {backwardation_stressed, contango_flattening}, OR signal `ts_flattening`/`backwardation` active (the existing seller-WARN), OR
- VIX > VIX3M (backwardation), OR VVIX ≥ ~115 and rising, OR IV-rank elevated with VIX ROC up.
- Calm contango (e.g. today: contango_calm, VIX 16.2, VVIX ~88) → **no hedge**.

**Instrument:** SPY **put debit spread, 30–45 DTE** (buy long leg ~1–1.5% OTM for same-day responsiveness; sell short leg ~5–6% OTM). Far-dated so it survives a multi-day hostile regime and can be **rolled**, and **closed when the regime flips back to contango_calm**. (VIX call spread is a noted alternative for pure vol-of-vol spikes; deferred.)

**Why a debit spread:** the IC's loss is bounded (≈ width − credit), so a bounded-payoff spread is the natural match — full payoff coverage at a fraction of a naked put's cost.

**Sizing (coverage ≈ 100% of the day's tail):**
- `daily_tail = Σ active bots' planned max-loss` (SPARK IC ≈ (width − credit) × contracts × 100 ≈ the ~$1,200 observed on bad days; add FLAME/INFERNO/BLAZE when live-relevant).
- Choose spread **width × 100 × contracts ≈ daily_tail** so MAX payoff ≈ the tail.
- Expected **cost ≈ 25–35% of width** (OTM, 30–45 DTE). Worked example at SPY ≈ $742, daily_tail ≈ $1,200:
  - Buy **~$730 put** (−1.6%) / sell **~$717 put** (−3.4%), width $13 → **max payoff ≈ $1,300** per spread; net debit ≈ **$350–450**.
  - Single-day realized on a −1.5% / vol-spike day ≈ $250–400 (delta + vega); approaches the full $1,300 if the down-move persists across the regime — i.e. it **balances the account over the hostile stretch**, the May/June failure mode.
- **Drag control:** only paid on flagged days (~20–30% of sessions historically), and closed when the regime clears, so calm-day drag ≈ 0.

## 4. Architecture
- **Hedge Advisor** (server, `lib/hedge/advisor.ts`): pure-ish function `(latchedRegime, bots' planned capital, SPY/VIX quote, chain) → HedgePlan { hedge:boolean, reason, long_strike, short_strike, dte, contracts, est_debit, est_max_payoff, est_sameday_offset }`. Pure decision core unit-tested; chain/quote I/O at the edge.
- **Daily latch + persistence**: pre-market job writes `regime_daily` (latched regime + hedge decision); the advisor reads the latch.
- **Surface**: `/volatility` page + bot dashboards show "Hedge today: BUY SPY 30D 730/717 put spread ×N (~$X, covers ~$Y)". 
- **v1 advisory** (operator places it). **v2 auto-place** via the SPARK Tradier production account — reuses the brokerage/Tradier order plumbing already built; same per-trade-approval option.

## 5. Compliance / safety
- Hedge orders are real-money on the SPARK live account → v2 gated behind the same approval + risk controls as the bots; never auto-place without an explicit enable + sizing cap.
- Display-/advisory-only in v1: zero trading-logic change to the bots.

## 6. Open questions / calibration
- Confirm `daily_tail` aggregation across which bots are live (SPARK only today; FLAME/INFERNO/BLAZE are paper — include their planned risk or SPARK-only?).
- Roll/close rules: close hedge when regime → contango_calm for N consecutive reads; roll at ≤14 DTE.
- Backtest the trigger against persisted history once it accrues (and a one-time historical backfill from VIX/VVIX data if available) to measure: flagged-day hit rate, avg loss saved, total hedge cost.
- VIX-call-spread variant as a second instrument (deferred).

## 7. Acceptance criteria (v1 advisory)
1. Daily-latched regime read (no flapping) drives a stable per-session hedge decision.
2. `regime_daily` persists the regime + hedge decision + realized next-day move.
3. Hedge Advisor emits a concrete SPY put-debit-spread plan (strikes/DTE/contracts/cost/payoff) sized to ~100% of the day's aggregate tail, only on flagged days; nothing on calm days.
4. Surfaced on `/volatility` + bot dashboards. No bot trading-logic change.
