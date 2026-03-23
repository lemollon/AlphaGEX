import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  getIcMarkToMarket,
  isConfigured,
  buildOccSymbol,
  getRawQuotes,
  getTimesales,
  getSandboxAccountPositions,
  calculateIcUnrealizedPnl,
  getTradierBaseUrl,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * Deep diagnostic: dumps raw Tradier API responses, all pricing methods,
 * and Tradier sandbox position data side-by-side so you can see exactly
 * where P&L numbers diverge.
 *
 * GET /api/flame/diagnose-pnl
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
    // 1. Open positions from DB
    const positionRows = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, total_credit, spread_width, open_time,
              sandbox_order_id
       FROM ${botTable(bot, 'positions')}
       WHERE status = 'open' ${dteFilter}
       ORDER BY open_time DESC`,
    )

    // 2. Latest equity snapshot (scanner's last calculation)
    const snapshotRows = await dbQuery(
      `SELECT snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note
       FROM ${botTable(bot, 'equity_snapshots')}
       ${dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''}
       ORDER BY snapshot_time DESC
       LIMIT 1`,
    )

    // 3. Load sandbox accounts (only sandbox — never expose production keys in diagnostics)
    let sandboxAccounts: Array<{ name: string; apiKey: string }> = []
    try {
      const acctRows = await dbQuery(
        `SELECT person, api_key FROM ironforge_accounts WHERE is_active = TRUE AND type = 'sandbox' ORDER BY id`,
      )
      sandboxAccounts = acctRows
        .filter((r: any) => r.api_key)
        .map((r: any) => ({ name: r.person, apiKey: r.api_key.trim() }))
    } catch { /* no accounts table */ }

    if (!positionRows.length) {
      return NextResponse.json({
        diagnosis: 'No open positions',
        tradier_api_url: getTradierBaseUrl(),
        tradier_connected: isConfigured(),
        scanner_snapshot: snapshotRows[0] || null,
      })
    }

    // 4. For each position, get ALL data sources
    const results = await Promise.all(
      positionRows.map(async (r: any) => {
        const ps = num(r.put_short_strike)
        const pl = num(r.put_long_strike)
        const cs = num(r.call_short_strike)
        const cl = num(r.call_long_strike)
        const contracts = int(r.contracts)
        const entryCredit = num(r.total_credit)
        const spreadWidth = num(r.spread_width) || Math.round((ps - pl) * 100) / 100
        const ticker = r.ticker || 'SPY'
        const expiration = r.expiration?.toISOString?.()?.slice(0, 10) || (r.expiration ? String(r.expiration).slice(0, 10) : '')

        const occPs = buildOccSymbol(ticker, expiration, ps, 'P')
        const occPl = buildOccSymbol(ticker, expiration, pl, 'P')
        const occCs = buildOccSymbol(ticker, expiration, cs, 'C')
        const occCl = buildOccSymbol(ticker, expiration, cl, 'C')
        const occSymbols = [occPs, occPl, occCs, occCl]

        // ─── SOURCE 1: Raw Tradier API quotes (all fields) ───
        const rawQuotes = isConfigured()
          ? await getRawQuotes([...occSymbols, ticker])
          : {}

        // Extract per-leg raw data
        const legNames = ['put_short', 'put_long', 'call_short', 'call_long'] as const
        const legOccs = [occPs, occPl, occCs, occCl]
        const rawLegs: Record<string, unknown> = {}
        for (let i = 0; i < 4; i++) {
          const raw = rawQuotes[legOccs[i]]
          if (raw) {
            rawLegs[legNames[i]] = {
              symbol: raw.symbol,
              bid: raw.bid,
              ask: raw.ask,
              last: raw.last,
              mid: raw.bid != null && raw.ask != null
                ? Math.round(((Number(raw.bid) + Number(raw.ask)) / 2) * 10000) / 10000
                : null,
              bid_date: raw.bid_date,
              ask_date: raw.ask_date,
              trade_date: raw.trade_date,
              volume: raw.volume,
              open_interest: raw.open_interest,
              description: raw.description,
            }
          } else {
            rawLegs[legNames[i]] = { error: 'No quote returned', occ: legOccs[i] }
          }
        }

        const spotRaw = rawQuotes[ticker]
        const rawSpot = spotRaw ? {
          last: spotRaw.last,
          bid: spotRaw.bid,
          ask: spotRaw.ask,
          trade_date: spotRaw.trade_date,
        } : null

        // ─── SOURCE 2: getIcMarkToMarket (position-monitor method) ───
        let mtmResult: Record<string, unknown> = { error: 'Not configured' }
        if (isConfigured()) {
          const mtm = await getIcMarkToMarket(ticker, expiration, ps, pl, cs, cl, entryCredit)
          if (mtm) {
            const pnlMid = calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close_mid, contracts, spreadWidth)
            const pnlLast = calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close_last, contracts, spreadWidth)
            const pnlBidAsk = calculateIcUnrealizedPnl(entryCredit, mtm.cost_to_close, contracts, spreadWidth)
            mtmResult = {
              cost_to_close_bidask: mtm.cost_to_close,
              cost_to_close_mid: mtm.cost_to_close_mid,
              cost_to_close_last: mtm.cost_to_close_last,
              last_prices_used: mtm.last_prices,
              pnl_using_bidask: pnlBidAsk,
              pnl_using_mid: pnlMid,
              pnl_using_last: pnlLast,
              spot_price: mtm.spot_price,
              quote_age_seconds: mtm.quote_age_seconds,
              validation_issues: mtm.validation_issues || [],
            }
          } else {
            mtmResult = { error: 'getIcMarkToMarket returned null' }
          }
        }

        // ─── SOURCE 3: Tradier sandbox account positions ───
        let sandboxOrderIds: Record<string, any> | null = null
        try {
          sandboxOrderIds = r.sandbox_order_id ? JSON.parse(r.sandbox_order_id) : null
        } catch { sandboxOrderIds = null }

        const sandboxData = await Promise.all(
          sandboxAccounts.map(async (acct) => {
            const acctInfo = sandboxOrderIds?.[acct.name]
            const acctContracts = typeof acctInfo === 'object' && acctInfo?.contracts
              ? int(acctInfo.contracts)
              : contracts

            let positionData: Record<string, unknown> = { error: 'No positions found' }
            try {
              const positions = await getSandboxAccountPositions(acct.apiKey, occSymbols)
              if (positions.length > 0) {
                const totalGainLoss = positions.reduce((s, p) => s + p.gain_loss, 0)
                const totalCostBasis = positions.reduce((s, p) => s + p.cost_basis, 0)
                const totalMarketValue = positions.reduce((s, p) => s + p.market_value, 0)
                positionData = {
                  total_gain_loss: Math.round(totalGainLoss * 100) / 100,
                  total_cost_basis: Math.round(totalCostBasis * 100) / 100,
                  total_market_value: Math.round(totalMarketValue * 100) / 100,
                  per_leg: positions.map(p => ({
                    symbol: p.symbol,
                    quantity: p.quantity,
                    cost_basis: p.cost_basis,
                    market_value: p.market_value,
                    gain_loss: p.gain_loss,
                    gain_loss_percent: p.gain_loss_percent,
                  })),
                }
              }
            } catch (err: unknown) {
              positionData = { error: err instanceof Error ? err.message : String(err) }
            }

            return {
              account_name: acct.name,
              contracts: acctContracts,
              tradier_positions_api: positionData,
            }
          }),
        )

        // ─── Compute all P&L methods for comparison ───
        const parse = (v: unknown) => typeof v === 'number' ? v : parseFloat(String(v || '0'))
        const psB = parse((rawLegs.put_short as any)?.bid)
        const psA = parse((rawLegs.put_short as any)?.ask)
        const psL = parse((rawLegs.put_short as any)?.last)
        const psM = parse((rawLegs.put_short as any)?.mid)
        const plB = parse((rawLegs.put_long as any)?.bid)
        const plA = parse((rawLegs.put_long as any)?.ask)
        const plL = parse((rawLegs.put_long as any)?.last)
        const plM = parse((rawLegs.put_long as any)?.mid)
        const csB = parse((rawLegs.call_short as any)?.bid)
        const csA = parse((rawLegs.call_short as any)?.ask)
        const csL = parse((rawLegs.call_short as any)?.last)
        const csM = parse((rawLegs.call_short as any)?.mid)
        const clB = parse((rawLegs.call_long as any)?.bid)
        const clA = parse((rawLegs.call_long as any)?.ask)
        const clL = parse((rawLegs.call_long as any)?.last)
        const clM = parse((rawLegs.call_long as any)?.mid)

        const costMid = Math.round((psM + csM - plM - clM) * 10000) / 10000
        const costLast = Math.round(((psL > 0 ? psL : psM) + (csL > 0 ? csL : csM) - (plL > 0 ? plL : plM) - (clL > 0 ? clL : clM)) * 10000) / 10000
        const costBidAsk = Math.round((psA + csA - plB - clB) * 10000) / 10000

        return {
          position_id: r.position_id,
          ticker,
          expiration,
          strikes: `${pl}/${ps}P - ${cs}/${cl}C`,
          contracts,
          entry_credit: entryCredit,
          spread_width: spreadWidth,

          // All 3 cost-to-close methods with P&L
          pricing_comparison: {
            bid_ask_worst_case: {
              cost: costBidAsk,
              pnl_per_contract: Math.round((entryCredit - Math.min(Math.max(0, costBidAsk), spreadWidth)) * 10000) / 10000,
              pnl_total: calculateIcUnrealizedPnl(entryCredit, costBidAsk, contracts, spreadWidth),
              formula: `PS_ask(${psA}) + CS_ask(${csA}) - PL_bid(${plB}) - CL_bid(${clB})`,
            },
            mid_price: {
              cost: costMid,
              pnl_per_contract: Math.round((entryCredit - Math.min(Math.max(0, costMid), spreadWidth)) * 10000) / 10000,
              pnl_total: calculateIcUnrealizedPnl(entryCredit, costMid, contracts, spreadWidth),
              formula: `PS_mid(${psM}) + CS_mid(${csM}) - PL_mid(${plM}) - CL_mid(${clM})`,
            },
            last_trade: {
              cost: costLast,
              pnl_per_contract: Math.round((entryCredit - Math.min(Math.max(0, costLast), spreadWidth)) * 10000) / 10000,
              pnl_total: calculateIcUnrealizedPnl(entryCredit, costLast, contracts, spreadWidth),
              formula: `PS_last(${psL > 0 ? psL : psM + '*'}) + CS_last(${csL > 0 ? csL : csM + '*'}) - PL_last(${plL > 0 ? plL : plM + '*'}) - CL_last(${clL > 0 ? clL : clM + '*'})`,
              note: 'Values marked with * fell back to mid (no last trade)',
            },
          },

          // Raw per-leg data from Tradier API
          raw_tradier_quotes: rawLegs,
          raw_spot: rawSpot,

          // getIcMarkToMarket output (what position-monitor uses)
          position_monitor_method: mtmResult,

          // Tradier sandbox positions API (what the portfolio shows)
          sandbox_accounts: sandboxData,
        }
      }),
    )

    // ─── Tradier timesales (last 10 minutes of SPY minute bars) ───
    // Compare latest candle close to the quote's "last" field.
    // If quote.last lags the timesales close, quotes are delayed.
    let timesalesData: Record<string, unknown> = {}
    if (isConfigured()) {
      try {
        const candles = await getTimesales('SPY', 10)
        const quoteSpot = results[0]?.raw_spot as any
        const quoteLast = quoteSpot?.last ? Number(quoteSpot.last) : null
        const latestCandle = candles.length > 0 ? candles[candles.length - 1] : null

        timesalesData = {
          candles,
          latest_candle: latestCandle,
          quote_last: quoteLast,
          delta: latestCandle && quoteLast != null
            ? Math.round((Number(latestCandle.close) - quoteLast) * 100) / 100
            : null,
          verdict: latestCandle && quoteLast != null
            ? Math.abs(Number(latestCandle.close) - quoteLast) > 0.50
              ? `STALE — quote SPY $${quoteLast} vs timesales $${latestCandle.close} (${latestCandle.time})`
              : `OK — quote SPY $${quoteLast} ≈ timesales $${latestCandle.close}`
            : 'No data to compare',
        }
      } catch (err: unknown) {
        timesalesData = { error: err instanceof Error ? err.message : String(err) }
      }
    }

    // ─── Historical equity snapshots (last 30 from today) ───
    let historicalSnapshots: Array<Record<string, unknown>> = []
    try {
      const snapRows = await dbQuery(
        `SELECT snapshot_time, balance, realized_pnl, unrealized_pnl, open_positions, note
         FROM ${botTable(bot, 'equity_snapshots')}
         ${dte ? `WHERE dte_mode = '${escapeSql(dte)}'` : ''}
         ORDER BY snapshot_time DESC
         LIMIT 30`,
      )
      historicalSnapshots = snapRows.map((r: any) => ({
        time: r.snapshot_time,
        balance: num(r.balance),
        realized_pnl: num(r.realized_pnl),
        unrealized_pnl: num(r.unrealized_pnl),
        open_positions: int(r.open_positions),
        note: r.note,
      })).reverse()  // oldest first
    } catch { /* table may not exist */ }

    return NextResponse.json({
      bot: bot.toUpperCase(),
      timestamp: new Date().toISOString(),
      tradier_api_url: getTradierBaseUrl(),
      tradier_connected: isConfigured(),

      // Cross-check: compare /markets/quotes vs /markets/timesales
      spy_timesales_vs_quote: timesalesData,

      // Historical scanner snapshots (unrealized P&L trail)
      equity_snapshot_history: historicalSnapshots,

      // Per-position deep dive
      positions: results,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
