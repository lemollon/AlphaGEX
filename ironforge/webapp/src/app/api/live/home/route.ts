import { NextResponse } from 'next/server'
import { getHomeData } from '@/lib/live/home'

export const dynamic = 'force-dynamic'

/**
 * Customer Home dashboard — wealth snapshot + recent trades payload.
 * Polled at ~60s by the client alongside /api/live/summary.
 */
export async function GET() {
  try {
    return NextResponse.json(await getHomeData())
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
