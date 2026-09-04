import { dbQuery, botTable, num, int, escapeSql, dteMode, CT_TODAY } from '@/lib/db'

/**
 * Customer Home dashboard payload — wealth snapshot aggregates and a
 * customer-clean recent-trades list. Scoped per bot via the same ledgerFilter
 * summary.ts uses (production rows for SPARK, paper rows for FLAME), with
 * the same honest-data rules (null when unavailable, never fabricated).
 */

import { scopeFilter, type LiveBot } from './viewer'
import { weekStartET, monthStartET } from './period-windows'

export interface HomeData {
  wealth: {
    weekly_income: number | null
    monthly_income: number | null
    lifetime_income: number
    lifetime_return_pct: number | null
  }
  recent_trades: Array<{
    closed_at: string
    strategy: string
    contract: string
    premium: number
    status: string
  }>
  yesterday_trades: number
  as_of: string
}

export async function getHomeData(
  BOT: LiveBot = 'spark',
  person: string | null = null,
  isOperator = false,
): Promise<HomeData> {
  const dte = dteMode(BOT)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const prodFilter = scopeFilter(BOT, person, isOperator)
  const closedFilter = `status IN ('closed', 'expired') AND realized_pnl IS NOT NULL ${dteFilter} ${prodFilter}`

  // Calendar week/month, not a rolling 7/30-day window — "This Week" resets
  // Monday 00:00:00 ET and "This Month" resets the 1st, both in the exchange's
  // own timezone. See period-windows.ts for the boundary math (and why it's
  // computed in JS rather than `date_trunc(... AT TIME ZONE ...)`: it makes
  // the boundary unit-testable without a live Postgres connection).
  const now = new Date()
  const weekStart = weekStartET(now).toISOString()
  const monthStart = monthStartET(now).toISOString()

  const [incomeRows, accountRows, lifetimeRows, tradeRows, yesterdayRows] = await Promise.all([
    dbQuery(
      `SELECT
         COALESCE(SUM(realized_pnl) FILTER (WHERE close_time >= '${weekStart}'), 0) AS weekly,
         COALESCE(SUM(realized_pnl) FILTER (WHERE close_time >= '${monthStart}'), 0) AS monthly
       FROM ${botTable(BOT, 'positions')}
       WHERE ${closedFilter}`,
    ),
    dbQuery(
      `SELECT starting_capital
       FROM ${botTable(BOT, 'paper_account')}
       WHERE is_active = TRUE ${dteFilter} ${prodFilter}
       ORDER BY id DESC LIMIT 1`,
    ),
    dbQuery(
      `SELECT COALESCE(SUM(realized_pnl), 0) AS total
       FROM ${botTable(BOT, 'positions')}
       WHERE ${closedFilter}`,
    ),
    dbQuery(
      `SELECT close_time, ticker, expiration, contracts, total_credit
       FROM ${botTable(BOT, 'positions')}
       WHERE ${closedFilter}
       ORDER BY close_time DESC
       LIMIT 6`,
    ),
    dbQuery(
      `SELECT COUNT(*) AS cnt
       FROM ${botTable(BOT, 'positions')}
       WHERE ${closedFilter}
         AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY} - 1`,
    ),
  ])

  const startingCapital = num(accountRows[0]?.starting_capital)
  const lifetimeRealizedPnl = Math.round(num(lifetimeRows[0]?.total) * 100) / 100
  const lifetimeReturnPct =
    startingCapital > 0 ? Math.round((lifetimeRealizedPnl / startingCapital) * 10000) / 100 : null

  const dteLabel = dte ? `${dte.toUpperCase()}` : ''
  const recentTrades = tradeRows.map((r) => {
    const expiration =
      (r.expiration as Date)?.toISOString?.()?.slice(0, 10) ||
      (r.expiration ? String(r.expiration).slice(0, 10) : '')
    const expLabel = expiration
      ? `${Number(expiration.slice(5, 7))}/${Number(expiration.slice(8, 10))}`
      : ''
    return {
      closed_at: r.close_time ? new Date(r.close_time as string).toISOString() : '',
      strategy: `${r.ticker || 'SPY'} Iron Condor`,
      contract: [r.ticker || 'SPY', expLabel, dteLabel].filter(Boolean).join(' '),
      premium: Math.round(num(r.total_credit) * int(r.contracts) * 100 * 100) / 100,
      status: 'Filled',
    }
  })

  return {
    wealth: {
      weekly_income: Math.round(num(incomeRows[0]?.weekly) * 100) / 100,
      monthly_income: Math.round(num(incomeRows[0]?.monthly) * 100) / 100,
      lifetime_income: lifetimeRealizedPnl,
      lifetime_return_pct: lifetimeReturnPct,
    },
    recent_trades: recentTrades,
    yesterday_trades: int(yesterdayRows[0]?.cnt),
    as_of: new Date().toISOString(),
  }
}
