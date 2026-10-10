import { NextRequest, NextResponse } from 'next/server'
import { getCustomerIdentity } from '@/lib/auth/customer-identity'
import { CustomersDbNotConfiguredError } from '@/lib/customers-db'
import { getMessageAuthor, reportMessage, REPORT_REASONS, type ReportReason } from '@/lib/community/store'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Report a message — Google Play's UGC policy requires this to exist in-app.
 *
 * Deliberately NOT gated on membership. Posting costs $15/mo, but reading the feed
 * is open, and a policy control that only paying members can reach is not a control.
 * A session is still required so a report is attributable and rate-limited by identity.
 */
export async function POST(req: NextRequest) {
  try {
    const identity = await getCustomerIdentity()
    const customerId = identity?.customerId ?? null
    if (!customerId) {
      return NextResponse.json({ error: 'Log in to report a message.' }, { status: 401 })
    }

    const body = await req.json().catch(() => ({}))
    const messageId = typeof body.message_id === 'string' ? body.message_id : ''
    const reason = typeof body.reason === 'string' ? body.reason.toUpperCase() : 'OTHER'
    if (!messageId) {
      return NextResponse.json({ error: 'A message is required.' }, { status: 400 })
    }
    if (!REPORT_REASONS.includes(reason as ReportReason)) {
      return NextResponse.json({ error: 'Unknown report reason.' }, { status: 400 })
    }

    const author = await getMessageAuthor(messageId)
    if (!author) {
      // Already gone — treat as success so the reporter is not told to try again
      // on something that no longer exists.
      return NextResponse.json({ status: 'success', result: 'already_removed' })
    }
    if (author.userId === customerId) {
      return NextResponse.json({ error: 'You cannot report your own message.' }, { status: 400 })
    }

    const result = await reportMessage({
      messageId,
      reporterId: customerId,
      reason: reason as ReportReason,
      author,
    })
    return NextResponse.json({ status: 'success', result })
  } catch (e) {
    if (e instanceof CustomersDbNotConfiguredError) {
      return NextResponse.json({ error: 'Community is not available yet.' }, { status: 503 })
    }
    console.error('[community] POST report failed:', e)
    return NextResponse.json({ error: 'Failed to report the message.' }, { status: 500 })
  }
}
