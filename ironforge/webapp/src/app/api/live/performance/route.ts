import { NextRequest, NextResponse } from 'next/server'
import { resolveLiveViewer } from '@/lib/live/viewer'
import { getPerformance } from '@/lib/live/performance'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Customer Performance payload — the viewer's all-time history combined across
 * every bot they own. Authorization is server-side via resolveLiveViewer: a
 * viewer with no mapped bots gets { empty: true }, never another account's data.
 */
export async function GET(req: NextRequest) {
  const viewer = await resolveLiveViewer(req)
  if (viewer.allowedBots.length === 0) {
    return NextResponse.json({ empty: true, viewer })
  }
  const data = await getPerformance(viewer.allowedBots, viewer.persons)
  return NextResponse.json({ ...data, viewer })
}
