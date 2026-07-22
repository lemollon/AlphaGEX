import { NextRequest, NextResponse } from 'next/server'
import { getLiveSummary } from '@/lib/live/summary'
import { resolveLiveViewer } from '@/lib/live/viewer'

export const dynamic = 'force-dynamic'

/**
 * Customer Live page — full-page payload (hero state, account, market
 * conditions, intraday equity). Polled at ~60s by the client.
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
    const summary = await getLiveSummary(viewer.bot, {
      allowAggregate: viewer.isOperator,
      person: viewer.person,
    })
    return NextResponse.json({ ...summary, viewer })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
