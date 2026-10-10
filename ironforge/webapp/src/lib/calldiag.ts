/**
 * CALLDIAG — IWM 10d/20d call diagonal, PAPER sleeve on FLAME accounts,
 * unlocked automatically once an account's equity clears CALLDIAG_MIN_EQUITY
 * (Leron, 2026-09-27: "Yes do that" to the profits-only CD1 spec in
 * dev/meltup/RESULT_calldiag_profits_only.md; unlock threshold raised to
 * $7,500 the same day, in-conversation follow-up — "CallDiag unlocks at
 * $7,500 and above", env-overridable since a later study might move it).
 *
 * Construction replicated EXACTLY from the research implementation
 * (tools/mr_book/gate_500s_iwm_intraday_retest.py `build()`/`exit_pos()`/
 * `ledger()`, unchanged) — every threshold below cites the line it came from:
 *   - front expiry = first listed expiry with (exp - tradeDate).days >= 10
 *     (FRONT_DTE); back expiry = first with .days >= 20 (BACK_DTE). Both
 *     must exist and differ, else no trade ("no_expiry").
 *   - spot = put-call-parity implied spot, MEDIAN of (strike + call_mid -
 *     put_mid) over strikes common to the front chain's calls and puts
 *     (the same formula `out/clusters/CLUSTER_calldiag_iwm.py`'s own
 *     `implied_spot()` documents as "the same put-call-parity implied-spot
 *     formula the trades' own spot/em columns use").
 *   - k_atm = the common strike nearest spot (ties broken toward the lower
 *     strike); em (expected move) = the ATM straddle's mid-to-mid SUM,
 *     `(callBid+callAsk)/2 + (putBid+putAsk)/2` — not divided by 2 again.
 *   - short strike (call side only — this sleeve never trades puts) = the
 *     LOWEST front-chain call strike >= spot + em; long (back) strike =
 *     short + W, W = CALLDIAG_WING_WIDTH = $1 (gate_500s's `W = 1.0`).
 *   - debit = 100 * (backLongAsk - frontShortBid); collateral (this sleeve's
 *     max-loss reference, confirmed structurally binding — 0/716 real trades
 *     ever breached it per RESULT_calldiag_profits_only.md) = 100*W +
 *     max(debit, 0).
 *   - exit = the LAST trading session strictly before the front expiry
 *     (`exit_pos()`'s own walk: keep advancing while the next date is still
 *     < front expiry); pnl = 100*(frontShortBidAtEntry - frontShortAskAtExit)
 *     + 100*(backLongBidAtExit - backLongAskAtEntry) - FEE*4 (FEE = $0.04,
 *     4 legs: open short+long, close short+long).
 *   - every session gets its own trade, overlapping positions allowed
 *     (`ledger(..., overlapping=True)` — the PRIMARY, held-out-tested column;
 *     the non-overlapping variant was never the one CD1/CD2 were built on).
 *
 * Vol stand-down gate replicated from `out/clusters/CLUSTER_calldiag_iwm.py`'s
 * frozen, held-out-tested rule (`clustered-loss-standdown-audit-19-strategies`
 * memory): stand down (skip new entries) when IWM's own trailing 5-session
 * realized volatility, annualized %, computed on PRIOR-CLOSE returns only
 * (never today's not-yet-known close), is <= 17.81 (the first-half discovery
 * median, frozen before the second-half test).
 *
 * Sizing: CD1 only — never more than 1 contract per account, ever (CD2's
 * cushion-scaled cap-3 variant was rejected: RESULT_calldiag_profits_only.md's
 * own robustness cut fails it, and its modeled worst day can exceed the
 * account's entire original deposit). Per-account gating mirrors FLINT's own
 * rule R1 (evaluateFlintProfitGate in flint.ts): eligible only when this
 * account's OWN (equity - floor) cushion clears the trade's collateral.
 *
 * PAPER ONLY in this PR — CALLDIAG_MODE='live' is deliberately UNIMPLEMENTED
 * at the order-placement layer (see calldiag-tracker.ts); getCallDiagMode()
 * still parses 'live' so the switch is future-safe, but no code path in this
 * PR ever places a real order under any mode.
 *
 * This file holds ONLY pure, DB/network-free logic (same split as flint.ts /
 * ebb-sizing.ts) so it is unit-testable without mocking Postgres or Tradier.
 */

export type CallDiagMode = 'off' | 'paper' | 'live'

/** Front leg: first listed expiry with dte >= this many days (gate_500s FRONT_DTE). */
export const CALLDIAG_FRONT_DTE = 10

/** Back leg: first listed expiry with dte >= this many days (gate_500s BACK_DTE). */
export const CALLDIAG_BACK_DTE = 20

/** Wing width, dollars (gate_500s W = 1.0). Long strike = short strike + this. */
export const CALLDIAG_WING_WIDTH = 1.0

/** Per-contract, per-leg fee (gate_500s FEE = 0.04). 4 legs per round trip (open x2, close x2). */
export const CALLDIAG_FEE_PER_LEG = 0.04

/** Never more than 1 contract per account — CD2's cap-3 scaling was rejected. */
export const CALLDIAG_MAX_CONTRACTS = 1

/** Default unlock threshold (Leron, 2026-09-27 follow-up: raised from $4,000 to $7,500). */
export const CALLDIAG_MIN_EQUITY_DEFAULT = 7500

/** Stand down (skip new entries) when trailing 5d realized vol (annualized %) <= this. */
export const CALLDIAG_RV5_STANDDOWN_THRESHOLD = 17.81

/** Minimum common front-chain strikes required before an implied spot is trusted. */
export const CALLDIAG_MIN_PARITY_STRIKES = 2

/**
 * off  — unset, or any value other than 'paper'/'live'. No row of any kind, ever.
 * paper — records to calldiag_positions only. No Tradier order placed.
 * live  — parsed for forward-compatibility; NOT wired to any order path in
 *         this PR (see calldiag-tracker.ts's header) — Leron approved PAPER
 *         only. Fails CLOSED: any unrecognized value resolves to 'off'.
 */
export function getCallDiagMode(): CallDiagMode {
  const raw = (process.env.CALLDIAG_MODE ?? '').trim().toLowerCase()
  if (raw === 'paper' || raw === 'live') return raw
  return 'off'
}

/**
 * CALLDIAG_MIN_EQUITY — the unlock threshold, in dollars. Default $7,500
 * (Leron, 2026-09-27). Env-overridable so a future study can move it without
 * a code change; unparsable or non-positive falls back to the default rather
 * than silently unlocking at $0.
 */
export function getCallDiagMinEquity(): number {
  const raw = Number(process.env.CALLDIAG_MIN_EQUITY)
  if (!Number.isFinite(raw) || raw <= 0) return CALLDIAG_MIN_EQUITY_DEFAULT
  return raw
}

/** Unlock rule: this account's OWN current equity must clear the threshold. `equity` unreadable never unlocks. */
export function isCallDiagUnlocked(equity: number | null, minEquity: number = getCallDiagMinEquity()): boolean {
  return equity != null && Number.isFinite(equity) && equity >= minEquity
}

/**
 * Trailing 5-session realized volatility, annualized %, on PRIOR-CLOSE daily
 * returns only — mirrors `CLUSTER_calldiag_iwm.py`'s `rv5_pct` exactly:
 * `ret.shift(1).rolling(5).std() * sqrt(252) * 100`, i.e. the sample (n-1)
 * standard deviation of the 5 most recent COMPLETED daily returns, never
 * touching the return that would require today's own not-yet-known close.
 * `returns` must be exactly the 5 most recent prior-close daily % returns,
 * oldest first; anything else returns null so the caller stands down rather
 * than guesses.
 */
export function computeTrailing5dRealizedVolPct(returns: number[]): number | null {
  const finite = returns.filter((r) => Number.isFinite(r))
  if (finite.length !== 5) return null
  const mean = finite.reduce((a, b) => a + b, 0) / finite.length
  const variance = finite.reduce((a, b) => a + (b - mean) ** 2, 0) / (finite.length - 1)
  return Math.sqrt(variance) * Math.sqrt(252) * 100
}

/**
 * Stand-down gate (frozen rule, `CLUSTER_calldiag_iwm.py`): stand down when
 * rv5Pct <= CALLDIAG_RV5_STANDDOWN_THRESHOLD (17.81). `rv5Pct == null` (vol
 * unmeasurable) fails CLOSED — stands down rather than guessing the tape is
 * lively enough to trade.
 */
export function isCallDiagStandDown(
  rv5Pct: number | null,
  threshold: number = CALLDIAG_RV5_STANDDOWN_THRESHOLD,
): boolean {
  if (rv5Pct == null || !Number.isFinite(rv5Pct)) return true
  return rv5Pct <= threshold
}

/** One (strike, right) NBBO quote. */
export interface CallDiagQuote {
  strike: number
  cp: 'C' | 'P'
  bid: number
  ask: number
}

/**
 * First listed expiry with (expiry - tradeDate) in whole days >= minDte —
 * `first_exp()` in gate_500s_iwm_intraday_retest.py, verbatim. `expirations`
 * need not be sorted; `tradeDate`/entries are ISO 'YYYY-MM-DD' strings.
 * null when no candidate clears minDte.
 */
export function pickCallDiagExpiry(expirations: string[], tradeDate: string, minDte: number): string | null {
  const t0 = Date.parse(tradeDate + 'T00:00:00Z')
  const candidates = expirations
    .filter((e) => {
      const days = Math.round((Date.parse(e + 'T00:00:00Z') - t0) / 86_400_000)
      return days >= minDte
    })
    .sort()
  return candidates.length > 0 ? candidates[0] : null
}

/**
 * Put-call-parity implied spot: median of (strike + callMid - putMid) over
 * strikes common to `quotes`' calls and puts, each leg requiring ask >= bid.
 * Mirrors `CLUSTER_calldiag_iwm.py`'s `implied_spot()` — the function that
 * module's own docstring says IS the formula the trades' own spot/em columns
 * use. null when fewer than CALLDIAG_MIN_PARITY_STRIKES common strikes exist.
 */
export function computeCallDiagImpliedSpot(quotes: CallDiagQuote[]): number | null {
  const calls = new Map<number, CallDiagQuote>()
  const puts = new Map<number, CallDiagQuote>()
  for (const q of quotes) {
    if (!(q.ask >= q.bid) || q.ask <= 0) continue
    const k = Math.round(q.strike * 1000) / 1000
    if (q.cp === 'C') calls.set(k, q)
    else if (q.cp === 'P') puts.set(k, q)
  }
  const common = Array.from(calls.keys()).filter((k) => puts.has(k))
  if (common.length < CALLDIAG_MIN_PARITY_STRIKES) return null
  const implied = common.map((k) => {
    const c = calls.get(k)!
    const p = puts.get(k)!
    const cMid = (c.bid + c.ask) / 2
    const pMid = (p.bid + p.ask) / 2
    return k + cMid - pMid
  })
  implied.sort((a, b) => a - b)
  const mid = Math.floor(implied.length / 2)
  return implied.length % 2 === 1 ? implied[mid] : (implied[mid - 1] + implied[mid]) / 2
}

export type CallDiagBuildSkipReason =
  | 'no_expiry'
  | 'spot_not_measurable'
  | 'no_common_strikes'
  | 'no_short_strike'
  | 'missing_leg_quote'

export interface CallDiagBuiltTrade {
  front: string
  back: string
  shortStrike: number
  longStrike: number
  spot: number
  em: number
  shortBid: number
  longAsk: number
  debit: number
  collateral: number
}

/**
 * Pure trade builder — byte-for-byte the arithmetic of `build()` in
 * gate_500s_iwm_intraday_retest.py, calls only (cp fixed to 'C'; this sleeve
 * never trades the put mirror). `frontQuotes` must contain BOTH calls and
 * puts for the front expiry (spot/em need both); `frontCallQuotes`/
 * `backCallQuotes` are looked up from the same set by strike. Returns a skip
 * reason string, matching the original's own string-return convention, or
 * the built trade.
 */
export function buildCallDiagTrade(
  front: string,
  back: string,
  frontQuotes: CallDiagQuote[],
  backCallQuotes: CallDiagQuote[],
  wingWidth: number = CALLDIAG_WING_WIDTH,
): CallDiagBuiltTrade | CallDiagBuildSkipReason {
  const spot = computeCallDiagImpliedSpot(frontQuotes)
  if (spot == null) return 'spot_not_measurable'

  const frontCalls = new Map<number, CallDiagQuote>()
  const frontPuts = new Map<number, CallDiagQuote>()
  for (const q of frontQuotes) {
    const k = Math.round(q.strike * 1000) / 1000
    if (q.cp === 'C') frontCalls.set(k, q)
    else if (q.cp === 'P') frontPuts.set(k, q)
  }
  const common = Array.from(frontCalls.keys()).filter((k) => frontPuts.has(k))
  if (common.length === 0) return 'no_common_strikes'

  let kAtm = common[0]
  let best = Math.abs(kAtm - spot)
  for (const k of common) {
    const d = Math.abs(k - spot)
    if (d < best || (d === best && k < kAtm)) {
      kAtm = k
      best = d
    }
  }
  const c = frontCalls.get(kAtm)!
  const p = frontPuts.get(kAtm)!
  const em = (c.bid + c.ask) / 2 + (p.bid + p.ask) / 2

  const target = spot + em
  const shortCandidates = Array.from(frontCalls.keys()).filter((k) => k >= target - 1e-9)
  if (shortCandidates.length === 0) return 'no_short_strike'
  const shortStrike = Math.min(...shortCandidates)
  const longStrike = shortStrike + wingWidth

  const shortQ = frontCalls.get(Math.round(shortStrike * 1000) / 1000)
  const backCalls = new Map<number, CallDiagQuote>()
  for (const q of backCallQuotes) backCalls.set(Math.round(q.strike * 1000) / 1000, q)
  const longQ = backCalls.get(Math.round(longStrike * 1000) / 1000)
  if (!shortQ || !longQ) return 'missing_leg_quote'

  const debit = Math.round((longQ.ask - shortQ.bid) * 100 * 100) / 100
  const collateral = Math.round((100 * wingWidth + Math.max(debit, 0)) * 100) / 100

  return { front, back, shortStrike, longStrike, spot, em, shortBid: shortQ.bid, longAsk: longQ.ask, debit, collateral }
}

/**
 * Exit day = the LAST trading session strictly before `frontExpiry` —
 * `exit_pos()`'s own walk (advance while the next date is still < front
 * expiry, keep the last one seen). `tradingDays` must be sorted ascending
 * ISO date strings and include `entryDate`. null (`no_session_before_expiry`)
 * when no such session exists after `entryDate` in `tradingDays`.
 */
export function pickCallDiagExitDate(tradingDays: string[], entryDate: string, frontExpiry: string): string | null {
  const i = tradingDays.indexOf(entryDate)
  if (i < 0) return null
  let xd: string | null = null
  let j = i + 1
  while (j < tradingDays.length && tradingDays[j] < frontExpiry) {
    xd = tradingDays[j]
    j += 1
  }
  return xd
}

/**
 * Exit P&L for one contract — byte-for-byte `exit_pos()`'s formula: buy back
 * the short leg at its exit ASK, sell the long leg at its exit BID, minus
 * FEE * 4 legs (open short+long, close short+long).
 */
export function computeCallDiagExitPnl(
  shortBidAtEntry: number,
  longAskAtEntry: number,
  shortAskAtExit: number,
  longBidAtExit: number,
  feePerLeg: number = CALLDIAG_FEE_PER_LEG,
): number {
  const pnl = 100 * (shortBidAtEntry - shortAskAtExit) + 100 * (longBidAtExit - longAskAtEntry) - feePerLeg * 4
  return Math.round(pnl * 100) / 100
}

export interface CallDiagCushionGateResult {
  eligible: boolean
  /** equity - floor, rounded to cents. null when equity or floor could not be read. */
  cushion: number | null
  /** null when eligible; otherwise the exact skip-reason string to log. */
  reason: string | null
}

/**
 * Per-account cushion gate — mirrors FLINT's own rule R1
 * (evaluateFlintProfitGate, flint.ts) exactly, fixed at CALLDIAG_MAX_CONTRACTS
 * (always 1; there is no step-down because there is nothing to step down
 * from — CD2's scaled sizing was rejected). `equity`/`floor` unreadable fails
 * CLOSED, same discipline as every other real-money gate in this codebase.
 */
export function evaluateCallDiagCushion(
  equity: number | null,
  floor: number | null,
  maxLoss: number,
): CallDiagCushionGateResult {
  if (equity == null || floor == null) {
    return { eligible: false, cushion: null, reason: 'skip:calldiag_profit_cushion(unreadable)' }
  }
  const cushion = Math.round((equity - floor) * 100) / 100
  if (cushion < maxLoss) {
    return {
      eligible: false,
      cushion,
      reason: `skip:calldiag_profit_cushion(cushion=$${cushion.toFixed(2)}<maxloss=$${maxLoss.toFixed(2)})`,
    }
  }
  return { eligible: true, cushion, reason: null }
}
