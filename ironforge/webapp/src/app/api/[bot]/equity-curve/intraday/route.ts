import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode, CT_TODAY } from '@/lib/db'
import { getIcMarkToMarket, isConfigured, calculateIcUnrealizedPnl, getLoadedSandboxAccountsAsync, getAccountIdForKey, getTradierBalanceDetail, getVerticalMarkToMarket, calculateVerticalUnrealizedPnl, getProductionAccountsForBot } from '@/lib/tradier'
import { isMarketOpen } from '@/lib/pt-tiers'
import { scopedStartingCapital } from '@/lib/account-basis'

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
    const [basis, snapshotRows, openPositions, ledgerRows] = await Promise.all([
      scopedStartingCapital(bot, `${dteFilter} ${accountTypeFilter}`),
      // Combine all in-scope account streams into ONE curve. Each
      // (person, account_type) writes its own snapshot row every ~1-min cycle a
      // few ms apart, so a raw ORDER BY snapshot_time interleaves them. Under
      // "All Accounts" SPARK's $19.5K production stream and $94K sandbox stream
      // alternated minute-by-minute, and the comparison chart — which rebases
      // the whole series to a single baseline (the first snapshot's equity) —
      // rendered every production point as a ~-80% plunge, producing the solid
      // blue "wall" down to the axis floor. Bucket to the minute, keep the last
      // snapshot per stream in each bucket (guards against a double-fired cycle),
      // then SUM across streams for a combined-portfolio equity per minute.
      // Single-stream scopes (the per-bot dashboard, which always pins
      // account_type) return one row per minute — same curve as before.
      dbQuery(
        `SELECT bucket AS snapshot_time,
                SUM(balance) AS balance,
                SUM(realized_pnl) AS realized_pnl,
                SUM(unrealized_pnl) AS unrealized_pnl,
                SUM(open_positions) AS open_positions,
                MAX(note) AS note
         FROM (
           SELECT date_trunc('minute', snapshot_time) AS bucket,
                  balance, realized_pnl, unrealized_pnl, open_positions, note,
                  ROW_NUMBER() OVER (
                    PARTITION BY date_trunc('minute', snapshot_time),
                                 person, COALESCE(account_type, 'sandbox')
                    ORDER BY snapshot_time DESC
                  ) AS rn
           FROM ${botTable(bot, 'equity_snapshots')}
           WHERE (snapshot_time AT TIME ZONE 'America/Chicago')::date = ${CT_TODAY}
             ${dteFilter} ${personFilter} ${accountTypeFilter}
         ) s
         WHERE rn = 1
         GROUP BY bucket
         ORDER BY bucket ASC`,
      ),
      dbQuery(
        `SELECT position_id, ticker, expiration,
                put_short_strike, put_long_strike,
                call_short_strike, call_long_strike,
                contracts, total_credit, spread_width${
                  bot === 'blaze' ? ', long_symbol, short_symbol, long_strike, short_strike, debit' : ''
                }
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' ${dteFilter} ${personFilter} ${accountTypeFilter}`,
      ),
      // Realized P&L recomputed from closed positions — the SAME formula
      // /status uses for the Balance card. paper_account.current_balance (which
      // is what the scanner copies into each snapshot) can drift from this, and
      // for SPARK sandbox it had: snapshots carried balance −$335 on a stale
      // $10K basis while the card showed $52,972 off a $63,100 basis.
      dbQuery(
        `SELECT COALESCE(SUM(realized_pnl), 0) AS realized_pnl
         FROM ${botTable(bot, 'positions')}
         WHERE status IN ('closed', 'expired')
           AND realized_pnl IS NOT NULL
           ${dteFilter} ${personFilter} ${accountTypeFilter}`,
      ),
    ])

    let startingCapital = basis.startingCapital

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
    let rebaseSource: 'tradier' | 'paper_account' | 'paper_ledger' = 'paper_account'
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

    // KINDLE production rebase: same idea as FLAME, but against KINDLE's OWN live
    // Tradier account (6YB70795 via TRADIER_KINDLE_* env). The scanner writes
    // snapshots on the paper basis (~$10K), but the Live view's top card shows the
    // real broker balance (~$350) — so without this the equity chart's Y-axis says
    // "$10,000" while the Balance card says "$354". Rebase to the broker's
    // start-of-day basis so the curve matches the account it's supposedly mirroring.
    if (bot === 'kindle' && accountTypeParam === 'production') {
      try {
        const prodAccts = await getProductionAccountsForBot('kindle')
        let eq = 0, closePl = 0, openPl = 0, have = false
        for (const pa of prodAccts) {
          if (!pa.accountId) continue
          const bal = await getTradierBalanceDetail(pa.apiKey, pa.accountId, pa.baseUrl)
          if (!bal || bal.total_equity == null) continue
          have = true
          eq += bal.total_equity
          closePl += bal.close_pl ?? 0
          openPl += bal.open_pl ?? 0
        }
        if (have) {
          const todayStartingBasis = Math.round((eq - closePl - openPl) * 100) / 100
          rebaseOffset = Math.round((todayStartingBasis - startingCapital) * 100) / 100
          startingCapital = todayStartingBasis
          rebaseSource = 'tradier'
        }
      } catch { /* fall back to paper basis */ }
    }

    // PAPER-LEDGER REBASE (2026-08-06). For every scope not already rebased to a
    // live broker balance above, land the curve on the same number the Balance
    // card shows: startingCapital + realized-from-closed-positions.
    //
    // The scanner writes each snapshot as a copy of `paper_account.current_balance`
    // (scanner.ts, "Equity snapshot" block), but /status deliberately does NOT
    // trust that column — it recomputes from the positions table because the
    // ledger column drifts. When `starting_capital` is later changed on the
    // account, historical snapshots are never rebased, so the two diverge
    // permanently. Observed 2026-08-06 on SPARK sandbox: every snapshot carried
    // balance −$335 (a $10K-era basis) while the card read $52,972 on the
    // $63,100 basis — a $53K gap between the chart and the header above it.
    //
    // A single constant offset preserves the intraday SHAPE exactly and only
    // moves the Y-axis onto the ledger. rebase_source reports which basis won so
    // an operator can still see that the raw column had drifted.
    if (rebaseSource === 'paper_account' && snapshotRows.length > 0) {
      const ledgerBalance = Math.round(
        (startingCapital + num(ledgerRows[0]?.realized_pnl)) * 100,
      ) / 100
      const lastRawBalance = num(snapshotRows[snapshotRows.length - 1]?.balance)
      const drift = Math.round((ledgerBalance - lastRawBalance) * 100) / 100
      if (drift !== 0) {
        rebaseOffset += drift
        rebaseSource = 'paper_ledger'
      }
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
            const contracts = int(pos.contracts)
            // BLAZE: directional vertical debit spread
            if (bot === 'blaze' && pos.long_symbol && pos.short_symbol) {
              const entryDebit = num(pos.debit)
              const verticalWidth = Math.abs(num(pos.short_strike) - num(pos.long_strike))
              const vResult = await getVerticalMarkToMarket(
                String(pos.long_symbol),
                String(pos.short_symbol),
                verticalWidth,
                pos.ticker || 'SPY',
              )
              if (!vResult) return 0
              return calculateVerticalUnrealizedPnl(
                entryDebit, vResult.value_to_close, contracts, verticalWidth,
              )
            }
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
      basis_account_count: basis.accountCount,
      snapshots,
      live_unrealized_pnl: liveUnrealizedPnl,
      open_position_count: openPositions.length,
      // Which basis the Y-axis is on: 'tradier' = rebased to a live broker
      // balance (FLAME / KINDLE production), 'paper_ledger' = rebased onto
      // starting_capital + realized-from-positions because the raw
      // paper_account.current_balance in the snapshots had drifted,
      // 'paper_account' = raw snapshot column, no drift found.
      rebase_source: rebaseSource,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
