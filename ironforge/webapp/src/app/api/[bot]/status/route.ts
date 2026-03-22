import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, sharedTable, num, int, escapeSql, validateBot, heartbeatName, dteMode, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl, getSandboxAccountBalances } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const personParam = req.nextUrl.searchParams.get('person')
  const filterByPerson = personParam && personParam !== 'all'

  try {
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const personFilter = filterByPerson ? `AND person = '${escapeSql(personParam)}'` : ''

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
       WHERE status = 'open' ${dteFilter} ${personFilter}`,
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
         ${dteFilter} ${personFilter}`,
    )

    // Today's realized P&L (trades closed today in CT)
    const todayRealizedQuery = dbQuery(
      `SELECT
        COALESCE(SUM(realized_pnl), 0) as today_realized_pnl,
        COUNT(*) as today_trades_closed
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${personFilter}`,
    )

    // Today's close reason breakdown (which PT tiers hit, with IC return data)
    const todayCloseReasonsQuery = dbQuery(
      `SELECT close_reason, realized_pnl, total_credit, contracts, close_price
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired')
         AND realized_pnl IS NOT NULL
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
         ${dteFilter} ${personFilter}
       ORDER BY close_time ASC`,
    )

    // Actual collateral from open positions (not stale paper_account value)
    const liveCollateralQuery = dbQuery(
      `SELECT COALESCE(SUM(collateral_required), 0) as actual_collateral
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${personFilter}`,
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
       WHERE status = 'open' ${dteFilter} ${personFilter}`,
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

    // Account balances — fetch real Tradier data for all bots (sandbox + production)
    const sandboxBalancesQuery = getSandboxAccountBalances().catch(() => [])

    const [accountRows, positionCountRows, heartbeatRows, snapshotRows, scansTodayRows, lastErrorRows, openPositionRows, liveStatsRows, liveCollateralRows, pendingCountRows, todayRealizedRows, sandboxBalances, todayCloseReasonRows] =
      await Promise.all([accountQuery, positionCountQuery, heartbeatQuery, snapshotQuery, scansTodayQuery, lastErrorQuery, openPositionsQuery, liveStatsQuery, liveCollateralQuery, pendingCountQuery, todayRealizedQuery, sandboxBalancesQuery, todayCloseReasonsQuery])

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
            // Use last trade prices — matches Tradier portfolio Gain/Loss calculation
            return calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close_last, contracts, spreadWidth)
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

    const todayRealizedPnl = Math.round(num(todayRealizedRows[0]?.today_realized_pnl) * 100) / 100
    const todayTradesClosed = int(todayRealizedRows[0]?.today_trades_closed)

    // Weighted IC return %: average of (credit - close_price) / credit
    // Weight by credit × contracts (larger positions count more)
    let totalWeight = 0
    let weightedReturnSum = 0
    for (const r of todayCloseReasonRows) {
      const credit = num(r.total_credit)
      const closePrice = num(r.close_price)
      const contracts = int(r.contracts) || 1
      if (credit > 0) {
        const weight = credit * contracts
        const icReturn = (credit - closePrice) / credit
        weightedReturnSum += icReturn * weight
        totalWeight += weight
      }
    }
    const todayIcReturnPct = totalWeight > 0
      ? Math.round((weightedReturnSum / totalWeight) * 10000) / 100
      : null

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
        today_realized_pnl: todayRealizedPnl,
        today_trades_closed: todayTradesClosed,
        today_ic_return_pct: todayIcReturnPct,
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
      today_close_reasons: todayCloseReasonRows.map((r) => {
        const pnl = Math.round(num(r.realized_pnl) * 100) / 100
        const credit = num(r.total_credit)
        const closePrice = num(r.close_price)
        // IC return %: how much of the credit premium was kept
        // Formula: (credit_received - close_price) / credit_received × 100
        // This is the TRUE IC win % — matches the PT tier targets (30%, 20%, 15%)
        const icReturnPct = credit > 0
          ? Math.round(((credit - closePrice) / credit) * 10000) / 100
          : 0
        return {
          close_reason: r.close_reason || '',
          realized_pnl: pnl,
          ic_return_pct: icReturnPct,
        }
      }),
      sandbox_accounts: sandboxBalances.map((s) => ({
        name: s.name,
        account_id: s.account_id,
        total_equity: s.total_equity,
        option_buying_power: s.option_buying_power,
        day_pnl: s.day_pnl,
        unrealized_pnl: s.unrealized_pnl,
        unrealized_pnl_pct: s.unrealized_pnl_pct,
        open_positions: s.open_positions_count,
      })),
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
