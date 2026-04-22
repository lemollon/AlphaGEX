/**
 * Intraday OHLCV bars for the Builder tab's CandleChart.
 *
 * Defaults to SPY 5-min bars × 80 bars = ~1 full RTH day. This matches
 * SpreadWorks' density (their default is 15-min × 80 bars = 3 RTH days);
 * we use 5-min because SPARK is 1DTE so the operator cares about intraday
 * price action, not multi-day context.
 *
 * Tradier's `session_filter='open'` filters out pre/post market bars, so
 * when the market is closed the chart naturally shows the last live
 * session's bars instead of after-hours noise tacked onto the end.
 *
 * Broken out from the snapshot route so this can be polled independently
 * (every 60s for chart refresh while the snapshot refreshes every 30s for
 * quotes/greeks/MTM).
 *
 * Query params:
 *   symbol   (default: SPY)
 *   interval (default: 5min, one of 1min|5min|15min)
 *   bars     (default: 80, max: 390)
 *
 * Response:
 *   { candles: [{time, open, high, low, close, volume}, ...] }
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import { getTimesales, isConfigured } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

type IntervalStr = '1min' | '5min' | '15min'

function parseInterval(raw: string | null): IntervalStr {
  if (raw === '1min' || raw === '5min' || raw === '15min') return raw
  return '5min'
}

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const symbol = req.nextUrl.searchParams.get('symbol') || 'SPY'
  const interval = parseInterval(req.nextUrl.searchParams.get('interval'))

  // Accept both `bars` (new) and `minutes` (legacy) params; `bars` wins.
  // `bars` is the count of candles we want back from the tail.
  const barsRaw = req.nextUrl.searchParams.get('bars')
    ?? req.nextUrl.searchParams.get('minutes')
    ?? '80'
  const barsParam = parseInt(barsRaw, 10)
  const bars = Number.isFinite(barsParam)
    ? Math.max(10, Math.min(390, barsParam))
    : 80

  if (!isConfigured()) {
    return NextResponse.json({ candles: [], tradier_connected: false })
  }

  try {
    // session='open' → RTH only. After-hours this freezes at the last
    // live candle of the most recent session, which is what the operator
    // asked for ("outside of market hours it should stick to results of
    // last live day").
    const candles = await getTimesales(symbol, bars, 'open', interval)
    return NextResponse.json({
      symbol,
      interval,
      bars,
      candles,
      tradier_connected: true,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Tradier transient failures shouldn't 500 the chart; return empty so
    // the UI shows "no data yet" instead of an error state.
    console.warn(`[builder/candles] ${bot} ${symbol}: ${msg}`)
    return NextResponse.json({ symbol, interval, bars, candles: [], tradier_connected: true, error: msg })
  }
}
