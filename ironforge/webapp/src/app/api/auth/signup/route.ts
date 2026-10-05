import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { validateSignup, type SignupPayload } from '@/lib/signup-validation'
import { hashPassword } from '@/lib/auth/password'
import { lookupPromo } from '@/lib/promo'
import { createCustomerAccount, writeAudit, clientIpFromHeaders, maskEmail } from '@/lib/auth/create-customer'
import { isCustomersDbConfigured, customerQuery } from '@/lib/customers-db'
import { isEnrollmentClosed, enrollmentClosedResponse } from '@/lib/enrollment-mode'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Account Creation (sub-project C) — persists a real prospect into the
 * `ironforge-customers` DB. Response contract matches the Phase-B stub so the
 * /signup client form is unchanged. The actual INSERT + audit + verification email
 * + Attio/CRM side effects live in lib/auth/create-customer.ts, shared with the
 * Google SSO callback (/api/auth/google/callback) so both signup paths create the
 * identical row shape — see that module's header.
 */

export async function POST(req: NextRequest) {
  // Enrollment closed: reject account creation server-side (handoff §4/§11 — the
  // overlay is not the security control). THE primary create path.
  if (isEnrollmentClosed()) return enrollmentClosedResponse()

  let body: Partial<SignupPayload>
  try {
    body = (await req.json()) as Partial<SignupPayload>
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid request body.' }, { status: 400 })
  }

  const payload: SignupPayload = {
    firstName: String(body.firstName ?? ''),
    lastName: String(body.lastName ?? ''),
    username: String(body.username ?? ''),
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

  // Pre-signup plan intent from a CTA (?plan/?bot) — allowlisted, never trusted as
  // more than a routing hint (audit M9).
  const rawIntent = (body as { intendedPlan?: unknown }).intendedPlan
  const intendedPlan = rawIntent === 'community' || rawIntent === 'automate' ? rawIntent : null

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

  const ip = clientIpFromHeaders(req.headers.get('x-forwarded-for'))
  const ua = req.headers.get('user-agent')
  const n = result.normalized
  // Founding promo (e.g. FORGE50). Validated against the static list; stored
  // canonical (UPPERCASE) or null. Honoured at activation — see lib/promo.ts.
  const promoCode = lookupPromo((body as { promoCode?: string }).promoCode)?.code ?? null

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

    // Username uniqueness is case-insensitive (unique index on lower(username)).
    // This pre-check gives the form a field error; the index is the enforcement.
    const existingUsername = await customerQuery<{ id: string }>(
      `SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1`,
      [n.username],
    )
    if (existingUsername.length > 0) {
      return NextResponse.json(
        { ok: false, fields: { username: 'That username is taken — try another.' }, error: 'That username is taken.' },
        { status: 400 },
      )
    }

    const passwordHash = await hashPassword(payload.password)

    const { userId: _userId, verifyToken, verifyCode } = await createCustomerAccount({
      firstName: n.firstName,
      lastName: n.lastName,
      username: n.username,
      email: n.email,
      phone: n.phone,
      state: n.state,
      passwordHash,
      authProvider: 'password',
      authUserId: null,
      referralCode: n.referralCode || null,
      promoCode,
      intendedPlan,
      ageConfirmed: payload.ageConfirmed,
      noAdviceAcknowledged: payload.noAdviceAcknowledged,
      electronicCommConsent: payload.electronicCommConsent,
      emailVerified: false,
      ip,
      userAgent: ua,
      source: 'signup',
      publicOrigin: publicOrigin(req),
    })

    const resBody: { ok: true; verifyUrl?: string; verifyCode?: string } = { ok: true }
    if (process.env.NODE_ENV !== 'production' && verifyToken) {
      resBody.verifyUrl = `/api/auth/verify?token=${encodeURIComponent(verifyToken)}`
      resBody.verifyCode = verifyCode
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
