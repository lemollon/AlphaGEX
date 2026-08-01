import { NextRequest, NextResponse } from 'next/server'
import { createHash, randomUUID } from 'crypto'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { validateWaitlist, CONSENT_VERSION, WAITLIST_SOURCE } from '@/lib/waitlist'
import { upsertWaitlistToAttio } from '@/lib/attio'
import { sendWaitlistConfirmation } from '@/lib/email'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/waitlist (8/26 handoff). Public, unauthenticated.
 *
 * Order of operations (reliability §): validate → rate-limit/bot-check → persist the
 * lead LOCALLY (never lost to an outage) → upsert Attio (system of record) → send the
 * confirmation email asynchronously. Success is returned only after Attio persists;
 * an Attio failure returns 503 but the local row + failed status let ops recover the
 * lead. Email failure never discards the submission.
 */

const RATE_IP_MAX = 5 // per 15 min
const RATE_IP_WINDOW_MIN = 15
const RATE_EMAIL_MAX = 3 // per day

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}
function ipHash(ip: string | null): string | null {
  return ip ? createHash('sha256').update(ip).digest('hex').slice(0, 32) : null
}

export async function POST(req: NextRequest) {
  if (!req.headers.get('content-type')?.includes('application/json')) {
    return NextResponse.json({ ok: false, code: 'BAD_REQUEST', message: 'JSON required.' }, { status: 415 })
  }
  const body = (await req.json().catch(() => null)) as Record<string, unknown> | null
  if (!body) {
    return NextResponse.json({ ok: false, code: 'BAD_REQUEST', message: 'Invalid request.' }, { status: 400 })
  }

  // Honeypot: a hidden field real users never fill. Silent success to not tip off bots.
  if (typeof body.company === 'string' && body.company.trim() !== '') {
    return NextResponse.json({ ok: true, submissionId: `wl_${randomUUID()}`, message: 'You are on the IronForge waitlist.' }, { status: 201 })
  }

  const parsed = validateWaitlist(body as Record<string, never>)
  if (!parsed.ok) {
    return NextResponse.json({ ok: false, code: 'VALIDATION_ERROR', fieldErrors: parsed.fieldErrors }, { status: 422 })
  }
  const n = parsed.data

  if (!isCustomersDbConfigured()) {
    return NextResponse.json({ ok: false, code: 'INTEGRATION_ERROR', message: 'We could not save your request. Please try again.' }, { status: 503 })
  }

  const iph = ipHash(clientIp(req))

  // Rate limits (handoff §10): per-IP 5/15min, per-email 3/day. Best-effort — a
  // counting failure must not block a legitimate lead, so it's caught.
  try {
    if (iph) {
      const ipCount = await customerQuery<{ c: string }>(
        `SELECT count(*)::int AS c FROM waitlist_submissions
          WHERE ip_hash = $1 AND created_at > now() - ($2 || ' minutes')::interval`,
        [iph, String(RATE_IP_WINDOW_MIN)],
      )
      if (Number(ipCount[0]?.c ?? 0) >= RATE_IP_MAX) {
        return NextResponse.json({ ok: false, code: 'RATE_LIMITED', message: 'Too many submissions. Please try again later.' }, { status: 429 })
      }
    }
    const emailCount = await customerQuery<{ c: string }>(
      `SELECT count(*)::int AS c FROM waitlist_submissions
        WHERE lower(email) = lower($1) AND created_at > now() - interval '1 day'`,
      [n.email],
    )
    // A same-email resubmit is an UPDATE (allowed); the cap guards abuse loops.
    if (Number(emailCount[0]?.c ?? 0) >= RATE_EMAIL_MAX) {
      return NextResponse.json({ ok: false, code: 'RATE_LIMITED', message: 'This email has already been submitted several times today.' }, { status: 429 })
    }
  } catch { /* fall through — never block a lead on a counting error */ }

  const submissionId = `wl_${randomUUID()}`

  // 1) Persist locally FIRST — the lead survives any downstream outage. Email is the
  //    dedupe key: a resubmit updates the row (and returns existing:true).
  let existing = false
  try {
    const rows = await customerQuery<{ existed: boolean }>(
      `INSERT INTO waitlist_submissions
         (submission_id, email, first_name, last_name, phone, city, state,
          trading_capital_range, consent, consent_version, source, ip_hash)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,TRUE,$9,$10,$11)
       ON CONFLICT (lower(email)) DO UPDATE SET
         first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name,
         phone = EXCLUDED.phone, city = EXCLUDED.city, state = EXCLUDED.state,
         trading_capital_range = EXCLUDED.trading_capital_range,
         consent_version = EXCLUDED.consent_version, consent_at = now(),
         ip_hash = EXCLUDED.ip_hash, updated_at = now()
       RETURNING (xmax <> 0) AS existed`,
      [submissionId, n.email, n.firstName, n.lastName, n.phone, n.city, n.state,
       n.tradingCapitalRange, CONSENT_VERSION, WAITLIST_SOURCE, iph],
    )
    existing = rows[0]?.existed === true
  } catch (e) {
    console.error('[waitlist] local persist failed:', e)
    return NextResponse.json({ ok: false, code: 'INTEGRATION_ERROR', message: 'We could not save your request. Please try again.' }, { status: 503 })
  }

  // 2) Attio — the system of record. Success is required for a 2xx (handoff §4).
  const attio = await upsertWaitlistToAttio({
    firstName: n.firstName, lastName: n.lastName, email: n.email, phone: n.phone,
    city: n.city, state: n.state, tradingCapitalRange: n.tradingCapitalRange,
    consentVersion: CONSENT_VERSION, submissionId,
  })
  if (!attio.synced && !attio.skipped) {
    await customerExecute(
      `UPDATE waitlist_submissions SET attio_status='failed', updated_at=now() WHERE lower(email)=lower($1)`,
      [n.email],
    ).catch(() => {})
    console.error('[waitlist] attio upsert failed:', attio.error)
    return NextResponse.json({ ok: false, code: 'INTEGRATION_ERROR', message: 'We could not save your request. Please try again.' }, { status: 503 })
  }
  await customerExecute(
    `UPDATE waitlist_submissions SET attio_status='synced', attio_person_id=$2, updated_at=now() WHERE lower(email)=lower($1)`,
    [n.email, attio.recordId ?? null],
  ).catch(() => {})

  // 3) Confirmation email — async, best-effort. A failure never discards the lead.
  void sendWaitlistConfirmation({ to: n.email, firstName: n.firstName })
    .then((r) =>
      customerExecute(
        `UPDATE waitlist_submissions SET email_status=$2, updated_at=now() WHERE lower(email)=lower($1)`,
        [n.email, r.sent ? 'sent' : r.skipped ? 'pending' : 'failed'],
      ).catch(() => {}),
    )
    .catch(() => {})

  return NextResponse.json(
    {
      ok: true,
      submissionId,
      existing,
      message: existing ? 'Your waitlist information has been updated.' : 'You are on the IronForge waitlist.',
    },
    { status: existing ? 200 : 201 },
  )
}
