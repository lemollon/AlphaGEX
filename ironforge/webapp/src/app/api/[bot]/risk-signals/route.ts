/**
 * Live risk-signal feed for the SPARK Market Pulse tab (Commit S1).
 *
 *   GET /api/spark/risk-signals
 *
 * Returns four beginner-friendly tiles:
 *   - Premium Quality (IV Rank of VIX over 52-week)
 *   - Volatility Pulse (ΔVIX over 15m / 1h / 4h)
 *   - Strike Distance (SDs between SPY and each short strike)
 *   - Today's Move vs Expected (realized range / option-priced range)
 *
 * SPARK-only. Other bots return an empty tiles array.
 * Read-only: no DB writes, no Tradier order placement, no scanner impact.
 */
import { NextRequest, NextResponse } from 'next/server'
import { validateBot } from '@/lib/db'
import { getRiskSignals } from '@/lib/risk-signals'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: { bot: string } },
) {
  const bot = validateBot(params.bot)
  if (!bot) return NextResponse.json({ error: 'Invalid bot' }, { status: 400 })
  if (bot !== 'spark') {
    return NextResponse.json({
      generated_at: new Date().toISOString(),
      spy_price: null,
      vix: null,
      has_open_position: false,
      tiles: [],
      note: 'Market Pulse is SPARK-only.',
    })
  }
  try {
    const signals = await getRiskSignals()
    return NextResponse.json(signals)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
