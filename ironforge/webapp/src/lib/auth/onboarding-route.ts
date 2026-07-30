/**
 * Maps a customer's onboarding_step to the route they should resume at after login
 * or email verification (sub-project: customer auth). Pure — no I/O.
 *
 * CUTOVER (7/30): every step now resolves to /enroll. The legacy /onboarding/* funnel
 * (legal → risk → brokerage → complete) is retired as a destination — the enrollment
 * flow from the July 29 handoff is live, and /enroll is an OWNERSHIP-AWARE door: it
 * resumes an open enrollment at the right screen, routes strategy owners to /live and
 * community members to /community, and only starts a fresh enrollment for customers
 * with nothing yet. One answer fits every step because the smart routing lives behind
 * the door, not in this resolver.
 *
 * The legacy pages stay deployed for anyone mid-flight on an old link; nothing routes
 * there anymore.
 */
export function nextRouteForOnboarding(_step: string | null | undefined): string {
  return '/enroll'
}
