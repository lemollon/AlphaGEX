/**
 * SPARK_FAVORABLE_UPSIZE — +1 SPARK contract, house-money-gated, on a
 * favorable-VIX day, for SPARK customer (sandbox mirror) accounts with a
 * deposit BELOW $7,500 only.
 *
 * Frozen by held-out backtest (Leron, 2026-09-27, "yes i want to add it"):
 * `dev/meltup/spark_addons_sim.py` / `RESULT_spark_addons.md`. Of every
 * add-on tested stacked on top of SPARK's own fast-start engine
 * (fast-start-sizing.ts, generalized for SPARK via
 * `{envVar:'SPARK_FAST_START'}`), only this favorable-day upsize passed —
 * and only at the $5,000 deposit: median $4,852 -> $6,000 held-out, 0 extra
 * floor breaches. It FAILED (below-deposit path count got worse) at $7,500
 * and $10,000, which is why this module hard-gates on deposit < $7,500 —
 * not a style choice, a documented pass/fail boundary. See also
 * `RESULT_spark_flint_separate.md`, which reuses this SAME <$7,500 boundary
 * as SPARK's baseline before layering FLINT's separate budget on top.
 *
 * THE RULE, PRECISELY (mirrors spark_addons_sim.py's upsize block exactly —
 * same budget SPARK's own fast-start engine already computed that day, read
 * off the `FastStartDecision` it returned, never re-derived):
 *   - Day must be a SPARK candidate day, favorable (VIX ratio <= 0.70,
 *     ebb-sizing.ts's isEbbFavorableVixDay/EBB_UPSIZE_VIX_RATIO_CEILING —
 *     reused as-is, same ceiling, same ratio construction), and SPARK's own
 *     per-contract max loss must be known (> 0).
 *   - Phase 1: gated on BOTH (a) cushion (equity - deposit) >= the extra
 *     lot's max loss, AND (b) the Phase-1 X%-of-deposit risk budget has
 *     room left AFTER SPARK's own (already-sized) contracts for the extra
 *     lot too. Two independent checks — matches spark_addons_sim.py's
 *     `phase1_alloc`'s own two-gate upsize block verbatim.
 *   - Phase 2: gated on cushion (equity - deposit) alone, AFTER SPARK's own
 *     contracts' cost — NOT the tighter K-floor budget. This is a real,
 *     deliberately looser gate than SPARK's own Phase-2 "extra" layer (see
 *     fast-start-sizing.ts's sizePhase2) — reproduced byte-for-byte from the
 *     sim, not tightened, because tightening it was never backtested.
 *   - The account's own ladder CAP (100, EBB_LADDER_CAP) still applies:
 *     the extra lot never pushes total SPARK contracts above the cap.
 *
 * PURE — no DB, no network. The caller (tradier.ts) supplies the
 * `FastStartDecision` SPARK's own sizing already produced this same tick
 * (so this module can never see a stale/inconsistent budget) plus this
 * day's SPARK max loss and favorable flag.
 */
import type { FastStartDecision } from './fast-start-sizing'

/** off|on, unset = off. */
export function isSparkFavorableUpsizeMode(): boolean {
  return (process.env.SPARK_FAVORABLE_UPSIZE ?? '').trim().toLowerCase() === 'on'
}

/** The settled pass/fail boundary from RESULT_spark_addons.md — deposit must be strictly below this. */
export const SPARK_UPSIZE_DEPOSIT_CEILING = 7500

/** True when `deposit` clears the settled pass boundary (< $7,500, never <=). */
export function isSparkUpsizeEligibleDeposit(deposit: number): boolean {
  return Number.isFinite(deposit) && deposit < SPARK_UPSIZE_DEPOSIT_CEILING
}

export interface SparkFavorableUpsizeInputs {
  /** The FastStartDecision SPARK's OWN sizing already produced this tick (same envVar/deposit/day). */
  decision: FastStartDecision
  /** This account's fixed deposit (state.deposit) — the SAME number the decision was computed from. */
  deposit: number
  /** Whether today is a SPARK candidate day at all (0DTE AM tranche entry window). */
  sparkCandidateDay: boolean
  /** This day's per-contract worst-case max loss for SPARK's own structure. null/<=0 = unreadable. */
  sparkMaxLossPerContract: number | null
  /** Prior-session VIX ratio <= 0.70 (ebbSizing.isEbbFavorableVixDay's own ceiling, reused). */
  favorable: boolean
  /** SPARK's static safety ceiling (EBB_LADDER_CAP = 100) — the extra lot may never cross it. */
  ladderCap: number
}

export interface SparkFavorableUpsizeResult {
  /** 0 or 1 extra SPARK contract. */
  upsizeContracts: 0 | 1
  /** Human-readable reason for the decision log. */
  reason: string
}

function isPositiveFinite(n: number | null | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n) && n > 0
}

/**
 * The upsize decision for one account, one day. Fails safe (0) on every
 * missing/invalid input, an ineligible deposit, an unfavorable day, a
 * non-candidate day, or SPARK_FAVORABLE_UPSIZE itself being off (checked by
 * the caller via isSparkFavorableUpsizeMode — this function does not read
 * env itself, so it stays trivially unit-testable with the flag implied on).
 */
export function decideSparkFavorableUpsize(inputs: SparkFavorableUpsizeInputs): SparkFavorableUpsizeResult {
  const { decision, deposit, sparkCandidateDay, sparkMaxLossPerContract, favorable, ladderCap } = inputs

  if (!sparkCandidateDay) {
    return { upsizeContracts: 0, reason: 'skip:spark_upsize(not_a_candidate_day)' }
  }
  if (!isSparkUpsizeEligibleDeposit(deposit)) {
    return { upsizeContracts: 0, reason: `skip:spark_upsize(deposit=$${deposit.toFixed(2)}>=$${SPARK_UPSIZE_DEPOSIT_CEILING} ceiling)` }
  }
  if (!favorable) {
    return { upsizeContracts: 0, reason: 'skip:spark_upsize(not_a_favorable_day)' }
  }
  const ml = isPositiveFinite(sparkMaxLossPerContract) ? sparkMaxLossPerContract : null
  if (ml === null) {
    return { upsizeContracts: 0, reason: 'skip:spark_upsize(maxloss_unreadable)' }
  }
  if (decision.ebbContracts + 1 > ladderCap) {
    return { upsizeContracts: 0, reason: `skip:spark_upsize(ladder_cap=${ladderCap} already at ${decision.ebbContracts})` }
  }

  if (decision.phase === 1) {
    if (decision.phase1CapBudget === null) {
      return { upsizeContracts: 0, reason: 'skip:spark_upsize(phase1_cap_budget_unavailable)' }
    }
    const cushion = decision.cushion
    const remainingCapBudget = decision.phase1CapBudget - decision.ebbContracts * ml
    if (cushion >= ml && remainingCapBudget >= ml) {
      return { upsizeContracts: 1, reason: `upsize:phase1(cushion=$${cushion.toFixed(2)}, remaining_cap=$${remainingCapBudget.toFixed(2)})` }
    }
    return {
      upsizeContracts: 0,
      reason: `skip:spark_upsize(phase1: cushion=$${cushion.toFixed(2)} or remaining_cap=$${remainingCapBudget.toFixed(2)} < maxloss=$${ml.toFixed(2)})`,
    }
  }

  // Phase 2 — gated on cushion (equity - deposit) alone, deliberately looser
  // than the K-floor budget (see file header).
  const remainingCushion = decision.cushion - decision.ebbContracts * ml
  if (remainingCushion >= ml) {
    return { upsizeContracts: 1, reason: `upsize:phase2(remaining_cushion=$${remainingCushion.toFixed(2)})` }
  }
  return {
    upsizeContracts: 0,
    reason: `skip:spark_upsize(phase2: remaining_cushion=$${remainingCushion.toFixed(2)} < maxloss=$${ml.toFixed(2)})`,
  }
}
