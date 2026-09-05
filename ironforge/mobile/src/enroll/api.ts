/**
 * Enrollment network calls (UAT #6, PR A). Every function here is a thin wrapper over
 * `api()` against the SAME v1 endpoints the web /enroll/* screens call
 * (webapp/src/app/enroll/useEnrollment.ts, BrokerClient.tsx, AgentClient.tsx,
 * ReviewClient.tsx) — no forked flow logic, per the build brief.
 */
import { api } from '@/api/client'
import type {
  EnrollmentResumeResponse,
  SetPlanResponse,
  GetLegalResponse,
  AcceptancesResponse,
  PlanCatalog,
  MembershipCheck,
  BrokerConnectionsResponse,
  SelectBrokerAccountResponse,
  AgentConfigResponse,
  ActivationPreview,
  ActivateResponse,
} from './types'

/** Create-or-resume. Called on mount of every /enroll/* screen, same as the web. */
export function resumeEnrollment(source = 'mobile_enroll'): Promise<EnrollmentResumeResponse> {
  return api<EnrollmentResumeResponse>('/api/v1/enrollments', { method: 'POST', body: { source } })
}

export function choosePlan(enrollmentId: string, plan: string): Promise<SetPlanResponse> {
  return api<SetPlanResponse>(`/api/v1/enrollments/${enrollmentId}/plan`, { method: 'PUT', body: { plan } })
}

export function getLegal(enrollmentId: string): Promise<GetLegalResponse> {
  return api<GetLegalResponse>(`/api/v1/enrollments/${enrollmentId}/legal`)
}

export function acceptLegal(
  enrollmentId: string,
  accepted: string[],
  signatureName?: string,
): Promise<AcceptancesResponse> {
  return api<AcceptancesResponse>(`/api/v1/enrollments/${enrollmentId}/acceptances`, {
    method: 'POST',
    body: signatureName ? { accepted, signature_name: signatureName } : { accepted },
  })
}

/** GET /api/public/plans — additive, unauthenticated. Real prices, never a mock constant. */
export function getPlanCatalog(): Promise<PlanCatalog> {
  return api<PlanCatalog>('/api/public/plans')
}

/** "I already subscribed on the web" (billing step) — reads entitlement, starts nothing. */
export function checkMembership(): Promise<MembershipCheck> {
  return api<MembershipCheck>('/api/billing/membership')
}

/** Same route the web /enroll/broker and mobile Agents screen already use. */
export function getBrokerConnections(): Promise<BrokerConnectionsResponse> {
  return api<BrokerConnectionsResponse>('/api/brokerage/connections')
}

export function selectBrokerAccount(
  enrollmentId: string,
  brokerAccountId: string,
): Promise<SelectBrokerAccountResponse> {
  return api<SelectBrokerAccountResponse>(`/api/v1/enrollments/${enrollmentId}/broker-account`, {
    method: 'PUT',
    body: { broker_account_id: brokerAccountId },
  })
}

/**
 * Starts the Tradier OAuth round trip. `redirectURI` is opened in an auth session by
 * the caller — this only mints it. `return_to: 'enroll'` is honored by the WEB branch
 * of the callback; the MOBILE branch of that same callback (tradier/callback/route.ts)
 * always deep-links to /account/brokerage regardless of return_to (a real mismatch vs
 * this build's brief — see the PR description). The broker screen listens for that
 * actual return route, not /enroll/broker, so the round trip still completes correctly.
 */
export function startTradierConnect(): Promise<{ ok: true; redirectURI: string }> {
  return api<{ ok: true; redirectURI: string }>('/api/onboarding/brokerage/tradier/connect', {
    method: 'POST',
    body: { return_to: 'enroll' },
  })
}

export function createAgentConfig(
  agentCode: 'spark' | 'flame',
  brokerAccountId: string,
): Promise<AgentConfigResponse> {
  return api<AgentConfigResponse>('/api/v1/agent-configs', {
    method: 'POST',
    body: { agent_code: agentCode, broker_account_id: brokerAccountId, config: {} },
  })
}

export function previewActivation(configId: string): Promise<ActivationPreview> {
  return api<ActivationPreview>('/api/v1/activations/preview', { method: 'POST', body: { config_id: configId } })
}

export function activate(opts: {
  configId: string
  previewHash: string
  riskAcknowledged: boolean
  authorizationAcknowledged: boolean
  idempotencyKey: string
}): Promise<ActivateResponse> {
  return api<ActivateResponse>('/api/v1/activations', {
    method: 'POST',
    headers: { 'Idempotency-Key': opts.idempotencyKey },
    body: {
      config_id: opts.configId,
      preview_hash: opts.previewHash,
      risk_acknowledged: opts.riskAcknowledged,
      authorization_acknowledged: opts.authorizationAcknowledged,
    },
  })
}

export function confirmationSeen(activationId: string): Promise<{ ok: true }> {
  return api<{ ok: true }>(`/api/v1/activations/${activationId}/confirmation-seen`, { method: 'POST' })
}
