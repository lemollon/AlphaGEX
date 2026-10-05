import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { normalizeEmail, isValidUsername } from '@/lib/signup-validation'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { isCustomerPath } from '@/lib/auth/access'
import {
  isGoogleOAuthConfigured,
  exchangeCodeForToken,
  verifyGoogleIdToken,
  googleRedirectUri,
  deriveUsernameBase,
} from '@/lib/auth/google-oauth'
import {
  verifyGoogleOAuthState,
  GOOGLE_OAUTH_COOKIE,
  googleOAuthCookieOptions,
} from '@/lib/auth/google-oauth-cookie'
import { createCustomerAccount, writeAudit, clientIpFromHeaders } from '@/lib/auth/create-customer'
import { isCustomersDbConfigured, customerQuery, customerExecute } from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Google OAuth return (web customer surface only — NOT the mobile app). EXACT
 * path: this is the registered redirect URI
 * (https://ironforge.trade/api/auth/google/callback). Mobile deliberately has no
 * Google sign-in here — adding one would trigger Apple Guideline 4.8 (any
 * third-party login on iOS requires an equivalent Sign in with Apple option),
 * which is out of scope for this change.
 *
 * Verifies state (double-submit against the signed cookie) + PKCE, exchanges the
 * code, verifies the id_token's signature and claims, then:
 *   - a known Google identity (auth_user_id = 'google:<sub>')        → sign in
 *   - an existing, EMAIL-VERIFIED account with a matching email       → link + sign in
 *   - an existing account whose OWN email is unverified               → refuse (never
 *     auto-link to an unverified mailbox someone else may have typo'd in)
 *   - no match at all                                                 → create via the
 *     SAME createCustomerAccount() the password signup route uses, no password,
 *     auth_provider='google', and continue into /enroll
 */
interface UserRow {
  id: string
  email: string
  onboarding_step: string
  email_verified: boolean
}

function safeNext(raw: string): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return '/enroll'
  const path = raw.split('?')[0].split('#')[0]
  return path === '/enroll' || isCustomerPath(path) ? path : '/enroll'
}

async function uniqueUsername(base: string): Promise<string> {
  const candidates = [
    base,
    ...Array.from({ length: 4 }, () => `${base}${Math.floor(100 + Math.random() * 900)}`),
  ]
  for (const candidate of candidates) {
    if (!isValidUsername(candidate)) continue
    const rows = await customerQuery<{ id: string }>(
      `SELECT id FROM users WHERE lower(username) = lower($1) LIMIT 1`,
      [candidate],
    )
    if (rows.length === 0) return candidate
  }
  // Astronomically unlikely to be reached, but a username MUST exist — never block
  // account creation on a naming collision.
  return `member${Date.now().toString(36)}`
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl
  const clearCookie = (res: NextResponse) => {
    res.cookies.set(GOOGLE_OAUTH_COOKIE, '', { ...googleOAuthCookieOptions(), maxAge: 0 })
    return res
  }
  const fail = (reason: string) => {
    const target = new URL('/login', publicOrigin(req))
    target.searchParams.set('googleError', reason)
    return clearCookie(NextResponse.redirect(target))
  }

  if (!isGoogleOAuthConfigured() || !isCustomersDbConfigured()) {
    return fail('unavailable')
  }

  const stateParam = url.searchParams.get('state')
  const saved = await verifyGoogleOAuthState(req.cookies.get(GOOGLE_OAUTH_COOKIE)?.value)
  // Double-submit CSRF check: the state Google echoed back must match the one
  // sealed into our own signed cookie at /start. A mismatch covers a forged,
  // replayed, or simply expired round trip — all three get the same safe failure.
  if (!saved || !stateParam || saved.state !== stateParam) {
    return fail('invalid_state')
  }
  if (url.searchParams.get('error')) {
    return fail('denied')
  }
  const code = url.searchParams.get('code')
  if (!code) {
    return fail('missing_code')
  }

  try {
    const redirectUri = googleRedirectUri(publicOrigin(req))
    const token = await exchangeCodeForToken(code, saved.verifier, redirectUri)
    const claims = await verifyGoogleIdToken(token.idToken)
    if (!claims) return fail('invalid_token')
    // Never trust an unverified Google email as proof of identity — it would let
    // anyone sign up as "you@gmail.com" without ever controlling that mailbox.
    if (!claims.emailVerified) return fail('email_unverified')

    const email = normalizeEmail(claims.email)
    const authUserId = `google:${claims.sub}`
    const ip = clientIpFromHeaders(req.headers.get('x-forwarded-for'))
    const ua = req.headers.get('user-agent')

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
        // Never auto-link to an account whose OWN email is unverified (spec
        // requirement) — that row could have been created by someone else
        // mistyping this address, and linking would hand them a live session.
        if (!existing.email_verified) {
          await writeAudit(existing.id, 'GOOGLE_LINK_BLOCKED_UNVERIFIED', ip, ua, {})
          return fail('unverified_existing')
        }
        await customerExecute(`UPDATE users SET auth_user_id = $2, updated_at = now() WHERE id = $1`, [
          existing.id,
          authUserId,
        ])
        user = existing
        await writeAudit(user.id, 'GOOGLE_ACCOUNT_LINKED', ip, ua, {})
      } else {
        const username = await uniqueUsername(deriveUsernameBase(claims))
        const { userId } = await createCustomerAccount({
          firstName: claims.givenName || 'Member',
          lastName: claims.familyName || '',
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
          // The "Continue with Google" button sits under the same age/no-advice/
          // electronic-communication disclosure shown on the password form (see
          // SignupClient) — continuing IS the affirmation, same as clicking
          // "Create Account" there.
          ageConfirmed: true,
          noAdviceAcknowledged: true,
          electronicCommConsent: true,
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

    const dest = new URL(safeNext(saved.next), publicOrigin(req))
    return clearCookie(NextResponse.redirect(dest))
  } catch (e) {
    console.error('[google/callback] failed:', e)
    return fail('server_error')
  }
}
