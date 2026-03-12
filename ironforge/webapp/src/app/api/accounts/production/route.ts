import { NextResponse } from 'next/server'
import {
  getSandboxAccountBalances,
  getLoadedSandboxAccounts,
  getSandboxPositionSymbols,
} from '@/lib/tradier'
import { dbQuery, botTable, num, escapeSql, dteMode, CT_TODAY } from '@/lib/databricks-sql'

export const dynamic = 'force-dynamic'

const BOTS = ['flame', 'spark', 'inferno'] as const

/**
 * GET /api/accounts/production
 *
 * Returns sandbox (production-mirror) account balances with per-bot position attribution.
 * Cross-references Tradier open position OCC symbols against each bot's positions table
 * to determine which bot owns each position.
 */
export async function GET() {
  try {
    const balances = await getSandboxAccountBalances()
    const sandboxAccounts = getLoadedSandboxAccounts()

    const accounts = await Promise.all(
      balances.map(async (acct) => {
        const acctConfig = sandboxAccounts.find((a) => a.name === acct.name)

        let tradierSymbols: string[] = []
        if (acctConfig?.apiKey) {
          tradierSymbols = await getSandboxPositionSymbols(acctConfig.apiKey)
        }

        // Cross-reference: for each bot, check which Tradier symbols match
        const botBreakdown = await Promise.all(
          BOTS.map(async (bot) => {
            const dte = dteMode(bot)
            const tbl = botTable(bot, 'positions')
            const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

            const openRows = await dbQuery(
              `SELECT put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                     expiration, ticker
              FROM ${tbl}
              WHERE status = 'open' ${dteFilter}`,
            )

            const botOccSymbols = new Set<string>()
            for (const row of openRows) {
              const exp = new Date(row.expiration + 'T12:00:00')
              const yy = String(exp.getFullYear()).slice(2)
              const mm = String(exp.getMonth() + 1).padStart(2, '0')
              const dd = String(exp.getDate()).padStart(2, '0')
              const dateStr = `${yy}${mm}${dd}`
              const ticker = row.ticker || 'SPY'

              for (const [strike, type] of [
                [row.put_short_strike, 'P'],
                [row.put_long_strike, 'P'],
                [row.call_short_strike, 'C'],
                [row.call_long_strike, 'C'],
              ] as const) {
                const s = String(Math.round(parseFloat(String(strike)) * 1000)).padStart(8, '0')
                botOccSymbols.add(`${ticker}${dateStr}${type}${s}`)
              }
            }

            const matchingPositions = tradierSymbols.filter((sym) => botOccSymbols.has(sym))
            const openPositions = matchingPositions.length > 0
              ? Math.ceil(matchingPositions.length / 4)
              : 0

            // Today's realized P&L
            const todayPnlRows = await dbQuery(
              `SELECT COALESCE(SUM(realized_pnl), 0) as pnl
              FROM ${tbl}
              WHERE status IN ('closed', 'expired')
                AND CAST(CONVERT_TIMEZONE('UTC', 'America/Chicago', close_time) AS DATE) = ${CT_TODAY}
                ${dteFilter}`,
            )
            const dayPnl = num(todayPnlRows[0]?.pnl)

            return {
              bot: bot.toUpperCase(),
              open_positions: openPositions,
              day_pnl: Math.round(dayPnl * 100) / 100,
            }
          }),
        )

        // Find unattributed positions
        const allBotSymbols = new Set<string>()
        for (const bot of BOTS) {
          const dte = dteMode(bot)
          const tbl = botTable(bot, 'positions')
          const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

          const openRows = await dbQuery(
            `SELECT put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   expiration, ticker
            FROM ${tbl}
            WHERE status = 'open' ${dteFilter}`,
          )

          for (const row of openRows) {
            const exp = new Date(row.expiration + 'T12:00:00')
            const yy = String(exp.getFullYear()).slice(2)
            const mm = String(exp.getMonth() + 1).padStart(2, '0')
            const dd = String(exp.getDate()).padStart(2, '0')
            const dateStr = `${yy}${mm}${dd}`
            const ticker = row.ticker || 'SPY'

            for (const [strike, type] of [
              [row.put_short_strike, 'P'],
              [row.put_long_strike, 'P'],
              [row.call_short_strike, 'C'],
              [row.call_long_strike, 'C'],
            ] as const) {
              const s = String(Math.round(parseFloat(String(strike)) * 1000)).padStart(8, '0')
              allBotSymbols.add(`${ticker}${dateStr}${type}${s}`)
            }
          }
        }

        const unattributedSymbols = tradierSymbols.filter((sym) => !allBotSymbols.has(sym))
        const unattributedCount = unattributedSymbols.length > 0
          ? Math.ceil(unattributedSymbols.length / 4)
          : 0

        const bots = [...botBreakdown]
        if (unattributedCount > 0) {
          bots.push({
            bot: 'UNATTRIBUTED',
            open_positions: unattributedCount,
            day_pnl: 0,
          })
        }

        return {
          account_id: acct.account_id,
          name: acct.name,
          balance: acct.total_equity,
          day_pnl: acct.day_pnl,
          open_positions: acct.open_positions_count,
          bots,
        }
      }),
    )

    return NextResponse.json(accounts)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
