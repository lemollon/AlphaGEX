import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    const rows = await query(`
      SELECT
        position_id, ticker, expiration,
        put_short_strike, put_long_strike,
        call_short_strike, call_long_strike,
        contracts, spread_width, total_credit,
        close_price, close_reason, realized_pnl,
        open_time, close_time,
        underlying_at_entry, vix_at_entry,
        wings_adjusted
      FROM ${botTable(bot, 'positions')}
      WHERE status IN ('closed', 'expired') AND dte_mode = '${dte}'
      ORDER BY close_time DESC
      LIMIT 50
    `)

    const trades = rows.map((r) => ({
      position_id: r.position_id,
      ticker: r.ticker,
      expiration: r.expiration,
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
      open_time: r.open_time,
      close_time: r.close_time,
      underlying_at_entry: num(r.underlying_at_entry),
      vix_at_entry: num(r.vix_at_entry),
      wings_adjusted: r.wings_adjusted === 'true' || r.wings_adjusted === '1',
    }))

    return NextResponse.json({ trades })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
