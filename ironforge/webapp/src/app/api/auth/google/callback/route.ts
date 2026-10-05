import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { normalizeEmail } from '@/lib/signup-validation'
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
import {
  signGooglePendingSignupState,
  GOOGLE_PENDING_SIGNUP_COOKIE,
  googlePendingSignupCookieOptions,
} from '@/lib/auth/google-pending-signup-cookie'
import { createCustomerAccount, writeAudit, clientIpFromHeaders } from '@/lib/auth/create-customer'
import { uniqueUsername } from '@/lib/auth/username'
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
 *   - no match, consents already captured (from /signup)              → create via the
 *     SAME createCustomerAccount() the password signup route uses, no password,
 *     auth_provider='google', and continue into /enroll
 *   - no match, consents NOT captured (from /login — nothing to carry)  → do NOT
 *     create an account on an implied yes. Seal the verified identity into the
 *     short-lived google-pending-signup-cookie and send the browser to
 *     /signup/google-consent, which asks for the same 3 boxes before anything is
 *     written to the database.
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
        const c = saved.consents
        const allConsented = Boolean(c?.ageConfirmed && c?.noAdviceAcknowledged && c?.electronicCommConsent)

        if (!allConsented) {
          // Login's "Continue with Google" carries no consents at all, and a
          // signup round trip can only reach here with all 3 true (the button is
          // disabled otherwise) — so an incomplete set means this did NOT start on
          // /signup with the boxes checked. Never create the account on an implied
          // yes: seal the verified Google identity into the short-lived pending
          // cookie and hand the browser to the one-time consent page instead.
          const pendingCookie = await signGooglePendingSignupState({
            sub: claims.sub,
            email,
            givenName: claims.givenName,
            familyName: claims.familyName,
            next: safeNext(saved.next),
          })
          const dest = new URL('/signup/google-consent', publicOrigin(req))
          const res = NextResponse.redirect(dest)
          res.cookies.set(GOOGLE_PENDING_SIGNUP_COOKIE, pendingCookie, googlePendingSignupCookieOptions())
          return clearCookie(res)
        }

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
          // Captured on /signup itself — the SAME 3 checkboxes the password form
          // requires, carried here through the signed OAuth cookie (see
          // google/start/route.ts). Never hardcoded true: an incomplete set is
          // caught above, before this line is reached.
          ageConfirmed: c!.ageConfirmed,
          noAdviceAcknowledged: c!.noAdviceAcknowledged,
          electronicCommConsent: c!.electronicCommConsent,
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
