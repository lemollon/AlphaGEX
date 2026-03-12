import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/databricks-sql'
import {
  getIcMarkToMarket,
  isConfigured,
  buildOccSymbol,
  getBatchOptionQuotes,
  getQuote,
  calculateIcUnrealizedPnl,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * Diagnostic endpoint: compares unrealized P&L from all sources.
 * Visit /api/spark/diagnose-pnl to see the raw data.
 */
export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  try {
    // 1. Get open positions from DB
    const positionRows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, spread_width, open_time
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}
       ORDER BY open_time DESC`,
    )

    // 2. Get latest equity snapshot (scanner's last calculation)
    const snapshotRows = await dbQuery(
      `SELECT snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note
       FROM ${botTable(bot, 'equity_snapshots')}
       ${dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''}
       ORDER BY snapshot_time DESC
       LIMIT 1`,
    )

    if (!positionRows.length) {
      return NextResponse.json({
        diagnosis: 'No open positions',
        positions: [],
        scanner_snapshot: snapshotRows[0] || null,
        tradier_connected: isConfigured(),
      })
    }

    // 3. For each position, get quotes via BOTH methods and compare
    const results = await Promise.all(
      positionRows.map(async (r) => {
        const ps = num(r.put_short_strike)
        const pl = num(r.put_long_strike)
        const cs = num(r.call_short_strike)
        const cl = num(r.call_long_strike)
        const contracts = int(r.contracts)
        const entryCredit = num(r.total_credit)
        const spreadWidth = num(r.spread_width) || Math.round((ps - pl) * 100) / 100
        const ticker = r.ticker || 'SPY'
        const expiration = r.expiration ? String(r.expiration).slice(0, 10) : ''

        // Method A: getIcMarkToMarket (used by position-monitor & status)
        let methodA: Record<string, unknown> = { error: 'Tradier not configured' }
        if (isConfigured()) {
          const mtm = await getIcMarkToMarket(ticker, expiration, ps, pl, cs, cl)
          if (mtm) {
            const pnl = calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close, contracts, spreadWidth)
            methodA = {
              cost_to_close: mtm.cost_to_close,
              put_short_ask: mtm.put_short_ask,
              put_long_bid: mtm.put_long_bid,
              call_short_ask: mtm.call_short_ask,
              call_long_bid: mtm.call_long_bid,
              spot_price: mtm.spot_price,
              raw_cost: Math.round((mtm.put_short_ask + mtm.call_short_ask - mtm.put_long_bid - mtm.call_long_bid) * 10000) / 10000,
              unrealized_pnl: pnl,
              formula: `(${entryCredit} - ${mtm.cost_to_close}) * 100 * ${contracts} = $${pnl}`,
            }
          } else {
            methodA = { error: 'getIcMarkToMarket returned null (quote unavailable)' }
          }
        }

        // Method B: getBatchOptionQuotes (used by position-detail)
        let methodB: Record<string, unknown> = { error: 'Tradier not configured' }
        if (isConfigured()) {
          const occPs = buildOccSymbol(ticker, expiration, ps, 'P')
          const occPl = buildOccSymbol(ticker, expiration, pl, 'P')
          const occCs = buildOccSymbol(ticker, expiration, cs, 'C')
          const occCl = buildOccSymbol(ticker, expiration, cl, 'C')

          const [batchQuotes, spyQ] = await Promise.all([
            getBatchOptionQuotes([occPs, occPl, occCs, occCl]),
            getQuote(ticker),
          ])

          const psQ = batchQuotes[occPs]
          const plQ = batchQuotes[occPl]
          const csQ = batchQuotes[occCs]
          const clQ = batchQuotes[occCl]

          if (psQ && plQ && csQ && clQ) {
            const rawCost = psQ.ask + csQ.ask - plQ.bid - clQ.bid
            const cappedCost = Math.min(Math.max(0, rawCost), spreadWidth)
            const costToClose = Math.round(cappedCost * 10000) / 10000
            const pnl = calculateIcUnrealizedPnl(entryCredit, costToClose, contracts, spreadWidth)

            // Scanner-style validation
            const validationIssues: string[] = []
            for (const [label, q] of [['PS', psQ], ['PL', plQ], ['CS', csQ], ['CL', clQ]] as const) {
              const qq = q as { bid: number; ask: number }
              if (qq.bid <= 0 && qq.ask <= 0) validationIssues.push(`${label}: zero bid/ask`)
              if (qq.bid > qq.ask && qq.ask > 0) validationIssues.push(`${label}: inverted (bid ${qq.bid} > ask ${qq.ask})`)
              const mid = (qq.bid + qq.ask) / 2
              if (mid > 0 && (qq.ask - qq.bid) > 0.50 * mid) {
                validationIssues.push(`${label}: wide spread (${(qq.ask - qq.bid).toFixed(2)} > 50% of mid ${mid.toFixed(2)})`)
              }
            }
            if (rawCost < 0) validationIssues.push(`Negative raw cost: ${rawCost.toFixed(4)}`)
            if (entryCredit > 0 && rawCost > 3 * entryCredit) {
              validationIssues.push(`Cost ${rawCost.toFixed(4)} > 3x entry ${entryCredit.toFixed(4)}`)
            }

            methodB = {
              occ_symbols: { ps: occPs, pl: occPl, cs: occCs, cl: occCl },
              quotes: {
                put_short: psQ,
                put_long: plQ,
                call_short: csQ,
                call_long: clQ,
              },
              spot_price: spyQ?.last ?? null,
              raw_cost: Math.round(rawCost * 10000) / 10000,
              capped_cost: costToClose,
              unrealized_pnl: pnl,
              formula: `(${entryCredit} - ${costToClose}) * 100 * ${contracts} = $${pnl}`,
              scanner_validation: validationIssues.length > 0
                ? { pass: false, issues: validationIssues }
                : { pass: true, issues: [] },
            }
          } else {
            methodB = {
              error: 'Some leg quotes unavailable',
              available: { ps: !!psQ, pl: !!plQ, cs: !!csQ, cl: !!clQ },
            }
          }
        }

        return {
          position_id: r.position_id,
          ticker,
          expiration,
          strikes: { put_long: pl, put_short: ps, call_short: cs, call_long: cl },
          contracts,
          entry_credit: entryCredit,
          spread_width: spreadWidth,
          open_time: r.open_time,
          method_a_getIcMarkToMarket: methodA,
          method_b_batchQuotes: methodB,
        }
      }),
    )

    // 4. Scanner's last known unrealized P&L
    const scannerSnapshot = snapshotRows[0]
      ? {
          snapshot_time: snapshotRows[0].snapshot_time,
          balance: num(snapshotRows[0].balance),
          realized_pnl: num(snapshotRows[0].realized_pnl),
          unrealized_pnl: num(snapshotRows[0].unrealized_pnl),
          open_positions: int(snapshotRows[0].open_positions),
          note: snapshotRows[0].note,
        }
      : null

    // 5. Summary comparison
    const methodAPnl = results.reduce((sum, r) => {
      const pnl = (r.method_a_getIcMarkToMarket as any)?.unrealized_pnl
      return sum + (typeof pnl === 'number' ? pnl : 0)
    }, 0)

    const methodBPnl = results.reduce((sum, r) => {
      const pnl = (r.method_b_batchQuotes as any)?.unrealized_pnl
      return sum + (typeof pnl === 'number' ? pnl : 0)
    }, 0)

    const scannerPnl = scannerSnapshot?.unrealized_pnl ?? null

    const hasValidationIssues = results.some((r) => {
      const v = (r.method_b_batchQuotes as any)?.scanner_validation
      return v && !v.pass
    })

    return NextResponse.json({
      bot: bot.toUpperCase(),
      timestamp: new Date().toISOString(),
      tradier_connected: isConfigured(),
      summary: {
        method_a_pnl: Math.round(methodAPnl * 100) / 100,
        method_b_pnl: Math.round(methodBPnl * 100) / 100,
        scanner_pnl: scannerPnl,
        all_agree: Math.abs(methodAPnl - methodBPnl) < 1 && (scannerPnl === null || Math.abs(methodAPnl - scannerPnl) < 50),
        has_validation_issues: hasValidationIssues,
        verdict: hasValidationIssues
          ? 'UNTRUSTED — Tradier quotes fail scanner validation (wide spreads / stale data). Scanner P&L is more reliable.'
          : 'OK — Tradier quotes pass validation',
      },
      scanner_snapshot: scannerSnapshot,
      positions: results,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
