import { NextRequest, NextResponse } from 'next/server'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { deriveUsernameBase } from '@/lib/auth/google-oauth'
import {
  verifyGooglePendingSignupState,
  GOOGLE_PENDING_SIGNUP_COOKIE,
  googlePendingSignupCookieOptions,
} from '@/lib/auth/google-pending-signup-cookie'
import { createCustomerAccount, writeAudit, clientIpFromHeaders } from '@/lib/auth/create-customer'
import { uniqueUsername } from '@/lib/auth/username'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Completes a Google sign-in that /api/auth/google/callback deferred because it
 * would have created a new account with no consents on file (started from
 * /login — see that route's header). The verified Google identity lives in the
 * signed, httpOnly, SameSite=Lax google-pending-signup cookie, never in this
 * request's body — so this route trusts the cookie for WHO, and the body only
 * for the 3 consent booleans a human just ticked on /signup/google-consent.
 *
 * CSRF: SameSite=Lax means the browser never attaches this cookie to a
 * cross-site POST, so a forged request from another origin arrives with no
 * cookie at all and fails the very first check. A same-site replay with a
 * tampered cookie value fails the HMAC check inside verifyGooglePendingSignupState.
 *
 * Re-runs the SAME identity-resolution the callback would have (by auth_user_id,
 * then by verified email) in case the account was created by some other route
 * during the few minutes this cookie was outstanding — never risk a duplicate row
 * or an accidental link to an unverified mailbox.
 */
interface UserRow {
  id: string
  email: string
  onboarding_step: string
  email_verified: boolean
}

export async function POST(req: NextRequest) {
  if (!isCustomersDbConfigured()) {
    return NextResponse.json(
      { ok: false, error: 'Account creation is temporarily unavailable. Please try again shortly.' },
      { status: 503 },
    )
  }

  const pending = await verifyGooglePendingSignupState(req.cookies.get(GOOGLE_PENDING_SIGNUP_COOKIE)?.value)
  if (!pending) {
    return NextResponse.json(
      { ok: false, code: 'expired', error: 'That confirmation link expired. Please continue with Google again.' },
      { status: 400 },
    )
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>
  // Never record consent=true unless the request says so explicitly — anything
  // other than the literal boolean true reads as false.
  const ageConfirmed = body.ageConfirmed === true
  const noAdviceAcknowledged = body.noAdviceAcknowledged === true
  const electronicCommConsent = body.electronicCommConsent === true
  if (!ageConfirmed || !noAdviceAcknowledged || !electronicCommConsent) {
    return NextResponse.json(
      { ok: false, error: 'You must check all 3 boxes to continue.' },
      { status: 400 },
    )
  }

  const email = pending.email
  const authUserId = `google:${pending.sub}`
  const ip = clientIpFromHeaders(req.headers.get('x-forwarded-for'))
  const ua = req.headers.get('user-agent')

  const clearPending = (res: NextResponse) => {
    res.cookies.set(GOOGLE_PENDING_SIGNUP_COOKIE, '', { ...googlePendingSignupCookieOptions(), maxAge: 0 })
    return res
  }

  try {
    const byProvider = await customerQuery<UserRow>(
      `SELECT id, email, onboarding_step, email_verified FROM users WHERE auth_user_id = $1 LIMIT 1`,
      [authUserId],
    )
    let user = byProvider[0]

    if (!user) {
      const byEmail = await customerQuery<UserRow>(
        `SELECT id, email, onboarding_step, email_verified FROM users WHERE email = $1 LIMIT 1`,
        [email],
      )
      const existing = byEmail[0]

      if (existing) {
        if (!existing.email_verified) {
          await writeAudit(existing.id, 'GOOGLE_LINK_BLOCKED_UNVERIFIED', ip, ua, {})
          return clearPending(
            NextResponse.json(
              {
                ok: false,
                code: 'unverified_existing',
                error:
                  'An IronForge account already uses that email but has not verified it yet. Check your inbox, or reset your password.',
              },
              { status: 409 },
            ),
          )
        }
        await customerExecute(`UPDATE users SET auth_user_id = $2, updated_at = now() WHERE id = $1`, [
          existing.id,
          authUserId,
        ])
        user = existing
        await writeAudit(user.id, 'GOOGLE_ACCOUNT_LINKED', ip, ua, {})
      } else {
        const username = await uniqueUsername(
          deriveUsernameBase({
            sub: pending.sub,
            email,
            emailVerified: true,
            givenName: pending.givenName,
            familyName: pending.familyName,
            picture: null,
          }),
        )
        const { userId } = await createCustomerAccount({
          firstName: pending.givenName || 'Member',
          lastName: pending.familyName || '',
          username,
          email,
          // Google's profile carries neither — collected later in onboarding, same
          // as any other field the password form asks for that a provider can't.
          phone: null,
          state: null,
          passwordHash: null,
          authProvider: 'google',
          authUserId,
          referralCode: null,
          promoCode: null,
          intendedPlan: null,
          // Just ticked on /signup/google-consent — checked for literal `true`
          // above, never defaulted or inherited from the callback's identity check.
          ageConfirmed,
          noAdviceAcknowledged,
          electronicCommConsent,
          emailVerified: true,
          ip,
          userAgent: ua,
          source: 'google_signup',
          publicOrigin: null,
        })
        user = { id: userId, email, onboarding_step: 'account_created', email_verified: true }
      }
    }

    const session = await getCustomerSession()
    session.customerId = user.id
    session.email = email
    session.emailVerified = true
    session.onboardingStep = user.onboarding_step
    await session.save()

    void customerExecute(`UPDATE users SET last_login_at = now() WHERE id = $1`, [user.id]).catch(() => {})
    await writeAudit(user.id, 'CUSTOMER_LOGIN', ip, ua, { method: 'google' })

    return clearPending(NextResponse.json({ ok: true, next: pending.next }))
  } catch (e) {
    console.error('[google/complete-signup] failed:', e)
    return NextResponse.json(
      { ok: false, error: 'Something went wrong creating your account. Please try again.' },
      { status: 500 },
    )
  }
}
