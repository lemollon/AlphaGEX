/**
 * FLAME_FAST_START — customer-account fast-start sizing + hard profit floor
 * (CPPI), ported from the frozen pre-registration `PREREG_fast_start_floor.md`
 * and `RESULT_profit_floor_cppi.md` in dev/meltup (Leron, 2026-09-27: "yes i
 * want to add it"). Frozen parameters: **2x ladder / X=20% / N=8 / K=0.25 /
 * variant G**.
 *
 * SCOPE: FLAME customer (sandbox mirror) accounts ONLY — same scope as
 * EBB_CUSTOMER_LADDER (see ebbCustomerLadderMode in ebb-sizing.ts). FLAME's
 * own production account and every SPARK account are UNTOUCHED by this file;
 * the caller in tradier.ts gates on the same `botName === 'flame'` +
 * account-type checks the profit ladder already uses.
 *
 * THIS FILE IS PURE — no DB, no network — so it is unit-testable without
 * mocking Postgres/Tradier, matching ebb-sizing.ts and flint.ts. Per-account
 * STATE (phase, deposit, high-water/peak-profit) is read/written by the
 * caller (tradier.ts) via fast_start_state / the existing
 * flint_account_floor + ebb_customer_high_water tables; this module only
 * computes the day's decision from whatever state it is handed and returns
 * the (possibly advanced) next state for the caller to persist.
 *
 * THE RULE, PRECISELY (see decideFastStartSizing below for the code):
 *
 * Phase 1 (cushion not yet built): EBB is sized at 2x its normal
 * (un-multiplied) ladder count on every EBB-candidate day. FLINT is NEVER
 * multiplied — it keeps its own standing rule (1 contract, gated on
 * cushion = equity-deposit >= that day's FLINT max loss), unchanged by this
 * file. The day's COMBINED EBB+FLINT max loss is capped at X=20% of the
 * account's DEPOSIT (a fixed dollar number, never the ratcheting equity) —
 * EBB is allocated first out of that budget, FLINT gets whatever budget is
 * left (sequential allocation, matching the doc's construction).
 *
 * Phase 1 -> Phase 2 trigger (one-way, never reverts): fires the first
 * EBB-candidate day the cushion (equity-deposit) reaches
 * N=8 x (that day's ACTUAL EBB contracts traded x EBB max loss + FLINT max
 * loss, if FLINT is also a candidate that day) — i.e. 8x the max loss this
 * account is ACTUALLY carrying today under the Phase-1 rule above, not an
 * unbounded, ever-growing ladder-scaled figure. `isFastStartTriggerMet`
 * below is the one place this check lives.
 *
 * Phase 2 (the CPPI floor, variant G): floor_t = deposit + K x peak_profit_t
 * (K=0.25), where peak_profit only ever ratchets up (max(0, high_water -
 * deposit)) — floor_t is therefore automatically monotonic and is never
 * persisted separately from peak_profit. budget_t = equity_t - floor_t.
 * A permanent MINIMUM (grandfather) layer of 1 EBB lot + 1 FLINT contract
 * (whichever are candidates today) is sized FIRST, sequentially (EBB then
 * FLINT), gated ONLY against the deposit (cushion = equity-deposit — the
 * SAME check Phase 1 already uses), so the minimum layer alone can never
 * push equity under deposit. An EXTRA EBB layer, above the minimum, up to
 * the account's normal (un-multiplied) ladder count, is then sized against
 * the K-floor budget NET of what the minimum layer already committed.
 * FLINT's normal cap is 1 contract, equal to its minimum layer, so it never
 * gets an "extra" layer under G. This construction guarantees equity can
 * never fall below deposit once Phase 2 has begun (proof: either the
 * minimum layer's own deposit-gate binds, bounding that day's loss by
 * equity-deposit directly, or the K-budget covers it and floor_t itself is
 * untouched).
 *
 * KILL SWITCH: FLAME_FAST_START=off (or unset — the default) makes
 * `isFastStartMode()` false. The caller (tradier.ts) must not invoke this
 * module at all when off — see decideFastStartSizing's own guard, which
 * returns the account's UNCHANGED normal-ladder numbers byte-for-byte if
 * called anyway, so a caller bug (calling this with the flag off) still
 * cannot change sizing.
 */

/** off|on, unset = off. FLAME customer accounts only — see file header. */
export function isFastStartMode(): boolean {
  return (process.env.FLAME_FAST_START ?? '').trim().toLowerCase() === 'on'
}

export const FAST_START_STYLE_MULT = 2
export const FAST_START_X = 0.20
export const FAST_START_N = 8
export const FAST_START_K = 0.25

export type FastStartPhase = 1 | 2

export interface FastStartAccountState {
  /** 1 = building the cushion (2x, X-capped). 2 = CPPI floor (G). One-way. */
  phase: FastStartPhase
  /** This account's seeded floor (flint_account_floor.floor_amount) — fixed for the life of the account. */
  deposit: number
}

/** Seeds a brand-new account: always Phase 1. The very first evaluation may
 * immediately advance to Phase 2 within the same call if the trigger is
 * already met (see decideFastStartSizing) — e.g. an existing account with
 * accumulated profit before FLAME_FAST_START was turned on. */
export function seedFastStartState(deposit: number): FastStartAccountState {
  return { phase: 1, deposit }
}

export interface FastStartDayInputs {
  ebbCandidateDay: boolean
  flintCandidateDay: boolean
  /** This lot's worst-case dollar loss today. null/NaN/<=0 = unreadable -> 0 EBB contracts, logged. Only meaningful when ebbCandidateDay. */
  ebbMaxLossPerLot: number | null
  /** This contract's worst-case dollar loss today. null/NaN/<=0 = unreadable -> 0 FLINT contracts, logged. Only meaningful when flintCandidateDay. */
  flintMaxLossPerContract: number | null
  /** Today's NORMAL (un-multiplied) EBB ladder count for this account — from ebbProfitLadderContracts/ebbLadderContracts. 0 or negative = below one rung. */
  normalEbbLadder: number
  /** This account's current equity (this SAME cycle's read — never a stale value). */
  equity: number
  /** max(0, high_water - deposit) — already ratcheted by the caller via ebb_customer_high_water. Never negative. */
  peakProfit: number
}

export interface FastStartDecision {
  phase: FastStartPhase
  ebbContracts: number
  flintContracts: number
  /** Phase 2 only. null in Phase 1. */
  floor: number | null
  /** Phase 2 only (equity - floor). null in Phase 1. */
  budget: number | null
  /** Phase 1 only: the fixed X% of the deposit. null in Phase 2. */
  phase1CapBudget: number | null
  /** cushion = equity - deposit, valid in both phases. */
  cushion: number
  /** The trigger threshold checked THIS call (N x today's actual combined max loss). null on a non-EBB-candidate day (never evaluated) or once already in Phase 2. */
  triggerLevel: number | null
  /** true exactly on the call that flips phase 1 -> 2. */
  triggeredToday: boolean
  /** Human-readable reason string for the decision log. */
  reason: string
}

export interface FastStartResult {
  decision: FastStartDecision
  nextState: FastStartAccountState
}

function isPositiveFinite(n: number | null | undefined): n is number {
  return typeof n === 'number' && Number.isFinite(n) && n > 0
}

/**
 * The full fast-start decision for one account, one day. Pure — no I/O.
 *
 * Fails safe on every missing/invalid input:
 *  - FLAME_FAST_START off -> returns the account's unmodified normal-ladder
 *    numbers (EBB = normalEbbLadder, FLINT = 0 — the caller's OWN pre-existing
 *    FLINT R1 gate is untouched by this module and must be applied by the
 *    caller separately; this function never claims authority over FLINT
 *    when fast-start itself is off).
 *  - normalEbbLadder <= 0 -> 0 EBB contracts, logged, in either phase.
 *  - ebbMaxLossPerLot / flintMaxLossPerContract missing on a day that leg is
 *    a candidate -> that leg trades 0, logged — never guesses a max loss.
 *  - Phase 1 cap smaller than 1 lot's max loss -> 0 EBB contracts, logged
 *    (not a fallback to 1 — never risk more than the cap allows).
 */
export function decideFastStartSizing(
  state: FastStartAccountState,
  inputs: FastStartDayInputs,
): FastStartResult {
  if (!isFastStartMode()) {
    return {
      decision: {
        phase: state.phase,
        ebbContracts: inputs.ebbCandidateDay ? Math.max(0, Math.floor(inputs.normalEbbLadder)) : 0,
        flintContracts: 0,
        floor: null,
        budget: null,
        phase1CapBudget: null,
        cushion: inputs.equity - state.deposit,
        triggerLevel: null,
        triggeredToday: false,
        reason: 'off:FLAME_FAST_START — unchanged normal-ladder sizing (FLINT R1 not evaluated here)',
      },
      nextState: state,
    }
  }

  const deposit = state.deposit
  const cushion = inputs.equity - deposit
  const normalLadder = Math.max(0, Math.floor(inputs.normalEbbLadder))
  const ebbMl = isPositiveFinite(inputs.ebbMaxLossPerLot) ? inputs.ebbMaxLossPerLot : null
  const flintMl = isPositiveFinite(inputs.flintMaxLossPerContract) ? inputs.flintMaxLossPerContract : null
  const common: Common = { deposit, cushion, normalLadder, ebbMl, flintMl }

  // ---- Trigger check FIRST (matches fast_start_floor_sim.py's own control
  // flow exactly: the trigger is checked, and phase is possibly advanced,
  // BEFORE that SAME day's sizing decision — a day that trips the trigger
  // is sized under Phase 2 THAT SAME DAY, not starting tomorrow). Only
  // evaluated while still in Phase 1; Phase 2 is sticky and never re-checks. ----
  let effectivePhase: FastStartPhase = state.phase
  let triggerLevel: number | null = null
  let triggeredToday = false
  let triggerNote = ''

  if (state.phase === 1) {
    // combined_ml_ladder = (normalLadder x EBB max loss, if EBB is a
    // candidate today) + (FLINT max loss, if FLINT is a candidate today),
    // using the UN-multiplied normal ladder and each leg's RAW max loss (0
    // when unreadable) — gated by CANDIDACY, never by whether that leg
    // actually ends up trading today.
    const ebbMlRaw = ebbMl ?? 0
    const flintMlRaw = flintMl ?? 0
    const combinedMlLadder =
      (inputs.ebbCandidateDay ? normalLadder * ebbMlRaw : 0) + (inputs.flintCandidateDay ? flintMlRaw : 0)
    const candToday = inputs.ebbCandidateDay || inputs.flintCandidateDay
    triggerLevel = FAST_START_N * combinedMlLadder
    if (candToday && combinedMlLadder > 0 && cushion >= triggerLevel) {
      triggeredToday = true
      effectivePhase = 2
      triggerNote = ` -> TRIGGER phase1->phase2 (cushion=$${cushion.toFixed(2)} >= $${triggerLevel.toFixed(2)})`
    }
  }

  const sized = effectivePhase === 1 ? sizePhase1(inputs, common) : sizePhase2(inputs, common)

  return {
    decision: {
      phase: effectivePhase,
      ebbContracts: sized.ebbContracts,
      flintContracts: sized.flintContracts,
      floor: sized.floor,
      budget: sized.budget,
      phase1CapBudget: sized.phase1CapBudget,
      cushion,
      triggerLevel,
      triggeredToday,
      reason: sized.reason + triggerNote,
    },
    nextState: { ...state, phase: effectivePhase },
  }
}

interface Common {
  deposit: number
  cushion: number
  normalLadder: number
  ebbMl: number | null
  flintMl: number | null
}

interface Sized {
  ebbContracts: number
  flintContracts: number
  floor: number | null
  budget: number | null
  phase1CapBudget: number | null
  reason: string
}

function sizePhase1(inputs: FastStartDayInputs, c: Common): Sized {
  const { deposit, cushion, normalLadder, ebbMl, flintMl } = c

  // FLINT's own standing rule — never multiplied, gated on the SAME cushion
  // (equity-deposit) the production R1 gate already uses. This module only
  // decides FLINT's slice of the SHARED X-budget; the caller's separate R1
  // gate (evaluateFlintProfitGate) still applies on top and may step this
  // down further (e.g. BP limits) — untouched by this file.
  const flintWantsToday = inputs.flintCandidateDay && flintMl !== null && cushion >= flintMl

  const ebbTargetToday = inputs.ebbCandidateDay ? FAST_START_STYLE_MULT * normalLadder : 0

  const phase1CapBudget = FAST_START_X * deposit

  let ebbContracts = 0
  if (inputs.ebbCandidateDay && ebbMl !== null && ebbTargetToday > 0) {
    ebbContracts = Math.max(0, Math.min(ebbTargetToday, Math.floor(phase1CapBudget / ebbMl)))
  }
  const remainingBudget = phase1CapBudget - ebbContracts * (ebbMl ?? 0)

  let flintContracts = 0
  if (flintWantsToday && flintMl !== null) {
    flintContracts = Math.max(0, Math.min(1, Math.floor(remainingBudget / flintMl)))
  }

  let reason =
    `phase1 deposit=$${deposit.toFixed(2)} cushion=$${cushion.toFixed(2)} ` +
    `normal_ladder=${normalLadder} ebb_target=${ebbTargetToday} cap_budget=$${phase1CapBudget.toFixed(2)} ` +
    `ebb=${ebbContracts} flint=${flintContracts}`

  if (!inputs.ebbCandidateDay) reason += ' (ebb not a candidate today)'
  if (inputs.ebbCandidateDay && ebbMl === null) reason += ' (ebb max-loss unreadable -> 0)'
  if (inputs.flintCandidateDay && flintMl === null) reason += ' (flint max-loss unreadable -> 0)'

  return {
    ebbContracts,
    flintContracts,
    // floor_level stays exactly at deposit for the entire time an account
    // is in Phase 1 (fast_start_floor_sim.py: `floor_level = deposit`, not
    // yet tracked/ratcheted) — surfaced here so the decision log has a
    // floor value on every row, phase 1 or 2.
    floor: deposit,
    budget: null,
    phase1CapBudget,
    reason,
  }
}

function sizePhase2(inputs: FastStartDayInputs, c: Common): Sized {
  const { deposit, cushion, normalLadder, ebbMl, flintMl } = c

  const floor = deposit + FAST_START_K * inputs.peakProfit
  const budget = inputs.equity - floor

  // Grandfather (minimum) layer — sequential, EBB then FLINT, gated ONLY
  // against the deposit cushion (never the K-floor budget) so this layer
  // alone can never push equity under deposit.
  const ebbMinTarget = inputs.ebbCandidateDay ? 1 : 0
  const flintMinTarget = inputs.flintCandidateDay ? 1 : 0

  let ebbMin = 0
  if (ebbMinTarget > 0 && ebbMl !== null && ebbMinTarget * ebbMl <= cushion) {
    ebbMin = ebbMinTarget
  }
  const remainingDepositCushion = cushion - ebbMin * (ebbMl ?? 0)

  let flintMin = 0
  if (flintMinTarget > 0 && flintMl !== null && flintMinTarget * flintMl <= remainingDepositCushion) {
    flintMin = flintMinTarget
  }

  const minimumCommitted = ebbMin * (ebbMl ?? 0) + flintMin * (flintMl ?? 0)
  const remainingKBudget = budget - minimumCommitted

  const extraTarget = inputs.ebbCandidateDay ? Math.max(0, normalLadder - ebbMin) : 0
  let extraEbb = 0
  if (extraTarget > 0 && ebbMl !== null && remainingKBudget > 0) {
    extraEbb = Math.max(0, Math.min(extraTarget, Math.floor(remainingKBudget / ebbMl)))
  }

  const ebbContracts = ebbMin + extraEbb
  const flintContracts = flintMin

  let reason =
    `phase2 deposit=$${deposit.toFixed(2)} floor=$${floor.toFixed(2)} budget=$${budget.toFixed(2)} ` +
    `cushion=$${cushion.toFixed(2)} ebb_min=${ebbMin} flint_min=${flintMin} extra_ebb=${extraEbb} ` +
    `ebb=${ebbContracts} flint=${flintContracts}`

  if (inputs.ebbCandidateDay && ebbMl === null) reason += ' (ebb max-loss unreadable -> 0)'
  if (inputs.flintCandidateDay && flintMl === null) reason += ' (flint max-loss unreadable -> 0)'
  if (!inputs.ebbCandidateDay) reason += ' (ebb not a candidate today)'
  if (!inputs.flintCandidateDay) reason += ' (flint not a candidate today)'

  return {
    ebbContracts,
    flintContracts,
    floor,
    budget,
    phase1CapBudget: null,
    reason,
  }
}
