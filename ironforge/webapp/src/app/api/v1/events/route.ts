import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerExecute, customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isAllowedEvent, isAllowedSurface, allowedPropsFor, type AnalyticsSurface } from '@/lib/analytics/events'
import { scrubProps } from '@/lib/analytics/scrub'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/v1/events — first-party analytics ingest for web, iOS and Android.
 *
 * No vendor SDK, no third-party request, no new API key: this writes directly
 * to `analytics_events` in the customers DB, the same way /api/track writes
 * page_views. Accepts EITHER a cookie session, a mobile bearer token, or (most
 * marketing/enrollment events, which fire before anyone is signed in) an
 * anonymous `anon_id` the client generates once and reuses — never derived
 * from IP or user agent, unlike the day-rotating hash /api/track uses for
 * page views, because these events must join across days (e.g. an enrollment
 * funnel) rather than reset daily.
 *
 * Accepts a single event ({event, props, surface}) or a batch ({events: [...]}),
 * so the same route serves the web track() helper (one event per call) and the
 * mobile helper (batched, like the existing /api/v1/analytics/events contract).
 *
 * Order: auth/anon resolution -> rate limit -> per-event allowlist + PII scrub
 * -> insert. An event with an unrecognized name or malformed shape is DROPPED
 * from the batch, not a reason to fail the whole request — never let one bad
 * row block the rest of a real session's telemetry.
 */

const MAX_EVENTS_PER_REQUEST = 50
// Generous enough for the mobile helper's own batching (up to 20 events / 10s)
// to run continuously for a few minutes, while still bounding a runaway client.
const RATE_LIMIT_MAX = 300
const RATE_LIMIT_WINDOW = "5 minutes"

interface RawEvent {
  event?: unknown
  props?: unknown
  surface?: unknown
}

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

function parseOne(
  raw: RawEvent,
  fallbackSurface: AnalyticsSurface | null,
): { event: string; props: Record<string, unknown> | null; surface: AnalyticsSurface } | null {
  if (!isAllowedEvent(raw.event)) return null
  const surface = isAllowedSurface(raw.surface) ? raw.surface : fallbackSurface
  if (!surface) return null
  const scrubbed = scrubProps((raw.props ?? null) as Record<string, unknown> | null)
  const props = allowedPropsFor(raw.event, scrubbed)
  return { event: raw.event, props, surface }
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    // Best-effort telemetry: no DB configured is not the caller's fault.
    return NextResponse.json({ ok: true, accepted: 0 })
  }

  const body = (await req.json().catch(() => null)) as
    | { event?: unknown; props?: unknown; surface?: unknown; anon_id?: unknown; events?: unknown }
    | null
  if (!body) return NextResponse.json({ ok: false, error: 'Invalid JSON body.' }, { status: 400 })

  const identity = await getCustomerIdentity().catch(() => null)
  const anonId = typeof body.anon_id === 'string' && body.anon_id.length > 0 ? body.anon_id.slice(0, 100) : null
  if (!identity && !anonId) {
    return NextResponse.json(
      { ok: false, error: 'anon_id is required when no session is present.' },
      { status: 400 },
    )
  }

  const fallbackSurface = isAllowedSurface(body.surface) ? body.surface : null
  const rawEvents: RawEvent[] = Array.isArray(body.events)
    ? (body.events as RawEvent[])
    : body.event
      ? [{ event: body.event, props: body.props, surface: body.surface }]
      : []

  if (rawEvents.length === 0) {
    return NextResponse.json({ ok: false, error: 'No event supplied.' }, { status: 400 })
  }
  if (rawEvents.length > MAX_EVENTS_PER_REQUEST) {
    return NextResponse.json(
      { ok: false, error: `A request may not carry more than ${MAX_EVENTS_PER_REQUEST} events.` },
      { status: 400 },
    )
  }

  // Rate limit, keyed on whichever identity the request actually carries —
  // DB-counted the same way /api/waitlist bounds repeat submissions, so there
  // is no separate in-memory limiter to keep consistent across instances.
  try {
    const rateKey = identity?.customerId ?? anonId ?? clientIp(req) ?? 'unknown'
    const rateColumn = identity?.customerId ? 'user_id::text' : 'anon_id'
    const windowRows = await customerQuery<{ c: number }>(
      `SELECT count(*)::int AS c FROM analytics_events
        WHERE ${rateColumn} = $1 AND created_at > now() - interval '${RATE_LIMIT_WINDOW}'`,
      [rateKey],
    )
    if (Number(windowRows[0]?.c ?? 0) >= RATE_LIMIT_MAX) {
      return NextResponse.json({ ok: false, error: 'Rate limited.' }, { status: 429 })
    }
  } catch {
    // Never block real telemetry on a counting error.
  }

  const parsed = rawEvents
    .map((e) => parseOne((e ?? {}) as RawEvent, fallbackSurface))
    .filter((e): e is NonNullable<typeof e> => e !== null)

  if (parsed.length === 0) {
    return NextResponse.json({ ok: false, error: 'No valid event in the request.' }, { status: 400 })
  }

  const values: string[] = []
  const params: unknown[] = []
  for (const e of parsed) {
    const base = params.length
    values.push(`($${base + 1}, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5})`)
    params.push(
      identity?.customerId ?? null,
      identity ? null : anonId,
      e.event,
      e.props ? JSON.stringify(e.props) : null,
      e.surface,
    )
  }

  try {
    const accepted = await customerExecute(
      `INSERT INTO analytics_events (user_id, anon_id, event, props, surface)
       VALUES ${values.join(', ')}`,
      params,
    )
    return NextResponse.json({ ok: true, accepted }, { status: 201 })
  } catch (e) {
    console.error('[events] write failed:', e)
    // A telemetry write failing must never surface as an error to the caller.
    return NextResponse.json({ ok: true, accepted: 0 })
  }
}
