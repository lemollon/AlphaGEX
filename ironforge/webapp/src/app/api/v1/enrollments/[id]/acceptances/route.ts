import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { getEnrollmentForUser, recordAcceptances, ensureLegalDocumentsSeeded } from '@/lib/enrollment/service'
import { isAutomatePlan } from '@/lib/enrollment/legal'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { isEnrollmentClosed, enrollmentClosedResponse } from '@/lib/enrollment-mode'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

/**
 * POST /api/v1/enrollments/{id}/acceptances — "Atomic all-required validation" (§6).
 *
 * Either EVERY required document is in the submission or nothing is written. A partial
 * write is the worst outcome available here: it reads as consent in the audit trail
 * while not actually being consent, and it would let activation proceed on paperwork the
 * customer never agreed to.
 *
 * Captures document id + version + timestamp + user + enrollment + ip + user agent
 * (§3 LEGAL-01) as an APPEND-ONLY record, so any past consent can be reconstructed
 * exactly — the §12 auditability criterion.
 */
export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  // Enrollment closed: never record a legal acceptance from a blocked flow
  // (handoff §4 "Persistence" — "or legal acceptance").
  if (isEnrollmentClosed()) return enrollmentClosedResponse()

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
    const body = (await req.json().catch(() => ({}))) as { accepted?: unknown; signature_name?: unknown }
    const codes = Array.isArray(body.accepted) ? body.accepted.filter((c): c is string => typeof c === 'string') : []
    const signatureName = typeof body.signature_name === 'string' ? body.signature_name.trim() : ''

    const enrollment = await getEnrollmentForUser(params.id, session.customerId)
    if (!enrollment) {
      const e = errorEnvelope('FORBIDDEN', 'That enrollment is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // LEGAL-AUTO-01: automate acceptance requires an explicit electronic signature —
    // the member's typed full legal name. Community acceptance is clickwrap at billing
    // submit and carries no signature. Server-enforced; a pre-checked box or an empty
    // string is not consent evidence.
    if (isAutomatePlan(enrollment.selected_plan) && signatureName.length < 2) {
      const e = errorEnvelope(
        'VALIDATION_FAILED',
        'Type your full legal name to sign the agreements.',
        { field: 'signature_name' },
      )
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    await ensureLegalDocumentsSeeded()
    const result = await recordAcceptances({
      userId: session.customerId,
      enrollmentId: enrollment.id,
      plan: enrollment.selected_plan,
      submittedCodes: codes,
      ip: clientIp(req),
      userAgent: req.headers.get('user-agent'),
      signatureName: signatureName.length >= 2 ? signatureName : null,
    })

    if (!result.ok) {
      const e = errorEnvelope(
        'LEGAL_ACCEPTANCE_INCOMPLETE',
        'Please accept all required agreements to continue.',
        { field: 'accepted' },
      )
      // The missing codes are the remediable detail — which documents, not just "some".
      return NextResponse.json({ ...e, missing: result.missing }, { status: statusFor(e.code) })
    }
    return NextResponse.json({ ok: true, next_step: 'billing' })
  } catch (e) {
    const env = redactProviderError('v1/acceptances', e, 'INTERNAL', 'Something went wrong. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
