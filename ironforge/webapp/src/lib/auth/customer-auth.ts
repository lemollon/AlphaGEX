/**
 * Pure auth-decision helpers for customer login (sub-project: customer auth).
 * Kept separate from session plumbing (customer-session.ts) and routing
 * (onboarding-route.ts) so the login contract is unit-testable without a DB.
 */

export type LoginOutcome = 'invalid_credentials' | 'email_unverified' | 'ok'

export function classifyLoginAttempt(p: {
  userExists: boolean
  passwordOk: boolean
  emailVerified: boolean
}): LoginOutcome {
  if (!p.userExists || !p.passwordOk) return 'invalid_credentials'
  if (!p.emailVerified) return 'email_unverified'
  return 'ok'
}

/**
 * A real bcrypt hash used ONLY to equalize response timing when no user row is
 * found, so an attacker cannot distinguish "unknown email" from "wrong password"
 * by latency. Never matches any real password. Regenerate with:
 *   node -e "console.log(require('bcryptjs').hashSync('x',10))"
 */
export const TIMING_DUMMY_HASH =
  '$2b$10$2h/JuRccXabXFfJoqnuUgeBWR2f/WqS4aM/6VGsuQPWZxh16Uix3u'
