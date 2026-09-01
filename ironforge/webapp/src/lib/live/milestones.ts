import { dbQuery, botTable, escapeSql } from '@/lib/db'
import type { LiveBot } from './viewer'

/**
 * Non-P&L "tenure/system-health" badges — days connected, scans completed,
 * month number. Deliberately NOT performance-based: no dollar amount, no win
 * rate. This is engagement/trust framing ("your bot has been working"), not
 * a results claim.
 *
 * Architecture note: unlike getLiveSummary (scoped to dte_mode + account, no
 * customer identity), `daysConnected`/`monthNumber` need to be anchored to
 * THIS customer's activation — which requires `customerId`. Following the
 * same pattern as getMembership/getActivationConfirmation: this is called
 * separately at the route level (app/api/live/summary/route.ts) and merged
 * into the response via object spread, rather than threaded into
 * getLiveSummary's existing signature.
 *
 * Every field is independently nullable and fails soft per-field: one query
 * failing (or `customerId` being null, e.g. an operator view) must not blank
 * out a sibling field that succeeded. Never throws.
 */

export interface Milestones {
  daysConnected: number | null
  scanNumber: number | null
  monthNumber: number | null
}

/** Pure month-from-days math, split out so it is testable without a database. */
export function daysToMonthNumber(daysConnected: number): number {
  return Math.floor(daysConnected / 30) + 1
}

export async function getMilestones(customerId: string | null, bot: LiveBot): Promise<Milestones> {
  let daysConnected: number | null = null
  let monthNumber: number | null = null
  let scanNumber: number | null = null

  if (customerId) {
    try {
      const rows = await dbQuery<{ created_at: string | Date }>(
        `SELECT created_at FROM ironforge_customer_bots
          WHERE customer_id = '${escapeSql(customerId)}' AND bot = '${escapeSql(bot)}'`,
      )
      const createdAt = rows[0]?.created_at
      if (createdAt) {
        const created = createdAt instanceof Date ? createdAt : new Date(createdAt)
        daysConnected = Math.floor((Date.now() - created.getTime()) / 86_400_000)
        monthNumber = daysToMonthNumber(daysConnected)
      }
    } catch {
      // No account mapping row, or the customers table is unreachable — an
      // operator view or a fresh signup legitimately has no anchor here.
      daysConnected = null
      monthNumber = null
    }
  }

  try {
    const rows = await dbQuery<{ cnt: string | number }>(
      `SELECT COUNT(*) AS cnt FROM ${botTable(bot, 'logs')} WHERE level = 'SCAN'`,
    )
    scanNumber = Number(rows[0]?.cnt ?? 0)
  } catch {
    scanNumber = null
  }

  return { daysConnected, scanNumber, monthNumber }
}
