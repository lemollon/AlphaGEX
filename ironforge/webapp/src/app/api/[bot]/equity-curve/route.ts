import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, escapeSql, validateBot, dteMode } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const period = req.nextUrl.searchParams.get('period') || 'all'
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  try {
    const capitalQuery = dbQuery(
      `SELECT starting_capital
       FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter}
       LIMIT 1`,
    )

    const curveQuery = dbQuery(
      `SELECT
        close_time,
        realized_pnl,
        SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
      FROM ${botTable(bot, 'positions')}
      WHERE status IN ('closed', 'expired')
        AND realized_pnl IS NOT NULL
        AND close_time IS NOT NULL
        ${dteFilter}
      ORDER BY close_time`,
    )

    const [capitalRows, curveRows] = await Promise.all([capitalQuery, curveQuery])

    const startingCapital = num(capitalRows[0]?.starting_capital) || 10000

    let curve = curveRows.map((row) => {
      const cumPnl = num(row.cumulative_pnl)
      return {
        timestamp: row.close_time || null,
        pnl: num(row.realized_pnl),
        cumulative_pnl: cumPnl,
        equity: Math.round((startingCapital + cumPnl) * 100) / 100,
      }
    })

    if (period !== 'all' && curve.length > 0) {
      const now = new Date()
      let cutoff: Date
      switch (period) {
        case '1d':
          cutoff = new Date(now.getFullYear(), now.getMonth(), now.getDate())
          break
        case '1w':
          cutoff = new Date(now.getTime() - 7 * 86_400_000)
          break
        case '1m':
          cutoff = new Date(now.getTime() - 30 * 86_400_000)
          break
        case '3m':
          cutoff = new Date(now.getTime() - 90 * 86_400_000)
          break
        default:
          cutoff = new Date(0)
      }
      curve = curve.filter((pt) => pt.timestamp && new Date(pt.timestamp) >= cutoff)
    }

    return NextResponse.json({ starting_capital: startingCapital, curve, period })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
