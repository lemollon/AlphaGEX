/**
 * Live risk-signal feed for the Market Pulse tab.
 *
 *   GET /api/{bot}/risk-signals
 *
 * Returns four beginner-friendly tiles:
 *   - Premium Quality (IV Rank of VIX over 52-week)
 *   - Volatility Pulse (ΔVIX over 15m / 1h / 4h)
 *   - Strike Distance (SDs between SPY and each short strike)
 *   - Today's Move vs Expected (realized range / option-priced range)
 *
 * Read-only: no DB writes, no Tradier order placement, no scanner impact.
 * Available for all bots — the open-position lookup is bot-aware so each
 * bot's Market Pulse tab reflects its own live position.
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
  try {
    const signals = await getRiskSignals(bot)
    return NextResponse.json(signals)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
