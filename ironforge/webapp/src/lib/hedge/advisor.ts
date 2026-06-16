/**
 * Regime Hedge Advisor — pure sizing core (Phase 2).
 *
 * Given the day's latched hedge decision + the bots' aggregate capital-at-risk
 * (the "tail") + SPY spot, produce a concrete SPY PUT DEBIT SPREAD plan sized to
 * ~`coverage` of the tail. A debit spread is the right tool: an Iron Condor's loss
 * is bounded (≈ width − credit), so a bounded-payoff spread matches it and costs a
 * fraction of a naked put. Far-dated (30–45 DTE) so it survives a multi-day hostile
 * regime and can be rolled.
 *
 * Pure + total: no I/O. The server fills `tail`/`spy` (and optionally a real chain
 * debit) and calls buildHedgePlan. Calm days → { hedge:false }.
 */

export interface HedgeInputs {
  flagged: boolean
  reasons: string[]
  /** Aggregate dollar tail to cover (Σ active bots' planned IC max-loss). */
  tail: number
  /** SPY spot. */
  spy: number
  /** Fraction of the tail to cover with max payoff (1.0 = ~balance the day). */
  coverage?: number
  /** Long-leg out-of-the-money fraction (closer to ATM = more same-day delta). */
  longOtmPct?: number
  /** Target days-to-expiration for the hedge. */
  dte?: number
  /** Estimated debit as a fraction of spread width (real chain overrides). */
  debitPctOfWidth?: number
}

export interface HedgePlan {
  hedge: boolean
  reason: string
  spy: number
  dte: number
  long_strike: number
  short_strike: number
  width: number
  contracts: number
  est_max_payoff: number
  est_debit: number
  est_cost_pct: number // debit / max payoff
  coverage_pct: number // max payoff / tail
  /** Rough single-day offset on a bad day (far-dated OTM spread realizes a fraction of max). */
  est_sameday_offset: number
}

const DEFAULTS = {
  coverage: 1.0,
  longOtmPct: 0.015,
  dte: 35,
  debitPctOfWidth: 0.33,
}
const MIN_WIDTH = 5
const MAX_WIDTH = 30
/** Heuristic: a 30–45 DTE OTM put spread marks up ~this fraction of max on one bad day. */
const SAMEDAY_FACTOR = 0.25

const round1 = (x: number) => Math.round(x)
const money = (x: number) => Math.round(x * 100) / 100

/** Build the hedge plan. Calm/unflagged or bad inputs → { hedge:false }. */
export function buildHedgePlan(input: HedgeInputs): HedgePlan {
  const coverage = input.coverage ?? DEFAULTS.coverage
  const longOtmPct = input.longOtmPct ?? DEFAULTS.longOtmPct
  const dte = input.dte ?? DEFAULTS.dte
  const debitPct = input.debitPctOfWidth ?? DEFAULTS.debitPctOfWidth

  const none = (reason: string): HedgePlan => ({
    hedge: false, reason, spy: input.spy, dte,
    long_strike: 0, short_strike: 0, width: 0, contracts: 0,
    est_max_payoff: 0, est_debit: 0, est_cost_pct: 0, coverage_pct: 0, est_sameday_offset: 0,
  })

  if (!input.flagged) return none('Regime calm — no hedge today.')
  if (!(input.spy > 0) || !(input.tail > 0)) return none('Insufficient inputs (SPY / tail).')

  const targetPayoff = input.tail * coverage

  // Size width to put 1 contract near the target; widen via contracts only if a
  // single spread would exceed MAX_WIDTH (keeps strikes sensible).
  let contracts = 1
  let width = targetPayoff / (contracts * 100)
  while (width > MAX_WIDTH) {
    contracts += 1
    width = targetPayoff / (contracts * 100)
  }
  width = Math.max(MIN_WIDTH, round1(width))

  const longStrike = round1(input.spy * (1 - longOtmPct))
  const shortStrike = longStrike - width

  const estMaxPayoff = contracts * width * 100
  const estDebit = estMaxPayoff * debitPct

  return {
    hedge: true,
    reason: input.reasons.length ? input.reasons.join('; ') : 'Regime flagged',
    spy: money(input.spy),
    dte,
    long_strike: longStrike,
    short_strike: shortStrike,
    width,
    contracts,
    est_max_payoff: money(estMaxPayoff),
    est_debit: money(estDebit),
    est_cost_pct: money(estDebit / estMaxPayoff),
    coverage_pct: money(estMaxPayoff / input.tail),
    est_sameday_offset: money(estMaxPayoff * SAMEDAY_FACTOR),
  }
}

/** One-line human summary, e.g. "BUY 1× SPY 35D 731/719 put spread — ~$396, covers ~$1,200". */
export function hedgePlanText(p: HedgePlan): string {
  if (!p.hedge) return p.reason
  return (
    `BUY ${p.contracts}× SPY ${p.dte}D ${p.long_strike}/${p.short_strike} put spread ` +
    `— ~$${p.est_debit.toFixed(0)} debit, covers ~$${p.est_max_payoff.toFixed(0)} ` +
    `(${Math.round(p.coverage_pct * 100)}% of tail)`
  )
}
