/**
 * Bot Ledger — the calculation core.
 *
 * PURE. No database, no clock, no environment. Everything this module touches
 * is an integer, which is what makes the KPI test vectors assertable without a
 * DB and what makes the published numbers reproducible by hand from the trade
 * log — the Definition of Done for this page.
 */

import { publicIdFor } from './public-id'
import {
  centsFromNumericString,
  divRoundHalfAway,
  formatScaled,
  meanExact,
  sumExact,
  LedgerMathError,
} from './money'
import type { LedgerBot } from './constants'
import type {
  LedgerTrade,
  Outcome,
  PeriodStats,
  ProjectionResult,
  PublicLedgerTrade,
  RawLedgerRow,
} from './types'

/** Percentages are carried as integer hundredths of a percent (2 dp). */
const PCT_SCALE = 10_000
const TWO_DP = 2

/**
 * Leg count, derived from which strike pairs are populated.
 *
 * FLAME changed strategy in April 2026: earlier rows are 4-leg iron condors,
 * later rows are 2-leg put credit spreads written with the call strikes zeroed
 * (see scanner.ts tryOpenFlamePutSpread). Reading the strikes rather than a
 * date keeps both epochs correct without a hardcoded cutover.
 */
export function legCountOf(row: {
  put_short_strike: unknown
  put_long_strike: unknown
  call_short_strike: unknown
  call_long_strike: unknown
}): number {
  const num = (v: unknown): number => {
    const n = Number(v)
    return Number.isFinite(n) ? n : 0
  }
  const puts = num(row.put_short_strike) > 0 && num(row.put_long_strike) > 0 ? 2 : 0
  const calls = num(row.call_short_strike) > 0 && num(row.call_long_strike) > 0 ? 2 : 0
  return puts + calls
}

/**
 * Public strategy label. Derived from leg count and DTE only — never from
 * close_reason, strikes, or any signal field, all of which the spec forbids
 * publishing.
 */
export function setupLabel(legs: number, dteLabel: string, ticker: string): string {
  const structure = legs === 4 ? 'Iron Condor' : 'Put Credit Spread'
  return `${ticker} ${dteLabel} ${structure}`
}

export function classifyOutcome(netCents: number): Outcome {
  if (netCents > 0) return 'WIN'
  if (netCents < 0) return 'LOSS'
  return 'SCRATCH'
}

/**
 * Project one database row onto the public one-contract basis.
 *
 * Historical positions were sized 1-127 contracts, so every published figure is
 * normalised to a single modelled contract. Rounding happens exactly once, at
 * `pnl / contracts`; everything after that is exact integer arithmetic, so
 * "classify on the rounded net" has no ambiguity left in it.
 */
export function projectTrade(
  row: RawLedgerRow,
  bot: LedgerBot,
  dteLabel: string,
): ProjectionResult {
  const contracts = Number(row.contracts)
  if (!Number.isInteger(contracts) || contracts <= 0) {
    return { ok: false, reason: 'INVALID_CONTRACTS' }
  }
  if (row.close_time === null || row.close_time === undefined) {
    return { ok: false, reason: 'MISSING_CLOSE_TIME' }
  }

  const legs = legCountOf(row)
  if (legs === 0) return { ok: false, reason: 'ZERO_LEGS' }

  let pnlCents: number
  let bpCents: number
  try {
    pnlCents = centsFromNumericString(row.realized_pnl)
    bpCents = divRoundHalfAway(centsFromNumericString(row.bp), contracts)
  } catch (err) {
    if (err instanceof LedgerMathError) return { ok: false, reason: 'INVALID_NUMERIC' }
    throw err
  }
  if (bpCents <= 0) return { ok: false, reason: 'INVALID_BUYING_POWER' }

  // The single inexact step in the whole pipeline.
  const netCents = divRoundHalfAway(pnlCents, contracts)
  const returnOnBpHpct = divRoundHalfAway(netCents * PCT_SCALE, bpCents)

  const closedAtMs = new Date(String(row.close_time)).getTime()
  if (!Number.isFinite(closedAtMs)) return { ok: false, reason: 'MISSING_CLOSE_TIME' }

  const etDate = String(row.et_date ?? '')
  const ctDate = String(row.ct_date ?? '')
  const rowId = Number(row.id)
  const ticker = row.ticker ? String(row.ticker) : 'SPY'

  const trade: LedgerTrade = {
    publicId: publicIdFor(bot, String(row.id)),
    bot,
    closedDate: etDate,
    closedAtMs,
    rowId: Number.isFinite(rowId) ? rowId : 0,
    setup: setupLabel(legs, dteLabel, ticker),
    legs,
    bpCents,
    netCents,
    returnOnBpHpct,
    outcome: classifyOutcome(netCents),
    tzDivergent: etDate !== ctDate,
  }
  return { ok: true, trade }
}

/**
 * Reduce a set of eligible trades to the published KPI block.
 *
 * Averages are taken over the STORED per-trade percentages, not over unrounded
 * ratios, so the visible column provably averages to the visible headline. A
 * reader with a calculator can check the page.
 */
export function summarize(trades: readonly LedgerTrade[]): PeriodStats {
  const closed = trades.length
  const wins = trades.filter((t) => t.outcome === 'WIN')
  const losses = trades.filter((t) => t.outcome === 'LOSS')
  const scratches = trades.filter((t) => t.outcome === 'SCRATCH')

  const grossProfit = sumExact(wins.map((t) => t.netCents))
  const grossLoss = Math.abs(sumExact(losses.map((t) => t.netCents)))

  const pct = (hpct: number | null): string | null =>
    hpct === null ? null : formatScaled(hpct, TWO_DP)

  return {
    closed_trades: closed,
    wins: wins.length,
    losses: losses.length,
    scratches: scratches.length,
    win_rate_pct: closed === 0 ? null : formatScaled(divRoundHalfAway(wins.length * PCT_SCALE, closed), TWO_DP),
    avg_return_on_bp_pct: pct(meanExact(trades.map((t) => t.returnOnBpHpct))),
    // null, never Infinity: a bot with no losses has no profit factor.
    profit_factor:
      grossLoss === 0 ? null : formatScaled(divRoundHalfAway(grossProfit * 100, grossLoss), TWO_DP),
    avg_winner_pct: pct(meanExact(wins.map((t) => t.returnOnBpHpct))),
    avg_loser_pct: pct(meanExact(losses.map((t) => t.returnOnBpHpct))),
  }
}

/**
 * Consecutive wins from the newest trade backward.
 *
 * A SCRATCH terminates a streak exactly as a LOSS does — it is an eligible
 * closed trade that is not a win.
 */
export function winStreak(newestFirst: readonly LedgerTrade[]): number {
  let n = 0
  for (const t of newestFirst) {
    if (t.outcome !== 'WIN') break
    n += 1
  }
  return n
}

/** Trade counts by public setup label, so a strategy change is visible. */
export function setupBreakdown(trades: readonly LedgerTrade[]): Record<string, number> {
  const out: Record<string, number> = {}
  for (const t of trades) out[t.setup] = (out[t.setup] ?? 0) + 1
  return out
}

/** Newest first, with a deterministic tie-break so pagination is stable. */
export function sortNewestFirst(trades: readonly LedgerTrade[]): LedgerTrade[] {
  return [...trades].sort((a, b) => b.closedAtMs - a.closedAtMs || b.rowId - a.rowId)
}

/** The allowlisted public shape. Nothing else may cross the wire. */
export function toPublicTrade(t: LedgerTrade): PublicLedgerTrade {
  return {
    public_id: t.publicId,
    closed_date: t.closedDate,
    bot: t.bot,
    setup: t.setup,
    buying_power_used: formatScaled(t.bpCents, TWO_DP),
    net_result: formatScaled(t.netCents, TWO_DP),
    return_on_bp_pct: formatScaled(t.returnOnBpHpct, TWO_DP),
    outcome: t.outcome.toLowerCase() as PublicLedgerTrade['outcome'],
  }
}
