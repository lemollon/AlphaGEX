/**
 * Maps a customer's onboarding_step to the route they should resume at after login
 * or email verification (sub-project: customer auth). Pure — no I/O. Future onboarding
 * steps (billing) add cases here.
 *
 * Funnel order: legal → risk → brokerage → complete. So legal_accepted resolves to
 * /onboarding/risk, risk_assessed resolves to /onboarding/brokerage, and
 * brokerage_connected resolves to /onboarding/complete. The brokerage step is skippable
 * (advisory): skipping advances straight to /onboarding/complete without setting
 * brokerage_connected, so the resolver never traps a skipper at /onboarding/brokerage.
 */
export function nextRouteForOnboarding(step: string | null | undefined): string {
  switch (step) {
    case 'account_created':
    case 'email_verified':
      return '/onboarding/legal'
    case 'legal_accepted':
      return '/onboarding/risk'
    case 'risk_assessed':
      return '/onboarding/brokerage'
    case 'brokerage_connected':
    default:
      return '/onboarding/complete'
  }
}
