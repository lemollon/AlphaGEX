/**
 * Bot Ledger — the only module in this folder that touches the database.
 *
 * Deliberately does NOT import from `src/lib/live/` — viewer.ts pulls in
 * `@/lib/tradier` (147 KB of broker client) that a public read endpoint has no
 * business loading.
 */

import { dbQuery, botTable, dteMode, escapeSql } from '@/lib/db'

import { PUBLIC_DATE_TZ, isLedgerBot, type LedgerBot } from './constants'
import type { RawLedgerRow } from './types'

/**
 * Eligibility, as a pure string builder so it can be asserted in unit tests
 * without a database.
 *
 * This REPRODUCES the operator console's filter exactly
 * (`src/app/api/[bot]/performance/route.ts`): closed-or-expired, has a realised
 * P&L, and matches the bot's current dte_mode. Publishing anything else would
 * mean the public page and the internal dashboard disagree about the same bot.
 *
 * Notes on individual clauses:
 *  - `dte_mode = '1DTE'` also drops the soft-deleted `ARCHIVED_1DTE` rows, which
 *    is the intended exclusion; the cutoff is disclosed on the card as the
 *    ledger inception date.
 *  - There is deliberately NO account_type filter. SPARK has no sandbox rows at
 *    all, and the console does not filter on it either; adding one here would
 *    silently empty the Spark card.
 *  - `DISTINCT ON (position_id)` guards the fact that position_id has no unique
 *    index and recovery endpoints can re-insert. Highest id wins (latest write).
 *  - `close_time < $1` pins row membership to the snapshot boundary, so a trade
 *    closing between the summary call and the log call cannot appear in one and
 *    not the other.
 */
export function eligibilitySql(bot: LedgerBot): string {
  if (!isLedgerBot(bot)) throw new Error(`not a ledger bot: ${bot}`)
  const table = botTable(bot, 'positions')
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const bpExpr = `COALESCE(NULLIF(collateral_required, 0), NULLIF(max_loss, 0))`

  return `SELECT DISTINCT ON (position_id)
       id,
       position_id,
       ticker,
       contracts,
       realized_pnl,
       ${bpExpr} AS bp,
       put_short_strike,
       put_long_strike,
       call_short_strike,
       call_long_strike,
       status,
       close_time,
       to_char((close_time AT TIME ZONE '${PUBLIC_DATE_TZ}')::date, 'YYYY-MM-DD') AS et_date,
       to_char((close_time AT TIME ZONE 'America/Chicago')::date, 'YYYY-MM-DD') AS ct_date
  FROM ${table}
 WHERE status IN ('closed', 'expired')
   AND realized_pnl IS NOT NULL
   AND close_time IS NOT NULL
   AND contracts > 0
   AND ${bpExpr} > 0
   ${dteFilter}
   AND close_time < $1
 ORDER BY position_id, id DESC`
}

/**
 * Companion aggregate over the SAME predicate.
 *
 * `pnl_total` is summed over the DEDUPED set specifically so it is comparable
 * to what JavaScript keeps — Postgres does the arithmetic in exact NUMERIC, so
 * any disagreement means our own parsing or filtering dropped something.
 * `raw_count` is the pre-dedupe count, which is the only way to see how many
 * rows DISTINCT ON collapsed.
 */
export function reconcileSql(bot: LedgerBot): string {
  if (!isLedgerBot(bot)) throw new Error(`not a ledger bot: ${bot}`)
  const table = botTable(bot, 'positions')
  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const bpExpr = `COALESCE(NULLIF(collateral_required, 0), NULLIF(max_loss, 0))`
  const predicate = `status IN ('closed', 'expired')
   AND realized_pnl IS NOT NULL
   AND close_time IS NOT NULL
   AND contracts > 0
   AND ${bpExpr} > 0
   ${dteFilter}
   AND close_time < $1`

  return `WITH deduped AS (
  SELECT DISTINCT ON (position_id) id, realized_pnl
    FROM ${table}
   WHERE ${predicate}
   ORDER BY position_id, id DESC
)
SELECT (SELECT COUNT(*)::int FROM ${table} WHERE ${predicate}) AS raw_count,
       COUNT(*)::int AS deduped_count,
       COALESCE(SUM(realized_pnl), 0) AS pnl_total
  FROM deduped`
}

export interface LoadedRows {
  rows: RawLedgerRow[]
  /** Rows matching the predicate before DISTINCT ON collapsed duplicates. */
  rawCount: number
  /** Deduped row count, per Postgres. */
  dedupedCount: number
  /** SQL-side SUM(realized_pnl) over the deduped set, as a NUMERIC string. */
  persistedPnl: unknown
}

/** Load every eligible row for one bot, pinned to a snapshot boundary. */
export async function loadEligibleRows(bot: LedgerBot, boundaryIso: string): Promise<LoadedRows> {
  const [rows, recon] = await Promise.all([
    dbQuery(eligibilitySql(bot), [boundaryIso]),
    dbQuery(reconcileSql(bot), [boundaryIso]),
  ])
  return {
    rows: rows as unknown as RawLedgerRow[],
    rawCount: Number(recon[0]?.raw_count ?? 0),
    dedupedCount: Number(recon[0]?.deduped_count ?? 0),
    persistedPnl: recon[0]?.pnl_total ?? '0',
  }
}
