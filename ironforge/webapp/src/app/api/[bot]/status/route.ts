import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot } from '@/lib/db'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = bot === 'flame' ? '2DTE' : '1DTE'

  try {
    const [accountRows, positionCountRows, heartbeatRows, snapshotRows] =
      await Promise.all([
        query(`
          SELECT starting_capital, current_balance, cumulative_pnl,
                 total_trades, collateral_in_use, buying_power,
                 high_water_mark, max_drawdown, is_active
          FROM ${botTable(bot, 'paper_account')}
          WHERE is_active = TRUE AND dte_mode = $1
          ORDER BY id DESC LIMIT 1
        `, [dte]),
        query(`
          SELECT COUNT(*) as cnt
          FROM ${botTable(bot, 'positions')}
          WHERE status = 'open' AND dte_mode = $1
        `, [dte]),
        query(`
          SELECT scan_count, last_heartbeat, status
          FROM bot_heartbeats
          WHERE bot_name = $1
        `, [bot.toUpperCase()]),
        query(`
          SELECT unrealized_pnl, open_positions, snapshot_time
          FROM ${botTable(bot, 'equity_snapshots')}
          WHERE dte_mode = $1
          ORDER BY snapshot_time DESC
          LIMIT 1
        `, [dte]),
      ])

    const acct = accountRows[0]
    const balance = num(acct?.current_balance)
    const startingCapital = num(acct?.starting_capital)
    const realizedPnl = num(acct?.cumulative_pnl)
    const unrealizedPnl = num(snapshotRows[0]?.unrealized_pnl)
    const totalPnl = realizedPnl + unrealizedPnl
    const returnPct = startingCapital > 0 ? (totalPnl / startingCapital) * 100 : 0

    const hb = heartbeatRows[0]

    return NextResponse.json({
      bot_name: bot.toUpperCase(),
      strategy: bot === 'flame' ? '2DTE Paper Iron Condor' : '1DTE Paper Iron Condor',
      dte: bot === 'flame' ? 2 : 1,
      ticker: 'SPY',
      is_active: acct?.is_active === true,
      account: {
        starting_capital: startingCapital,
        balance,
        cumulative_pnl: realizedPnl,
        unrealized_pnl: unrealizedPnl,
        total_pnl: Math.round(totalPnl * 100) / 100,
        return_pct: Math.round(returnPct * 100) / 100,
        total_trades: int(acct?.total_trades),
        collateral_in_use: num(acct?.collateral_in_use),
        buying_power: num(acct?.buying_power),
        high_water_mark: num(acct?.high_water_mark),
        max_drawdown: num(acct?.max_drawdown),
      },
      open_positions: int(positionCountRows[0]?.cnt),
      last_scan: hb?.last_heartbeat?.toISOString?.() || hb?.last_heartbeat || null,
      last_snapshot: snapshotRows[0]?.snapshot_time?.toISOString?.() || snapshotRows[0]?.snapshot_time || null,
      scan_count: int(hb?.scan_count),
    })
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
