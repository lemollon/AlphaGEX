import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, validateBot, dteMode, escapeSql, CT_TODAY } from '@/lib/db'

export const dynamic = 'force-dynamic'

/**
 * Debug endpoint: show raw DB values for today's closed trades
 * so we can verify the IC return % math with actual data.
 *
 * GET /api/{bot}/debug-ic-return
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  const rows = await dbQuery(
    `SELECT position_id, close_reason, total_credit, close_price, contracts,
            realized_pnl, collateral_required, open_time, close_time
     FROM ${botTable(bot, 'positions')}
     WHERE status IN ('closed', 'expired')
       AND realized_pnl IS NOT NULL
       AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
       ${dteFilter}
     ORDER BY close_time ASC`,
  )

  const trades = rows.map((r) => {
    const credit = num(r.total_credit)
    const closePrice = num(r.close_price)
    const contracts = int(r.contracts) || 1
    const pnl = num(r.realized_pnl)
    // IC return: (credit - close_price) / credit
    const icReturnDirect = credit > 0 ? ((credit - closePrice) / credit) * 100 : 0
    // Alternative: pnl / (credit * contracts * 100)
    const icReturnFromPnl = credit > 0 ? (pnl / (credit * contracts * 100)) * 100 : 0

    return {
      position_id: r.position_id,
      close_reason: r.close_reason,
      total_credit: credit,
      close_price: closePrice,
      contracts,
      realized_pnl: pnl,
      collateral: num(r.collateral_required),
      open_time: r.open_time,
      close_time: r.close_time,
      // Computed
      ic_return_direct_pct: Math.round(icReturnDirect * 100) / 100,
      ic_return_from_pnl_pct: Math.round(icReturnFromPnl * 100) / 100,
      credit_exposure_dollars: credit * contracts * 100,
    }
  })

  // Aggregate
  let totalPnl = 0
  let totalCreditExposure = 0
  for (const t of trades) {
    totalPnl += t.realized_pnl
    totalCreditExposure += t.credit_exposure_dollars
  }

  return NextResponse.json({
    bot,
    today_trade_count: trades.length,
    total_realized_pnl: Math.round(totalPnl * 100) / 100,
    total_credit_exposure: Math.round(totalCreditExposure * 100) / 100,
    aggregate_ic_return_pct: totalCreditExposure > 0
      ? Math.round((totalPnl / totalCreditExposure) * 10000) / 100
      : null,
    trades,
  })
}
