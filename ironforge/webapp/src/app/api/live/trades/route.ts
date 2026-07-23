import { NextRequest, NextResponse } from 'next/server'
import { resolveLiveViewer } from '@/lib/live/viewer'
import { getCustomerTrades } from '@/lib/live/trades-history'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Customer Trade History — the viewer's own closed trades across owned strategies.
 * Authorization is server-side via resolveLiveViewer: a viewer with no mapped
 * bots gets { empty: true }, never another account's data.
 */
export async function GET(req: NextRequest) {
  try {
    const viewer = await resolveLiveViewer(req)
    if (viewer.allowedBots.length === 0) {
      return NextResponse.json({ empty: true, viewer })
    }
    const trades = await getCustomerTrades(viewer.allowedBots, viewer.persons, viewer.paperBots)
    return NextResponse.json({ trades, viewer })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
