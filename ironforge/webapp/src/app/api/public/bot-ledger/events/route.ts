import { NextRequest, NextResponse } from 'next/server'

import { log } from '@/lib/logger'
import { MAX_EVENTS_PER_REQUEST, validateEvent } from '@/lib/bot-ledger/event-schema'
import { requestIdFrom } from '@/lib/bot-ledger/request-id'

/**
 * PUBLIC Bot Ledger analytics collector.
 *
 * First-party and vendor-free: no cookies, no device id, no third-party
 * script. Events are validated against a strict allowlist
 * (`lib/bot-ledger/event-schema.ts`) and written to the structured log, which
 * is where the operational dashboards already read from.
 *
 * The endpoint is public, so it is treated as hostile input: rate limited per
 * IP, capped batch size, capped body, and an allowlist that rejects any extra
 * key rather than passing it through. Nothing here is ever persisted to a
 * trade table.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const WINDOW_MS = 60_000
const MAX_PER_WINDOW = 30
const MAX_BODY_BYTES = 8_192

const HITS = new Map<string, number[]>()

function rateLimited(key: string): boolean {
  const now = Date.now()
  const arr = (HITS.get(key) ?? []).filter((t) => now - t < WINDOW_MS)
  arr.push(now)
  HITS.set(key, arr)
  // Cheap eviction so the map cannot grow without bound on a public route.
  // forEach rather than for..of: tsconfig targets es5, which cannot iterate a
  // Map without --downlevelIteration.
  if (HITS.size > 5_000) {
    const stale: string[] = []
    HITS.forEach((v, k) => {
      if (v.every((t) => now - t >= WINDOW_MS)) stale.push(k)
    })
    stale.forEach((k) => HITS.delete(k))
  }
  return arr.length > MAX_PER_WINDOW
}

function clientKey(req: NextRequest): string {
  const fwd = req.headers.get('x-forwarded-for') ?? ''
  return fwd.split(',')[0].trim() || req.headers.get('x-real-ip') || 'unknown'
}

export async function POST(req: NextRequest) {
  const requestId = requestIdFrom(req.headers)
  const headers = { 'Cache-Control': 'no-store', 'x-request-id': requestId }

  if (rateLimited(clientKey(req))) {
    return new NextResponse(null, { status: 429, headers })
  }

  const text = await req.text().catch(() => '')
  if (text.length > MAX_BODY_BYTES) {
    return new NextResponse(null, { status: 413, headers })
  }

  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return new NextResponse(null, { status: 400, headers })
  }

  const raw = (parsed as { events?: unknown })?.events
  if (!Array.isArray(raw)) return new NextResponse(null, { status: 400, headers })

  let accepted = 0
  let rejected = 0
  for (const item of raw.slice(0, MAX_EVENTS_PER_REQUEST)) {
    const event = validateEvent(item)
    if (!event) {
      rejected += 1
      continue
    }
    accepted += 1
    log('info', 'bot-ledger-analytics', event.name, { ...event.props, request_id: requestId })
  }

  // A rejected event is worth knowing about — it means either the client and
  // the schema have drifted, or someone is probing the endpoint.
  if (rejected > 0) {
    log('warn', 'bot-ledger-analytics', 'rejected malformed events', {
      rejected,
      request_id: requestId,
    })
  }

  // 204: the browser fires these with sendBeacon and ignores the body.
  return new NextResponse(null, { status: 204, headers })
}
