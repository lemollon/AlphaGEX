import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, sharedTable, num, int, escapeSql, validateBot, heartbeatName, dteMode, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)

  try {
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

    const accountQuery = dbQuery(
      `SELECT starting_capital, current_balance, cumulative_pnl,
              total_trades, collateral_in_use, buying_power,
              high_water_mark, max_drawdown, is_active
       FROM ${botTable(bot, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter}
       ORDER BY id DESC LIMIT 1`,
    )

    const positionCountQuery = dbQuery(
      `SELECT COUNT(*) as cnt
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}`,
    )

    // Live reconciliation: compute realized P&L and trade count from actual closed positions
    // This is the source of truth — paper_account can drift out of sync
    const liveStatsQuery = dbQuery(
      `SELECT
        COALESCE(SUM(realized_pnl), 0) as actual_realized_pnl,
        COUNT(*) as actual_total_trades
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         ${dteFilter}`,
    )

    // Actual collateral from open positions (not stale paper_account value)
    const liveCollateralQuery = dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) as actual_collateral
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}`,
    )

    const hbName = heartbeatName(bot)
    const heartbeatQuery = dbQuery(
      `SELECT scan_count, last_heartbeat, status, details
       FROM ${sharedTable('bot_heartbeats')}
       WHERE bot_name = '${escapeSql(hbName)}'`,
    )

    const snapshotQuery = dbQuery(
      `SELECT unrealized_pnl, open_positions, snapshot_time
       FROM ${botTable(bot, 'equity_snapshots')}
       ${dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''}
       ORDER BY snapshot_time DESC
       LIMIT 1`,
    )

    const scansTodayQuery = dbQuery(
      `SELECT COUNT(*) as cnt
       FROM ${botTable(bot, 'logs')}
       WHERE level = 'SCAN'
         AND (log_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter}`,
    )

    const lastErrorQuery = dbQuery(
      `SELECT log_time, message
       FROM ${botTable(bot, 'logs')}
       WHERE level = 'ERROR' ${dteFilter}
       ORDER BY log_time DESC LIMIT 1`,
    )

    const openPositionsQuery = dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, spread_width
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}`,
    )

    // Pending order count (FLAME only — graceful fallback if table doesn't exist)
    const pendingCountQuery = bot === 'flame'
      ? dbQuery(
          `SELECT COUNT(*) as cnt
           FROM ${botTable(bot, 'pending_orders')}
           WHERE status = 'pending'
             AND created_date = ${CT_TODAY}
             ${dteFilter}`,
        ).catch(() => [{ cnt: 0 }])
      : Promise.resolve([{ cnt: 0 }])

    const [accountRows, positionCountRows, heartbeatRows, snapshotRows, scansTodayRows, lastErrorRows, openPositionRows, liveStatsRows, liveCollateralRows, pendingCountRows] =
      await Promise.all([accountQuery, positionCountQuery, heartbeatQuery, snapshotQuery, scansTodayQuery, lastErrorQuery, openPositionsQuery, liveStatsQuery, liveCollateralQuery, pendingCountQuery])

    const acct = accountRows[0]
    const startingCapital = num(acct?.starting_capital) || 10000

    // Use LIVE stats from actual positions (source of truth), not stale paper_account
    const liveStats = liveStatsRows[0]
    const realizedPnl = Math.round(num(liveStats?.actual_realized_pnl) * 100) / 100
    const totalTrades = int(liveStats?.actual_total_trades)
    const liveCollateral = num(liveCollateralRows[0]?.actual_collateral)
    const balance = Math.round((startingCapital + realizedPnl) * 100) / 100
    const buyingPower = Math.round((balance - liveCollateral) * 100) / 100

    // Compute live unrealized P&L from open positions via Tradier
    let unrealizedPnl: number | null = null
    if (openPositionRows.length > 0 && isConfigured()) {
      let anyMtmSucceeded = false
      const mtmResults = await Promise.all(
        openPositionRows.map(async (pos) => {
          try {
            const entryCredit = num(pos.total_credit)
            const mtm = await getIcMarkToMarket(
              pos.ticker || 'SPY',
              pos.expiration?.toISOString?.()?.slice(0, 10) || String(pos.expiration).slice(0, 10),
              num(pos.put_short_strike),
              num(pos.put_long_strike),
              num(pos.call_short_strike),
              num(pos.call_long_strike),
              entryCredit,
            )
            if (!mtm) return null
            anyMtmSucceeded = true
            const contracts = int(pos.contracts)
            const spreadWidth = num(pos.spread_width) || (num(pos.put_short_strike) - num(pos.put_long_strike))
            return calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close, contracts, spreadWidth)
          } catch (err: unknown) {
            console.error(`[${bot}] MTM failed for position ${pos.position_id}:`, err instanceof Error ? err.message : err)
            return null
          }
        }),
      )
      if (anyMtmSucceeded) {
        unrealizedPnl = mtmResults.reduce((a: number, b) => a + (b ?? 0), 0)
      }
      // else: unrealizedPnl stays null — frontend should show "—"
    } else if (openPositionRows.length > 0) {
      // Tradier not configured but positions exist — unrealized PnL unavailable
      unrealizedPnl = null
    } else {
      unrealizedPnl = 0
    }

    const totalPnl = realizedPnl + (unrealizedPnl ?? 0)
    const returnPct = startingCapital > 0 ? (totalPnl / startingCapital) * 100 : 0

    const hb = heartbeatRows[0]
    const lastErr = lastErrorRows[0]

    // Parse heartbeat details JSON for SPY/VIX and bot state
    let hbDetails: { action?: string; reason?: string; spot?: number; vix?: number } = {}
    if (hb?.details) {
      try { hbDetails = typeof hb.details === 'string' ? JSON.parse(hb.details) : hb.details } catch {
        // Malformed JSON in heartbeat details — ignore
      }
    }

    const pendingOrderCount = int(pendingCountRows[0]?.cnt)

    // Derive bot_state from heartbeat status + action
    const hbStatus = hb?.status || 'unknown'
    const hbAction = hbDetails.action || ''
    const botState =
      hbStatus === 'error' ? 'error'
      : hbAction === 'pending_fill' ? 'pending_fill'
      : hbAction === 'awaiting_fill' ? 'awaiting_fill'
      : hbAction === 'monitoring' ? 'monitoring'
      : hbAction === 'traded' || hbAction === 'closed' ? 'traded'
      : hbAction === 'outside_window' || hbAction === 'outside_entry_window' ? 'market_closed'
      : hbStatus === 'idle' ? 'idle'
      : hbStatus === 'active' ? 'scanning'
      : 'unknown'

    const dteNum = bot === 'flame' ? 2 : bot === 'spark' ? 1 : 0
    const strategy = bot === 'flame' ? '2DTE Paper Iron Condor'
      : bot === 'spark' ? '1DTE Paper Iron Condor'
      : '0DTE Paper Iron Condor'

    return NextResponse.json({
      bot_name: bot.toUpperCase(),
      strategy,
      dte: dteNum,
      ticker: 'SPY',
      is_active: acct?.is_active === true || acct?.is_active === 'true',
      account: {
        starting_capital: startingCapital,
        balance,
        cumulative_pnl: realizedPnl,
        unrealized_pnl: unrealizedPnl,
        total_pnl: Math.round(totalPnl * 100) / 100,
        return_pct: Math.round(returnPct * 100) / 100,
        total_trades: totalTrades,
        collateral_in_use: liveCollateral,
        buying_power: buyingPower,
        high_water_mark: num(acct?.high_water_mark),
        max_drawdown: num(acct?.max_drawdown),
      },
      open_positions: int(positionCountRows[0]?.cnt),
      pending_order_count: pendingOrderCount,
      last_scan: hb?.last_heartbeat || null,
      last_snapshot: snapshotRows[0]?.snapshot_time || null,
      scan_count: int(hb?.scan_count),
      scans_today: int(scansTodayRows[0]?.cnt),
      spot_price: hbDetails.spot || null,
      vix: hbDetails.vix || null,
      bot_state: botState,
      last_scan_reason: hbDetails.reason || null,
      last_error: lastErr ? {
        time: lastErr.log_time || null,
        message: lastErr.message || null,
      } : null,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
