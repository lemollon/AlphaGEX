import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl, getLoadedSandboxAccountsAsync, getAccountIdForKey, getTradierBalanceDetail } from '@/lib/tradier'
import { isMarketOpen } from '@/lib/pt-tiers'

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
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const personFilter = filterByPerson ? `AND person = '${escapeSql(personParam)}'` : ''
  const accountTypeParam = req.nextUrl.searchParams.get('account_type')
  const accountTypeFilter = accountTypeParam
    ? `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountTypeParam)}'`
    : ''

  try {
    const [capitalRows, snapshotRows, openPositions] = await Promise.all([
      dbQuery(
        `SELECT starting_capital
         FROM ${botTable(bot, 'paper_account')}
         WHERE is_active = TRUE ${dteFilter} ${accountTypeFilter}
         LIMIT 1`,
      ),
      dbQuery(
        `SELECT snapshot_time, balance, realized_pnl, unrealized_pnl,
               open_positions, note
         FROM ${botTable(bot, 'equity_snapshots')}
         WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
           ${dteFilter} ${personFilter} ${accountTypeFilter}
         ORDER BY snapshot_time ASC`,
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

    let startingCapital = num(capitalRows[0]?.starting_capital) || 10000

    // FLAME intraday rebase: scanner writes snapshot.balance against the
    // paper_account $10K basis, but the /flame top card shows the live
    // Tradier User sandbox balance. Rebase the curve so the Y-axis matches
    // the top card — otherwise the chart says "Balance: $9,800" while the
    // Balance card says "$68,447". Same P&L shape, Tradier basis.
    //
    // today_starting_basis = Tradier total_equity − Tradier close_pl − Tradier open_pl
    //   (= Tradier balance at start of today)
    // rebased_balance      = snapshot.balance + (today_starting_basis − paper_starting_capital)
    // rebased_equity       = rebased_balance + snapshot.unrealized_pnl
    //
    // On Tradier failure: keep scanner's paper-basis balance (same as before).
    let rebaseOffset = 0
    let rebaseSource: 'tradier' | 'paper_account' = 'paper_account'
    if (bot === 'flame') {
      try {
        const accts = await getLoadedSandboxAccountsAsync()
        const userAcct = accts.find((a) => a.name === 'User' && a.type === 'sandbox')
        if (userAcct) {
          const accountId = await getAccountIdForKey(userAcct.apiKey, userAcct.baseUrl)
          if (accountId) {
            const bal = await getTradierBalanceDetail(userAcct.apiKey, accountId, userAcct.baseUrl)
            if (bal && bal.total_equity != null) {
              const tradierEquity = bal.total_equity
              const tradierClosePl = bal.close_pl ?? 0
              const tradierOpenPl = bal.open_pl ?? 0
              const todayStartingBasis = Math.round((tradierEquity - tradierClosePl - tradierOpenPl) * 100) / 100
              rebaseOffset = Math.round((todayStartingBasis - startingCapital) * 100) / 100
              startingCapital = todayStartingBasis
              rebaseSource = 'tradier'
            }
          }
        }
      } catch { /* fall back to paper basis */ }
    }

    const snapshots = snapshotRows.map((r) => {
      const rawBalance = num(r.balance)
      const rebasedBalance = Math.round((rawBalance + rebaseOffset) * 100) / 100
      const unrealized = num(r.unrealized_pnl)
      return {
        timestamp: r.snapshot_time || null,
        balance: rebasedBalance,
        realized_pnl: num(r.realized_pnl),
        unrealized_pnl: unrealized,
        equity: Math.round((rebasedBalance + unrealized) * 100) / 100,
        open_positions: int(r.open_positions),
        note: r.note,
      }
    })

    // Compute live unrealized P&L from open positions via Tradier
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

    // Append a live snapshot with current unrealized P&L — ONLY while market is open.
    // After 3:00 PM CT (or weekends), don't extend the chart with a synthetic 'now' point;
    // the curve should end at the last real scanner snapshot.
    const marketIsOpen = isMarketOpen()
    if (marketIsOpen && snapshots.length > 0) {
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
    } else if (marketIsOpen && openPositions.length > 0) {
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
      // FLAME-only: tells the operator whether the curve is rebased to
      // Tradier or still on the $10K paper basis (fallback).
      rebase_source: rebaseSource,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
