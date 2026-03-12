import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  try {
    const rows = await dbQuery(
      `SELECT
        position_id, ticker, expiration,
        put_short_strike, put_long_strike,
        call_short_strike, call_long_strike,
        contracts, spread_width, total_credit,
        close_price, close_reason, realized_pnl,
        open_time, close_time,
        underlying_at_entry, vix_at_entry,
        wings_adjusted, sandbox_order_id
      FROM ${botTable(bot, 'positions')}
      WHERE status IN ('closed', 'expired') ${dteFilter}
      ORDER BY close_time DESC
      LIMIT 50`,
    )

    const trades = rows.map((r) => ({
      position_id: r.position_id,
      ticker: r.ticker,
      expiration: r.expiration ? String(r.expiration).slice(0, 10) : null,
      put_short_strike: num(r.put_short_strike),
      put_long_strike: num(r.put_long_strike),
      call_short_strike: num(r.call_short_strike),
      call_long_strike: num(r.call_long_strike),
      contracts: int(r.contracts),
      spread_width: num(r.spread_width),
      total_credit: num(r.total_credit),
      close_price: num(r.close_price),
      close_reason: r.close_reason || '',
      realized_pnl: num(r.realized_pnl),
      open_time: r.open_time || null,
      close_time: r.close_time || null,
      underlying_at_entry: num(r.underlying_at_entry),
      vix_at_entry: num(r.vix_at_entry),
      wings_adjusted: r.wings_adjusted === true || r.wings_adjusted === 'true',
      sandbox_order_ids: r.sandbox_order_id ? (() => { try { return JSON.parse(r.sandbox_order_id) } catch { return null } })() : null,
    }))

    return NextResponse.json({ trades })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
