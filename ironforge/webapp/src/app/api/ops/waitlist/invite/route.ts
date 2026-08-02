import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { customerQuery, customerExecute, isCustomersDbConfigured } from '@/lib/customers-db'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { isEmailConfigured, sendWaitlistInvitation } from '@/lib/email'
import { publicOrigin } from '@/lib/public-origin'

/**
 * Invite waitlist leads into enrollment.
 *
 * GET  — the invite queue: uninvited waitlist rows, newest first, so an operator can see who is
 *        waiting before sending anything.
 * POST — {"submissionIds": ["wl_…", …]} sends the invitation, stamps invited_at/invited_by, and
 *        emits crm.invitation_sent → customer_lifecycle = 'Invited'.
 *
 * Why this endpoint exists: the CRM spec makes "Invitation sent" a P0 integration event and
 * Invited a lifecycle status, but no invitation mechanism existed anywhere in the product. With
 * enrollment closed behind ENROLLMENT_WAITLIST_MODE there was also no path back in for a
 * specific lead, so the Enrollment Pipeline's Invited column could never be populated by
 * anything. This is the missing half of the enrollment gate.
 *
 * SAFETY — this sends real email to real prospects:
 *   - Operator session or service token. Never public.
 *   - Idempotent on invited_at: an already-invited lead is reported as skipped, never re-sent.
 *     The UPDATE claims the row (WHERE invited_at IS NULL) BEFORE the send, so two concurrent
 *     operators cannot both invite the same person.
 *   - Explicit id list only. There is deliberately no "invite everyone" switch — a bulk blast
 *     is not something that should be one fat-fingered request away.
 *   - A send failure releases the claim so the lead can be retried.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/** Sending more than this in one request is almost certainly a mistake, not an intent. */
const MAX_PER_REQUEST = 50

interface WaitlistRow {
  submission_id: string
  email: string
  first_name: string
}

async function gate(req: NextRequest): Promise<NextResponse | null> {
  const ops = await getSession()
  const viaToken = hasValidServiceToken(req.headers.get('x-ironforge-service'))
  if (!ops.userId && !viaToken) {
    return NextResponse.json({ ok: false, error: 'Operator session or service token required.' }, { status: 401 })
  }
  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'CUSTOMERS_DATABASE_URL is not set.' }, { status: 503 })
  }
  return null
}

export async function GET(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked

  const pending = await customerQuery<Record<string, unknown>>(
    `SELECT submission_id, email, first_name, last_name, city, state,
            trading_capital_range, created_at, attio_status
       FROM waitlist_submissions
      WHERE invited_at IS NULL
      ORDER BY created_at DESC
      LIMIT 200`,
  )
  const invitedCount = await customerQuery<{ n: string }>(
    `SELECT count(*)::text AS n FROM waitlist_submissions WHERE invited_at IS NOT NULL`,
  )

  return NextResponse.json({
    ok: true,
    pending,
    pendingCount: pending.length,
    invitedCount: Number(invitedCount[0]?.n ?? 0),
  })
}

export async function POST(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked

  const ops = await getSession()
  const actor = ops.userId ? `operator:${ops.userId}` : 'service-token'

  const body = (await req.json().catch(() => ({}))) as { submissionIds?: unknown }
  const ids = Array.isArray(body.submissionIds)
    ? body.submissionIds.filter((v): v is string => typeof v === 'string' && v.trim().length > 0)
    : []

  if (ids.length === 0) {
    return NextResponse.json(
      { ok: false, error: 'submissionIds must be a non-empty array of waitlist submission ids.' },
      { status: 400 },
    )
  }
  if (ids.length > MAX_PER_REQUEST) {
    return NextResponse.json(
      { ok: false, error: `Refusing to invite ${ids.length} leads in one request (max ${MAX_PER_REQUEST}).` },
      { status: 400 },
    )
  }

  const enrollUrl = `${publicOrigin(req)}/enroll`
  const invited: string[] = []
  const skipped: string[] = []
  const failed: Array<{ submissionId: string; error: string }> = []

  for (const submissionId of ids) {
    // Claim FIRST. The invited_at IS NULL predicate is what makes this idempotent and
    // concurrency-safe: whoever wins the UPDATE owns the send.
    const claimed = await customerQuery<WaitlistRow>(
      `UPDATE waitlist_submissions
          SET invited_at = now(), invited_by = $2, updated_at = now()
        WHERE submission_id = $1 AND invited_at IS NULL
        RETURNING submission_id, email, first_name`,
      [submissionId, actor],
    )
    if (claimed.length === 0) {
      skipped.push(submissionId)
      continue
    }

    const row = claimed[0]
    const sent = await sendWaitlistInvitation({
      to: row.email,
      firstName: row.first_name,
      enrollUrl,
    })

    if (!sent.sent && !sent.skipped) {
      // Release the claim so this lead can be retried rather than silently never invited.
      await customerExecute(
        `UPDATE waitlist_submissions SET invited_at = NULL, invited_by = NULL, updated_at = now()
          WHERE submission_id = $1`,
        [submissionId],
      ).catch(() => {})
      failed.push({ submissionId, error: sent.error ?? 'send failed' })
      continue
    }

    await enqueueCrmEvent({
      eventId: `invite_${submissionId}`,
      eventType: 'crm.invitation_sent',
      correlationId: submissionId,
      payload: {
        email: row.email,
        firstName: row.first_name,
        invitedAt: new Date().toISOString(),
        invitedBy: actor,
      },
    })
    invited.push(submissionId)
  }

  return NextResponse.json({
    ok: failed.length === 0,
    invited,
    skipped,
    failed,
    // Surfaced explicitly: when email isn't configured the lifecycle still advances to Invited,
    // which would otherwise look like a successful send that nobody received.
    emailConfigured: isEmailConfigured(),
  })
}
