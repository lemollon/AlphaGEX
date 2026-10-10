import { NextRequest, NextResponse } from 'next/server'
import { isCustomersDbConfigured, customerExecute } from '@/lib/customers-db'
import { parseResendEvent, isHardBounce, verifySvixSignature, SUPPRESSING_EVENT_TYPES } from '@/lib/waitlist-drip/resend-webhook'
import { suppressSequenceByEmail } from '@/lib/waitlist-drip/sequence'

/**
 * POST /api/email/webhook/resend — Resend delivery events (no session; Svix-signed).
 *
 * Paste this URL into the Resend dashboard (Webhooks → Add) with at least `email.bounced`
 * and `email.complained` selected, and put the signing secret it shows in
 * RESEND_WEBHOOK_SECRET on ironforge-customer.
 *
 * FAILS CLOSED: an unset secret or a bad signature is 401 and nothing is stored. An attacker
 * who could post unsigned bounces could silence the whole waitlist, so "not configured"
 * means "not accepting".
 *
 * Every verified event is stored in email_events keyed on the Svix message id (replays
 * insert nothing). A Permanent bounce or a complaint then suppresses the address's sequence
 * row immediately — and the drain re-checks email_events before every send anyway, so even
 * a row missed here is caught at send time.
 *
 * Always 200 after a valid signature, even for event types we ignore, so Resend does not
 * retry-storm on the events we did not subscribe to.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

export async function POST(req: NextRequest) {
  const raw = await req.text().catch(() => '')
  const verdict = verifySvixSignature(
    {
      id: req.headers.get('svix-id'),
      timestamp: req.headers.get('svix-timestamp'),
      signature: req.headers.get('svix-signature'),
    },
    raw,
  )
  if (!verdict.ok) {
    if (verdict.reason === 'secret_unset') {
      console.error('[email/webhook] RESEND_WEBHOOK_SECRET unset — rejecting webhook (fail closed)')
    }
    return NextResponse.json({ ok: false, error: verdict.reason }, { status: 401 })
  }

  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, error: 'CUSTOMERS_DATABASE_URL is not set.' }, { status: 503 })
  }

  let body: unknown = null
  try {
    body = JSON.parse(raw)
  } catch {
    return NextResponse.json({ ok: false, error: 'invalid json' }, { status: 400 })
  }
  const event = parseResendEvent(body)
  if (!event) return NextResponse.json({ ok: true, ignored: true })

  const svixId = req.headers.get('svix-id') as string
  let stored = 0
  let suppressed = 0
  for (let i = 0; i < event.emails.length; i++) {
    const email = event.emails[i]
    // One row per recipient; the Svix id is per message, so suffix it for multi-recipient sends.
    const providerEventId = event.emails.length === 1 ? svixId : `${svixId}:${i}`
    const inserted = await customerExecute(
      `INSERT INTO email_events (provider, provider_event_id, event_type, email, message_id, bounce_type, payload)
       VALUES ('resend', $1, $2, $3, $4, $5, $6::jsonb)
       ON CONFLICT (provider_event_id) DO NOTHING`,
      [providerEventId, event.type, email, event.messageId, event.bounceType, JSON.stringify(body)],
    ).catch((e) => {
      console.error('[email/webhook] store failed:', e)
      return 0
    })
    stored += inserted
    if (SUPPRESSING_EVENT_TYPES.has(event.type)) {
      const reason = event.type === 'email.complained' ? 'complaint' : isHardBounce(event) ? 'hard_bounce' : null
      if (reason) {
        suppressed += await suppressSequenceByEmail(email, reason).catch((e) => {
          console.error('[email/webhook] suppress failed:', e)
          return 0
        })
      }
    }
  }
  return NextResponse.json({ ok: true, type: event.type, stored, suppressed })
}
