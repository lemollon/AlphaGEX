import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { createOrResumeEnrollment, ensureLegalDocumentsSeeded, nextStepFor } from '@/lib/enrollment/service'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'

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
  const session = await getCustomerSession()
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
    const enrollment = await createOrResumeEnrollment(
      session.customerId,
      typeof body.source === 'string' ? body.source.slice(0, 60) : undefined,
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
