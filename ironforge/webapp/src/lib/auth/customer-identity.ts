/**
 * ONE way to ask "which customer is this request?", for both the web cookie and the
 * mobile bearer token.
 *
 * Why this shape: getCustomerSession() reads the cookie via next/headers rather than a
 * passed-in request, and so does this. That means a call site swapping to
 * getCustomerIdentity() changes NO function signature anywhere up the stack — including
 * resolveLiveViewer(), which takes a NextRequest it never actually uses for auth. That
 * single substitution is what makes all five /api/live/* routes bearer-aware without
 * editing a route file.
 *
 * Returns a PLAIN OBJECT with no .save()/.destroy(). That is deliberate: the cookie
 * write paths (customer-login, customer-logout, ops/impersonate) must keep using
 * getCustomerSession(), and this shape makes migrating one of them by mistake a
 * compile error instead of a silent no-op at runtime.
 *
 * Precedence: bearer first, then cookie. A device presenting a token is unambiguously
 * acting as that token's owner; the cookie is only consulted when there is no bearer.
 */

import { headers } from 'next/headers'
import { getCustomerSession } from '@/lib/auth/customer-session-server'
import { bearerFrom, verifyMobileToken, type MobileTokenType } from '@/lib/auth/mobile-token'
import { customerQuery } from '@/lib/customers-db'

export interface CustomerIdentity {
  customerId: string
  email?: string
  emailVerified?: boolean
  onboardingStep?: string
  source: 'cookie' | 'bearer'
}

export interface IdentityOptions {
  /**
   * Compare the token's `ep` claim against users.token_epoch (one indexed row read).
   * Use on any route that changes money, credentials, or trading state — it is the
   * only way to honour a revocation inside the access token's 15-minute life.
   */
  verifyEpoch?: boolean
  /**
   * Require a step-up token (fresh password check) rather than a plain access token.
   * Implies verifyEpoch. Cookie sessions never satisfy this.
   */
  requireStepUp?: boolean
}

async function bearerIdentity(opts: IdentityOptions): Promise<CustomerIdentity | null> {
  const token = bearerFrom(headers().get('authorization'))
  if (!token) return null

  const type: MobileTokenType = opts.requireStepUp ? 'step' : 'acc'
  const claims = await verifyMobileToken(token, { type })
  if (!claims) return null

  if (opts.verifyEpoch || opts.requireStepUp) {
    const rows = await customerQuery<{
      token_epoch: number
      email: string
      email_verified: boolean
      onboarding_step: string | null
    }>(
      `SELECT token_epoch, email, email_verified, onboarding_step
         FROM users WHERE id = $1 LIMIT 1`,
      [claims.sub],
    )
    const row = rows[0]
    // No row, or an epoch bumped since minting (password change, logout-all,
    // detected token theft) — the token is dead.
    if (!row || row.token_epoch !== claims.ep) return null
    return {
      customerId: claims.sub,
      email: row.email,
      emailVerified: row.email_verified,
      onboardingStep: row.onboarding_step ?? undefined,
      source: 'bearer',
    }
  }

  return { customerId: claims.sub, source: 'bearer' }
}

/**
 * The signed-in customer, or null. Never throws.
 *
 * @param opts.verifyEpoch    check the revocation epoch (sensitive routes)
 * @param opts.requireStepUp  demand a fresh step-up token (stepUpActions)
 */
export async function getCustomerIdentity(
  opts: IdentityOptions = {},
): Promise<CustomerIdentity | null> {
  try {
    const bearer = await bearerIdentity(opts)
    if (bearer) return bearer
  } catch {
    // A malformed header or an unreachable DB must not 500 a request that may still
    // carry a perfectly good cookie. Fall through.
  }

  // A step-up requirement is a property of the mobile flow; a cookie can never satisfy it.
  if (opts.requireStepUp) return null

  try {
    const session = await getCustomerSession()
    if (!session.customerId) return null
    return {
      customerId: session.customerId,
      email: session.email,
      emailVerified: session.emailVerified,
      onboardingStep: session.onboardingStep,
      source: 'cookie',
    }
  } catch {
    return null
  }
}
