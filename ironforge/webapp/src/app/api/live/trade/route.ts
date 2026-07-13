import { NextRequest, NextResponse } from 'next/server'
import { getLiveTrade } from '@/lib/live/summary'
import { resolveLiveViewer } from '@/lib/live/viewer'

export const dynamic = 'force-dynamic'

/**
 * Customer Live page — active-trade state with live unrealized P&L and the
 * mini sparkline series. Polled at ~30s by the client while the page is open.
 * Account-aware: ?account=spark|spark2, authorized server-side per viewer
 * (operators see all; customers only their mapped bots; anonymous = spark).
 */
export async function GET(req: NextRequest) {
  try {
    const viewer = await resolveLiveViewer(req)
    if (!viewer.bot) {
      // Viewer has no live account (fresh signup / anonymous): empty state,
      // never another account's data.
      return NextResponse.json({ empty: true, viewer })
    }
    return NextResponse.json(await getLiveTrade(viewer.bot))
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
