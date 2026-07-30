import { NextRequest, NextResponse } from 'next/server'
import { resolveCustomerUserId } from '@/lib/brokerage/identity'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/onboarding/brokerage/interest — a customer clicked Connect on a brokerage
 * we do not integrate with yet (BROKER-01 shows tastytrade as available per the
 * approved visual; the graceful state emits this interest event instead of a dead
 * end). Session-guarded; writes an audit_events row so demand is measurable.
 */

const KNOWN_BROKERS = new Set(['tastytrade'])

export async function POST(req: NextRequest) {
  const uid = await resolveCustomerUserId(req)
  if (!uid) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true, stored: false })

  const body = (await req.json().catch(() => ({}))) as { broker?: unknown }
  const broker = typeof body.broker === 'string' ? body.broker.toLowerCase().trim() : ''
  if (!KNOWN_BROKERS.has(broker)) {
    return NextResponse.json({ ok: false, error: 'Unknown brokerage.' }, { status: 400 })
  }

  await customerExecute(
    `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, 'BROKER_INTEREST', $2)`,
    [uid, JSON.stringify({ broker })],
  ).catch(() => {})

  return NextResponse.json({ ok: true })
}
