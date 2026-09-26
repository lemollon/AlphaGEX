/**
 * FLAME-CALL — SPY 0DTE call credit spread, traded ONLY on the days FLAME's
 * own VIX decay gate SKIPS the put side (ratio > 0.80). Pre-registered
 * backtest, mirrors the FLAME put spread's conventions (NBBO pricing,
 * fixed-size single contract, hold-to-expiry, assignment guard) but is a
 * completely separate sleeve: separate table (flame_call_sleeve_positions,
 * see scanner.ts), separate arm switch (FLAME_CALL_SLEEVE_MODE), separate
 * production path (placeCallSpreadOrderAllAccounts in tradier.ts). It can
 * never read or write FLAME's put-side ledger, sizing, or P&L.
 *
 * This file holds ONLY pure, DB/network-free logic so it can be unit tested
 * without mocking Postgres or Tradier — same split as lib/ebb-sizing.ts.
 *
 * SHIPPED DISARMED. FLAME_CALL_SLEEVE_MODE is unset by default, which
 * getCallSleeveMode() resolves to 'off' — the scanner places no order of any
 * kind (paper or live) while off. 'live' additionally requires FLAME's own
 * isFlameLiveArmed() gate in tradier.ts, so a single missing env var on
 * either switch keeps this fully inert.
 */

export type CallSleeveMode = 'off' | 'paper' | 'live'

/** Net credit floor, per share. Below this the spread is not worth the assignment risk. */
export const CALL_SLEEVE_MIN_CREDIT = 0.10

/** Fixed size for this sleeve — deliberately NOT the EBB count ladder (spec: 1 lot, flat). */
export const CALL_SLEEVE_DEFAULT_MAX_CONTRACTS = 1

/** Distance (dollars) inside which — or above — the short call strike trips the buy-back guard. */
export const CALL_SLEEVE_DEFAULT_GUARD_BUFFER = 0.25

/** Short call is placed at least this many dollars OTM at entry; long call is one more OTM. */
export const CALL_SLEEVE_OTM_OFFSET = 2

/**
 * off  — unset, or any value other than 'paper'/'live'. No order of any kind, ever.
 * paper — records to flame_call_sleeve_positions only. No Tradier order placed.
 * live  — also places on FLAME's production account(s) via the same production
 *         path FLAME's put spread uses (still gated behind isFlameLiveArmed()).
 *
 * Fails CLOSED: any unrecognized value (typo, blank, "true", "1"...) resolves to 'off'.
 */
export function getCallSleeveMode(): CallSleeveMode {
  const raw = (process.env.FLAME_CALL_SLEEVE_MODE ?? '').trim().toLowerCase()
  if (raw === 'paper' || raw === 'live') return raw
  return 'off'
}

/** CALL_SLEEVE_MAX_CONTRACTS — default 1, floored to a whole number, never below 1. */
export function getCallSleeveMaxContracts(): number {
  const raw = Number(process.env.CALL_SLEEVE_MAX_CONTRACTS)
  if (!Number.isFinite(raw) || raw < 1) return CALL_SLEEVE_DEFAULT_MAX_CONTRACTS
  return Math.floor(raw)
}

/**
 * CALL_SLEEVE_GUARD_BUFFER — default 0.25. Setting it to '' or '0' disables the
 * guard entirely (the position then always holds to expiry/close, same as a
 * bot with no guard at all). Any other non-negative number is honored;
 * anything unparsable falls back to the default rather than silently
 * disabling real-money assignment protection.
 */
export function getCallSleeveGuardBuffer(): number {
  const raw = process.env.CALL_SLEEVE_GUARD_BUFFER
  if (raw === undefined) return CALL_SLEEVE_DEFAULT_GUARD_BUFFER
  const trimmed = raw.trim()
  if (trimmed === '' || trimmed === '0') return 0
  const n = Number(trimmed)
  if (!Number.isFinite(n) || n < 0) return CALL_SLEEVE_DEFAULT_GUARD_BUFFER
  return n
}

/**
 * Short call: the first whole-dollar strike at least $2 above spot at entry.
 * Long call: short + $2 (the wing).
 *
 *   spot 768.05 -> ceil(770.05) = 771 short, 773 long
 *   spot 770.00 -> ceil(772.00) = 772 short, 774 long
 */
export function computeCallStrikes(spot: number): { short: number; long: number } {
  const short = Math.ceil(spot + CALL_SLEEVE_OTM_OFFSET)
  return { short, long: short + CALL_SLEEVE_OTM_OFFSET }
}

/** Net credit must clear the floor. Equal to the floor is accepted (>=, not >). */
export function meetsCallCreditFloor(credit: number): boolean {
  return Number.isFinite(credit) && credit >= CALL_SLEEVE_MIN_CREDIT
}

/**
 * The day filter: trade ONLY on days FLAME's own VIX decay ratio exceeds its
 * ceiling — i.e. exactly the days FLAME's gate skips the put side. `ratio`
 * must be the SAME ratio FLAME's vixDecayCheck() computed (scanner.ts) — this
 * function does not recompute it, it only re-applies the threshold test so
 * the two gates cannot silently drift apart. `null` (unknown/unavailable
 * history) never trades — fails closed, same direction as FLAME's own gate.
 */
export function isCallSleeveDayEligible(ratio: number | null, ceiling: number): boolean {
  return ratio !== null && Number.isFinite(ratio) && ratio > ceiling
}

/**
 * Assignment guard: true when spot is within `buffer` dollars of, or above,
 * the short call strike. `buffer <= 0` means the guard is disabled (see
 * getCallSleeveGuardBuffer) and this always returns false — the position
 * holds to settlement unguarded, deliberately, not by accident.
 */
export function isCallGuardTriggered(spot: number, shortStrike: number, buffer: number): boolean {
  if (!(buffer > 0)) return false
  return spot >= shortStrike - buffer
}

/* ------------------------------------------------------------------ */
/*  FORWARD-LOGGING ONLY — daily dealer-gamma context. Not statistically */
/*  confirmed; recorded so a sizing hypothesis (this sleeve loses on low */
/*  call-side dealer gamma at entry, wins big on high) can be re-tested  */
/*  later against the backtest's `igex_call` feature. Stores RAW values  */
/*  ONLY — tiers vs the trailing 20 sessions are computed OFFLINE, never */
/*  here. Never gates, sizes, or otherwise touches a trade. See          */
/*  scanner.ts logCallSleeveDailyContext / getGammaExposureComponents    */
/*  (tradier.ts) for how these numbers are actually sourced.            */
/* ------------------------------------------------------------------ */

/**
 * Live dealer-gamma read for one day's context row. Every field is nullable
 * because a vendor/data outage must never block or alter the sleeve — see
 * getGammaExposureComponents (tradier.ts) and getTvMarketStructure
 * (gex/trading-volatility-client.ts), both of which fail closed to null.
 * `gammaSource` names exactly where the non-null fields came from, or
 * 'unavailable' when nothing could be read.
 */
export interface CallSleeveGammaContext {
  callGamma: number | null
  putGamma: number | null
  netGamma: number | null
  gammaFlip: number | null
  putWall: number | null
  callWall: number | null
  gammaSource: string
}

/** A gamma context with every field null and an explicit 'unavailable' source. */
export const UNAVAILABLE_GAMMA_CONTEXT: CallSleeveGammaContext = {
  callGamma: null,
  putGamma: null,
  netGamma: null,
  gammaFlip: null,
  putWall: null,
  callWall: null,
  gammaSource: 'unavailable',
}

/** One row of `flame_call_sleeve_daily_context`. */
export interface CallSleeveDailyContextRow {
  trade_date: string
  evaluated_at: string
  spot: number | null
  vix_ratio: number | null
  call_short_strike_considered: number | null
  call_long_strike_considered: number | null
  entry_credit_seen: number | null
  decision: string
  call_gamma: number | null
  put_gamma: number | null
  net_gamma: number | null
  gamma_flip: number | null
  put_wall: number | null
  call_wall: number | null
  gamma_source: string
}

/**
 * Pure row builder — no DB, no network, so this is unit-testable in
 * isolation (see flame-call-sleeve.test.ts). `gamma` may be null (vendor
 * outage before a gamma read was even attempted); every gamma field then
 * writes NULL with gammaSource 'unavailable', never a fabricated number.
 */
export function buildCallSleeveDailyContextRow(input: {
  tradeDate: string
  evaluatedAt: Date
  spot: number | null
  vixRatio: number | null
  shortStrike: number | null
  longStrike: number | null
  entryCredit: number | null
  decision: string
  gamma: CallSleeveGammaContext | null
}): CallSleeveDailyContextRow {
  const g = input.gamma ?? UNAVAILABLE_GAMMA_CONTEXT
  return {
    trade_date: input.tradeDate,
    evaluated_at: input.evaluatedAt.toISOString(),
    spot: input.spot,
    vix_ratio: input.vixRatio,
    call_short_strike_considered: input.shortStrike,
    call_long_strike_considered: input.longStrike,
    entry_credit_seen: input.entryCredit,
    decision: input.decision,
    call_gamma: g.callGamma,
    put_gamma: g.putGamma,
    net_gamma: g.netGamma,
    gamma_flip: g.gammaFlip,
    put_wall: g.putWall,
    call_wall: g.callWall,
    gamma_source: g.gammaSource,
  }
}
