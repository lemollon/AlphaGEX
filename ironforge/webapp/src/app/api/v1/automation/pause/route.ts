import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { errorEnvelope, statusFor } from '@/lib/enrollment/errors'
import { enqueueCrmEvent, recurringEventId } from '@/lib/crm/outbox'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Customer automation pause (spec §23). Pausing stops NEW positions immediately;
 * open positions still close per the strategy's exit rules — the executor's gate
 * blocks opens on status='paused' but never gates closes, so a pause can never
 * strand risk in the account. Trial days keep counting while paused (ADR 0008).
 */

interface ActivationRow {
  activation_id: string
  agent_code: string
  status: string
  paused_at: string | null
}

async function liveActivations(userId: string): Promise<ActivationRow[]> {
  return customerQuery<ActivationRow>(
    `SELECT a.id AS activation_id, ac.agent_code, a.status, a.paused_at
       FROM activations a
       JOIN agent_configs ac ON ac.id = a.config_id
      WHERE ac.user_id = $1 AND a.status IN ('active', 'paused')
      ORDER BY a.activated_at DESC NULLS LAST`,
    [userId],
  )
}

/**
 * Mirror a pause/resume into the CRM.
 *
 * This is the ONLY place a customer-initiated `Paused` can originate: the Stripe webhook
 * deliberately never publishes it (a past_due invoice is not a pause), so before this the
 * `Paused` lifecycle value and the "Paused & Canceled" view existed with nothing on earth able
 * to set them.
 *
 * Strictly additive and fully swallowed. Pausing automation is a risk control — it must succeed
 * and return even if the CRM, the customers DB read, or the outbox is having a bad day.
 */
async function mirrorPauseToCrm(userId: string, agent: string | null, paused: boolean): Promise<void> {
  try {
    const user = (
      await customerQuery<{ email: string; first_name: string; last_name: string }>(
        `SELECT email, first_name, last_name FROM users WHERE id = $1 LIMIT 1`,
        [userId],
      )
    )[0]
    if (!user) return

    // One event per distinct subscription. DISTINCT collapses a bundle (two bot rows sharing one
    // Stripe subscription) into the single membership record it actually is.
    const subs = await customerQuery<{ stripe_subscription_id: string; status: string }>(
      `SELECT DISTINCT stripe_subscription_id, status
         FROM customer_bot_subscriptions
        WHERE user_id = $1
          AND status IN ('trialing', 'active', 'past_due')
          AND stripe_subscription_id IS NOT NULL
          AND ($2::text IS NULL OR bot = $2)`,
      [userId, agent],
    )
    // No membership → nothing to mark Paused. Inventing a membershipId here would create a
    // stray membership record in Attio that no billing event will ever reconcile.
    if (!subs.length) return

    for (const sub of subs) {
      // On resume we publish what the membership genuinely is, never a blanket 'Active': a
      // customer whose card failed resumes their bots as Past Due, and saying otherwise would
      // tell the CRM they are in good standing when they are not.
      const membershipStatus = paused ? 'Paused' : sub.status === 'past_due' ? 'Past Due' : 'Active'
      const lifecycle = paused ? 'Paused' : sub.status === 'past_due' ? undefined : 'Active'

      await enqueueCrmEvent({
        // Bucketed to the minute: a customer can legitimately pause, resume, and pause again in
        // one day, and a subject-keyed id would swallow every occurrence after the first.
        eventId: recurringEventId(
          `${paused ? 'membership_paused' : 'membership_resumed'}:${sub.stripe_subscription_id}:${agent ?? 'all'}`,
        ),
        // Resume is NOT 'crm.reactivation' — that means a returning customer whose billing came
        // back (spec §6), and reusing it here would make the two indistinguishable in the outbox.
        eventType: paused ? 'crm.membership_paused' : 'crm.subscription_active',
        userId,
        correlationId: sub.stripe_subscription_id,
        payload: {
          email: user.email,
          firstName: user.first_name,
          lastName: user.last_name,
          ironforgeUserId: userId,
          membershipId: sub.stripe_subscription_id,
          stripeSubscriptionId: sub.stripe_subscription_id,
          membershipStatus,
          lifecycle,
        },
      })
    }
  } catch (e) {
    console.error('[automation/pause] crm mirror failed (non-fatal):', e)
  }
}

export async function GET() {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) return NextResponse.json({ ok: true, activations: [] })

  const rows = await liveActivations(session.customerId)
  return NextResponse.json({
    ok: true,
    activations: rows.map((r) => ({
      activation_id: r.activation_id,
      agent: r.agent_code,
      paused: r.status === 'paused',
      paused_at: r.paused_at,
    })),
  })
}

export async function POST(req: NextRequest) {
  const identity = await getCustomerIdentity()
  // Cookie OR mobile bearer.
  const session = { customerId: identity?.customerId ?? null }
  if (!session.customerId) {
    const e = errorEnvelope('UNAUTHORIZED', 'Please sign in to continue.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  if (!isCustomersDbConfigured()) {
    const e = errorEnvelope('NOT_CONFIGURED', 'Automation controls are temporarily unavailable.')
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const body = (await req.json().catch(() => ({}))) as { paused?: unknown; agent?: unknown }
  if (typeof body.paused !== 'boolean') {
    const e = errorEnvelope('VALIDATION_FAILED', 'Send { "paused": true } or { "paused": false }.', { field: 'paused' })
    return NextResponse.json(e, { status: statusFor(e.code) })
  }
  const agent = typeof body.agent === 'string' ? body.agent.toLowerCase() : null
  if (agent !== null && agent !== 'spark' && agent !== 'flame') {
    const e = errorEnvelope('VALIDATION_FAILED', 'Unknown agent.', { field: 'agent' })
    return NextResponse.json(e, { status: statusFor(e.code) })
  }

  const nextStatus = body.paused ? 'paused' : 'active'
  const updated = await customerExecute(
    `UPDATE activations a
        SET status = $2,
            paused_at = CASE WHEN $2 = 'paused' THEN now() ELSE a.paused_at END,
            updated_at = now()
       FROM agent_configs ac
      WHERE ac.id = a.config_id
        AND ac.user_id = $1
        AND a.status IN ('active', 'paused')
        AND a.status IS DISTINCT FROM $2
        AND ($3::text IS NULL OR ac.agent_code = $3)`,
    [session.customerId, nextStatus, agent],
  )

  if (updated > 0) {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, metadata) VALUES ($1, $2, $3)`,
      [session.customerId, body.paused ? 'AUTOMATION_PAUSED' : 'AUTOMATION_RESUMED', JSON.stringify({ agent: agent ?? 'all' })],
    ).catch(() => {})
    // Only mirror a real transition. The UPDATE's `status IS DISTINCT FROM` guard means
    // updated === 0 is a no-op re-click, and re-publishing Paused on those would restamp the
    // lifecycle every time the customer opened the page.
    await mirrorPauseToCrm(session.customerId, agent, body.paused)
  }

  const rows = await liveActivations(session.customerId)
  return NextResponse.json({
    ok: true,
    updated,
    activations: rows.map((r) => ({
      activation_id: r.activation_id,
      agent: r.agent_code,
      paused: r.status === 'paused',
      paused_at: r.paused_at,
    })),
  })
}
