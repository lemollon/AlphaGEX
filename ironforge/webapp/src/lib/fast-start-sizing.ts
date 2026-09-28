/**
 * FLAME_FAST_START — customer-account fast-start sizing + hard profit floor
 * (CPPI), ported from the frozen pre-registration `PREREG_fast_start_floor.md`
 * and `RESULT_profit_floor_cppi.md` in dev/meltup (Leron, 2026-09-27: "yes i
 * want to add it"). Frozen parameters: **2x ladder / X=20% / N=8 / K=0.25 /
 * variant G**.
 *
 * SCOPE (widened 2026-09-27, Leron: wants the account on Tradier 6YB71371 —
 * his own live FLAME account, ~$4,242 — covered too): every FLAME customer
 * (sandbox mirror) account under EBB_CUSTOMER_LADDER=profit, PLUS FLAME's own
 * production account (person='Flame', account_type='production', 6YB71371).
 * Every SPARK account is UNTOUCHED regardless of this flag — the caller in
 * tradier.ts gates on `botName === 'flame'` before ever reaching this file.
 * "Deposit" for the production account is `getProductionLadderCapital('flame',
 * 'Flame').starting` (the SAME funded-capital figure EBB's own production
 * ladder already keys on) rather than flint_account_floor (which is
 * sandbox-only); "peak_profit" is that same call's `highWater` minus that
 * starting figure — both already-ratcheted, already-read-elsewhere values,
 * never a new ratchet mechanism invented for this file.
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

/**
 * off|on, unset = off. Defaults to FLAME_FAST_START (FLAME customer accounts
 * — see file header) so every pre-existing call site (and FLAME's own unit/
 * parity/wiring tests, which call this with no argument) is byte-for-byte
 * unchanged. `envVar` generalizes this to other bots sharing this engine —
 * SPARK's customer sizing (tradier.ts) passes 'SPARK_FAST_START' explicitly
 * (2026-09-27/29, SPARK_FAST_START — same frozen rule, SPARK's own rung).
 */
export function isFastStartMode(envVar: string = 'FLAME_FAST_START'): boolean {
  return (process.env[envVar] ?? '').trim().toLowerCase() === 'on'
}

export const FAST_START_STYLE_MULT = 2
export const FAST_START_X = 0.20
export const FAST_START_N = 8
export const FAST_START_K = 0.25

/**
 * v3 (2026-09-27/29, guarded-P&L re-validation, source: fast_start_floor_sim.py
 * FROZEN_V3): any account with `deposit >= FAST_START_DEPOSIT_CAP` NEVER runs
 * fast-start or the CPPI floor — it trades the plain standing BASE ladder for
 * its entire life (byte-identical to `off`, see decideFastStartSizing's own
 * early return). v3 grid-tested this at $5,000/$6,000 and fast-start LOST to
 * plain BASE there — Leron tightened the cap from the sim file's own $7,500
 * default down to $5,000 as a result. The parity fixture
 * (fast_start_floor_fixtures_guarded_v3.json) never exercises this boundary
 * directly (its paths are $2,000/$4,242, both well under either number), so
 * a dedicated unit test pins $5,000 and $7,500 -> exact BASE instead.
 */
export const FAST_START_DEPOSIT_CAP = 5000

/**
 * v3: $/leg added to EBB max loss and to FLINT max loss, but ONLY inside
 * Phase 2's CPPI budget checks (sizePhase2 below, and the phase-2 branch of
 * sizeFlintGivenEbbOutcome) — never in Phase 1's 20% risk cap, never in the
 * Phase 1->2 trigger (evaluateFastStartTrigger, unchanged). Real pnl is
 * NEVER adjusted by this — only the cost figure a budget check compares
 * against. Reason (fast_start_floor_sim.py "V3 RULE"): the guarded P&L has
 * days where a guard-fire buyback's REALIZED loss exceeds the stated max
 * loss by up to $47.70 (FLINT) — the never-below-deposit GUARANTEE is
 * produced entirely by Phase 2's budget check (there is no floor yet in
 * Phase 1, so margining Phase 1 or the trigger buys no extra safety, only
 * costs money — confirmed by v2's own p10 loss at $2,000 with no
 * guarantee-strength benefit). $50 comfortably covers the observed $47.70
 * worst case.
 */
export const FAST_START_PHASE2_MARGIN = 50

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
export interface FastStartSizingOpts {
  /**
   * Skip the Phase 1 -> 2 trigger check entirely and size under
   * `state.phase` AS GIVEN (never advances it). Set by the caller for
   * every INTRADAY sizing call — phase/peak_profit/floor are updated ONLY
   * once per day, at EOD, from that day's CLOSING equity (see
   * evaluateFastStartTrigger + fast-start-db.ts's updateFastStartEodState),
   * so intraday unrealized marks can never flip the phase or ratchet the
   * floor mid-day. Live/intraday equity is still used for the (equity -
   * floor) budget/cushion arithmetic within sizing itself — only the
   * TRANSITION decision and the peak_profit/floor ratchet are EOD-gated.
   */
  skipTriggerCheck?: boolean
  /**
   * Which env var gates this call (default 'FLAME_FAST_START') — see
   * isFastStartMode's own doc. SPARK's customer sizing passes
   * 'SPARK_FAST_START'; every pre-existing call site (no 3rd arg, or no
   * `envVar` key) is byte-for-byte unchanged.
   */
  envVar?: string
}

/**
 * The Phase 1 -> 2 trigger check, standalone — shared by decideFastStartSizing
 * (intraday, phase-check normally skipped per FastStartSizingOpts) and the
 * EOD-only ratchet (fast-start-db.ts's updateFastStartEodState, which calls
 * this directly with that day's CLOSING equity/cushion). One implementation,
 * never duplicated.
 */
export function evaluateFastStartTrigger(
  cushion: number,
  normalLadder: number,
  ebbCandidateDay: boolean,
  ebbMaxLossPerLot: number | null,
  flintCandidateDay: boolean,
  flintMaxLossPerContract: number | null,
): { triggered: boolean; triggerLevel: number; combinedMlLadder: number } {
  const ebbMlRaw = isPositiveFinite(ebbMaxLossPerLot) ? ebbMaxLossPerLot : 0
  const flintMlRaw = isPositiveFinite(flintMaxLossPerContract) ? flintMaxLossPerContract : 0
  const combinedMlLadder = (ebbCandidateDay ? Math.max(0, Math.floor(normalLadder)) * ebbMlRaw : 0) + (flintCandidateDay ? flintMlRaw : 0)
  const candToday = ebbCandidateDay || flintCandidateDay
  const triggerLevel = FAST_START_N * combinedMlLadder
  const triggered = candToday && combinedMlLadder > 0 && cushion >= triggerLevel
  return { triggered, triggerLevel, combinedMlLadder }
}

export function decideFastStartSizing(
  state: FastStartAccountState,
  inputs: FastStartDayInputs,
  opts?: FastStartSizingOpts,
): FastStartResult {
  const envVar = opts?.envVar ?? 'FLAME_FAST_START'
  if (!isFastStartMode(envVar)) {
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
        reason: `off:${envVar} — unchanged normal-ladder sizing (FLINT R1 not evaluated here)`,
      },
      nextState: state,
    }
  }

  // v3 is a FLAME-ONLY correction (this module is SHARED with SPARK_FAST_START
  // — see FastStartSizingOpts.envVar — and SPARK's own rule/parity was
  // already validated and shipped independently, at deposits ($5,000/
  // $7,500/$10,000) that would otherwise collide with FLAME's own v3
  // deposit cap below). Gate both v3 additions (deposit cap here, and the
  // $50 Phase-2 margin in sizePhase2/sizeFlintGivenEbbOutcome) on
  // envVar==='FLAME_FAST_START' so a SPARK_FAST_START call is BYTE-FOR-BYTE
  // unaffected by anything in this section.
  const isFlameV3 = envVar === 'FLAME_FAST_START'

  // v3 deposit cap: >= $5,000 NEVER runs fast-start/the floor — trades the
  // plain standing BASE ladder for its ENTIRE life (fast_start_floor_sim.py's
  // `_simulate_base_as_v2_trace`), reproduced EXACTLY including FLINT's own
  // standing rule here (unlike the `off` branch above, which deliberately
  // leaves FLINT to the caller's separate R1 gate) — deposit_cap's whole
  // point is "byte-identical to BASE," and BASE's own FLINT leg IS this
  // formula (cushion >= flint_maxloss), so it is decided here rather than
  // split across two code paths the way `off` is.
  if (isFlameV3 && state.deposit >= FAST_START_DEPOSIT_CAP) {
    const cushionCap = inputs.equity - state.deposit
    const baseEbb = inputs.ebbCandidateDay ? Math.max(0, Math.floor(inputs.normalEbbLadder)) : 0
    const baseFlintMl = isPositiveFinite(inputs.flintMaxLossPerContract) ? inputs.flintMaxLossPerContract : null
    const baseFlint = inputs.flintCandidateDay && baseFlintMl !== null && cushionCap >= baseFlintMl ? 1 : 0
    return {
      decision: {
        phase: state.phase,
        ebbContracts: baseEbb,
        flintContracts: baseFlint,
        floor: null,
        budget: null,
        phase1CapBudget: null,
        cushion: cushionCap,
        triggerLevel: null,
        triggeredToday: false,
        reason: `deposit_cap: deposit=$${state.deposit.toFixed(2)} >= $${FAST_START_DEPOSIT_CAP.toFixed(2)} — plain BASE ladder, never fast-start (ebb=${baseEbb} flint=${baseFlint})`,
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

  if (state.phase === 1 && !opts?.skipTriggerCheck) {
    const check = evaluateFastStartTrigger(
      cushion, normalLadder, inputs.ebbCandidateDay, ebbMl, inputs.flintCandidateDay, flintMl,
    )
    triggerLevel = check.triggerLevel
    if (check.triggered) {
      triggeredToday = true
      effectivePhase = 2
      triggerNote = ` -> TRIGGER phase1->phase2 (cushion=$${cushion.toFixed(2)} >= $${triggerLevel.toFixed(2)})`
    }
  } else if (state.phase === 1 && opts?.skipTriggerCheck) {
    triggerNote = ' (intraday: trigger check skipped, EOD-only per FastStartSizingOpts)'
  }

  const sized = effectivePhase === 1 ? sizePhase1(inputs, common) : sizePhase2(inputs, common, isFlameV3)

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

function sizePhase2(inputs: FastStartDayInputs, c: Common, applyV3Margin: boolean): Sized {
  const { deposit, cushion, normalLadder, ebbMl, flintMl } = c

  const floor = deposit + FAST_START_K * inputs.peakProfit
  const budget = inputs.equity - floor

  // v3: $50/leg margin, ONLY here in Phase 2's budget checks (never in
  // Phase 1 or the trigger — see FAST_START_PHASE2_MARGIN's own doc), and
  // ONLY for FLAME (`applyV3Margin`, resolved by the caller from
  // envVar==='FLAME_FAST_START' — SPARK_FAST_START's own, separately
  // shipped/validated Phase-2 math is untouched). Added to the COST figure
  // every gate below compares against; the real max-loss values (ebbMl/
  // flintMl) are never mutated, so `combined_maxloss`/pnl logging elsewhere
  // stays the account's real risk, not the margined one.
  const marginPerLeg = applyV3Margin ? FAST_START_PHASE2_MARGIN : 0
  const ebbMlEff = ebbMl !== null ? ebbMl + marginPerLeg : null
  const flintMlEff = flintMl !== null ? flintMl + marginPerLeg : null

  // Grandfather (minimum) layer — sequential, EBB then FLINT, gated ONLY
  // against the deposit cushion (never the K-floor budget) so this layer
  // alone can never push equity under deposit.
  const ebbMinTarget = inputs.ebbCandidateDay ? 1 : 0
  const flintMinTarget = inputs.flintCandidateDay ? 1 : 0

  let ebbMin = 0
  if (ebbMinTarget > 0 && ebbMlEff !== null && ebbMinTarget * ebbMlEff <= cushion) {
    ebbMin = ebbMinTarget
  }
  const remainingDepositCushion = cushion - ebbMin * (ebbMlEff ?? 0)

  let flintMin = 0
  if (flintMinTarget > 0 && flintMlEff !== null && flintMinTarget * flintMlEff <= remainingDepositCushion) {
    flintMin = flintMinTarget
  }

  const minimumCommitted = ebbMin * (ebbMlEff ?? 0) + flintMin * (flintMlEff ?? 0)
  const remainingKBudget = budget - minimumCommitted

  const extraTarget = inputs.ebbCandidateDay ? Math.max(0, normalLadder - ebbMin) : 0
  let extraEbb = 0
  if (extraTarget > 0 && ebbMlEff !== null && remainingKBudget > 0) {
    extraEbb = Math.max(0, Math.min(extraTarget, Math.floor(remainingKBudget / ebbMlEff)))
  }

  const ebbContracts = ebbMin + extraEbb
  const flintContracts = flintMin

  let reason =
    `phase2 deposit=$${deposit.toFixed(2)} floor=$${floor.toFixed(2)} budget=$${budget.toFixed(2)} ` +
    `cushion=$${cushion.toFixed(2)} margin=$${marginPerLeg.toFixed(2)}/leg ` +
    `ebb_min=${ebbMin} flint_min=${flintMin} extra_ebb=${extraEbb} ` +
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

/**
 * FLINT-SIDE-ONLY sizing, given EBB's ALREADY-KNOWN outcome for today.
 *
 * WHY THIS EXISTS (live-vs-sim ordering gap, see tradier.ts call sites and
 * the PR description for the full writeup): the sim allocates EBB FIRST,
 * then gives FLINT whatever budget/cushion is left — a pure function of
 * "how much did EBB use." In the live scanner, FLINT's own entry
 * (tryOpenFlint) always runs BEFORE FLAME's EBB entry logic in the SAME
 * scan tick (scanBot('flame') calls FLINT's guard/settle/entry, THEN EBB's),
 * so FLINT cannot ask "what did EBB decide THIS SAME TICK" — it can only
 * see EBB's outcome from an EARLIER tick today, or none yet.
 *
 * The caller (tradier.ts) is responsible for resolving `ebbContractsToday`
 * and `ebbMaxLossPerLot` from EBB's own today position row when one exists.
 * When EBB HAS NOT YET traded today (no row exists and EBB's own entry
 * window has not yet closed), the caller must NOT call this function at
 * all — it must size FLINT to 0 for this tick and retry next tick (see
 * the caller's own "defer until EBB is observable" comment). This function
 * always assumes `ebbContractsToday`/`ebbMaxLossPerLot` ARE the real,
 * final numbers for today — it never guesses.
 *
 * Phase 1: remaining budget = X% of deposit − ebbContractsToday ×
 * ebbMaxLossPerLot (EBB's REAL committed risk, not a re-derived target).
 * Phase 2: ebbMin is inferred as 1 iff ebbContractsToday >= 1 — valid
 * because floor_level >= deposit always, so budget_K <= budget_dep
 * (cushion), meaning EBB's "extra" layer can only be nonzero when its
 * minimum layer already fired (worked through in fast_start_floor_sim.py's
 * phase2_alloc: n_min_ebb's own gate is strictly looser than what extra_ebb
 * needs to be positive).
 *
 * FLAME-ONLY (v3, 2026-09-29): the Phase-2 branch unconditionally adds the
 * $50/leg margin (FAST_START_PHASE2_MARGIN) — safe today because the ONLY
 * caller is FLAME's own FLINT wiring in tradier.ts (`botName === 'flame'`
 * gates it before this is ever reached). SPARK has its OWN, separately
 * shipped/validated FLINT budget (spark-flint-separate.ts) and never calls
 * this function. If a future caller ever wants to reuse this for another
 * bot, it MUST add an explicit opt-out for this margin first — do not
 * assume it's safe by default.
 */
export function sizeFlintGivenEbbOutcome(
  phase: FastStartPhase,
  deposit: number,
  equity: number,
  peakProfit: number,
  ebbContractsToday: number,
  ebbMaxLossPerLot: number | null,
  flintCandidateDay: boolean,
  flintMaxLossPerContract: number | null,
): { flintContracts: number; reason: string } {
  const cushion = equity - deposit
  const flintMl = isPositiveFinite(flintMaxLossPerContract) ? flintMaxLossPerContract : null
  const ebbMl = isPositiveFinite(ebbMaxLossPerLot) ? ebbMaxLossPerLot : 0
  const ebbCommitted = Math.max(0, ebbContractsToday) * ebbMl

  if (!flintCandidateDay || flintMl === null) {
    return { flintContracts: 0, reason: 'flint not a candidate today or max-loss unreadable' }
  }

  if (phase === 1) {
    const phase1CapBudget = FAST_START_X * deposit
    const remaining = phase1CapBudget - ebbCommitted
    const flintContracts = cushion >= flintMl ? Math.max(0, Math.min(1, Math.floor(remaining / flintMl))) : 0
    return {
      flintContracts,
      reason: `phase1 (ebb-given) cap_budget=$${phase1CapBudget.toFixed(2)} ebb_committed=$${ebbCommitted.toFixed(2)} ` +
        `remaining=$${remaining.toFixed(2)} flint=${flintContracts}`,
    }
  }

  // Phase 2: minimum layer only, sequential AFTER ebb's own minimum
  // commitment. v3: $50/leg margin here too (matching sizePhase2's own
  // Phase-2-only margin) — ebbMl/flintMl below are ONLY the cost figures
  // these gates compare against, never the real risk.
  const ebbMlEff = ebbMl + FAST_START_PHASE2_MARGIN
  const flintMlEff = flintMl + FAST_START_PHASE2_MARGIN
  const ebbMin = ebbContractsToday >= 1 ? 1 : 0
  const remainingDepositCushion = cushion - ebbMin * ebbMlEff
  const flintContracts = flintMlEff <= remainingDepositCushion ? 1 : 0
  return {
    flintContracts,
    reason: `phase2 (ebb-given) margin=$${FAST_START_PHASE2_MARGIN.toFixed(2)}/leg ebb_min=${ebbMin} cushion=$${cushion.toFixed(2)} ` +
      `remaining_deposit_cushion=$${remainingDepositCushion.toFixed(2)} flint=${flintContracts}`,
  }
}
