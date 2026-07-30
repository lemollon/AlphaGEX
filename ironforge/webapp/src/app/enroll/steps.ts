/**
 * The one mapping from server-owned enrollment position to /enroll/* routes.
 *
 * The server's `next_step` vocabulary (lib/enrollment/service.ts nextStepFor) is
 * plan | legal | billing | setup | done. The UI is route-per-screen, and `setup`
 * spans three screens (broker → agent → review), so this module owns the translation
 * in ONE place — the server page redirect and the client guard must never disagree.
 *
 * Pure: importable from server and client components alike.
 */

export type EnrollPageStep = 'plan' | 'legal' | 'billing' | 'broker' | 'agent' | 'review' | 'done'

/**
 * How far along each PAGE is. broker/agent/review share a rank: they are all inside
 * the server's `setup` step, and movement between them is client-navigated (the server
 * re-validates everything at activation anyway).
 */
export const PAGE_RANK: Record<EnrollPageStep, number> = {
  plan: 0,
  legal: 1,
  billing: 2,
  broker: 3,
  agent: 3,
  review: 3,
  done: 4,
}

/**
 * Canonical route for a server next_step.
 *
 * Community quirk: the approved visual set has NO standalone Community legal screen —
 * its core documents are the clickwrap block on the Community billing submit. So a
 * community enrollment whose next_step is 'legal' canonically lands on /enroll/billing,
 * where the clickwrap acceptance is recorded before checkout.
 */
export function routeForNextStep(
  nextStep: string | null | undefined,
  selectedPlan: string | null | undefined,
): { route: string; rank: number } {
  switch (nextStep) {
    case 'legal':
      return selectedPlan === 'community'
        ? { route: '/enroll/billing', rank: PAGE_RANK.billing }
        : { route: '/enroll/legal', rank: PAGE_RANK.legal }
    case 'billing':
      return { route: '/enroll/billing', rank: PAGE_RANK.billing }
    case 'setup':
      return { route: '/enroll/broker', rank: PAGE_RANK.broker }
    case 'done':
      return { route: '/enroll/done', rank: PAGE_RANK.done }
    case 'plan':
    default:
      return { route: '/enroll/plan', rank: PAGE_RANK.plan }
  }
}
