import { NextResponse } from 'next/server'
import { getTrackRecord } from '@/lib/live/track-record'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * PUBLIC track record — no session, no viewer scoping, by design.
 *
 * Safe to serve anonymously because getTrackRecord() reads only CLOSED trades:
 * realised P&L, win rate, per-day aggregates. It returns no account balance, no
 * open position, and no per-customer state. Do not widen it to anything that
 * reads ironforge_accounts or a live broker balance.
 */
export async function GET() {
  try {
    const data = await getTrackRecord(25)
    return NextResponse.json(data, {
      // Cheap to recompute but hit by every anonymous visitor; a short cache keeps
      // a marketing traffic spike off the trading database.
      headers: { 'Cache-Control': 'public, max-age=300, stale-while-revalidate=600' },
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
