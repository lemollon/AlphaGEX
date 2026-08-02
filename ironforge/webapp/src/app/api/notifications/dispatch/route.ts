import { NextRequest, NextResponse } from 'next/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { dispatchToCustomers } from '@/lib/push/dispatch'
import { safeAppRoute } from '@/lib/mobile/deep-link'
import type { NotificationEvent, NotificationCategory } from '@/lib/push/types'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Internal dispatch seam: the scanner (operator service) POSTs here so notification
 * policy, copy, and device state all live on the customer service where the app's own
 * routes need them too. Same shape as POST /api/brokerage/trades, which is already
 * "scanner produces a customer-visible side effect, service-token guarded".
 *
 * Self-guards rather than relying on middleware, because IRONFORGE_PUBLIC_MODE bypasses
 * the gate entirely — a route that can trigger pushes to arbitrary customers must not
 * inherit that.
 */
const CATEGORIES: NotificationCategory[] = [
  'trade_opened',
  'trade_closed',
  'trade_approval',
  'brokerage_health',
  'billing',
  'community',
]

export async function POST(req: NextRequest) {
  if (!hasValidServiceToken(req.headers.get('x-ironforge-service'))) {
    return NextResponse.json({ ok: false, error: 'forbidden' }, { status: 403 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const customerIds = Array.isArray(body.customerIds)
    ? body.customerIds.filter((x): x is string => typeof x === 'string')
    : []
  const raw = (body.event ?? {}) as Record<string, unknown>

  const category = String(raw.category ?? '') as NotificationCategory
  if (!CATEGORIES.includes(category)) {
    return NextResponse.json({ ok: false, error: 'Unknown category.' }, { status: 400 })
  }
  const eventKey = String(raw.eventKey ?? '')
  if (!eventKey) {
    return NextResponse.json({ ok: false, error: 'eventKey is required.' }, { status: 400 })
  }

  const event: NotificationEvent = {
    category,
    eventKey,
    occurredAt: String(raw.occurredAt ?? new Date().toISOString()),
    // Producers never choose a free-form destination — safeAppRoute clamps to the
    // customer-surface allowlist.
    route: safeAppRoute(typeof raw.route === 'string' ? raw.route : undefined),
    routeParams:
      raw.routeParams && typeof raw.routeParams === 'object'
        ? (raw.routeParams as Record<string, string>)
        : {},
    title: String(raw.title ?? 'IronForge'),
    body: String(raw.body ?? ''),
    amount: typeof raw.amount === 'number' ? raw.amount : null,
    state: typeof raw.state === 'string' ? raw.state : null,
  }

  const result = await dispatchToCustomers(event, customerIds)
  return NextResponse.json({ ok: true, ...result })
}
