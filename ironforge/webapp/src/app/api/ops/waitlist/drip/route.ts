import { NextRequest, NextResponse } from 'next/server'
import { getSession } from '@/lib/auth/server'
import { hasValidServiceToken } from '@/lib/auth/session'
import { customerQuery, isCustomersDbConfigured } from '@/lib/customers-db'
import { isEmailConfigured, sendEmail } from '@/lib/email'
import { publicOriginFromEnv } from '@/lib/public-origin'
import { DRIP_EMAILS, DRIP_FINAL_STAGE } from '@/lib/waitlist-drip/copy'
import { drainWaitlistDrip, dripLinks, sendPreconditionBlocker } from '@/lib/waitlist-drip/drain'
import { businessAddressFromEnv, renderDripEmail } from '@/lib/waitlist-drip/render'
import { defaultFirstSendDate, firstSendAt, formatCT, isDateKey, sendHourCT, DRIP_TIMEZONE } from '@/lib/waitlist-drip/schedule'
import { backfillWaitlistSequence } from '@/lib/waitlist-drip/sequence'

/**
 * Waitlist drip operations. Operator session or service token — same gate as /api/ops/crm/*.
 *
 * GET — status: counts per stage and status, the next 20 due sends, recent sends, recent
 *       failures, and the send-precondition blocker (business address / origin / Resend) so
 *       a missing env var is visible here before anyone fires the backfill.
 *
 * POST {"action":"backfill","firstSendDate":"YYYY-MM-DD","dryRun":true}
 *       Seeds a sequence row for every waitlist submission that has none, with Email 1 due at
 *       the send hour (CT) on firstSendDate (deferred to the next business day if needed).
 *       Default firstSendDate = the next business day strictly after today (Chicago) — the
 *       backfill can never cause a same-day send unless the date is passed explicitly.
 *       dryRun (default TRUE — an omitted flag never sends) reports counts and writes nothing.
 *       Idempotent: rows that already exist are never touched.
 *
 * POST {"action":"drain","limit":25}   — run one drain tick now (same code as the scanner).
 * POST {"action":"preview","stage":3,"firstName":"Ada"} — rendered subject/html/text, no send.
 * POST {"action":"test-send","to":"you@example.com","stage":1,"firstName":"Ada"}
 *       Sends ONE rendered email to an explicit address (an operator's own inbox) so the
 *       template can be checked in a real client. Never touches the waitlist. Uses a
 *       throwaway token, so the footer links 404 by design.
 */
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

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

  const [byStatus, byStage, due, recentSends, recentFailures, suppressedByReason, waitlist, prefs, events] =
    await Promise.all([
      customerQuery<{ status: string; n: string }>(`SELECT status, count(*)::text AS n FROM waitlist_sequence GROUP BY status`),
      customerQuery<{ stage: number; n: string }>(`SELECT stage, count(*)::text AS n FROM waitlist_sequence GROUP BY stage ORDER BY stage`),
      customerQuery<Record<string, unknown>>(
        `SELECT id, email, first_name, stage + 1 AS next_stage, next_send_at, send_attempts, last_error
           FROM waitlist_sequence
          WHERE status = 'active' AND next_send_at IS NOT NULL
          ORDER BY next_send_at ASC
          LIMIT 20`,
      ),
      customerQuery<Record<string, unknown>>(
        `SELECT s.email, l.stage, l.status, l.resend_message_id, l.sent_at
           FROM waitlist_sequence_sends l JOIN waitlist_sequence s ON s.id = l.sequence_id
          ORDER BY l.sent_at DESC LIMIT 20`,
      ),
      customerQuery<Record<string, unknown>>(
        `SELECT id, email, stage, send_attempts, last_error, updated_at
           FROM waitlist_sequence WHERE status = 'failed' ORDER BY updated_at DESC LIMIT 20`,
      ),
      customerQuery<{ reason: string; n: string }>(
        `SELECT COALESCE(suppression_reason, 'unknown') AS reason, count(*)::text AS n
           FROM waitlist_sequence WHERE status = 'suppressed' GROUP BY 1`,
      ),
      customerQuery<{ n: string; not_enrolled: string }>(
        `SELECT count(*)::text AS n,
                count(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM waitlist_sequence s WHERE lower(s.email) = lower(w.email)))::text AS not_enrolled
           FROM waitlist_submissions w`,
      ),
      customerQuery<{ n: string }>(`SELECT count(*)::text AS n FROM email_preferences WHERE unsubscribed`),
      customerQuery<{ event_type: string; n: string }>(`SELECT event_type, count(*)::text AS n FROM email_events GROUP BY 1`),
    ])

  const now = new Date()
  const nextDefault = defaultFirstSendDate(now)
  return NextResponse.json({
    ok: true,
    now: now.toISOString(),
    nowCT: formatCT(now),
    config: {
      timezone: DRIP_TIMEZONE,
      sendHourCT: sendHourCT(),
      finalStage: DRIP_FINAL_STAGE,
      emailConfigured: isEmailConfigured(),
      businessAddressSet: !!businessAddressFromEnv(),
      publicOrigin: publicOriginFromEnv(),
      resendWebhookSecretSet: !!process.env.RESEND_WEBHOOK_SECRET,
      /** null = sends may proceed; otherwise the exact missing precondition. */
      sendBlocker: sendPreconditionBlocker(),
    },
    backfillDefault: {
      firstSendDate: nextDefault,
      firstSendAt: firstSendAt(nextDefault).toISOString(),
      firstSendAtCT: formatCT(firstSendAt(nextDefault)),
    },
    waitlist: { submissions: Number(waitlist[0]?.n ?? 0), notEnrolled: Number(waitlist[0]?.not_enrolled ?? 0) },
    counts: {
      byStatus: Object.fromEntries(byStatus.map((r) => [r.status, Number(r.n)])),
      byStage: Object.fromEntries(byStage.map((r) => [String(r.stage), Number(r.n)])),
      suppressedByReason: Object.fromEntries(suppressedByReason.map((r) => [r.reason, Number(r.n)])),
      unsubscribedAddresses: Number(prefs[0]?.n ?? 0),
      providerEvents: Object.fromEntries(events.map((r) => [r.event_type, Number(r.n)])),
    },
    nextDue: due.map((r) => ({ ...r, next_send_at_ct: r.next_send_at ? formatCT(new Date(String(r.next_send_at))) : null })),
    recentSends,
    failed: recentFailures,
  })
}

export async function POST(req: NextRequest) {
  const blocked = await gate(req)
  if (blocked) return blocked
  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  const action = typeof body.action === 'string' ? body.action : ''

  if (action === 'backfill') {
    const firstSendDate = body.firstSendDate
    if (firstSendDate !== undefined && !isDateKey(firstSendDate)) {
      return NextResponse.json({ ok: false, error: 'firstSendDate must be YYYY-MM-DD' }, { status: 400 })
    }
    // Default TRUE: an omitted flag must never be the thing that scheduled real mail.
    const dryRun = body.dryRun !== false
    const result = await backfillWaitlistSequence({ firstSendDate: firstSendDate as string | undefined, dryRun })
    return NextResponse.json({ ok: true, action, ...result, firstSendAtCT: formatCT(new Date(result.firstSendAt)) })
  }

  if (action === 'drain') {
    const limit = typeof body.limit === 'number' ? body.limit : 25
    const result = await drainWaitlistDrip({ limit })
    return NextResponse.json({ ok: true, action, ...result })
  }

  if (action === 'preview' || action === 'test-send') {
    const stage = Number(body.stage ?? 1)
    if (!DRIP_EMAILS.some((e) => e.stage === stage)) {
      return NextResponse.json({ ok: false, error: `stage must be 1-${DRIP_FINAL_STAGE}` }, { status: 400 })
    }
    const origin = publicOriginFromEnv() ?? 'https://example.invalid'
    const address = businessAddressFromEnv() || (action === 'preview' ? '[IRONFORGE_BUSINESS_ADDRESS unset]' : '')
    let rendered
    try {
      rendered = renderDripEmail({
        stage,
        firstName: typeof body.firstName === 'string' ? body.firstName : null,
        links: dripLinks(origin, 'preview-token-not-valid-'),
        businessAddress: address,
      })
    } catch (e) {
      return NextResponse.json({ ok: false, error: e instanceof Error ? e.message : 'render failed' }, { status: 409 })
    }
    if (action === 'preview') return NextResponse.json({ ok: true, action, ...rendered })

    const to = typeof body.to === 'string' ? body.to.trim() : ''
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(to)) {
      return NextResponse.json({ ok: false, error: '"to" must be an explicit email address' }, { status: 400 })
    }
    const blocker = sendPreconditionBlocker()
    if (blocker) return NextResponse.json({ ok: false, error: blocker }, { status: 409 })
    const sent = await sendEmail({
      to,
      subject: `[TEST ${stage}/${DRIP_FINAL_STAGE}] ${rendered.subject}`,
      html: rendered.html,
      text: rendered.text,
    })
    return NextResponse.json({ ok: sent.sent, action, to, stage, ...sent }, { status: sent.sent ? 200 : 502 })
  }

  return NextResponse.json(
    { ok: false, error: `unknown action "${action}" — expected backfill | drain | preview | test-send.` },
    { status: 400 },
  )
}
