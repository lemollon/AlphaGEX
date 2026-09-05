/**
 * In-app enrollment (UAT #6, PR A) — response shapes mirrored from the webapp's
 * enrollment v1 API (webapp/src/lib/enrollment/service.ts, .../legal.ts,
 * .../activation.ts) and the additive public plan catalogue
 * (webapp/src/app/api/public/plans/route.ts).
 *
 * Hand-written mirror, same convention as src/api/types.ts — no shared package between
 * the two apps, so a drift here renders "undefined" rather than throwing.
 */

/** The server's own vocabulary — see webapp lib/enrollment/service.ts nextStepFor(). */
export type EnrollmentNextStep = 'plan' | 'legal' | 'billing' | 'setup' | 'done'

export interface EnrollmentSummary {
  id: string
  selected_plan: string | null
  status: string
}

/** POST /api/v1/enrollments */
export interface EnrollmentResumeResponse {
  enrollment: EnrollmentSummary
  next_step: EnrollmentNextStep
}

/** PUT /api/v1/enrollments/{id}/plan */
export interface LegalRequirement {
  code: string
  title: string
  version: string
  contentUri: string
  accepted: boolean
}

export interface LegalBlock {
  documents: LegalRequirement[]
  outstanding: string[]
}

export interface SetPlanResponse {
  ok: true
  selected_plan: string
  next_step: 'legal'
  legal: LegalBlock
}

/** GET /api/v1/enrollments/{id}/legal */
export interface GetLegalResponse extends LegalBlock {
  enrollment_id: string
  selected_plan: string | null
}

/** POST /api/v1/enrollments/{id}/acceptances */
export type AcceptancesResponse = { ok: true; next_step: 'billing' } | { ok: false; missing: string[]; message?: string }

/** GET /api/public/plans — additive, read-only plan catalogue (no auth, no PII). */
export interface PlanCatalog {
  community: { key: string; name: string; price_monthly: number }
  bots: Array<{ slug: 'spark' | 'flame'; name: string; blurb: string; price_monthly: number; accent: string }>
  both: { price_monthly: number }
  trial_days: number
}

/** GET /api/billing/membership — used by "I already subscribed on the web" (billing step). */
export interface MembershipCheck {
  ok: boolean
  configured?: boolean
  membership: {
    plan: string
    status: string
    badge: string
    price_monthly: number
    next_billing_date: string | null
    bots: string[]
  } | null
}

/** GET /api/brokerage/connections (same route the web /enroll/broker screen uses). */
export interface BrokerAccountPick {
  id: string
  mask: string | null
  eligibility: string | null
  ineligible_reason: string | null
}

export interface BrokerConnectionPick {
  id: string
  provider: string
  status: string
  accounts: BrokerAccountPick[]
}

export interface BrokerConnectionsResponse {
  ok: boolean
  configured?: boolean
  connections: BrokerConnectionPick[]
}

/** PUT /api/v1/enrollments/{id}/broker-account */
export interface SelectBrokerAccountResponse {
  ok: true
  broker_account: { id: string; display_mask: string }
  next_step: 'agent'
}

/** POST /api/v1/agent-configs */
export interface AgentConfigResponse {
  id: string
  agent_code: 'spark' | 'flame'
  rule_version: string
  status: 'valid' | 'draft'
  limits: { max_deployment_cents: number; buying_power_cents: number | null }
  violations: string[]
  warnings: string[]
}

export interface ActivationBlocker {
  code: string
  message: string
  remediable: boolean
}

/** POST /api/v1/activations/preview */
export interface ActivationPreview {
  preview_hash: string
  expires_in_seconds: number
  snapshot: {
    agent: 'spark' | 'flame'
    rule_version: string
    account_mask: string
    max_deployment_cents: number
    buying_power_cents: number
    plan: { name: string; price_monthly: number; interval: string } | null
    trial: { eligible_days_total: number; counts: string }
  }
  can_activate: boolean
  blockers: ActivationBlocker[]
}

/** POST /api/v1/activations */
export type ActivateResponse =
  | {
      ok: true
      activation_id: string
      agent: 'spark' | 'flame'
      account_mask: string
      trial: { status: string; eligible_days_used: number; eligible_days_total: number }
    }
  | { ok: false; blockers?: ActivationBlocker[]; message?: string; current_preview_hash?: string }
