import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, t, num, int, validateBot, dteMode, heartbeatName } from '@/lib/databricks'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const botName = heartbeatName(bot)

  try {
    const [accountRows, positionCountRows, positionCollateralRows, heartbeatRows, snapshotRows, scansTodayRows, lastErrorRows] =
      await Promise.all([
        query(`
          SELECT starting_capital, current_balance, cumulative_pnl,
                 total_trades, collateral_in_use, buying_power,
                 high_water_mark, max_drawdown, is_active
          FROM ${botTable(bot, 'paper_account')}
          WHERE is_active = TRUE AND dte_mode = '${dte}'
          ORDER BY id DESC LIMIT 1
        `),
        query(`
          SELECT COUNT(*) as cnt
          FROM ${botTable(bot, 'positions')}
          WHERE status = 'open' AND dte_mode = '${dte}'
        `),
        query(`
          SELECT COALESCE(SUM(collateral_required), 0) as total_collateral
          FROM ${botTable(bot, 'positions')}
          WHERE status = 'open' AND dte_mode = '${dte}'
        `),
        query(`
          SELECT scan_count, last_heartbeat, status, details
          FROM ${t('bot_heartbeats')}
          WHERE bot_name = '${botName}'
        `),
        query(`
          SELECT unrealized_pnl, open_positions, snapshot_time
          FROM ${botTable(bot, 'equity_snapshots')}
          WHERE dte_mode = '${dte}'
          ORDER BY snapshot_time DESC
          LIMIT 1
        `),
        query(`
          SELECT COUNT(*) as cnt
          FROM ${botTable(bot, 'logs')}
          WHERE level = 'SCAN'
            AND CAST(log_time AS DATE) = CURRENT_DATE()
            AND dte_mode = '${dte}'
        `),
        query(`
          SELECT log_time, message
          FROM ${botTable(bot, 'logs')}
          WHERE level = 'ERROR' AND dte_mode = '${dte}'
          ORDER BY log_time DESC LIMIT 1
        `),
      ])

    const acct = accountRows[0]
    const balance = num(acct?.current_balance)
    const startingCapital = num(acct?.starting_capital)
    const realizedPnl = num(acct?.cumulative_pnl)
    const unrealizedPnl = num(snapshotRows[0]?.unrealized_pnl)
    const totalPnl = realizedPnl + unrealizedPnl
    const returnPct = startingCapital > 0 ? (totalPnl / startingCapital) * 100 : 0

    const hb = heartbeatRows[0]
    const lastErr = lastErrorRows[0]

    // Parse heartbeat details JSON for SPY/VIX and bot state
    let hbDetails: Record<string, any> = {}
    if (hb?.details) {
      try { hbDetails = JSON.parse(hb.details) } catch {}
    }

    // Derive bot_state from heartbeat status + action
    const hbStatus = hb?.status || 'unknown'
    const hbAction = hbDetails.action || ''
    const botState =
      hbStatus === 'error' ? 'error'
      : hbAction === 'monitoring' ? 'monitoring'
      : hbAction === 'traded' || hbAction === 'closed' ? 'traded'
      : hbAction === 'outside_window' || hbAction === 'outside_entry_window' ? 'market_closed'
      : hbStatus === 'idle' ? 'idle'
      : hbStatus === 'active' ? 'scanning'
      : 'unknown'

    return NextResponse.json({
      bot_name: botName,
      strategy: bot === 'flame' ? '2DTE Paper Iron Condor' : '1DTE Paper Iron Condor',
      dte: bot === 'flame' ? 2 : 1,
      ticker: 'SPY',
      is_active: acct?.is_active === 'true' || acct?.is_active === '1',
      account: {
        starting_capital: startingCapital,
        balance,
        cumulative_pnl: realizedPnl,
        unrealized_pnl: unrealizedPnl,
        total_pnl: Math.round(totalPnl * 100) / 100,
        return_pct: Math.round(returnPct * 100) / 100,
        total_trades: int(acct?.total_trades),
        collateral_in_use: num(acct?.collateral_in_use) || num(positionCollateralRows[0]?.total_collateral),
        buying_power: num(acct?.buying_power),
        high_water_mark: num(acct?.high_water_mark),
        max_drawdown: num(acct?.max_drawdown),
      },
      open_positions: int(positionCountRows[0]?.cnt),
      last_scan: hb?.last_heartbeat || null,
      last_snapshot: snapshotRows[0]?.snapshot_time || null,
      scan_count: int(hb?.scan_count),
      scans_today: int(scansTodayRows[0]?.cnt),
      spot_price: hbDetails.spot ? parseFloat(hbDetails.spot) : null,
      vix: hbDetails.vix ? parseFloat(hbDetails.vix) : null,
      bot_state: botState,
      last_error: lastErr ? {
        time: lastErr.log_time || null,
        message: lastErr.message || null,
      } : null,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
