import type { EnrollmentNextStep } from './types'

/**
 * The one mapping from server-owned enrollment position to /enroll/* screens.
 *
 * Ported from webapp/src/app/enroll/steps.ts — the server's `next_step` vocabulary
 * (plan | legal | billing | setup | done) is the same one nextStepFor() in
 * webapp/src/lib/enrollment/service.ts emits, so a deep link or a resumed session on
 * mobile lands on the identical screen the web funnel would. `setup` spans three
 * mobile screens (broker → agent → review); movement between those three is
 * client-navigated, same as web, because activation re-validates everything anyway.
 *
 * Pure — no navigation, no I/O — so it is unit-testable without expo-router.
 */
export type EnrollPageStep = 'create-account' | 'verify' | 'legal' | 'plan' | 'billing' | 'broker' | 'agents' | 'review' | 'done'

/** How far along each SCREEN is, for the "don't let a customer skip ahead" guard. */
export const PAGE_RANK: Record<EnrollPageStep, number> = {
  'create-account': -1,
  verify: -1,
  plan: 0,
  legal: 1,
  billing: 2,
  broker: 3,
  agents: 3,
  review: 3,
  done: 4,
}

/**
 * Canonical mobile route for a server `next_step`.
 *
 * Community quirk mirrors the web: the approved screen set has no standalone
 * Community legal screen (its core Terms/Privacy/Refund are accepted as a clickwrap
 * at the Community billing submit), so a community enrollment whose next_step is
 * 'legal' canonically lands on /enroll/billing.
 *
 * Ember quirk (10.4 redesign): Ember is free and never asks for a card (design-spec
 * §5 step 5 — "skipped automatically for Ember"), so an Ember enrollment whose
 * next_step is 'billing' canonically skips straight to /enroll/broker. billing.tsx
 * also redirects forward on mount as a second guard, in case a customer's browser
 * history lands them back on that screen directly.
 */
export function routeForNextStep(
  nextStep: EnrollmentNextStep | string | null | undefined,
  selectedPlan: string | null | undefined,
): { route: string; rank: number } {
  switch (nextStep) {
    case 'legal':
      return selectedPlan === 'community'
        ? { route: '/enroll/billing', rank: PAGE_RANK.billing }
        : { route: '/enroll/legal', rank: PAGE_RANK.legal }
    case 'billing':
      return selectedPlan === 'ember'
        ? { route: '/enroll/broker', rank: PAGE_RANK.broker }
        : { route: '/enroll/billing', rank: PAGE_RANK.billing }
    case 'setup':
      return { route: '/enroll/broker', rank: PAGE_RANK.broker }
    case 'done':
      return { route: '/', rank: PAGE_RANK.done }
    case 'plan':
    default:
      return { route: '/enroll/plan', rank: PAGE_RANK.plan }
  }
}
