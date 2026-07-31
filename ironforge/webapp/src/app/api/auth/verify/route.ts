import { NextRequest, NextResponse } from 'next/server'
import { publicOrigin } from '@/lib/public-origin'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { hashToken, isExpired } from '@/lib/auth/verification-token'
import {
  ONBOARDING_COOKIE,
  onboardingCookieOptions,
  signOnboardingToken,
} from '@/lib/auth/onboarding'
import {
  isCustomersDbConfigured,
  customerQuery,
  customerExecute,
  customerTransaction,
} from '@/lib/customers-db'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

/**
 * Email verification callback (sub-project C). Validates + consumes a token, flips
 * the user to email_verified, writes an EMAIL_VERIFIED audit, then mints the
 * customer session and lands the user on /enroll (UAT-006 — the token proves
 * control of the email; forcing a second sign-in broke the enrollment sequence).
 * The email that delivers this link is sub-project D.
 */

interface TokenRow {
  id: string
  user_id: string
  expires_at: string
  consumed_at: string | null
}

function clientIp(req: NextRequest): string | null {
  const xff = req.headers.get('x-forwarded-for')
  return xff ? xff.split(',')[0].trim() : null
}

export async function GET(req: NextRequest) {
  const origin = publicOrigin(req)
  const fail = () => NextResponse.redirect(`${origin}/login?verifyError=1`)

  const raw = req.nextUrl.searchParams.get('token')
  if (!raw) return fail()
  if (!isCustomersDbConfigured()) return fail()

  try {
    const rows = await customerQuery<TokenRow>(
      `SELECT id, user_id, expires_at, consumed_at
         FROM email_verification_tokens WHERE token_hash = $1 LIMIT 1`,
      [hashToken(raw)],
    )
    const row = rows[0]
    if (!row || row.consumed_at || isExpired(row.expires_at, new Date())) {
      return fail()
    }

    await customerTransaction(async (run) => {
      await run(
        `UPDATE users
            SET email_verified = TRUE,
                account_status = 'email_verified',
                onboarding_step = 'email_verified',
                updated_at = now()
          WHERE id = $1`,
        [row.user_id],
      )
      await run(
        `UPDATE email_verification_tokens SET consumed_at = now() WHERE id = $1`,
        [row.id],
      )
    })

    try {
      await customerExecute(
        `INSERT INTO audit_events (user_id, event_type, ip_address, user_agent, metadata)
         VALUES ($1, $2, $3, $4, $5)`,
        [
          row.user_id,
          'EMAIL_VERIFIED',
          clientIp(req),
          req.headers.get('user-agent'),
          JSON.stringify({ token_id: row.id }),
        ],
      )
    } catch (e) {
      console.error('[verify] audit write failed:', e)
    }

    // UAT-006: possession of a valid, unconsumed verification token IS proof of
    // control of the email — mint the customer session here and land the user
    // directly on /enroll (which resumes at the correct step server-side). The old
    // behavior redirected to a bare Sign In page, forcing a second authentication
    // and breaking the enrollment sequence. If the session can't be established
    // (cross-device edge, secret rotation), fall back to the login door with the
    // verified banner — a purposeful sign-in handoff, not a dead end.
    try {
      const users = await customerQuery<{ email: string; onboarding_step: string | null }>(
        `SELECT email, onboarding_step FROM users WHERE id = $1 LIMIT 1`,
        [row.user_id],
      )
      const session = await getCustomerSession()
      session.customerId = row.user_id
      session.email = users[0]?.email
      session.emailVerified = true
      session.onboardingStep = users[0]?.onboarding_step ?? 'email_verified'
      await session.save()

      const res = NextResponse.redirect(`${origin}/enroll`)
      // Legacy onboarding cookie is best-effort only — nothing routes to /onboarding
      // anymore, so its failure must never demote a successfully minted session.
      try {
        const token = await signOnboardingToken(row.user_id)
        res.cookies.set(ONBOARDING_COOKIE, token, onboardingCookieOptions())
      } catch { /* legacy hand-off cookie only */ }
      return res
    } catch (e) {
      console.error('[verify] session mint failed, falling back to login door:', e)
      return NextResponse.redirect(`${origin}/login?verified=1`)
    }
  } catch (e) {
    console.error('[verify] verification failed:', e)
    return fail()
  }
}
