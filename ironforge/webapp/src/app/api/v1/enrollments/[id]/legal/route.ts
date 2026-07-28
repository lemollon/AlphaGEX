import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { getEnrollmentForUser, legalRequirementsFor, ensureLegalDocumentsSeeded } from '@/lib/enrollment/service'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * GET /api/v1/enrollments/{id}/legal — required document VERSIONS (§6).
 *
 * "No stale cached versions." Computed on every request from the code registry and the
 * user's acceptance history; nothing here is cached and the response is force-dynamic.
 * A customer must never be shown, or allowed to accept, a version that is no longer the
 * active one.
 *
 * Each document carries its version and content URI so the UI can meet §3 LEGAL-01:
 * open it with version + effective date, and require it be opened before acceptance.
 */
export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const session = await getCustomerSession()
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Enrollment is temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  try {
    const enrollment = await getEnrollmentForUser(params.id, session.customerId)
    if (!enrollment) {
      const e = errorEnvelope('FORBIDDEN', 'That enrollment is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }
    await ensureLegalDocumentsSeeded()
    const legal = await legalRequirementsFor(enrollment.selected_plan, session.customerId)
    return NextResponse.json(
      { enrollment_id: enrollment.id, selected_plan: enrollment.selected_plan, ...legal },
      { headers: { 'Cache-Control': 'no-store' } },
    )
  } catch (e) {
    const env = redactProviderError('v1/legal', e, 'INTERNAL', 'Something went wrong. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
