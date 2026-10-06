/**
 * The one mapping from server-owned enrollment position to /enroll/* routes.
 *
 * ORDER (10/5 reorder, Leron): Create account -> Agreements -> Choose agent -> Connect
 * brokerage -> Billing -> Review & enter, matching IronForge_Enrollment_10.4.html's step
 * rail exactly. This is a WEB-ONLY concern — the mobile app does not import this file
 * (it has its own navigation over the same API) and keeps its existing plan -> legal ->
 * billing -> broker -> agent -> review sequence; the server tells each caller which
 * order applies via `next_step` (see lib/enrollment/service.ts nextStepFor vs
 * resolveNextStepWeb), and this module only ever has to translate the WEB vocabulary.
 *
 * `agent` is kept as a page/step value for the dedicated AGENT-01 screen, which still
 * exists as a resumable FALLBACK (an account or agent change can always invalidate a
 * config and send a customer back to re-derive one) — it is no longer a rail step of
 * its own; the web order mints the config automatically the moment a brokerage account
 * is chosen (see broker/BrokerClient.tsx), so it shares the `broker` rank.
 *
 * Pure: importable from server and client components alike.
 */

export type EnrollPageStep = 'account' | 'legal' | 'plan' | 'broker' | 'agent' | 'billing' | 'review' | 'done'

/** How far along each PAGE is, in the web order's six visible rail steps. */
export const PAGE_RANK: Record<EnrollPageStep, number> = {
  account: 0,
  legal: 1,
  plan: 2,
  broker: 3,
  agent: 3,
  billing: 4,
  review: 5,
  done: 6,
}

/**
 * Canonical route for a server next_step (the WEB vocabulary — see service.ts
 * resolveNextStepWeb: 'legal' | 'plan' | 'broker' | 'billing' | 'setup' | 'done').
 *
 * `selectedPlan` is accepted for forward compatibility with callers that still pass it
 * (e.g. a future plan-specific routing need) but the web order has no plan-conditional
 * branch left here: Agreements runs before a plan exists, and Community's completion
 * now happens inline from the Choose agent screen (PlanClient) rather than via a
 * special-cased route here.
 */
export function routeForNextStep(
  nextStep: string | null | undefined,
  _selectedPlan?: string | null,
): { route: string; rank: number } {
  switch (nextStep) {
    case 'plan':
      return { route: '/enroll/plan', rank: PAGE_RANK.plan }
    case 'broker':
      return { route: '/enroll/broker', rank: PAGE_RANK.broker }
    case 'billing':
      return { route: '/enroll/billing', rank: PAGE_RANK.billing }
    case 'setup':
      return { route: '/enroll/review', rank: PAGE_RANK.review }
    case 'done':
      return { route: '/enroll/done', rank: PAGE_RANK.done }
    case 'legal':
    default:
      return { route: '/enroll/legal', rank: PAGE_RANK.legal }
  }
}
