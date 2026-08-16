import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import { scopedStartingCapital } from '@/lib/account-basis'
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
  canReadProductionBalance,
  getLiveEquityForBot,
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
  // ARCHIVED HISTORY — folded into ONE continuous curve (operator decision,
  // 2026-08-07: "it all needs to be combined into one").
  //
  // Two separate mechanisms hid a bot's older trades from every endpoint:
  //   1. status = 'archived_reset'      — the curve only accepted 'closed'/'expired'
  //   2. dte_mode = 'ARCHIVED_1DTE'     — every route pins the live dte_mode
  // On SPARK that is 86 sandbox trades (2026-02-27 → 07-22, +$20,442.40) and 35
  // production trades (04-20 → 06-16, −$2,050.57).
  //
  // CRITICAL — the baseline must be REBASED, not reused. The live ledger's
  // starting_capital already reflects post-reset capital, so adding archived P&L
  // on top of it would double-count the reset and end the curve above the
  // Balance card. Rebasing by the archived total (see combinedBaseline below)
  // keeps every delta exact AND still lands the final point on the live balance.
  // The reset is a CAPITAL event, not a trading result, so it belongs in the
  // baseline rather than as a step in the equity line.
  // Off by default so no existing caller changes behaviour.
  const includeArchived = req.nextUrl.searchParams.get('include_archived') === '1'
  // Archived rows live under an ARCHIVED_* dte_mode, so the live-mode pin has to
  // widen or they stay invisible even with the status opened up.
  const curveDteFilter =
    includeArchived && dte
      ? `AND (dte_mode = '${escapeSql(dte)}' OR dte_mode LIKE 'ARCHIVED%')`
      : dteFilter
  const curveStatusFilter = includeArchived
    ? `status IN ('closed', 'expired', 'archived_reset')`
    : `status IN ('closed', 'expired')`
  // Predicate identifying the archived side of the union, used both to total the
  // rebase amount and to mark where the live book begins.
  const archivedPredicate = `(status = 'archived_reset'${dte ? ` OR dte_mode LIKE 'ARCHIVED%'` : ''})`

  try {
    // Include the counterfactual cumulative P&L so the chart can render a
    // second line ("if we'd held to 2:59 PM every day"). All three bots
    // now carry the hypothetical_eod_* columns.
    const hypoSelect = `, hypothetical_eod_pnl,
           SUM(COALESCE(hypothetical_eod_pnl, 0)) OVER (ORDER BY close_time) as cumulative_hypothetical_pnl`

    const [basis, curveRows, openPositions, archivedAgg] = await Promise.all([
      // Basis must cover the same accounts the P&L below is summed over —
      // see lib/account-basis.ts for the blended-curve bug this fixes.
      scopedStartingCapital(bot, `${dteFilter} ${accountTypeFilter}`),
      dbQuery(
        `SELECT
          close_time,
          realized_pnl,
          ${includeArchived ? archivedPredicate : 'FALSE'} AS is_archived,
          SUM(realized_pnl) OVER (ORDER BY close_time) as cumulative_pnl${hypoSelect}
        FROM ${botTable(bot, 'positions')}
        WHERE ${curveStatusFilter}
          AND realized_pnl IS NOT NULL
          AND close_time IS NOT NULL
          ${curveDteFilter} ${personFilter} ${accountTypeFilter}
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
      // Total P&L of the archived side only — the amount the baseline must be
      // pulled back by so the combined curve still ends on the live balance.
      includeArchived
        ? dbQuery(
            `SELECT COALESCE(SUM(realized_pnl), 0) AS pnl,
                    COUNT(*)                       AS trades,
                    MIN(close_time)                AS first_close,
                    MAX(close_time)                AS last_close
             FROM ${botTable(bot, 'positions')}
             WHERE ${archivedPredicate}
               AND realized_pnl IS NOT NULL
               AND close_time IS NOT NULL
               ${curveDteFilter} ${personFilter} ${accountTypeFilter}`,
          )
        : Promise.resolve([]),
    ])

    // Rebase: live_balance = basis + live_era_pnl, and the combined curve ends at
    // basis + (live_era_pnl + archived_pnl). Subtracting archived_pnl from the
    // baseline cancels that extra term, so the final point still equals the
    // Balance card while every step in between stays exact.
    const archivedPnl = Math.round(num(archivedAgg[0]?.pnl) * 100) / 100
    const archivedTrades = int(archivedAgg[0]?.trades)
    let startingCapital = Math.round((basis.startingCapital - archivedPnl) * 100) / 100
    let rebaseSource: 'tradier' | 'paper_account' = 'paper_account'
    // Where the live book takes over — rendered as an informational marker, NOT
    // a break in the line.
    const liveEraStart = curveRows.find((r) => r.is_archived === false || r.is_archived === 'f')
      ?.close_time ?? null

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
    // Tradier is the point of reference for a live account. getLiveEquityForBot
    // resolves the bot's OWN production account whichever way it is credentialed
    // — table (SPARK) or env (FLAME) — where getSandboxAccountBalances() only saw
    // table-backed ones and would have rebased FLAME onto SPARK's balance.
    if (canReadProductionBalance(bot) && accountTypeParam === 'production') {
      try {
        const eqLive = await getLiveEquityForBot(bot)
        if (eqLive != null) {
          const eq = eqLive
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

    // ── Archived-history summary (metadata only) ─────────────────────────
    // The archived trades are already IN `curve` above — one continuous series.
    // This block only describes them so the chart can mark where the live book
    // begins and footnote the rebase.
    const archivedSummary = includeArchived && archivedTrades > 0
      ? {
          trade_count: archivedTrades,
          realized_total: archivedPnl,
          first_close: archivedAgg[0]?.first_close ?? null,
          last_close: archivedAgg[0]?.last_close ?? null,
          live_era_starts_at: liveEraStart,
          ledger_starting_capital: basis.startingCapital,
          rebase_note:
            'Archived trades are merged into a single continuous curve. The baseline is ' +
            'the live ledger starting_capital MINUS the archived P&L, because that ' +
            'starting_capital already reflects post-reset capital — without the rebase the ' +
            'account reset would be counted twice and the curve would not end on the ' +
            'Balance card. Every trade-to-trade delta is exact; the capital reset itself ' +
            'is absorbed into the baseline rather than drawn as a step.',
        }
      : null

    return NextResponse.json({
      starting_capital: startingCapital,
      archived_summary: archivedSummary,
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
