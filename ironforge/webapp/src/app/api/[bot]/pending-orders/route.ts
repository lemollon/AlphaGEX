import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/pending-orders
 *
 * Returns pending sandbox orders awaiting fill.
 * Only shows today's pending orders (prior days are dead by definition).
 *
 * Response:
 *   { pending_orders: [...], count: N }
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''

  try {
    const rows = await dbQuery(
      `SELECT pending_id, position_id, bot_name, dte_mode,
              order_type, sandbox_account, tradier_order_id,
              sandbox_contracts, ticker, expiration,
              put_short, put_long, call_short, call_long,
              paper_contracts, total_credit, spread_width, collateral_per,
              max_profit, max_loss,
              spot_price, vix, expected_move,
              status, fill_price, resolved_at,
              created_at, created_date
       FROM ${botTable(bot, 'pending_orders')}
       WHERE created_date = CURRENT_DATE
         ${dteFilter}
       ORDER BY created_at DESC
       LIMIT 50`,
    )

    const pending_orders = rows.map((r) => ({
      pending_id: r.pending_id,
      position_id: r.position_id,
      bot_name: r.bot_name,
      order_type: r.order_type,
      sandbox_account: r.sandbox_account,
      tradier_order_id: int(r.tradier_order_id),
      sandbox_contracts: int(r.sandbox_contracts),
      ticker: r.ticker || 'SPY',
      expiration: r.expiration,
      put_short: num(r.put_short),
      put_long: num(r.put_long),
      call_short: num(r.call_short),
      call_long: num(r.call_long),
      paper_contracts: int(r.paper_contracts),
      total_credit: num(r.total_credit),
      spread_width: num(r.spread_width),
      collateral_per: num(r.collateral_per),
      max_profit: num(r.max_profit),
      max_loss: num(r.max_loss),
      spot_price: num(r.spot_price),
      vix: num(r.vix),
      status: r.status,
      fill_price: r.fill_price != null ? num(r.fill_price) : null,
      resolved_at: r.resolved_at || null,
      created_at: r.created_at || null,
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
    if (msg.includes('TABLE_OR_VIEW_NOT_FOUND') || msg.includes('does not exist')) {
      return NextResponse.json({ pending_orders: [], count: 0, pending_count: 0 })
    }
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
