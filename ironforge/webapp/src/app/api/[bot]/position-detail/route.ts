import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  isConfigured,
  buildOccSymbol,
  getBatchOptionQuotes,
  getQuote,
  getLoadedSandboxAccounts,
  getSandboxAccountPositions,
  calculateIcUnrealizedPnl,
} from '@/lib/tradier'
import { getCurrentPTTier, getCTNow } from '@/lib/pt-tiers'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''

  try {
    const positionRows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss, max_profit,
              underlying_at_entry, vix_at_entry, collateral_required,
              wings_adjusted, open_time, sandbox_order_id
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}
       ORDER BY open_time DESC`,
    )

    if (!positionRows.length) {
      return NextResponse.json({ positions: [], tradier_connected: isConfigured() })
    }

    const ptTier = getCurrentPTTier(getCTNow())
    const sandboxAccounts = getLoadedSandboxAccounts()

    const positions = await Promise.all(
      positionRows.map(async (r) => {
        const ps = num(r.put_short_strike)
        const pl = num(r.put_long_strike)
        const cs = num(r.call_short_strike)
        const cl = num(r.call_long_strike)
        const contracts = int(r.contracts)
        const entryCredit = num(r.total_credit)
        const putCredit = num(r.put_credit)
        const callCredit = num(r.call_credit)
        const collateral = num(r.collateral_required)
        const ticker = r.ticker || 'SPY'
        const expiration = r.expiration?.toISOString?.()?.slice(0, 10) || (r.expiration ? String(r.expiration).slice(0, 10) : '')

        const occPs = buildOccSymbol(ticker, expiration, ps, 'P')
        const occPl = buildOccSymbol(ticker, expiration, pl, 'P')
        const occCs = buildOccSymbol(ticker, expiration, cs, 'C')
        const occCl = buildOccSymbol(ticker, expiration, cl, 'C')
        const occSymbols = [occPs, occPl, occCs, occCl]

        let legQuotes: Record<string, { bid: number; ask: number; mid: number; last: number }> = {}
        let spyPrice: number | null = null

        if (isConfigured()) {
          const [batchQuotes, spyQ] = await Promise.all([
            getBatchOptionQuotes(occSymbols),
            getQuote(ticker),
          ])
          legQuotes = batchQuotes
          spyPrice = spyQ?.last ?? null
        }

        const psQ = legQuotes[occPs]
        const plQ = legQuotes[occPl]
        const csQ = legQuotes[occCs]
        const clQ = legQuotes[occCl]
        const hasQuotes = !!(psQ && plQ && csQ && clQ)

        const legs = [
          { type: 'put_long' as const, label: 'Put Long', strike: pl, option_type: 'P', side: 'buy' as const, occ: occPl, quantity: contracts, current_bid: plQ?.bid ?? null, current_ask: plQ?.ask ?? null, current_mid: plQ?.mid ?? null },
          { type: 'put_short' as const, label: 'Put Short', strike: ps, option_type: 'P', side: 'sell' as const, occ: occPs, quantity: contracts, current_bid: psQ?.bid ?? null, current_ask: psQ?.ask ?? null, current_mid: psQ?.mid ?? null },
          { type: 'call_short' as const, label: 'Call Short', strike: cs, option_type: 'C', side: 'sell' as const, occ: occCs, quantity: contracts, current_bid: csQ?.bid ?? null, current_ask: csQ?.ask ?? null, current_mid: csQ?.mid ?? null },
          { type: 'call_long' as const, label: 'Call Long', strike: cl, option_type: 'C', side: 'buy' as const, occ: occCl, quantity: contracts, current_bid: clQ?.bid ?? null, current_ask: clQ?.ask ?? null, current_mid: clQ?.mid ?? null },
        ]

        let currentDebit: number | null = null
        // currentDebitMid uses last/mid prices to match Tradier's P&L calculation.
        // currentDebit (bid/ask worst-case) is kept for cost-to-close and PT/SL proximity.
        let currentDebitMid: number | null = null
        let paperPnl: number | null = null
        let spreadPnlPerContract: number | null = null
        let pctProfitCaptured: number | null = null

        if (hasQuotes) {
          // Worst-case bid/ask debit (what you'd actually pay to close)
          const rawDebit = psQ.ask + csQ.ask - plQ.bid - clQ.bid
          const spreadWidthCalc = Math.round((ps - pl) * 100) / 100
          currentDebit = Math.round(Math.min(Math.max(0, rawDebit), spreadWidthCalc) * 10000) / 10000

          // Mid/last price debit — matches Tradier's Gain/Loss calculation.
          // Tradier uses last trade prices; we use last with mid fallback.
          const psLast = psQ.last > 0 ? psQ.last : psQ.mid
          const plLast = plQ.last > 0 ? plQ.last : plQ.mid
          const csLast = csQ.last > 0 ? csQ.last : csQ.mid
          const clLast = clQ.last > 0 ? clQ.last : clQ.mid
          const rawDebitMid = psLast + csLast - plLast - clLast
          currentDebitMid = Math.round(Math.min(Math.max(0, rawDebitMid), spreadWidthCalc) * 10000) / 10000

          spreadPnlPerContract = Math.round((entryCredit - currentDebitMid) * 10000) / 10000
          paperPnl = calculateIcUnrealizedPnl(entryCredit, currentDebitMid, contracts, spreadWidthCalc)
          pctProfitCaptured = entryCredit > 0
            ? Math.round(((entryCredit - currentDebitMid) / entryCredit) * 10000) / 100
            : 0
        }

        const maxProfit = Math.round(entryCredit * 100 * contracts * 100) / 100
        const maxLoss = Math.round(collateral * 100) / 100
        const putBreakeven = Math.round((ps - entryCredit) * 10000) / 10000
        const callBreakeven = Math.round((cs + entryCredit) * 10000) / 10000
        const distanceToPut = spyPrice != null ? Math.round((spyPrice - ps) * 100) / 100 : null
        const distanceToCall = spyPrice != null ? Math.round((cs - spyPrice) * 100) / 100 : null

        const currentPtPct = ptTier.pct
        const ptTargetPrice = Math.round(entryCredit * (1 - currentPtPct) * 10000) / 10000
        const ptTargetDollar = Math.round(entryCredit * currentPtPct * 100 * contracts * 100) / 100
        let pctToPt: number | null = null
        if (currentDebit != null) {
          const remaining = currentDebit - ptTargetPrice
          const totalToGo = entryCredit - ptTargetPrice
          pctToPt = totalToGo > 0 ? Math.round((remaining / totalToGo) * 10000) / 100 : 0
        }

        let sandboxOrderIds: Record<string, unknown> | null = null
        try {
          sandboxOrderIds = r.sandbox_order_id ? JSON.parse(r.sandbox_order_id) : null
        } catch {
          sandboxOrderIds = null
        }

        const sandboxResults = await Promise.all(
          sandboxAccounts.map(async (acct) => {
            const acctInfo = (sandboxOrderIds as Record<string, Record<string, unknown>> | null)?.[acct.name]
            if (!acctInfo) return null

            const acctInfoObj = typeof acctInfo === 'object' ? (acctInfo as Record<string, unknown>) : null
            const orderId = acctInfoObj ? acctInfoObj.order_id : acctInfo
            const acctContracts = acctInfoObj ? int(acctInfoObj.contracts) : contracts
            const fillPrice = acctInfoObj ? Number(acctInfoObj.fill_price || 0) : 0

            // Use Tradier fill price for entry credit when available (more accurate
            // than paper entry credit since sandbox may fill at different prices).
            const acctEntryCredit = fillPrice > 0 ? fillPrice : entryCredit

            let tradierPnl: number | null = null
            let tradierCostBasis: number | null = null
            let tradierMarketValue: number | null = null
            try {
              const positions = await getSandboxAccountPositions(acct.apiKey, occSymbols)
              if (positions.length > 0) {
                tradierCostBasis = positions.reduce((s, p) => s + p.cost_basis, 0)
                tradierMarketValue = positions.reduce((s, p) => s + p.market_value, 0)
              }
            } catch {
              // Sandbox may be unreachable
            }

            // Compute P&L using mid/last prices to match Tradier's Gain/Loss.
            // Falls back to market_value - cost_basis if no production quotes.
            let calcPnl: number | null = null
            if (currentDebitMid != null) {
              calcPnl = Math.round((acctEntryCredit - currentDebitMid) * 100 * acctContracts * 100) / 100
              tradierPnl = calcPnl
            } else if (tradierCostBasis != null && tradierMarketValue != null) {
              tradierPnl = Math.round((tradierMarketValue - tradierCostBasis) * 100) / 100
            }

            return {
              name: acct.name, order_id: orderId, contracts: acctContracts,
              fill_price: fillPrice > 0 ? fillPrice : null,
              entry_credit_total: Math.round(acctEntryCredit * 100 * acctContracts * 100) / 100,
              current_debit_total: currentDebitMid != null ? Math.round(currentDebitMid * 100 * acctContracts * 100) / 100 : null,
              calculated_pnl: calcPnl,
              tradier_pnl: tradierPnl != null ? Math.round(tradierPnl * 100) / 100 : null,
              tradier_cost_basis: tradierCostBasis != null ? Math.round(tradierCostBasis * 100) / 100 : null,
              tradier_market_value: tradierMarketValue != null ? Math.round(tradierMarketValue * 100) / 100 : null,
            }
          }),
        )

        const paperAccount = {
          name: 'Paper', order_id: null, contracts,
          entry_credit_total: maxProfit,
          current_debit_total: currentDebitMid != null ? Math.round(currentDebitMid * 100 * contracts * 100) / 100 : null,
          calculated_pnl: paperPnl,
          tradier_pnl: null, tradier_cost_basis: null, tradier_market_value: null,
        }

        return {
          position_id: r.position_id, ticker, expiration,
          put_short_strike: ps, put_long_strike: pl, put_credit: putCredit,
          call_short_strike: cs, call_long_strike: cl, call_credit: callCredit,
          contracts, spread_width: num(r.spread_width),
          total_credit: entryCredit, collateral_required: collateral,
          underlying_at_entry: num(r.underlying_at_entry),
          open_time: r.open_time || null, spy_price: spyPrice,
          legs,
          entry_credit: entryCredit, current_debit: currentDebitMid, cost_to_close: currentDebit,
          spread_pnl_per_contract: spreadPnlPerContract, paper_pnl: paperPnl,
          max_profit: maxProfit, max_loss: maxLoss,
          put_breakeven: putBreakeven, call_breakeven: callBreakeven,
          distance_to_put: distanceToPut, distance_to_call: distanceToCall,
          pct_profit_captured: pctProfitCaptured,
          current_pt_tier: ptTier.label, current_pt_pct: Math.round(currentPtPct * 100),
          pt_target_price: ptTargetPrice, pt_target_dollar: ptTargetDollar, pct_to_pt: pctToPt,
          progress: { max_loss: -maxLoss, current: paperPnl, zero: 0, pt_target: ptTargetDollar, max_profit: maxProfit },
          sandbox_accounts: [paperAccount, ...sandboxResults.filter(Boolean)],
        }
      }),
    )

    return NextResponse.json({ positions, tradier_connected: isConfigured() })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
