/**
 * STOKE — SPY 0DTE call credit spread, a third FLAME sleeve, fired only on
 * the days EBB's own VIX-decay gate ratio SKIPS the put side (ratio > 0.80)
 * AND yesterday's SPY session closed DOWN (PREREG_STOKE_BUILD.md, 2026-10-15,
 * "K1" filter). Validated: RESULT_STOKE_FILTERED.md Arm K1 — 103 trades
 * (3.9y window), $298/yr, maxDD $201, ret/DD 1.49 full window, 1.68 in
 * 2025+. Zero overlap with EBB by construction (fires only on EBB's own
 * skip days) and zero overlap with FLINT by construction (FLINT requires
 * prior-day-UP; STOKE requires prior-day-DOWN — mutually exclusive).
 *
 * Own file, own table (flame_stoke_positions), own arm switch (STOKE_MODE),
 * own production path (placeStokeOrderAllAccounts in tradier.ts). It can
 * never read or write FLAME's put-side ledger/sizing/P&L, FLINT's ledger, or
 * EBB's equity — its own profit gate reads ONLY its own dedicated standing
 * floor (STOKE_FLOOR_AMOUNT) and its own cumulative realized P&L, the same
 * independence shape FLINT's own rule R1 uses (PREREG_FLAME_SLEEVE_
 * INDEPENDENCE.md).
 *
 * This file holds ONLY pure, DB/network-free logic so it can be unit tested
 * without mocking Postgres or Tradier — same split as lib/flint.ts and
 * lib/ebb-sizing.ts.
 *
 * SHIPPED DISARMED by default. STOKE_MODE is unset by default, which
 * getStokeMode() resolves to 'off' — the scanner places no order of any
 * kind (paper or live) while off. 'live' additionally requires FLAME's own
 * isFlameLiveArmed() gate in tradier.ts (the same gate FLINT's own live path
 * is behind), so a single missing env var on either switch keeps this fully
 * inert. Leron has asked for STOKE to go live immediately on merge — arming
 * (setting STOKE_MODE) is the main loop's job after this PR merges, not
 * something done inside this file.
 */

export type StokeMode = 'off' | 'paper' | 'live'

/** Net credit floor default, per share. Below this the spread is not worth the assignment risk. */
export const STOKE_MIN_CREDIT_DEFAULT = 0.10

/** Fixed size for this sleeve — one lot, flat. No upsize feature exists for STOKE. */
export const STOKE_MAX_CONTRACTS_DEFAULT = 1

/** Distance (dollars) inside which — or above — the short call strike trips the buy-back guard. Mirrors FLINT's own default. */
export const STOKE_GUARD_BUFFER_DEFAULT = 0.25

/** Short call is placed at the NEAREST strike to spot + this many dollars (default 2, per PREREG_high_vix_call_spread.md Arm B — the filtered K1 arm this sleeve ships). The long call's wing is always +2, independent of this offset. */
export const STOKE_OTM_OFFSET_DEFAULT = 2

/** Round-trip commission for the 2-leg spread: $0.70/leg, matching every other spread convention in this codebase. */
export const STOKE_COMMISSION_PER_CONTRACT = 1.40

/** Minimum option buying power a live order must clear, per contract. */
export const STOKE_BP_FLOOR_PER_CONTRACT = 200

/**
 * STOKE's own dedicated standing floor allocation, dollars — NOT the
 * account's shared EBB deposit/ladder floor, and NOT FLINT's own floor.
 * Default $500, carried over from FLINT's own backtest-validated number
 * (RESULT_FLAME_THREE_SLEEVE_MIX.md) at FLINT's same 1-lot cap and
 * comparable $2-wide-spread worst case — Leron, 2026-10-15: "I want it live
 * and armed immediately." No floor-level backtest was run for STOKE
 * specifically; only the K1 filter/edge itself was validated
 * (RESULT_STOKE_FILTERED.md). Leron's to correct if he wants a different
 * number.
 */
export const STOKE_FLOOR_AMOUNT_DEFAULT = 500

/**
 * STOKE_FLOOR_AMOUNT — default 500. Unparsable or negative falls back to
 * the default rather than silently granting a zero/negative standing floor
 * on a real-money gate.
 */
export function getStokeFloorAmount(): number {
  const raw = Number(process.env.STOKE_FLOOR_AMOUNT)
  if (!Number.isFinite(raw) || raw < 0) return STOKE_FLOOR_AMOUNT_DEFAULT
  return raw
}

/**
 * off  — unset, or any value other than 'paper'/'live'. No order of any kind, ever.
 * paper — records to flame_stoke_positions only. No Tradier order placed.
 * live  — also places on FLAME's production account(s) via the dedicated
 *         STOKE production path (still gated behind isFlameLiveArmed()).
 *
 * Fails CLOSED: any unrecognized value (typo, blank, "true", "1"...) resolves to 'off'.
 */
export function getStokeMode(): StokeMode {
  const raw = (process.env.STOKE_MODE ?? '').trim().toLowerCase()
  if (raw === 'paper' || raw === 'live') return raw
  return 'off'
}

/** STOKE_MAX_CONTRACTS — default 1, floored to a whole number, never below 1. */
export function getStokeMaxContracts(): number {
  const raw = Number(process.env.STOKE_MAX_CONTRACTS)
  if (!Number.isFinite(raw) || raw < 1) return STOKE_MAX_CONTRACTS_DEFAULT
  return Math.floor(raw)
}

/**
 * STOKE_GUARD_BUFFER — default 0.25. Setting it to '' or '0' disables the
 * guard entirely (the position then always holds to expiry/close, same as a
 * bot with no guard at all). Any other non-negative number is honored;
 * anything unparsable falls back to the default rather than silently
 * disabling real-money assignment protection.
 */
export function getStokeGuardBuffer(): number {
  const raw = process.env.STOKE_GUARD_BUFFER
  if (raw === undefined) return STOKE_GUARD_BUFFER_DEFAULT
  const trimmed = raw.trim()
  if (trimmed === '' || trimmed === '0') return 0
  const n = Number(trimmed)
  if (!Number.isFinite(n) || n < 0) return STOKE_GUARD_BUFFER_DEFAULT
  return n
}

/**
 * STOKE_OTM_OFFSET — dollars added to spot before rounding to the nearest
 * strike that picks the short strike. Default 2. Unparsable or negative
 * falls back to the default rather than silently placing the short strike
 * at or below spot.
 */
export function getStokeOtmOffset(): number {
  const raw = Number(process.env.STOKE_OTM_OFFSET)
  if (!Number.isFinite(raw) || raw < 0) return STOKE_OTM_OFFSET_DEFAULT
  return raw
}

/**
 * STOKE_MIN_CREDIT — default 0.10. Unparsable or negative falls back to the
 * default rather than silently accepting a worthless (or negative) credit.
 */
export function getStokeMinCredit(): number {
  const raw = Number(process.env.STOKE_MIN_CREDIT)
  if (!Number.isFinite(raw) || raw < 0) return STOKE_MIN_CREDIT_DEFAULT
  return raw
}

/**
 * Short call: the NEAREST whole-dollar strike to spot + otmOffset (default
 * STOKE_OTM_OFFSET_DEFAULT = 2) — Math.round, not FLINT's Math.ceil, per
 * PREREG_high_vix_call_spread.md's Arm B convention ("nearest strike to
 * spot + $2"), the arm RESULT_STOKE_FILTERED.md validated. Long call is
 * always short + $2 — the wing width is fixed, independent of the OTM offset.
 *
 *   spot 768.05, offset 2 -> round(770.05) = 770 short, 772 long
 *   spot 768.60, offset 2 -> round(770.60) = 771 short, 773 long
 */
export function computeStokeStrikes(
  spot: number,
  otmOffset: number = STOKE_OTM_OFFSET_DEFAULT,
): { short: number; long: number } {
  const short = Math.round(spot + otmOffset)
  return { short, long: short + 2 }
}

/** Net credit must clear the floor. Equal to the floor is accepted (>=, not >). */
export function meetsStokeCreditFloor(credit: number, minCredit: number = STOKE_MIN_CREDIT_DEFAULT): boolean {
  return Number.isFinite(credit) && credit >= minCredit
}

/**
 * Gate 1 — fires only on days EBB's own VIX-decay gate ratio SKIPS the put
 * side, i.e. ratio strictly above the ceiling EBB itself uses for FLAME
 * (scanner.ts's VIX_DECAY_CEILING.flame, 0.80). `ratio` must be the EXACT
 * same number EBB's own gate computes (vixDecayCheck in scanner.ts) — this
 * function does not re-derive it, only applies the ">0.80" test. A null
 * (unavailable/short history) ratio fails CLOSED, same direction as every
 * other real-money gate — never trades on a ratio it could not read.
 */
export function isStokeVixGateEligible(ratio: number | null, ceiling: number = 0.80): boolean {
  return ratio != null && Number.isFinite(ratio) && ratio > ceiling
}

/**
 * Assignment guard: true when spot is within `buffer` dollars of, or above,
 * the short call strike. `buffer <= 0` means the guard is disabled (see
 * getStokeGuardBuffer) and this always returns false — the position holds
 * to settlement unguarded, deliberately, not by accident. Byte-for-byte the
 * same shape as FLINT's isFlintGuardTriggered.
 */
export function isStokeGuardTriggered(spot: number, shortStrike: number, buffer: number): boolean {
  if (!(buffer > 0)) return false
  return spot >= shortStrike - buffer
}

/**
 * Worst-case dollar loss for ONE STOKE trade: the full wing width minus the
 * credit collected, times 100, times contracts, plus the round-trip
 * commission. This is the number the profit gate below protects against —
 * the WORST case, never max_profit or an expected value, matching every
 * other collateral/max-loss calculation in this codebase (byte-for-byte the
 * same formula as FLINT's flintMaxLoss).
 */
export function stokeMaxLoss(shortStrike: number, longStrike: number, credit: number, contracts: number): number {
  return (longStrike - shortStrike - credit) * 100 * contracts + STOKE_COMMISSION_PER_CONTRACT * contracts
}

export interface StokeProfitGateResult {
  eligible: boolean
  /** stokeFloor + stokeRealizedPnl, rounded to cents. null when either input could not be read. */
  cushion: number | null
  /** null when eligible; otherwise the exact skip-reason string to log. */
  reason: string | null
}

/**
 * STOKE's OWN profit gate — the R1-equivalent for this sleeve, independent
 * of the account's shared EBB equity AND of FLINT's own floor/P&L
 * (PREREG_STOKE_BUILD.md, 2026-10-15). `stokeFloor` is STOKE's own
 * dedicated standing allocation (STOKE_FLOOR_AMOUNT, default $500 — see
 * getStokeFloorAmount above), never the account's funded/ladder floor and
 * never FLINT's floor. `stokeRealizedPnl` is STOKE's own cumulative
 * realized P&L on this account ONLY (getStokeCumulativeRealizedPnl,
 * scanner.ts) — never EBB's put-side or FLINT's call-side P&L.
 * `cushion = stokeFloor + stokeRealizedPnl`: STOKE may always risk its own
 * floor, even at zero or negative running P&L (so a brand-new account can
 * take STOKE's FIRST trade without waiting on EBB's or FLINT's profit),
 * plus whatever it has earned on top of it.
 *
 * Evaluated INDEPENDENTLY per account — one account's cushion has no effect
 * on any other account's decision. `stokeFloor` or `stokeRealizedPnl`
 * unreadable (null) fails CLOSED: never guesses a number for a real-money
 * gate.
 */
export function evaluateStokeProfitGate(
  stokeFloor: number | null,
  stokeRealizedPnl: number | null,
  maxLoss: number,
): StokeProfitGateResult {
  if (stokeFloor == null || stokeRealizedPnl == null) {
    return { eligible: false, cushion: null, reason: 'skip:stoke_profit_cushion(unreadable)' }
  }
  const cushion = Math.round((stokeFloor + stokeRealizedPnl) * 100) / 100
  if (cushion < maxLoss) {
    return {
      eligible: false,
      cushion,
      reason: `skip:stoke_profit_cushion(cushion=$${cushion.toFixed(2)}<maxloss=$${maxLoss.toFixed(2)})`,
    }
  }
  return { eligible: true, cushion, reason: null }
}

export interface StokeContractsDecision {
  /** 0 means neither size cleared the profit gate — the caller must skip entirely. */
  contracts: number
  /** The gate result for the chosen size (or, when contracts is 0, for `base` — the last one tried). */
  gate: StokeProfitGateResult
}

/**
 * STOKE's profit gate, applied with a desired/base pair for structural
 * symmetry with FLINT's decideFlintContractsForCushion — STOKE has no
 * upsize feature, so every real call site passes desired === base, making
 * this exactly ONE evaluation of evaluateStokeProfitGate, byte-for-byte.
 * Shared, pure logic for both money paths (scanner.ts's paper ledger and
 * tradier.ts's per-account production/sandbox loop) so the gate math lives
 * in exactly one place.
 */
export function decideStokeContractsForCushion(
  desired: number,
  base: number,
  stokeFloor: number | null,
  stokeRealizedPnl: number | null,
  shortStrike: number,
  longStrike: number,
  credit: number,
): StokeContractsDecision {
  const candidates = desired > base ? [desired, base] : [desired]
  let gate: StokeProfitGateResult = { eligible: false, cushion: null, reason: 'skip:stoke_profit_cushion(unreadable)' }
  for (const c of candidates) {
    const loss = stokeMaxLoss(shortStrike, longStrike, credit, c)
    gate = evaluateStokeProfitGate(stokeFloor, stokeRealizedPnl, loss)
    if (gate.eligible) return { contracts: c, gate }
  }
  return { contracts: 0, gate }
}
