/**
 * FLAME ↔ Tradier Reconciliation
 *
 * GET /api/flame/reconcile
 *   Compare paper positions to Tradier (sandbox or production).
 *   Detects orphan legs, entry credit drift, and unrealized P&L mismatches.
 *
 * POST /api/flame/reconcile
 *   Close orphan Tradier positions that have no matching paper position.
 *   Only closes legs not tracked by the database — preserves matched positions.
 */
import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, dbExecute, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  buildOccSymbol,
  getLoadedSandboxAccountsAsync,
  getSandboxAccountPositions,
  getIcMarkToMarket,
  closeOrphanSandboxPositions,
  isConfigured,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

interface LegMatch {
  occ_symbol: string
  strike: number
  type: 'P' | 'C'
  role: 'short' | 'long'
  paper_qty: number           // expected from paper (+/- contracts)
  tradier_qty: number         // actual in Tradier
  tradier_cost_basis: number
  tradier_market_value: number
  tradier_gain_loss: number
  qty_match: boolean
}

interface PositionRecon {
  position_id: string
  ticker: string
  expiration: string
  contracts: number
  paper_entry_credit: number
  paper_unrealized_pnl: number | null
  paper_unrealized_pct: number | null
  accounts: Record<string, {
    legs: LegMatch[]
    all_legs_found: boolean
    total_cost_basis: number         // sum of 4 legs' cost basis
    total_market_value: number       // sum of 4 legs' market value
    total_gain_loss: number          // sum of 4 legs' gain/loss
    tradier_unrealized_pct: number | null  // gain_loss / abs(cost_basis)
    // Entry comparison
    implied_entry_credit: number     // abs(cost_basis) / 100 / contracts
    entry_credit_diff: number        // paper - implied
    entry_credit_diff_pct: number    // diff as % of paper credit
    // Unrealized comparison
    unrealized_pnl_diff: number      // paper - tradier
    unrealized_pct_diff: number      // paper % - tradier %
  }>
}

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  // Only FLAME has sandbox/production positions
  if (bot !== 'flame') {
    return NextResponse.json({
      error: `Reconciliation only available for FLAME (has Tradier accounts). ${bot.toUpperCase()} is paper-only.`,
    }, { status: 400 })
  }

  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 503 })
  }

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  // Filter by account_type: production (Live Trading) or sandbox (Paper Trading)
  const accountType = _req.nextUrl.searchParams.get('account_type') || 'sandbox'
  const accountTypeFilter = `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountType)}'`

  try {
    // 1. Get open positions filtered by account_type
    const paperRows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit,
              sandbox_order_id, open_time
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${accountTypeFilter}
       ORDER BY open_time DESC`,
    )

    // 2. Get Tradier accounts filtered by type (production = Logan only, sandbox = User/Matt/Logan sandbox)
    const allAccounts = await getLoadedSandboxAccountsAsync()
    const accounts = allAccounts.filter(a => a.type === accountType)
    const accountPositions: Record<string, Array<{
      symbol: string; quantity: number; cost_basis: number;
      market_value: number; gain_loss: number; gain_loss_percent: number;
    }>> = {}

    for (const acct of accounts) {
      accountPositions[acct.name] = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
    }

    // 3. Build OCC symbols for each paper position and match
    const results: PositionRecon[] = []
    const matchedTradierSymbols: Record<string, Set<string>> = {}
    for (const acct of accounts) matchedTradierSymbols[acct.name] = new Set()

    for (const row of paperRows) {
      const ticker = row.ticker || 'SPY'
      const exp = row.expiration?.toISOString?.()?.slice(0, 10) ||
        (row.expiration ? String(row.expiration).slice(0, 10) : '')
      const ps = num(row.put_short_strike)
      const pl = num(row.put_long_strike)
      const cs = num(row.call_short_strike)
      const cl = num(row.call_long_strike)
      const contracts = int(row.contracts)
      const entryCredit = num(row.total_credit)
      const spreadWidth = num(row.spread_width) || (ps - pl)

      // Build OCC symbols for all 4 legs
      const legs: Array<{ occ: string; strike: number; type: 'P' | 'C'; role: 'short' | 'long'; expectedQty: number }> = [
        { occ: buildOccSymbol(ticker, exp, ps, 'P'), strike: ps, type: 'P', role: 'short', expectedQty: -contracts },
        { occ: buildOccSymbol(ticker, exp, pl, 'P'), strike: pl, type: 'P', role: 'long', expectedQty: contracts },
        { occ: buildOccSymbol(ticker, exp, cs, 'C'), strike: cs, type: 'C', role: 'short', expectedQty: -contracts },
        { occ: buildOccSymbol(ticker, exp, cl, 'C'), strike: cl, type: 'C', role: 'long', expectedQty: contracts },
      ]

      // Get live MTM for paper P&L
      let paperUnrealizedPnl: number | null = null
      let paperUnrealizedPct: number | null = null
      try {
        const mtm = await getIcMarkToMarket(ticker, exp, ps, pl, cs, cl, entryCredit)
        if (mtm) {
          const costLast = mtm.cost_to_close_last
          const cappedCost = Math.min(Math.max(0, costLast), spreadWidth)
          paperUnrealizedPnl = Math.round((entryCredit - cappedCost) * 100 * contracts * 100) / 100
          paperUnrealizedPct = entryCredit > 0
            ? Math.round(((entryCredit - cappedCost) / entryCredit) * 10000) / 100
            : 0
        }
      } catch { /* MTM fetch failed — will show null */ }

      // Parse sandbox order info for entry fill comparison
      let sandboxInfo: Record<string, { order_id?: number; contracts?: number; fill_price?: number }> = {}
      try {
        if (row.sandbox_order_id) sandboxInfo = JSON.parse(row.sandbox_order_id)
      } catch { /* ignore parse error */ }

      // Match each account
      const acctResults: PositionRecon['accounts'] = {}

      for (const acct of accounts) {
        const positions = accountPositions[acct.name]
        const posMap = new Map(positions.map(p => [p.symbol, p]))

        const legMatches: LegMatch[] = []
        let allFound = true
        let totalCost = 0
        let totalMv = 0
        let totalGl = 0

        for (const leg of legs) {
          const tPos = posMap.get(leg.occ)
          if (tPos) {
            matchedTradierSymbols[acct.name].add(leg.occ)
            const qtyMatch = tPos.quantity === leg.expectedQty
            legMatches.push({
              occ_symbol: leg.occ,
              strike: leg.strike,
              type: leg.type,
              role: leg.role,
              paper_qty: leg.expectedQty,
              tradier_qty: tPos.quantity,
              tradier_cost_basis: tPos.cost_basis,
              tradier_market_value: tPos.market_value,
              tradier_gain_loss: tPos.gain_loss,
              qty_match: qtyMatch,
            })
            if (!qtyMatch) allFound = false
            totalCost += tPos.cost_basis
            totalMv += tPos.market_value
            totalGl += tPos.gain_loss
          } else {
            allFound = false
            legMatches.push({
              occ_symbol: leg.occ,
              strike: leg.strike,
              type: leg.type,
              role: leg.role,
              paper_qty: leg.expectedQty,
              tradier_qty: 0,
              tradier_cost_basis: 0,
              tradier_market_value: 0,
              tradier_gain_loss: 0,
              qty_match: false,
            })
          }
        }

        // Tradier cost basis for an IC: short legs have negative cost, long legs positive
        // Net cost basis is negative (you received credit). abs(netCost) / 100 / contracts = credit per share.
        const absCost = Math.abs(totalCost)
        const acctContracts = sandboxInfo[acct.name]?.contracts || contracts
        const impliedCredit = absCost > 0 && acctContracts > 0
          ? Math.round((absCost / 100 / acctContracts) * 10000) / 10000
          : 0

        const tradierPct = absCost > 0
          ? Math.round((totalGl / absCost) * 10000) / 100
          : null

        acctResults[acct.name] = {
          legs: legMatches,
          all_legs_found: allFound,
          total_cost_basis: Math.round(totalCost * 100) / 100,
          total_market_value: Math.round(totalMv * 100) / 100,
          total_gain_loss: Math.round(totalGl * 100) / 100,
          tradier_unrealized_pct: tradierPct,
          implied_entry_credit: impliedCredit,
          entry_credit_diff: Math.round((entryCredit - impliedCredit) * 10000) / 10000,
          entry_credit_diff_pct: impliedCredit > 0
            ? Math.round(((entryCredit - impliedCredit) / entryCredit) * 10000) / 100
            : 0,
          unrealized_pnl_diff: paperUnrealizedPnl != null
            ? Math.round((paperUnrealizedPnl - totalGl) * 100) / 100
            : 0,
          unrealized_pct_diff: paperUnrealizedPct != null && tradierPct != null
            ? Math.round((paperUnrealizedPct - tradierPct) * 100) / 100
            : 0,
        }
      }

      results.push({
        position_id: row.position_id,
        ticker,
        expiration: exp,
        contracts,
        paper_entry_credit: entryCredit,
        paper_unrealized_pnl: paperUnrealizedPnl,
        paper_unrealized_pct: paperUnrealizedPct,
        accounts: acctResults,
      })
    }

    // 4. Find orphans: Tradier positions not matched to any paper position
    const orphans: Record<string, Array<{
      symbol: string; quantity: number; cost_basis: number;
      market_value: number; gain_loss: number;
    }>> = {}
    let totalOrphans = 0

    for (const acct of accounts) {
      const positions = accountPositions[acct.name]
      const unmatched = positions.filter(
        p => p.quantity !== 0 && !matchedTradierSymbols[acct.name].has(p.symbol),
      )
      if (unmatched.length > 0) {
        orphans[acct.name] = unmatched
        totalOrphans += unmatched.length
      }
    }

    // 5. Summary checks
    const checks: Array<{ name: string; pass: boolean; detail: string }> = []

    // Check A: All paper positions have all 4 legs in each account
    for (const r of results) {
      for (const [acctName, acctData] of Object.entries(r.accounts)) {
        checks.push({
          name: `${r.position_id} legs in ${acctName}`,
          pass: acctData.all_legs_found,
          detail: acctData.all_legs_found
            ? 'All 4 legs found with correct quantities'
            : `Missing/wrong legs: ${acctData.legs.filter(l => !l.qty_match).map(l => `${l.occ_symbol} (paper=${l.paper_qty}, tradier=${l.tradier_qty})`).join(', ')}`,
        })
      }
    }

    // Check B: Entry credit within 5% (fills can differ slightly)
    for (const r of results) {
      for (const [acctName, acctData] of Object.entries(r.accounts)) {
        if (!acctData.all_legs_found) continue
        const pct = Math.abs(acctData.entry_credit_diff_pct)
        checks.push({
          name: `${r.position_id} entry credit vs ${acctName}`,
          pass: pct < 5,
          detail: `Paper=$${r.paper_entry_credit.toFixed(4)}, Tradier implied=$${acctData.implied_entry_credit.toFixed(4)}, diff=${acctData.entry_credit_diff_pct.toFixed(1)}%`,
        })
      }
    }

    // Check C: Unrealized P&L % within 5 points
    for (const r of results) {
      for (const [acctName, acctData] of Object.entries(r.accounts)) {
        if (!acctData.all_legs_found || r.paper_unrealized_pct == null || acctData.tradier_unrealized_pct == null) continue
        const diff = Math.abs(acctData.unrealized_pct_diff)
        checks.push({
          name: `${r.position_id} unrealized % vs ${acctName}`,
          pass: diff < 5,
          detail: `Paper=${r.paper_unrealized_pct.toFixed(1)}%, Tradier=${acctData.tradier_unrealized_pct.toFixed(1)}%, diff=${acctData.unrealized_pct_diff.toFixed(1)}pp`,
        })
      }
    }

    // Check D: No orphans
    checks.push({
      name: 'No orphan Tradier positions',
      pass: totalOrphans === 0,
      detail: totalOrphans === 0
        ? 'All Tradier positions match a paper position'
        : `${totalOrphans} orphan legs across accounts: ${Object.entries(orphans).map(([a, ps]) => `${a}: ${ps.map(p => p.symbol).join(', ')}`).join('; ')}`,
    })

    const passCount = checks.filter(c => c.pass).length
    const failCount = checks.filter(c => !c.pass).length

    return NextResponse.json({
      summary: {
        paper_positions: paperRows.length,
        sandbox_accounts: accounts.map(a => a.name),
        total_checks: checks.length,
        passed: passCount,
        failed: failCount,
        total_orphan_legs: totalOrphans,
        verdict: failCount === 0 ? 'ALL_MATCH' : 'MISMATCH',
      },
      positions: results,
      orphans,
      checks,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}

/**
 * POST /api/flame/reconcile
 *
 * Close orphan Tradier positions that have no matching paper position.
 * Uses the same detection logic as GET, then calls closeOrphanSandboxPositions
 * to close only the unmatched legs — preserving positions tracked by the DB.
 */
export async function POST(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  if (bot !== 'flame') {
    return NextResponse.json({
      error: `Orphan close only available for FLAME (has Tradier accounts). ${bot.toUpperCase()} is paper-only.`,
    }, { status: 400 })
  }

  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured' }, { status: 503 })
  }

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  const accountType = _req.nextUrl.searchParams.get('account_type') || 'sandbox'
  const accountTypeFilter = `AND COALESCE(account_type, 'sandbox') = '${escapeSql(accountType)}'`

  try {
    // 1. Get open paper positions to build matched OCC symbols
    const paperRows = await dbQuery(
      `SELECT ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter} ${accountTypeFilter}
       ORDER BY open_time DESC`,
    )

    // Build set of OCC symbols that correspond to tracked paper positions
    const matchedSymbols = new Set<string>()
    for (const row of paperRows) {
      const ticker = row.ticker || 'SPY'
      const exp = row.expiration?.toISOString?.()?.slice(0, 10) ||
        (row.expiration ? String(row.expiration).slice(0, 10) : '')
      for (const [strike, type] of [
        [num(row.put_short_strike), 'P'], [num(row.put_long_strike), 'P'],
        [num(row.call_short_strike), 'C'], [num(row.call_long_strike), 'C'],
      ] as [number, string][]) {
        matchedSymbols.add(buildOccSymbol(ticker, exp, strike, type as 'P' | 'C'))
      }
    }

    // 2. Get Tradier accounts filtered by type
    const allAccounts = await getLoadedSandboxAccountsAsync()
    const accounts = allAccounts.filter(a => a.type === accountType)

    if (accounts.length === 0) {
      return NextResponse.json({ error: `No ${accountType} accounts configured` }, { status: 400 })
    }

    // 3. For each account, find orphan positions and close them
    const results: Array<{
      account: string
      orphans_found: number
      closed: number
      failed: number
      details: string[]
    }> = []
    let totalClosed = 0
    let totalFailed = 0
    let totalOrphans = 0

    for (const acct of accounts) {
      const positions = await getSandboxAccountPositions(acct.apiKey, undefined, acct.baseUrl)
      const orphans = positions.filter(p => p.quantity !== 0 && !matchedSymbols.has(p.symbol))

      if (orphans.length === 0) {
        results.push({
          account: acct.name,
          orphans_found: 0,
          closed: 0,
          failed: 0,
          details: [`${acct.name}: No orphan positions to close`],
        })
        continue
      }

      totalOrphans += orphans.length
      const orphanSymbols = new Set(orphans.map(o => o.symbol))
      const closeResult = await closeOrphanSandboxPositions(acct.apiKey, acct.name, orphanSymbols, acct.baseUrl)

      totalClosed += closeResult.closed
      totalFailed += closeResult.failed
      results.push({
        account: acct.name,
        orphans_found: orphans.length,
        closed: closeResult.closed,
        failed: closeResult.failed,
        details: closeResult.details,
      })
    }

    // 4. Log the action
    try {
      await dbExecute(
        `INSERT INTO ${botTable(bot, 'logs')} (log_time, level, message, details, dte_mode)
         VALUES (NOW(), 'RECONCILE',
                 $1, $2, '${escapeSql(dte || '2DTE')}')`,
        [
          `Manual orphan close (${accountType}): ${totalOrphans} found, ${totalClosed} closed, ${totalFailed} failed`,
          JSON.stringify({ account_type: accountType, results, source: 'reconcile-api-post' }),
        ],
      )
    } catch {
      // Non-fatal
    }

    return NextResponse.json({
      action: 'close_orphans',
      account_type: accountType,
      total_orphans_found: totalOrphans,
      total_closed: totalClosed,
      total_failed: totalFailed,
      results,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
