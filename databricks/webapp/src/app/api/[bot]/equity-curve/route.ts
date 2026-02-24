import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, validateBot } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'
  const period = req.nextUrl.searchParams.get('period') || 'all'

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

    // Build full curve with correct cumulative P&L
    let curve = curveRows.map((row) => {
      const cumPnl = num(row.cumulative_pnl)
      return {
        timestamp: row.close_time,
        pnl: num(row.realized_pnl),
        cumulative_pnl: cumPnl,
        equity: Math.round((startingCapital + cumPnl) * 100) / 100,
      }
    })

    // Apply period filter client-side so cumulative P&L stays correct
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
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
