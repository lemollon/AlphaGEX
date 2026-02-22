import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, validateBot } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    const [capitalRows, curveRows] = await Promise.all([
      query(`
        SELECT starting_capital
        FROM ${botTable(bot, 'paper_account')}
        WHERE is_active = TRUE AND dte_mode = '${dte}'
        LIMIT 1
      `),
      query(`
        SELECT
          close_time,
          realized_pnl,
          SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
        FROM ${botTable(bot, 'positions')}
        WHERE status IN ('closed', 'expired')
          AND realized_pnl IS NOT NULL
          AND close_time IS NOT NULL
          AND dte_mode = '${dte}'
        ORDER BY close_time
      `),
    ])

    const startingCapital = num(capitalRows[0]?.starting_capital) || 5000

    const curve = curveRows.map((row) => {
      const cumPnl = num(row.cumulative_pnl)
      return {
        timestamp: row.close_time,
        pnl: num(row.realized_pnl),
        cumulative_pnl: cumPnl,
        equity: Math.round((startingCapital + cumPnl) * 100) / 100,
      }
    })

    return NextResponse.json({ starting_capital: startingCapital, curve })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
