/**
 * Intraday OHLCV bars for the Builder tab's CandleChart.
 *
 * Defaults to SPY 1-min bars for the last 60 minutes. Reuses the existing
 * `getTimesales` helper in tradier.ts. Broken out from the snapshot route
 * so this can be polled independently (e.g., every 60s for chart refresh
 * while the snapshot refreshes every 30s for quotes/greeks/MTM).
 *
 * Query params:
 *   symbol  (default: SPY)
 *   minutes (default: 60, max: 390 = one full session)
 *
 * Response:
 *   { candles: [{time, open, high, low, close, volume}, ...] }
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import { getTimesales, isConfigured } from '@/lib/tradier'

export const dynamic = 'force-dynamic'

export async function GET(
  req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })

  const symbol = req.nextUrl.searchParams.get('symbol') || 'SPY'
  const minutesParam = parseInt(req.nextUrl.searchParams.get('minutes') || '60', 10)
  const minutes = Number.isFinite(minutesParam)
    ? Math.max(10, Math.min(390, minutesParam))
    : 60

  if (!isConfigured()) {
    return NextResponse.json({ candles: [], tradier_connected: false })
  }

  try {
    const candles = await getTimesales(symbol, minutes)
    return NextResponse.json({
      symbol,
      minutes,
      candles,
      tradier_connected: true,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    // Tradier transient failures shouldn't 500 the chart; return empty so
    // the UI shows "no data yet" instead of an error state.
    console.warn(`[builder/candles] ${bot} ${symbol}: ${msg}`)
    return NextResponse.json({ symbol, minutes, candles: [], tradier_connected: true, error: msg })
  }
}
