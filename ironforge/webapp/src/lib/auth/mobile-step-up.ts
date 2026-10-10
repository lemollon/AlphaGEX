import { headers } from 'next/headers'
import { getCustomerIdentity, type CustomerIdentity } from '@/lib/auth/customer-identity'

/**
 * Header the NEW mobile client (src/auth/stepUp.ts / api/client.ts in the mobile
 * app) sends on every authenticated request, once it ships. Its presence is the
 * ONLY thing that turns this gate on for a given caller.
 *
 * Why a capability header rather than unconditionally requiring step-up: every
 * app build already in customers' hands and in Apple review (builds 24-26, Android
 * build 10) was compiled before this gate existed and has no step-up client at
 * all — it has never minted a step-up token and never will until an update ships.
 * Requiring step-up unconditionally would 401 brokerage connect/disconnect and
 * account deletion for every one of those installs, including the App Review
 * tester's, the moment this merges. Gating on a header only the NEW client sends
 * means an old build keeps exactly today's behavior (a plain access token is
 * enough), while a new build opts itself into the stricter check. Once the step-up
 * client has been out long enough that no ungated build is still in the field,
 * this can be made unconditional and the header requirement dropped.
 */
export const STEP_UP_CAPABLE_HEADER = 'x-ironforge-stepup'

/**
 * Identity resolution for a route gated by MOBILE_SESSION_POLICY.stepUpActions
 * (brokerage connect/disconnect, billing cancel, password change, trade approve).
 *
 * Cookie (web dashboard) sessions are UNAFFECTED — stepUpActions and the
 * `/api/auth/mobile/reauth` flow that mints a step-up token are a mobile-app-only
 * concept (mobile-policy.ts); there is no cookie equivalent today, and gating the
 * shared web dashboard behind one would lock out a surface this task never touched.
 *
 * A bearer (mobile) caller that sends STEP_UP_CAPABLE_HEADER must present an actual
 * step-up token (type 'step', minted by a fresh password check) rather than a plain
 * access token to reach a route guarded this way. A bearer caller WITHOUT that
 * header — every build shipped before this gate existed — is let through exactly
 * as before: a valid plain access token is sufficient, full stop.
 */
export async function requireIdentityWithStepUp(): Promise<
  | { identity: CustomerIdentity; error: null }
  | { identity: null; error: 'unauthorized' | 'step_up_required' }
> {
  const plain = await getCustomerIdentity()
  if (plain?.source === 'cookie') return { identity: plain, error: null }

  const capable = headers().get(STEP_UP_CAPABLE_HEADER) === '1'
  if (!capable) {
    // Old client (or anything else that never sends the header) — today's
    // behavior, unchanged: a plain access token (or none) is all this checks.
    if (plain) return { identity: plain, error: null }
    return { identity: null, error: 'unauthorized' }
  }

  const stepped = await getCustomerIdentity({ requireStepUp: true })
  if (stepped) return { identity: stepped, error: null }

  // A step-up-capable caller resolved on the plain pass but not the step-up pass
  // means they presented a valid, ordinary access token — not a step-up token.
  // That is the "changed something sensitive without a fresh password check" case
  // this exists to block, so it gets its own code rather than a generic 401.
  if (plain) return { identity: null, error: 'step_up_required' }
  return { identity: null, error: 'unauthorized' }
}
