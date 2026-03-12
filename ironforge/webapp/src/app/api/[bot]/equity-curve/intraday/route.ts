import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  try {
    const capitalQuery = dbQuery(
      `SELECT starting_capital
       FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter}
       LIMIT 1`,
    )

    const snapshotQuery = dbQuery(
      `SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
             open_positions, note
       FROM ${botTable(bot, 'equity_snapshots')}
       WHERE CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', snapshot_time) AS DATE) = ${CT_TODAY}
         ${dteFilter}
       ORDER BY snapshot_time ASC`,
    )

    const [capitalRows, snapshotRows] = await Promise.all([capitalQuery, snapshotQuery])

    const startingCapital = num(capitalRows[0]?.starting_capital) || 10000

    const snapshots = snapshotRows.map((r) => ({
      timestamp: r.snapshot_time || null,
      balance: num(r.balance),
      realized_pnl: num(r.realized_pnl),
      unrealized_pnl: num(r.unrealized_pnl),
      equity: num(r.balance) + num(r.unrealized_pnl),
      open_positions: int(r.open_positions),
      note: r.note,
    }))

    return NextResponse.json({ starting_capital: startingCapital, snapshots })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
