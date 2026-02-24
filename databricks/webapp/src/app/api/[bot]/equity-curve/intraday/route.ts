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
    const [capitalRows, snapshotRows] = await Promise.all([
      query(`
        SELECT starting_capital
        FROM ${botTable(bot, 'paper_account')}
        WHERE is_active = TRUE AND dte_mode = '${dte}'
        LIMIT 1
      `),
      query(`
        SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
               open_positions, note
        FROM ${botTable(bot, 'equity_snapshots')}
        WHERE dte_mode = '${dte}'
          AND CAST(snapshot_time AS DATE) = CURRENT_DATE()
        ORDER BY snapshot_time ASC
      `),
    ])

    const startingCapital = num(capitalRows[0]?.starting_capital) || 5000

    const snapshots = snapshotRows.map((r) => ({
      timestamp: r.snapshot_time,
      balance: num(r.balance),
      realized_pnl: num(r.realized_pnl),
      unrealized_pnl: num(r.unrealized_pnl),
      equity: num(r.balance) + num(r.unrealized_pnl),
      open_positions: int(r.open_positions),
      note: r.note,
    }))

    return NextResponse.json({ starting_capital: startingCapital, snapshots })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
