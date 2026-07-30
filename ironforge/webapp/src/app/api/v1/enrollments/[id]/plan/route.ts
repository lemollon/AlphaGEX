import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomersDbConfigured } from '@/lib/customers-db'
import { getEnrollmentForUser, setEnrollmentPlan, legalRequirementsFor } from '@/lib/enrollment/service'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { BOT_PLANS, COMMUNITY_PLAN, BOTH_PLAN } from '@/lib/billing/plans'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Plans this deployment actually sells. Community + the per-bot model kept this session.
 * 'automate' is the PLAN-01 family value — persisted before an agent is chosen; the
 * agent choice becomes agent_configs.agent_code at AGENT-01 and is never a second plan
 * PUT (setEnrollmentPlan rewinds the funnel to legal by design).
 */
const VALID_PLANS = new Set<string>([
  COMMUNITY_PLAN.key,
  ...Object.keys(BOT_PLANS),
  'both',
  'automate',
])

/**
 * PUT /api/v1/enrollments/{id}/plan — "Choose plan. Recomputes legal requirements" (§6).
 *
 * The recompute is structural, not a step: legal requirements are DERIVED from the plan
 * on every read and never cached onto the enrollment, so switching Community ↔ Automate
 * cannot leave a stale "legal complete" flag behind — the §12 acceptance criterion
 * "Changing Community ↔ Automate recomputes legal/billing requirements without
 * duplicate user".
 */
export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
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
    const body = (await req.json().catch(() => ({}))) as { plan?: unknown }
    const plan = String(body.plan ?? '')
    if (!VALID_PLANS.has(plan)) {
      const e = errorEnvelope('PLAN_INVALID', 'Choose one of the available plans.', { field: 'plan' })
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Ownership check — an id alone is never authority (§8).
    const enrollment = await getEnrollmentForUser(params.id, session.customerId)
    if (!enrollment) {
      const e = errorEnvelope('FORBIDDEN', 'That enrollment is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    await setEnrollmentPlan(params.id, session.customerId, plan)
    const legal = await legalRequirementsFor(plan, session.customerId)
    return NextResponse.json({ ok: true, selected_plan: plan, next_step: 'legal', legal })
  } catch (e) {
    const env = redactProviderError('v1/plan', e, 'INTERNAL', 'Something went wrong. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
