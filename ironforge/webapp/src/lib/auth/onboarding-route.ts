/**
 * Maps a customer's onboarding_step to the route they should resume at after login
 * or email verification (sub-project: customer auth). Pure — no I/O. Future onboarding
 * steps (billing, brokerage) add cases here.
 *
 * The risk-assessment step sits between legal and completion, so legal_accepted resolves
 * to /onboarding/risk and risk_assessed resolves to /onboarding/complete.
 */
export function nextRouteForOnboarding(step: string | null | undefined): string {
  switch (step) {
    case 'account_created':
    case 'email_verified':
      return '/onboarding/legal'
    case 'legal_accepted':
      return '/onboarding/risk'
    case 'risk_assessed':
    default:
      return '/onboarding/complete'
  }
}
