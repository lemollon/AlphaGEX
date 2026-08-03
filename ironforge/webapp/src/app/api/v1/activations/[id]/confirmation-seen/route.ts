import { NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { isUuid } from '@/lib/enrollment/ids'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/v1/activations/{id}/confirmation-seen — stamp the DASH-FIRST-01
 * confirmation as shown, exactly once. Ownership-scoped; the IS NULL predicate makes
 * a replay a no-op rather than an update.
 */
export async function POST(_req: Request, { params }: { params: { id: string } }) {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  // Malformed ids raise on the UUID cast rather than matching no rows.
  if (!isUuid(params.id) || !isUuid(session.customerId)) {
    const e = errorEnvelope('FORBIDDEN', 'That activation is not available.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  try {
    await customerExecute(
      `UPDATE activations SET confirmation_shown_at = now()
        WHERE id = $1 AND user_id = $2 AND confirmation_shown_at IS NULL`,
      [params.id, session.customerId],
    )
    return NextResponse.json({ ok: true })
  } catch (e) {
    const env = redactProviderError('v1/confirmation-seen', e, 'INTERNAL', 'Something went wrong.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
