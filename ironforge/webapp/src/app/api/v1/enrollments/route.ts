import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { advanceBillingIfComplete, createOrResumeEnrollment, ensureLegalDocumentsSeeded, nextStepFor } from '@/lib/enrollment/service'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { isEnrollmentClosed, enrollmentClosedResponse } from '@/lib/enrollment-mode'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/v1/enrollments — create or RESUME the enrollment intent (spec §6).
 *
 * Returns { enrollment, next_step }. next_step is computed SERVER-SIDE so a resumed
 * session — including one opened from an email deep link days later — cannot disagree
 * with where the server thinks the customer is (§3 DONE-01).
 *
 * Path note: the spec writes /v1/...; this app serves everything under /api, so the
 * routes are /api/v1/... The contract is otherwise as specified.
 */
export async function POST(req: NextRequest) {
  // Enrollment closed: do not begin a new enrollment intent (handoff §4/§11).
  if (isEnrollmentClosed()) return enrollmentClosedResponse()

  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Enrollment is temporarily unavailable. Please try again shortly.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  try {
    const body = (await req.json().catch(() => ({}))) as { source?: unknown }
    await ensureLegalDocumentsSeeded()
    // Resume-time billing advancement: the customer returning from hosted Checkout may
    // beat the Stripe webhook here. Re-deriving the transition from Stripe state makes
    // the funnel immune to webhook lag; nothing advances that isn't provably paid/saved.
    const enrollment = await advanceBillingIfComplete(
      await createOrResumeEnrollment(
        session.customerId,
        typeof body.source === 'string' ? body.source.slice(0, 60) : undefined,
      ),
    )
    return NextResponse.json({
      enrollment: {
        id: enrollment.id,
        selected_plan: enrollment.selected_plan,
        status: enrollment.status,
      },
      next_step: nextStepFor(enrollment),
    })
  } catch (e) {
    const env = redactProviderError('v1/enrollments', e, 'INTERNAL', 'Something went wrong. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
