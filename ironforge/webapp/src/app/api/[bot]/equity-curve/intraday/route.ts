import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl } from '@/lib/tradier'

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
    const [capitalRows, snapshotRows, openPositions] = await Promise.all([
      dbQuery(
        `SELECT starting_capital
         FROM ${botTable(bot, 'paper_account')}
         WHERE is_active = TRUE ${dteFilter}
         LIMIT 1`,
      ),
      dbQuery(
        `SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
               open_positions, note
         FROM ${botTable(bot, 'equity_snapshots')}
         WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
           ${dteFilter}
         ORDER BY snapshot_time ASC`,
      ),
      dbQuery(
        `SELECT position_id, ticker, expiration,
                put_short_strike, put_long_strike,
                call_short_strike, call_long_strike,
                contracts, total_credit, spread_width
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' ${dteFilter}`,
      ),
    ])

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

    // Compute live unrealized P&L from open positions via Tradier
    let liveUnrealizedPnl = 0
    if (openPositions.length > 0 && isConfigured()) {
      const mtmResults = await Promise.all(
        openPositions.map(async (pos) => {
          try {
            const entryCredit = num(pos.total_credit)
            const mtm = await getIcMarkToMarket(
              pos.ticker || 'SPY',
              String(pos.expiration).slice(0, 10),
              num(pos.put_short_strike),
              num(pos.put_long_strike),
              num(pos.call_short_strike),
              num(pos.call_long_strike),
              entryCredit,
            )
            if (!mtm) return 0
            const contracts = int(pos.contracts)
            const spreadWidth = num(pos.spread_width) || (num(pos.put_short_strike) - num(pos.put_long_strike))
            return calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close, contracts, spreadWidth)
          } catch {
            return 0
          }
        }),
      )
      liveUnrealizedPnl = mtmResults.reduce((a, b) => a + b, 0)
    }

    // Append a live snapshot with current unrealized P&L
    if (snapshots.length > 0) {
      const latest = snapshots[snapshots.length - 1]
      snapshots.push({
        timestamp: new Date().toISOString(),
        balance: latest.balance,
        realized_pnl: latest.realized_pnl,
        unrealized_pnl: liveUnrealizedPnl,
        equity: latest.balance + liveUnrealizedPnl,
        open_positions: openPositions.length,
        note: 'live',
      })
    } else if (openPositions.length > 0) {
      // Morning edge case: no snapshots yet today but positions are open.
      // Create TWO synthetic snapshots so the chart draws a line, not a single dot.
      // First point = market open baseline, second point = current live state.
      const now = new Date()
      const marketOpenToday = new Date(now)
      marketOpenToday.setHours(now.getHours() - 1) // ~1h before current time as baseline
      // Clamp to 8:30 AM CT equivalent (approximate — just needs to be before "now")
      if (marketOpenToday.getTime() >= now.getTime()) {
        marketOpenToday.setTime(now.getTime() - 300_000) // 5 min before now as fallback
      }

      snapshots.push({
        timestamp: marketOpenToday.toISOString(),
        balance: startingCapital,
        realized_pnl: 0,
        unrealized_pnl: 0,
        equity: startingCapital,
        open_positions: openPositions.length,
        note: 'synthetic_open',
      })
      snapshots.push({
        timestamp: now.toISOString(),
        balance: startingCapital,
        realized_pnl: 0,
        unrealized_pnl: liveUnrealizedPnl,
        equity: startingCapital + liveUnrealizedPnl,
        open_positions: openPositions.length,
        note: 'live',
      })
    }

    return NextResponse.json({
      starting_capital: startingCapital,
      snapshots,
      live_unrealized_pnl: liveUnrealizedPnl,
      open_position_count: openPositions.length,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
