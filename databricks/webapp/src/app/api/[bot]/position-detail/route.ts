import { NextRequest, NextResponse } from 'next/server'
import { query, botTable, num, int, validateBot, dteMode } from '@/lib/databricks'
import {
  isConfigured,
  buildOccSymbol,
  getOptionQuote,
  getQuote,
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

  try {
    const positionRows = await query(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike, put_credit,
              call_short_strike, call_long_strike, call_credit,
              contracts, spread_width, total_credit, max_loss, max_profit,
              underlying_at_entry, vix_at_entry, collateral_required,
              open_time, sandbox_order_id
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' AND dte_mode = '${dte}'
       ORDER BY open_time DESC`,
    )

    if (!positionRows.length) {
      return NextResponse.json({ positions: [], tradier_connected: isConfigured() })
    }

    const ptTier = getCurrentPTTier(getCTNow())

    const positions = await Promise.all(
      positionRows.map(async (r: Record<string, string | null>) => {
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
        const expiration = String(r.expiration || '').slice(0, 10)

        // Build OCC symbols for all 4 legs
        const occPs = buildOccSymbol(ticker, expiration, ps, 'P')
        const occPl = buildOccSymbol(ticker, expiration, pl, 'P')
        const occCs = buildOccSymbol(ticker, expiration, cs, 'C')
        const occCl = buildOccSymbol(ticker, expiration, cl, 'C')

        // Fetch live quotes for all legs + SPY in parallel
        let psQ: { bid: number; ask: number; last: number } | null = null
        let plQ: { bid: number; ask: number; last: number } | null = null
        let csQ: { bid: number; ask: number; last: number } | null = null
        let clQ: { bid: number; ask: number; last: number } | null = null
        let spyPrice: number | null = null

        if (isConfigured()) {
          const [psRes, plRes, csRes, clRes, spyQ] = await Promise.all([
            getOptionQuote(occPs),
            getOptionQuote(occPl),
            getOptionQuote(occCs),
            getOptionQuote(occCl),
            getQuote(ticker),
          ])
          psQ = psRes
          plQ = plRes
          csQ = csRes
          clQ = clRes
          spyPrice = spyQ?.last ?? null
        }

        const hasQuotes = !!(psQ && plQ && csQ && clQ)

        // Per-leg details
        const legs = [
          {
            type: 'put_long',
            label: 'Put Long',
            strike: pl,
            option_type: 'P',
            side: 'buy' as const,
            occ: occPl,
            quantity: contracts,
            current_bid: plQ?.bid ?? null,
            current_ask: plQ?.ask ?? null,
            current_mid: plQ ? Math.round(((plQ.bid + plQ.ask) / 2) * 100) / 100 : null,
          },
          {
            type: 'put_short',
            label: 'Put Short',
            strike: ps,
            option_type: 'P',
            side: 'sell' as const,
            occ: occPs,
            quantity: contracts,
            current_bid: psQ?.bid ?? null,
            current_ask: psQ?.ask ?? null,
            current_mid: psQ ? Math.round(((psQ.bid + psQ.ask) / 2) * 100) / 100 : null,
          },
          {
            type: 'call_short',
            label: 'Call Short',
            strike: cs,
            option_type: 'C',
            side: 'sell' as const,
            occ: occCs,
            quantity: contracts,
            current_bid: csQ?.bid ?? null,
            current_ask: csQ?.ask ?? null,
            current_mid: csQ ? Math.round(((csQ.bid + csQ.ask) / 2) * 100) / 100 : null,
          },
          {
            type: 'call_long',
            label: 'Call Long',
            strike: cl,
            option_type: 'C',
            side: 'buy' as const,
            occ: occCl,
            quantity: contracts,
            current_bid: clQ?.bid ?? null,
            current_ask: clQ?.ask ?? null,
            current_mid: clQ ? Math.round(((clQ.bid + clQ.ask) / 2) * 100) / 100 : null,
          },
        ]

        // P&L math
        let currentDebit: number | null = null
        let paperPnl: number | null = null
        let spreadPnlPerContract: number | null = null
        let pctProfitCaptured: number | null = null

        if (hasQuotes && psQ && plQ && csQ && clQ) {
          currentDebit =
            Math.round(
              (psQ.ask + csQ.ask - plQ.bid - clQ.bid) * 10000,
            ) / 10000
          currentDebit = Math.max(0, currentDebit)
          spreadPnlPerContract =
            Math.round((entryCredit - currentDebit) * 10000) / 10000
          paperPnl =
            Math.round(spreadPnlPerContract * 100 * contracts * 100) / 100
          pctProfitCaptured =
            entryCredit > 0
              ? Math.round(
                  ((entryCredit - currentDebit) / entryCredit) * 10000,
                ) / 100
              : 0
        }

        // Key metrics
        const maxProfit =
          Math.round(entryCredit * 100 * contracts * 100) / 100
        const maxLoss = Math.round(collateral * 100) / 100
        const putBreakeven =
          Math.round((ps - entryCredit) * 10000) / 10000
        const callBreakeven =
          Math.round((cs + entryCredit) * 10000) / 10000
        const distanceToPut =
          spyPrice != null
            ? Math.round((spyPrice - ps) * 100) / 100
            : null
        const distanceToCall =
          spyPrice != null
            ? Math.round((cs - spyPrice) * 100) / 100
            : null

        // PT tier
        const currentPtPct = ptTier.pct
        const ptTargetPrice =
          Math.round(entryCredit * (1 - currentPtPct) * 10000) / 10000
        const ptTargetDollar =
          Math.round(entryCredit * currentPtPct * 100 * contracts * 100) / 100
        let pctToPt: number | null = null
        if (currentDebit != null) {
          const remaining = currentDebit - ptTargetPrice
          const totalToGo = entryCredit - ptTargetPrice
          pctToPt =
            totalToGo > 0
              ? Math.round((remaining / totalToGo) * 10000) / 100
              : 0
        }

        // Sandbox accounts from position JSON
        const sandboxAccounts: Array<{
          name: string
          order_id: number | string | null
          contracts: number
          entry_credit_total: number
          current_debit_total: number | null
          calculated_pnl: number | null
          tradier_pnl: number | null
          tradier_cost_basis: number | null
          tradier_market_value: number | null
        }> = []

        // Paper account entry
        sandboxAccounts.push({
          name: 'Paper',
          order_id: null,
          contracts,
          entry_credit_total: maxProfit,
          current_debit_total:
            currentDebit != null
              ? Math.round(currentDebit * 100 * contracts * 100) / 100
              : null,
          calculated_pnl: paperPnl,
          tradier_pnl: null,
          tradier_cost_basis: null,
          tradier_market_value: null,
        })

        // Parse sandbox order IDs and add per-account entries
        let sandboxOrderIds: Record<string, unknown> | null = null
        try {
          sandboxOrderIds = r.sandbox_order_id
            ? JSON.parse(r.sandbox_order_id)
            : null
        } catch {
          sandboxOrderIds = null
        }

        if (sandboxOrderIds && typeof sandboxOrderIds === 'object') {
          for (const [name, val] of Object.entries(sandboxOrderIds)) {
            const isNew = typeof val === 'object' && val !== null && 'order_id' in (val as Record<string, unknown>)
            const orderId = isNew ? (val as { order_id: string | number }).order_id : val
            const acctContracts = isNew ? (val as { contracts?: number }).contracts ?? contracts : contracts

            let calcPnl: number | null = null
            if (currentDebit != null) {
              calcPnl =
                Math.round(
                  (entryCredit - currentDebit) * 100 * acctContracts * 100,
                ) / 100
            }

            sandboxAccounts.push({
              name,
              order_id: orderId as string | number | null,
              contracts: acctContracts,
              entry_credit_total:
                Math.round(entryCredit * 100 * acctContracts * 100) / 100,
              current_debit_total:
                currentDebit != null
                  ? Math.round(currentDebit * 100 * acctContracts * 100) / 100
                  : null,
              calculated_pnl: calcPnl,
              tradier_pnl: null,
              tradier_cost_basis: null,
              tradier_market_value: null,
            })
          }
        }

        return {
          position_id: r.position_id,
          ticker,
          expiration,
          put_short_strike: ps,
          put_long_strike: pl,
          put_credit: putCredit,
          call_short_strike: cs,
          call_long_strike: cl,
          call_credit: callCredit,
          contracts,
          spread_width: num(r.spread_width),
          total_credit: entryCredit,
          collateral_required: collateral,
          underlying_at_entry: num(r.underlying_at_entry),
          open_time: r.open_time,
          spy_price: spyPrice,
          legs,
          entry_credit: entryCredit,
          current_debit: currentDebit,
          spread_pnl_per_contract: spreadPnlPerContract,
          paper_pnl: paperPnl,
          max_profit: maxProfit,
          max_loss: maxLoss,
          put_breakeven: putBreakeven,
          call_breakeven: callBreakeven,
          distance_to_put: distanceToPut,
          distance_to_call: distanceToCall,
          pct_profit_captured: pctProfitCaptured,
          current_pt_tier: ptTier.label,
          current_pt_pct: Math.round(currentPtPct * 100),
          pt_target_price: ptTargetPrice,
          pt_target_dollar: ptTargetDollar,
          pct_to_pt: pctToPt,
          progress: {
            max_loss: -maxLoss,
            current: paperPnl,
            zero: 0,
            pt_target: ptTargetDollar,
            max_profit: maxProfit,
          },
          sandbox_accounts: sandboxAccounts,
        }
      }),
    )

    return NextResponse.json({
      positions,
      tradier_connected: isConfigured(),
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: message }, { status: 500 })
  }
}
