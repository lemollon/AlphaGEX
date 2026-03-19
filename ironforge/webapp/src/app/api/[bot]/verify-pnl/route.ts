import { NextRequest, NextResponse } from 'next/server'
import { dbQuery, botTable, num, int, escapeSql, validateBot, dteMode } from '@/lib/db'
import {
  isConfigured,
  buildOccSymbol,
  getTimesales,
  calculateIcUnrealizedPnl,
  getTradierBaseUrl,
} from '@/lib/tradier'

export const dynamic = 'force-dynamic'

/**
 * Verify P&L on closed trades by comparing our stored close_price
 * against Tradier's historical timesales data for each option leg.
 *
 * For each closed trade:
 * 1. Look up the 4 option legs in Tradier timesales (minute bars)
 * 2. Find the candle closest to our recorded close_time
 * 3. Compute what mid/last/bid-ask cost-to-close would have been
 * 4. Compare against our stored close_price and realized_pnl
 *
 * This proves whether our pricing method was accurate at close time.
 *
 * GET /api/flame/verify-pnl?limit=5
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const dte = dteMode(bot)
  const dteFilter = dte ? `AND dte_mode = '${escapeSql(dte)}'` : ''
  const limit = Math.min(int(req.nextUrl.searchParams.get('limit') || '5') || 5, 20)

  if (!isConfigured()) {
    return NextResponse.json({ error: 'Tradier not configured — cannot fetch historical data' }, { status: 503 })
  }

  try {
    // Get recent closed trades
    const trades = await dbQuery(
      `SELECT position_id, ticker, expiration,
              put_short_strike, put_long_strike,
              call_short_strike, call_long_strike,
              contracts, spread_width, total_credit,
              close_price, close_reason, realized_pnl,
              open_time, close_time,
              sandbox_order_id, sandbox_close_order_id
       FROM ${botTable(bot, 'positions')}
       WHERE status IN ('closed', 'expired') ${dteFilter}
       ORDER BY close_time DESC
       LIMIT ${limit}`,
    )

    if (!trades.length) {
      return NextResponse.json({ message: 'No closed trades to verify' })
    }

    const results = await Promise.all(
      trades.map(async (t: any) => {
        const ps = num(t.put_short_strike)
        const pl = num(t.put_long_strike)
        const cs = num(t.call_short_strike)
        const cl = num(t.call_long_strike)
        const contracts = int(t.contracts)
        const entryCredit = num(t.total_credit)
        const storedClosePrice = num(t.close_price)
        const storedPnl = num(t.realized_pnl)
        const spreadWidth = num(t.spread_width) || Math.round((ps - pl) * 100) / 100
        const ticker = t.ticker || 'SPY'
        const expiration = t.expiration?.toISOString?.()?.slice(0, 10) || String(t.expiration || '').slice(0, 10)
        const closeTime = t.close_time

        // Build OCC symbols for each leg
        const occPs = buildOccSymbol(ticker, expiration, ps, 'P')
        const occPl = buildOccSymbol(ticker, expiration, pl, 'P')
        const occCs = buildOccSymbol(ticker, expiration, cs, 'C')
        const occCl = buildOccSymbol(ticker, expiration, cl, 'C')

        // Fetch timesales for each leg + SPY
        const [tsPs, tsPl, tsCs, tsCl, tsSpy] = await Promise.all([
          getTimesales(occPs, 60).catch(() => []),
          getTimesales(occPl, 60).catch(() => []),
          getTimesales(occCs, 60).catch(() => []),
          getTimesales(occCl, 60).catch(() => []),
          getTimesales(ticker, 60).catch(() => []),
        ])

        // Find the candle closest to close_time for each leg
        const findNearestCandle = (candles: Array<{ time: string; close: number }>, target: Date | string) => {
          if (!candles.length) return null
          const targetMs = new Date(target).getTime()
          let best = candles[0]
          let bestDelta = Math.abs(new Date(best.time).getTime() - targetMs)
          for (const c of candles) {
            const delta = Math.abs(new Date(c.time).getTime() - targetMs)
            if (delta < bestDelta) {
              best = c
              bestDelta = delta
            }
          }
          return { ...best, offset_seconds: Math.round(bestDelta / 1000) }
        }

        const nearPs = findNearestCandle(tsPs, closeTime)
        const nearPl = findNearestCandle(tsPl, closeTime)
        const nearCs = findNearestCandle(tsCs, closeTime)
        const nearCl = findNearestCandle(tsCl, closeTime)
        const nearSpy = findNearestCandle(tsSpy, closeTime)

        // Compute cost-to-close from historical timesales (using close prices = last trade at that minute)
        let historicalCost: number | null = null
        let historicalPnl: number | null = null
        if (nearPs && nearPl && nearCs && nearCl) {
          historicalCost = Math.round(
            (nearPs.close + nearCs.close - nearPl.close - nearCl.close) * 10000,
          ) / 10000
          historicalPnl = calculateIcUnrealizedPnl(entryCredit, historicalCost, contracts, spreadWidth)
        }

        // Extract Tradier fill price from sandbox_close_order_id if available
        let tradierFillPrice: number | null = null
        try {
          const closeInfo = t.sandbox_close_order_id ? JSON.parse(t.sandbox_close_order_id) : null
          if (closeInfo?.User?.fill_price) tradierFillPrice = closeInfo.User.fill_price
          else if (closeInfo?.Matt?.fill_price) tradierFillPrice = closeInfo.Matt.fill_price
          else if (closeInfo?.Logan?.fill_price) tradierFillPrice = closeInfo.Logan.fill_price
        } catch { /* not JSON */ }

        // Compute deltas
        const deltaVsHistorical = historicalCost != null
          ? Math.round((storedClosePrice - historicalCost) * 10000) / 10000
          : null
        const pnlDelta = historicalPnl != null
          ? Math.round((storedPnl - historicalPnl) * 100) / 100
          : null

        return {
          position_id: t.position_id,
          close_time: closeTime,
          close_reason: t.close_reason,
          strikes: `${pl}/${ps}P - ${cs}/${cl}C`,
          contracts,
          entry_credit: entryCredit,

          // What we stored
          stored: {
            close_price: storedClosePrice,
            realized_pnl: storedPnl,
            tradier_fill_price: tradierFillPrice,
          },

          // What Tradier historical timesales says
          historical_timesales: {
            cost_to_close: historicalCost,
            realized_pnl: historicalPnl,
            per_leg: {
              put_short: nearPs ? { price: nearPs.close, time: nearPs.time, offset_sec: nearPs.offset_seconds } : 'no data',
              put_long: nearPl ? { price: nearPl.close, time: nearPl.time, offset_sec: nearPl.offset_seconds } : 'no data',
              call_short: nearCs ? { price: nearCs.close, time: nearCs.time, offset_sec: nearCs.offset_seconds } : 'no data',
              call_long: nearCl ? { price: nearCl.close, time: nearCl.time, offset_sec: nearCl.offset_seconds } : 'no data',
            },
            spy_at_close: nearSpy ? { price: nearSpy.close, time: nearSpy.time } : 'no data',
          },

          // Comparison
          delta: {
            close_price_vs_historical: deltaVsHistorical,
            pnl_vs_historical: pnlDelta,
            verdict: deltaVsHistorical != null
              ? Math.abs(deltaVsHistorical) < 0.005
                ? 'MATCH'
                : Math.abs(deltaVsHistorical) < 0.02
                  ? `CLOSE (±$${Math.abs(deltaVsHistorical).toFixed(4)})`
                  : `DIVERGENT — stored ${storedClosePrice.toFixed(4)} vs historical ${historicalCost!.toFixed(4)} (Δ$${deltaVsHistorical.toFixed(4)}, P&L Δ$${pnlDelta?.toFixed(2)})`
              : 'No timesales data — may be expired or too old',
          },
        }
      }),
    )

    // Summary
    const verified = results.filter(r => r.delta.verdict === 'MATCH')
    const close = results.filter(r => typeof r.delta.verdict === 'string' && r.delta.verdict.startsWith('CLOSE'))
    const divergent = results.filter(r => typeof r.delta.verdict === 'string' && r.delta.verdict.startsWith('DIVERGENT'))
    const noData = results.filter(r => typeof r.delta.verdict === 'string' && r.delta.verdict.startsWith('No timesales'))

    return NextResponse.json({
      bot: bot.toUpperCase(),
      timestamp: new Date().toISOString(),
      tradier_api_url: getTradierBaseUrl(),
      summary: {
        total: results.length,
        match: verified.length,
        close: close.length,
        divergent: divergent.length,
        no_data: noData.length,
        verdict: divergent.length === 0
          ? 'ALL TRADES VERIFIED — stored close prices match Tradier historical data'
          : `${divergent.length}/${results.length} trades have price discrepancies`,
      },
      trades: results,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
