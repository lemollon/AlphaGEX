/**
 * SPARK_FLINT — FLINT (the SPY 0DTE call credit spread, flint.ts) traded on
 * SPARK customer accounts with its OWN separate, profits-only budget.
 *
 * Frozen by held-out backtest (Leron, 2026-09-27, "Leron-approved follow-up"
 * per the sim's own header): `dev/meltup/spark_flint_separate_sim.py` /
 * `RESULT_spark_flint_separate.md`, variant (a) — fixed 1 lot, profits-only,
 * PASSES at all three tested deposits ($5,000/$7,500/$10,000): held-out
 * median $6,000 -> $6,196 at $5,000 (and similarly positive at $7,500/
 * $10,000), 0 extra floor breaches, FLINT profitable 91-92% of the time on
 * days SPARK itself lost money.
 *
 * WHY SEPARATE FROM spark_addons_sim.py's shared-budget version: folding
 * FLINT's own max loss into SPARK's Phase-1->Phase-2 TRIGGER (the design
 * `RESULT_spark_addons.md` tested first) delayed SPARK's own, better-paying
 * Phase-2 access more than FLINT's edge made up for — every shared-budget
 * add-on FAILED for that reason. This module touches NOTHING about SPARK's
 * own fast-start trigger or sizing (fast-start-sizing.ts, called with
 * `{envVar:'SPARK_FAST_START'}`, is 100% unaware FLINT exists): FLINT here
 * only ever spends money the account has ALREADY made (profit above
 * deposit — evaluateFlintProfitGate, reused byte-for-byte from flint.ts, the
 * SAME rule R1 gate FLAME's own FLINT sleeve uses), and the ONE thing this
 * module adds on top is the account-level safety net below.
 *
 * THE SAFETY NET (the one piece NOT already in flint.ts): if the day's
 * COMBINED cost (SPARK's own already-sized contracts' max loss + FLINT's 1
 * contract) could push equity below the account's CURRENT floor (deposit in
 * Phase 1, the ratcheted CPPI floor in Phase 2 — `decision.floor` from
 * SPARK's own fast-start decision, read fresh every call, never a second
 * source of truth), FLINT is dropped for that day. SPARK's own count is
 * NEVER reduced to make room — matches the task spec ("drop FLINT first")
 * and spark_flint_separate_sim.py's own construction exactly
 * (`if n_flint>0 and (spark_cost+flint_cost) > (equity-floor_level): n_flint=0`).
 *
 * PURE — no DB, no network. The caller (placeCallSpreadOrderAllAccounts,
 * tradier.ts) supplies this SAME account's already-decided SPARK contract
 * count and floor for TODAY (computed once, earlier in the same scan tick,
 * by the SPARK ladder branch) so this module can never see a stale budget.
 */
import { evaluateFlintProfitGate, type FlintProfitGateResult } from './flint'

/** off|on, unset = off. */
export function isSparkFlintMode(): boolean {
  return (process.env.SPARK_FLINT ?? '').trim().toLowerCase() === 'on'
}

/** Fixed size for this sleeve on SPARK accounts — never laddered, matching FLINT's own FLAME-side rule. */
export const SPARK_FLINT_MAX_CONTRACTS = 1

export interface SparkFlintBudgetInputs {
  /** This account's current equity (this SAME cycle's read). */
  equity: number
  /** This account's fixed deposit (state.deposit) — the profits-only floor for rule R1. */
  deposit: number
  /** SPARK's OWN current floor for TODAY (decision.floor: = deposit in Phase 1, the ratcheted CPPI floor in Phase 2). */
  sparkFloor: number
  /** Whether FLINT itself is a candidate today (FLINT's own R1-independent day filter — always true per flint.ts's isFlintDayEligible, but threaded through so a future gate shows as a diff here). */
  flintCandidateDay: boolean
  /** This day's worst-case per-contract dollar loss for FLINT's structure — the caller computes this via flint.ts's own `flintMaxLoss(shortStrike, longStrike, credit, 1)`; this module takes the number directly (matching every other pure sizing module in this codebase — fast-start-sizing.ts, ebb-sizing.ts — which all take precomputed maxLoss dollars, never strikes/credit). null/<=0 = unreadable. */
  flintMaxLossPerContract: number | null
  /** SPARK's OWN contracts already sized for this account today (fast-start ladder + favorable upsize, if any). */
  sparkContractsToday: number
  /** This day's per-contract worst-case max loss for SPARK's own structure. null/<=0 treated as 0 cost (never blocks FLINT on an unreadable SPARK number — SPARK's own gates already refused to trade in that case). */
  sparkMaxLossPerContract: number | null
}

export interface SparkFlintBudgetResult {
  /** 0 or 1 — SPARK_FLINT_MAX_CONTRACTS. */
  flintContracts: 0 | 1
  /** true when rule R1 itself refused it (never got to the safety net) OR the safety net dropped it. */
  droppedForSafety: boolean
  /** FLINT's own max loss for the contract count this call is evaluating (for the decision log). */
  flintMaxLossToday: number
  reason: string
}

function nonNegativeCost(n: number | null | undefined): number {
  return typeof n === 'number' && Number.isFinite(n) && n > 0 ? n : 0
}

/**
 * The FLINT-on-SPARK decision for one account, one day. Fails safe (0
 * contracts) on every missing/invalid input or an unreadable equity/deposit
 * — never guesses on a real-money profits-only gate.
 */
export function decideSparkFlintContracts(inputs: SparkFlintBudgetInputs): SparkFlintBudgetResult {
  const {
    equity, deposit, sparkFloor, flintCandidateDay,
    flintMaxLossPerContract, sparkContractsToday, sparkMaxLossPerContract,
  } = inputs

  const flintMl = typeof flintMaxLossPerContract === 'number' && Number.isFinite(flintMaxLossPerContract) && flintMaxLossPerContract > 0
    ? flintMaxLossPerContract
    : null

  if (!flintCandidateDay) {
    return { flintContracts: 0, droppedForSafety: false, flintMaxLossToday: flintMl ?? 0, reason: 'skip:spark_flint(not_a_candidate_day)' }
  }
  if (flintMl === null) {
    return { flintContracts: 0, droppedForSafety: false, flintMaxLossToday: 0, reason: 'skip:spark_flint(maxloss_unreadable)' }
  }

  // Rule R1 — profits-only, gated against DEPOSIT (never SPARK's ratcheted
  // floor) — variant (a)'s own construction: `profit = equity - deposit`.
  const gate: FlintProfitGateResult = evaluateFlintProfitGate(equity, deposit, flintMl)
  if (!gate.eligible) {
    return {
      flintContracts: 0,
      droppedForSafety: false,
      flintMaxLossToday: flintMl,
      reason: gate.reason ?? 'skip:spark_flint(r1_unreadable)',
    }
  }

  // Account-level safety net: SPARK's own sizing is NEVER reduced — FLINT is
  // dropped first if the COMBINED cost could cross the account's CURRENT
  // floor (deposit in Phase 1, the ratcheted CPPI floor in Phase 2).
  const sparkMl = nonNegativeCost(sparkMaxLossPerContract)
  const sparkCost = Math.max(0, sparkContractsToday) * sparkMl
  const combinedCost = sparkCost + flintMl
  const budgetToFloor = equity - sparkFloor
  if (combinedCost > budgetToFloor) {
    return {
      flintContracts: 0,
      droppedForSafety: true,
      flintMaxLossToday: flintMl,
      reason: `skip:spark_flint_floor_safety(combined=$${combinedCost.toFixed(2)}>budget=$${budgetToFloor.toFixed(2)}, spark_cost=$${sparkCost.toFixed(2)}, flint_ml=$${flintMl.toFixed(2)})`,
    }
  }

  return {
    flintContracts: SPARK_FLINT_MAX_CONTRACTS,
    droppedForSafety: false,
    flintMaxLossToday: flintMl,
    reason: `flint:${SPARK_FLINT_MAX_CONTRACTS}(cushion=$${gate.cushion?.toFixed(2) ?? 'n/a'}, budget_to_floor=$${budgetToFloor.toFixed(2)})`,
  }
}
