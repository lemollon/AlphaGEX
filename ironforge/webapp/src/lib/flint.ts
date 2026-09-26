/**
 * FLINT — SPY 0DTE call credit spread, traded on FLAME's own production and
 * paper accounts, EVERY trading day (Leron, 2026-09-26: "i want it to go
 * live", named it "FLINT", approved the final spec). Formerly "FLAME-CALL",
 * which traded only the days FLAME's own VIX decay gate skipped the put
 * side — FLINT drops that gate entirely and trades unconditionally, one
 * lot, one trade per account per day. Own table (flint_positions), own arm
 * switch (FLINT_MODE), own production path (placeCallSpreadOrderAllAccounts
 * in tradier.ts). It can never read or write FLAME's put-side ledger,
 * sizing, or P&L, though it DOES read FLAME's put-side collateral (see
 * flintRequiredBp below) and FLAME's own per-account funded/high-water
 * ledger (getProductionLadderCapital in tradier.ts) for its own profit gate.
 *
 * This file holds ONLY pure, DB/network-free logic so it can be unit tested
 * without mocking Postgres or Tradier — same split as lib/ebb-sizing.ts.
 *
 * SHIPPED DISARMED. FLINT_MODE is unset by default, which getFlintMode()
 * resolves to 'off' — the scanner places no order of any kind (paper or
 * live) while off. 'live' additionally requires FLAME's own
 * isFlameLiveArmed() gate in tradier.ts, so a single missing env var on
 * either switch keeps this fully inert.
 */

export type FlintMode = 'off' | 'paper' | 'live'

/** Net credit floor default, per share. Below this the spread is not worth the assignment risk. */
export const FLINT_MIN_CREDIT_DEFAULT = 0.10

/** Fixed size for this sleeve — deliberately NOT the EBB count ladder (spec: 1 lot, flat). */
export const FLINT_MAX_CONTRACTS_DEFAULT = 1

/** Distance (dollars) inside which — or above — the short call strike trips the buy-back guard. */
export const FLINT_GUARD_BUFFER_DEFAULT = 0.25

/** Short call is placed at least this many dollars OTM at entry (default). The long call's wing is always +2, independent of this offset. */
export const FLINT_OTM_OFFSET_DEFAULT = 1

/** Round-trip commission for the 2-leg spread: $0.70/leg, matching every other spread convention in this codebase. */
export const FLINT_COMMISSION_PER_CONTRACT = 1.40

/** Minimum option buying power a live order must clear, per contract, before FLAME's own same-day put margin is added on top. */
export const FLINT_BP_FLOOR_PER_CONTRACT = 200

/**
 * off  — unset, or any value other than 'paper'/'live'. No order of any kind, ever.
 * paper — records to flint_positions only. No Tradier order placed.
 * live  — also places on FLAME's production account(s) via the same production
 *         path FLAME's put spread uses (still gated behind isFlameLiveArmed()).
 *
 * Fails CLOSED: any unrecognized value (typo, blank, "true", "1"...) resolves to 'off'.
 */
export function getFlintMode(): FlintMode {
  const raw = (process.env.FLINT_MODE ?? '').trim().toLowerCase()
  if (raw === 'paper' || raw === 'live') return raw
  return 'off'
}

/** FLINT_MAX_CONTRACTS — default 1, floored to a whole number, never below 1. */
export function getFlintMaxContracts(): number {
  const raw = Number(process.env.FLINT_MAX_CONTRACTS)
  if (!Number.isFinite(raw) || raw < 1) return FLINT_MAX_CONTRACTS_DEFAULT
  return Math.floor(raw)
}

/**
 * FLINT_GUARD_BUFFER — default 0.25. Setting it to '' or '0' disables the
 * guard entirely (the position then always holds to expiry/close, same as a
 * bot with no guard at all). Any other non-negative number is honored;
 * anything unparsable falls back to the default rather than silently
 * disabling real-money assignment protection.
 */
export function getFlintGuardBuffer(): number {
  const raw = process.env.FLINT_GUARD_BUFFER
  if (raw === undefined) return FLINT_GUARD_BUFFER_DEFAULT
  const trimmed = raw.trim()
  if (trimmed === '' || trimmed === '0') return 0
  const n = Number(trimmed)
  if (!Number.isFinite(n) || n < 0) return FLINT_GUARD_BUFFER_DEFAULT
  return n
}

/**
 * FLINT_OTM_OFFSET — dollars added to spot before the ceiling that picks the
 * short strike. Default 1. Unparsable or negative falls back to the default
 * rather than silently placing the short strike at or below spot.
 */
export function getFlintOtmOffset(): number {
  const raw = Number(process.env.FLINT_OTM_OFFSET)
  if (!Number.isFinite(raw) || raw < 0) return FLINT_OTM_OFFSET_DEFAULT
  return raw
}

/**
 * FLINT_MIN_CREDIT — default 0.10. Unparsable or negative falls back to the
 * default rather than silently accepting a worthless (or negative) credit.
 */
export function getFlintMinCredit(): number {
  const raw = Number(process.env.FLINT_MIN_CREDIT)
  if (!Number.isFinite(raw) || raw < 0) return FLINT_MIN_CREDIT_DEFAULT
  return raw
}

/**
 * Short call: the first whole-dollar strike at least `otmOffset` dollars
 * above spot at entry (default FLINT_OTM_OFFSET_DEFAULT = 1). Long call is
 * always short + $2 — the wing width is fixed, independent of the OTM offset.
 *
 *   spot 768.05, offset 1 -> ceil(769.05) = 770 short, 772 long
 *   spot 770.00, offset 1 -> ceil(771.00) = 771 short, 773 long
 */
export function computeFlintStrikes(
  spot: number,
  otmOffset: number = FLINT_OTM_OFFSET_DEFAULT,
): { short: number; long: number } {
  const short = Math.ceil(spot + otmOffset)
  return { short, long: short + 2 }
}

/** Net credit must clear the floor. Equal to the floor is accepted (>=, not >). */
export function meetsFlintCreditFloor(credit: number, minCredit: number = FLINT_MIN_CREDIT_DEFAULT): boolean {
  return Number.isFinite(credit) && credit >= minCredit
}

/**
 * The day filter. FLINT trades EVERY trading day (Leron, 2026-09-26) —
 * unlike the old FLAME-CALL sleeve, which traded only the days FLAME's own
 * VIX decay gate ratio exceeded its ceiling. `ratio` is still recorded in
 * flint_daily_context for research (the sizing hypothesis it was collected
 * for), but it is intentionally NEVER used to gate entry any more. This
 * function is deliberately unconditional — kept, and wired into the caller
 * as a no-op, so that a future accidental re-introduction of a ratio gate
 * shows up as a diff to THIS function, not a silent behavior change buried
 * in scanner.ts.
 */
export function isFlintDayEligible(_ratio: number | null): boolean {
  return true
}

/**
 * Assignment guard: true when spot is within `buffer` dollars of, or above,
 * the short call strike. `buffer <= 0` means the guard is disabled (see
 * getFlintGuardBuffer) and this always returns false — the position holds
 * to settlement unguarded, deliberately, not by accident.
 */
export function isFlintGuardTriggered(spot: number, shortStrike: number, buffer: number): boolean {
  if (!(buffer > 0)) return false
  return spot >= shortStrike - buffer
}

/**
 * Worst-case dollar loss for ONE FLINT trade: the full wing width minus the
 * credit collected, times 100, times contracts, plus the round-trip
 * commission. This is the number rule R1 (the per-account profit gate)
 * protects against — the WORST case, never max_profit or an expected value,
 * matching every other collateral/max-loss calculation in this codebase.
 */
export function flintMaxLoss(shortStrike: number, longStrike: number, credit: number, contracts: number): number {
  return (longStrike - shortStrike - credit) * 100 * contracts + FLINT_COMMISSION_PER_CONTRACT * contracts
}

export interface FlintProfitGateResult {
  eligible: boolean
  /** equity - floor, rounded to cents. null when equity or floor could not be read. */
  cushion: number | null
  /** null when eligible; otherwise the exact skip-reason string to log. */
  reason: string | null
}

/**
 * Rule R1 — the per-account profit gate. Leron, 2026-09-26: "a loss eats
 * into the total account profits" only, per account — never the funded
 * floor. `floor` is that account's net deposits: the funded/starting-capital
 * seed the EBB count ladder already tracks per production account (see
 * getProductionLadderCapital in tradier.ts) or, for the paper book, FLAME's
 * own paper ledger's starting_capital. `equity` is that account's CURRENT
 * balance — the same Tradier balance (or paper current_balance) the scanner
 * already reads elsewhere. `cushion` is the profit accumulated above the
 * funded floor; FLINT may only ever risk what sits inside that cushion.
 *
 * Evaluated INDEPENDENTLY per account — one account's cushion has no effect
 * on any other account's decision. `equity` or `floor` unreadable (null)
 * fails CLOSED: never guesses a number for a real-money gate.
 */
export function evaluateFlintProfitGate(
  equity: number | null,
  floor: number | null,
  maxLoss: number,
): FlintProfitGateResult {
  if (equity == null || floor == null) {
    return { eligible: false, cushion: null, reason: 'skip:flint_profit_cushion(unreadable)' }
  }
  const cushion = Math.round((equity - floor) * 100) / 100
  if (cushion < maxLoss) {
    return {
      eligible: false,
      cushion,
      reason: `skip:flint_profit_cushion(cushion=$${cushion.toFixed(2)}<maxloss=$${maxLoss.toFixed(2)})`,
    }
  }
  return { eligible: true, cushion, reason: null }
}

export interface FlintContractsDecision {
  /** 0 means neither size cleared rule R1 — the caller must skip entirely. */
  contracts: number
  /** The gate result for the chosen size (or, when contracts is 0, for `base` — the last one tried). */
  gate: FlintProfitGateResult
}

/**
 * Rule R1, applied to a favorable-day TARGET size with a fallback: tries
 * `desired` first, stepping down to `base` if only the extra lot(s) break
 * the cushion — Leron, 2026-09-26: "if cushion covers 1 but not 2, trade
 * 1." When `desired === base` (upsize off, or not eligible today) this is
 * exactly ONE evaluation of evaluateFlintProfitGate — byte-for-byte the
 * pre-upsize single-size gate. Shared, pure logic for both money paths
 * (scanner.ts's paper ledger and tradier.ts's per-account production/
 * sandbox loop) so the step-down rule lives in exactly one place.
 */
export function decideFlintContractsForCushion(
  desired: number,
  base: number,
  equity: number | null,
  floor: number | null,
  shortStrike: number,
  longStrike: number,
  credit: number,
): FlintContractsDecision {
  const candidates = desired > base ? [desired, base] : [desired]
  let gate: FlintProfitGateResult = { eligible: false, cushion: null, reason: 'skip:flint_profit_cushion(unreadable)' }
  for (const c of candidates) {
    const loss = flintMaxLoss(shortStrike, longStrike, credit, c)
    gate = evaluateFlintProfitGate(equity, floor, loss)
    if (gate.eligible) return { contracts: c, gate }
  }
  return { contracts: 0, gate }
}

/**
 * FLINT_FAVORABLE_UPSIZE — off|on, unset = off (Leron, 2026-09-26: "Yes" to
 * "Build both into the bots, with FLINT's size-up switching itself on at
 * day 20?"). At the 13:05 CT entry, +1 contract (base stays
 * FLINT_MAX_CONTRACTS_DEFAULT = 1; the upsize path's effective ceiling is
 * 2) when today's call-side dealer gamma is in the top third of the
 * trailing 20 LOGGED sessions (see evaluateFlintGammaUpsize below) — the
 * hypothesis flint_daily_context.call_gamma was collected to test. SELF-
 * ACTIVATES once 20 qualifying sessions exist; before that it is inactive,
 * not skipped-for-cushion — a different log line so an operator can tell
 * "still warming up" apart from "gated by real money." Fails CLOSED on any
 * unrecognized value.
 */
export function getFlintFavorableUpsizeMode(): boolean {
  return (process.env.FLINT_FAVORABLE_UPSIZE ?? '').trim().toLowerCase() === 'on'
}

/** Minimum trailing LOGGED sessions (same gamma_source as today) before the gamma upsize can activate at all. */
export const FLINT_GAMMA_UPSIZE_MIN_SESSIONS = 20

/** 67th percentile — "top third" of the trailing sample. */
export const FLINT_GAMMA_UPSIZE_PERCENTILE = 0.67

/**
 * Linear-interpolated percentile of `values` (numpy's default method) —
 * pure, no DB. Non-finite entries are dropped before ranking. null on an
 * empty sample; the caller must skip, never guess.
 */
export function percentileOf(values: number[], p: number): number | null {
  const finite = values.filter((v) => Number.isFinite(v))
  if (finite.length === 0) return null
  const sorted = [...finite].sort((a, b) => a - b)
  const idx = p * (sorted.length - 1)
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo)
}

export interface FlintGammaUpsizeResult {
  eligible: boolean
  /** null when eligible; otherwise the exact skip/inactive reason to log. */
  reason: string | null
  /** The 67th-percentile threshold today's call_gamma was compared against. null before day 20. */
  threshold: number | null
  /** How many trailing LOGGED sessions (matching today's gamma_source) fed the threshold. */
  sessionsUsed: number
}

/**
 * The gamma upsize decision — a MARKET-WIDE signal (dealer call-side gamma),
 * evaluated ONCE per scan tick and shared by every account (the paper book
 * and each production account independently apply their OWN cushion/BP
 * check against the resulting contract count; this function decides only
 * whether 2 is even the target). `trailingCallGamma` must already be
 * filtered by the caller to rows with a non-null call_gamma and the SAME
 * gamma_source as `todayCallGamma` — mixing sources would compare numbers
 * from different vendors/methodologies.
 *
 * `n < FLINT_GAMMA_UPSIZE_MIN_SESSIONS` -> INACTIVE (self-activation not
 * reached yet), never a cushion skip — distinct log line so "still warming
 * up" cannot be mistaken for "gated by real money."
 */
export function evaluateFlintGammaUpsize(
  todayCallGamma: number | null,
  trailingCallGamma: number[],
  minSessions: number = FLINT_GAMMA_UPSIZE_MIN_SESSIONS,
  percentile: number = FLINT_GAMMA_UPSIZE_PERCENTILE,
): FlintGammaUpsizeResult {
  const n = trailingCallGamma.length
  if (n < minSessions) {
    return { eligible: false, reason: `inactive: n=${n}/${minSessions} sessions logged`, threshold: null, sessionsUsed: n }
  }
  if (todayCallGamma == null || !Number.isFinite(todayCallGamma)) {
    return { eligible: false, reason: 'skip:flint_gamma_upsize(today_call_gamma_unreadable)', threshold: null, sessionsUsed: n }
  }
  const threshold = percentileOf(trailingCallGamma, percentile)
  if (threshold == null) {
    return { eligible: false, reason: 'skip:flint_gamma_upsize(threshold_unreadable)', threshold: null, sessionsUsed: n }
  }
  const eligible = todayCallGamma >= threshold
  return {
    eligible,
    reason: eligible ? null : `skip:flint_gamma_upsize(today=${todayCallGamma}<p67=${threshold.toFixed(4)})`,
    threshold,
    sessionsUsed: n,
  }
}

/* ------------------------------------------------------------------ */
/*  FORWARD-LOGGING ONLY — daily dealer-gamma context. Not statistically */
/*  confirmed; recorded so a sizing hypothesis (this sleeve loses on low */
/*  call-side dealer gamma at entry, wins big on high) can be re-tested  */
/*  later against the backtest's `igex_call` feature. Stores RAW values  */
/*  ONLY — tiers vs the trailing 20 sessions are computed OFFLINE, never */
/*  here. Never gates, sizes, or otherwise touches a trade. See          */
/*  scanner.ts logFlintDailyContext / getGammaExposureComponents         */
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
export interface FlintGammaContext {
  callGamma: number | null
  putGamma: number | null
  netGamma: number | null
  gammaFlip: number | null
  putWall: number | null
  callWall: number | null
  gammaSource: string
}

/** A gamma context with every field null and an explicit 'unavailable' source. */
export const UNAVAILABLE_FLINT_GAMMA_CONTEXT: FlintGammaContext = {
  callGamma: null,
  putGamma: null,
  netGamma: null,
  gammaFlip: null,
  putWall: null,
  callWall: null,
  gammaSource: 'unavailable',
}

/** One row of `flint_daily_context`. */
export interface FlintDailyContextRow {
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
 * isolation (see flint.test.ts). `gamma` may be null (vendor outage before a
 * gamma read was even attempted); every gamma field then writes NULL with
 * gammaSource 'unavailable', never a fabricated number.
 */
export function buildFlintDailyContextRow(input: {
  tradeDate: string
  evaluatedAt: Date
  spot: number | null
  vixRatio: number | null
  shortStrike: number | null
  longStrike: number | null
  entryCredit: number | null
  decision: string
  gamma: FlintGammaContext | null
}): FlintDailyContextRow {
  const g = input.gamma ?? UNAVAILABLE_FLINT_GAMMA_CONTEXT
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
