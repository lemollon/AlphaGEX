import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/pending-orders
 *
 * Returns pending sandbox/production orders awaiting fill.
 * Only shows today's pending orders (prior days are dead by definition).
 *
 * Schema columns (per db.ts setupTables): id, position_id, ticker, expiration,
 * put_short_strike, put_long_strike, call_short_strike, call_long_strike,
 * contracts, total_credit, status, created_at, updated_at, dte_mode.
 *
 * Response:
 *   { pending_orders: [...], count: N, pending_count: N }
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''

  try {
    const rows = await dbQuery(
      `SELECT id, position_id, ticker, expiration,
              put_short_strike, put_long_strike, call_short_strike, call_long_strike,
              contracts, total_credit, status, created_at, updated_at
       FROM ${botTable(bot, 'pending_orders')}
       WHERE (created_at AT TIME ZONE 'America/Chicago')::date =
             (CURRENT_TIMESTAMP AT TIME ZONE 'America/Chicago')::date
         ${dteFilter}
       ORDER BY created_at DESC
       LIMIT 50`,
    )

    const pending_orders = rows.map((r) => ({
      id: r.id,
      position_id: r.position_id,
      ticker: r.ticker || 'SPY',
      expiration: r.expiration,
      put_short: num(r.put_short_strike),
      put_long: num(r.put_long_strike),
      call_short: num(r.call_short_strike),
      call_long: num(r.call_long_strike),
      contracts: int(r.contracts),
      total_credit: num(r.total_credit),
      status: r.status,
      created_at: r.created_at || null,
      updated_at: r.updated_at || null,
    }))

    // Count only pending (not yet resolved)
    const pending_count = pending_orders.filter((o) => o.status === 'pending').length

    return NextResponse.json({
      pending_orders,
      count: pending_orders.length,
      pending_count,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Table might not exist yet — return empty instead of 500
    if (msg.includes('does not exist') || msg.includes('relation') || msg.includes('undefined')) {
      return NextResponse.json({ pending_orders: [], count: 0, pending_count: 0 })
    }
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
