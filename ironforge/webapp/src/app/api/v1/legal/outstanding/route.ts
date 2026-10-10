import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { legalRequirementsFor } from '@/lib/enrollment/service'
import { isAutomatePlan } from '@/lib/enrollment/legal'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const LIVE_STATUSES = ['trialing', 'active', 'past_due']

/**
 * GET /api/v1/legal/outstanding — the logged-in-customer half of legal
 * versioning. `staleDocumentCodes`/`legalRequirementsFor` already existed for
 * a NOT-YET-ACTIVE enrollment (blocking activation on a stale document), but
 * nothing ever re-ran that check for someone already active: bump a
 * document's version in lib/enrollment/legal.ts and an existing member would
 * never be asked to re-accept it. This is the read side of that gap; POST
 * /api/v1/legal/reaccept is the write side.
 *
 * Plan is derived the same way /api/billing/entitlements does (owned bots
 * from customer_bot_subscriptions), not trusted from the client — a
 * Community-only member only ever owes the `core` scope, never the
 * automate-family documents a Spark/Flame/Ember member owes.
 */
export async function GET() {
  const identity = await getCustomerIdentity()
  if (!identity?.customerId) {
    return NextResponse.json({ ok: false, error: 'Please sign in to continue.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: true, documents: [], outstanding: [] })
  }

  try {
    const rows = await customerQuery<{ bot: string; status: string }>(
      `SELECT bot, status FROM customer_bot_subscriptions WHERE user_id = $1`,
      [identity.customerId],
    )
    const bots = rows.filter((r) => LIVE_STATUSES.includes(r.status)).map((r) => r.bot)
    const plan = bots.some((b) => isAutomatePlan(b)) ? 'automate' : null

    const { documents, outstanding } = await legalRequirementsFor(plan, identity.customerId)
    return NextResponse.json({ ok: true, documents, outstanding })
  } catch {
    // A read failure here must never lock a signed-in customer out of their own
    // dashboard — the gate below treats a failed/empty fetch as "nothing outstanding".
    return NextResponse.json({ ok: true, documents: [], outstanding: [] })
  }
}
