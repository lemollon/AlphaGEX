import { NextRequest, NextResponse } from 'next/server'
import { customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { ctDateString, isBotUserAgent, normalizeTrackedPath, visitorHash } from '@/lib/track'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/track — public, unauthenticated, first-party page-view beacon.
 * Fired by <TrackPageView> on every client-side route change.
 *
 * PRIVACY: the request's IP and user agent are read ONLY to derive a one-way,
 * same-day-stable hash (visitorHash). Neither value is ever written anywhere —
 * the row that lands in `page_views` carries the calendar day, the normalized
 * path, the hash, and a hit counter. No cookie is set or read.
 *
 * Always answers 204, even on a rejected/invalid body or a DB failure — a
 * beacon caller has nothing useful to do with an error response, and a
 * tracking hiccup must never surface to a real visitor.
 */
export async function POST(req: NextRequest) {
  const raw = await req.text().catch(() => null)
  if (!raw) return new NextResponse(null, { status: 204 })

  let body: Record<string, unknown> | null = null
  try {
    body = JSON.parse(raw) as Record<string, unknown>
  } catch {
    return new NextResponse(null, { status: 204 })
  }

  const ua = req.headers.get('user-agent') ?? ''
  if (isBotUserAgent(ua)) return new NextResponse(null, { status: 204 })

  const path = normalizeTrackedPath(body?.path)
  if (!path) return new NextResponse(null, { status: 204 })

  if (!isCustomersDbConfigured()) return new NextResponse(null, { status: 204 })

  const xff = req.headers.get('x-forwarded-for')
  const ip = xff ? xff.split(',')[0].trim() : 'unknown'
  const day = ctDateString()
  const visitor = visitorHash({ day, ip, ua })

  try {
    await customerExecute(
      `INSERT INTO page_views (day, path, visitor)
       VALUES ($1, $2, $3)
       ON CONFLICT (day, path, visitor) DO UPDATE SET hits = page_views.hits + 1, last_seen = now()`,
      [day, path, visitor],
    )
  } catch (e) {
    console.error('[track] write failed:', e)
  }

  return new NextResponse(null, { status: 204 })
}
