import { getCustomerIdentity, type CustomerIdentity } from '@/lib/auth/customer-identity'

/**
 * Identity resolution for a route gated by MOBILE_SESSION_POLICY.stepUpActions
 * (brokerage connect/disconnect, billing cancel, password change, trade approve).
 *
 * Cookie (web dashboard) sessions are UNAFFECTED — stepUpActions and the
 * `/api/auth/mobile/reauth` flow that mints a step-up token are a mobile-app-only
 * concept (mobile-policy.ts); there is no cookie equivalent today, and gating the
 * shared web dashboard behind one would lock out a surface this task never touched.
 *
 * A bearer (mobile) caller must present an actual step-up token (type 'step', minted
 * by a fresh password check) rather than a plain access token to reach a route guarded
 * this way — presenting the ordinary access token here is rejected the same as
 * presenting none at all, which is what makes the Face ID + password prompt in the app
 * (src/auth/stepUp.ts) load-bearing instead of decorative.
 */
export async function requireIdentityWithStepUp(): Promise<
  | { identity: CustomerIdentity; error: null }
  | { identity: null; error: 'unauthorized' | 'step_up_required' }
> {
  const plain = await getCustomerIdentity()
  if (plain?.source === 'cookie') return { identity: plain, error: null }

  const stepped = await getCustomerIdentity({ requireStepUp: true })
  if (stepped) return { identity: stepped, error: null }

  // A bearer caller resolved on the plain pass but not the step-up pass means they
  // presented a valid, ordinary access token — not a step-up token. That is the
  // "changed something sensitive without a fresh password check" case this exists
  // to block, so it gets its own code rather than a generic 401.
  if (plain) return { identity: null, error: 'step_up_required' }
  return { identity: null, error: 'unauthorized' }
}
