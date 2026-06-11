import { NextRequest, NextResponse } from 'next/server'
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
 * the user to email_verified, writes an EMAIL_VERIFIED audit, then (sub-project F)
 * issues a signed onboarding cookie and redirects into the onboarding funnel at
 * /onboarding/legal. The email that delivers this link is sub-project D.
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
  const origin = req.nextUrl.origin
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

    // Sub-project F: hand the (now-verified) prospect into the onboarding funnel.
    // The signed cookie is what the /onboarding/* guard checks — they have no login
    // session yet. If signing fails (secret unset), fall back to the login screen.
    try {
      const token = await signOnboardingToken(row.user_id)
      const res = NextResponse.redirect(`${origin}/onboarding/legal`)
      res.cookies.set(ONBOARDING_COOKIE, token, onboardingCookieOptions())
      return res
    } catch (e) {
      console.error('[verify] onboarding token sign failed:', e)
      return NextResponse.redirect(`${origin}/login?verified=1`)
    }
  } catch (e) {
    console.error('[verify] verification failed:', e)
    return fail()
  }
}
