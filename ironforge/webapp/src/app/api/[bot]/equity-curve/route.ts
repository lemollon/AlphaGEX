import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const period = req.nextUrl.searchParams.get('period') || 'all'
  const personParam = req.nextUrl.searchParams.get('person')
  const filterByPerson = personParam && personParam !== 'all'
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const personFilter = filterByPerson ? `AND person = '${escapeSql(personParam)}'` : ''
  const accountTypeParam = req.nextUrl.searchParams.get('account_type')
  const accountTypeFilter = accountTypeParam
    ? `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountTypeParam)}'`
    : ''

  try {
    // SPARK-only: include the counterfactual cumulative P&L so the chart
    // can render a second line ("if we'd held to 2:59 PM every day").
    // For other bots the columns don't exist, so we omit them from SELECT
    // entirely to avoid querying a missing column.
    const hypoSelect = bot === 'spark'
      ? `, hypothetical_eod_pnl,
           SUM(COALESCE(hypothetical_eod_pnl, 0)) OVER (ORDER BY close_time) as cumulative_hypothetical_pnl`
      : ''

    const [capitalRows, curveRows, openPositions] = await Promise.all([
      dbQuery(
        `SELECT starting_capital
         FROM ${botTable(bot, 'paper_account')}
         WHERE is_active = TRUE ${dteFilter} ${accountTypeFilter}
         LIMIT 1`,
      ),
      dbQuery(
        `SELECT
          close_time,
          realized_pnl,
          SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl${hypoSelect}
        FROM ${botTable(bot, 'positions')}
        WHERE status IN ('closed', 'expired')
          AND realized_pnl IS NOT NULL
          AND close_time IS NOT NULL
          ${dteFilter} ${personFilter} ${accountTypeFilter}
        ORDER BY close_time`,
      ),
      dbQuery(
        `SELECT position_id, ticker, expiration,
                put_short_strike, put_long_strike,
                call_short_strike, call_long_strike,
                contracts, total_credit, spread_width
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' ${dteFilter} ${personFilter} ${accountTypeFilter}`,
      ),
    ])

    const startingCapital = num(capitalRows[0]?.starting_capital) || 10000

    let curve = curveRows.map((row) => {
      const cumPnl = num(row.cumulative_pnl)
      const point: {
        timestamp: string | null
        pnl: number
        cumulative_pnl: number
        equity: number
        hypothetical_pnl?: number | null
        cumulative_hypothetical_pnl?: number
        hypothetical_equity?: number
      } = {
        timestamp: row.close_time || null,
        pnl: num(row.realized_pnl),
        cumulative_pnl: cumPnl,
        equity: Math.round((startingCapital + cumPnl) * 100) / 100,
      }
      // SPARK-only: SPARK closed-trade rows carry counterfactual fields so
      // EquityChart can plot a second line. cumulative_hypothetical_pnl is
      // a running sum over rows where hypothetical_eod_pnl IS NOT NULL —
      // unmeasured rows contribute 0 so the line stays flat across gaps,
      // visually signaling "we don't have data here."
      if (bot === 'spark') {
        const cumHypo = num(row.cumulative_hypothetical_pnl)
        point.hypothetical_pnl = row.hypothetical_eod_pnl == null ? null : num(row.hypothetical_eod_pnl)
        point.cumulative_hypothetical_pnl = Math.round(cumHypo * 100) / 100
        point.hypothetical_equity = Math.round((startingCapital + cumHypo) * 100) / 100
      }
      return point
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

    // Append a live point with unrealized P&L from open positions so the
    // equity curve reflects the current state, not just closed trades.
    let liveUnrealizedPnl = 0
    if (openPositions.length > 0 && isConfigured()) {
      const mtmResults = await Promise.all(
        openPositions.map(async (pos) => {
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

    if (openPositions.length > 0) {
      const last = curve.length > 0 ? curve[curve.length - 1] : null
      const lastCumPnl = last ? last.cumulative_pnl : 0
      const liveCumPnl = lastCumPnl + liveUnrealizedPnl
      const livePoint: {
        timestamp: string
        pnl: number
        cumulative_pnl: number
        equity: number
        hypothetical_pnl?: number | null
        cumulative_hypothetical_pnl?: number
        hypothetical_equity?: number
      } = {
        timestamp: new Date().toISOString(),
        pnl: liveUnrealizedPnl,
        cumulative_pnl: Math.round(liveCumPnl * 100) / 100,
        equity: Math.round((startingCapital + liveCumPnl) * 100) / 100,
      }
      // SPARK live point carries the previous hypothetical cum forward
      // unchanged — open positions don't have a hypo number until they
      // close, so the line stays flat at its last known value.
      if (bot === 'spark' && last && last.cumulative_hypothetical_pnl != null) {
        livePoint.cumulative_hypothetical_pnl = last.cumulative_hypothetical_pnl
        livePoint.hypothetical_equity = Math.round((startingCapital + last.cumulative_hypothetical_pnl) * 100) / 100
        livePoint.hypothetical_pnl = null
      }
      curve.push(livePoint)
    }

    return NextResponse.json({
      starting_capital: startingCapital,
      curve,
      period,
      open_position_count: openPositions.length,
      live_unrealized_pnl: liveUnrealizedPnl,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
