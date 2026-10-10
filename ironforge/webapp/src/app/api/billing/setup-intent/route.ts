import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import {
  isStripeConfigured,
  getOrCreateCustomer,
  createCustomer,
  createSetupIntent,
  isMissingCustomerError,
} from '@/lib/billing/stripe'
import { getEnrollmentForUser } from '@/lib/enrollment/service'
import { isAutomatePlan } from '@/lib/enrollment/legal'
import { isEnrollmentClosed, enrollmentClosedResponse } from '@/lib/enrollment-mode'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/billing/setup-intent — the EMBEDDED-card counterpart to
 * POST /api/billing/checkout's `intent: 'enrollment_setup'` branch (10/5 reorder).
 *
 * Returns a SetupIntent client_secret for the enrollment Billing step's Stripe
 * Elements/Payment Element form, instead of a hosted-Checkout url. Same guard as the
 * hosted path: only an owned enrollment, currently in billing_pending, on an
 * automate-family plan may mint one. $0 due today; see createSetupIntent() for why
 * this is a SetupIntent and not a subscription.
 *
 * BillingClient.tsx falls back to the hosted-Checkout path entirely when
 * NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY is not configured — this route is never called
 * in that case.
 */
export async function POST(req: NextRequest) {
  if (isEnrollmentClosed()) return enrollmentClosedResponse()

  const identity = await getCustomerIdentity()
  if (!identity) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

  if (!isStripeConfigured() || !isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Billing is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  try {
    const body = (await req.json().catch(() => null)) as { enrollment_id?: unknown } | null
    const enrollmentId = body && typeof body.enrollment_id === 'string' ? body.enrollment_id : null
    const enrollment = enrollmentId ? await getEnrollmentForUser(enrollmentId, identity.customerId) : null
    if (!enrollment) {
      return NextResponse.json({ ok: false, error: 'That enrollment is not available.' }, { status: 403 })
    }
    if (enrollment.status !== 'billing_pending' || !isAutomatePlan(enrollment.selected_plan)) {
      return NextResponse.json({ ok: false, error: 'Billing is not the current step for this enrollment.' }, { status: 409 })
    }

    const rows = await customerQuery<{ id: string; email: string | null; stripe_customer_id: string | null }>(
      `SELECT id, email, stripe_customer_id FROM users WHERE id = $1 LIMIT 1`,
      [identity.customerId],
    )
    const user = rows[0]
    if (!user) return NextResponse.json({ ok: false, error: 'unauthorized' }, { status: 401 })

    const persistCustomer = async (id: string) => {
      if (id !== user.stripe_customer_id) {
        await customerExecute(`UPDATE users SET stripe_customer_id = $2, updated_at = now() WHERE id = $1`, [user.id, id])
      }
    }

    let customerId = await getOrCreateCustomer({ existingId: user.stripe_customer_id, email: user.email, userId: user.id })
    await persistCustomer(customerId)

    let intent: { id: string; client_secret: string }
    try {
      intent = await createSetupIntent({ customerId })
    } catch (e) {
      if (!isMissingCustomerError(e)) throw e
      customerId = await createCustomer({ email: user.email, userId: user.id })
      await persistCustomer(customerId)
      intent = await createSetupIntent({ customerId })
    }

    return NextResponse.json({ ok: true, client_secret: intent.client_secret })
  } catch {
    return NextResponse.json({ ok: false, error: 'Could not start billing setup. Please try again.' }, { status: 500 })
  }
}
