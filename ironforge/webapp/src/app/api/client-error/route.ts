import { NextRequest, NextResponse } from 'next/server'
import { rateLimited } from '@/lib/rate-limit'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/client-error — public, unauthenticated crash/error beacon for the
 * mobile app (and web, if ever needed). Stood up 2026-10-14 because the app
 * has NO crash visibility at all: Sentry's DSN was never set (see
 * mobile/src/monitoring/sentry.ts — "Leron has not created the Sentry project
 * yet"), so a client-side JS exception or unhandled rejection leaves zero
 * trace anywhere. A tester reporting "Sparky is glitching" with no server
 * request ever landing for that attempt is exactly the blind spot this
 * closes — the crash may be happening before the network call ever fires.
 *
 * Deliberately NOT the analytics_events pipe (POST /api/v1/events): that
 * table's prop allowlist is a handful of short tags (cta, placement, …) by
 * design, and a stack trace does not belong jammed into one of those slots.
 * This is the simplest thing that can possibly work: log it structured, to
 * Render's own log stream, where list_logs can grep `[CLIENT_CRASH]` and get
 * an answer in one query — no new DB table, no new schema, no new vendor
 * account. Reachable with NO session (a crash can happen before sign-in),
 * same public treatment as /api/track for the identical reason.
 *
 * Always answers fast and never throws — a reporting beacon must never
 * become a second thing to debug.
 */
const MAX_FIELD_LEN = 4000

function clip(v: unknown): string | null {
  if (typeof v !== 'string' || !v) return null
  return v.length > MAX_FIELD_LEN ? v.slice(0, MAX_FIELD_LEN) + '…[clipped]' : v
}

export async function POST(req: NextRequest) {
  const xff = req.headers.get('x-forwarded-for')
  const ip = xff ? xff.split(',')[0].trim() : 'unknown'

  // Generous but bounded — a crash loop must not be able to flood Render's log
  // stream, but a real incident can legitimately fire several of these fast.
  if (rateLimited(`client-error:${ip}`, { windowMs: 60_000, maxPerWindow: 30 })) {
    return new NextResponse(null, { status: 204 })
  }

  const body = (await req.json().catch(() => null)) as Record<string, unknown> | null
  if (!body) return new NextResponse(null, { status: 204 })

  const report = {
    message: clip(body.message),
    stack: clip(body.stack),
    componentStack: clip(body.componentStack),
    screen: clip(body.screen),
    kind: clip(body.kind), // 'js_exception' | 'unhandled_rejection' | 'network_error' | ...
    build: clip(body.build),
    appVersion: clip(body.appVersion),
    platform: clip(body.platform),
    userAgent: req.headers.get('user-agent') ?? null,
    ip,
    ts: new Date().toISOString(),
  }

  // Tag is deliberately UPPERCASE and bracketed — grep '[CLIENT_CRASH]' in
  // Render logs (type=app) to pull every report, newest first.
  console.error('[CLIENT_CRASH]', JSON.stringify(report))

  return new NextResponse(null, { status: 204 })
}
