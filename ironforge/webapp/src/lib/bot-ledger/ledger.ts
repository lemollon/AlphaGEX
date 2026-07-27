/**
 * Bot Ledger — orchestrator.
 *
 * Loads the eligible universe once, projects it, derives the snapshot identity
 * from the projected content, and answers both public endpoints from the same
 * in-memory set. At ~80 rows total, loading everything and paging in memory is
 * the right call — it also makes the digest and the invariants free.
 */

import { dteMode } from '@/lib/db'

import {
  CALCULATION_VERSION,
  LEDGER_BOTS,
  LEDGER_BOT_NAME,
  LEDGER_BOT_TAGLINE,
  LEDGER_EXECUTION_MODE,
  LEDGER_MASCOT,
  NET_BASIS,
  PERIOD_DAYS,
  type LedgerBot,
  type LedgerBotFilter,
  type LedgerPeriod,
} from './constants'
import {
  projectTrade,
  setupBreakdown,
  sortNewestFirst,
  summarize,
  toPublicTrade,
  winStreak,
} from './calc'
import { centsFromNumericString, divRoundHalfAway, formatScaled } from './money'
import { loadEligibleRows } from './query'
import { bucketStartMs, classifySnapshot, digestOf, makeSnapshotId, parseSnapshotId } from './snapshot'
import { decodeCursor, encodeCursor, filterKey } from './cursor'
import {
  assertBotSummary,
  assertDedupeCount,
  assertPersistedTotal,
  assertPublicTradeShape,
  LedgerInvariantError,
} from './assertions'
import type {
  BotSummary,
  DataQuality,
  LedgerErrorCode,
  LedgerTrade,
  SummaryResponse,
  TradesResponse,
} from './types'

const DAY_MS = 86_400_000
const PCT_SCALE = 10_000

export class LedgerRequestError extends Error {
  readonly code: LedgerErrorCode
  readonly status: number
  readonly extra: Record<string, unknown>
  constructor(code: LedgerErrorCode, status: number, message: string, extra: Record<string, unknown> = {}) {
    super(message)
    this.name = 'LedgerRequestError'
    this.code = code
    this.status = status
    this.extra = extra
  }
}

interface Universe {
  boundaryMs: number
  asOf: string
  snapshotId: string
  digest: string
  byBot: Record<LedgerBot, LedgerTrade[]>
  dq: DataQuality
  newestClosedMs: number | null
}

function emptyDataQuality(): DataQuality {
  return {
    tz_date_divergences: 0,
    dedupe_dropped: 0,
    excluded_no_bp: 0,
    excluded_zero_legs: 0,
    excluded_invalid_contracts: 0,
    excluded_missing_close_time: 0,
    excluded_invalid_numeric: 0,
  }
}

/**
 * Build the whole eligible universe as of a bucket boundary.
 *
 * The boundary is the bucket START, not its end, so the published `as_of` is
 * literally the cutoff used for row membership — no trade can be inside the
 * window but outside the stated as_of.
 */
async function loadUniverse(nowMs: number): Promise<Universe> {
  const boundaryMs = bucketStartMs(nowMs)
  const asOf = new Date(boundaryMs).toISOString()
  const dq = emptyDataQuality()

  const byBot = {} as Record<LedgerBot, LedgerTrade[]>
  let newestClosedMs: number | null = null

  const loaded = await Promise.all(
    LEDGER_BOTS.map(async (bot) => ({ bot, ...(await loadEligibleRows(bot, asOf)) })),
  )

  for (const { bot, rows, rawCount, dedupedCount, persistedPnl } of loaded) {
    const dteLabel = dteMode(bot) ?? ''
    const trades: LedgerTrade[] = []

    // Raw P&L across every received row — the only figure with a Postgres-side
    // counterpart, so the only one that can prove our parsing agrees.
    const rawPnlCents: number[] = []
    let rawPnlParsable = true
    for (const row of rows) {
      try {
        rawPnlCents.push(centsFromNumericString(row.realized_pnl))
      } catch {
        rawPnlParsable = false
      }
    }
    assertDedupeCount(bot, dedupedCount, rows.length)
    if (rawPnlParsable) {
      assertPersistedTotal(bot, centsFromNumericString(persistedPnl), rawPnlCents)
    }

    for (const row of rows) {
      const result = projectTrade(row, bot, dteLabel)
      if (!result.ok) {
        switch (result.reason) {
          case 'INVALID_BUYING_POWER': dq.excluded_no_bp += 1; break
          case 'ZERO_LEGS': dq.excluded_zero_legs += 1; break
          case 'INVALID_CONTRACTS': dq.excluded_invalid_contracts += 1; break
          case 'MISSING_CLOSE_TIME': dq.excluded_missing_close_time += 1; break
          case 'INVALID_NUMERIC': dq.excluded_invalid_numeric += 1; break
        }
        continue
      }
      const t = result.trade
      if (t.tzDivergent) dq.tz_date_divergences += 1
      if (newestClosedMs === null || t.closedAtMs > newestClosedMs) newestClosedMs = t.closedAtMs
      trades.push(t)
    }

    dq.dedupe_dropped += Math.max(0, rawCount - rows.length)
    byBot[bot] = sortNewestFirst(trades)
  }

  const allDtos = LEDGER_BOTS.flatMap((b) => byBot[b].map(toPublicTrade))
  const digest = digestOf(allDtos)

  return {
    boundaryMs,
    asOf,
    snapshotId: makeSnapshotId(boundaryMs, digest),
    digest,
    byBot,
    dq,
    newestClosedMs,
  }
}

function windowTrades(trades: readonly LedgerTrade[], boundaryMs: number, period: LedgerPeriod): LedgerTrade[] {
  const startMs = boundaryMs - PERIOD_DAYS[period] * DAY_MS
  return trades.filter((t) => t.closedAtMs >= startMs && t.closedAtMs <= boundaryMs)
}

function buildBotSummary(bot: LedgerBot, lifetime: LedgerTrade[], period: LedgerTrade[]): BotSummary {
  const stats = summarize(period)
  const lifetimeWins = lifetime.filter((t) => t.outcome === 'WIN').length
  // `lifetime` is newest-first, so the oldest trade carries the inception date.
  const oldest = lifetime.length ? lifetime[lifetime.length - 1] : null

  return {
    bot,
    name: LEDGER_BOT_NAME[bot],
    tagline: LEDGER_BOT_TAGLINE[bot],
    execution_mode: LEDGER_EXECUTION_MODE[bot],
    mascot: LEDGER_MASCOT[bot],
    ...stats,
    lifetime_closed_trades: lifetime.length,
    lifetime_wins: lifetimeWins,
    lifetime_win_rate_pct:
      lifetime.length === 0
        ? null
        : formatScaled(divRoundHalfAway(lifetimeWins * PCT_SCALE, lifetime.length), 2),
    current_win_streak: winStreak(lifetime),
    inception_date: oldest ? oldest.closedDate : null,
    setups: setupBreakdown(lifetime),
  }
}

export async function getLedgerSummary(opts: {
  period: LedgerPeriod
  now: number
}): Promise<SummaryResponse> {
  const universe = await loadUniverse(opts.now)

  const bots = LEDGER_BOTS.map((bot) => {
    const lifetime = universe.byBot[bot]
    const period = windowTrades(lifetime, universe.boundaryMs, opts.period)
    const summary = buildBotSummary(bot, lifetime, period)
    assertBotSummary(summary, period)
    return summary
  })

  const freshness =
    universe.newestClosedMs === null
      ? null
      : Math.max(0, Math.round((opts.now - universe.newestClosedMs) / 1000))

  return {
    snapshot_id: universe.snapshotId,
    as_of: universe.asOf,
    period: opts.period,
    calculation_version: CALCULATION_VERSION,
    net_basis: NET_BASIS,
    data_freshness_seconds: freshness,
    generated_at: new Date(opts.now).toISOString(),
    reconciled: true,
    bots,
    data_quality: universe.dq,
  }
}

export async function getLedgerTrades(opts: {
  bot: LedgerBotFilter
  limit: number
  cursor?: string | null
  snapshotId?: string | null
  now: number
}): Promise<TradesResponse> {
  const universe = await loadUniverse(opts.now)

  // Honour a client-supplied snapshot, or 409 so it re-fetches rather than
  // rendering a log that disagrees with the cards it was shown beside.
  if (opts.snapshotId) {
    const parsed = parseSnapshotId(opts.snapshotId)
    const verdict = classifySnapshot(parsed, opts.now, universe.digest)
    if (verdict === 'INVALID_SNAPSHOT') {
      throw new LedgerRequestError('INVALID_SNAPSHOT', 400, 'Unrecognised snapshot.', {
        current_snapshot_id: universe.snapshotId,
      })
    }
    if (verdict === 'SNAPSHOT_EXPIRED') {
      throw new LedgerRequestError('SNAPSHOT_EXPIRED', 409, 'Refresh required.', {
        current_snapshot_id: universe.snapshotId,
      })
    }
  }

  const pool =
    opts.bot === 'all'
      ? sortNewestFirst(LEDGER_BOTS.flatMap((b) => universe.byBot[b]))
      : universe.byBot[opts.bot]

  const key = filterKey(opts.bot, opts.limit)
  let offset = 0
  if (opts.cursor) {
    const payload = decodeCursor(opts.cursor)
    if (!payload || payload.f !== key) {
      throw new LedgerRequestError('INVALID_CURSOR', 400, 'Invalid pagination cursor.')
    }
    if (payload.v !== CALCULATION_VERSION || payload.s !== universe.snapshotId) {
      throw new LedgerRequestError('SNAPSHOT_EXPIRED', 409, 'Refresh required.', {
        current_snapshot_id: universe.snapshotId,
      })
    }
    offset = payload.o
  }

  const page = pool.slice(offset, offset + opts.limit)
  const items = page.map(toPublicTrade)
  assertPublicTradeShape(items)

  const hasNext = offset + opts.limit < pool.length
  const hasPrev = offset > 0

  return {
    snapshot_id: universe.snapshotId,
    as_of: universe.asOf,
    calculation_version: CALCULATION_VERSION,
    net_basis: NET_BASIS,
    generated_at: new Date(opts.now).toISOString(),
    filter: { bot: opts.bot },
    items,
    total: pool.length,
    next_cursor: hasNext
      ? encodeCursor({ v: CALCULATION_VERSION, s: universe.snapshotId, f: key, o: offset + opts.limit })
      : null,
    previous_cursor: hasPrev
      ? encodeCursor({
          v: CALCULATION_VERSION,
          s: universe.snapshotId,
          f: key,
          o: Math.max(0, offset - opts.limit),
        })
      : null,
  }
}

export { LedgerInvariantError }
