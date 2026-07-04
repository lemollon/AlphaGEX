import { NextResponse } from 'next/server'
import { getLiveTrade } from '@/lib/live/summary'

export const dynamic = 'force-dynamic'

/**
 * Customer Live page — active-trade state with live unrealized P&L and the
 * mini sparkline series. Polled at ~30s by the client while the page is open.
 */
export async function GET() {
  try {
    return NextResponse.json(await getLiveTrade())
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
