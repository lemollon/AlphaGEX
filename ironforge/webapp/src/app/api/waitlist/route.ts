import { NextRequest, NextResponse } from 'next/server'
import { createHash, randomUUID } from 'crypto'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'
import { validateWaitlist, CONSENT_VERSION, WAITLIST_SOURCE } from '@/lib/waitlist'
import { upsertWaitlistToAttio } from '@/lib/attio'
import { enqueueCrmEvent } from '@/lib/crm/outbox'
import { CAPITAL_RANGE_TO_VOLUME, toLeadSource } from '@/lib/crm/schema'
import { sendWaitlistConfirmation } from '@/lib/email'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * POST /api/waitlist (8/26 handoff). Public, unauthenticated.
 *
 * Order of operations (reliability §): validate → rate-limit/bot-check → persist the
 * lead LOCALLY (never lost to an outage) → queue the CRM event → best-effort inline Attio
 * upsert → send the confirmation email asynchronously. Email failure never discards the
 * submission.
 *
 * CHANGED with the CRM outbox: an Attio failure no longer returns 503. The original design
 * made Attio success a precondition for 2xx, which meant a transient CRM blip told a real
 * prospect "we could not save your request" — after the lead had already been saved — and
 * nothing ever retried the sync. Delivery is now durable and retried, so 2xx is the truthful
 * answer: the lead IS captured. Only a local-persist failure still 503s, because that is the
 * one case where the lead really is lost.
 */

const RATE_IP_MAX = 5 // per 15 min
const RATE_IP_WINDOW_MIN = 15
const RATE_EMAIL_MAX = 3 // per day

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

// Campaign/referral attribution (handoff §5). Whitelisted, length-capped strings
// only — never trust raw client metadata into storage. Returns null when empty.
const CAMPAIGN_KEYS = [
  'utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term',
  'referralCode', 'landingPath',
] as const
function sanitizeCampaign(raw: unknown): Record<string, string> | null {
  if (!raw || typeof raw !== 'object') return null
  const src = raw as Record<string, unknown>
  const out: Record<string, string> = {}
  for (const k of CAMPAIGN_KEYS) {
    const v = src[k]
    if (typeof v === 'string') {
      const s = v.trim().slice(0, 200)
      if (s) out[k] = s
    }
  }
  return Object.keys(out).length > 0 ? out : null
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
  const campaign = sanitizeCampaign((body as Record<string, unknown>).campaign)
  const campaignJson = campaign ? JSON.stringify(campaign) : null

  // 1) Persist locally FIRST — the lead survives any downstream outage. Email is the
  //    dedupe key: a resubmit updates the row (and returns existing:true).
  let existing = false
  let alreadyEmailed = false
  /**
   * The campaign as STORED, which is not necessarily the one just submitted: the upsert
   * COALESCEs so a resubmit carrying no attribution keeps the original. The CRM event must use
   * this, not the incoming request — see the enqueue below.
   */
  let storedCampaign: Record<string, unknown> | null = campaign
  try {
    const rows = await customerQuery<{ existed: boolean; email_status: string; campaign: Record<string, unknown> | null }>(
      `INSERT INTO waitlist_submissions
         (submission_id, email, first_name, last_name, phone, city, state,
          trading_capital_range, consent, consent_version, source, ip_hash, campaign)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,TRUE,$9,$10,$11,$12::jsonb)
       ON CONFLICT (lower(email)) DO UPDATE SET
         first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name,
         phone = EXCLUDED.phone, city = EXCLUDED.city, state = EXCLUDED.state,
         trading_capital_range = EXCLUDED.trading_capital_range,
         consent_version = EXCLUDED.consent_version, consent_at = now(),
         ip_hash = EXCLUDED.ip_hash,
         -- keep earlier attribution if this resubmit carried none (§6: append, don't delete)
         campaign = COALESCE(EXCLUDED.campaign, waitlist_submissions.campaign),
         updated_at = now()
       RETURNING (xmax <> 0) AS existed, email_status, campaign`,
      [submissionId, n.email, n.firstName, n.lastName, n.phone, n.city, n.state,
       n.tradingCapitalRange, CONSENT_VERSION, WAITLIST_SOURCE, iph, campaignJson],
    )
    existing = rows[0]?.existed === true
    // Idempotent confirmation (handoff §7): don't re-send to someone already
    // confirmed. A prior FAILED/pending send still re-sends on resubmit.
    alreadyEmailed = rows[0]?.email_status === 'sent'
    storedCampaign = rows[0]?.campaign ?? null
  } catch (e) {
    console.error('[waitlist] local persist failed:', e)
    return NextResponse.json({ ok: false, code: 'INTEGRATION_ERROR', message: 'We could not save your request. Please try again.' }, { status: 503 })
  }

  // 2) CRM. The outbox is the DURABLE path: enqueue first, so the event survives an Attio
  //    outage, a bad deploy, or an unset API key and is retried until it lands (AC-CRM-010).
  //    The inline upsert below is only a latency optimisation on top of it.
  await enqueueCrmEvent({
    eventId: submissionId,
    eventType: 'crm.waitlist_submitted',
    correlationId: submissionId,
    payload: {
      email: n.email,
      firstName: n.firstName,
      lastName: n.lastName,
      phone: n.phone,
      city: n.city,
      state: n.state,
      tradingVolume: CAPITAL_RANGE_TO_VOLUME[n.tradingCapitalRange],
      // Derived from the STORED campaign, never the incoming one. Verified live on 8/2: a
      // resubmit with no campaign data recomputed lead_source from the empty request and
      // overwrote the original 'LinkedIn' attribution with 'Organic'. The SQL above already
      // guards against exactly this with COALESCE; reading the request instead of the returned
      // row bypassed that guard.
      leadSource: toLeadSource(storedCampaign),
      marketingConsent: true,
      waitlistDate: new Date().toISOString(),
    },
  })

  // Fast path: try the write inline so a normal submission appears in Attio immediately and we
  // can record the person id locally. A failure here is NOT fatal — the lead is already saved
  // and already queued.
  const attio = await upsertWaitlistToAttio({
    firstName: n.firstName, lastName: n.lastName, email: n.email, phone: n.phone,
    city: n.city, state: n.state, tradingCapitalRange: n.tradingCapitalRange,
    consentVersion: CONSENT_VERSION, submissionId,
  })
  if (attio.synced) {
    await customerExecute(
      `UPDATE waitlist_submissions SET attio_status='synced', attio_person_id=$2, updated_at=now() WHERE lower(email)=lower($1)`,
      [n.email, attio.recordId ?? null],
    ).catch(() => {})
  } else {
    // Previously this stamped 'synced' with a NULL person id whenever Attio was merely SKIPPED
    // (ATTIO_API_KEY unset) — the DB claimed every lead was in the CRM while nothing had been
    // sent. 'queued' is the honest state: not in Attio yet, delivery owned by the outbox.
    if (!attio.skipped) console.error('[waitlist] inline attio upsert failed (queued for retry):', attio.error)
    await customerExecute(
      `UPDATE waitlist_submissions SET attio_status='queued', updated_at=now() WHERE lower(email)=lower($1)`,
      [n.email],
    ).catch(() => {})
  }

  // 3) Confirmation email — async, best-effort, sent ONCE per confirmed prospect.
  //    A failure never discards the lead; a resubmit after a failed send retries.
  if (!alreadyEmailed) {
    void sendWaitlistConfirmation({ to: n.email, firstName: n.firstName })
      .then((r) =>
        customerExecute(
          `UPDATE waitlist_submissions SET email_status=$2, updated_at=now() WHERE lower(email)=lower($1)`,
          [n.email, r.sent ? 'sent' : r.skipped ? 'pending' : 'failed'],
        ).catch(() => {}),
      )
      .catch(() => {})
  }

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
