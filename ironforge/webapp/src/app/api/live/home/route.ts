import { NextRequest, NextResponse } from 'next/server'
import { getHomeData } from '@/lib/live/home'
import { resolveLiveViewer } from '@/lib/live/viewer'

export const dynamic = 'force-dynamic'

/**
 * Customer Home dashboard payload (wealth snapshot, daily brief, recent
 * trades). Polled at ~60s by the client.
 * Account-aware: ?account=spark|spark2, authorized server-side per viewer
 * (operators see all; customers only their mapped bots; anonymous = spark).
 */
export async function GET(req: NextRequest) {
  try {
    const viewer = await resolveLiveViewer(req)
    return NextResponse.json(await getHomeData(viewer.bot))
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
