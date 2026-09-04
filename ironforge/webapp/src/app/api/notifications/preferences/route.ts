import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Notification preferences (APP-036).
 *
 * Column allowlist rather than spreading the body into SQL: this route writes to a
 * table that also holds nothing else, but the pattern matters — an unfiltered
 * key loop here would let a caller name any column.
 */
const BOOL_COLUMNS = [
  'trade_opened',
  'trade_closed',
  'trade_approval',
  'brokerage_health',
  'billing',
  'community',
  'show_amounts_on_lockscreen',
  'sound',
  'weekly_summary',
] as const

const DEFAULTS: Record<string, boolean> = {
  trade_opened: true,
  trade_closed: true,
  trade_approval: true,
  brokerage_health: true,
  billing: true,
  community: false,
  show_amounts_on_lockscreen: false,
  sound: true,
  weekly_summary: false,
}

export async function GET() {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, preferences: DEFAULTS })
  }

  const rows = await customerQuery<Record<string, boolean>>(
    `SELECT ${BOOL_COLUMNS.join(', ')} FROM notification_prefs WHERE user_id = $1 LIMIT 1`,
    [identity.customerId],
  )
  // No row yet = schema defaults, so the settings screen renders the same thing the
  // dispatcher would actually apply.
  return NextResponse.json({ ok: true, preferences: rows[0] ?? DEFAULTS })
}

export async function PUT(req: NextRequest) {
  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'unavailable' }, { status: 503 })
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>

  const updates: string[] = []
  const params: unknown[] = [identity.customerId]
  for (const col of BOOL_COLUMNS) {
    if (typeof body[col] === 'boolean') {
      params.push(body[col])
      updates.push(`${col} = $${params.length}`)
    }
  }
  if (updates.length === 0) {
    return NextResponse.json({ ok: false, error: 'No valid preferences supplied.' }, { status: 400 })
  }

  await customerExecute(
    `INSERT INTO notification_prefs (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING`,
    [identity.customerId],
  )
  await customerExecute(
    `UPDATE notification_prefs SET ${updates.join(', ')}, updated_at = now() WHERE user_id = $1`,
    params,
  )

  const rows = await customerQuery<Record<string, boolean>>(
    `SELECT ${BOOL_COLUMNS.join(', ')} FROM notification_prefs WHERE user_id = $1 LIMIT 1`,
    [identity.customerId],
  )
  return NextResponse.json({ ok: true, preferences: rows[0] ?? DEFAULTS })
}
