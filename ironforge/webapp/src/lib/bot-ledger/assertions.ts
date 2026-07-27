/**
 * Bot Ledger — reconciliation invariants.
 *
 * This page exists to PROVE a track record. A page whose trade table does not
 * add up to its own headline KPIs is worse than a page that is down: it is
 * affirmative evidence the numbers cannot be trusted. So a hard invariant
 * failure refuses to serve rather than serving something plausible.
 *
 * Every quantity here is an integer, so the tolerance is exactly zero.
 */

import { sumExact } from './money'
import type { BotSummary, LedgerTrade, PeriodStats, PublicLedgerTrade } from './types'

export class LedgerInvariantError extends Error {
  readonly detail: string
  constructor(detail: string) {
    super(`bot-ledger invariant violated: ${detail}`)
    this.name = 'LedgerInvariantError'
    this.detail = detail
  }
}

const DECIMAL_RE = /^-?\d+\.\d{1,2}$/

function assertDecimal(label: string, v: string | null): void {
  if (v === null) return
  if (typeof v !== 'string') throw new LedgerInvariantError(`${label} is not a string`)
  if (!DECIMAL_RE.test(v)) throw new LedgerInvariantError(`${label} is not a decimal string: ${v}`)
  if (v === '-0.00' || v === '-0.0') throw new LedgerInvariantError(`${label} is negative zero`)
  if (v.includes('Infinity') || v.includes('NaN')) {
    throw new LedgerInvariantError(`${label} is non-finite: ${v}`)
  }
}

/** Counts partition cleanly, and every ratio is null exactly when it must be. */
export function assertPeriodStats(label: string, stats: PeriodStats, trades: readonly LedgerTrade[]): void {
  if (stats.wins + stats.losses + stats.scratches !== stats.closed_trades) {
    throw new LedgerInvariantError(
      `${label}: ${stats.wins}+${stats.losses}+${stats.scratches} != ${stats.closed_trades}`,
    )
  }
  if (stats.closed_trades !== trades.length) {
    throw new LedgerInvariantError(`${label}: closed_trades disagrees with the trade set`)
  }

  const nullIff = (name: string, value: string | null, shouldBeNull: boolean): void => {
    if (shouldBeNull !== (value === null)) {
      throw new LedgerInvariantError(`${label}.${name} nullability is wrong (got ${String(value)})`)
    }
  }
  nullIff('win_rate_pct', stats.win_rate_pct, stats.closed_trades === 0)
  nullIff('avg_return_on_bp_pct', stats.avg_return_on_bp_pct, stats.closed_trades === 0)
  nullIff('avg_winner_pct', stats.avg_winner_pct, stats.wins === 0)
  nullIff('avg_loser_pct', stats.avg_loser_pct, stats.losses === 0)
  // profit_factor is null exactly when there are no losses — never Infinity.
  nullIff('profit_factor', stats.profit_factor, stats.losses === 0)

  assertDecimal(`${label}.win_rate_pct`, stats.win_rate_pct)
  assertDecimal(`${label}.avg_return_on_bp_pct`, stats.avg_return_on_bp_pct)
  assertDecimal(`${label}.profit_factor`, stats.profit_factor)
  assertDecimal(`${label}.avg_winner_pct`, stats.avg_winner_pct)
  assertDecimal(`${label}.avg_loser_pct`, stats.avg_loser_pct)
}

export function assertBotSummary(summary: BotSummary, periodTrades: readonly LedgerTrade[]): void {
  assertPeriodStats(`${summary.bot}.period`, summary, periodTrades)

  if (summary.lifetime_closed_trades < summary.closed_trades) {
    throw new LedgerInvariantError(`${summary.bot}: lifetime count is below the selected period count`)
  }
  if (summary.lifetime_wins > summary.lifetime_closed_trades) {
    throw new LedgerInvariantError(`${summary.bot}: lifetime wins exceed lifetime trades`)
  }
  assertDecimal(`${summary.bot}.lifetime_win_rate_pct`, summary.lifetime_win_rate_pct)
  if ((summary.lifetime_win_rate_pct === null) !== (summary.lifetime_closed_trades === 0)) {
    throw new LedgerInvariantError(`${summary.bot}: lifetime_win_rate_pct nullability is wrong`)
  }
  if (summary.current_win_streak < 0 || summary.current_win_streak > summary.lifetime_closed_trades) {
    throw new LedgerInvariantError(`${summary.bot}: implausible win streak`)
  }
}

/**
 * The check that actually catches silent breakage: our parse or our row
 * handling disagreeing with Postgres.
 *
 * Compares the SQL `SUM(realized_pnl)` over the deduped set against the same
 * sum recomputed in JavaScript from the rows we received. Both sides are exact
 * — Postgres sums in NUMERIC, we sum in integer cents — so the tolerance is
 * zero. Note this is the RAW position P&L, not the per-contract normalisation,
 * because only the raw figure has a Postgres-side counterpart to compare with.
 */
export function assertPersistedTotal(
  bot: string,
  persistedCents: number,
  rawPnlCents: readonly number[],
): void {
  const recomputed = sumExact(rawPnlCents)
  if (recomputed !== persistedCents) {
    throw new LedgerInvariantError(
      `${bot}: persisted total ${persistedCents} != recomputed ${recomputed}`,
    )
  }
}

/** Postgres and JavaScript must agree on how many rows survived dedupe. */
export function assertDedupeCount(bot: string, dedupedCount: number, received: number): void {
  if (dedupedCount !== received) {
    throw new LedgerInvariantError(
      `${bot}: dedupe count ${dedupedCount} != rows received ${received}`,
    )
  }
}

/** No forbidden field may reach the wire, whatever the projection did. */
const ALLOWED_TRADE_KEYS = new Set([
  'public_id',
  'closed_date',
  'bot',
  'setup',
  'buying_power_used',
  'net_result',
  'return_on_bp_pct',
  'outcome',
])

export function assertPublicTradeShape(items: readonly PublicLedgerTrade[]): void {
  for (const item of items) {
    for (const key of Object.keys(item)) {
      if (!ALLOWED_TRADE_KEYS.has(key)) {
        throw new LedgerInvariantError(`public trade carries a disallowed field: ${key}`)
      }
    }
    assertDecimal('trade.buying_power_used', item.buying_power_used)
    assertDecimal('trade.net_result', item.net_result)
    assertDecimal('trade.return_on_bp_pct', item.return_on_bp_pct)
    if (!/^\d{4}-\d{2}-\d{2}$/.test(item.closed_date)) {
      throw new LedgerInvariantError(`trade.closed_date is not a plain date: ${item.closed_date}`)
    }
  }
}
