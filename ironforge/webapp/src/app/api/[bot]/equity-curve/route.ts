import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import { scopedStartingCapital, DEFAULT_STARTING_CAPITAL } from '@/lib/account-basis'
import {
  getIcMarkToMarket,
  isConfigured,
  calculateIcUnrealizedPnl,
  getLoadedSandboxAccountsAsync,
  getAccountIdForKey,
  getTradierBalanceDetail,
  getVerticalMarkToMarket,
  calculateVerticalUnrealizedPnl,
  getSandboxAccountBalances,
  PRODUCTION_BOT,
} from '@/lib/tradier'

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
  // Pre-reset history. Rows parked at status='archived_reset' are real closed
  // trades from before the account was reset — SPARK sandbox has 86 of them
  // (2026-02-27 → 07-22, +$20,442.40) that no endpoint could reach, because the
  // curve query only accepts status IN ('closed','expired').
  //
  // Returned as a SEPARATE series, never merged into `curve`. They belong to a
  // retired ledger with its own starting capital, so splicing them onto the
  // current book would draw a reset boundary as if it were continuous equity.
  // Off by default so no existing caller changes behaviour.
  const includeArchived = req.nextUrl.searchParams.get('include_archived') === '1'

  try {
    // Include the counterfactual cumulative P&L so the chart can render a
    // second line ("if we'd held to 2:59 PM every day"). All three bots
    // now carry the hypothetical_eod_* columns.
    const hypoSelect = `, hypothetical_eod_pnl,
           SUM(COALESCE(hypothetical_eod_pnl, 0)) OVER (ORDER BY close_time) as cumulative_hypothetical_pnl`

    const [basis, curveRows, openPositions] = await Promise.all([
      // Basis must cover the same accounts the P&L below is summed over —
      // see lib/account-basis.ts for the blended-curve bug this fixes.
      scopedStartingCapital(bot, `${dteFilter} ${accountTypeFilter}`),
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
                contracts, total_credit, spread_width${
                  bot === 'blaze' ? ', long_symbol, short_symbol, long_strike, short_strike, debit' : ''
                }
         FROM ${botTable(bot, 'positions')}
         WHERE status = 'open' ${dteFilter} ${personFilter} ${accountTypeFilter}`,
      ),
    ])

    let startingCapital = basis.startingCapital
    let rebaseSource: 'tradier' | 'paper_account' = 'paper_account'

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
      // Closed-trade rows carry counterfactual fields so EquityChart can
      // plot a second line. cumulative_hypothetical_pnl is a running sum
      // over rows where hypothetical_eod_pnl IS NOT NULL — unmeasured rows
      // contribute 0 so the line stays flat across gaps, visually signaling
      // "we don't have data here." Available for all three bots.
      const cumHypo = num(row.cumulative_hypothetical_pnl)
      point.hypothetical_pnl = row.hypothetical_eod_pnl == null ? null : num(row.hypothetical_eod_pnl)
      point.cumulative_hypothetical_pnl = Math.round(cumHypo * 100) / 100
      point.hypothetical_equity = Math.round((startingCapital + cumHypo) * 100) / 100
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
            const contracts = int(pos.contracts)
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

    // FLAME historical rebase: same idea as the intraday endpoint — scanner
    // re-seeds paper_account.starting_capital to \$10K every cycle, but the
    // /flame top card shows the live Tradier User sandbox balance. Rebase
    // so the LAST point of the curve ends at Tradier. Same P&L shape/deltas,
    // Tradier basis on the Y-axis.
    //
    //   lastCumPnl   = cumulative realized at the most recent closed trade
    //   rebaseStart  = tradier.total_equity − lastCumPnl − liveUnrealized
    //   curve.equity = rebaseStart + cumulative_pnl   → ends at Tradier balance
    //
    // On Tradier failure: keep paper-basis starting_capital.
    if (bot === 'flame') {
      try {
        const accts = await getLoadedSandboxAccountsAsync()
        const userAcct = accts.find((a) => a.name === 'User' && a.type === 'sandbox')
        if (userAcct) {
          const accountId = await getAccountIdForKey(userAcct.apiKey, userAcct.baseUrl)
          if (accountId) {
            const bal = await getTradierBalanceDetail(userAcct.apiKey, accountId, userAcct.baseUrl)
            if (bal?.total_equity != null) {
              const lastCumPnl = curve.length > 0 ? curve[curve.length - 1].cumulative_pnl : 0
              const rebaseStart = Math.round((bal.total_equity - lastCumPnl - liveUnrealizedPnl) * 100) / 100
              const offset = rebaseStart - startingCapital
              if (offset !== 0) {
                curve = curve.map((pt) => ({
                  ...pt,
                  equity: Math.round((pt.equity + offset) * 100) / 100,
                  ...(pt.hypothetical_equity != null
                    ? { hypothetical_equity: Math.round((pt.hypothetical_equity + offset) * 100) / 100 }
                    : {}),
                }))
              }
              startingCapital = rebaseStart
              rebaseSource = 'tradier'
            }
          }
        }
      } catch { /* fall back to paper basis */ }
    }

    // SPARK production rebase: the top card shows the live Tradier (Iron Viper)
    // balance, and it's pause-independent — so rebase the curve to end at that
    // same broker equity (same P&L shape, broker basis on the Y-axis), keeping
    // the chart consistent with the scorecard. Uses getSandboxAccountBalances
    // (NOT pause-gated), so a paused bot still gets the right basis.
    if (bot === PRODUCTION_BOT && accountTypeParam === 'production') {
      try {
        const prodBals = (await getSandboxAccountBalances()).filter(
          (s) => s.account_type === 'production' && s.total_equity != null,
        )
        if (prodBals.length > 0) {
          const eq = Math.round(prodBals.reduce((a, s) => a + (s.total_equity ?? 0), 0) * 100) / 100
          const lastCumPnl = curve.length > 0 ? curve[curve.length - 1].cumulative_pnl : 0
          const rebaseStart = Math.round((eq - lastCumPnl - liveUnrealizedPnl) * 100) / 100
          const offset = rebaseStart - startingCapital
          if (offset !== 0) {
            curve = curve.map((pt) => ({
              ...pt,
              equity: Math.round((pt.equity + offset) * 100) / 100,
              ...(pt.hypothetical_equity != null
                ? { hypothetical_equity: Math.round((pt.hypothetical_equity + offset) * 100) / 100 }
                : {}),
            }))
          }
          startingCapital = rebaseStart
          rebaseSource = 'tradier'
        }
      } catch { /* fall back to paper basis */ }
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
      // Live point carries the previous hypothetical cum forward unchanged
      // — open positions don't have a hypo number until they close, so the
      // line stays flat at its last known value.
      if (last && last.cumulative_hypothetical_pnl != null) {
        livePoint.cumulative_hypothetical_pnl = last.cumulative_hypothetical_pnl
        livePoint.hypothetical_equity = Math.round((startingCapital + last.cumulative_hypothetical_pnl) * 100) / 100
        livePoint.hypothetical_pnl = null
      }
      curve.push(livePoint)
    }

    // ── Pre-reset segment ────────────────────────────────────────────────
    // Its baseline is the RETIRED ledger(s) for this scope (is_active = FALSE),
    // not the live one — that is the account these trades were actually run on.
    // The ledger's own `total_trades`/`cumulative_pnl` counters are reported
    // alongside the figures recomputed from the position rows, because on SPARK
    // they disagree (ledger says 100 trades / +$11,087.40; the rows say 86 /
    // +$20,442.40). Surfacing both is the honest move — silently picking one
    // would hide that some counted trades no longer have rows. See
    // /api/{bot}/fix-missing-history.
    let archived: {
      starting_capital: number
      curve: Array<{ timestamp: string | null; pnl: number; cumulative_pnl: number; equity: number }>
      trade_count: number
      realized_total: number
      ledger_ids: number[]
      ledger_counter_trades: number
      ledger_counter_pnl: number
      basis_note: string
    } | null = null

    if (includeArchived) {
      const [archivedRows, retiredLedgers] = await Promise.all([
        dbQuery(
          `SELECT close_time, realized_pnl,
                  SUM(realized_pnl) OVER (ORDER BY close_time) AS cumulative_pnl
           FROM ${botTable(bot, 'positions')}
           WHERE status = 'archived_reset'
             AND realized_pnl IS NOT NULL
             AND close_time IS NOT NULL
             ${dteFilter} ${personFilter} ${accountTypeFilter}
           ORDER BY close_time`,
        ),
        dbQuery(
          `SELECT id, starting_capital, total_trades, cumulative_pnl
           FROM ${botTable(bot, 'paper_account')}
           WHERE is_active = FALSE ${dteFilter} ${accountTypeFilter}`,
        ),
      ])

      if (archivedRows.length > 0) {
        const archivedBasis =
          retiredLedgers.reduce((a, r) => a + num(r.starting_capital), 0) || DEFAULT_STARTING_CAPITAL
        archived = {
          starting_capital: archivedBasis,
          curve: archivedRows.map((row) => {
            const cum = num(row.cumulative_pnl)
            return {
              timestamp: row.close_time || null,
              pnl: num(row.realized_pnl),
              cumulative_pnl: Math.round(cum * 100) / 100,
              equity: Math.round((archivedBasis + cum) * 100) / 100,
            }
          }),
          trade_count: archivedRows.length,
          realized_total:
            Math.round(num(archivedRows[archivedRows.length - 1]?.cumulative_pnl) * 100) / 100,
          ledger_ids: retiredLedgers.map((r) => int(r.id)),
          ledger_counter_trades: retiredLedgers.reduce((a, r) => a + int(r.total_trades), 0),
          ledger_counter_pnl:
            Math.round(retiredLedgers.reduce((a, r) => a + num(r.cumulative_pnl), 0) * 100) / 100,
          basis_note:
            'Baseline is the summed starting_capital of the RETIRED ledger(s) for this scope. ' +
            'This segment ran on a different account than the current curve — the two are ' +
            'separated by an account reset and must not be read as one continuous balance.',
        }
      }
    }

    return NextResponse.json({
      starting_capital: startingCapital,
      archived: archived,
      // How many active paper accounts the basis was summed over. 1 = a pinned
      // single-account view; >1 = a blended scope, where the curve is a
      // combined-portfolio series and not any one account's balance.
      basis_account_count: basis.accountCount,
      curve,
      period,
      open_position_count: openPositions.length,
      live_unrealized_pnl: liveUnrealizedPnl,
      rebase_source: rebaseSource,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
