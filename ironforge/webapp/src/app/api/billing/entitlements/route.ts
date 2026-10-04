import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * The bots (and bot-shaped rows like 'community', 'ember') this customer currently has an
 * active/trialing subscription to. Drives nav ownership badges and the Open Account page's
 * "you already run X" copy. Self-guarded (no session → empty), and degrades to empty when
 * billing isn't provisioned.
 */
const LIVE_STATUSES = ['trialing', 'active', 'past_due']

export async function GET() {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId || !isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, bots: [] })
  }
  try {
    const rows = await customerQuery<{ bot: string; status: string }>(
      `SELECT bot, status FROM customer_bot_subscriptions WHERE user_id = $1`,
      [session.customerId],
    )
    const bots = rows.filter((r) => LIVE_STATUSES.includes(r.status)).map((r) => r.bot)
    return NextResponse.json({ ok: true, bots })
  } catch {
    return NextResponse.json({ ok: true, bots: [] })
  }
}
