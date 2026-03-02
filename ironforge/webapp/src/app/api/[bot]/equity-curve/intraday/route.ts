import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot, dteMode } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)

  try {
    const capitalQuery = dte
      ? query(`
          SELECT starting_capital
          FROM ${botTable(bot, 'paper_account')}
          WHERE is_active = TRUE AND dte_mode = $1
          LIMIT 1
        `, [dte])
      : query(`
          SELECT starting_capital
          FROM ${botTable(bot, 'paper_account')}
          WHERE is_active = TRUE
          LIMIT 1
        `)

    const snapshotQuery = dte
      ? query(`
          SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
                 open_positions, note
          FROM ${botTable(bot, 'equity_snapshots')}
          WHERE dte_mode = $1
            AND snapshot_time::date = CURRENT_DATE
          ORDER BY snapshot_time ASC
        `, [dte])
      : query(`
          SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
                 open_positions, note
          FROM ${botTable(bot, 'equity_snapshots')}
          WHERE snapshot_time::date = CURRENT_DATE
          ORDER BY snapshot_time ASC
        `)

    const [capitalRows, snapshotRows] = await Promise.all([capitalQuery, snapshotQuery])

    const startingCapital = num(capitalRows[0]?.starting_capital) || 10000

    const snapshots = snapshotRows.map((r) => ({
      timestamp: r.snapshot_time?.toISOString?.() || r.snapshot_time,
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
