import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { getEnrollmentForUser } from '@/lib/enrollment/service'
import { isEmberPlan } from '@/lib/enrollment/legal'
import { createAgentConfigDraft } from '@/lib/enrollment/agent-config-service'
import type { Violation } from '@/lib/enrollment/agent-rules'
import { errorEnvelope, statusFor, redactProviderError } from '@/lib/enrollment/errors'
import { isUuid } from '@/lib/enrollment/ids'
import { isEnrollmentClosed, enrollmentClosedResponse } from '@/lib/enrollment-mode'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * PUT /api/v1/enrollments/{id}/broker-account — "Select account. Server eligibility
 * validation" (§6).
 *
 * The validation is re-done HERE from the stored verdict rather than trusting anything
 * the client sends. A client that posts an ineligible account id — by tampering, or
 * simply because its list went stale while the customer sat on the screen — must be
 * refused, and refused with the reason (§12 "Activation cannot proceed and the UI
 * explains the exact remediable reason").
 *
 * Selecting an account also INVALIDATES any existing agent configuration: "Any account
 * or agent change invalidates the activation review" (§3 AGENT-02). Silently keeping a
 * config that was validated against a different account is how an activation snapshot
 * stops describing what will actually happen.
 *
 * WEB ORDER (10/5 reorder): the web funnel now runs account -> legal -> agent (choose
 * plan) -> broker -> billing -> review — AGENT-01's own screen no longer sits between
 * broker and billing, so THIS is where the web order mints the agent_configs row (via
 * the shared createAgentConfigDraft, identical validation to AGENT-01) and advances the
 * enrollment out of legal_pending (billing_pending for Spark/Flame, setup_required
 * direct for Ember — same branch service.ts already uses after legal). Gated on
 * `identity.source === 'cookie'` (a browser session; the mobile app authenticates with
 * a bearer token) AND `status === 'legal_pending'`, so the APP ORDER — which reaches
 * this route much later, while status is already 'setup_required' from its own
 * billing-then-broker sequence — takes neither branch and is byte-for-byte unchanged.
 */
export async function PUT(req: NextRequest, { params }: { params: { id: string } }) {
  // Enrollment closed: never create/attach a brokerage record from a blocked
  // flow (handoff §4 "Persistence" — "brokerage record").
  if (isEnrollmentClosed()) return enrollmentClosedResponse()

  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer. Shape preserved so the checks below read unchanged.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Brokerage setup is temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  try {
    const body = (await req.json().catch(() => ({}))) as { broker_account_id?: unknown }
    const accountId = String(body.broker_account_id ?? '')
    if (!accountId) {
      const e = errorEnvelope('VALIDATION_FAILED', 'Choose an account to continue.', { field: 'broker_account_id' })
      return NextResponse.json(e, { status: statusFor(e.code) })
    }
    // A malformed id raises on the UUID cast below rather than returning no rows.
    if (!isUuid(accountId)) {
      const e = errorEnvelope('FORBIDDEN', 'That account is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    const enrollment = await getEnrollmentForUser(params.id, session.customerId)
    if (!enrollment) {
      const e = errorEnvelope('FORBIDDEN', 'That enrollment is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Ownership AND eligibility in one query: the join to brokerage_connections is what
    // stops one customer selecting another's account by id.
    const rows = await customerQuery<{
      id: string; eligibility: string; ineligible_reason: string | null; display_mask: string
    }>(
      `SELECT ba.id, ba.eligibility, ba.ineligible_reason, ba.display_mask
         FROM broker_accounts ba
         JOIN brokerage_connections bc ON bc.id = ba.connection_id
        WHERE ba.id = $1 AND bc.user_id = $2
        LIMIT 1`,
      [accountId, session.customerId],
    )
    const account = rows[0]
    if (!account) {
      const e = errorEnvelope('FORBIDDEN', 'That account is not available.')
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    if (account.eligibility !== 'eligible') {
      const e = errorEnvelope(
        'BROKER_ACCOUNT_INELIGIBLE',
        account.ineligible_reason || 'This account is not eligible for automated options trading.',
        { field: 'broker_account_id' },
      )
      return NextResponse.json(e, { status: statusFor(e.code) })
    }

    // Any prior config was validated against a DIFFERENT account — mark it stale so it
    // must be re-validated rather than silently reused.
    await customerExecute(
      `UPDATE agent_configs SET status = 'stale', updated_at = now()
        WHERE user_id = $1 AND status = 'valid' AND (broker_account_id IS DISTINCT FROM $2)`,
      [session.customerId, account.id],
    )

    // Web order only (see the class comment): mint the config here and advance past
    // legal_pending. See the doc comment above for why this never fires for the app.
    const isWebOrder = identity?.source === 'cookie' && enrollment.status === 'legal_pending' && enrollment.selected_plan != null
    let configId: string | null = null
    let nextStep = 'agent'
    let violationMessage: string | null = null

    if (isWebOrder) {
      const draft = await createAgentConfigDraft({
        userId: session.customerId,
        agentCode: enrollment.selected_plan!,
        brokerAccountId: account.id,
      })
      // Only a VALID config may advance the enrollment — draft.ok merely means the
      // draft row was persisted (it is, even when invalid, so a resumed customer has
      // something to come back to). A draft config with violations (e.g. Ember's
      // $500-$2,000 band failing against this account's buying power) must not
      // silently advance past legal_pending — that would mint a status the dedicated
      // banner below could never surface.
      if (draft.ok && draft.status === 'valid') {
        configId = draft.id
        const ember = isEmberPlan(enrollment.selected_plan)
        await customerExecute(
          `UPDATE enrollments SET status = $3, current_step = $4, updated_at = now()
            WHERE id = $1 AND user_id = $2 AND status = 'legal_pending'`,
          [params.id, session.customerId, ember ? 'setup_required' : 'billing_pending', ember ? 'setup' : 'billing'],
        )
        nextStep = ember ? 'setup' : 'billing'
      } else if (draft.ok) {
        const violations = draft.violations as Violation[]
        violationMessage = violations[0]?.message ?? null
      }
      // draft.ok === false (account/agent not found): fall through to the app-order
      // bookkeeping below so the customer is not left with no record at all —
      // ReviewClient/AgentClient's existing fallback chain surfaces the violation.
    }

    if (!isWebOrder || !configId) {
      await customerExecute(
        `UPDATE enrollments SET current_step = 'agent', updated_at = now()
          WHERE id = $1 AND user_id = $2`,
        [params.id, session.customerId],
      )
    }

    return NextResponse.json({
      ok: true,
      broker_account: { id: account.id, display_mask: account.display_mask },
      config_id: configId,
      next_step: configId ? nextStep : 'agent',
      violation: violationMessage,
    })
  } catch (e) {
    const env = redactProviderError('v1/broker-account', e, 'INTERNAL', 'Could not select that account. Please try again.')
    return NextResponse.json(env, { status: statusFor(env.code) })
  }
}
