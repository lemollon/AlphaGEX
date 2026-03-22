import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const personParam = req.nextUrl.searchParams.get('person')
  const filterByPerson = personParam && personParam !== 'all'
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const personFilter = filterByPerson ? `AND person = '${escapeSql(personParam)}'` : ''

  try {
    const rows = await dbQuery(
      `SELECT
        position_id, ticker, expiration,
        put_short_strike, put_long_strike, put_credit,
        call_short_strike, call_long_strike, call_credit,
        contracts, spread_width, total_credit, max_loss, max_profit,
        underlying_at_entry, vix_at_entry, collateral_required,
        oracle_win_probability, oracle_advice,
        wings_adjusted, status, open_time
      FROM ${botTable(bot, 'positions')}
      WHERE status = 'open' ${dteFilter} ${personFilter}
      ORDER BY open_time DESC`,
    )

    const positions = rows.map((r) => ({
      position_id: r.position_id,
      ticker: r.ticker,
      expiration: r.expiration?.toISOString?.()?.slice(0, 10) || (r.expiration ? String(r.expiration).slice(0, 10) : null),
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
      wings_adjusted: r.wings_adjusted === true || r.wings_adjusted === 'true',
      open_time: r.open_time || null,
    }))

    return NextResponse.json({ positions })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
