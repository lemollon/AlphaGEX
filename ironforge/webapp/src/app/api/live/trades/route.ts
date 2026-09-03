import { NextRequest, NextResponse } from 'next/server'
import { resolveLiveViewer, isLiveBot, type LiveBot } from '@/lib/live/viewer'
import { getCustomerTradesPage } from '@/lib/live/trades-history'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Customer Trade History — the viewer's own closed trades across owned strategies,
 * cursor-paginated (APP-020). Authorization is server-side via resolveLiveViewer: a
 * viewer with no mapped bots gets { empty: true }, never another account's data.
 *
 * Query params (all optional): limit (default 50, max 200), cursor (opaque, from a
 * prior response's next_cursor), bot (spark|flame), days (30|90 — omitted = all
 * time), q (free-text search over ticker/close reason/agent name/date).
 *
 * No-param calls stay backward compatible: the response still has a `trades` array
 * (now page 1 of 50, not up to 300 per bot) plus the two new pagination fields.
 */
export async function GET(req: NextRequest) {
  try {
    const viewer = await resolveLiveViewer(req)
    if (viewer.allowedBots.length === 0) {
      return NextResponse.json({ empty: true, viewer })
    }

    const sp = req.nextUrl.searchParams
    const botParam = sp.get('bot')
    const daysParam = sp.get('days')
    const limitParam = sp.get('limit')

    const bot: LiveBot | null = isLiveBot(botParam) && viewer.allowedBots.includes(botParam) ? botParam : null
    const days: 30 | 90 | null = daysParam === '30' ? 30 : daysParam === '90' ? 90 : null

    const result = await getCustomerTradesPage(
      viewer.allowedBots,
      viewer.persons,
      viewer.paperBots,
      viewer.isOperator,
      {
        limit: limitParam ? Number(limitParam) : undefined,
        cursor: sp.get('cursor'),
        bot,
        days,
        q: sp.get('q'),
      },
    )

    return NextResponse.json({
      trades: result.trades,
      next_cursor: result.next_cursor,
      total: result.total,
      viewer,
    })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err)
    return NextResponse.json({ error: msg }, { status: 500 })
  }
}
