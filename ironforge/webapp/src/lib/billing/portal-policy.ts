/**
 * Which Stripe Customer Portal a caller is allowed to be sent to.
 *
 * Extracted from the route so the rule has exactly one definition and can be tested.
 * Buried inline it is three lines of `if` that look like defensive noise, and the one
 * thing that must never happen — a mobile client receiving the default portal — is
 * invisible to anyone reading the handler.
 */

export type PortalClient = 'web' | 'mobile'

export type PortalDecision =
  | { allowed: true; configuration: string | null }
  | { allowed: false; reason: 'portal_unconfigured' }

/**
 * Web keeps Stripe's default portal (full self-service, including plan changes).
 *
 * Mobile is only ever allowed a NAMED configuration — one created with subscription
 * updates disabled. Stripe's default portal permits changing plan, and a plan change
 * reachable from inside the iOS app is a purchasing mechanism under App Review
 * Guideline 3.1.1, which is a rejected build.
 *
 * 🚨 So mobile FAILS CLOSED. With no configuration id, the answer is "not allowed",
 * never "fall back to the default". That fallback is the whole bug: it would restore
 * the violation silently, at the moment an env var went missing, on the platform where
 * it costs the most.
 */
export function resolvePortalConfiguration(
  client: PortalClient,
  configuredMobileId: string | null | undefined,
): PortalDecision {
  if (client !== 'mobile') return { allowed: true, configuration: null }

  const id = configuredMobileId?.trim()
  if (!id) return { allowed: false, reason: 'portal_unconfigured' }

  return { allowed: true, configuration: id }
}
