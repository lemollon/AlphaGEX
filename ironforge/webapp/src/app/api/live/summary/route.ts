import { NextResponse } from 'next/server'
import { getLiveSummary } from '@/lib/live/summary'

export const dynamic = 'force-dynamic'

/**
 * Customer Live page — full-page payload (hero state, account, market
 * conditions, intraday equity). Polled at ~60s by the client.
 */
export async function GET() {
  try {
    return NextResponse.json(await getLiveSummary())
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
