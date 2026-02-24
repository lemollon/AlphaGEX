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
        put_short_strike, put_long_strike, put_credit,
        call_short_strike, call_long_strike, call_credit,
        contracts, spread_width, total_credit, max_loss, max_profit,
        underlying_at_entry, vix_at_entry, collateral_required,
        oracle_win_probability, oracle_advice,
        wings_adjusted, status, open_time
      FROM ${botTable(bot, 'positions')}
      WHERE status = 'open' AND dte_mode = '${dte}'
      ORDER BY open_time DESC
    `)

    const positions = rows.map((r) => ({
      position_id: r.position_id,
      ticker: r.ticker,
      expiration: r.expiration,
      put_short_strike: num(r.put_short_strike),
      put_long_strike: num(r.put_long_strike),
      put_credit: num(r.put_credit),
      call_short_strike: num(r.call_short_strike),
      call_long_strike: num(r.call_long_strike),
      call_credit: num(r.call_credit),
      contracts: int(r.contracts),
      spread_width: num(r.spread_width),
      total_credit: num(r.total_credit),
      max_loss: num(r.max_loss),
      max_profit: num(r.max_profit),
      underlying_at_entry: num(r.underlying_at_entry),
      vix_at_entry: num(r.vix_at_entry),
      collateral_required: num(r.collateral_required),
      oracle_win_probability: num(r.oracle_win_probability),
      oracle_advice: r.oracle_advice,
      wings_adjusted: r.wings_adjusted === 'true' || r.wings_adjusted === '1',
      open_time: r.open_time,
    }))

    return NextResponse.json({ positions })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
