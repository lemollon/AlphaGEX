import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Batched mobile analytics ingest (APP-048).
 *
 * The client (src/analytics/track.ts) already redacts anything matching
 * /account|token|password|secret/i before an event ever leaves the device. This route
 * repeats the same scrub server-side rather than trusting that redaction — a
 * compromised or out-of-date build is exactly the case a client-side rule alone
 * cannot cover.
 *
 * The 50-event cap matches the client's batching (up to 20 events / 10s): a request
 * that claims more than that is either a bug or something worth rejecting rather than
 * silently truncating.
 */
const MAX_EVENTS = 50
const SENSITIVE_KEY_RE = /account|token|password|secret/i

interface RawEvent {
  event?: unknown
  props?: unknown
  ts?: unknown
  app_version?: unknown
  platform?: unknown
}

function scrubProps(props: unknown): Record<string, unknown> | null {
  if (!props || typeof props !== 'object' || Array.isArray(props)) return null
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(props as Record<string, unknown>)) {
    if (SENSITIVE_KEY_RE.test(k)) continue
    out[k] = v
  }
  return out
}

function parseEvent(raw: RawEvent): { event: string; props: Record<string, unknown> | null; ts: string; appVersion: string | null; platform: string | null } | null {
  if (typeof raw.event !== 'string' || !raw.event) return null
  const ts =
    typeof raw.ts === 'number'
      ? new Date(raw.ts).toISOString()
      : typeof raw.ts === 'string'
        ? raw.ts
        : new Date().toISOString()
  return {
    event: raw.event,
    props: scrubProps(raw.props),
    ts,
    appVersion: typeof raw.app_version === 'string' ? raw.app_version : null,
    platform: typeof raw.platform === 'string' ? raw.platform : null,
  }
}

export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    // No DB configured is not the client's fault — accept and drop, same as every
    // other best-effort telemetry sink, rather than making a screen retry forever.
    return NextResponse.json({ ok: true, accepted: 0 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const rawEvents = body.events
  if (!Array.isArray(rawEvents) || rawEvents.length === 0) {
    return NextResponse.json({ ok: false, error: 'events must be a non-empty array.' }, { status: 400 })
  }
  if (rawEvents.length > MAX_EVENTS) {
    return NextResponse.json({ ok: false, error: `events must not exceed ${MAX_EVENTS}.` }, { status: 400 })
  }

  const parsed = rawEvents.map((e) => parseEvent((e ?? {}) as RawEvent)).filter((e): e is NonNullable<typeof e> => e !== null)
  if (parsed.length === 0) {
    return NextResponse.json({ ok: false, error: 'No valid events supplied.' }, { status: 400 })
  }

  const values: string[] = []
  const params: unknown[] = []
  for (const e of parsed) {
    const base = params.length
    values.push(
      `($${base + 1}, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6})`,
    )
    params.push(identity.customerId, e.event, e.props ? JSON.stringify(e.props) : null, e.ts, e.appVersion, e.platform)
  }

  const accepted = await customerExecute(
    `INSERT INTO mobile_analytics_events (owner_id, event, props, ts, app_version, platform)
     VALUES ${values.join(', ')}`,
    params,
  )

  return NextResponse.json({ ok: true, accepted })
}
