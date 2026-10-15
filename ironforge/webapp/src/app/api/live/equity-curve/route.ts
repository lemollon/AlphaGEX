import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, escapeSql, dteMode } from '@/lib/db'
import { resolveLiveViewer, scopeFilter, resolveAccountMode } from '@/lib/live/viewer'
import { scopedStartingCapital } from '@/lib/account-basis'
import {
  canReadProductionBalance,
  getLiveEquityForBot,
  getIcMarkToMarket,
  calculateIcUnrealizedPnl,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

type Period = 'week' | 'month' | 'year' | 'all'
const PERIODS: Period[] = ['week', 'month', 'year', 'all']

/**
 * Day-granularity equity history for the Live page's period toggle
 * (Week/Month/Year/All-time — Today stays on /api/live/summary's own
 * 5-min `equity_snapshots` series). Same query shape as the operator
 * dashboard's `/api/[bot]/equity-curve` route — one point per closed trade,
 * cumulative realized P&L rebased onto the live balance — just re-scoped the
 * way `summary.ts`'s intraday query is scoped: customer-owned account only,
 * never an unscoped fleet total handed to a non-operator.
 */
export async function GET(req: NextRequest) {
  try {
    const viewer = await resolveLiveViewer(req)
    if (!viewer.bot) {
      return NextResponse.json({ empty: true, points: [], period_pnl: null, period_pnl_pct: null })
    }
    const bot = viewer.bot

    const periodParam = req.nextUrl.searchParams.get('period')
    const period: Period = PERIODS.includes(periodParam as Period) ? (periodParam as Period) : 'month'

    const dte = dteMode(bot)
    const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
    const prodFilter = scopeFilter(bot, viewer.person, viewer.isOperator)

    const [basis, curveRows, openPositions] = await Promise.all([
      scopedStartingCapital(bot, `${dteFilter} ${prodFilter}`),
      dbQuery(
        `SELECT close_time, realized_pnl,
                SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl
         FROM ${botTable(bot, 'positions')}
         WHERE status IN ('closed', 'expired')
           AND realized_pnl IS NOT NULL
           AND close_time IS NOT NULL
           ${dteFilter} ${prodFilter}
         ORDER BY close_time`,
      ),
      dbQuery(
        `SELECT position_id, ticker, expiration,
                put_short_strike, put_long_strike,
                call_short_strike, call_long_strike,
                contracts, total_credit, spread_width
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' ${dteFilter} ${prodFilter}`,
      ),
    ])

    let startingCapital = basis.startingCapital
    let curve = curveRows.map((row) => {
      const cumPnl = num(row.cumulative_pnl)
      return {
        timestamp: row.close_time ? String(row.close_time) : null,
        cumulative_pnl: cumPnl,
        equity: Math.round((startingCapital + cumPnl) * 100) / 100,
      }
    })

    // Live unrealized P&L from open positions — same per-position MTM calc the
    // operator route uses (Spark/Flame never carry the blaze-style vertical legs).
    let liveUnrealizedPnl = 0
    if (openPositions.length > 0 && isConfigured()) {
      const mtmResults = await Promise.all(
        openPositions.map(async (pos) => {
          try {
            const contracts = Number(pos.contracts) || 0
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
            const spreadWidth = num(pos.spread_width) || (num(pos.put_short_strike) - num(pos.put_long_strike))
            return calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close, contracts, spreadWidth)
          } catch {
            return 0
          }
        }),
      )
      liveUnrealizedPnl = mtmResults.reduce((a, b) => a + b, 0)
    }

    // Rebase onto the live Tradier balance when this account's own ledger is
    // the production one — same idea as the operator route's SPARK/FLAME
    // rebase, via the bot-agnostic helper that resolves either credentialing
    // path (table-backed or env-backed).
    let rebaseSource: 'tradier' | 'paper_account' = 'paper_account'
    if (canReadProductionBalance(bot) && resolveAccountMode(bot) === 'production') {
      try {
        const eqLive = await getLiveEquityForBot(bot)
        if (eqLive != null) {
          const lastCumPnl = curve.length > 0 ? curve[curve.length - 1].cumulative_pnl : 0
          const rebaseStart = Math.round((eqLive - lastCumPnl - liveUnrealizedPnl) * 100) / 100
          const offset = rebaseStart - startingCapital
          if (offset !== 0) {
            curve = curve.map((pt) => ({ ...pt, equity: Math.round((pt.equity + offset) * 100) / 100 }))
          }
          startingCapital = rebaseStart
          rebaseSource = 'tradier'
        }
      } catch {
        // fall back to the paper basis
      }
    }

    if (openPositions.length > 0) {
      const last = curve.length > 0 ? curve[curve.length - 1] : null
      const lastCumPnl = last ? last.cumulative_pnl : 0
      const liveCumPnl = Math.round((lastCumPnl + liveUnrealizedPnl) * 100) / 100
      curve.push({
        timestamp: new Date().toISOString(),
        cumulative_pnl: liveCumPnl,
        equity: Math.round((startingCapital + liveCumPnl) * 100) / 100,
      })
    }

    if (period !== 'all' && curve.length > 0) {
      const now = Date.now()
      const cutoffMs = period === 'week' ? 7 * 86_400_000 : period === 'month' ? 30 * 86_400_000 : 365 * 86_400_000
      const cutoff = new Date(now - cutoffMs)
      curve = curve.filter((pt) => pt.timestamp && new Date(pt.timestamp) >= cutoff)
    }

    // Header figure for this period: start-of-period equity to now — never
    // "Today's Result", which stays scoped to the Today view only.
    const periodOpenEquity = curve.length > 0 ? curve[0].equity : null
    const periodPnl = curve.length > 0 && periodOpenEquity != null
      ? Math.round((curve[curve.length - 1].equity - periodOpenEquity) * 100) / 100
      : null
    const periodPnlPct = periodPnl != null && periodOpenEquity
      ? Math.round((periodPnl / periodOpenEquity) * 10000) / 100
      : null

    return NextResponse.json({
      period,
      points: curve.map((pt) => ({ timestamp: pt.timestamp, equity: pt.equity })),
      period_pnl: periodPnl,
      period_pnl_pct: periodPnlPct,
      rebase_source: rebaseSource,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
