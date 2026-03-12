import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, validateBot } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

/**
 * GET /api/[bot]/daily-perf
 *
 * Returns the last 30 days of daily performance summaries.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  try {
    const rows = await dbQuery(
      `SELECT trade_date, trades_executed, positions_closed, realized_pnl
       FROM ${botTable(bot, 'daily_perf')}
       ORDER BY trade_date DESC
       LIMIT 30`,
    )

    const data = rows.map((r) => ({
      trade_date: String(r.trade_date).slice(0, 10),
      trades_executed: int(r.trades_executed),
      positions_closed: int(r.positions_closed),
      realized_pnl: num(r.realized_pnl),
    }))

    return NextResponse.json(data)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
