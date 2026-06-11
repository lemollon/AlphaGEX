import { NextRequest, NextResponse } from 'next/server'
import { validateSignup, type SignupPayload } from '@/lib/signup-validation'
import { hashPassword } from '@/lib/auth/password'
import { generateToken, TOKEN_TTL_MS } from '@/lib/auth/verification-token'
import { sendVerificationEmail } from '@/lib/email'
import { syncContactToAttio, enqueueAttioSync } from '@/lib/attio'
import {
  isCustomersDbConfigured,
  customerQuery,
  customerExecute,
  customerTransaction,
} from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Account Creation (sub-project C) — persists a real prospect into the
 * `ironforge-customers` DB. Response contract matches the Phase-B stub so the
 * /signup client form is unchanged. Email send (D) and Attio sync (E) are wired
 * in below as best-effort steps that never block account creation.
 */

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!domain) return '***'
  return `${local.slice(0, 1)}***@${domain}`
}

async function writeAudit(
  userId: string | null,
  eventType: string,
  ip: string | null,
  ua: string | null,
  metadata: Record<string, unknown>,
): Promise<void> {
  // Best-effort: audit failures must never block the user (doc §5).
  try {
    await customerExecute(
      `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
       VALUES ($1, $2, $3, $4, $5)`,
      [userId, eventType, ip, ua, JSON.stringify(metadata)],
    )
  } catch (e) {
    console.error('[signup] audit write failed:', eventType, e)
  }
}

export async function POST(req: NextRequest) {
  let body: Partial<SignupPayload>
  try {
    body = (await req.json()) as Partial<SignupPayload>
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid request body.' }, { status: 400 })
  }

  const payload: SignupPayload = {
    firstName: String(body.firstName ?? ''),
    lastName: String(body.lastName ?? ''),
    email: String(body.email ?? ''),
    phone: String(body.phone ?? ''),
    state: String(body.state ?? ''),
    password: String(body.password ?? ''),
    confirmPassword: String(body.confirmPassword ?? ''),
    referralCode: String(body.referralCode ?? ''),
    ageConfirmed: Boolean(body.ageConfirmed),
    noAdviceAcknowledged: Boolean(body.noAdviceAcknowledged),
    electronicCommConsent: Boolean(body.electronicCommConsent),
  }

  const result = validateSignup(payload)
  if (!result.ok) {
    return NextResponse.json(
      { ok: false, error: 'Please correct the highlighted fields.', fields: result.errors },
      { status: 400 },
    )
  }

  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Account creation is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const ip = clientIp(req)
  const ua = req.headers.get('user-agent')
  const n = result.normalized

  try {
    const existing = await customerQuery<{ id: string }>(
      `SELECT id FROM users WHERE email = $1 LIMIT 1`,
      [n.email],
    )
    if (existing.length > 0) {
      await writeAudit(null, 'DUPLICATE_EMAIL_ATTEMPT', ip, ua, { email_masked: maskEmail(n.email) })
      return NextResponse.json(
        {
          ok: false,
          code: 'duplicate_email',
          error:
            'This email is already associated with an IronForge account. Log in or reset your password.',
        },
        { status: 409 },
      )
    }

    const passwordHash = await hashPassword(payload.password)
    const { raw: rawToken, hash: tokenHash } = generateToken()
    const expiresAt = new Date(Date.now() + TOKEN_TTL_MS).toISOString()

    const userId = await customerTransaction<string>(async (run) => {
      const rows = await run(
        `INSERT INTO users
           (password_hash, first_name, last_name, email, phone, state, referral_code,
            age_confirmed, no_advice_acknowledged, electronic_comm_consent)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
         RETURNING id`,
        [
          passwordHash,
          n.firstName,
          n.lastName,
          n.email,
          n.phone,
          n.state,
          n.referralCode || null,
          payload.ageConfirmed,
          payload.noAdviceAcknowledged,
          payload.electronicCommConsent,
        ],
      )
      const uid = rows[0].id as string
      await run(
        `INSERT INTO email_verification_tokens (user_id, token_hash, expires_at)
         VALUES ($1,$2,$3)`,
        [uid, tokenHash, expiresAt],
      )
      return uid
    })

    await writeAudit(userId, 'ACCOUNT_CREATED', ip, ua, {
      source: 'signup',
      state: n.state,
      referral_code: n.referralCode || null,
      age_confirmed: payload.ageConfirmed,
      no_advice_acknowledged: payload.noAdviceAcknowledged,
      electronic_comm_consent: payload.electronicCommConsent,
    })

    // Send the verification email (non-blocking: failure never blocks the account).
    const verifyUrl = `${req.nextUrl.origin}/api/auth/verify?token=${encodeURIComponent(rawToken)}`
    try {
      const emailRes = await sendVerificationEmail({ to: n.email, verifyUrl, firstName: n.firstName })
      if (emailRes.sent) {
        await writeAudit(userId, 'EMAIL_VERIFICATION_SENT', ip, ua, { email_masked: maskEmail(n.email) })
      } else if (emailRes.error) {
        console.error('[signup] verification email failed:', emailRes.error)
      }
    } catch (e) {
      console.error('[signup] verification email threw:', e)
    }

    // Sub-project E: mirror the prospect into Attio CRM (best-effort; never blocks
    // the account). On failure, queue for retry + record an ATTIO_SYNC_FAILED audit.
    try {
      const contact = {
        firstName: n.firstName,
        lastName: n.lastName,
        email: n.email,
        phone: n.phone,
        state: n.state,
        referralCode: n.referralCode || undefined,
      }
      const attioRes = await syncContactToAttio(contact)
      if (attioRes.synced) {
        await writeAudit(userId, 'ATTIO_SYNCED', ip, ua, { record_id: attioRes.recordId ?? null })
      } else if (!attioRes.skipped) {
        await enqueueAttioSync(userId, contact, attioRes.error ?? 'unknown')
        await writeAudit(userId, 'ATTIO_SYNC_FAILED', ip, ua, {
          error: (attioRes.error ?? '').slice(0, 200),
        })
      }
    } catch (e) {
      console.error('[signup] attio sync threw:', e)
    }

    const resBody: { ok: true; verifyUrl?: string } = { ok: true }
    if (process.env.NODE_ENV !== 'production') {
      resBody.verifyUrl = `/api/auth/verify?token=${encodeURIComponent(rawToken)}`
    }
    return NextResponse.json(resBody)
  } catch (e) {
    console.error('[signup] account creation failed:', e)
    return NextResponse.json(
      { ok: false, error: 'Something went wrong creating your account. Please try again.' },
      { status: 500 },
    )
  }
}
