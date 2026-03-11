import { NextResponse } from 'next/server'
import {
  getSandboxAccountBalances,
  getLoadedSandboxAccounts,
  getSandboxPositionSymbols,
} from '@/lib/tradier'
import { query, botTable, dteMode, CT_TODAY } from '@/lib/db'

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
    // 1. Fetch all sandbox account balances from Tradier
    const balances = await getSandboxAccountBalances()
    const sandboxAccounts = getLoadedSandboxAccounts()

    // 2. For each account, get its open OCC symbols and cross-reference against bot tables
    const accounts = await Promise.all(
      balances.map(async (acct) => {
        // Find the API key for this account
        const acctConfig = sandboxAccounts.find((a) => a.name === acct.name)

        // Get this account's open position symbols from Tradier
        let tradierSymbols: string[] = []
        if (acctConfig?.apiKey) {
          tradierSymbols = await getSandboxPositionSymbols(acctConfig.apiKey)
        }

        // 3. Cross-reference: for each bot, check which of the Tradier symbols
        //    match open positions in that bot's positions table
        const botBreakdown = await Promise.all(
          BOTS.map(async (bot) => {
            const dte = dteMode(bot)
            const tbl = botTable(bot, 'positions')

            // Get all open position OCC symbols for this bot that have sandbox orders
            // The sandbox_order_id field tracks which positions were mirrored
            const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
            const openRows = await query<{
              put_short_strike: string
              put_long_strike: string
              call_short_strike: string
              call_long_strike: string
              expiration: string
              ticker: string
              realized_pnl: string | null
            }>(`
              SELECT put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                     expiration, ticker
              FROM ${tbl}
              WHERE status = 'open' ${dteFilter}
            `)

            // Build the OCC symbols for this bot's open positions
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
              ]) {
                const s = String(Math.round(parseFloat(strike as string) * 1000)).padStart(8, '0')
                botOccSymbols.add(`${ticker}${dateStr}${type}${s}`)
              }
            }

            // Count how many of this account's Tradier positions match this bot
            const matchingPositions = tradierSymbols.filter((sym) => botOccSymbols.has(sym))
            // Each IC has 4 legs, so divide by 4 for position count
            const openPositions = matchingPositions.length > 0
              ? Math.ceil(matchingPositions.length / 4)
              : 0

            // Get today's realized P&L for this bot (closed trades today)
            const todayPnlRows = await query<{ pnl: string }>(`
              SELECT COALESCE(SUM(realized_pnl), 0) as pnl
              FROM ${tbl}
              WHERE status IN ('closed', 'expired')
                AND (close_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
                ${dteFilter}
            `)
            const dayPnl = parseFloat(todayPnlRows[0]?.pnl || '0')

            return {
              bot: bot.toUpperCase(),
              open_positions: openPositions,
              day_pnl: Math.round(dayPnl * 100) / 100,
            }
          }),
        )

        // Count positions not attributed to any bot
        const attributedSymbols = new Set<string>()
        // Re-gather all bot symbols to find unattributed
        for (const bot of BOTS) {
          const dte = dteMode(bot)
          const tbl = botTable(bot, 'positions')
          const dteFilter = dte ? `AND dte_mode = '${dte}'` : ''
          const openRows = await query<{
            put_short_strike: string
            put_long_strike: string
            call_short_strike: string
            call_long_strike: string
            expiration: string
            ticker: string
          }>(`
            SELECT put_short_strike, put_long_strike, call_short_strike, call_long_strike,
                   expiration, ticker
            FROM ${tbl}
            WHERE status = 'open' ${dteFilter}
          `)
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
            ]) {
              const s = String(Math.round(parseFloat(strike as string) * 1000)).padStart(8, '0')
              attributedSymbols.add(`${ticker}${dateStr}${type}${s}`)
            }
          }
        }

        const unattributedSymbols = tradierSymbols.filter((sym) => !attributedSymbols.has(sym))
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
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 })
  }
}
